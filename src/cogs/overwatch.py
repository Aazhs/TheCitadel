"""Overwatch cog — private-channel personal productivity enforcer.

Runs a 15-minute check-in loop that pings the configured user in a
private guild channel, demands progress updates, and escalates tone on
missed check-ins. Uses Gemini API for intent parsing and the main
Postgres database. Deployed alongside the rest of Citadel on Render.

All commands use Discord slash commands (/ow-*).
"""

from __future__ import annotations

import logging
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks
from sqlalchemy import select

from src.config import get_settings
from src.db.engine import get_session_factory
from src.db.models import AccTask, LogType
from src.providers import gemini_client
from src.services import overwatch as ow_service

logger = logging.getLogger("arena.cogs.overwatch")

CHANNEL_NAME = "overwatch-zone"


class Overwatch(commands.Cog):
    """Private-channel overwatch cog for a single user.

    On load, creates (or finds) a private text channel visible only to
    the target user and the bot. Check-ins and escalation happen in that
    channel. Task management uses slash commands usable anywhere.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.settings = get_settings()
        self.user_id = int(self.settings.overwatch_user_id)  # type: ignore[arg-type]
        self.guild_id = int(self.settings.overwatch_guild_id)  # type: ignore[arg-type]
        self._channel: discord.TextChannel | None = None

    async def cog_load(self) -> None:
        """Start the check-in loop."""
        if not self.settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required for the Overwatch cog")

        self.checkin_loop.start()
        logger.info("Overwatch cog loaded — loop started for user %s", self.user_id)

    async def cog_unload(self) -> None:
        """Cancel the loop."""
        self.checkin_loop.cancel()
        logger.info("Overwatch cog unloaded")

    # ------------------------------------------------------------------
    # Channel management
    # ------------------------------------------------------------------

    async def _ensure_channel(self) -> discord.TextChannel | None:
        """Find or create the private overwatch channel."""
        if self._channel is not None:
            return self._channel

        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            logger.error("Overwatch guild %s not found", self.guild_id)
            return None

        for ch in guild.text_channels:
            if ch.name == CHANNEL_NAME:
                self._channel = ch
                logger.info("Found existing overwatch channel: #%s", ch.name)
                return self._channel

        target_member = guild.get_member(self.user_id)
        if target_member is None:
            try:
                target_member = await guild.fetch_member(self.user_id)
            except discord.NotFound:
                logger.error("Target user %s not found in guild %s", self.user_id, self.guild_id)
                return None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                embed_links=True,
            ),
            target_member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            ),
        }

        try:
            self._channel = await guild.create_text_channel(
                name=CHANNEL_NAME,
                overwrites=overwrites,
                topic="🔒 Private overwatch zone — bot check-ins and task tracking",
                reason="Overwatch cog: private channel for check-ins",
            )
            logger.info("Created private overwatch channel: #%s", self._channel.name)
            return self._channel
        except discord.Forbidden:
            logger.error("Missing permissions to create channel in guild %s", self.guild_id)
            return None
        except Exception:
            logger.exception("Failed to create overwatch channel")
            return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_overwatch_msg(self, message: discord.Message) -> bool:
        """Check if a message is from the target user in the overwatch channel."""
        return (
            self._channel is not None
            and message.channel.id == self._channel.id
            and message.author.id == self.user_id
            and not message.author.bot
        )

    async def _send(self, text: str) -> discord.Message | None:
        """Send a message to the overwatch channel."""
        channel = await self._ensure_channel()
        if channel is None:
            return None
        try:
            return await channel.send(text)
        except discord.Forbidden:
            logger.error("Cannot send to overwatch channel — missing permissions")
            return None

    async def _ping(self, text: str) -> discord.Message | None:
        """Send a message that pings the target user."""
        return await self._send(f"<@{self.user_id}> {text}")

    def _session_context_dict(self, active_session, task=None) -> dict:
        """Build a session context dict for the LLM."""
        ctx: dict = {}
        if active_session:
            if task:
                ctx["task_title"] = task.title
            if active_session.target_end_time:
                remaining = (active_session.target_end_time.replace(tzinfo=None) - datetime.now()).total_seconds() / 60
                ctx["minutes_remaining"] = max(0, int(remaining))
        return ctx

    def _user_context_dict(self, user_context) -> dict:
        """Build a user context dict for the LLM."""
        return {
            "current_topic": user_context.current_topic,
            "subject_name": user_context.subject_name,
            "known_blockers": user_context.known_blockers,
        }

    # ------------------------------------------------------------------
    # 15-minute check-in loop
    # ------------------------------------------------------------------

    @tasks.loop(minutes=15)
    async def checkin_loop(self) -> None:
        """Core overwatch loop — runs every 15 minutes."""
        try:
            if ow_service.is_quiet_hours(
                self.settings.quiet_hours_start,
                self.settings.quiet_hours_end,
            ):
                logger.debug("Quiet hours — skipping check-in")
                return

            channel = await self._ensure_channel()
            if channel is None:
                logger.warning("No overwatch channel — skipping check-in")
                return

            async with get_session_factory()() as session:
                user_context = await ow_service.get_or_create_context(session)
                active_session = await ow_service.get_active_session(session)
                state = ow_service.determine_loop_state(active_session)

                task = None
                if active_session:
                    task = await session.scalar(
                        select(AccTask).where(AccTask.id == active_session.task_id)
                    )

                tone = gemini_client.escalation_tone(user_context.missed_checkins)
                api_key = self.settings.gemini_api_key
                model = self.settings.gemini_model

                if state == "active":
                    task_name = task.title if task else "your current task"
                    msg = f"⏱️ **Check-in** — How's progress on **{task_name}**?"
                    if active_session.target_end_time:
                        remaining = (
                            active_session.target_end_time.replace(tzinfo=None) - datetime.now()
                        ).total_seconds() / 60
                        msg += f" ({max(0, int(remaining))} min remaining)"

                elif state == "overdue":
                    task_name = task.title if task else "your task"
                    feedback = await gemini_client.generate_feedback(
                        intent="DISTRACTED",
                        context=f"Task '{task_name}' is OVERDUE. User has not responded.",
                        tone=tone,
                        api_key=api_key,
                        model=model,
                    )
                    msg = f"🚨 **OVERDUE** — **{task_name}** passed its target time.\n{feedback}"

                else:  # idle
                    queue = await ow_service.get_task_queue(session)
                    if queue:
                        top_task = queue[0]
                        score = ow_service.priority_risk_score(top_task)
                        msg = (
                            f"📋 **What's next?** — Top priority: **{top_task.title}** "
                            f"(risk score: {score:.1f})\n"
                            f"Use `/ow-start` to begin a session."
                        )
                    else:
                        msg = (
                            "📋 **No tasks in queue.** What are you working on?\n"
                            "Use `/ow-start` to begin a session."
                        )

                sent = await self._ping(msg)
                if sent is None:
                    return

                await ow_service.log_activity(
                    session,
                    LogType.CHECK_IN,
                    ai_feedback=msg,
                )

                # Wait for a reply in the channel (14-minute window)
                def check(m: discord.Message) -> bool:
                    return self._is_overwatch_msg(m) and not m.content.startswith("/")

                try:
                    reply = await self.bot.wait_for("message", check=check, timeout=840)
                except TimeoutError:
                    missed = await ow_service.increment_missed_checkins(session)
                    esc_tone = gemini_client.escalation_tone(missed)
                    nag = await gemini_client.generate_feedback(
                        intent="DISTRACTED",
                        context=f"User has ignored {missed} consecutive check-in(s).",
                        tone=esc_tone,
                        api_key=api_key,
                        model=model,
                    )
                    await self._ping(f"⚠️ **Missed check-in #{missed}**\n{nag}")
                    await ow_service.log_activity(
                        session,
                        LogType.ESCALATION,
                        ai_feedback=nag,
                    )
                    return

                # Got a reply — parse intent
                await ow_service.reset_missed_checkins(session)

                intent_result = await gemini_client.parse_user_intent(
                    reply.content,
                    session_context=self._session_context_dict(active_session, task),
                    user_context=self._user_context_dict(user_context),
                    api_key=api_key,
                    model=model,
                )

                if intent_result.intent == "UNCLEAR" and not intent_result.summary:
                    await self._send(
                        "❓ I couldn't parse that. Could you rephrase? "
                        "What are you working on right now?"
                    )
                    await ow_service.log_activity(
                        session,
                        LogType.PARSE_ERROR,
                        user_update=reply.content,
                        ai_feedback=intent_result.raw_response,
                    )
                    return

                context_str = f"Task: {task.title if task else 'none'}, User said: {reply.content}"
                feedback = await gemini_client.generate_feedback(
                    intent=intent_result.intent,
                    context=context_str,
                    tone=tone,
                    api_key=api_key,
                    model=model,
                )

                if intent_result.intent == "COMPLETED" and active_session:
                    completed_task = await ow_service.complete_session(session)
                    task_name = completed_task.title if completed_task else "your task"
                    await self._send(f"✅ **{task_name}** marked done.\n{feedback}")
                    await ow_service.log_activity(
                        session, LogType.SESSION_END,
                        user_update=reply.content, ai_feedback=feedback,
                    )

                elif intent_result.intent == "DISTRACTED":
                    await self._send(f"🔴 **Off track.**\n{feedback}")
                    await ow_service.log_activity(
                        session, LogType.DISTRACTION,
                        user_update=reply.content, ai_feedback=feedback,
                    )

                elif intent_result.intent == "START_SESSION":
                    title = intent_result.task_title or "unnamed task"
                    mins = intent_result.minutes or 30
                    await ow_service.start_session(session, title, mins)
                    await self._send(f"🚀 **Session started:** {title} ({mins} min)\n{feedback}")
                    await ow_service.log_activity(
                        session, LogType.SESSION_START,
                        user_update=reply.content, ai_feedback=feedback,
                    )

                else:
                    await self._send(feedback)
                    await ow_service.log_activity(
                        session, LogType.CHECK_IN,
                        user_update=reply.content, ai_feedback=feedback,
                    )

        except Exception as e:
            logger.exception("Error in overwatch check-in loop: %s", e)

    @checkin_loop.before_loop
    async def before_checkin_loop(self) -> None:
        """Wait until the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------
    # Slash commands — /ow-*
    # ------------------------------------------------------------------

    @app_commands.command(name="ow-start", description="Start a timed work session on a task")
    @app_commands.describe(task="What you're working on", minutes="How many minutes (default: 30)")
    async def ow_start(
        self,
        interaction: discord.Interaction,
        task: str,
        minutes: int = 30,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        async with get_session_factory()() as session:
            await ow_service.start_session(session, task, minutes)
            await ow_service.log_activity(
                session, LogType.COMMAND,
                user_update=f"/ow-start {task} {minutes}",
                ai_feedback=f"Started session: {task} ({minutes} min)",
            )

        await interaction.followup.send(
            f"🚀 **Session started:** {task}\n"
            f"⏱️ Target: {minutes} minutes\n"
            f"I'll check in on you in `#overwatch-zone`.",
            ephemeral=True,
        )

        # Also notify in the overwatch channel
        await self._send(
            f"🚀 **Session started:** {task} ({minutes} min)\n"
            f"Check-ins will fire every 15 minutes."
        )

    @app_commands.command(name="ow-status", description="Check your current session and stats")
    async def ow_status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        async with get_session_factory()() as session:
            active = await ow_service.get_active_session(session)
            ctx = await ow_service.get_or_create_context(session)

            embed = discord.Embed(title="📊 Overwatch Status", color=discord.Color.dark_gold())

            if active:
                task = await session.scalar(select(AccTask).where(AccTask.id == active.task_id))
                task_name = task.title if task else "unknown"

                remaining = "N/A"
                if active.target_end_time:
                    delta = (active.target_end_time.replace(tzinfo=None) - datetime.now()).total_seconds() / 60
                    remaining = f"{max(0, int(delta))} min"

                elapsed = int((datetime.now() - active.start_time.replace(tzinfo=None)).total_seconds() / 60)

                embed.add_field(name="Task", value=f"**{task_name}**", inline=True)
                embed.add_field(name="Elapsed", value=f"{elapsed} min", inline=True)
                embed.add_field(name="Remaining", value=remaining, inline=True)
            else:
                embed.description = "No active session. Use `/ow-start` to begin."

            embed.add_field(name="Missed Check-ins", value=str(ctx.missed_checkins), inline=True)

            if ctx.current_topic:
                embed.add_field(name="Current Topic", value=ctx.current_topic, inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="ow-done", description="Mark your current task as complete")
    async def ow_done(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        async with get_session_factory()() as session:
            completed_task = await ow_service.complete_session(session)
            if completed_task:
                await ow_service.log_activity(
                    session, LogType.SESSION_END,
                    user_update="/ow-done",
                    ai_feedback=f"Completed: {completed_task.title}",
                )
                await interaction.followup.send(
                    f"✅ **{completed_task.title}** marked done.", ephemeral=True
                )
                await self._send(f"✅ **{completed_task.title}** marked done.")
            else:
                await interaction.followup.send(
                    "No active session to complete.", ephemeral=True
                )

    @app_commands.command(name="ow-pause", description="Pause the current session")
    async def ow_pause(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        async with get_session_factory()() as session:
            paused = await ow_service.pause_session(session)
            if paused:
                await ow_service.log_activity(session, LogType.COMMAND, user_update="/ow-pause")
                await interaction.followup.send("⏸️ Session paused.", ephemeral=True)
                await self._send("⏸️ Session paused.")
            else:
                await interaction.followup.send("No active session to pause.", ephemeral=True)

    @app_commands.command(name="ow-resume", description="Resume the last paused session")
    async def ow_resume(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        async with get_session_factory()() as session:
            resumed = await ow_service.resume_session(session)
            if resumed:
                await ow_service.log_activity(session, LogType.COMMAND, user_update="/ow-resume")
                await interaction.followup.send("▶️ Session resumed.", ephemeral=True)
                await self._send("▶️ Session resumed.")
            else:
                await interaction.followup.send("No paused session to resume.", ephemeral=True)

    @app_commands.command(name="ow-queue", description="View your task queue sorted by priority")
    async def ow_queue(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        async with get_session_factory()() as session:
            queue = await ow_service.get_task_queue(session)

            if not queue:
                await interaction.followup.send(
                    "📋 **Queue is empty.** Use `/ow-start` to add work.",
                    ephemeral=True,
                )
                return

            embed = discord.Embed(
                title="📋 Task Queue",
                description="Sorted by priority risk score (highest first)",
                color=discord.Color.dark_teal(),
            )

            for i, task in enumerate(queue[:10], 1):
                score = ow_service.priority_risk_score(task)
                status_emoji = "🔵" if task.status == "pending" else "🟡"
                embed.add_field(
                    name=f"{i}. {status_emoji} {task.title}",
                    value=f"Priority: `{task.priority}` | Risk: `{score:.1f}` | ID: `{task.id}`",
                    inline=False,
                )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="ow-skip", description="Skip/remove the top task or a specific task")
    @app_commands.describe(task_id="Task ID to skip (omit to skip top task)")
    async def ow_skip(
        self,
        interaction: discord.Interaction,
        task_id: int | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        async with get_session_factory()() as session:
            if task_id is not None:
                skipped = await ow_service.skip_task(session, task_id)
                if skipped:
                    await ow_service.log_activity(
                        session, LogType.COMMAND, user_update=f"/ow-skip {task_id}"
                    )
                    await interaction.followup.send(
                        f"⏭️ Task #{task_id} skipped.", ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"Task #{task_id} not found.", ephemeral=True
                    )
            else:
                queue = await ow_service.get_task_queue(session)
                if queue:
                    top = queue[0]
                    await ow_service.skip_task(session, top.id)
                    await ow_service.log_activity(
                        session, LogType.COMMAND,
                        user_update=f"/ow-skip (top: {top.title})",
                    )
                    await interaction.followup.send(
                        f"⏭️ Skipped **{top.title}**.", ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "Queue is empty, nothing to skip.", ephemeral=True
                    )

    @app_commands.command(name="ow-log", description="View recent activity log")
    @app_commands.describe(count="Number of entries to show (default: 10)")
    async def ow_log(
        self,
        interaction: discord.Interaction,
        count: int = 10,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        from src.db.models import AccActivityLog

        async with get_session_factory()() as session:
            stmt = (
                select(AccActivityLog)
                .order_by(AccActivityLog.timestamp.desc())
                .limit(min(count, 20))
            )
            logs = list((await session.scalars(stmt)).all())

        if not logs:
            await interaction.followup.send("📜 No activity yet.", ephemeral=True)
            return

        embed = discord.Embed(
            title="📜 Overwatch Activity Log",
            color=discord.Color.greyple(),
        )

        type_emoji = {
            "check_in": "✅",
            "escalation": "⚠️",
            "command": "⌨️",
            "session_start": "🚀",
            "session_end": "🏁",
            "distraction": "🔴",
            "parse_error": "❓",
        }

        for log in logs:
            emoji = type_emoji.get(log.log_type, "📝")
            ts = log.timestamp.strftime("%m/%d %H:%M") if log.timestamp else "?"
            value_parts = []
            if log.user_update:
                value_parts.append(f"**You:** {log.user_update[:80]}")
            if log.ai_feedback:
                value_parts.append(f"**Bot:** {log.ai_feedback[:80]}")

            embed.add_field(
                name=f"{emoji} {log.log_type.replace('_', ' ').title()} — {ts}",
                value="\n".join(value_parts) if value_parts else "—",
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="ow-add", description="Add a task to the queue without starting a session")
    @app_commands.describe(
        task="Task name",
        priority="Priority level (low/medium/high)",
    )
    @app_commands.choices(priority=[
        app_commands.Choice(name="Low", value="low"),
        app_commands.Choice(name="Medium", value="medium"),
        app_commands.Choice(name="High", value="high"),
    ])
    async def ow_add(
        self,
        interaction: discord.Interaction,
        task: str,
        priority: str = "medium",
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        from src.db.models import TaskStatus

        async with get_session_factory()() as session:
            new_task = AccTask(
                title=task,
                priority=priority,
                status=TaskStatus.PENDING.value,
            )
            session.add(new_task)
            await session.commit()
            await session.refresh(new_task)

            await ow_service.log_activity(
                session, LogType.COMMAND,
                user_update=f"/ow-add {task} [{priority}]",
            )

        await interaction.followup.send(
            f"📌 Added **{task}** (priority: `{priority}`, ID: `{new_task.id}`).",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(Overwatch(bot))
