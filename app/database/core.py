import aiosqlite
import logging
from app.config import settings
import os

logger = logging.getLogger(__name__)

async def init_db():
    db_dir = os.path.dirname(settings.database_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
        
    async with aiosqlite.connect(settings.database_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                language_mode TEXT DEFAULT 'auto',
                manual_language TEXT,
                last_tg_language TEXT,
                portions INTEGER DEFAULT 2,
                max_time INTEGER,
                equipment TEXT,
                excluded_ingredients TEXT,
                allergens TEXT,
                vegetarian BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS shopping_list (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                ingredient_id TEXT,
                ingredient_name TEXT,
                amount REAL,
                unit TEXT,
                is_bought BOOLEAN DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                user_id INTEGER,
                recipe_id TEXT,
                PRIMARY KEY (user_id, recipe_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                recipe_id TEXT,
                portions INTEGER,
                rating INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS draft_state (
                user_id INTEGER PRIMARY KEY,
                state_data TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                event_name TEXT,
                event_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()
        logger.info("Database initialized")

async def backup_db(backup_path: str):
    async with aiosqlite.connect(settings.database_path) as src:
        async with aiosqlite.connect(backup_path) as dst:
            await src.backup(dst)
