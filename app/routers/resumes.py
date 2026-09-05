"""简历版本库：上传、下载、文本抽取（PDF/DOCX）、AI 结构化 / 体检 / 预测题、管理。"""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user
from app.database import DATA_DIR, get_session
from app.models import Resume, User
from app.routers.ai import _call_llm, _parse_json_loose
from app.routers.settings import get_ai_config

router = APIRouter()

UPLOAD_DIR = DATA_DIR / "uploads" / "resumes"
ALLOWED_EXTS = {".pdf", ".doc", ".docx"}
MAX_SIZE = 20 * 1024 * 1024  # 20MB

STRUCTURE_PROMPT = """你是简历整理助手。下面是从一份 PDF/Word 简历中机器抽取的文本，抽取过程可能存在顺序错乱、断行破碎、栏目内容混在一起等问题。
请将其整理为结构清晰的 Markdown，严格遵守：
1. 固定输出以下板块（用 ## 二级标题），板块按此顺序排列：
## 个人信息
## 教育背景
## 专业技能
## 工作经历
## 项目经历
2. 每个板块内部条目按原文出现顺序排列；原文确实没有的板块，标题下写「（原文未提供）」。
3. 只做格式修复：合并断行、把被拆散的条目归回原位、修正顺序错乱与明显错字；**严格保留原文信息，禁止编造、推测或删除任何实质内容**（公司名、时间、数字必须与原文一致）。
4. 时间段（如 2019.06 - 2022.07）原样保留，不要换算或省略。
5. **层级结构**（工作经历、项目经历必须遵守）：
   - 每段工作/每个项目是一个一级条目（"- " 开头），概要格式：公司或项目名 + 职位/角色 + 时间
   - 条目下的「工作职责」「核心工作」「项目描述」「主要业绩」「技术栈」等内容，用缩进两个空格的二级列表（"  - " 开头）挂在所属条目之下
   - 二级条目（如「核心工作」）若还罗列了具体事项，再用缩进四个空格的三级列表（"    - " 开头）逐条列出
   - **严禁把子内容与主条目排成同级**；每一行只放一件事
6. 少量不属于五大板块的内容（证书、自我评价等），放入末尾「## 其他信息」；没有则不要输出该板块。
7. 只输出 Markdown，不要任何解释。

简历原始文本：
----- 开始 -----
{content}
----- 结束 -----"""


def _structure_with_ai(session: Session, raw: str) -> str:
    """调用 AI 将简历原始文本整理为 5 大板块 Markdown；失败抛 HTTPException。"""
    cfg = get_ai_config(session)
    if not cfg["api_key"]:
        raise HTTPException(status_code=400, detail="尚未配置 AI，请先在「设置」中填写 API Key")
    prompt = STRUCTURE_PROMPT.replace("{content}", raw[:12000])
    md = _call_llm(cfg["base_url"], cfg["model"], cfg["api_key"], prompt).strip()
    if "##" not in md:
        raise HTTPException(status_code=502, detail=f"AI 返回内容无法解析：{md[:200]}")
    return md


def _resume_ai_content(r: Resume) -> str:
    """优先用 AI 整理后的结构化内容，否则用抽取原文。"""
    content = r.structured or r.text
    if not content:
        raise HTTPException(
            status_code=400,
            detail="简历没有文本内容，请先上传支持抽取的格式（PDF / DOCX）",
        )
    return content[:12000]


