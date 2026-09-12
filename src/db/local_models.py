"""ORM models for the local accountability database.

These tables live in a local SQLite file and are completely separate from
the Postgres models in models.py. They are registered on LocalBase and
managed by local_engine.py's create_all() — no Alembic migrations.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.local_base import LocalBase


# ---------------------------------------------------------------------------
# Enums (stored as strings in SQLite)
# ---------------------------------------------------------------------------


class TaskPriority(enum.StrEnum):
    """Priority level for a task."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskStatus(enum.StrEnum):
    """Lifecycle status of a task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class LogType(enum.StrEnum):
    """Category of an activity log entry."""

    CHECK_IN = "check_in"
    ESCALATION = "escalation"
    COMMAND = "command"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    DISTRACTION = "distraction"
    PARSE_ERROR = "parse_error"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Task(LocalBase):
    """A unit of work to be tracked by the accountability system."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    priority: Mapped[str] = mapped_column(
        String(10), default=TaskPriority.MEDIUM.value, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default=TaskStatus.PENDING.value, nullable=False
    )
    scheduled_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    sessions: Mapped[list[ActiveSession]] = relationship(
        "ActiveSession", back_populates="task", cascade="all, delete-orphan"
    )


class ActiveSession(LocalBase):
    """Tracks the currently active work session for a task."""

    __tablename__ = "active_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False)
    start_time: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    target_end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    task: Mapped[Task] = relationship("Task", back_populates="sessions")


class UserContext(LocalBase):
    """Persistent context about the user for subject-aware check-ins.

    This table is expected to hold exactly one row, upserted on each update.
    """

    __tablename__ = "user_context"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subject_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_topic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    known_blockers: Mapped[str | None] = mapped_column(Text, nullable=True)
    missed_checkins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ActivityLog(LocalBase):
    """Append-only audit trail for all accountability system events."""

    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    log_type: Mapped[str] = mapped_column(String(20), nullable=False)
    user_update: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
