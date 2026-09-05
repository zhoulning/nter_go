"""AI / 转写 / 知识库 / 浏览器等系统配置的读写。

配置全局共享（所有用户共用一套 AI 能力），仅内置管理员账号（admin）可查看与修改。
"""
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import require_builtin_admin
from app.database import get_session
from app.models import Setting, User
from app.routers.audit import client_ip, log_action

router = APIRouter()

KEY_BASE_URL = "ai_base_url"
KEY_MODEL = "ai_model"
KEY_API_KEY = "ai_api_key"
KEY_CDP = "browser_cdp_endpoint"
KEY_KB_PATH = "question_kb_path"       # 私有知识库文件夹（AI 生成答案时检索）
KEY_ASR_PROVIDER = "asr_provider"      # local / cloud
KEY_ASR_WHISPER_MODEL = "asr_whisper_model"
KEY_ASR_CLOUD_BASE_URL = "asr_cloud_base_url"
KEY_ASR_CLOUD_MODEL = "asr_cloud_model"
KEY_ASR_CLOUD_API_KEY = "asr_cloud_api_key"
KEY_REGISTRATION = "registration_enabled"  # 是否开放自主注册（默认开，注册后需审核）

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
def read_ai_settings(admin: None = Depends(require_builtin_admin), session: Session = Depends(get_session)):
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
def update_ai_settings(
    body: AiSettingsUpdate,
    request: Request,
    admin: User = Depends(require_builtin_admin),
    session: Session = Depends(get_session),
):
    changed = body.model_dump(exclude_unset=True)
    if "base_url" in changed and changed["base_url"]:
        if not str(changed["base_url"]).startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="base_url 必须以 http(s):// 开头")
    for field, storage_key in (("base_url", KEY_BASE_URL), ("model", KEY_MODEL), ("api_key", KEY_API_KEY)):
        if field in changed and changed[field] is not None:
            _save(session, storage_key, str(changed[field]).strip())
    field_names = {"base_url": "接口地址", "model": "模型", "api_key": "API Key"}
    updated = "、".join(field_names[k] for k, v in changed.items() if v is not None)
    log_action(session, "settings.ai", user=admin, target="AI 配置", ip=client_ip(request), detail=f"更新：{updated}")
    session.commit()
    return read_ai_settings(session)


def get_browser_config(session: Session) -> dict[str, str]:
    data = _read_settings(session)
    return {"cdp_endpoint": (data.get(KEY_CDP) or DEFAULT_CDP).rstrip("/")}


@router.get("/settings/browser")
def read_browser_settings(
    admin: None = Depends(require_builtin_admin), session: Session = Depends(get_session)
):
    return get_browser_config(session)


@router.put("/settings/browser")
def update_browser_settings(
    body: BrowserSettingsUpdate,
    request: Request,
    admin: User = Depends(require_builtin_admin),
    session: Session = Depends(get_session),
):
    if body.cdp_endpoint is not None:
        value = body.cdp_endpoint.strip()
        if value and not value.startswith("http://"):
            raise HTTPException(status_code=400, detail="cdp_endpoint 需以 http:// 开头")
        _save(session, KEY_CDP, value or DEFAULT_CDP)
        log_action(session, "settings.browser", user=admin, target="浏览器直连", ip=client_ip(request), detail=f"调试地址：{value or DEFAULT_CDP}")
        session.commit()
    return read_browser_settings(session)


# ---- 私有知识库（Obsidian vault）设置 ----

KB_EXTS = {".md", ".markdown", ".txt", ".pdf", ".docx"}


class KbSettingsUpdate(BaseModel):
    path: Optional[str] = None


def get_kb_path(session: Session) -> str:
    """供其他模块读取知识库路径（未配置返回空串）。"""
    return (_read_settings(session).get(KEY_KB_PATH) or "").strip()


def _kb_stats(path: str) -> dict:
    p = Path(path) if path else None
    if not p or not p.is_dir():
        return {"path": path, "exists": False, "file_count": 0}
    try:
        count = sum(1 for f in p.rglob("*") if f.is_file() and f.suffix.lower() in KB_EXTS)
    except OSError:
        count = 0
    return {"path": path, "exists": True, "file_count": count}


@router.get("/settings/kb")
def read_kb_settings(
    admin: None = Depends(require_builtin_admin), session: Session = Depends(get_session)
):
    return _kb_stats(get_kb_path(session))


@router.put("/settings/kb")
def update_kb_settings(
    body: KbSettingsUpdate,
    request: Request,
    admin: User = Depends(require_builtin_admin),
    session: Session = Depends(get_session),
):
    if body.path is not None:
        _save(session, KEY_KB_PATH, body.path.strip())
        log_action(
            session,
            "settings.kb",
            user=admin,
            target="知识库",
            ip=client_ip(request),
            detail=f"路径：{body.path.strip() or '（清空，停用）'}",
        )
        session.commit()
    return read_kb_settings(session)


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
def read_asr_settings(
    admin: None = Depends(require_builtin_admin), session: Session = Depends(get_session)
):
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
def update_asr_settings(
    body: AsrSettingsUpdate,
    request: Request,
    admin: User = Depends(require_builtin_admin),
    session: Session = Depends(get_session),
):
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
    updated = []
    for field, storage_key in mapping:
        if field in changed and changed[field] is not None:
            _save(session, storage_key, str(changed[field]).strip())
            updated.append(field)
    log_action(session, "settings.asr", user=admin, target="语音转写", ip=client_ip(request), detail=f"更新：{'、'.join(updated)}")
    session.commit()
    return read_asr_settings(session)


# ---- 注册开关 ----

def get_registration_enabled(session: Session) -> bool:
    """是否开放自主注册（关闭后只能由管理员建号）。默认开放。"""
    raw = (_read_settings(session).get(KEY_REGISTRATION) or "").strip().lower()
    if raw == "":
        return True
    return raw in ("1", "true", "yes", "on")


@router.get("/settings/registration")
def read_registration_settings(
    admin: None = Depends(require_builtin_admin), session: Session = Depends(get_session)
):
    return {"enabled": get_registration_enabled(session)}


@router.put("/settings/registration")
def update_registration_settings(
    body: dict,
    request: Request,
    admin: User = Depends(require_builtin_admin),
    session: Session = Depends(get_session),
):
    enabled = bool(body.get("enabled"))
    _save(session, KEY_REGISTRATION, "true" if enabled else "false")
    log_action(
        session,
        "settings.registration",
        user=admin,
        target="注册开关",
        ip=client_ip(request),
        detail="开放自主注册" if enabled else "关闭自主注册",
    )
    session.commit()
    return {"enabled": enabled}
