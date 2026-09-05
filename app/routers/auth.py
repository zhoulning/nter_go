"""登录 / 注册 / 个人资料 REST API。"""
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import (
    BUILTIN_ADMIN,
    clear_auth_cookie,
    create_session,
    destroy_session,
    get_current_user,
    get_optional_user,
    hash_password,
    set_auth_cookie,
    verify_password,
)
from app.database import DATA_DIR, get_session
from app.models import (
    NOTIF_ACCOUNT,
    USER_ACTIVE,
    USER_PENDING,
    USER_REJECTED,
    Notification,
    User,
)
from app.routers.audit import client_ip, log_action
from app.routers.settings import get_registration_enabled

router = APIRouter()

AVATAR_DIR = DATA_DIR / "uploads" / "avatars"
AVATAR_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
AVATAR_MAX_SIZE = 2 * 1024 * 1024  # 2MB


def _user_brief(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "display_name": u.display_name,
        "role": u.role,
        "status": u.status,
        "avatar_path": u.avatar_path,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def _me_payload(u: User) -> dict:
    has_avatar = bool(u.avatar_path) and Path(u.avatar_path).is_file()
    return {
        **_user_brief(u),
        "avatar_url": "/api/auth/avatar" if has_avatar else None,
    }


def notify(session: Session, user_id: int, title: str, body: str = "") -> None:
    """给指定用户写一条站内通知。"""
    session.add(Notification(user_id=user_id, type=NOTIF_ACCOUNT, title=title, body=body or None))


def notify_admins(session: Session, title: str, body: str = "") -> None:
    for admin in session.exec(select(User).where(User.role == "admin")).all():
        notify(session, admin.id, title, body)


# ---- 注册 / 登录 / 登出 ----

class RegisterPayload(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None


class LoginPayload(BaseModel):
    username: str
    password: str


@router.get("/auth/register-status")
def register_status(session: Session = Depends(get_session)):
    return {"enabled": get_registration_enabled(session)}


@router.post("/auth/register")
def register(body: RegisterPayload, request: Request, session: Session = Depends(get_session)):
    if not get_registration_enabled(session):
        raise HTTPException(status_code=403, detail="当前未开放注册，请联系管理员创建账号")
    username = body.username.strip()
    if len(username) < 2 or len(username) > 32:
        raise HTTPException(status_code=400, detail="用户名长度需在 2-32 个字符之间")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    if username == BUILTIN_ADMIN:
        raise HTTPException(status_code=400, detail="该用户名为系统内置账号保留")
    exists = session.exec(select(User).where(User.username == username)).first()
    if exists:
        raise HTTPException(status_code=400, detail="用户名已被使用")
    user = User(
        username=username,
        password_hash=hash_password(body.password),
        display_name=(body.display_name or "").strip() or None,
        status=USER_PENDING,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    log_action(session, "auth.register", user=user, ip=client_ip(request), detail="注册申请待审核")
    notify_admins(session, "新用户注册待审核", f"{username} 提交了注册申请，请在「系统功能 → 用户管理」中审核。")
    session.commit()
    return {"status": "pending", "message": "注册已提交，等待管理员审核通过后即可登录"}


@router.post("/auth/login")
def login(
    body: LoginPayload,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    username = body.username.strip()
    user = session.exec(select(User).where(User.username == username)).first()
    # 统一报错文案，避免暴露「用户名存在与否」
    if user is None or not verify_password(body.password, user.password_hash):
        log_action(session, "auth.login_failed", username=username, ip=client_ip(request), detail="用户名或密码错误")
        session.commit()
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if user.status == USER_PENDING:
        raise HTTPException(status_code=403, detail="账号正在等待管理员审核，通过后才能登录")
    if user.status == USER_REJECTED:
        raise HTTPException(status_code=403, detail="注册申请未被通过，请联系管理员")
    if user.status != USER_ACTIVE:
        raise HTTPException(status_code=403, detail="账号已被禁用，请联系管理员")
    token = create_session(session, user.id)
    user.last_login_at = datetime.now()
    session.add(user)
    log_action(session, "auth.login", user=user, ip=client_ip(request))
    session.commit()
    set_auth_cookie(response, token)
    return _me_payload(user)


@router.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    user = get_optional_user(request, session)
    if user:
        log_action(session, "auth.logout", user=user, ip=client_ip(request))
        session.commit()
    destroy_session(session, request)
    clear_auth_cookie(response)
    return {"ok": True}


# ---- 当前用户 ----

class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None


class PasswordUpdate(BaseModel):
    old_password: str
    new_password: str


@router.get("/auth/me")
def read_me(user: User = Depends(get_current_user)):
    return _me_payload(user)


@router.put("/auth/me")
def update_me(
    body: ProfileUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if body.display_name is not None:
        user.display_name = body.display_name.strip() or None
        session.add(user)
        log_action(session, "account.profile_update", user=user, ip=client_ip(request), detail=f"昵称改为 {user.display_name or '（空，显示用户名）'}")
        session.commit()
    return _me_payload(user)


@router.put("/auth/me/password")
def update_password(
    body: PasswordUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码至少 6 位")
    user.password_hash = hash_password(body.new_password)
    session.add(user)
    log_action(session, "account.password_change", user=user, ip=client_ip(request))
    session.commit()
    return {"ok": True}


@router.get("/auth/avatar")
def read_avatar(user: User = Depends(get_current_user)):
    """当前登录用户的头像图片（带登录态校验）。"""
    if not user.avatar_path:
        raise HTTPException(status_code=404, detail="未设置头像")
    path = Path(user.avatar_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="头像文件不存在")
    from fastapi.responses import FileResponse

    return FileResponse(path)


@router.post("/auth/me/avatar")
def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in AVATAR_EXTS:
        raise HTTPException(status_code=400, detail="头像仅支持 png / jpg / webp / gif")
    data = file.file.read()
    if len(data) > AVATAR_MAX_SIZE:
        raise HTTPException(status_code=400, detail="头像图片不能超过 2MB")
    if not data:
        raise HTTPException(status_code=400, detail="文件内容为空")
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    # 覆盖旧头像前先删掉旧文件
    if user.avatar_path:
        Path(user.avatar_path).unlink(missing_ok=True)
    path = AVATAR_DIR / f"u{user.id}_{int(time.time())}{ext}"
    path.write_bytes(data)
    user.avatar_path = str(path)
    session.add(user)
    log_action(session, "account.avatar_update", user=user, ip=client_ip(request))
    session.commit()
    return _me_payload(user)


@router.delete("/auth/me/avatar")
def delete_avatar(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if user.avatar_path:
        Path(user.avatar_path).unlink(missing_ok=True)
        user.avatar_path = None
        session.add(user)
        log_action(session, "account.avatar_remove", user=user, ip=client_ip(request))
        session.commit()
    return _me_payload(user)
