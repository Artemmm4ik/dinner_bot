import json
import secrets
from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.filters import Command
from app.database.repo import repo
from app.database import plus
from app.tg_bot.ui import kb, home, t
from app.services.web_recipes import (
    search,
    SearchUnavailable,
    public_link,
    recipe_details,
    refresh_recent,
)

router = Router()


async def prompt(message, uid, lang):
    await repo.save_draft(uid, {"awaiting": "internet"})
    await message.answer(
        t(
            lang,
            "🌐 Напишите блюдо или продукты: «ужин из кабачков и курицы за 30 минут». Поиск идёт по сайтам, а не по короткому каталогу.\n\nБот покажет найденные рецепты и их состав. Время, состав и ограничения нужно проверить у автора рецепта. Поиск идёт по индексу публичных страниц; бот загружает выбранные страницы без Telegram ID. Источники: Клопотенко, SHUBA, Еда.",
            "🌐 Напишіть страву або продукти: «вечеря з кабачків і курки за 30 хвилин». Пошук іде сайтами, а не коротким каталогом.\n\nБот покаже знайдені рецепти та їхній склад. Час, склад та обмеження треба перевірити в автора рецепта. Пошук іде індексом публічних сторінок; бот завантажує вибрані сторінки без Telegram ID. Источники: Клопотенко, SHUBA, Еда.",
        ),
        reply_markup=kb(home(lang)),
    )


async def results(message, uid, lang, query, page=0):
    await message.answer(t(lang, "Ищу рецепты…", "Шукаю рецепти…"))
    try:
        found = await search(uid, query, lang, page)
    except SearchUnavailable:
        text = t(
            lang,
            "Источники временно недоступны или ограничили загрузку. Попробуйте позже.",
            "Джерела тимчасово недоступні або обмежили завантаження. Спробуйте пізніше.",
        )
        return await message.answer(
            text,
            reply_markup=kb(
                [
                    (
                        t(
                            lang,
                            "Рецепты с известным составом",
                            "Рецепти з відомим складом",
                        ),
                        "search",
                    )
                ],
                home(lang),
            ),
        )
    token = secrets.token_hex(6)
    await repo.save_draft(
        uid,
        {
            "awaiting": "internet",
            "web": found,
            "query": query,
            "page": page,
            "token": token,
        },
    )
    if not found:
        rows = []
        if getattr(found, "has_more", False):
            rows.append(
                [
                    (
                        t(
                            lang,
                            "Проверить следующие страницы",
                            "Перевірити наступні сторінки",
                        ),
                        f"web_more:{token}",
                    )
                ]
            )
        await message.answer(
            t(
                lang,
                "На этих страницах не удалось разобрать доступные рецепты. Попробуйте следующие или уточните название блюда.",
                "На цих сторінках не вдалося розібрати доступні рецепти. Спробуйте наступні або уточніть назву страви.",
            ),
            reply_markup=kb(*rows, home(lang)),
        )
        return
    for index, row in enumerate(found):
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=t(
                            lang,
                            "Открыть рецепт у автора ↗",
                            "Відкрити рецепт в автора ↗",
                        ),
                        url=row["url"],
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=t(lang, "Состав рецепта", "Склад рецепта"),
                        callback_data=f"web_read:{token}:{index}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=t(lang, "🔖 Сохранить ссылку", "🔖 Зберегти посилання"),
                        callback_data=f"web_save:{token}:{index}",
                    )
                ],
            ]
        )
        await message.answer(f"{row['title']}\n{row['domain']}", reply_markup=keyboard)
    rows = []
    if getattr(found, "has_more", False):
        rows.append([(t(lang, "Ещё результаты", "Ще результати"), f"web_more:{token}")])
    rows += [[(t(lang, "Другой запрос", "Інший запит"), "web_search")], home(lang)]
    await message.answer(
        t(
            lang,
            "Результаты прямого парсинга сайтов. Совпадение с ограничениями питания не проверено.",
            "Результати прямого парсингу сайтів. Відповідність обмеженням харчування не перевірено.",
        ),
        reply_markup=kb(*rows),
    )


@router.message(Command("search"))
async def command_search(message: Message, lang: str):
    await prompt(message, message.from_user.id, lang)


