#!/usr/bin/env python3
"""Script to add a user as an admin to a specific guild."""

import argparse
import asyncio
import os
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Add the project root to sys.path so we can import src modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.db.engine import close_db, get_session, init_db
from src.db.models import GuildAdmin, GuildSettings


async def main() -> None:
    parser = argparse.ArgumentParser(description="Add an admin to a guild.")
    parser.add_argument("guild_id", type=str, help="The Discord Guild ID")
    parser.add_argument("user_id", type=str, help="The Discord User ID")
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL environment variable is required.")
        sys.exit(1)

    init_db(database_url)

    try:
        session: AsyncSession = await get_session()
        async with session.begin():
            # Find the guild
            stmt = select(GuildSettings).where(GuildSettings.discord_guild_id == args.guild_id)
            guild = await session.scalar(stmt)

            if not guild:
                print(f"Error: Guild with ID {args.guild_id} not found in the database.")
                sys.exit(1)

            # Check if admin already exists
            stmt = select(GuildAdmin).where(
                GuildAdmin.guild_settings_id == guild.id,
                GuildAdmin.discord_user_id == args.user_id,
            )
            existing_admin = await session.scalar(stmt)

            if existing_admin:
                print(f"User {args.user_id} is already an admin for guild {args.guild_id}.")
                return

            # Create admin
            new_admin = GuildAdmin(
                guild_settings_id=guild.id,
                discord_user_id=args.user_id,
            )
            session.add(new_admin)
            
        print(f"Successfully added user {args.user_id} as admin for guild {args.guild_id}.")
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
