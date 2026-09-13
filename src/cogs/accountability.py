"""Accountability cog — private-channel personal accountability system.

Runs a 15-minute check-in loop that pings the configured user in a
private guild channel, demands progress updates, and escalates tone on
missed check-ins. Uses Gemini API for intent parsing and the main
Postgres database. Deployed alongside the rest of Citadel on Render.
"""

from __future__ import annotations

import logging
from datetime import datetime

import discord
from discord.ext import commands, tasks

from src.config import get_settings
from src.db.engine import get_session_factory
from src.db.models import AccTask, LogType
from src.providers import gemini_client
from src.services import accountability as acc_service

logger = logging.getLogger("arena.cogs.accountability")

CHANNEL_NAME = "accountability-zone"


class Accountability(commands.Cog):
    """Private-channel accountability cog for a single user.

    On load, creates (or finds) a private text channel visible only to
    the target user and the bot. All check-ins, commands, and escalation
    happen in that channel.

    Loaded conditionally based on ACCOUNTABILITY_ENABLED. Uses Gemini API
    and the main Postgres database.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.settings = get_settings()
        self.user_id = int(self.settings.accountability_user_id)  # type: ignore[arg-type]
        self.guild_id = int(self.settings.accountability_guild_id)  # type: ignore[arg-type]
        self._channel: discord.TextChannel | None = None

    async def cog_load(self) -> None:
        """Start the check-in loop."""
        if not self.settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required for the accountability cog")

        self.checkin_loop.start()
        logger.info("Accountability cog loaded — loop started for user %s", self.user_id)

    async def cog_unload(self) -> None:
        """Cancel the loop."""
        self.checkin_loop.cancel()
        logger.info("Accountability cog unloaded")

    # ------------------------------------------------------------------
    # Channel management
    # ------------------------------------------------------------------

    async def _ensure_channel(self) -> discord.TextChannel | None:
        """Find or create the private accountability channel."""
        if self._channel is not None:
            return self._channel

        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            logger.error("Accountability guild %s not found", self.guild_id)
            return None

        # Look for existing channel by name
        for ch in guild.text_channels:
            if ch.name == CHANNEL_NAME:
                self._channel = ch
                logger.info("Found existing accountability channel: #%s", ch.name)
                return self._channel

        # Create it with permission overwrites
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
                topic="🔒 Private accountability zone — bot check-ins and task tracking",
                reason="Accountability cog: private channel for check-ins",
            )
            logger.info("Created private accountability channel: #%s", self._channel.name)
            return self._channel
        except discord.Forbidden:
            logger.error("Missing permissions to create channel in guild %s", self.guild_id)
            return None
        except Exception:
            logger.exception("Failed to create accountability channel")
            return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_accountability_msg(self, message: discord.Message) -> bool:
        """Check if a message is from the target user in the accountability channel."""
        return (
            self._channel is not None
            and message.channel.id == self._channel.id
            and message.author.id == self.user_id
            and not message.author.bot
        )

    async def _send(self, text: str) -> discord.Message | None:
        """Send a message to the accountability channel."""
        channel = await self._ensure_channel()
        if channel is None:
            return None
        try:
            return await channel.send(text)
        except discord.Forbidden:
            logger.error("Cannot send to accountability channel — missing permissions")
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
        """Core accountability loop — runs every 15 minutes."""
        try:
            if acc_service.is_quiet_hours(
                self.settings.quiet_hours_start,
                self.settings.quiet_hours_end,
            ):
                logger.debug("Quiet hours — skipping check-in")
                return

            channel = await self._ensure_channel()
            if channel is None:
                logger.warning("No accountability channel — skipping check-in")
                return

            async with get_session_factory()() as session:
                user_context = await acc_service.get_or_create_context(session)
                active_session = await acc_service.get_active_session(session)
                state = acc_service.determine_loop_state(active_session)

                task = None
                if active_session:
                    from sqlalchemy import select

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
                    queue = await acc_service.get_task_queue(session)
                    if queue:
                        top_task = queue[0]
                        score = acc_service.priority_risk_score(top_task)
                        msg = (
                            f"📋 **What's next?** — Top priority: **{top_task.title}** "
                            f"(risk score: {score:.1f})\n"
                            f"Reply with what you're working on, or `!start {top_task.title} 30`"
                        )
                    else:
                        msg = (
                            "📋 **No tasks in queue.** What are you working on?\n"
                            "Use `!start <task> <minutes>` to begin a session."
                        )

                sent = await self._ping(msg)
                if sent is None:
                    return

                await acc_service.log_activity(
                    session,
                    LogType.CHECK_IN,
                    ai_feedback=msg,
                )

                # Wait for a reply in the channel (14-minute window)
                def check(m: discord.Message) -> bool:
                    return self._is_accountability_msg(m) and not m.content.startswith("!")

                try:
                    reply = await self.bot.wait_for("message", check=check, timeout=840)
                except TimeoutError:
                    missed = await acc_service.increment_missed_checkins(session)
                    esc_tone = gemini_client.escalation_tone(missed)
                    nag = await gemini_client.generate_feedback(
                        intent="DISTRACTED",
                        context=f"User has ignored {missed} consecutive check-in(s).",
                        tone=esc_tone,
                        api_key=api_key,
                        model=model,
                    )
                    await self._ping(f"⚠️ **Missed check-in #{missed}**\n{nag}")
                    await acc_service.log_activity(
                        session,
                        LogType.ESCALATION,
                        ai_feedback=nag,
                    )
                    return

                # Got a reply — parse intent
                await acc_service.reset_missed_checkins(session)

                intent_result = await gemini_client.parse_user_intent(
                    reply.content,
                    session_context=self._session_context_dict(active_session, task),
                    user_context=self._user_context_dict(user_context),
                    api_key=api_key,
                    model=model,
                )

                # Handle parse error
                if intent_result.intent == "UNCLEAR" and not intent_result.summary:
                    await self._send(
                        "❓ I couldn't parse that. Could you rephrase? "
                        "What are you working on right now?"
                    )
                    await acc_service.log_activity(
                        session,
                        LogType.PARSE_ERROR,
                        user_update=reply.content,
                        ai_feedback=intent_result.raw_response,
                    )
                    return

                # Generate feedback based on intent
                context_str = f"Task: {task.title if task else 'none'}, User said: {reply.content}"
                feedback = await gemini_client.generate_feedback(
                    intent=intent_result.intent,
                    context=context_str,
                    tone=tone,
                    api_key=api_key,
                    model=model,
                )

                # Act on intent
                if intent_result.intent == "COMPLETED" and active_session:
                    completed_task = await acc_service.complete_session(session)
                    task_name = completed_task.title if completed_task else "your task"
                    await self._send(f"✅ **{task_name}** marked done.\n{feedback}")
                    await acc_service.log_activity(
                        session,
                        LogType.SESSION_END,
                        user_update=reply.content,
                        ai_feedback=feedback,
                    )

                elif intent_result.intent == "DISTRACTED":
                    await self._send(f"🔴 **Off track.**\n{feedback}")
                    await acc_service.log_activity(
                        session,
                        LogType.DISTRACTION,
                        user_update=reply.content,
                        ai_feedback=feedback,
                    )

                elif intent_result.intent == "START_SESSION":
                    title = intent_result.task_title or "unnamed task"
                    mins = intent_result.minutes or 30
                    await acc_service.start_session(session, title, mins)
                    await self._send(f"🚀 **Session started:** {title} ({mins} min)\n{feedback}")
                    await acc_service.log_activity(
                        session,
                        LogType.SESSION_START,
                        user_update=reply.content,
                        ai_feedback=feedback,
                    )

                else:
                    await self._send(feedback)
                    await acc_service.log_activity(
                        session,
                        LogType.CHECK_IN,
                        user_update=reply.content,
                        ai_feedback=feedback,
                    )

        except Exception as e:
            logger.exception("Error in accountability check-in loop: %s", e)

    @checkin_loop.before_loop
    async def before_checkin_loop(self) -> None:
        """Wait until the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------
    # Command router (message-based in the private channel)
    # ------------------------------------------------------------------

    @commands.Cog.listener("on_message")
    async def on_message(self, message: discord.Message) -> None:
        """Route !commands from the accountability channel."""
        if not self._is_accountability_msg(message):
            return

        if not message.content.startswith("!"):
            return

        parts = message.content.strip().split(maxsplit=2)
        command = parts[0].lower()

        try:
            if command == "!start":
                await self._cmd_start(message, parts)
            elif command == "!status":
                await self._cmd_status(message)
            elif command == "!pause":
                await self._cmd_pause(message)
            elif command == "!resume":
                await self._cmd_resume(message)
            elif command == "!done":
                await self._cmd_done(message)
            elif command == "!queue":
                await self._cmd_queue(message)
            elif command == "!skip":
                await self._cmd_skip(message, parts)
            else:
                await message.reply(
                    "Unknown command. Available: `!start`, `!status`, `!pause`, "
                    "`!resume`, `!done`, `!queue`, `!skip`"
                )
        except Exception as e:
            logger.exception("Error handling command %s: %s", command, e)
            await message.reply(f"⚠️ Error: {e}")

    # ------------------------------------------------------------------
    # Command implementations
    # ------------------------------------------------------------------

    async def _cmd_start(self, message: discord.Message, parts: list[str]) -> None:
        """Handle !start <task> <minutes>."""
        if len(parts) < 2:
            await message.reply("Usage: `!start <task name> <minutes>`\nExample: `!start auth module 45`")
            return

        remaining = message.content[len("!start"):].strip()
        tokens = remaining.rsplit(maxsplit=1)

        if len(tokens) == 2 and tokens[1].isdigit():
            task_title = tokens[0]
            minutes = int(tokens[1])
        else:
            task_title = remaining
            minutes = 30

        async with get_session_factory()() as session:
            await acc_service.start_session(session, task_title, minutes)
            await acc_service.log_activity(
                session,
                LogType.COMMAND,
                user_update=message.content,
                ai_feedback=f"Started session: {task_title} ({minutes} min)",
            )

        await message.reply(
            f"🚀 **Session started:** {task_title}\n"
            f"⏱️ Target: {minutes} minutes\n"
            f"I'll check in on you periodically."
        )

    async def _cmd_status(self, message: discord.Message) -> None:
        """Handle !status."""
        async with get_session_factory()() as session:
            active = await acc_service.get_active_session(session)
            ctx = await acc_service.get_or_create_context(session)

            if active:
                from sqlalchemy import select

                task = await session.scalar(select(AccTask).where(AccTask.id == active.task_id))
                task_name = task.title if task else "unknown"

                remaining = "N/A"
                if active.target_end_time:
                    delta = (active.target_end_time.replace(tzinfo=None) - datetime.now()).total_seconds() / 60
                    remaining = f"{max(0, int(delta))} min"

                elapsed = int((datetime.now() - active.start_time.replace(tzinfo=None)).total_seconds() / 60)

                await message.reply(
                    f"📊 **Active Session**\n"
                    f"• Task: **{task_name}**\n"
                    f"• Elapsed: {elapsed} min\n"
                    f"• Remaining: {remaining}\n"
                    f"• Missed check-ins: {ctx.missed_checkins}"
                )
            else:
                await message.reply(
                    f"📊 **No active session**\n"
                    f"• Missed check-ins: {ctx.missed_checkins}\n"
                    f"Use `!start <task> <minutes>` to begin."
                )

    async def _cmd_pause(self, message: discord.Message) -> None:
        """Handle !pause."""
        async with get_session_factory()() as session:
            paused = await acc_service.pause_session(session)
            if paused:
                await acc_service.log_activity(
                    session, LogType.COMMAND, user_update="!pause"
                )
                await message.reply("⏸️ Session paused.")
            else:
                await message.reply("No active session to pause.")

    async def _cmd_resume(self, message: discord.Message) -> None:
        """Handle !resume."""
        async with get_session_factory()() as session:
            resumed = await acc_service.resume_session(session)
            if resumed:
                await acc_service.log_activity(
                    session, LogType.COMMAND, user_update="!resume"
                )
                await message.reply("▶️ Session resumed.")
            else:
                await message.reply("No paused session to resume.")

    async def _cmd_done(self, message: discord.Message) -> None:
        """Handle !done."""
        async with get_session_factory()() as session:
            completed_task = await acc_service.complete_session(session)
            if completed_task:
                await acc_service.log_activity(
                    session,
                    LogType.SESSION_END,
                    user_update="!done",
                    ai_feedback=f"Completed: {completed_task.title}",
                )
                await message.reply(f"✅ **{completed_task.title}** marked done. Nice work.")
            else:
                await message.reply("No active session to complete.")

    async def _cmd_queue(self, message: discord.Message) -> None:
        """Handle !queue."""
        async with get_session_factory()() as session:
            queue = await acc_service.get_task_queue(session)

            if not queue:
                await message.reply("📋 **Queue is empty.** Use `!start <task> <minutes>` to add work.")
                return

            lines = ["📋 **Task Queue** (by priority risk):"]
            for i, task in enumerate(queue[:10], 1):
                score = acc_service.priority_risk_score(task)
                status_emoji = "🔵" if task.status == "pending" else "🟡"
                lines.append(
                    f"{i}. {status_emoji} **{task.title}** "
                    f"[{task.priority}] — risk: {score:.1f}"
                )

            await message.reply("\n".join(lines))

    async def _cmd_skip(self, message: discord.Message, parts: list[str]) -> None:
        """Handle !skip [task_id]."""
        async with get_session_factory()() as session:
            if len(parts) >= 2 and parts[1].isdigit():
                task_id = int(parts[1])
                skipped = await acc_service.skip_task(session, task_id)
                if skipped:
                    await acc_service.log_activity(
                        session, LogType.COMMAND, user_update=f"!skip {task_id}"
                    )
                    await message.reply(f"⏭️ Task #{task_id} skipped.")
                else:
                    await message.reply(f"Task #{task_id} not found.")
            else:
                queue = await acc_service.get_task_queue(session)
                if queue:
                    top = queue[0]
                    await acc_service.skip_task(session, top.id)
                    await acc_service.log_activity(
                        session, LogType.COMMAND, user_update=f"!skip (top: {top.title})"
                    )
                    await message.reply(f"⏭️ Skipped **{top.title}**.")
                else:
                    await message.reply("Queue is empty, nothing to skip.")


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(Accountability(bot))
