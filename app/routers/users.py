"""用户管理 REST API（仅超级管理员）。"""
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.auth import BUILTIN_ADMIN, hash_password, is_builtin_user, require_admin
from app.database import DATA_DIR, get_session
from app.routers.audit import client_ip, log_action
from app.models import (
    NOTIF_ACCOUNT,
    ROLE_ADMIN,
    USER_ACTIVE,
    USER_DISABLED,
    USER_PENDING,
    USER_REJECTED,
    InterviewRound,
    MatchReport,
    MockInterview,
    Notification,
    Offer,
    Opportunity,
    Prediction,
    Question,
    QuestionSource,
    Recording,
    ResearchMaterial,
    ResearchNote,
    ReviewReport,
    Resume,
    User,
    UserSession,
)

router = APIRouter()

# 内置超级管理员（BUILTIN_ADMIN，见 app/auth.py）：不可删除、不可被他人禁用；管理员角色的唯一授予入口


# 用户被删除时需要级联清理的业务表
_OWNED_TABLES = (
    ReviewReport,
    Recording,
    MockInterview,
    Prediction,
    MatchReport,
    ResearchMaterial,
    ResearchNote,
    Offer,
    QuestionSource,
    Question,
    InterviewRound,
    Opportunity,
    Resume,
    Notification,
)


def _user_row(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "display_name": u.display_name,
        "role": u.role,
        "status": u.status,
        "reject_reason": u.reject_reason,
        "has_avatar": bool(u.avatar_path) and Path(u.avatar_path).is_file(),
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "approved_at": u.approved_at.isoformat() if u.approved_at else None,
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
    }


