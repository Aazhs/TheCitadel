"""Business logic for the accountability system.

Handles state machine transitions, priority scoring, escalation tracking,
and activity logging. All functions take an AsyncSession parameter to stay
testable and consistent with the existing service pattern.

Uses the main Postgres database (same as competitive-programming features).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select, update

from src.db.models import (
    AccActivityLog as ActivityLog,
)
from src.db.models import (
    AccSession as ActiveSession,
)
from src.db.models import (
    AccTask as Task,
)
from src.db.models import (
    AccUserContext as UserContext,
)
from src.db.models import (
    LogType,
    TaskPriority,
    TaskStatus,
)

logger = logging.getLogger("arena.services.accountability")

# ---------------------------------------------------------------------------
# Priority Risk scoring weights — documented as tunable in the roadmap
# ---------------------------------------------------------------------------

_PRIORITY_WEIGHTS: dict[str, float] = {
    TaskPriority.LOW.value: 1.0,
    TaskPriority.MEDIUM.value: 3.0,
    TaskPriority.HIGH.value: 5.0,
}

_OVERDUE_WEIGHT: float = 0.5  # per overdue hour


def priority_risk_score(task: Task, now: datetime | None = None) -> float:
    """Calculate Priority Risk score for a task.

    Formula: priority_weight + overdue_hours * 0.5
    Higher score = more urgent. Tasks with no scheduled_time get 0 overdue bonus.

    Args:
        task: The task to score.
        now: Override for current time (useful for testing).

    Returns:
        A float score — higher is more urgent.
    """
    if now is None:
        now = datetime.now()

    weight = _PRIORITY_WEIGHTS.get(task.priority, _PRIORITY_WEIGHTS[TaskPriority.MEDIUM.value])

    overdue_hours = 0.0
    if task.scheduled_time and task.scheduled_time.replace(tzinfo=None) < now:
        delta = now - task.scheduled_time.replace(tzinfo=None)
        overdue_hours = delta.total_seconds() / 3600.0

    return weight + (overdue_hours * _OVERDUE_WEIGHT)


# ---------------------------------------------------------------------------
# User context management (single-row table)
# ---------------------------------------------------------------------------


async def get_or_create_context(session) -> UserContext:
    """Get or create the single UserContext row."""
    result = await session.scalar(select(UserContext).limit(1))
    if result is None:
        result = UserContext(subject_name=None, current_topic=None, missed_checkins=0)
        session.add(result)
        await session.commit()
        await session.refresh(result)
    return result


async def increment_missed_checkins(session) -> int:
    """Increment the missed check-in counter and return the new value."""
    ctx = await get_or_create_context(session)
    ctx.missed_checkins += 1
    await session.commit()
    logger.info("Missed check-ins incremented to %d", ctx.missed_checkins)
    return ctx.missed_checkins


async def reset_missed_checkins(session) -> None:
    """Reset the missed check-in counter to zero."""
    ctx = await get_or_create_context(session)
    if ctx.missed_checkins > 0:
        ctx.missed_checkins = 0
        await session.commit()
        logger.info("Missed check-ins reset to 0")


async def update_context(
    session,
    *,
    subject_name: str | None = None,
    current_topic: str | None = None,
    known_blockers: str | None = None,
) -> UserContext:
    """Update fields on the UserContext row."""
    ctx = await get_or_create_context(session)
    if subject_name is not None:
        ctx.subject_name = subject_name
    if current_topic is not None:
        ctx.current_topic = current_topic
    if known_blockers is not None:
        ctx.known_blockers = known_blockers
    await session.commit()
    return ctx


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


async def get_active_session(session) -> ActiveSession | None:
    """Get the currently active work session, if any."""
    stmt = (
        select(ActiveSession)
        .where(ActiveSession.is_active.is_(True))
        .limit(1)
    )
    return await session.scalar(stmt)


async def start_session(session, task_title: str, minutes: int) -> ActiveSession:
    """Start a new work session, creating the task if needed.

    Deactivates any existing active session first.
    """
    # Deactivate any existing active session
    await session.execute(
        update(ActiveSession).where(ActiveSession.is_active.is_(True)).values(is_active=False)
    )

    # Find or create the task
    stmt = select(Task).where(Task.title == task_title).limit(1)
    task = await session.scalar(stmt)
    if task is None:
        task = Task(title=task_title, status=TaskStatus.IN_PROGRESS.value)
        session.add(task)
        await session.flush()
    else:
        task.status = TaskStatus.IN_PROGRESS.value

    now = datetime.now()
    new_session = ActiveSession(
        task_id=task.id,
        start_time=now,
        target_end_time=now + timedelta(minutes=minutes),
        is_active=True,
    )
    session.add(new_session)

    # Update user context
    ctx = await get_or_create_context(session)
    ctx.current_topic = task_title

    await session.commit()
    await session.refresh(new_session)

    logger.info("Started session for '%s' (%d minutes)", task_title, minutes)
    return new_session


async def complete_session(session) -> Task | None:
    """Mark the active session as complete and its task as done."""
    active = await get_active_session(session)
    if active is None:
        return None

    active.is_active = False

    task = await session.scalar(select(Task).where(Task.id == active.task_id))
    if task:
        task.status = TaskStatus.DONE.value

    await session.commit()
    logger.info("Completed session (task: %s)", task.title if task else "unknown")
    return task


async def pause_session(session) -> bool:
    """Pause the active session (deactivate without marking task done)."""
    active = await get_active_session(session)
    if active is None:
        return False

    active.is_active = False
    await session.commit()
    logger.info("Paused active session")
    return True


async def resume_session(session) -> ActiveSession | None:
    """Resume the most recently paused session."""
    stmt = (
        select(ActiveSession)
        .where(ActiveSession.is_active.is_(False))
        .order_by(ActiveSession.start_time.desc())
        .limit(1)
    )
    last_session = await session.scalar(stmt)
    if last_session is None:
        return None

    last_session.is_active = True
    await session.commit()
    logger.info("Resumed session")
    return last_session


# ---------------------------------------------------------------------------
# Task queue
# ---------------------------------------------------------------------------


async def get_task_queue(session) -> list[Task]:
    """Get pending/in-progress tasks sorted by Priority Risk score (descending)."""
    stmt = select(Task).where(Task.status.in_([TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value]))
    tasks = list((await session.scalars(stmt)).all())

    now = datetime.now()
    tasks.sort(key=lambda t: priority_risk_score(t, now), reverse=True)
    return tasks


async def skip_task(session, task_id: int) -> bool:
    """Mark a task as done (skipped) by ID."""
    task = await session.scalar(select(Task).where(Task.id == task_id))
    if task is None:
        return False

    task.status = TaskStatus.DONE.value
    await session.commit()
    logger.info("Skipped task #%d: %s", task_id, task.title)
    return True


# ---------------------------------------------------------------------------
# Activity logging
# ---------------------------------------------------------------------------


async def log_activity(
    session,
    log_type: str | LogType,
    user_update: str | None = None,
    ai_feedback: str | None = None,
) -> ActivityLog:
    """Append an entry to the activity log."""
    if isinstance(log_type, LogType):
        log_type = log_type.value

    entry = ActivityLog(
        timestamp=datetime.now(),
        log_type=log_type,
        user_update=user_update,
        ai_feedback=ai_feedback,
    )
    session.add(entry)
    await session.commit()
    return entry


# ---------------------------------------------------------------------------
# Loop state determination
# ---------------------------------------------------------------------------


def determine_loop_state(active_session: ActiveSession | None) -> str:
    """Determine the current state for the 15-minute check-in loop.

    Returns one of 'active', 'overdue', or 'idle'.
    """
    if active_session is None:
        return "idle"

    now = datetime.now()
    if active_session.target_end_time:
        target = active_session.target_end_time.replace(tzinfo=None) if active_session.target_end_time.tzinfo else active_session.target_end_time
        if target < now:
            return "overdue"

    return "active"


# ---------------------------------------------------------------------------
# Quiet hours check
# ---------------------------------------------------------------------------


def is_quiet_hours(start_str: str, end_str: str) -> bool:
    """Check if the current local time falls within quiet hours."""
    now = datetime.now().time()

    start_parts = start_str.split(":")
    end_parts = end_str.split(":")

    from datetime import time as dt_time

    start = dt_time(int(start_parts[0]), int(start_parts[1]))
    end = dt_time(int(end_parts[0]), int(end_parts[1]))

    if start <= end:
        return start <= now <= end
    else:
        return now >= start or now <= end
