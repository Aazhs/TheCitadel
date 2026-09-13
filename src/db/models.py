"""SQLAlchemy ORM models for The Citadel."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, PortableJSONB


class GuildSettings(Base):
    """Per-guild configuration for the bot."""

    __tablename__ = "guild_settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    discord_guild_id: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )
    timezone: Mapped[str] = mapped_column(String(50), default="UTC", server_default="UTC")
    onboarding_channel_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    announcement_channel_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    contest_alert_channel_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    alert_role_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    auto_create_events: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    last_auto_event_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    members: Mapped[list[GuildMember]] = relationship(
        "GuildMember", back_populates="guild_settings", cascade="all, delete-orphan"
    )
    events: Mapped[list[Event]] = relationship(
        "Event", back_populates="guild_settings", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<GuildSettings(id={self.id}, guild={self.discord_guild_id})>"


class GuildAdmin(Base):
    """Admin access for the web dashboard."""

    __tablename__ = "guild_admins"
    __table_args__ = (UniqueConstraint("guild_settings_id", "discord_user_id", name="uq_guild_admin"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    guild_settings_id: Mapped[int] = mapped_column(
        ForeignKey("guild_settings.id", ondelete="CASCADE"), nullable=False
    )
    discord_user_id: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    guild_settings: Mapped[GuildSettings] = relationship("GuildSettings")

    def __repr__(self) -> str:
        return f"<GuildAdmin(id={self.id}, user={self.discord_user_id}, guild={self.guild_settings_id})>"


class User(Base):
    """A Discord user known to the bot."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    discord_user_id: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    memberships: Mapped[list[GuildMember]] = relationship(
        "GuildMember", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, discord={self.discord_user_id})>"


