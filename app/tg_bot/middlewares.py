from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from app.database.repo import repo
from app.locales.manager import detect_language


class UserLanguageMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        # End Telegram's spinner before DB-heavy processing. An expired old callback
        # must not prevent the action itself from being handled.
        if hasattr(event, "data"):
            try:
                await event.answer()
            except TelegramBadRequest:
                pass
        user = event.from_user
        if not user:
            return
        chat = getattr(event, "chat", None) or getattr(
            getattr(event, "message", None), "chat", None
        )
        if chat and chat.type != "private":
            return
        current = await repo.get_user(user.id)
        lang = (
            detect_language(user.language_code)
            if user.language_code
            else (current or {}).get("last_tg_language") or "uk"
        )
        await repo.create_user(user.id, lang)
        if not current or current["last_tg_language"] != lang:
            await repo.update_user_language(user.id, lang)
        data["lang"] = lang
        return await handler(event, data)
