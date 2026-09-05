"""岗位情报：五大板块 Markdown 情报 + 多渠道资料收集 + AI 生成。

信息渠道（按优先级）：
1. 参考材料：抓取的网页（直连 / CDP 浏览器兜底）与手动粘贴的资料；
2. 本地数据：JD、城市、薪资、关联简历；
3. 模型公开知识：仅限广为人知的事实，须标注「公开资料，建议核实」。

写作铁律：拿不准的一律不写，宁少勿编。
"""
import re
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user
from app.database import get_session
from app.models import NOTE_TYPES, Opportunity, ResearchMaterial, ResearchNote, Resume, User
from app.routers.ai import _call_llm, _extract_site_page, _fetch_url, _strip_html
from app.routers.settings import get_ai_config, get_browser_config

router = APIRouter()

NOTE_TYPE_LABELS = {
    "company": "公司调研",
    "team": "团队与业务调研",
    "tech": "技术栈调研",
    "self_intro": "自我介绍稿",
    "ask_back": "反问清单",
    "employee": "员工评价",
}


class NoteUpdate(BaseModel):
    content: str = ""
    ai_generated: bool = False


class OutlineRequest(BaseModel):
    overwrite: bool = False


class MaterialFetchRequest(BaseModel):
    urls: list[str] = []
    manual_text: str = ""
    manual_title: str = ""


def _get_opportunity(session: Session, opportunity_id: int, user: User) -> Opportunity:
    """取当前用户的岗位；不存在或越权一律 404。"""
    opp = session.get(Opportunity, opportunity_id)
    if opp is None or opp.user_id != user.id:
        raise HTTPException(status_code=404, detail="岗位不存在")
    return opp


def _note_dict(note: ResearchNote) -> dict:
    return {
        "id": note.id,
        "opportunity_id": note.opportunity_id,
        "note_type": note.note_type,
        "content": note.content,
        "ai_generated": note.ai_generated,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    }