REVIEW_PROMPT = """你是资深技术面试官与简历顾问。基于下面的简历内容做一次「简历体检」：先逐维打分，再推导总分，最后给优化建议。

【评分口径】目标岗位默认为 Java 后端/服务端开发；若求职者补充背景中有说明，则按背景评估。分数的含义是「这份简历投递目标岗位时，通过简历筛选（拿到面试机会）的竞争力判断」，不是简历质量的百分比：
- 95+ 竞争力极强，大厂筛选也几乎必得面试机会；
- 85-94 稳过主流公司筛选，容易拿到面试；
- 70-84 中小厂大概率过筛，投大厂有风险；
- 55-69 过筛困难，需明显修改后再投；
- 55 以下基本过不了筛，需要重写核心板块。
禁止把正常简历都聚在 75-90：达到目标岗位的筛选期望就应给 85+。

【五个维度各打 1-5 分】（5 分指「优秀」而非「完美无瑕」）：
- completeness 内容完整性：5=教育 / 技能 / 工作 / 项目板块齐全，每段经历有角色、时间、技术栈与结果；4=缺个别非关键项；3=有板块缺失或经历普遍缺结果；2=经历残缺、要素不全；1=结构性缺失。
- quantification 亮点与量化程度（简历是筛选文档，量化就是硬通货，此处按高标准要求）：5=核心经历普遍有量化结果且口径经得起追问；4=主要经历有量化、部分缺失；3=偶有数字、以职责罗列为主；2=几乎纯职责描述；1=没有任何可验证的成果表述。to B / 内部系统缺业务数据时，可用技术口径指标（规模、延迟、吞吐、覆盖率）替代，不算缺量化。
- credibility 经历说服力：5=贡献边界清晰、技术选型有理由、复杂度可感知、经得起深挖；4=多数经历具体可信；3=概述性描述多、深挖易露怯；2=套话多、贡献模糊；1=有明显注水或前后矛盾痕迹。
- concision 表达简洁度：5=动词开头、一条一事、无废话；4=基本简洁、偶有冗长；3=有堆砌与重复；2=明显啰嗦、长段大段；1=表述混乱难读。
- relevance 岗位匹配度：5=技能与经历精准对准目标岗位方向；4=主体对口；3=有关联但重点偏移；2=方向错位明显；1=基本不对口。

【总分推导】基础分 = 各维度得分折成百分制（(评分-1)÷4×100）后按权重加权：内容完整性 15%、亮点与量化 25%、经历说服力 25%、表达简洁 15%、岗位匹配 20%；最终 score 只允许在基础分 ±5 内微调，必须与维度分满足该推导关系。

【优化建议】给出 6-8 条 suggestions，按重要性从高到低排序。每条：
- title：一句话概括问题
- detail：具体怎么改，必须引用简历中的真实位置与内容举例（如「工作经历第 2 条的 QPS 数字缺少压测口径」）
- level："high"（硬伤必须改）/"mid"（明显加分）/"low"（锦上添花）
要求：建议必须基于简历真实内容、具体到条目，禁止泛泛而谈，禁止编造简历中不存在的信息；若提供了求职者补充背景，评估口径（目标方向、诉求、特殊情况）必须与背景保持一致。

只输出 JSON（不要输出任何其他内容）：
{{"score": 82, "dimensions": {{"completeness": 4, "quantification": 3, "credibility": 4, "concision": 4, "relevance": 4}}, "suggestions": [{{"title": "...", "detail": "...", "level": "high"}}]}}

简历内容：
----- 开始 -----
{content}
----- 结束 -----

求职者补充背景（体检的重要依据，未提供则为「（未提供）」）：
{background}"""


QUESTIONS_PROMPT = """你是技术面试官。基于下面的简历内容，预测面试中最可能被问到的问题：
1. 出 8 道题：优先针对简历中的具体项目、数字、技术选型做「追问式」出题（如「你提到 QPS 5w，怎么压测出来的？」），再补充对应技能栈的深度题。
2. 每题字段：
   - tag：考察维度，必须从这些值里选（与题库维度一致）：项目深挖/系统设计/场景设计/语言特性/JUC/JVM/MySQL/Redis/消息队列/分布式/微服务/计算机网络/算法/软素质，纯技能八股优先用具体技术维度（如 MySQL/Redis），匹配不上才用「其他」
   - q：问题
   - a：参考答案要点，3-5 条，每条独占一行并以「1. 2. 3.」编号，关键词用 **加粗** 标出，结合简历真实内容
   - full：完整答案（口述版），面试现场可以直接说出来的第一人称完整表述：先用一句话给核心结论（独占一行），再分 2-4 个要点，每个要点独占一行、以「1. 2. 3.」编号、用两三句话展开，关键词用 **加粗** 标出；总长 250-400 字，不要寒暄和总结陈词，内容必须能用上简历中的项目/经历
3. 禁止出与简历无关的通用套题；答案要点与完整答案必须能用上简历中的经历。
4. 若提供了求职者补充背景（目标方向、求职诉求、特殊情况如 Gap/转行/离职原因），出题和答案必须结合背景调整：面向目标岗位出题，并可包含 1 道 friendly 表述的动机/规划类问题。
5. 若下方指定了「出题方向」，全部题目必须围绕该方向展开（仍基于简历真实内容，tag 也按该方向归类）；未指定则按第 1 条综合出题。
只输出 JSON：{"questions": [{"tag": "项目深挖", "q": "...", "a": "...", "full": "..."}]}

简历内容：
----- 开始 -----
{content}
----- 结束 -----

求职者补充背景（出题的重要依据，未提供则为「（未提供）」）：
{background}

出题方向（指定后所有题目聚焦该方向；未指定则为「（未指定，综合出题）」）：
{direction}"""


DIM_WEIGHTS = {
    "completeness": 0.15,
    "quantification": 0.25,
    "credibility": 0.25,
    "concision": 0.15,
    "relevance": 0.20,
}


