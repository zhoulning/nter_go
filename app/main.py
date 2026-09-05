"""进击の面试 后端入口。

- 开发模式：uvicorn app.main:app --reload（前端另起 vite dev server）
- 使用模式：python run.py（托管 frontend/dist 静态资源并自动打开浏览器）
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlmodel import Session, select

from app.auth import hash_password
from app.database import BASE_DIR, engine, init_db
from app.models import ROLE_ADMIN, USER_ACTIVE, Setting, User
from app.routers import (
    ai,
    audit,
    auth,
    calendar,
    career,
    match,
    mock_interviews,
    notifications,
    offers,
    recordings,
    opportunities,
    predictions,
    questions,
    research,
    resumes,
    settings,
    stats,
    users,
)
from app.routers.questions import backfill_question_sources
from app.seed import seed_if_empty, seed_offers_if_empty

FRONTEND_DIST = BASE_DIR / "frontend" / "dist"

# 业务表清单：多用户改造时需要补 user_id 列并回填
_OWNED_TABLES = (
    "opportunity",
    "interviewround",
    "question",
    "questionsource",
    "resume",
    "offer",
    "recording",
    "reviewreport",
    "researchnote",
    "matchreport",
    "researchmaterial",
    "prediction",
    "mockinterview",
)


def _migrate() -> None:
    """轻量迁移。

    v1.1：看板不再设「笔试」状态，存量数据归入「已投递」。
    v1.2：新增投递时间字段（create_all 不会给已有表加列，需手动 ALTER），
          已投出但缺该字段的岗位用创建时间近似回填。
    """
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE opportunity SET status = 'applied' WHERE status = 'written_test'")
        )
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(opportunity)"))}
        if "applied_at" not in cols:
            conn.execute(text("ALTER TABLE opportunity ADD COLUMN applied_at DATETIME"))
        # v1.4：职责/要求两列合并进统一的工作描述（jd_text），然后删掉旧列
        if "responsibilities" in cols or "requirements" in cols:
            conn.execute(
                text(
                    "UPDATE opportunity SET jd_text = "
                    "TRIM(COALESCE('工作职责：' || char(10) || responsibilities || char(10) || char(10), '') || "
                    "COALESCE('任职要求：' || char(10) || requirements, ''), char(10)) "
                    "WHERE (responsibilities IS NOT NULL OR requirements IS NOT NULL) "
                    "AND (jd_text IS NULL OR jd_text = '')"
                )
            )
            if "responsibilities" in cols:
                conn.execute(text("ALTER TABLE opportunity DROP COLUMN responsibilities"))
            if "requirements" in cols:
                conn.execute(text("ALTER TABLE opportunity DROP COLUMN requirements"))
        conn.execute(
            text(
                "UPDATE opportunity SET applied_at = created_at "
                "WHERE applied_at IS NULL AND status != 'wishlist'"
            )
        )
        # v1.11：题目关联增强 —— 简历关联 + AI 口述版/简答版答案
        qcols = {row[1] for row in conn.execute(text("PRAGMA table_info(question)"))}
        if "resume_id" not in qcols:
            conn.execute(text("ALTER TABLE question ADD COLUMN resume_id INTEGER"))
        if "answer_spoken" not in qcols:
            conn.execute(text("ALTER TABLE question ADD COLUMN answer_spoken TEXT"))
        if "answer_brief" not in qcols:
            conn.execute(text("ALTER TABLE question ADD COLUMN answer_brief TEXT"))
        # v1.7：岗位关联简历 + 简历默认标记
        if "resume_id" not in cols:
            conn.execute(text("ALTER TABLE opportunity ADD COLUMN resume_id INTEGER"))
        # v1.10：AI 矫正稿字段
        rcols = {row[1] for row in conn.execute(text("PRAGMA table_info(recording)"))}
        if "transcript_clean" not in rcols:
            conn.execute(text("ALTER TABLE recording ADD COLUMN transcript_clean TEXT"))
        if "polished_at" not in rcols:
            conn.execute(text("ALTER TABLE recording ADD COLUMN polished_at DATETIME"))
        if "polish_error" not in rcols:
            conn.execute(text("ALTER TABLE recording ADD COLUMN polish_error TEXT"))
        if "polish_status" not in rcols:
            conn.execute(text("ALTER TABLE recording ADD COLUMN polish_status VARCHAR(24) DEFAULT 'none'"))
        if "kind" not in rcols:
            conn.execute(text("ALTER TABLE recording ADD COLUMN kind VARCHAR(24) DEFAULT 'recording'"))
        resume_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(resume)"))}
        if "is_default" not in resume_cols:
            conn.execute(text("ALTER TABLE resume ADD COLUMN is_default BOOLEAN DEFAULT 0"))
        # v1.9：简历结构化文本（AI 整理的 5 大板块）
        if "structured" not in resume_cols:
            conn.execute(text("ALTER TABLE resume ADD COLUMN structured TEXT"))
        # v1.10：简历体检得分 / 优化建议 / 预测面试题
        if "score" not in resume_cols:
            conn.execute(text("ALTER TABLE resume ADD COLUMN score INTEGER"))
        if "review_json" not in resume_cols:
            conn.execute(text("ALTER TABLE resume ADD COLUMN review_json TEXT"))
        if "questions_json" not in resume_cols:
            conn.execute(text("ALTER TABLE resume ADD COLUMN questions_json TEXT"))
        # v1.15：求职者补充背景（AI 体检与出题的重要依据）
        if "background" not in resume_cols:
            conn.execute(text("ALTER TABLE resume ADD COLUMN background TEXT"))
        # v2.1：预测面试题的出题方向（最近一次生成时指定）
        if "questions_direction" not in resume_cols:
            conn.execute(text("ALTER TABLE resume ADD COLUMN questions_direction TEXT"))
        # 简历归档标记（模型已定义，功能接入前先保证列存在）
        if "archived" not in resume_cols:
            conn.execute(text("ALTER TABLE resume ADD COLUMN archived BOOLEAN DEFAULT 0"))
        # v1.8：工作地址（详细地址）
        if "address" not in cols:
            conn.execute(text("ALTER TABLE opportunity ADD COLUMN address TEXT"))
        # v2.0：多用户 —— 业务表补 user_id 列（回填在 lifespan 里拿到 admin id 后做）
        for table in _OWNED_TABLES:
            tcols = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if "user_id" not in tcols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER"))
        # v2.2：每用户一份职业画像（JSON；设默认简历时自动重生成）
        ucols = {row[1] for row in conn.execute(text("PRAGMA table_info(user)"))}
        if "career_profile" not in ucols:
            conn.execute(text("ALTER TABLE user ADD COLUMN career_profile TEXT"))


def _ensure_admin(session: Session) -> User:
    """保证存在超级管理员；全新系统自动创建 admin / admin123。"""
    admin = session.exec(select(User).where(User.role == ROLE_ADMIN)).first()
    if admin is not None:
        return admin
    admin = User(
        username="admin",
        password_hash=hash_password("admin123"),
        display_name="管理员",
        role=ROLE_ADMIN,
        status=USER_ACTIVE,
    )
    session.add(admin)
    session.commit()
    session.refresh(admin)
    print("[init] 已创建超级管理员账号：admin / admin123（请登录后在设置中修改密码）")
    return admin


def _backfill_user_ids(session: Session, admin_id: int) -> None:
    """存量数据全部归属超级管理员 admin。"""
    from sqlalchemy import text as _text

    with engine.begin() as conn:
        for table in _OWNED_TABLES:
            conn.execute(
                _text(f"UPDATE {table} SET user_id = :uid WHERE user_id IS NULL"),
                {"uid": admin_id},
            )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    _migrate()
    with Session(engine) as session:
        admin = _ensure_admin(session)
        _backfill_user_ids(session, admin.id)
        seed_if_empty(session, admin.id)
        seed_offers_if_empty(session)
        backfill_question_sources(session)
        # v2.2：画像改为每用户一份 —— 旧版全局画像（Setting.career_profile）迁移给 admin
        legacy = session.get(Setting, "career_profile")
        if legacy is not None and legacy.value.strip():
            if not (admin.career_profile or "").strip():
                admin.career_profile = legacy.value
                session.add(admin)
            session.delete(legacy)
            session.commit()
    yield


app = FastAPI(title="进击の面试 API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(audit.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")
app.include_router(opportunities.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(career.router, prefix="/api")
app.include_router(ai.router, prefix="/api")
app.include_router(calendar.router, prefix="/api")
app.include_router(questions.router, prefix="/api")
app.include_router(resumes.router, prefix="/api")
app.include_router(offers.router, prefix="/api")
app.include_router(recordings.router, prefix="/api")
app.include_router(research.router, prefix="/api")
app.include_router(match.router, prefix="/api")
app.include_router(predictions.router, prefix="/api")
app.include_router(mock_interviews.router, prefix="/api")
app.include_router(stats.router, prefix="/api")

# 生产模式：托管前端构建产物（SPA 回退到 index.html）
if FRONTEND_DIST.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            return {"detail": "Not Found"}
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
