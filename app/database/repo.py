import json
import logging
from typing import Optional, Dict, Any, List
from app.database.core import get_db_pool

logger = logging.getLogger(__name__)

class DBRepo:
    async def _execute(self, query: str, *params) -> None:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(query, *params)

    async def _fetchone(self, query: str, *params) -> Optional[dict]:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)
            return dict(row) if row else None

    async def _fetchall(self, query: str, *params) -> List[dict]:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows]

    async def get_user(self, user_id: int) -> Optional[dict]:
        return await self._fetchone("SELECT * FROM users WHERE user_id = $1", user_id)

    async def create_user(self, user_id: int, language_mode: str = 'auto', tg_language: str = 'uk') -> None:
        await self._execute(
            "INSERT INTO users (user_id, language_mode, last_tg_language) VALUES ($1, $2, $3) ON CONFLICT (user_id) DO NOTHING",
            user_id, language_mode, tg_language
        )

    async def update_user_language(self, user_id: int, mode: str, manual_lang: Optional[str] = None, tg_lang: Optional[str] = None):
        if manual_lang is not None:
            await self._execute("UPDATE users SET language_mode = $1, manual_language = $2 WHERE user_id = $3", mode, manual_lang, user_id)
        if tg_lang is not None:
            await self._execute("UPDATE users SET language_mode = $1, last_tg_language = $2 WHERE user_id = $3", mode, tg_lang, user_id)
        if manual_lang is None and tg_lang is None:
            await self._execute("UPDATE users SET language_mode = $1 WHERE user_id = $2", mode, user_id)

    async def update_user_prefs(self, user_id: int, portions: int, max_time: Optional[int] = None, equipment: Optional[str] = None, vegetarian: bool = False):
        await self._execute(
            "UPDATE users SET portions = $1, max_time = $2, equipment = $3, vegetarian = $4 WHERE user_id = $5",
            portions, max_time, equipment, vegetarian, user_id
        )

    async def get_draft(self, user_id: int) -> Optional[dict]:
        row = await self._fetchone("SELECT state_data FROM draft_state WHERE user_id = $1", user_id)
        if row and row['state_data']:
            return json.loads(row['state_data'])
        return None

    async def save_draft(self, user_id: int, draft: dict):
        await self._execute(
            "INSERT INTO draft_state (user_id, state_data) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET state_data = $2",
            user_id, json.dumps(draft)
        )

    async def clear_draft(self, user_id: int):
        await self._execute("DELETE FROM draft_state WHERE user_id = $1", user_id)

    async def add_shopping_item(self, user_id: int, ingredient_id: str, name: str, amount: Optional[float], unit: Optional[str]):
        await self._execute(
            "INSERT INTO shopping_list (user_id, ingredient_id, ingredient_name, amount, unit) VALUES ($1, $2, $3, $4, $5)",
            user_id, ingredient_id, name, amount, unit
        )

    async def get_shopping_list(self, user_id: int) -> List[dict]:
        return await self._fetchall("SELECT * FROM shopping_list WHERE user_id = $1", user_id)

    async def mark_bought(self, item_id: int, user_id: int):
        await self._execute("UPDATE shopping_list SET is_bought = TRUE WHERE id = $1 AND user_id = $2", item_id, user_id)

    async def delete_shopping_item(self, item_id: int, user_id: int):
        await self._execute("DELETE FROM shopping_list WHERE id = $1 AND user_id = $2", item_id, user_id)

    async def clear_bought(self, user_id: int):
        await self._execute("DELETE FROM shopping_list WHERE user_id = $1 AND is_bought = TRUE", user_id)
        
    async def clear_shopping_list(self, user_id: int):
        await self._execute("DELETE FROM shopping_list WHERE user_id = $1", user_id)

    async def toggle_favorite(self, user_id: int, recipe_id: str) -> bool:
        row = await self._fetchone("SELECT * FROM favorites WHERE user_id = $1 AND recipe_id = $2", user_id, recipe_id)
        if row:
            await self._execute("DELETE FROM favorites WHERE user_id = $1 AND recipe_id = $2", user_id, recipe_id)
            return False
        else:
            await self._execute("INSERT INTO favorites (user_id, recipe_id) VALUES ($1, $2)", user_id, recipe_id)
            return True

    async def get_favorites(self, user_id: int) -> List[str]:
        rows = await self._fetchall("SELECT recipe_id FROM favorites WHERE user_id = $1", user_id)
        return [r['recipe_id'] for r in rows]

    async def add_history(self, user_id: int, recipe_id: str, portions: int):
        await self._execute(
            "INSERT INTO history (user_id, recipe_id, portions) VALUES ($1, $2, $3)",
            user_id, recipe_id, portions
        )
        
    async def get_history(self, user_id: int) -> List[dict]:
        return await self._fetchall("SELECT * FROM history WHERE user_id = $1 ORDER BY created_at DESC LIMIT 50", user_id)

    async def rate_history(self, history_id: int, user_id: int, rating: int):
        await self._execute("UPDATE history SET rating = $1 WHERE id = $2 AND user_id = $3", rating, history_id, user_id)

    async def log_event(self, user_id: int, event_name: str, event_data: Optional[dict] = None):
        await self._execute(
            "INSERT INTO analytics (user_id, event_name, event_data) VALUES ($1, $2, $3)",
            user_id, event_name, json.dumps(event_data) if event_data else None
        )
        
    async def delete_user_data(self, user_id: int):
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM draft_state WHERE user_id = $1", user_id)
                await conn.execute("DELETE FROM shopping_list WHERE user_id = $1", user_id)
                await conn.execute("DELETE FROM favorites WHERE user_id = $1", user_id)
                await conn.execute("DELETE FROM history WHERE user_id = $1", user_id)
                await conn.execute("DELETE FROM analytics WHERE user_id = $1", user_id)
                await conn.execute("DELETE FROM users WHERE user_id = $1", user_id)

    # Idempotency methods
    async def is_update_processed(self, update_id: int) -> bool:
        row = await self._fetchone("SELECT 1 FROM processed_updates WHERE update_id = $1", update_id)
        return bool(row)

    async def mark_update_processed(self, update_id: int) -> None:
        await self._execute("INSERT INTO processed_updates (update_id) VALUES ($1) ON CONFLICT DO NOTHING", update_id)

repo = DBRepo()