def _parse_dimensions(raw) -> dict | None:
    """五维 1-5 分；任一维缺失或非法则返回 None（不参与总分推导）。"""
    if not isinstance(raw, dict):
        return None
    dims = {}
    for key in DIM_WEIGHTS:
        try:
            dims[key] = max(1, min(5, int(raw.get(key))))
        except (TypeError, ValueError):
            return None
    return dims


def _get_owned_resume(session: Session, resume_id: int, user: User) -> Resume:
    """取当前用户的简历；不存在或越权一律 404。"""
    r = session.get(Resume, resume_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(status_code=404, detail="简历不存在")
    return r


@router.post("/resumes/{resume_id}/review")
def review_resume(
    resume_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """AI 简历体检：五维打分 + 推导总分 + 优化建议。"""
    r = _get_owned_resume(session, resume_id, user)
    content = _resume_ai_content(r)
    cfg = get_ai_config(session)
    if not cfg["api_key"]:
        raise HTTPException(status_code=400, detail="尚未配置 AI，请先在「设置」中填写 API Key")
    prompt = REVIEW_PROMPT.replace("{content}", content).replace(
        "{background}", r.background or "（未提供）"
    )
    raw = _call_llm(cfg["base_url"], cfg["model"], cfg["api_key"], prompt)
    try:
        data = _parse_json_loose(raw)
    except ValueError:
        raise HTTPException(status_code=502, detail=f"AI 返回内容无法解析：{raw[:200]}")

    try:
        score = max(0, min(100, int(data.get("score", 0))))
    except (TypeError, ValueError):
        score = 0
    # 总分推导（Prompt「先算后调」的服务端强制版）：基础分 = 五维加权，模型总分钳制在 ±5 内
    dimensions = _parse_dimensions(data.get("dimensions"))
    base_score = None
    if dimensions:
        base_score = round(
            sum(w * (dimensions[k] - 1) / 4 * 100 for k, w in DIM_WEIGHTS.items())
        )
        score = max(0, min(100, round(max(base_score - 5, min(base_score + 5, score)))))
    suggestions = [
        s
        for s in (data.get("suggestions") or [])
        if isinstance(s, dict) and s.get("title")
    ]
    if not suggestions:
        raise HTTPException(status_code=502, detail="AI 未返回有效的优化建议，请重试")

    r.score = score
    r.review_json = json.dumps(
        {"suggestions": suggestions, "dimensions": dimensions, "base_score": base_score},
        ensure_ascii=False,
    )
    session.add(r)
    session.commit()
    session.refresh(r)
    return _resume_dict(r)


class PredictQuestionsBody(BaseModel):
    direction: Optional[str] = None  # 出题方向（可选，如「侧重系统设计」「针对 XX 公司一面」）


@router.post("/resumes/{resume_id}/predict-questions")
def predict_questions(
    resume_id: int,
    body: Optional[PredictQuestionsBody] = None,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """基于简历内容预测面试题 + 参考答案要点；可指定出题方向。"""
    r = _get_owned_resume(session, resume_id, user)
    content = _resume_ai_content(r)
    cfg = get_ai_config(session)
    if not cfg["api_key"]:
        raise HTTPException(status_code=400, detail="尚未配置 AI，请先在「设置」中填写 API Key")
    direction = (body.direction or "").strip() if body else ""
    prompt = (
        QUESTIONS_PROMPT.replace("{content}", content)
        .replace("{background}", r.background or "（未提供）")
        .replace("{direction}", direction or "（未指定，综合出题）")
    )
    raw = _call_llm(cfg["base_url"], cfg["model"], cfg["api_key"], prompt)
    try:
        data = _parse_json_loose(raw)
    except ValueError:
        raise HTTPException(status_code=502, detail=f"AI 返回内容无法解析：{raw[:200]}")

    questions = [
        q
        for q in (data.get("questions") or [])
        if isinstance(q, dict) and q.get("q")
    ]
    if not questions:
        raise HTTPException(status_code=502, detail="AI 未返回有效题目，请重试")

    r.questions_json = json.dumps({"questions": questions}, ensure_ascii=False)
    r.questions_direction = direction or None
    session.add(r)
    session.commit()
    session.refresh(r)
    return _resume_dict(r)


class ResumeUpdate(BaseModel):
    name: Optional[str] = None
    note: Optional[str] = None
    background: Optional[str] = None


def _extract_pdf_text(path: Path) -> Optional[str]:
    """PDF 抽取：优先 PyMuPDF（按版面坐标自上而下，顺序可靠），回退 pypdf。"""
    try:
        import pymupdf

        doc = pymupdf.open(str(path))
        try:
            parts = [page.get_text("text", sort=True) for page in doc]
        finally:
            doc.close()
        text = "\n".join(parts)
        if text.strip():
            return text.strip()
    except Exception:
        pass
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip() or None
    except Exception:
        return None


def _extract_text(path: Path, ext: str) -> Optional[str]:
    """从简历文件抽取纯文本；不支持的格式返回 None。"""
    try:
        if ext == ".pdf":
            return _extract_pdf_text(path)
        if ext == ".docx":
            import docx  # python-docx

            document = docx.Document(str(path))
            text = "\n".join(p.text for p in document.paragraphs if p.text.strip())
            return text.strip() or None
    except Exception:
        return None
    return None


def _resume_dict(r: Resume) -> dict:
    data = jsonable_encoder(r)
    data["filepath"] = str(r.filepath)  # 明确返回字符串
    return data


@router.get("/resumes")
def list_resumes(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    resumes = session.exec(
        select(Resume)
        .where(Resume.user_id == user.id)
        .order_by(Resume.created_at.desc())
    ).all()
    return {"items": [_resume_dict(r) for r in resumes], "total": len(resumes)}


@router.post("/resumes")
def upload_resume(
    file: UploadFile,
    name: Optional[str] = Form(default=None),
    note: Optional[str] = Form(default=None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    original = Path(file.filename or "resume.pdf")
    ext = original.suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"仅支持 {'/'.join(sorted(ALLOWED_EXTS))} 格式，收到：{ext or '无扩展名'}",
        )

    data = file.file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(data) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="文件超过 20MB 限制")

    user_dir = UPLOAD_DIR / f"u{user.id}"  # 简历文件按用户分目录
    user_dir.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid.uuid4().hex}{ext}"
    path = user_dir / stored
    path.write_bytes(data)

    text = _extract_text(path, ext)
    structured = None
    if text:
        try:
            # 上传时若已配置 AI，自动整理为五大板块结构
            structured = _structure_with_ai(session, text)
        except HTTPException:
            structured = None  # 未配置 Key 或调用失败时保留原文，可稍后手动整理
    resume = Resume(
        name=(name or original.stem).strip() or original.stem,
        filename=original.name,
        filepath=str(path),
        ext=ext,
        size=len(data),
        text=text,
        structured=structured,
        note=(note or None),
        user_id=user.id,
    )
    session.add(resume)
    session.commit()
    session.refresh(resume)
    return _resume_dict(resume)


@router.patch("/resumes/{resume_id}")
def update_resume(
    resume_id: int,
    body: ResumeUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    r = _get_owned_resume(session, resume_id, user)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(r, field, value)
    session.add(r)
    session.commit()
    session.refresh(r)
    return _resume_dict(r)


@router.post("/resumes/{resume_id}/reextract")
def reextract_text(
    resume_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """重新抽取文本（如需升级解析逻辑）。"""
    r = _get_owned_resume(session, resume_id, user)
    path = Path(r.filepath)
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件已丢失")
    r.text = _extract_text(path, r.ext)
    session.add(r)
    session.commit()
    return {"ok": True, "text_len": len(r.text or "")}


@router.post("/resumes/{resume_id}/set-default")
def set_default_resume(
    resume_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """将该简历设为当前用户的默认，其余取消默认（用户内唯一默认）。"""
    r = _get_owned_resume(session, resume_id, user)
    for other in session.exec(
        select(Resume).where(Resume.user_id == user.id, Resume.is_default == True)  # noqa: E712
    ).all():
        other.is_default = False
        session.add(other)
    r.is_default = True
    session.add(r)
    session.commit()
    return {"ok": True, "default_id": r.id}


@router.post("/resumes/{resume_id}/structure")
def structure_resume(
    resume_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """用 AI 将简历整理为五大板块（个人信息/教育背景/专业技能/工作经历/项目经历）。"""
    r = _get_owned_resume(session, resume_id, user)
    raw = r.text
    if not raw:
        path = Path(r.filepath)
        raw = _extract_text(path, r.ext) if path.exists() else None
    if not raw:
        raise HTTPException(status_code=400, detail="没有可整理的文本（该格式不支持自动抽取）")
    try:
        r.structured = _structure_with_ai(session, raw)
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    session.add(r)
    session.commit()
    session.refresh(r)
    return _resume_dict(r)


@router.get("/resumes/{resume_id}/file")
def download_resume(
    resume_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    r = _get_owned_resume(session, resume_id, user)
    path = Path(r.filepath)
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件已丢失")
    return FileResponse(path, filename=r.filename)


@router.delete("/resumes/{resume_id}")
def delete_resume(
    resume_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    r = _get_owned_resume(session, resume_id, user)
    path = Path(r.filepath)
    if path.exists():
        path.unlink(missing_ok=True)
    session.delete(r)
    session.commit()
    return {"ok": True}
