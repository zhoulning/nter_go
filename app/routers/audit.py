"""操作日志（审计）：登录认证、用户管理、系统配置变更留痕与查询。

写入口 log_action 由各业务路由在操作成功的事务里调用；
查询接口仅超级管理员可用。
"""
from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy import select as sa_select
from sqlmodel import Session, col, select

from app.auth import require_admin
from app.database import get_session
from app.models import AuditLog, User

router = APIRouter()


def client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def log_action(
    session: Session,
    action: str,
    user: Optional[User] = None,
    username: Optional[str] = None,
    target: Optional[str] = None,
    detail: Optional[str] = None,
    ip: Optional[str] = None,
) -> None:
    """写一条审计日志（加入当前事务，随调用方一起提交）。

    登录失败等用户尚未知的场景传 username；其余传 user 对象。
    """
    session.add(
        AuditLog(
            user_id=user.id if user else None,
            username=username if username is not None else (user.username if user else ""),
            action=action,
            target=target,
            detail=detail,
            ip=ip,
        )
    )


@router.get("/audit-logs")
def list_audit_logs(
    category: str = "",      # 空=全部 / auth / account / user / settings（action 前缀）
    username: str = "",
    limit: int = 50,
    offset: int = 0,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    conds = []
    if category:
        conds.append(col(AuditLog.action).startswith(f"{category}."))
    name_conds = list(conds)
    if username:
        conds.append(AuditLog.username == username.strip())

    items = session.exec(
        select(AuditLog)
        .where(*conds)
        .order_by(col(AuditLog.created_at).desc(), col(AuditLog.id).desc())
        .offset(offset)
        .limit(limit)
    ).all()
    total = session.execute(sa_select(func.count()).select_from(AuditLog).where(*conds)).scalar_one()

    # 筛选下拉用：该分类下出现过的操作人（不按 username 过滤）
    usernames = [
        row[0]
        for row in session.execute(
            sa_select(AuditLog.username)
            .distinct()
            .where(*name_conds)
            .where(col(AuditLog.username) != "")
            .order_by(AuditLog.username)
        ).all()
    ]

    return {
        "items": [
            {
                "id": log.id,
                "user_id": log.user_id,
                "username": log.username,
                "action": log.action,
                "target": log.target,
                "detail": log.detail,
                "ip": log.ip,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in items
        ],
        "total": total,
        "usernames": usernames,
    }
