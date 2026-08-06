"""SQLAlchemy ORM models for Algorithm Arena."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


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

    def __repr__(self) -> str:
        return f"<GuildSettings(id={self.id}, guild={self.discord_guild_id})>"


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
    """Association between a user and a guild, with arena-specific state."""

    __tablename__ = "guild_members"
    __table_args__ = (UniqueConstraint("guild_settings_id", "user_id", name="uq_guild_member"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    guild_settings_id: Mapped[int] = mapped_column(
        ForeignKey("guild_settings.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    verified_competitor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
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
        UniqueConstraint("guild_settings_id", "contest_id", "notification_type", name="uq_delivery_guild_contest_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    guild_settings_id: Mapped[int] = mapped_column(ForeignKey("guild_settings.id", ondelete="CASCADE"), nullable=False)
    contest_id: Mapped[int] = mapped_column(ForeignKey("contests.id", ondelete="CASCADE"), nullable=False)
    notification_type: Mapped[str] = mapped_column(String(10), nullable=False)  # '24h', '1h', '10m'

    scheduled_for_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")  # 'PENDING', 'SENT', 'FAILED'
    discord_message_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    guild_settings: Mapped[GuildSettings] = relationship("GuildSettings")
    contest: Mapped[Contest] = relationship("Contest")

    def __repr__(self) -> str:
        return f"<NotificationDelivery(id={self.id}, type={self.notification_type}, status={self.status})>"