class GuildMember(Base):
    """Association between a user and a guild, with Citadel-specific state."""

    __tablename__ = "guild_members"
    __table_args__ = (UniqueConstraint("guild_settings_id", "user_id", name="uq_guild_member"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    guild_settings_id: Mapped[int] = mapped_column(
        ForeignKey("guild_settings.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    verified_competitor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Leaderboard & Statistics
    arena_points_all_time: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    arena_points_current_cycle: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    events_participated: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    verified_results_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    problems_solved_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    current_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    longest_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # Star Ratings
    cp_star_rating: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    dsa_star_rating: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    guild_settings: Mapped[GuildSettings] = relationship("GuildSettings", back_populates="members")
    user: Mapped[User] = relationship("User", back_populates="memberships")
    linked_accounts: Mapped[list[LinkedAccount]] = relationship(
        "LinkedAccount", back_populates="guild_member", cascade="all, delete-orphan"
    )
    event_registrations: Mapped[list[EventRegistration]] = relationship(
        "EventRegistration", back_populates="guild_member", cascade="all, delete-orphan"
    )
    event_submissions: Mapped[list[EventSubmission]] = relationship(
        "EventSubmission", back_populates="guild_member", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<GuildMember(id={self.id}, guild_settings_id={self.guild_settings_id}, "
            f"user_id={self.user_id})>"
        )


class LinkedAccount(Base):
    """A linked competitive programming account."""

    __tablename__ = "linked_accounts"
    __table_args__ = (
        UniqueConstraint("guild_member_id", "platform", name="uq_linked_account_platform"),
        Index("ix_linked_accounts_normalized_handle", "normalized_handle"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    guild_member_id: Mapped[int] = mapped_column(
        ForeignKey("guild_members.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    handle: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_handle: Mapped[str] = mapped_column(String(255), nullable=False)
    profile_url: Mapped[str] = mapped_column(String(255), nullable=False)
    validation_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    current_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    global_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    guild_member: Mapped[GuildMember] = relationship(
        "GuildMember", back_populates="linked_accounts"
    )

    def __repr__(self) -> str:
        return f"<LinkedAccount(id={self.id}, platform={self.platform}, handle={self.handle})>"


class Contest(Base):
    """A competitive programming contest from an external platform."""

    __tablename__ = "contests"
    __table_args__ = (
        UniqueConstraint("platform", "external_contest_id", name="uq_contest_platform_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    external_contest_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    start_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phase: Mapped[str] = mapped_column(String(50), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Contest(id={self.id}, platform={self.platform}, name={self.name})>"


class NotificationDelivery(Base):
    """Tracks a scheduled or sent reminder notification."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "guild_settings_id",
            "contest_id",
            "notification_type",
            name="uq_delivery_guild_contest_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    guild_settings_id: Mapped[int] = mapped_column(
        ForeignKey("guild_settings.id", ondelete="CASCADE"), nullable=False
    )
    contest_id: Mapped[int] = mapped_column(
        ForeignKey("contests.id", ondelete="CASCADE"), nullable=False
    )
    notification_type: Mapped[str] = mapped_column(String(10), nullable=False)  # '24h', '1h', '10m'

    scheduled_for_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING"
    )  # 'PENDING', 'SENT', 'FAILED'
    discord_message_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    guild_settings: Mapped[GuildSettings] = relationship("GuildSettings")
    contest: Mapped[Contest] = relationship("Contest")

    def __repr__(self) -> str:
        return f"<NotificationDelivery(id={self.id}, type={self.notification_type}, status={self.status})>"


class Event(Base):
    """An admin-created coding event (contest, watch party, practice session, etc.)."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    guild_settings_id: Mapped[int] = mapped_column(
        ForeignKey("guild_settings.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    official_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    start_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    registration_deadline_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    submission_deadline_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    results_require_moderator_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    announcement_channel_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    discussion_channel_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    results_channel_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    announcement_message_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    points_config: Mapped[dict | None] = mapped_column(PortableJSONB, nullable=True)
    created_by_discord_user_id: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    guild_settings: Mapped[GuildSettings] = relationship("GuildSettings", back_populates="events")
    registrations: Mapped[list[EventRegistration]] = relationship(
        "EventRegistration", back_populates="event", cascade="all, delete-orphan"
    )
    submissions: Mapped[list[EventSubmission]] = relationship(
        "EventSubmission", back_populates="event", cascade="all, delete-orphan"
    )
    leaderboard_entries: Mapped[list[EventLeaderboardEntry]] = relationship(
        "EventLeaderboardEntry", back_populates="event", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Event(id={self.id}, title={self.title!r}, status={self.status})>"


class EventRegistration(Base):
    """A member's registration for a coding event."""

    __tablename__ = "event_registrations"
    __table_args__ = (
        UniqueConstraint("event_id", "guild_member_id", name="uq_event_registration"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    guild_member_id: Mapped[int] = mapped_column(
        ForeignKey("guild_members.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="registered")
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    event: Mapped[Event] = relationship("Event", back_populates="registrations")
    guild_member: Mapped[GuildMember] = relationship(
        "GuildMember", back_populates="event_registrations"
    )

    def __repr__(self) -> str:
        return (
            f"<EventRegistration(id={self.id}, event_id={self.event_id}, "
            f"guild_member_id={self.guild_member_id})>"
        )




class EventSubmission(Base):
    """A member's self-reported results for a coding event."""

    __tablename__ = "event_submissions"
    __table_args__ = (UniqueConstraint("event_id", "guild_member_id", name="uq_event_submission"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    guild_member_id: Mapped[int] = mapped_column(
        ForeignKey("guild_members.id", ondelete="CASCADE"), nullable=False
    )
    questions_solved: Mapped[int] = mapped_column(Integer, nullable=False)
    claimed_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    claimed_rating_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    claimed_rating_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    claimed_rating_change: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reflection: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    verified_by_discord_user_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    moderator_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    points_awarded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_breakdown: Mapped[dict | None] = mapped_column(PortableJSONB, nullable=True)

    # Relationships
    event: Mapped[Event] = relationship("Event", back_populates="submissions")
    guild_member: Mapped[GuildMember] = relationship(
        "GuildMember", back_populates="event_submissions"
    )

    def __repr__(self) -> str:
        return (
            f"<EventSubmission(id={self.id}, event_id={self.event_id}, "
            f"status={self.verification_status})>"
        )


class EventLeaderboardEntry(Base):
    """Computed leaderboard entry for a member in a specific event."""

    __tablename__ = "event_leaderboard_entries"
    __table_args__ = (
        UniqueConstraint("event_id", "guild_member_id", name="uq_event_lb_entry"),
        Index("ix_event_lb_event_rank", "event_id", "rank"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    guild_member_id: Mapped[int] = mapped_column(
        ForeignKey("guild_members.id", ondelete="CASCADE"), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    total_points: Mapped[int] = mapped_column(Integer, nullable=False)
    score_breakdown: Mapped[dict | None] = mapped_column(PortableJSONB, nullable=True)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    event: Mapped[Event] = relationship("Event", back_populates="leaderboard_entries")
    guild_member: Mapped[GuildMember] = relationship("GuildMember")

    def __repr__(self) -> str:
        return (
            f"<EventLeaderboardEntry(id={self.id}, event_id={self.event_id}, "
            f"rank={self.rank}, points={self.total_points})>"
        )


class AuditLog(Base):
    """Tracks moderator actions for accountability."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    guild_settings_id: Mapped[int] = mapped_column(
        ForeignKey("guild_settings.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    performed_by_discord_user_id: Mapped[str] = mapped_column(String(20), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    guild_settings: Mapped[GuildSettings] = relationship("GuildSettings")

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action={self.action!r})>"


class RoleMapping(Base):
    """Configuration for server roles managed by the bot (ratings and achievements)."""

    __tablename__ = "role_mappings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    guild_settings_id: Mapped[int] = mapped_column(
        ForeignKey("guild_settings.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # 'cp_rating', 'dsa_rating', 'achievement', 'champion'
    min_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    role_id: Mapped[str] = mapped_column(String(20), nullable=False)
    role_name_cache: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    guild_settings: Mapped[GuildSettings] = relationship("GuildSettings")

    def __repr__(self) -> str:
        return f"<RoleMapping(id={self.id}, category={self.category}, role_id={self.role_id})>"


# ---------------------------------------------------------------------------
# Accountability system models
# ---------------------------------------------------------------------------



class TaskPriority(enum.StrEnum):
    """Priority level for an accountability task."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskStatus(enum.StrEnum):
    """Lifecycle status of an accountability task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class LogType(enum.StrEnum):
    """Category of an accountability activity log entry."""

    CHECK_IN = "check_in"
    ESCALATION = "escalation"
    COMMAND = "command"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    DISTRACTION = "distraction"
    PARSE_ERROR = "parse_error"


class AccTask(Base):
    """A unit of work tracked by the accountability system."""

    __tablename__ = "acc_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    priority: Mapped[str] = mapped_column(
        String(10), default=TaskPriority.MEDIUM.value, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default=TaskStatus.PENDING.value, nullable=False
    )
    scheduled_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    sessions: Mapped[list[AccSession]] = relationship(
        "AccSession", back_populates="task", cascade="all, delete-orphan"
    )


class AccSession(Base):
    """Tracks active work sessions for accountability tasks."""

    __tablename__ = "acc_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("acc_tasks.id"), nullable=False)
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    target_end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    task: Mapped[AccTask] = relationship("AccTask", back_populates="sessions")


class AccUserContext(Base):
    """Persistent context about the user for subject-aware check-ins.

    Expected to hold exactly one row, upserted on each update.
    """

    __tablename__ = "acc_user_context"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subject_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_topic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    known_blockers: Mapped[str | None] = mapped_column(Text, nullable=True)
    missed_checkins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class AccActivityLog(Base):
    """Append-only audit trail for all accountability system events."""

    __tablename__ = "acc_activity_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    log_type: Mapped[str] = mapped_column(String(20), nullable=False)
    user_update: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)

