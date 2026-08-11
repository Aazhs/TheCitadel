import asyncio
import os
import sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def drop_all():
    url = os.getenv("DATABASE_URL")
    if not url:
        print("Error: DATABASE_URL environment variable is required.")
        sys.exit(1)
        
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE;"))
        await conn.execute(text("CREATE SCHEMA public;"))
        await conn.execute(text("GRANT ALL ON SCHEMA public TO postgres;"))
        await conn.execute(text("GRANT ALL ON SCHEMA public TO public;"))
        print("Schema public dropped and recreated. Database is now completely empty.")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(drop_all())
