import aiosqlite
import json
from typing import Optional, Dict, Any, List
from app.config import settings

class DBRepo:
    def __init__(self):
        self.db_path = settings.database_path

    async def _execute(self, query: str, params: tuple = ()) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(query, params)
            await db.commit()

    async def _fetchone(self, query: str, params: tuple = ()) -> Optional[aiosqlite.Row]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                return await cursor.fetchone()

    async def _fetchall(self, query: str, params: tuple = ()) -> List[aiosqlite.Row]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                return await cursor.fetchall()

    async def get_user(self, user_id: int) -> Optional[dict]:
        row = await self._fetchone("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return dict(row) if row else None

    async def create_user(self, user_id: int, language_mode: str = 'auto', tg_language: str = 'uk') -> None:
        await self._execute(
            "INSERT OR IGNORE INTO users (user_id, language_mode, last_tg_language) VALUES (?, ?, ?)",
            (user_id, language_mode, tg_language)
        )

    async def update_user_language(self, user_id: int, mode: str, manual_lang: Optional[str] = None, tg_lang: Optional[str] = None):
        updates = ["language_mode = ?"]
        params = [mode]
        if manual_lang is not None:
            updates.append("manual_language = ?")
            params.append(manual_lang)
        if tg_lang is not None:
            updates.append("last_tg_language = ?")
            params.append(tg_lang)
        
        query = f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?"
        params.append(user_id)
        await self._execute(query, tuple(params))

    async def update_user_prefs(self, user_id: int, portions: int, max_time: Optional[int] = None, equipment: Optional[str] = None, vegetarian: bool = False):
        await self._execute(
            "UPDATE users SET portions = ?, max_time = ?, equipment = ?, vegetarian = ? WHERE user_id = ?",
            (portions, max_time, equipment, int(vegetarian), user_id)
        )

    async def get_draft(self, user_id: int) -> Optional[dict]:
        row = await self._fetchone("SELECT state_data FROM draft_state WHERE user_id = ?", (user_id,))
        if row and row['state_data']:
            return json.loads(row['state_data'])
        return None

    async def save_draft(self, user_id: int, draft: dict):
        await self._execute(
            "INSERT OR REPLACE INTO draft_state (user_id, state_data) VALUES (?, ?)",
            (user_id, json.dumps(draft))
        )

    async def clear_draft(self, user_id: int):
        await self._execute("DELETE FROM draft_state WHERE user_id = ?", (user_id,))

    async def add_shopping_item(self, user_id: int, ingredient_id: str, name: str, amount: Optional[float], unit: Optional[str]):
        await self._execute(
            "INSERT INTO shopping_list (user_id, ingredient_id, ingredient_name, amount, unit) VALUES (?, ?, ?, ?, ?)",
            (user_id, ingredient_id, name, amount, unit)
        )

    async def get_shopping_list(self, user_id: int) -> List[dict]:
        rows = await self._fetchall("SELECT * FROM shopping_list WHERE user_id = ?", (user_id,))
        return [dict(r) for r in rows]

    async def mark_bought(self, item_id: int, user_id: int):
        await self._execute("UPDATE shopping_list SET is_bought = 1 WHERE id = ? AND user_id = ?", (item_id, user_id))

    async def delete_shopping_item(self, item_id: int, user_id: int):
        await self._execute("DELETE FROM shopping_list WHERE id = ? AND user_id = ?", (item_id, user_id))

    async def clear_bought(self, user_id: int):
        await self._execute("DELETE FROM shopping_list WHERE user_id = ? AND is_bought = 1", (user_id,))
        
    async def clear_shopping_list(self, user_id: int):
        await self._execute("DELETE FROM shopping_list WHERE user_id = ?", (user_id,))

    async def toggle_favorite(self, user_id: int, recipe_id: str) -> bool:
        row = await self._fetchone("SELECT * FROM favorites WHERE user_id = ? AND recipe_id = ?", (user_id, recipe_id))
        if row:
            await self._execute("DELETE FROM favorites WHERE user_id = ? AND recipe_id = ?", (user_id, recipe_id))
            return False
        else:
            await self._execute("INSERT INTO favorites (user_id, recipe_id) VALUES (?, ?)", (user_id, recipe_id))
            return True

    async def get_favorites(self, user_id: int) -> List[str]:
        rows = await self._fetchall("SELECT recipe_id FROM favorites WHERE user_id = ?", (user_id,))
        return [r['recipe_id'] for r in rows]

    async def add_history(self, user_id: int, recipe_id: str, portions: int):
        await self._execute(
            "INSERT INTO history (user_id, recipe_id, portions) VALUES (?, ?, ?)",
            (user_id, recipe_id, portions)
        )
        
    async def get_history(self, user_id: int) -> List[dict]:
        rows = await self._fetchall("SELECT * FROM history WHERE user_id = ? ORDER BY created_at DESC LIMIT 50", (user_id,))
        return [dict(r) for r in rows]

    async def rate_history(self, history_id: int, user_id: int, rating: int):
        await self._execute("UPDATE history SET rating = ? WHERE id = ? AND user_id = ?", (rating, history_id, user_id))

    async def log_event(self, user_id: int, event_name: str, event_data: Optional[dict] = None):
        await self._execute(
            "INSERT INTO analytics (user_id, event_name, event_data) VALUES (?, ?, ?)",
            (user_id, event_name, json.dumps(event_data) if event_data else None)
        )
        
    async def delete_user_data(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM draft_state WHERE user_id = ?", (user_id,))
            await db.execute("DELETE FROM shopping_list WHERE user_id = ?", (user_id,))
            await db.execute("DELETE FROM favorites WHERE user_id = ?", (user_id,))
            await db.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
            await db.execute("DELETE FROM analytics WHERE user_id = ?", (user_id,))
            await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            await db.commit()

repo = DBRepo()
