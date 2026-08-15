"""Cog for managing The Citadel role mappings and synchronization."""

import logging
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from src.db.engine import get_session_factory
from src.db.models import GuildMember, GuildSettings, RoleMapping
from src.services.roles import get_guild_role_mappings, sync_member_roles

logger = logging.getLogger("arena.cogs.roles")


class Roles(commands.Cog):
    """Admin commands for mapping and syncing server roles."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    role_group = app_commands.Group(name="role-map", description="Manage The Citadel role mappings")

    @role_group.command(name="view", description="View current role mappings.")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def view_roles(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        
        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = select(GuildSettings).where(GuildSettings.discord_guild_id == str(interaction.guild.id))
            settings = await session.scalar(stmt)
            if not settings:
                await interaction.followup.send("❌ Server not configured.")
                return
                
            mappings = await get_guild_role_mappings(session, settings.id)
            
            if not mappings:
                await interaction.followup.send("No role mappings configured.")
                return
                
            embed = discord.Embed(title="The Citadel Role Mappings", color=discord.Color.blue())
            
            for category, category_mappings in mappings.items():
                lines = []
                for m in sorted(category_mappings, key=lambda x: x.min_value or 0):
                    lines.append(f"Min Value: {m.min_value} -> <@&{m.role_id}>")
                embed.add_field(name=category.replace("_", " ").title(), value="\n".join(lines), inline=False)
                
            await interaction.followup.send(embed=embed)

    @role_group.command(name="set", description="Set a role mapping.")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def set_role(
        self, 
        interaction: discord.Interaction, 
        category: Literal["cp_rating", "dsa_rating", "achievement", "champion"],
        role: discord.Role,
        min_value: int | None = None
    ) -> None:
        await interaction.response.defer()
        
        # Verify role is manageable by bot
        if role >= interaction.guild.me.top_role:
            await interaction.followup.send("❌ Cannot manage this role. My role must be higher in the server settings.")
            return
            
        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = select(GuildSettings).where(GuildSettings.discord_guild_id == str(interaction.guild.id))
            settings = await session.scalar(stmt)
            if not settings:
                await interaction.followup.send("❌ Server not configured.")
                return
                
            # Upsert
            stmt = select(RoleMapping).where(
                RoleMapping.guild_settings_id == settings.id,
                RoleMapping.category == category,
                RoleMapping.min_value == min_value
            )
            mapping = await session.scalar(stmt)
            
            if mapping:
                mapping.role_id = str(role.id)
                mapping.role_name_cache = role.name
            else:
                mapping = RoleMapping(
                    guild_settings_id=settings.id,
                    category=category,
                    min_value=min_value,
                    role_id=str(role.id),
                    role_name_cache=role.name
                )
                session.add(mapping)
                
            await session.commit()
            await interaction.followup.send(f"✅ Set `{category}` (min_value={min_value}) to {role.mention}")

    @role_group.command(name="remove", description="Remove a role mapping.")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def remove_role(
        self, 
        interaction: discord.Interaction, 
        category: Literal["cp_rating", "dsa_rating", "achievement", "champion"],
        min_value: int | None = None
    ) -> None:
        await interaction.response.defer()
        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = select(GuildSettings).where(GuildSettings.discord_guild_id == str(interaction.guild.id))
            settings = await session.scalar(stmt)
            if not settings:
                await interaction.followup.send("❌ Server not configured.")
                return
                
            del_stmt = delete(RoleMapping).where(
                RoleMapping.guild_settings_id == settings.id,
                RoleMapping.category == category,
                RoleMapping.min_value == min_value
            )
            await session.execute(del_stmt)
            await session.commit()
            await interaction.followup.send(f"✅ Removed mapping for `{category}` (min_value={min_value})")

    @app_commands.command(name="sync-roles", description="Force sync all member roles.")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def sync_all_roles(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        
        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = select(GuildSettings).where(GuildSettings.discord_guild_id == str(interaction.guild.id))
            settings = await session.scalar(stmt)
            if not settings:
                await interaction.followup.send("❌ Server not configured.")
                return
                
            mappings = await get_guild_role_mappings(session, settings.id)
            if not mappings:
                await interaction.followup.send("❌ No role mappings configured. Set them up first.")
                return
                
            stmt = select(GuildMember).where(GuildMember.guild_settings_id == settings.id).options(selectinload(GuildMember.user))
            members = (await session.scalars(stmt)).all()
            
            count = 0
            for gm in members:
                discord_member = interaction.guild.get_member(int(gm.user.discord_user_id))
                if discord_member:
                    await sync_member_roles(session, discord_member, gm, mappings)
                    count += 1
                    
            await interaction.followup.send(f"✅ Synced roles for {count} members.")

    @role_group.command(name="auto-setup", description="Auto-create and map 1-5 star roles for CP and DSA.")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def auto_setup_roles(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        
        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = select(GuildSettings).where(GuildSettings.discord_guild_id == str(interaction.guild.id))
            settings = await session.scalar(stmt)
            if not settings:
                await interaction.followup.send("❌ Server not configured.")
                return

            colors = {
                1: discord.Color.light_gray(),
                2: discord.Color.green(),
                3: discord.Color.blue(),
                4: discord.Color.purple(),
                5: discord.Color.gold()
            }
            
            categories = {
                "cp_rating": "Competitive Programming",
                "dsa_rating": "dsa"
            }
            
            created_count = 0
            
            for category, suffix in categories.items():
                for stars in range(1, 6):
                    role_name = f"{'⭐' * stars} {suffix}"
                    color = colors[stars]
                    
                    # Check if mapping already exists
                    stmt_map = select(RoleMapping).where(
                        RoleMapping.guild_settings_id == settings.id,
                        RoleMapping.category == category,
                        RoleMapping.min_value == stars
                    )
                    mapping = await session.scalar(stmt_map)
                    
                    # Search if role with this name already exists to avoid dupes
                    existing_role = discord.utils.get(interaction.guild.roles, name=role_name)
                    
                    if not existing_role:
                        try:
                            existing_role = await interaction.guild.create_role(
                                name=role_name,
                                color=color,
                                hoist=True,
                                reason="The Citadel auto-setup"
                            )
                            created_count += 1
                        except discord.Forbidden:
                            await interaction.followup.send("❌ Missing permissions to create roles. Make sure I have 'Manage Roles'.")
                            return
                        except discord.HTTPException as e:
                            await interaction.followup.send(f"❌ Error creating role: {e}")
                            return
                    
                    # Update mapping
                    if mapping:
                        mapping.role_id = str(existing_role.id)
                        mapping.role_name_cache = existing_role.name
                    else:
                        mapping = RoleMapping(
                            guild_settings_id=settings.id,
                            category=category,
                            min_value=stars,
                            role_id=str(existing_role.id),
                            role_name_cache=existing_role.name
                        )
                        session.add(mapping)
            
            await session.commit()
            
            # Optionally trigger a sync for existing members
            mappings = await get_guild_role_mappings(session, settings.id)
            stmt_members = select(GuildMember).where(GuildMember.guild_settings_id == settings.id).options(selectinload(GuildMember.user))
            members = (await session.scalars(stmt_members)).all()
            
            synced_count = 0
            for gm in members:
                if interaction.guild:
                    discord_member = interaction.guild.get_member(int(gm.user.discord_user_id))
                    if discord_member:
                        await sync_member_roles(session, discord_member, gm, mappings)
                        synced_count += 1
                    
            await interaction.followup.send(f"✅ Auto-setup complete! Created {created_count} new roles and synced {synced_count} members.")


async def setup(bot: commands.Bot) -> None:
    from src.db.models import User # local import to avoid circular dependency issues at top level
    await bot.add_cog(Roles(bot))
