from aiogram import Router
from aiogram.types import Message
from app.locales.manager import get_text
from app.database.repo import repo
from app.services.recipe_catalog import catalog

router = Router()


@router.message(lambda msg: msg.text in ["🕘 Історія", "🕘 История"])
async def btn_history(message: Message, lang: str):
    user_id = message.from_user.id
    history_records = await repo.get_history(user_id)

    if not history_records:
        await message.answer(get_text(lang, "history_empty"))
        return

    text = get_text(lang, "history_title") + "\n\n"

    # Show last 10 records
    for h in history_records[:10]:
        recipe = catalog.get_by_id(h["recipe_id"])
        if recipe:
            title = recipe["title"][lang]
            date_str = h["created_at"][:10]
            rating_str = ""
            if h["rating"] == 1:
                rating_str = "👍"
            elif h["rating"] == 0:
                rating_str = "👎"

            text += f"• {date_str}: {title} ({h['portions']} порц.) {rating_str}\n"

    await message.answer(text)
