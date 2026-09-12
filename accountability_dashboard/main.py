"""FastAPI dashboard for the accountability system.

Reads/writes the same local SQLite database that the accountability cog
uses. Fully separate from the Next.js dashboard — own process, own port,
no shared auth.

Run with: uvicorn accountability_dashboard.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path

# Add the project root to sys.path so we can import src.db.local_models
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.local_models import (
    ActiveSession,
    ActivityLog,
    Task,
    TaskPriority,
    TaskStatus,
)

# ---------------------------------------------------------------------------
# Database setup (own engine, reads the same .db file as the cog)
# ---------------------------------------------------------------------------


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
# Helper: priority risk score (duplicated from service to avoid tight coupling)
# ---------------------------------------------------------------------------

_PRIORITY_WEIGHTS = {
    TaskPriority.LOW.value: 1.0,
    TaskPriority.MEDIUM.value: 3.0,
    TaskPriority.HIGH.value: 5.0,
}


def _priority_risk_score(task: Task) -> float:
    now = datetime.now()
    weight = _PRIORITY_WEIGHTS.get(task.priority, 3.0)
    overdue_hours = 0.0
    if task.scheduled_time and task.scheduled_time < now:
        overdue_hours = (now - task.scheduled_time).total_seconds() / 3600.0
    return weight + (overdue_hours * 0.5)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main dashboard page — task queue, active session, activity log."""
    async with _get_session() as session:
        # Task queue
        stmt = select(Task).where(
            Task.status.in_([TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value])
        )
        tasks = list((await session.scalars(stmt)).all())
        tasks.sort(key=_priority_risk_score, reverse=True)

        # Compute scores for template
        task_data = []
        for t in tasks:
            task_data.append({
                "id": t.id,
                "title": t.title,
                "domain": t.domain,
                "priority": t.priority,
                "status": t.status,
                "scheduled_time": t.scheduled_time,
                "risk_score": round(_priority_risk_score(t), 1),
            })

        # Active session
        active_stmt = select(ActiveSession).where(ActiveSession.is_active.is_(True)).limit(1)
        active_session = await session.scalar(active_stmt)
        session_data = None
        if active_session:
            task = await session.scalar(select(Task).where(Task.id == active_session.task_id))
            elapsed = int((datetime.now() - active_session.start_time).total_seconds() / 60)
            remaining = None
            if active_session.target_end_time:
                remaining = max(
                    0, int((active_session.target_end_time - datetime.now()).total_seconds() / 60)
                )
            session_data = {
                "task_title": task.title if task else "Unknown",
                "start_time": active_session.start_time.strftime("%H:%M"),
                "elapsed_min": elapsed,
                "remaining_min": remaining,
                "target_end": (
                    active_session.target_end_time.strftime("%H:%M")
                    if active_session.target_end_time
                    else None
                ),
            }

        # Activity log (last 25 entries)
        log_stmt = select(ActivityLog).order_by(ActivityLog.timestamp.desc()).limit(25)
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
        "index.html",
        {
            "request": request,
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
    priority: str = Form(...),
    scheduled_time: str = Form(None),
):
    """Update task metadata."""
    async with _get_session() as session:
        task = await session.scalar(select(Task).where(Task.id == task_id))
        if task:
            task.title = title
            task.priority = priority
            if scheduled_time:
                try:
                    task.scheduled_time = datetime.fromisoformat(scheduled_time)
                except ValueError:
                    pass
            await session.commit()
    return RedirectResponse(url="/", status_code=303)


@app.post("/task/complete/{task_id}")
async def complete_task(task_id: int):
    """Mark a task as done."""
    async with _get_session() as session:
        task = await session.scalar(select(Task).where(Task.id == task_id))
        if task:
            task.status = TaskStatus.DONE.value
            await session.commit()
    return RedirectResponse(url="/", status_code=303)


@app.post("/session/cancel")
async def cancel_session():
    """Cancel the active session."""
    async with _get_session() as session:
        await session.execute(
            update(ActiveSession)
            .where(ActiveSession.is_active.is_(True))
            .values(is_active=False)
        )
        await session.commit()
    return RedirectResponse(url="/", status_code=303)


@app.get("/api/active-session")
async def api_active_session():
    """JSON endpoint for live-polling the active session timer."""
    async with _get_session() as session:
        active = await session.scalar(
            select(ActiveSession).where(ActiveSession.is_active.is_(True)).limit(1)
        )
        if not active:
            return {"active": False}

        task = await session.scalar(select(Task).where(Task.id == active.task_id))
        elapsed = int((datetime.now() - active.start_time).total_seconds())
        remaining = None
        if active.target_end_time:
            remaining = max(0, int((active.target_end_time - datetime.now()).total_seconds()))

        return {
            "active": True,
            "task_title": task.title if task else "Unknown",
            "elapsed_seconds": elapsed,
            "remaining_seconds": remaining,
        }
