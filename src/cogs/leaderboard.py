"""Leaderboard cog — scoring config, leaderboard display, and finalization commands."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from src.services import audit as audit_service
from src.services import guild_settings as gs_service
from src.services import leaderboard as leaderboard_service
from src.services.scoring import get_effective_config, parse_rank_bonus_tiers

logger = logging.getLogger("arena.cogs.leaderboard")


class Leaderboard(commands.Cog):
    """Cog for event leaderboard management and scoring configuration."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /event-set-scoring ───────────────────────────────────────────

    @app_commands.command(
        name="event-set-scoring", description="Configure scoring for an event"
    )
    @app_commands.describe(
        event_id="Event ID",
        participation_points="Points for participating (default: 100)",
        per_question_points="Points per question solved (default: 100)",
        rating_gain_multiplier="Multiplier for positive rating gain (default: 2)",
        rank_bonus_enabled="Enable rank-based bonus points",
        rank_bonus_tiers="Rank bonus tiers as 'max_rank:bonus,...' (e.g. '10:200,50:100')",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def event_set_scoring(
        self,
        interaction: discord.Interaction,
        event_id: int,
        participation_points: int | None = None,
        per_question_points: int | None = None,
        rating_gain_multiplier: int | None = None,
        rank_bonus_enabled: bool | None = None,
        rank_bonus_tiers: str | None = None,
    ) -> None:
        """Set scoring parameters for an event."""
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)
        try:
            overrides: dict = {}
            if participation_points is not None:
                overrides["participation_points"] = participation_points
            if per_question_points is not None:
                overrides["per_question_points"] = per_question_points
            if rating_gain_multiplier is not None:
                overrides["rating_gain_multiplier"] = rating_gain_multiplier
            if rank_bonus_enabled is not None:
                overrides["rank_bonus_enabled"] = rank_bonus_enabled
            if rank_bonus_tiers is not None:
                overrides["rank_bonus_tiers"] = parse_rank_bonus_tiers(rank_bonus_tiers)

            guild_id = str(interaction.guild.id)
            event = await leaderboard_service.set_scoring_config(event_id, guild_id, overrides)

            settings = await gs_service.get_or_create(guild_id)
            await audit_service.log_action(
                settings.id,
                "event_set_scoring",
                str(interaction.user.id),
                target_type="event",
                target_id=event_id,
                details=str(overrides),
            )

            # Show effective config
            effective = get_effective_config(event.points_config)

            embed = discord.Embed(
                title=f"✅ Scoring Configured for Event {event_id}",
                color=discord.Color.green(),
            )
            embed.add_field(
                name="Participation Points",
                value=str(effective["participation_points"]),
                inline=True,
            )
            embed.add_field(
                name="Per Question Points",
                value=str(effective["per_question_points"]),
                inline=True,
            )
            embed.add_field(
                name="Rating Gain Multiplier",
                value=f"×{effective['rating_gain_multiplier']}",
                inline=True,
            )
            embed.add_field(
                name="Rank Bonus",
                value="Enabled" if effective["rank_bonus_enabled"] else "Disabled",
                inline=True,
            )
            if effective["rank_bonus_tiers"]:
                tiers_str = ", ".join(
                    f"Top {t['max_rank']}: +{t['bonus']} pts"
                    for t in effective["rank_bonus_tiers"]
                )
                embed.add_field(name="Rank Bonus Tiers", value=tiers_str, inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)
        except Exception:
            logger.exception("Error in event-set-scoring")
            await interaction.followup.send("❌ An unexpected error occurred.", ephemeral=True)

    # ── /event-leaderboard ───────────────────────────────────────────

    @app_commands.command(
        name="event-leaderboard", description="View the leaderboard for an event"
    )
    @app_commands.describe(event_id="Event ID")
    @app_commands.guild_only()
    async def event_leaderboard(
        self, interaction: discord.Interaction, event_id: int
    ) -> None:
        """Display the top 10 standings for an event."""
        await interaction.response.defer()
        try:
            await leaderboard_service.compute_leaderboard(event_id)
            entries = await leaderboard_service.get_leaderboard(event_id, limit=10)

            if not entries:
                await interaction.followup.send(
                    "📭 No verified submissions found for this event."
                )
                return

            embed = _build_leaderboard_embed(entries, event_id)
            await interaction.followup.send(embed=embed)
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}")
        except Exception:
            logger.exception("Error in event-leaderboard")
            await interaction.followup.send("❌ An unexpected error occurred.")

    # ── /event-leaderboard-post ──────────────────────────────────────

    @app_commands.command(
        name="event-leaderboard-post",
        description="Post leaderboard results to a channel",
    )
    @app_commands.describe(
        event_id="Event ID",
        channel="Channel to post results to",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def event_leaderboard_post(
        self,
        interaction: discord.Interaction,
        event_id: int,
        channel: discord.TextChannel,
    ) -> None:
        """Post the full leaderboard to a channel."""
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)
        try:
            await leaderboard_service.compute_leaderboard(event_id)
            entries = await leaderboard_service.get_leaderboard(event_id, limit=50)

            if not entries:
                await interaction.followup.send(
                    "❌ No verified submissions found for this event.", ephemeral=True
                )
                return

            embed = _build_leaderboard_embed(entries, event_id)
            await channel.send(embed=embed)

            settings = await gs_service.get_or_create(str(interaction.guild.id))
            await audit_service.log_action(
                settings.id,
                "event_leaderboard_post",
                str(interaction.user.id),
                target_type="event",
                target_id=event_id,
                details=f"Posted to #{channel.name} ({channel.id})",
            )

            await interaction.followup.send(
                f"✅ Leaderboard posted to {channel.mention}", ephemeral=True
            )
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)
        except Exception:
            logger.exception("Error in event-leaderboard-post")
            await interaction.followup.send("❌ An unexpected error occurred.", ephemeral=True)

    # ── /event-finalize ──────────────────────────────────────────────

    @app_commands.command(
        name="event-finalize",
        description="Finalize event results and lock the leaderboard",
    )
    @app_commands.describe(
        event_id="Event ID",
        confirm="Confirm finalization even if submissions are still open",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def event_finalize(
        self,
        interaction: discord.Interaction,
        event_id: int,
        confirm: bool = False,
    ) -> None:
        """Finalize results, compute final standings, and lock the leaderboard."""
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)
        try:
            entries = await leaderboard_service.finalize_leaderboard(
                event_id, force=confirm
            )

            settings = await gs_service.get_or_create(str(interaction.guild.id))
            await audit_service.log_action(
                settings.id,
                "event_finalize",
                str(interaction.user.id),
                target_type="event",
                target_id=event_id,
                details=f"Finalized with {len(entries)} entries, force={confirm}",
            )
            await interaction.followup.send(
                f"✅ Event {event_id} finalized. {len(entries)} entries locked.",
                ephemeral=True,
            )
        except ValueError as e:
            if "open" in str(e).lower() and not confirm:
                await interaction.followup.send(
                    f"❌ {e} Use `confirm=True` to bypass.", ephemeral=True
                )
            else:
                await interaction.followup.send(f"❌ {e}", ephemeral=True)
        except Exception:
            logger.exception("Error in event-finalize")
            await interaction.followup.send("❌ An unexpected error occurred.", ephemeral=True)


