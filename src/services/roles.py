"""Role synchronization engine for Algorithm Arena."""

import logging
from collections import defaultdict
from typing import Sequence

import discord
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import GuildMember, RoleMapping
from src.services.stats import get_current_cycle_start

logger = logging.getLogger("arena.services.roles")


async def get_guild_role_mappings(session: AsyncSession, guild_settings_id: int) -> dict[str, list[RoleMapping]]:
    """Fetch and organize role mappings for a guild."""
    stmt = select(RoleMapping).where(RoleMapping.guild_settings_id == guild_settings_id)
    mappings = (await session.scalars(stmt)).all()
    
    result = defaultdict(list)
    for mapping in mappings:
        result[mapping.category].append(mapping)
        
    return dict(result)


async def sync_member_roles(
    session: AsyncSession,
    discord_member: discord.Member,
    guild_member: GuildMember,
    mappings: dict[str, list[RoleMapping]]
) -> None:
    """Sync Discord roles for a single member based on their arena stats and ratings.
    
    This engine ONLY adds/removes roles that are explicitly configured in RoleMapping.
    It will never touch unrelated server roles.
    """
    if not discord_member or not discord_member.guild:
        return

    guild = discord_member.guild
    
    # 1. Determine which mapped roles the user SHOULD have
    target_role_ids: set[str] = set()
    all_managed_role_ids: set[str] = set()
    
    for category, category_mappings in mappings.items():
        # Keep track of all managed roles so we know what we're allowed to remove
        for m in category_mappings:
            all_managed_role_ids.add(m.role_id)
            
        if category == "cp_rating":
            # For ratings, user gets exactly ONE role matching their current star tier
            # We sort descending so we can just find the highest one they qualify for
            sorted_mappings = sorted(category_mappings, key=lambda x: x.min_value or 0, reverse=True)
            for m in sorted_mappings:
                if guild_member.cp_star_rating >= (m.min_value or 0):
                    target_role_ids.add(m.role_id)
                    break # Only one rating role per category

        elif category == "dsa_rating":
            sorted_mappings = sorted(category_mappings, key=lambda x: x.min_value or 0, reverse=True)
            for m in sorted_mappings:
                if guild_member.dsa_star_rating >= (m.min_value or 0):
                    target_role_ids.add(m.role_id)
                    break

        elif category == "achievement":
            # Achievements are cumulative. User gets all they qualify for.
            for m in category_mappings:
                if m.min_value is None:
                    continue
                # Hardcoded logic for specific achievements based on min_value conventions:
                # We can convention that min_value = threshold for 'events_participated'
                # For "Verified Competitor", maybe min_value = 1 for linked accounts
                if m.role_name_cache and "Verified" in m.role_name_cache and guild_member.verified_competitor:
                    target_role_ids.add(m.role_id)
                elif m.role_name_cache and "Regular" in m.role_name_cache and guild_member.events_participated >= m.min_value:
                    target_role_ids.add(m.role_id)
                    
        elif category == "champion":
            # Champion roles are handled specially (e.g. at the end of a cycle)
            pass

    # 2. Compare with current roles
    current_role_ids = {str(role.id) for role in discord_member.roles}
    
    roles_to_add_ids = target_role_ids - current_role_ids
    # Only remove roles that we manage AND the user shouldn't have anymore
    roles_to_remove_ids = (current_role_ids & all_managed_role_ids) - target_role_ids
    
    roles_to_add = []
    for r_id in roles_to_add_ids:
        role = guild.get_role(int(r_id))
        if role:
            roles_to_add.append(role)
            
    roles_to_remove = []
    for r_id in roles_to_remove_ids:
        role = guild.get_role(int(r_id))
        if role:
            roles_to_remove.append(role)
            
    # 3. Apply changes via Discord API
    if roles_to_add:
        try:
            await discord_member.add_roles(*roles_to_add, reason="Algorithm Arena: Earned new roles")
            logger.info(f"Added roles {[r.name for r in roles_to_add]} to {discord_member.display_name}")
        except discord.Forbidden:
            logger.warning(f"Forbidden to add roles to {discord_member.display_name}. Hierarchy issue?")
        except discord.HTTPException as e:
            logger.error(f"HTTP Exception adding roles to {discord_member.display_name}: {e}")

    if roles_to_remove:
        try:
            await discord_member.remove_roles(*roles_to_remove, reason="Algorithm Arena: No longer qualifies for roles")
            logger.info(f"Removed roles {[r.name for r in roles_to_remove]} from {discord_member.display_name}")
        except discord.Forbidden:
            logger.warning(f"Forbidden to remove roles from {discord_member.display_name}. Hierarchy issue?")
        except discord.HTTPException as e:
            logger.error(f"HTTP Exception removing roles from {discord_member.display_name}: {e}")
