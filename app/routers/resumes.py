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

from app.database import DATA_DIR, get_session
from app.models import Resume
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


REVIEW_PROMPT = """你是资深技术面试官与简历顾问。基于下面的简历内容做一次「简历体检」：
1. 给出总分 score（0-100 整数）：从内容完整性、亮点与量化程度、经历说服力、表达简洁度、与目标岗位匹配度五个维度综合评估。目标岗位默认为 Java 后端/服务端开发，若简历方向不同或求职者补充背景中有说明，则按背景评估。
2. 给出 6-8 条优化建议 suggestions，按重要性从高到低排序。每条：
   - title：一句话概括问题
   - detail：具体怎么改，必须引用简历中的真实位置与内容举例（如「工作经历第 2 条的 QPS 数字缺少压测口径」）
   - level："high"（硬伤必须改）/"mid"（明显加分）/"low"（锦上添花）
要求：建议必须基于简历真实内容、具体到条目，禁止泛泛而谈，禁止编造简历中不存在的信息；若提供了求职者补充背景，评估口径（目标方向、诉求、特殊情况）必须与背景保持一致。
只输出 JSON：{"score": 82, "suggestions": [{"title": "...", "detail": "...", "level": "high"}]}

简历内容：
----- 开始 -----
{content}
----- 结束 -----

求职者补充背景（体检的重要依据，未提供则为「（未提供）」）：
{background}"""


QUESTIONS_PROMPT = """你是技术面试官。基于下面的简历内容，预测面试中最可能被问到的问题：
1. 出 8 道题：优先针对简历中的具体项目、数字、技术选型做「追问式」出题（如「你提到 QPS 5w，怎么压测出来的？」），再补充对应技能栈的深度题。
2. 每题：tag（维度：项目深挖/专业技能/系统设计/场景设计等）、q（问题）、a（参考答案要点，3-5 句，结合简历真实内容作答）。
3. 禁止出与简历无关的通用套题；答案要点必须能用上简历中的经历。
4. 若提供了求职者补充背景（目标方向、求职诉求、特殊情况如 Gap/转行/离职原因），出题和答案必须结合背景调整：面向目标岗位出题，并可包含 1 道 friendly 表述的动机/规划类问题。
只输出 JSON：{"questions": [{"tag": "项目深挖", "q": "...", "a": "..."}]}

简历内容：
----- 开始 -----
{content}
----- 结束 -----

求职者补充背景（出题的重要依据，未提供则为「（未提供）」）：
{background}"""


@router.post("/resumes/{resume_id}/review")
def review_resume(resume_id: int, session: Session = Depends(get_session)):
    """AI 简历体检：得分 + 优化建议。"""
    r = session.get(Resume, resume_id)
    if r is None:
        raise HTTPException(status_code=404, detail="简历不存在")
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
    suggestions = [
        s
        for s in (data.get("suggestions") or [])
        if isinstance(s, dict) and s.get("title")
    ]
    if not suggestions:
        raise HTTPException(status_code=502, detail="AI 未返回有效的优化建议，请重试")

    r.score = score
    r.review_json = json.dumps({"suggestions": suggestions}, ensure_ascii=False)
    session.add(r)
    session.commit()
    session.refresh(r)
    return _resume_dict(r)


@router.post("/resumes/{resume_id}/predict-questions")
def predict_questions(resume_id: int, session: Session = Depends(get_session)):
    """基于简历内容预测面试题 + 参考答案要点。"""
    r = session.get(Resume, resume_id)
    if r is None:
        raise HTTPException(status_code=404, detail="简历不存在")
    content = _resume_ai_content(r)
    cfg = get_ai_config(session)
    if not cfg["api_key"]:
        raise HTTPException(status_code=400, detail="尚未配置 AI，请先在「设置」中填写 API Key")
    prompt = QUESTIONS_PROMPT.replace("{content}", content).replace(
        "{background}", r.background or "（未提供）"
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
def list_resumes(session: Session = Depends(get_session)):
    resumes = session.exec(select(Resume).order_by(Resume.created_at.desc())).all()
    return {"items": [_resume_dict(r) for r in resumes], "total": len(resumes)}


@router.post("/resumes")
def upload_resume(
    file: UploadFile,
    name: Optional[str] = Form(default=None),
    note: Optional[str] = Form(default=None),
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

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid.uuid4().hex}{ext}"
    path = UPLOAD_DIR / stored
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
    )
    session.add(resume)
    session.commit()
    session.refresh(resume)
    return _resume_dict(resume)


@router.patch("/resumes/{resume_id}")
def update_resume(
    resume_id: int, body: ResumeUpdate, session: Session = Depends(get_session)
):
    r = session.get(Resume, resume_id)
    if r is None:
        raise HTTPException(status_code=404, detail="简历不存在")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(r, field, value)
    session.add(r)
    session.commit()
    session.refresh(r)
    return _resume_dict(r)


@router.post("/resumes/{resume_id}/reextract")
def reextract_text(resume_id: int, session: Session = Depends(get_session)):
    """重新抽取文本（如需升级解析逻辑）。"""
    r = session.get(Resume, resume_id)
    if r is None:
        raise HTTPException(status_code=404, detail="简历不存在")
    path = Path(r.filepath)
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件已丢失")
    r.text = _extract_text(path, r.ext)
    session.add(r)
    session.commit()
    return {"ok": True, "text_len": len(r.text or "")}


@router.post("/resumes/{resume_id}/set-default")
def set_default_resume(resume_id: int, session: Session = Depends(get_session)):
    """将该简历设为默认，其余取消默认（全局唯一默认）。"""
    r = session.get(Resume, resume_id)
    if r is None:
        raise HTTPException(status_code=404, detail="简历不存在")
    for other in session.exec(select(Resume).where(Resume.is_default == True)).all():  # noqa: E712
        other.is_default = False
        session.add(other)
    r.is_default = True
    session.add(r)
    session.commit()
    return {"ok": True, "default_id": r.id}


@router.post("/resumes/{resume_id}/structure")
def structure_resume(resume_id: int, session: Session = Depends(get_session)):
    """用 AI 将简历整理为五大板块（个人信息/教育背景/专业技能/工作经历/项目经历）。"""
    r = session.get(Resume, resume_id)
    if r is None:
        raise HTTPException(status_code=404, detail="简历不存在")
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
def download_resume(resume_id: int, session: Session = Depends(get_session)):
    r = session.get(Resume, resume_id)
    if r is None:
        raise HTTPException(status_code=404, detail="简历不存在")
    path = Path(r.filepath)
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件已丢失")
    return FileResponse(path, filename=r.filename)


@router.delete("/resumes/{resume_id}")
def delete_resume(resume_id: int, session: Session = Depends(get_session)):
    r = session.get(Resume, resume_id)
    if r is None:
        raise HTTPException(status_code=404, detail="简历不存在")
    path = Path(r.filepath)
    if path.exists():
        path.unlink(missing_ok=True)
    session.delete(r)
    session.commit()
    return {"ok": True}