# ── Helpers ──────────────────────────────────────────────────────────

_MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def _build_leaderboard_embed(
    entries: list, event_id: int
) -> discord.Embed:
    """Build a leaderboard embed from a list of EventLeaderboardEntry rows."""
    embed = discord.Embed(
        title=f"🏆 Event {event_id} — Leaderboard",
        color=discord.Color.gold(),
    )

    is_final = False
    lines: list[str] = []

    for entry in entries:
        medal = _MEDALS.get(entry.rank, f"**#{entry.rank}**")
        discord_id = entry.guild_member.user.discord_user_id
        line = f"{medal} <@{discord_id}> — **{entry.total_points}** pts"

        if entry.score_breakdown:
            bd = entry.score_breakdown
            parts = []
            if bd.get("questions"):
                parts.append(f"Q: {bd['questions']}")
            if bd.get("rating_gain"):
                parts.append(f"Rating: +{bd['rating_gain']}")
            if bd.get("rank_bonus"):
                parts.append(f"Rank: +{bd['rank_bonus']}")
            if parts:
                line += f"\n  ╰ {' | '.join(parts)}"

        lines.append(line)

        if entry.is_final:
            is_final = True

    embed.description = "\n".join(lines)

    if is_final:
        embed.set_footer(text="✅ Results finalized")

    return embed


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(Leaderboard(bot))
