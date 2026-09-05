"""职业画像 / 职业方向档案 API。

方向档案与当前方向全局共享（所有用户的 AI 功能按同一方向出题）；
画像属于内置管理员（admin）本人，仅其可读写与 AI 生成。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user, require_builtin_admin
from app.database import get_session
from app.models import Resume, User
from app.routers.ai import _call_llm, _parse_json_loose
from app.routers.audit import client_ip, log_action
from app.routers.settings import get_ai_config
from app.tracks import (
    EMPTY_PROFILE,
    build_profile_text,
    get_current_track,
    get_custom_dimensions,
    get_profile,
    get_track,
    list_tracks,
    set_current_track,
    set_custom_dimensions,
    set_profile,
)

router = APIRouter()

# 画像允许写入的字段白名单（track_key 允许为空 = 未判定）
_PROFILE_FIELDS = {"track_key", "years", "headline", "skills", "strengths", "gaps", "summary"}


class ProfileUpdate(BaseModel):
    track_key: Optional[str] = None
    years: Optional[int] = None
    headline: Optional[str] = None
    skills: Optional[list[str]] = None
    strengths: Optional[list[str]] = None
    gaps: Optional[list[str]] = None
    summary: Optional[str] = None


class TrackSwitch(BaseModel):
    key: str


class ProfileGenerateRequest(BaseModel):
    resume_id: Optional[int] = None


class CustomDimsUpdate(BaseModel):
    dimensions: list[str]


PROFILE_PROMPT = """你是职业发展顾问。基于下面的简历内容，为求职者生成一份「职业画像」，后续 AI 出题、简历体检、模拟面试都会参考它。

【候选职业方向】track_key 必须从下面选一个最匹配的：
{track_options}

只输出一个 JSON 对象，不要任何解释或前后缀：
{{
  "track_key": "最匹配的方向 key",
  "years": 工作年限数字（整数，无法判断填 null）,
  "headline": "一句话画像，如：8 年 Java 后端，主攻高并发与稳定性建设",
  "skills": ["技能栈清单 8-15 项，具体不空泛，按熟练度从高到低"],
  "strengths": ["职业优势 2-4 条，须有简历依据"],
  "gaps": ["相对所选方向的明显短板或空白 1-3 条，没有则给空数组"],
  "summary": "两三句职业概述：方向、领域、层级、核心亮点"
}}

要求：所有内容必须基于简历真实信息，禁止编造简历中不存在的经历；判断方向以工作经历与项目所用技术为主。

简历内容：
----- 开始 -----
{content}
----- 结束 -----"""


@router.get("/career/overview")
def career_overview(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """方向档案列表 + 当前方向。所有登录用户可读（题库维度预设依赖它）。"""
    return {"tracks": list_tracks(), "current_key": get_current_track(session)["key"]}


@router.put("/career/track")
def switch_track(
    body: TrackSwitch,
    session: Session = Depends(get_session),
    user: User = Depends(require_builtin_admin),
    request: Request = None,
):
    if get_track(body.key) is None:
        raise HTTPException(status_code=404, detail="职业方向不存在")
    old = get_current_track(session)["key"]
    if old != body.key:
        set_current_track(session, body.key)
        session.commit()
        log_action(
            session, "career.track", user=user, target=body.key,
            detail=f"{old} → {body.key}", ip=client_ip(request) if request else None,
        )
        session.commit()
    return {"ok": True, "current_key": body.key}


def _clean_profile(data: dict) -> dict:
    """按白名单裁剪并规范画像字段。"""
    profile = dict(EMPTY_PROFILE)
    for k in _PROFILE_FIELDS & set(data.keys()):
        v = data[k]
        if k in ("skills", "strengths", "gaps"):
            if isinstance(v, list):
                profile[k] = [str(x).strip() for x in v if str(x).strip()][:20]
        elif k == "years":
            try:
                profile[k] = max(0, min(60, int(v)))
            except (TypeError, ValueError):
                profile[k] = None
        else:
            profile[k] = str(v or "").strip()[:500]
    return profile


@router.get("/career/profile")
def read_profile(
    session: Session = Depends(get_session),
    user: User = Depends(require_builtin_admin),
):
    return get_profile(session)


@router.put("/career/profile")
def save_profile(
    body: ProfileUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(require_builtin_admin),
):
    profile = get_profile(session)
    patch = body.model_dump(exclude_none=True)
    if "track_key" in patch and patch["track_key"] and get_track(patch["track_key"]) is None:
        raise HTTPException(status_code=404, detail="职业方向不存在")
    profile.update(_clean_profile(patch))
    set_profile(session, profile)
    session.commit()
    log_action(session, "career.profile", user=user, target="update")
    session.commit()
    return profile


@router.post("/career/profile/generate")
def generate_profile(
    body: ProfileGenerateRequest,
    session: Session = Depends(get_session),
    user: User = Depends(require_builtin_admin),
):
    """从简历 AI 生成职业画像：指定简历优先，否则默认简历。生成后直接落库。"""
    cfg = get_ai_config(session)
    if not cfg["api_key"]:
        raise HTTPException(status_code=400, detail="尚未配置 AI API Key，请先到「设置」中填写")

    resume: Resume | None = None
    if body.resume_id is not None:
        resume = session.get(Resume, body.resume_id)
        if resume is None or resume.user_id != user.id:
            raise HTTPException(status_code=404, detail="简历不存在")
    if resume is None:
        resume = session.exec(
            select(Resume)
            .where(Resume.user_id == user.id)
            .order_by(Resume.is_default.desc(), Resume.created_at.desc())
        ).first()
    if resume is None:
        raise HTTPException(status_code=400, detail="还没有简历，请先到「简历库」上传")
    content = (resume.structured or resume.text or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="该简历没有文本内容，请重新上传 PDF / DOCX")

    options = "\n".join(f"- {t['key']}：{t['name']}（{t['tagline']}）" for t in list_tracks())
    prompt = PROFILE_PROMPT.replace("{track_options}", options).replace("{content}", content[:12000])
    raw = _call_llm(cfg["base_url"], cfg["model"], cfg["api_key"], prompt)
    data = _parse_json_loose(raw)
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="AI 返回内容无法解析，请重试")
    profile = _clean_profile(data)
    if profile["track_key"] and get_track(profile["track_key"]) is None:
        profile["track_key"] = ""
    set_profile(session, profile)
    session.commit()
    log_action(session, "career.profile", user=user, target="generate", detail=resume.name)
    session.commit()
    return profile


@router.put("/career/dimensions")
def save_custom_dims(
    body: CustomDimsUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(require_builtin_admin),
):
    """维护自定义考察维度（交叉背景用，如「大模型」「数通/网络协议」）。"""
    set_custom_dimensions(session, body.dimensions)
    session.commit()
    log_action(session, "career.dimensions", user=user, target="update")
    session.commit()
    return {"dimensions": get_custom_dimensions(session)}


@router.get("/career/context")
def career_context(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """当前方向 + 画像文本（AI 相关功能注入用）。"""
    return {
        "current_key": get_current_track(session)["key"],
        "profile_text": build_profile_text(session),
    }
