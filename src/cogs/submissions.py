import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

from src.services import audit as audit_service
from src.services import events as event_service
from src.services import guild_settings as gs_service
from src.services import leaderboard as leaderboard_service
from src.services import submissions as submissions_service

logger = logging.getLogger("arena.cogs.submissions")


class SubmitResultsModal(discord.ui.Modal, title="Submit Your Results"):
    questions_solved = discord.ui.TextInput(
        label="Questions Solved",
        style=discord.TextStyle.short,
        placeholder="e.g., 3",
        required=True,
    )
    claimed_rank = discord.ui.TextInput(
        label="Your Rank (optional)",
        style=discord.TextStyle.short,
        placeholder="e.g., 150",
        required=False,
    )
    rating_input = discord.ui.TextInput(
        label="Rating Before / After (optional)",
        style=discord.TextStyle.short,
        placeholder="e.g., 1200 / 1350",
        required=False,
    )
    evidence_url = discord.ui.TextInput(
        label="Evidence URL (optional)",
        style=discord.TextStyle.short,
        placeholder="https://...",
        required=False,
    )
    reflection = discord.ui.TextInput(
        label="Short Reflection (optional)",
        style=discord.TextStyle.paragraph,
        placeholder="How did it go?",
        required=False,
    )

    def __init__(self, event_id: int):
        super().__init__()
        self.event_id = event_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            questions_solved_val = int(self.questions_solved.value.strip())
            if questions_solved_val < 0:
                raise ValueError("Questions solved must be >= 0")

            claimed_rank_val = None
            if self.claimed_rank.value.strip():
                claimed_rank_val = int(self.claimed_rank.value.strip())
                if claimed_rank_val <= 0:
                    raise ValueError("Rank must be positive")

            rating_before = None
            rating_after = None
            if self.rating_input.value.strip():
                parts = self.rating_input.value.split("/")
                if len(parts) != 2:
                    raise ValueError("Rating must be in format Before / After")
                rating_before = int(parts[0].strip())
                rating_after = int(parts[1].strip())

            evidence_url_val = None
            if self.evidence_url.value.strip():
                evidence_url_val = self.evidence_url.value.strip()
                if not evidence_url_val.startswith(("http://", "https://")):
                    raise ValueError("Evidence URL must start with http:// or https://")

            reflection_val = (
                self.reflection.value.strip() if self.reflection.value.strip() else None
            )

            guild_id = str(interaction.guild.id)
            user_id = str(interaction.user.id)

            # Get event to check approval setting
            event = await event_service.get_event(self.event_id, guild_id)
            if not event:
                await interaction.followup.send("❌ Event not found.", ephemeral=True)
                return

            await submissions_service.create_or_update_submission(
                event_id=self.event_id,
                guild_id=guild_id,
                user_id=user_id,
                questions_solved=questions_solved_val,
                claimed_rank=claimed_rank_val,
                claimed_rating_before=rating_before,
                claimed_rating_after=rating_after,
                evidence_url=evidence_url_val,
                reflection=reflection_val,
            )

            if event.results_require_moderator_approval:
                await interaction.followup.send(
                    "✅ Results submitted (self-reported, pending moderator review)",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "✅ Results submitted and verified!", ephemeral=True
                )

        except ValueError as e:
            await interaction.followup.send(f"❌ Invalid input: {e}", ephemeral=True)
        except Exception:
            logger.exception("Error submitting results")
            await interaction.followup.send(
                "❌ An unexpected error occurred.", ephemeral=True
            )


class DynamicSubmitButton(
    discord.ui.DynamicItem[discord.ui.Button], template=r"submit_results:(?P<event_id>\d+)"
):
    def __init__(self, event_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label="📝 Submit Results",
                style=discord.ButtonStyle.success,
                custom_id=f"submit_results:{event_id}",
            )
        )
        self.event_id = event_id

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction, item: discord.ui.Item, match: re.Match[str], /
    ) -> "DynamicSubmitButton":
        event_id = int(match.group("event_id"))
        return cls(event_id)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(SubmitResultsModal(self.event_id))


class SubmitResultsView(discord.ui.View):
    def __init__(self, event_id: int):
        super().__init__(timeout=None)
        button = discord.ui.Button(
            label="📝 Submit Results",
            style=discord.ButtonStyle.success,
            custom_id=f"submit_results:{event_id}",
        )
        self.add_item(button)


