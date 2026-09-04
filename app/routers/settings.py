"""AI 配置的读写。Key 只存本地 SQLite，不上传任何第三方。"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.database import get_session
from app.models import Setting

router = APIRouter()

KEY_BASE_URL = "ai_base_url"
KEY_MODEL = "ai_model"
KEY_API_KEY = "ai_api_key"
KEY_CDP = "browser_cdp_endpoint"
KEY_ASR_PROVIDER = "asr_provider"      # local / cloud
KEY_ASR_WHISPER_MODEL = "asr_whisper_model"
KEY_ASR_CLOUD_BASE_URL = "asr_cloud_base_url"
KEY_ASR_CLOUD_MODEL = "asr_cloud_model"
KEY_ASR_CLOUD_API_KEY = "asr_cloud_api_key"

DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
DEFAULT_MODEL = "glm-4-flash"
DEFAULT_CDP = "http://127.0.0.1:9222"
DEFAULT_ASR_PROVIDER = "local"
DEFAULT_ASR_WHISPER_MODEL = "small"
DEFAULT_ASR_CLOUD_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_ASR_CLOUD_MODEL = "FunAudioLLM/SenseVoiceSmall"


class AiSettingsUpdate(BaseModel):
    base_url: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None


class BrowserSettingsUpdate(BaseModel):
    cdp_endpoint: Optional[str] = None


def _read_settings(session: Session) -> dict[str, str]:
    rows = session.exec(select(Setting)).all()
    return {r.key: r.value for r in rows}


def _save(session: Session, key: str, value: str) -> None:
    row = session.get(Setting, key)
    if row is None:
        session.add(Setting(key=key, value=value))
    else:
        row.value = value
        session.add(row)


def get_ai_config(session: Session) -> dict[str, str]:
    """供其他模块读取 AI 配置（带默认值）。"""
    data = _read_settings(session)
    return {
        "base_url": (data.get(KEY_BASE_URL) or DEFAULT_BASE_URL).rstrip("/"),
        "model": data.get(KEY_MODEL) or DEFAULT_MODEL,
        "api_key": data.get(KEY_API_KEY) or "",
    }


@router.get("/settings/ai")
def read_ai_settings(session: Session = Depends(get_session)):
    cfg = get_ai_config(session)
    key = cfg["api_key"]
    masked = f"{key[:4]}****{key[-4:]}" if len(key) > 8 else ("****" if key else None)
    return {
        "base_url": cfg["base_url"],
        "model": cfg["model"],
        "api_key_configured": bool(key),
        "api_key_masked": masked,
    }


@router.put("/settings/ai")
def update_ai_settings(body: AiSettingsUpdate, session: Session = Depends(get_session)):
    changed = body.model_dump(exclude_unset=True)
    if "base_url" in changed and changed["base_url"]:
        if not str(changed["base_url"]).startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="base_url 必须以 http(s):// 开头")
    for field, storage_key in (("base_url", KEY_BASE_URL), ("model", KEY_MODEL), ("api_key", KEY_API_KEY)):
        if field in changed and changed[field] is not None:
            _save(session, storage_key, str(changed[field]).strip())
    session.commit()
    return read_ai_settings(session)


def get_browser_config(session: Session) -> dict[str, str]:
    data = _read_settings(session)
    return {"cdp_endpoint": (data.get(KEY_CDP) or DEFAULT_CDP).rstrip("/")}


@router.get("/settings/browser")
def read_browser_settings(session: Session = Depends(get_session)):
    return get_browser_config(session)


@router.put("/settings/browser")
def update_browser_settings(body: BrowserSettingsUpdate, session: Session = Depends(get_session)):
    if body.cdp_endpoint is not None:
        value = body.cdp_endpoint.strip()
        if value and not value.startswith("http://"):
            raise HTTPException(status_code=400, detail="cdp_endpoint 需以 http:// 开头")
        _save(session, KEY_CDP, value or DEFAULT_CDP)
        session.commit()
    return read_browser_settings(session)


# ---- 语音转写（ASR）设置 ----


class AsrSettingsUpdate(BaseModel):
    provider: Optional[str] = None       # local / cloud
    whisper_model: Optional[str] = None  # tiny / base / small / medium
    cloud_base_url: Optional[str] = None
    cloud_model: Optional[str] = None
    cloud_api_key: Optional[str] = None


def get_asr_config(session: Session) -> dict[str, str]:
    data = _read_settings(session)
    return {
        "provider": data.get(KEY_ASR_PROVIDER) or DEFAULT_ASR_PROVIDER,
        "whisper_model": data.get(KEY_ASR_WHISPER_MODEL) or DEFAULT_ASR_WHISPER_MODEL,
        "cloud_base_url": (data.get(KEY_ASR_CLOUD_BASE_URL) or DEFAULT_ASR_CLOUD_BASE_URL).rstrip("/"),
        "cloud_model": data.get(KEY_ASR_CLOUD_MODEL) or DEFAULT_ASR_CLOUD_MODEL,
        "cloud_api_key": data.get(KEY_ASR_CLOUD_API_KEY) or "",
    }


@router.get("/settings/asr")
def read_asr_settings(session: Session = Depends(get_session)):
    cfg = get_asr_config(session)
    key = cfg["cloud_api_key"]
    masked = f"{key[:4]}****{key[-4:]}" if len(key) > 8 else ("****" if key else None)
    return {
        "provider": cfg["provider"],
        "whisper_model": cfg["whisper_model"],
        "cloud_base_url": cfg["cloud_base_url"],
        "cloud_model": cfg["cloud_model"],
        "cloud_api_key_configured": bool(key),
        "cloud_api_key_masked": masked,
    }


@router.put("/settings/asr")
def update_asr_settings(body: AsrSettingsUpdate, session: Session = Depends(get_session)):
    changed = body.model_dump(exclude_unset=True)
    if "provider" in changed and changed["provider"] not in ("local", "cloud"):
        raise HTTPException(status_code=400, detail="provider 仅支持 local / cloud")
    if "whisper_model" in changed and changed["whisper_model"] not in ("tiny", "base", "small", "medium"):
        raise HTTPException(status_code=400, detail="whisper_model 仅支持 tiny / base / small / medium")
    mapping = (
        ("provider", KEY_ASR_PROVIDER),
        ("whisper_model", KEY_ASR_WHISPER_MODEL),
        ("cloud_base_url", KEY_ASR_CLOUD_BASE_URL),
        ("cloud_model", KEY_ASR_CLOUD_MODEL),
        ("cloud_api_key", KEY_ASR_CLOUD_API_KEY),
    )
    for field, storage_key in mapping:
        if field in changed and changed[field] is not None:
            _save(session, storage_key, str(changed[field]).strip())
    session.commit()
    return read_asr_settings(session)
