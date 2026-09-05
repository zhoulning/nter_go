"""登录认证：密码哈希（PBKDF2，标准库）、会话签发与校验、FastAPI 依赖。

会话走 HttpOnly Cookie（30 天），库里只存 token 的 sha256；
所有业务接口通过 Depends(get_current_user) 拿到当前用户做数据隔离。
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Request, Response
from sqlmodel import Session, select

from app.database import get_session
from app.models import USER_ACTIVE, User, UserSession

COOKIE_NAME = "session_token"
SESSION_DAYS = 30
_PBKDF2_ITERATIONS = 120_000


# ---- 密码 ----

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


# ---- 会话 ----

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(session: Session, user_id: int) -> str:
    """签发新会话，返回要写入 Cookie 的原始 token。"""
    token = secrets.token_urlsafe(32)
    session.add(
        UserSession(
            token_hash=_hash_token(token),
            user_id=user_id,
            expires_at=datetime.now() + timedelta(days=SESSION_DAYS),
        )
    )
    session.commit()
    return token


def destroy_session(session: Session, request: Request) -> None:
    raw = request.cookies.get(COOKIE_NAME)
    if raw:
        row = session.get(UserSession, _hash_token(raw))
        if row:
            session.delete(row)
            session.commit()


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


# ---- FastAPI 依赖 ----

def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
) -> User:
    raw = request.cookies.get(COOKIE_NAME)
    if raw:
        row = session.exec(
            select(UserSession).where(UserSession.token_hash == _hash_token(raw))
        ).first()
        if row and row.expires_at > datetime.now():
            user = session.get(User, row.user_id)
            if user and user.status == USER_ACTIVE:
                return user
            if user and user.status != USER_ACTIVE:
                raise HTTPException(status_code=401, detail="账号不可用，请重新登录")
    raise HTTPException(
        status_code=401,
        detail="未登录或登录已过期",
        headers={"X-Auth-Required": "1"},
    )


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


# 内置超级管理员账号（用户名固定 admin）：不可删除、不可禁用；系统配置（AI/浏览器/知识库/注册）仅它可管理
BUILTIN_ADMIN = "admin"


def is_builtin_user(u: User) -> bool:
    return u.username == BUILTIN_ADMIN


def require_builtin_admin(user: User = Depends(require_admin)) -> User:
    if not is_builtin_user(user):
        raise HTTPException(status_code=403, detail="仅内置管理员账号（admin）可管理系统配置")
    return user


def get_optional_user(request: Request, session: Session = Depends(get_session)) -> Optional[User]:
    """未登录返回 None 而不是 401（登录/注册接口旁的低敏接口用）。"""
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    row = session.exec(
        select(UserSession).where(UserSession.token_hash == _hash_token(raw))
    ).first()
    if not row or row.expires_at <= datetime.now():
        return None
    user = session.get(User, row.user_id)
    if user and user.status == USER_ACTIVE:
        return user
    return None