@router.callback_query(F.data.startswith("web_"))
async def callbacks(q: CallbackQuery, lang: str):
    if not isinstance(q.message, Message):
        return
    uid, message = q.from_user.id, q.message
    parts = q.data.split(":")
    action = parts[0]
    if action == "web_search":
        return await prompt(message, uid, lang)
    if action == "web_quick" and len(parts) == 2:
        if not await plus.active(uid):
            from app.tg_bot.payments import show_plus

            return await show_plus(message, uid, lang)
        draft = await repo.get_draft(uid) or {}
        if draft.get("token") != parts[1] or len(draft.get("web", [])) < 3:
            return await prompt(message, uid, lang)
        await repo._execute(
            "INSERT INTO web_boards(user_id,body) VALUES($1,$2)",
            uid,
            json.dumps(draft["web"][:3], ensure_ascii=False),
        )
        return await message.answer(
            t(
                lang,
                "План сохранён. Условия питания по сайтам не проверены.",
                "План збережено. Умови харчування за сайтами не перевірено.",
            ),
            reply_markup=kb(
                [(t(lang, "Открыть планы", "Відкрити плани"), "web_boards")], home(lang)
            ),
        )
    if action in ("web_more", "web_save", "web_read"):
        draft = await repo.get_draft(uid) or {}
        if len(parts) < 2 or parts[1] != draft.get("token"):
            return await message.answer(
                t(
                    lang,
                    "Результаты устарели. Запустите новый поиск.",
                    "Результати застаріли. Запустіть новий пошук.",
                ),
                reply_markup=kb([(t(lang, "Поиск", "Пошук"), "web_search")]),
            )
        if action == "web_more":
            return await results(message, uid, lang, draft["query"], draft["page"] + 1)
        if (
            len(parts) != 3
            or not parts[2].isdigit()
            or int(parts[2]) >= len(draft["web"])
        ):
            return
        row = draft["web"][int(parts[2])]
        if not public_link(row["url"]):
            return
        if action == "web_read":
            ingredients = row.get("ingredients", [])
            text = row["title"] + "\n\n" + "\n".join("• " + i for i in ingredients)
            text += (
                t(
                    lang,
                    "\n\nКоличество — как у автора, без пересчёта. Приготовление: ",
                    "\n\nКількість — як в автора, без перерахунку. Приготування: ",
                )
                + row["url"]
            )
            for start in range(0, len(text), 3800):
                await message.answer(text[start : start + 3800])
            return
        await repo._execute(
            "INSERT INTO web_saved(user_id,url,title) VALUES($1,$2,$3) ON CONFLICT(user_id,url) DO NOTHING",
            uid,
            row["url"],
            row["title"],
        )
        return await message.answer(
            t(lang, "Ссылка сохранена.", "Посилання збережено.")
        )
    if action == "web_saved":
        saved = await repo._fetchall(
            "SELECT * FROM web_saved WHERE user_id=$1 ORDER BY id DESC LIMIT 40", uid
        )
        rows = [
            [
                InlineKeyboardButton(text=r["title"][:60], url=r["url"]),
                InlineKeyboardButton(text="×", callback_data=f"web_delete:{r['id']}"),
            ]
            for r in saved
        ]
        rows.append(
            [
                InlineKeyboardButton(
                    text=t(
                        lang,
                        "📅 Собрать интернет-план · Plus",
                        "📅 Зібрати інтернет-план · Plus",
                    ),
                    callback_data="web_plan",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=t(lang, "Мои интернет-планы", "Мої інтернет-плани"),
                    callback_data="web_boards",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="← " + t(lang, "Меню", "Меню"), callback_data="home"
                )
            ]
        )
        return await message.answer(
            t(
                lang,
                "Сохранённые ссылки:"
                if saved
                else "Сначала сохраните рецепты из поиска.",
                "Збережені посилання:"
                if saved
                else "Спочатку збережіть рецепти з пошуку.",
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
    if action == "web_delete" and len(parts) == 2 and parts[1].isdigit():
        await repo._execute(
            "DELETE FROM web_saved WHERE id=$1 AND user_id=$2", int(parts[1]), uid
        )
        return await message.answer(t(lang, "Ссылка удалена.", "Посилання видалено."))
    if action == "web_plan":
        if not await plus.active(uid):
            from app.tg_bot.payments import show_plus

            return await show_plus(message, uid, lang)
        await repo.save_draft(uid, {"awaiting": "web_board"})
        saved = await repo._fetchall(
            "SELECT id,title FROM web_saved WHERE user_id=$1 ORDER BY id DESC LIMIT 40",
            uid,
        )
        return await message.answer(
            t(
                lang,
                "Введите ID 3, 5 или 7 сохранённых рецептов в порядке ужинов, через пробел. Например: 12 9 4. В таком плане сохраняются ссылки; состав и покупки автоматически не рассчитываются.\n\n",
                "Введіть ID 3, 5 або 7 збережених рецептів у порядку вечерь, через пробіл. Наприклад: 12 9 4. У такому плані зберігаються посилання; склад та покупки автоматично не розраховуються.\n\n",
            )
            + "\n".join(f"{r['id']}: {r['title']}" for r in saved),
            reply_markup=kb(home(lang)),
        )
    if action == "web_boards":
        saved = await repo._fetchall(
            "SELECT id,created_at FROM web_boards WHERE user_id=$1 ORDER BY id DESC LIMIT 20",
            uid,
        )
        return await message.answer(
            t(lang, "Интернет-планы:", "Інтернет-плани:"),
            reply_markup=kb(
                *[
                    [(f"#{r['id']} · {r['created_at']:%d.%m}", f"web_board:{r['id']}")]
                    for r in saved
                ],
                home(lang),
            ),
        )
    if (
        action in ("web_board", "web_ingredients")
        and len(parts) == 2
        and parts[1].isdigit()
    ):
        row = await repo._fetchone(
            "SELECT body FROM web_boards WHERE user_id=$1 AND id=$2", uid, int(parts[1])
        )
        if row:
            recipes = json.loads(row["body"])
            if action == "web_ingredients":
                for recipe in recipes:
                    try:
                        details = await recipe_details(recipe["url"])
                    except SearchUnavailable:
                        details = None
                    text = recipe["title"] + "\n"
                    text += (
                        "\n".join("• " + i for i in details["ingredients"])
                        if details
                        else t(
                            lang,
                            "Состав недоступен; откройте источник.",
                            "Склад недоступний; відкрийте джерело.",
                        )
                    )
                    text += "\n" + recipe["url"]
                    for start in range(0, len(text), 3800):
                        await message.answer(text[start : start + 3800])
                return await message.answer(
                    t(
                        lang,
                        "Количество указано для порций автора. Повторяющиеся продукты и единицы не суммируются автоматически.",
                        "Кількість указано для порцій автора. Повторювані продукти й одиниці не підсумовуються автоматично.",
                    )
                )
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=f"{i + 1}. {r['title']}"[:64], url=r["url"]
                        )
                    ]
                    for i, r in enumerate(recipes)
                ]
            )
            keyboard.inline_keyboard.append(
                [
                    InlineKeyboardButton(
                        text=t(lang, "🛒 Состав всех блюд", "🛒 Склад усіх страв"),
                        callback_data=f"web_ingredients:{parts[1]}",
                    )
                ]
            )
            return await message.answer(
                t(
                    lang,
                    "📅 Ваш интернет-план. Открывайте рецепты по порядку.",
                    "📅 Ваш інтернет-план. Відкривайте рецепти за порядком.",
                ),
                reply_markup=keyboard,
            )