class Submissions(commands.Cog):
    """Cog for managing and reviewing contest submissions."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Register dynamic items on load."""
        self.bot.add_dynamic_items(DynamicSubmitButton)

    async def cog_unload(self) -> None:
        """Unregister dynamic items on unload."""
        self.bot.remove_dynamic_items(DynamicSubmitButton)

    @app_commands.command(name="submission-list", description="List submissions for an event")
    @app_commands.describe(
        event_id="Event ID",
        status="Filter by status (pending/verified/rejected)",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def submission_list(
        self, interaction: discord.Interaction, event_id: int, status: str | None = None
    ) -> None:
        """List event submissions."""
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        guild_id = str(interaction.guild.id)

        try:
            submissions = await submissions_service.list_submissions(
                event_id, guild_id, status=status
            )

            if not submissions:
                await interaction.followup.send("📭 No submissions found.", ephemeral=True)
                return

            embed = discord.Embed(
                title=f"📋 Submissions for Event {event_id}",
                color=discord.Color.blue(),
            )

            for s in submissions:
                member_mention = f"<@{s.guild_member.user.discord_user_id}>"
                status_emoji = {
                    "pending": "⏳",
                    "verified": "✅",
                    "rejected": "❌",
                }.get(s.verification_status, "❓")

                details = [
                    f"Questions Solved: {s.questions_solved} (self-reported)",
                    f"Status: {status_emoji} {s.verification_status}",
                ]
                if s.claimed_rank is not None:
                    details.append(f"Rank: {s.claimed_rank} (self-reported)")
                if s.claimed_rating_before is not None and s.claimed_rating_after is not None:
                    details.append(
                        f"Rating: {s.claimed_rating_before} → {s.claimed_rating_after} "
                        f"(self-reported)"
                    )
                details.append(f"Submission ID: {s.id}")

                embed.add_field(
                    name=f"Submission by {member_mention}",
                    value="\n".join(details),
                    inline=False,
                )

            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception:
            logger.exception("Error listing submissions")
            await interaction.followup.send("❌ An error occurred.", ephemeral=True)

    @app_commands.command(name="submission-approve", description="Approve a submission")
    @app_commands.describe(submission_id="Submission ID", note="Optional moderator note")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def submission_approve(
        self, interaction: discord.Interaction, submission_id: int, note: str | None = None
    ) -> None:
        """Approve a submission."""
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)
        try:
            settings = await gs_service.get_or_create(str(interaction.guild.id))
            verified_by = str(interaction.user.id)
            await submissions_service.approve_submission(submission_id, verified_by, note=note)
            await audit_service.log_action(
                settings.id,
                "approve_submission",
                verified_by,
                target_type="submission",
                target_id=submission_id,
            )

            # Auto-recompute leaderboard after approval
            try:
                sub = await submissions_service.get_submission(submission_id)
                if sub:
                    await leaderboard_service.compute_leaderboard(sub.event_id)
            except Exception:
                logger.warning("Leaderboard recompute after approve failed", exc_info=True)

            await interaction.followup.send(
                f"✅ Submission `{submission_id}` approved.", ephemeral=True
            )
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)
        except Exception:
            logger.exception("Error approving submission")
            await interaction.followup.send("❌ An error occurred.", ephemeral=True)

    @app_commands.command(name="submission-reject", description="Reject a submission")
    @app_commands.describe(
        submission_id="Submission ID",
        reason="Reason for rejection (required)",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def submission_reject(
        self, interaction: discord.Interaction, submission_id: int, reason: str
    ) -> None:
        """Reject a submission."""
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)
        try:
            settings = await gs_service.get_or_create(str(interaction.guild.id))
            verified_by = str(interaction.user.id)
            await submissions_service.reject_submission(submission_id, verified_by, reason)
            await audit_service.log_action(
                settings.id,
                "reject_submission",
                verified_by,
                target_type="submission",
                target_id=submission_id,
            )

            # Auto-recompute leaderboard after rejection
            try:
                sub = await submissions_service.get_submission(submission_id)
                if sub:
                    await leaderboard_service.compute_leaderboard(sub.event_id)
            except Exception:
                logger.warning("Leaderboard recompute after reject failed", exc_info=True)

            await interaction.followup.send(
                f"✅ Submission `{submission_id}` rejected.", ephemeral=True
            )
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)
        except Exception:
            logger.exception("Error rejecting submission")
            await interaction.followup.send("❌ An error occurred.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(Submissions(bot))
