"""Accountability dashboard — FastAPI web UI for the accountability system.

Reads from the same Postgres database as the bot. Shows task queue,
active sessions, and activity log. Deployed alongside the bot on Render.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------------
# Database setup (connects to the same Postgres as the bot)
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/postgres",
)
_engine = None
_session_factory = None


def _init_db():
    """Initialise the async Postgres engine for the dashboard."""
    global _engine, _session_factory
    url = DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    _engine = create_async_engine(url, echo=False)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


def _get_session() -> AsyncSession:
    """Get a new async session."""
    if _session_factory is None:
        _init_db()
    return _session_factory()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise and tear down the database engine."""
    _init_db()
    yield
    if _engine:
        await _engine.dispose()


app = FastAPI(title="Accountability Dashboard", lifespan=lifespan)

# Static files and templates
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ---------------------------------------------------------------------------
# Import models (same models as the bot)
# ---------------------------------------------------------------------------

# We import the model classes inline to avoid pulling in the full bot config.
# The table names are stable since they're managed by Alembic.
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class DashBase(DeclarativeBase):
    pass


class DashAccTask(DashBase):
    __tablename__ = "acc_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    priority: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20))
    scheduled_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DashAccSession(DashBase):
    __tablename__ = "acc_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("acc_tasks.id"))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    target_end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean)


class DashAccActivityLog(DashBase):
    __tablename__ = "acc_activity_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    log_type: Mapped[str] = mapped_column(String(20))
    user_update: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Dashboard landing page — task queue, active session, activity log."""
    async with _get_session() as session:
        # Active tasks
        task_stmt = (
            select(DashAccTask)
            .where(DashAccTask.status.in_(["pending", "in_progress"]))
            .order_by(DashAccTask.created_at.desc())
        )
        tasks = list((await session.scalars(task_stmt)).all())
        task_data = [
            {
                "id": t.id,
                "title": t.title,
                "priority": t.priority,
                "status": t.status,
            }
            for t in tasks
        ]

        # Active session
        session_stmt = (
            select(DashAccSession)
            .where(DashAccSession.is_active.is_(True))
            .limit(1)
        )
        active = await session.scalar(session_stmt)
        session_data = None
        if active:
            task = await session.scalar(
                select(DashAccTask).where(DashAccTask.id == active.task_id)
            )
            elapsed = int(
                (datetime.now() - active.start_time.replace(tzinfo=None)).total_seconds() / 60
            )
            remaining = None
            if active.target_end_time:
                remaining = int(
                    (active.target_end_time.replace(tzinfo=None) - datetime.now()).total_seconds() / 60
                )
            session_data = {
                "task_title": task.title if task else "unknown",
                "elapsed_minutes": elapsed,
                "remaining_minutes": remaining,
                "start_time": active.start_time.strftime("%H:%M"),
            }

        # Activity log (last 20)
        log_stmt = (
            select(DashAccActivityLog)
            .order_by(DashAccActivityLog.timestamp.desc())
            .limit(20)
        )
        logs = list((await session.scalars(log_stmt)).all())
        log_data = [
            {
                "id": log.id,
                "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M"),
                "log_type": log.log_type,
                "user_update": log.user_update,
                "ai_feedback": log.ai_feedback,
            }
            for log in logs
        ]

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "tasks": task_data,
            "active_session": session_data,
            "activity_log": log_data,
            "now": datetime.now().strftime("%Y-%m-%d %H:%M"),
        },
    )


@app.post("/task/edit/{task_id}")
async def edit_task(
    task_id: int,
    title: str = Form(...),
    priority: str = Form("medium"),
):
    """Edit a task's title or priority."""
    async with _get_session() as session:
        task = await session.scalar(
            select(DashAccTask).where(DashAccTask.id == task_id)
        )
        if task:
            task.title = title
            task.priority = priority
            await session.commit()

    return RedirectResponse(url="/", status_code=303)


@app.post("/task/complete/{task_id}")
async def complete_task(task_id: int):
    """Mark a task as done from the dashboard."""
    async with _get_session() as session:
        task = await session.scalar(
            select(DashAccTask).where(DashAccTask.id == task_id)
        )
        if task:
            task.status = "done"
            await session.commit()

    return RedirectResponse(url="/", status_code=303)
