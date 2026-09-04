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
from sqlmodel import Session

from app.database import BASE_DIR, engine, init_db
from app.routers import (
    ai,
    calendar,
    match,
    mock_interviews,
    offers,
    recordings,
    opportunities,
    predictions,
    questions,
    research,
    resumes,
    settings,
    stats,
)
from app.routers.questions import backfill_question_sources
from app.seed import seed_if_empty, seed_offers_if_empty

FRONTEND_DIST = BASE_DIR / "frontend" / "dist"


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
        # v1.8：工作地址（详细地址）
        if "address" not in cols:
            conn.execute(text("ALTER TABLE opportunity ADD COLUMN address TEXT"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    _migrate()
    with Session(engine) as session:
        seed_if_empty(session)
        seed_offers_if_empty(session)
        backfill_question_sources(session)
    yield


app = FastAPI(title="进击の面试 API", version="0.1.1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(opportunities.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
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
