"""录音上传、双通道转写与 AI 复盘报告。"""
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app.asr import probe_duration, transcribe_cloud, transcribe_local
from app.auth import get_current_user
from app.database import DATA_DIR, engine, get_session
from app.kb import search_knowledge_base
from app.models import InterviewRound, Opportunity, Recording, ReviewReport, Resume, User
from app.review import build_review, polish_transcript
from app.routers.ai import _call_llm, _parse_json_loose
from app.routers.settings import get_ai_config, get_asr_config

router = APIRouter()

UPLOAD_DIR = DATA_DIR / "uploads" / "recordings"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".webm", ".wma"}
MAX_SIZE = 200 * 1024 * 1024

ROUND_LABELS = {
    "written": "笔试", "first": "一面", "second": "二面", "third": "三面",
    "comprehensive": "综合面", "hr": "HR面", "other": "面试",
}

# 进程内任务表：防止同一录音并发起转写/复盘任务
_tasks: set[str] = set()
_tasks_lock = threading.Lock()


def _task_guard(key: str) -> bool:
    with _tasks_lock:
        if key in _tasks:
            return False
        _tasks.add(key)
        return True


def _task_release(key: str) -> None:
    with _tasks_lock:
        _tasks.discard(key)


def _rec_dict(
    rec: Recording,
    opp: Opportunity | None,
    round_: InterviewRound | None,
    review: ReviewReport | None,
    include_transcript: bool = True,
) -> dict:
    data = {
        "id": rec.id,
        "opportunity_id": rec.opportunity_id,
        "round_id": rec.round_id,
        "kind": rec.kind,
        "filename": rec.filename,
        "ext": rec.ext,
        "size": rec.size,
        "duration_sec": rec.duration_sec,
        "transcript_engine": rec.transcript_engine,
        "status": rec.status,
        "progress": rec.progress,
        "error": rec.error,
        "review_status": rec.review_status,
        "review_error": rec.review_error,
        "created_at": rec.created_at.isoformat(),
        "company": opp.company if opp else None,
        "position": opp.position if opp else None,
        "round_type": round_.round_type if round_ else None,
        "round_scheduled_at": round_.scheduled_at.isoformat() if round_ and round_.scheduled_at else None,
        "review_score": review.overall_score if review else None,
        "review_model": review.model if review else None,
        "review_created_at": review.created_at.isoformat() if review else None,
    }
    if include_transcript:
        data["transcript"] = rec.transcript
        data["transcript_clean"] = rec.transcript_clean
        data["polished_at"] = rec.polished_at.isoformat() if rec.polished_at else None
        data["polish_status"] = rec.polish_status
        data["polish_error"] = rec.polish_error
    return data


def _get_or_404(session: Session, recording_id: int, user: User) -> Recording:
    rec = session.get(Recording, recording_id)
    if rec is None or rec.user_id != user.id:
        raise HTTPException(status_code=404, detail="录音不存在")
    return rec