async def handle_text(message, lang, draft):
    uid = message.from_user.id
    if draft.get("awaiting") == "internet":
        await results(message, uid, lang, message.text[:350])
        return True
    if draft.get("awaiting") == "web_board":
        if not await plus.active(uid):
            from app.tg_bot.payments import show_plus

            await show_plus(message, uid, lang)
            return True
        ids = message.text.split()
        if (
            len(ids) not in (3, 5, 7)
            or any(not x.isdigit() for x in ids)
            or len(set(ids)) != len(ids)
        ):
            await message.answer(
                t(
                    lang,
                    "Нужны 3, 5 или 7 разных ID через пробел.",
                    "Потрібні 3, 5 або 7 різних ID через пробіл.",
                )
            )
            return True
        saved = await repo._fetchall(
            "SELECT id,title,url FROM web_saved WHERE user_id=$1 AND id=ANY($2::bigint[])",
            uid,
            list(map(int, ids)),
        )
        by_id = {r["id"]: r for r in saved}
        if len(by_id) != len(ids):
            await message.answer(
                t(
                    lang,
                    "Не все рецепты найдены среди ваших ссылок.",
                    "Не всі рецепти знайдено серед ваших посилань.",
                )
            )
            return True
        ordered = [by_id[int(i)] for i in ids]
        await repo._execute(
            "INSERT INTO web_boards(user_id,body) VALUES($1,$2)",
            uid,
            json.dumps(ordered, ensure_ascii=False),
        )
        await repo.clear_draft(uid)
        await message.answer(
            t(lang, "План сохранён.", "План збережено."),
            reply_markup=kb(
                [(t(lang, "Открыть планы", "Відкрити плани"), "web_boards")], home(lang)
            ),
        )
        return True
    return False


@router.message(Command("refresh_sources"))
async def refresh(message: Message, lang: str):
    from app.config import settings

    if message.from_user.id not in settings.admin_ids:
        return
    await message.answer(
        t(lang, "Обновляю индекс источников…", "Оновлюю індекс джерел…")
    )
    await refresh_recent()
    from app.services.web_recipes import index_urls

    count = len(await index_urls())
    await message.answer(
        t(
            lang,
            f"В индексе {count} адресов. Недоступные источники пропускаются.",
            f"В індексі {count} адрес. Недоступні джерела пропускаються.",
        )
    )
