import asyncpg
import logging
from app.config import settings

logger = logging.getLogger(__name__)

pool = None


async def init_db():
    global pool
    # Neon recommended settings: smaller pool size, statement cache size limits.
    pool = await asyncpg.create_pool(
        settings.database_url,
        min_size=1,
        max_size=3,
        statement_cache_size=0,
        command_timeout=30,
        server_settings={"statement_timeout": "20000"},
    )

    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                language_mode VARCHAR DEFAULT 'auto',
                manual_language VARCHAR,
                last_tg_language VARCHAR,
                portions INTEGER DEFAULT 2,
                max_time INTEGER,
                equipment TEXT,
                excluded_ingredients TEXT,
                allergens TEXT,
                vegetarian BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS shopping_list (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                ingredient_id VARCHAR,
                ingredient_name VARCHAR,
                amount REAL,
                unit VARCHAR,
                is_bought BOOLEAN DEFAULT FALSE
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                recipe_id VARCHAR,
                PRIMARY KEY (user_id, recipe_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                recipe_id VARCHAR,
                portions INTEGER,
                rating INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS draft_state (
                user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                state_data TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS analytics (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                event_name VARCHAR,
                event_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_updates (
                update_id BIGINT PRIMARY KEY,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        from pathlib import Path

        await conn.execute(Path(__file__).with_name("plus.sql").read_text())
        logger.info("PostgreSQL database schema initialized")


async def get_db_pool():
    if not pool:
        await init_db()
    return pool


async def close_db():
    global pool
    if pool:
        await pool.close()
        pool = None
