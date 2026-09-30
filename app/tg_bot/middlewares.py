from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from app.database.repo import repo
from app.locales.manager import detect_language

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
                # Update tg_lang if changed
                if db_user['last_tg_language'] != tg_lang:
                    await repo.update_user_language(user.id, 'auto', tg_lang=tg_lang)
                lang = tg_lang
            else:
                lang = db_user['manual_language'] or 'uk'
                
        data["lang"] = lang
        data["db_user"] = db_user
        
        return await handler(event, data)