@router.get("/opportunities/{opportunity_id}/notes")
def list_notes(
    opportunity_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _get_opportunity(session, opportunity_id, user)
    rows = session.exec(
        select(ResearchNote).where(ResearchNote.opportunity_id == opportunity_id)
    ).all()
    return {"items": [_note_dict(n) for n in rows]}


@router.put("/opportunities/{opportunity_id}/notes/{note_type}")
def save_note(
    opportunity_id: int,
    note_type: str,
    body: NoteUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if note_type not in NOTE_TYPES:
        raise HTTPException(status_code=404, detail="未知的笔记类型")
    _get_opportunity(session, opportunity_id, user)

    note = session.exec(
        select(ResearchNote).where(
            ResearchNote.opportunity_id == opportunity_id,
            ResearchNote.note_type == note_type,
        )
    ).first()
    if note is None:
        note = ResearchNote(
            opportunity_id=opportunity_id, note_type=note_type, user_id=user.id
        )
    note.content = body.content
    note.ai_generated = body.ai_generated
    note.updated_at = datetime.now()
    session.add(note)
    session.commit()
    session.refresh(note)
    return _note_dict(note)


@router.delete("/opportunities/{opportunity_id}/notes/{note_type}")
def delete_note(
    opportunity_id: int,
    note_type: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _get_opportunity(session, opportunity_id, user)
    note = session.exec(
        select(ResearchNote).where(
            ResearchNote.opportunity_id == opportunity_id,
            ResearchNote.note_type == note_type,
        )
    ).first()
    if note is None:
        raise HTTPException(status_code=404, detail="该笔记尚不存在")
    session.delete(note)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------- 参考材料


def _material_dict(m: ResearchMaterial, preview: bool = True) -> dict:
    return {
        "id": m.id,
        "source_type": m.source_type,
        "title": m.title,
        "url": m.url,
        "content": (m.content[:400] + "…") if preview and len(m.content) > 400 else m.content,
        "size": len(m.content),
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


@router.get("/opportunities/{opportunity_id}/materials")
def list_materials(
    opportunity_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _get_opportunity(session, opportunity_id, user)
    rows = session.exec(
        select(ResearchMaterial)
        .where(ResearchMaterial.opportunity_id == opportunity_id)
        .order_by(ResearchMaterial.created_at.desc())  # type: ignore[attr-defined]
    ).all()
    return {"items": [_material_dict(m) for m in rows]}


def _title_from_html(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    if not m:
        return ""
    return _strip_html(m.group(1))[:80]


_LOGIN_WALL_KEYWORDS = ("登录", "登陆", "扫码", "验证码", "请先注册", "log in", "sign in")


def _looks_like_login_wall(text: str) -> bool:
    """整篇都很短且登录提示词密集时，判定为登录墙空壳；长正文即使带登录词也放行。"""
    if len(text) >= 1000:
        return False
    return sum(1 for k in _LOGIN_WALL_KEYWORDS if k in text.lower()) >= 2


def _fetch_material(session: Session, url: str) -> ResearchMaterial:
    """抓取单个 URL：先服务端直抓，内容过少或失败时回退 CDP 浏览器抓取。"""
    title, text, via = "", "", "url"
    try:
        html = _fetch_url(url)
        text = _strip_html(html)
        title = _title_from_html(html)
    except Exception:
        text = ""
    if len(text) < 400:
        # 直抓失败 / SPA 空壳 / 被反爬拦截：走用户自己的浏览器（真实指纹 + 登录态）
        cdp = get_browser_config(session)["cdp_endpoint"]
        page = _extract_site_page(url, cdp, require_jd=False)
        title, text, via = page.get("title", ""), page.get("text", ""), "browser"
    return ResearchMaterial(
        opportunity_id=0,  # 由调用方回填
        source_type=via,
        title=title or url[:80],
        url=url,
        content=text.strip()[:8000],
    )


@router.post("/opportunities/{opportunity_id}/materials")
def add_materials(
    opportunity_id: int,
    body: MaterialFetchRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _get_opportunity(session, opportunity_id, user)
    saved, failed, duplicates = [], [], []

    existing_urls = {
        m.url
        for m in session.exec(
            select(ResearchMaterial).where(
                ResearchMaterial.opportunity_id == opportunity_id
            )
        ).all()
        if m.url
    }

    for url in body.urls:
        url = url.strip()
        if not url:
            continue
        if not url.startswith(("http://", "https://")):
            failed.append({"url": url, "error": "链接需以 http(s):// 开头"})
            continue
        if url in existing_urls:
            duplicates.append(url)
            continue
        try:
            m = _fetch_material(session, url)
            if len(m.content) < 300 or _looks_like_login_wall(m.content):
                failed.append({"url": url, "error": "抓到的正文过少或是登录墙，未作为资料保存"})
                continue
            m.opportunity_id = opportunity_id
            m.user_id = user.id
            session.add(m)
            session.commit()
            session.refresh(m)
            existing_urls.add(url)
            saved.append(_material_dict(m))
        except HTTPException as e:
            failed.append({"url": url, "error": str(e.detail)[:160]})
        except Exception as e:
            failed.append({"url": url, "error": f"{type(e).__name__}: {str(e)[:120]}"})

    if body.manual_text.strip():
        m = ResearchMaterial(
            opportunity_id=opportunity_id,
            user_id=user.id,
            source_type="manual",
            title=body.manual_title.strip() or "粘贴的资料",
            url=None,
            content=body.manual_text.strip()[:8000],
        )
        session.add(m)
        session.commit()
        session.refresh(m)
        saved.append(_material_dict(m))

    return {"saved": saved, "failed": failed, "duplicates": duplicates}


@router.delete("/opportunities/{opportunity_id}/materials/{material_id}")
def delete_material(
    opportunity_id: int,
    material_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _get_opportunity(session, opportunity_id, user)
    m = session.get(ResearchMaterial, material_id)
    if m is None or m.opportunity_id != opportunity_id:
        raise HTTPException(status_code=404, detail="资料不存在")
    session.delete(m)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------- 自动调研


def _auto_sources(company: str) -> list[tuple[str, str]]:
    """按公司名生成候选情报来源（label, url）。"""
    q = quote(company)
    return [
        ("维基百科", f"https://zh.wikipedia.org/zh-cn/{q}"),
        ("百度百科", f"https://baike.baidu.com/item/{q}"),
        ("企查查", f"https://www.qcc.com/web/search?key={q}"),
        ("爱企查", f"https://aiqicha.baidu.com/s?q={q}"),
        ("小红书", f"https://www.xiaohongshu.com/search_result_ai?keyword={quote(company + ' 面试')}&source=web_explore_feed"),
        ("知乎", f"https://www.zhihu.com/search?type=content&q={quote(company + ' 面试 怎么样')}"),
        ("脉脉", f"https://maimai.cn/web/search_center?highlight=true&query={quote(company)}&type=feed"),
        # 员工相关
        ("脉脉·加班评价", f"https://maimai.cn/web/search_center?highlight=true&query={quote(company + ' 加班')}&type=feed"),
        ("小红书·工作体验", f"https://www.xiaohongshu.com/search_result_ai?keyword={quote(company + ' 工作体验')}&source=web_explore_feed"),
        ("知乎·工作体验", f"https://www.zhihu.com/search?type=content&q={quote(company + ' 工作体验 加班 福利')}"),
        ("职友集", f"https://www.jobui.com/search/?keyword={q}"),
    ]


@router.post("/opportunities/{opportunity_id}/notes/auto-research")
def auto_research(
    opportunity_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """自动调研：按公司名到多个公开渠道收集资料，逐源容错，成功的存为参考材料。"""
    opp = _get_opportunity(session, opportunity_id, user)
    saved, failed, duplicates = [], [], []

    existing_urls = {
        m.url
        for m in session.exec(
            select(ResearchMaterial).where(
                ResearchMaterial.opportunity_id == opportunity_id
            )
        ).all()
        if m.url
    }

    for label, url in _auto_sources(opp.company):
        if url in existing_urls:
            duplicates.append(label)
            continue
        try:
            m = _fetch_material(session, url)
            m.title = f"{label}·{m.title or opp.company}"[:90]
            if len(m.content) < 400 or _looks_like_login_wall(m.content):
                failed.append({
                    "source": label,
                    "error": "需要登录或被反爬拦截——可在专用浏览器登录该站点后，通过「抓取资料」手动重试",
                })
                continue
            m.opportunity_id = opportunity_id
            m.user_id = user.id
            session.add(m)
            session.commit()
            session.refresh(m)
            existing_urls.add(url)
            saved.append(_material_dict(m))
        except HTTPException as e:
            err = str(e.detail)[:160]
            if "BOSS" in err or "招聘" in err or "登录" in err:
                # 底层抓取的报错文案是职位提取场景的，自动调研场景统一成中性描述
                err = "该渠道需要登录或被反爬拦截——在专用浏览器中登录该站点后重试即可"
            failed.append({"source": label, "error": err})
        except Exception as e:
            failed.append({"source": label, "error": f"{type(e).__name__}: {str(e)[:120]}"})

    return {"saved": saved, "failed": failed, "duplicates": duplicates}


# ---------------------------------------------------------------- AI 情报生成

_OUTLINE_HINTS = {
    "company": """请输出「公司调研」情报（Markdown）。围绕：
1. 主营业务与产品线；2. 商业模式与主要收入来源；3. 公司规模 / 融资 / 上市状态；
4. 行业地位与主要竞品对比；5. 近期动态（新产品、组织调整、财报要点）；
6. 技术团队规模与工程文化线索；7. 风险与口碑（加班情况、业务稳定性）。
有资料或公开常识支撑的小节直接写事实；没有的只留小节标题，附「该查什么、去哪查」的检查项。""",
    "team": """请输出「团队与业务调研」情报（Markdown）。围绕：
1. 该岗位所属部门 / 业务线的定位与价值（从 JD 职责反推）；
2. 团队规模与分工推测；3. 团队可能使用的技术栈与基建（从 JD 技能要求反推）；
4. 该业务当前的核心指标与挑战；5. 面试中值得向面试官确认的问题清单。
有依据的直接写并说明依据（如「从 JD 第 3 条可推断」）；推测性的内容标注「（推测）」。""",
    "tech": """请输出「技术栈调研」情报（Markdown）：从 JD 中提取全部技术关键词，逐项展开：
- 该技术在该公司业务中可能的用途（结合业务线推测）；
- 核心概念与原理要点（面试高频角度）；
- 结合我的简历，可能被追问的问题方向。
按「必须精通 / 重点熟悉 / 了解即可」分层排序。这部分主要基于 JD 与简历，不需要外部资料。""",
    "self_intro": """请输出「自我介绍稿」（Markdown），包含两版：
1. **1 分钟版**（电话 / HR 初筛用）：开场 → 核心经历与量化结果 → 与该岗位的契合点 → 求职动机；
2. **3 分钟版**（技术面开场用）：在 1 分钟版基础上展开重点项目（背景-方案-结果）、技术亮点。
要求：只使用简历中真实存在的内容，禁止编造经历与数字；突出与该 JD 的匹配点；
在正文中用「【检查】」标注需要用户核对或替换成真实数字的位置。""",
    "employee": """请输出「员工评价」情报（Markdown），围绕：
1. 工作强度与加班情况（是否大小周、常态化加班、弹性工作）；
2. 薪资福利（社保公积金缴纳基数与比例、补贴、年终奖惯例、调薪机制）；
3. 团队氛围与管理风格；4. 离职率、裁员与业务稳定性动态；
5. 员工的真实好评与差评（分开列出，标注来源渠道）。
评价类内容必须有来源依据；没有可靠来源的部分宁缺毋滥，只给「去哪查」的检查项。""",
    "ask_back": """请输出「反问清单」（Markdown），按场景分组：
1. 问业务（业务方向、目标与挑战）；2. 问团队（规模、分工、技术演进）；
3. 问成长（培养机制、技术氛围、晋升路径）；4. 问流程（后续轮次安排与反馈时间）。
每个反问附一句「为什么问 / 能获得什么信息」；要求体现对该公司做过功课（可引用 JD 内容），
避免薪资加班等敏感话题（留到 Offer 阶段）。共 8-12 条。""",
}

WRITING_RULES = """写作原则（严格遵守）：
1. 信息优先级：参考资料 > JD 与简历 > 广为人知的公开常识；
2. 广为人知的常识（如知名公司的主营业务、产品线、总部城市）可以直接写，句末标注「（公开资料，建议核实）」；
3. 拿不准的一律不写：禁止编造数字、日期、融资金额、组织架构与任何内部信息——宁少勿编，内容短不代表不完整；
4. 缺资料的小节只保留标题和「去哪里查、查什么」的检查项（如：看准网查面试评价、官网查产品线）；
5. 直接输出 Markdown 正文，不要输出任何解释性文字。"""


def _materials_block(session: Session, opportunity_id: int) -> str:
    rows = session.exec(
        select(ResearchMaterial)
        .where(ResearchMaterial.opportunity_id == opportunity_id)
        .order_by(ResearchMaterial.created_at.desc())  # type: ignore[attr-defined]
    ).all()
    if not rows:
        return "（暂无参考资料——请依靠 JD、简历与广为人知的公开常识；不了解的内容不要写）"
    blocks = []
    for m in rows:
        source = m.url or "手动粘贴"
        blocks.append(f"——《{m.title}》（来源：{source}）：\n{m.content[:2500]}")
    return "\n\n".join(blocks)[:9000]


def _outline_prompt(
    session: Session, opp: Opportunity, note_type: str, resume_text: str | None
) -> str:
    jd = (opp.jd_text or "").strip() or "（未提供 JD）"
    department = f"，部门 / 业务线：{opp.department}" if opp.department else ""
    city_salary = "、".join(
        filter(
            None,
            [f"城市：{opp.city}" if opp.city else "", f"薪资：{opp.salary_range}" if opp.salary_range else ""],
        )
    ) or "未填写"
    resume_block = ""
    if note_type in ("self_intro", "tech") and resume_text:
        resume_block = f"\n\n【我的简历摘要】\n{resume_text[:6000]}"
    materials = _materials_block(session, opp.id)
    hint = _OUTLINE_HINTS[note_type]
    return f"""你是一位资深求职辅导顾问。候选人正在准备 {opp.company} 的「{opp.position}」岗位面试（{department}；{city_salary}）。

【JD】
{jd}{resume_block}

【已收集的参考资料】
{materials}

{hint}

{WRITING_RULES}

输出开头：# {NOTE_TYPE_LABELS[note_type]}：{opp.company} · {opp.position}"""


@router.post("/opportunities/{opportunity_id}/notes/{note_type}/outline")
def generate_outline(
    opportunity_id: int,
    note_type: str,
    body: OutlineRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if note_type not in NOTE_TYPES:
        raise HTTPException(status_code=404, detail="未知的笔记类型")
    opp = _get_opportunity(session, opportunity_id, user)

    existing = session.exec(
        select(ResearchNote).where(
            ResearchNote.opportunity_id == opportunity_id,
            ResearchNote.note_type == note_type,
        )
    ).first()
    if existing is not None and existing.content.strip() and not body.overwrite:
        raise HTTPException(status_code=409, detail="该笔记已有内容，覆盖生成请携带 overwrite=true")

    resume_text = None
    if opp.resume_id:
        resume = session.get(Resume, opp.resume_id)
        if resume is not None and resume.user_id == user.id:
            resume_text = resume.structured or resume.text

    cfg = get_ai_config(session)
    if not cfg["api_key"]:
        raise HTTPException(status_code=400, detail="尚未配置 AI，请先在「设置」中填写 API Key")

    raw = _call_llm(
        cfg["base_url"], cfg["model"], cfg["api_key"],
        _outline_prompt(session, opp, note_type, resume_text),
        max_tokens=8192,
    )
    content = raw.strip()
    if not content:
        raise HTTPException(status_code=502, detail="AI 未返回内容，请重试")

    if existing is None:
        existing = ResearchNote(
            opportunity_id=opportunity_id, note_type=note_type, user_id=user.id
        )
    existing.content = content
    existing.ai_generated = True
    existing.updated_at = datetime.now()
    session.add(existing)
    session.commit()
    session.refresh(existing)
    return _note_dict(existing)