@router.post("/recordings")
async def upload_recording(
    file: UploadFile = File(...),
    opportunity_id: int = Form(...),
    round_id: Optional[int] = Form(None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    opp = session.get(Opportunity, opportunity_id)
    if opp is None or opp.user_id != user.id:
        raise HTTPException(status_code=404, detail="岗位不存在")
    round_ = None
    if round_id:
        round_ = session.get(InterviewRound, round_id)
        if round_ is None or round_.user_id != user.id or round_.opportunity_id != opportunity_id:
            raise HTTPException(status_code=400, detail="轮次与岗位不匹配")

    ext = Path(file.filename or "audio.mp3").suffix.lower() or ".mp3"
    if ext not in ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail=f"不支持的音频格式：{ext}")

    user_dir = UPLOAD_DIR / f"u{user.id}"  # 录音文件按用户分目录
    user_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filepath = user_dir / f"rec_{ts}{ext}"
    size = 0
    try:
        with open(filepath, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_SIZE:
                    raise HTTPException(status_code=400, detail="文件超过 200MB 上限")
                out.write(chunk)
    except HTTPException:
        filepath.unlink(missing_ok=True)
        raise

    rec = Recording(
        opportunity_id=opportunity_id,
        round_id=round_id,
        kind="recording",
        filename=file.filename or filepath.name,
        filepath=str(filepath),
        ext=ext,
        size=size,
        duration_sec=probe_duration(filepath),
        user_id=user.id,
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return _rec_dict(rec, opp, round_, None)


@router.get("/recordings")
def list_recordings(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    recordings = session.exec(
        select(Recording)
        .where(Recording.user_id == user.id)
        .order_by(Recording.created_at.desc())
    ).all()
    opps = {
        o.id: o for o in session.exec(select(Opportunity).where(Opportunity.user_id == user.id)).all()
    }
    rounds = {
        r.id: r for r in session.exec(select(InterviewRound).where(InterviewRound.user_id == user.id)).all()
    }
    reports = {
        r.recording_id: r
        for r in session.exec(select(ReviewReport).where(ReviewReport.user_id == user.id)).all()
    }
    return {
        "items": [
            _rec_dict(rec, opps.get(rec.opportunity_id), rounds.get(rec.round_id), reports.get(rec.id))
            for rec in recordings
        ],
        "total": len(recordings),
    }


@router.get("/recordings/{recording_id}")
def get_recording(
    recording_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    rec = _get_or_404(session, recording_id, user)
    opp = session.get(Opportunity, rec.opportunity_id)
    round_ = session.get(InterviewRound, rec.round_id) if rec.round_id else None
    review = session.exec(
        select(ReviewReport).where(ReviewReport.recording_id == recording_id)
    ).first()
    data = _rec_dict(rec, opp, round_, review)
    data["review"] = None
    if review is not None:
        try:
            data["review"] = {
                "id": review.id,
                "recording_id": review.recording_id,
                "model": review.model,
                "overall_score": review.overall_score,
                "question_count": review.question_count,
                "report": json.loads(review.report),
                "created_at": review.created_at.isoformat(),
            }
        except Exception:
            data["review"] = None
    return data


@router.get("/recordings/{recording_id}/file")
def download_recording(
    recording_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """下载原始录音文件。"""
    rec = _get_or_404(session, recording_id, user)
    if rec.kind == "text":
        raise HTTPException(status_code=400, detail="文字复盘没有录音文件")
    path = Path(rec.filepath)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="录音文件已丢失，可能被手动清理")
    return FileResponse(path, filename=rec.filename, media_type="application/octet-stream")


@router.delete("/recordings/{recording_id}")
def delete_recording(
    recording_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    rec = _get_or_404(session, recording_id, user)
    report = session.exec(
        select(ReviewReport).where(ReviewReport.recording_id == recording_id)
    ).first()
    if report:
        session.delete(report)
    session.delete(rec)
    session.commit()
    Path(rec.filepath).unlink(missing_ok=True)
    return {"ok": True}


class TextReviewCreate(BaseModel):
    opportunity_id: int
    round_id: Optional[int] = None
    title: Optional[str] = None      # 复盘标题，默认「文字复盘 + 日期」
    transcript: str                  # 面试文字稿（问答记录 / 面经均可）


@router.post("/recordings/text")
def create_text_review(
    body: TextReviewCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """创建文字复盘（现场面试等无录音场景，直接基于文字稿生成报告）。"""
    opp = session.get(Opportunity, body.opportunity_id)
    if opp is None or opp.user_id != user.id:
        raise HTTPException(status_code=404, detail="机会不存在")
    round_ = None
    if body.round_id:
        round_ = session.get(InterviewRound, body.round_id)
        if round_ is None or round_.user_id != user.id or round_.opportunity_id != body.opportunity_id:
            raise HTTPException(status_code=400, detail="轮次与机会不匹配")
    text = body.transcript.strip()
    if len(text) < 10:
        raise HTTPException(status_code=400, detail="文字稿内容太短，至少 10 个字")

    title = (body.title or "").strip() or f"文字复盘 {datetime.now().strftime('%Y/%m/%d')}"
    rec = Recording(
        opportunity_id=body.opportunity_id,
        round_id=body.round_id,
        kind="text",
        filename=title,
        filepath="",
        ext="",
        transcript=text,
        transcript_engine="manual",
        status="transcribed",
        progress=100,
        user_id=user.id,
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return _rec_dict(rec, opp, round_, None)


class TranscriptUpdate(BaseModel):
    transcript: str
    target: str = "raw"  # raw=原始稿 / clean=AI 矫正稿（手动编辑）


@router.put("/recordings/{recording_id}/transcript")
def save_transcript(
    recording_id: int,
    body: TranscriptUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    rec = _get_or_404(session, recording_id, user)
    value = body.transcript.strip() or None
    if body.target == "clean":
        rec.transcript_clean = value
        if value:
            rec.polished_at = datetime.now()
            rec.polish_status = "done"
        else:
            rec.polish_status = "none"
            rec.polished_at = None
    else:
        rec.transcript = value
        rec.transcript_engine = rec.transcript_engine or "manual"
        rec.status = "transcribed" if rec.transcript else "uploaded"
        rec.progress = 100 if rec.transcript else 0
        rec.error = None
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return _rec_dict(rec, session.get(Opportunity, rec.opportunity_id), None, None)


class TranscribeRequest(BaseModel):
    engine: str = "local"  # local / cloud


@router.post("/recordings/{recording_id}/transcribe")
def transcribe_recording(
    recording_id: int,
    body: TranscribeRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    rec = _get_or_404(session, recording_id, user)
    if rec.status == "transcribing":
        raise HTTPException(status_code=400, detail="该录音正在转写中")
    if body.engine not in ("local", "cloud"):
        raise HTTPException(status_code=400, detail="engine 仅支持 local / cloud")

    asr_cfg = get_asr_config(session)
    if body.engine == "cloud" and not asr_cfg["cloud_api_key"]:
        raise HTTPException(status_code=400, detail="尚未配置云端 ASR 的 API Key，请到「设置」中填写")

    rec.status = "transcribing"
    rec.progress = 0
    rec.error = None
    session.add(rec)
    session.commit()

    key = f"transcribe:{recording_id}"
    if not _task_guard(key):
        raise HTTPException(status_code=400, detail="任务已在进行中")
    thread = threading.Thread(
        target=_transcribe_worker, args=(recording_id, body.engine, asr_cfg), daemon=True
    )
    thread.start()
    return {"ok": True, "status": "transcribing"}


def _transcribe_worker(recording_id: int, channel: str, asr_cfg: dict[str, str]) -> None:
    key = f"transcribe:{recording_id}"
    session = Session(engine)
    try:
        rec = session.get(Recording, recording_id)
        if rec is None:
            return
        media = Path(rec.filepath)
        if channel == "cloud":
            text = transcribe_cloud(
                media, asr_cfg,
                on_progress=lambda p: _bump_progress(session, recording_id, p),
            )
            engine_label = f"cloud:{asr_cfg['cloud_model']}"
        else:
            text = transcribe_local(
                media, asr_cfg["whisper_model"],
                on_progress=lambda p: _bump_progress(session, recording_id, p),
            )
            engine_label = f"whisper-{asr_cfg['whisper_model']}"
        rec = session.get(Recording, recording_id)
        if text:
            rec.transcript = text
            rec.transcript_engine = engine_label
            rec.status = "transcribed"
            rec.progress = 100
            rec.error = None
        else:
            # 空结果不覆盖已有文字稿（可能上一轮转写/手动粘贴过）
            had_transcript = bool(rec.transcript)
            rec.status = "transcribed" if had_transcript else "failed"
            rec.progress = 100 if had_transcript else rec.progress
            rec.error = None if had_transcript else "转写完成但没有识别到语音内容"
        session.add(rec)
        session.commit()
    except Exception as e:
        rec = session.get(Recording, recording_id)
        if rec is not None:
            rec.status = "failed"
            rec.error = str(e)[:1000]
            session.add(rec)
            session.commit()
    finally:
        session.close()
        _task_release(key)


def _bump_progress(session: Session, recording_id: int, progress: int) -> None:
    rec = session.get(Recording, recording_id)
    if rec is not None:
        rec.progress = progress
        session.add(rec)
        session.commit()


class ReviewRequest(BaseModel):
    resume_id: Optional[int] = None


@router.post("/recordings/{recording_id}/review")
def generate_review(
    recording_id: int,
    body: ReviewRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    rec = _get_or_404(session, recording_id, user)
    if not rec.transcript:
        raise HTTPException(status_code=400, detail="该录音还没有文字稿，请先转写或手动粘贴")
    if rec.review_status == "running":
        raise HTTPException(status_code=400, detail="复盘报告正在生成中")
    opp = session.get(Opportunity, rec.opportunity_id)
    if opp is None or opp.user_id != user.id:
        raise HTTPException(status_code=404, detail="岗位不存在")

    ai_cfg = get_ai_config(session)
    if not ai_cfg["api_key"]:
        raise HTTPException(status_code=400, detail="尚未配置 AI 的 API Key，请到「设置」中填写")

    resume_id = body.resume_id if body.resume_id is not None else opp.resume_id
    if resume_id is not None:
        resume = session.get(Resume, resume_id)
        if resume is None or resume.user_id != user.id:
            resume_id = None

    rec.review_status = "running"
    rec.review_error = None
    session.add(rec)
    session.commit()

    key = f"review:{recording_id}"
    if not _task_guard(key):
        raise HTTPException(status_code=400, detail="任务已在进行中")
    thread = threading.Thread(
        target=_review_worker,
        args=(recording_id, resume_id, ai_cfg["base_url"], ai_cfg["model"], ai_cfg["api_key"]),
        daemon=True,
    )
    thread.start()
    return {"ok": True, "status": "running"}


def _review_worker(
    recording_id: int,
    resume_id: Optional[int],
    base_url: str,
    model: str,
    api_key: str,
) -> None:
    key = f"review:{recording_id}"
    session = Session(engine)
    try:
        rec = session.get(Recording, recording_id)
        opp = session.get(Opportunity, rec.opportunity_id)
        round_ = session.get(InterviewRound, rec.round_id) if rec.round_id else None
        resume_text = ""
        if resume_id:
            resume = session.get(Resume, resume_id)
            resume_text = resume.text or ""

        # 知识库片段：按文字稿开头 + 岗位关键词检索，供 improved / 点评参考（失败不阻塞复盘）
        transcript_head = ((rec.transcript_clean or rec.transcript) or "")[:600]
        try:
            kb_hits = (
                search_knowledge_base(session, f"{transcript_head} {opp.company} {opp.position}")
                if transcript_head.strip()
                else []
            )
        except Exception:
            kb_hits = []
        if kb_hits:
            kb_text = "\n".join(
                f"[{i}] 来源 {h['source']}\n{h['text']}" for i, h in enumerate(kb_hits, 1)
            )[:2400]
        else:
            kb_text = "（未配置知识库或未检索到相关笔记，忽略本节）"

        report = build_review(
            base_url, model, api_key,
            company=opp.company,
            position=opp.position,
            round_label=ROUND_LABELS.get(round_.round_type, "面试") if round_ else "面试",
            jd_text=opp.jd_text or "",
            resume_text=resume_text,
            transcript=(rec.transcript_clean or rec.transcript) or "",
            kb_text=kb_text,
        )

        existing = session.exec(
            select(ReviewReport).where(ReviewReport.recording_id == recording_id)
        ).first()
        if existing is None:
            existing = ReviewReport(recording_id=recording_id, user_id=rec.user_id)
        existing.model = model
        existing.resume_id = resume_id
        existing.report = json.dumps(report, ensure_ascii=False)
        existing.overall_score = int(report.get("overall", {}).get("score", 0) or 0)
        existing.question_count = len(report.get("questions", []))
        existing.created_at = datetime.now()
        session.add(existing)

        rec = session.get(Recording, recording_id)
        rec.review_status = "done"
        session.add(rec)
        session.commit()
    except Exception as e:
        rec = session.get(Recording, recording_id)
        if rec is not None:
            rec.review_status = "failed"
            rec.review_error = str(e)[:1000]
            session.add(rec)
            session.commit()
    finally:
        session.close()
        _task_release(key)


@router.post("/recordings/{recording_id}/polish")
def polish_recording(
    recording_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    rec = _get_or_404(session, recording_id, user)
    if not rec.transcript:
        raise HTTPException(status_code=400, detail="该录音还没有原始文字稿，请先转写或手动粘贴")
    if rec.polish_status == "running":
        raise HTTPException(status_code=400, detail="AI 矫正正在生成中")
    ai_cfg = get_ai_config(session)
    if not ai_cfg["api_key"]:
        raise HTTPException(status_code=400, detail="尚未配置 AI 的 API Key，请到「设置」中填写")

    rec.polish_status = "running"
    rec.polish_error = None
    session.add(rec)
    session.commit()

    key = f"polish:{recording_id}"
    if not _task_guard(key):
        raise HTTPException(status_code=400, detail="任务已在进行中")
    thread = threading.Thread(
        target=_polish_worker,
        args=(recording_id, ai_cfg["base_url"], ai_cfg["model"], ai_cfg["api_key"]),
        daemon=True,
    )
    thread.start()
    return {"ok": True, "status": "running"}


def _polish_worker(recording_id: int, base_url: str, model: str, api_key: str) -> None:
    key = f"polish:{recording_id}"
    session = Session(engine)
    try:
        rec = session.get(Recording, recording_id)
        polished = polish_transcript(base_url, model, api_key, rec.transcript or "")
        rec = session.get(Recording, recording_id)
        rec.transcript_clean = polished
        rec.polished_at = datetime.now()
        rec.polish_status = "done"
        session.add(rec)
        session.commit()
    except Exception as e:
        rec = session.get(Recording, recording_id)
        if rec is not None:
            rec.polish_status = "failed"
            rec.polish_error = str(e)[:1000]
            session.add(rec)
            session.commit()
    finally:
        session.close()
        _task_release(key)