def _get_user(session: Session, user_id: int) -> User:
    u = session.get(User, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return u


@router.get("/users")
def list_users(admin: User = Depends(require_admin), session: Session = Depends(get_session)):
    users = session.exec(select(User).order_by(col(User.created_at).asc())).all()
    return [_user_row(u) for u in users]


class UserCreate(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None
    role: str = "user"


@router.post("/users")
def create_user(
    body: UserCreate,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """管理员直接建号：跳过审核，创建即为可用状态。"""
    username = body.username.strip()
    if len(username) < 2 or len(username) > 32:
        raise HTTPException(status_code=400, detail="用户名长度需在 2-32 个字符之间")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    if body.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="role 仅支持 admin / user")
    if username == BUILTIN_ADMIN:
        raise HTTPException(status_code=400, detail="该用户名为系统内置账号保留")
    if body.role == "admin" and not is_builtin_user(admin):
        raise HTTPException(status_code=403, detail="仅内置管理员账号（admin）可以创建管理员账号")
    if session.exec(select(User).where(User.username == username)).first():
        raise HTTPException(status_code=400, detail="用户名已被使用")
    user = User(
        username=username,
        password_hash=hash_password(body.password),
        display_name=(body.display_name or "").strip() or None,
        role=body.role,
        status=USER_ACTIVE,
        approved_at=datetime.now(),
    )
    session.add(user)
    log_action(
        session,
        "user.create",
        user=admin,
        target=username,
        ip=client_ip(request),
        detail="角色：" + ("管理员" if body.role == "admin" else "普通用户"),
    )
    session.commit()
    session.refresh(user)
    return _user_row(user)


class RejectPayload(BaseModel):
    reason: Optional[str] = None


@router.post("/users/{user_id}/approve")
def approve_user(
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    u = _get_user(session, user_id)
    if u.status not in (USER_PENDING, USER_REJECTED):
        raise HTTPException(status_code=400, detail="仅待审核 / 已拒绝的账号可以审核通过")
    u.status = USER_ACTIVE
    u.approved_at = datetime.now()
    u.reject_reason = None
    session.add(u)
    session.add(
        Notification(
            user_id=u.id,
            type=NOTIF_ACCOUNT,
            title="注册审核通过",
            body="你的账号已通过审核，现在可以登录使用了。",
        )
    )
    log_action(session, "user.approve", user=admin, target=u.username, ip=client_ip(request))
    session.commit()
    return _user_row(u)


@router.post("/users/{user_id}/reject")
def reject_user(
    user_id: int,
    body: RejectPayload,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    u = _get_user(session, user_id)
    if u.status != USER_PENDING:
        raise HTTPException(status_code=400, detail="仅待审核的账号可以拒绝")
    u.status = USER_REJECTED
    u.reject_reason = (body.reason or "").strip() or None
    session.add(u)
    session.add(
        Notification(
            user_id=u.id,
            type=NOTIF_ACCOUNT,
            title="注册申请未通过",
            body=u.reject_reason or "如有疑问请联系管理员。",
        )
    )
    log_action(session, "user.reject", user=admin, target=u.username, ip=client_ip(request), detail=u.reject_reason)
    session.commit()
    return _user_row(u)


@router.post("/users/{user_id}/disable")
def disable_user(
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    u = _get_user(session, user_id)
    if u.id == admin.id:
        raise HTTPException(status_code=400, detail="不能禁用自己的账号")
    if is_builtin_user(u):
        raise HTTPException(status_code=400, detail="内置管理员账号不可禁用")
    if u.status != USER_ACTIVE:
        raise HTTPException(status_code=400, detail="仅正常状态的账号可以禁用")
    u.status = USER_DISABLED
    session.add(u)
    # 立刻踢下线：清掉该用户所有会话
    for s in session.exec(select(UserSession).where(UserSession.user_id == u.id)).all():
        session.delete(s)
    session.add(
        Notification(
            user_id=u.id,
            type=NOTIF_ACCOUNT,
            title="账号已被禁用",
            body="你的账号已被管理员禁用，如需恢复请联系管理员。",
        )
    )
    log_action(session, "user.disable", user=admin, target=u.username, ip=client_ip(request))
    session.commit()
    return _user_row(u)


@router.post("/users/{user_id}/enable")
def enable_user(
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    u = _get_user(session, user_id)
    if u.status != USER_DISABLED:
        raise HTTPException(status_code=400, detail="仅已禁用的账号可以启用")
    u.status = USER_ACTIVE
    session.add(u)
    log_action(session, "user.enable", user=admin, target=u.username, ip=client_ip(request))
    session.commit()
    return _user_row(u)


class AdminResetPassword(BaseModel):
    new_password: str


@router.post("/users/{user_id}/password")
def reset_password(
    user_id: int,
    body: AdminResetPassword,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    u = _get_user(session, user_id)
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码至少 6 位")
    if u.role == ROLE_ADMIN and not is_builtin_user(admin):
        raise HTTPException(status_code=403, detail="仅内置管理员账号（admin）可以重置管理员密码")
    u.password_hash = hash_password(body.new_password)
    session.add(u)
    # 重置密码后踢掉旧会话
    for s in session.exec(select(UserSession).where(UserSession.user_id == u.id)).all():
        session.delete(s)
    log_action(session, "user.reset_password", user=admin, target=u.username, ip=client_ip(request))
    session.commit()
    return {"ok": True}


def delete_user_data(session: Session, user: User) -> None:
    """级联删除某用户的全部业务数据与上传文件（不含 user 行本身）。"""
    for table in _OWNED_TABLES:
        for row in session.exec(select(table).where(table.user_id == user.id)).all():
            session.delete(row)
    for s in session.exec(select(UserSession).where(UserSession.user_id == user.id)).all():
        session.delete(s)
    # 上传文件：按用户隔离的目录整个清掉
    for sub in ("resumes", "recordings"):
        dir_path = DATA_DIR / "uploads" / sub / f"u{user.id}"
        if dir_path.is_dir():
            for f in dir_path.iterdir():
                f.unlink(missing_ok=True)
            dir_path.rmdir()
    if user.avatar_path:
        Path(user.avatar_path).unlink(missing_ok=True)


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    u = _get_user(session, user_id)
    if u.id == admin.id:
        raise HTTPException(status_code=400, detail="不能删除自己的账号，需由其他管理员操作")
    if is_builtin_user(u):
        raise HTTPException(status_code=400, detail="内置管理员账号（admin）不可删除")
    deleted_username = u.username
    was_admin = u.role == ROLE_ADMIN
    delete_user_data(session, u)
    session.delete(u)
    log_action(
        session,
        "user.delete",
        user=admin,
        target=deleted_username,
        ip=client_ip(request),
        detail="已删除管理员账号并级联清理其全部业务数据" if was_admin else "已级联删除该用户全部业务数据",
    )
    session.commit()
    return {"ok": True}


@router.get("/users/{user_id}/avatar")
def read_user_avatar(
    user_id: int,
    _admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    u = _get_user(session, user_id)
    if not u.avatar_path:
        raise HTTPException(status_code=404, detail="未设置头像")
    path = Path(u.avatar_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="头像文件不存在")
    return FileResponse(path)
