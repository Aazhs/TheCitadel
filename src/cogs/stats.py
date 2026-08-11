"""Cog for viewing server-wide leaderboards and personal statistics."""

import logging
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.db.engine import get_session_factory
from src.db.models import GuildMember, GuildSettings

logger = logging.getLogger("arena.cogs.stats")


class Stats(commands.Cog):
    """View leaderboards and personal statistics."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="leaderboard",
        description="View the server-wide leaderboard.",
    )
    @app_commands.describe(
        scope="The time period for the leaderboard",
        metric="The metric to rank members by",
    )
    @app_commands.guild_only()
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        scope: Literal["all-time", "current-cycle"] = "current-cycle",
        metric: Literal["arena-points", "problems-solved", "participation"] = "arena-points",
    ) -> None:
        """View the server-wide leaderboard."""
        await interaction.response.defer()
        
        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = select(GuildSettings).where(GuildSettings.discord_guild_id == str(interaction.guild.id))
            settings = await session.scalar(stmt)
            if not settings:
                await interaction.followup.send("❌ Server not configured.")
                return

            member_stmt = (
                select(GuildMember)
                .where(GuildMember.guild_settings_id == settings.id)
                .options(selectinload(GuildMember.user))
            )
            
            # Determine ordering
            if metric == "arena-points":
                if scope == "all-time":
                    member_stmt = member_stmt.order_by(GuildMember.arena_points_all_time.desc())
                else:
                    member_stmt = member_stmt.order_by(GuildMember.arena_points_current_cycle.desc())
            elif metric == "problems-solved":
                member_stmt = member_stmt.order_by(GuildMember.problems_solved_total.desc())
            elif metric == "participation":
                member_stmt = member_stmt.order_by(GuildMember.events_participated.desc())
                
            member_stmt = member_stmt.limit(10)
            
            members = (await session.scalars(member_stmt)).all()
            
            if not members:
                await interaction.followup.send("No statistics found for this server yet.")
                return
                
            embed = discord.Embed(
                title=f"🏆 Leaderboard: {metric.replace('-', ' ').title()} ({scope.replace('-', ' ').title()})",
                color=discord.Color.gold(),
            )
            
            description = []
            for i, member in enumerate(members, start=1):
                discord_user = interaction.guild.get_member(int(member.user.discord_user_id))
                name = discord_user.display_name if discord_user else f"<@{member.user.discord_user_id}>"
                
                if metric == "arena-points":
                    val = member.arena_points_all_time if scope == "all-time" else member.arena_points_current_cycle
                elif metric == "problems-solved":
                    val = member.problems_solved_total
                else:
                    val = member.events_participated
                    
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"#{i}"
                description.append(f"{medal} **{name}**: {val}")
                
            embed.description = "\n".join(description)
            await interaction.followup.send(embed=embed)


    @app_commands.command(
        name="my-stats",
        description="View your personal Algorithm Arena statistics.",
    )
    @app_commands.guild_only()
    async def my_stats(self, interaction: discord.Interaction) -> None:
        """View personal statistics."""
        await interaction.response.defer()
        
        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = select(GuildSettings).where(GuildSettings.discord_guild_id == str(interaction.guild.id))
            settings = await session.scalar(stmt)
            if not settings:
                await interaction.followup.send("❌ Server not configured.")
                return
                
            stmt = (
                select(GuildMember)
                .join(GuildMember.user)
                .where(
                    GuildMember.guild_settings_id == settings.id,
                    User.discord_user_id == str(interaction.user.id)
                )
                .options(selectinload(GuildMember.linked_accounts))
            )
            member = (await session.execute(stmt)).scalar_one_or_none()
            
            if not member:
                await interaction.followup.send("You have no statistics yet. Participate in an event or link an account!")
                return
                
            embed = discord.Embed(
                title=f"📊 Statistics for {interaction.user.display_name}",
                color=discord.Color.blue(),
            )
            
            embed.add_field(name="CP Star Rating", value=f"{'⭐' * member.cp_star_rating if member.cp_star_rating else 'Unrated'}", inline=True)
            embed.add_field(name="DSA Star Rating", value=f"{'⭐' * member.dsa_star_rating if member.dsa_star_rating else 'Unrated'}", inline=True)
            embed.add_field(name="Events Participated", value=str(member.events_participated), inline=True)
            
            embed.add_field(name="Arena Points (All-Time)", value=str(member.arena_points_all_time), inline=True)
            embed.add_field(name="Arena Points (Cycle)", value=str(member.arena_points_current_cycle), inline=True)
            embed.add_field(name="Problems Solved", value=str(member.problems_solved_total), inline=True)
            
            embed.add_field(name="Current Streak", value=f"{member.current_streak} events", inline=True)
            embed.add_field(name="Longest Streak", value=f"{member.longest_streak} events", inline=True)
            
            await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    from src.db.models import User # local import to avoid circular dependency issues at top level
    await bot.add_cog(Stats(bot))
