from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject, Update
from app.database.repo import repo
from app.locales.manager import detect_language
import logging

logger = logging.getLogger(__name__)

class IdempotencyMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        update_id = event.update_id
        
        # Check if already processed
        if await repo.is_update_processed(update_id):
            logger.info(f"Update {update_id} already processed. Skipping.")
            return None
            
        try:
            result = await handler(event, data)
            # Mark as processed only if successful
            await repo.mark_update_processed(update_id)
            return result
        except Exception as e:
            logger.error(f"Error processing update {update_id}: {e}")
            raise

class UserLanguageMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)
            
        # Get from DB
        db_user = await repo.get_user(user.id)
        tg_lang = detect_language(user.language_code)
        
        if not db_user:
            await repo.create_user(user.id, 'auto', tg_lang)
            lang = tg_lang
            db_user = await repo.get_user(user.id)
        else:
            if db_user['language_mode'] == 'auto':
                if db_user['last_tg_language'] != tg_lang:
                    await repo.update_user_language(user.id, 'auto', tg_lang=tg_lang)
                lang = tg_lang
            else:
                lang = db_user['manual_language'] or 'uk'
                
        data["lang"] = lang
        data["db_user"] = db_user
        
        return await handler(event, data)
