import json
import secrets
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from app.config import settings
from app.database.repo import repo
from app.database import plus
from app.database.core import get_db_pool
from app.services.recipe_data import INGREDIENTS
from app.services.recipe_catalog import catalog
from app.services.planner import (
    defaults,
    parse,
    identify,
    rank,
    make_plan,
    replacement,
    groceries,
)
from app.tg_bot.ui import t, kb, menu, home
from app.tg_bot import payments

router = Router()


async def profile(uid):
    user = await repo.get_user(uid)
    data = defaults()
    if user and user.get("prefs_json"):
        data.update(json.loads(user["prefs_json"]))
    elif user:
        data["portions"] = min(8, max(1, user.get("portions") or 2))
        data["minutes"] = user.get("max_time") or 60
        data["vegetarian"] = bool(user.get("vegetarian"))
    return data


async def save_profile(uid, data):
    await repo._execute(
        "UPDATE users SET prefs_json=$1 WHERE user_id=$2", json.dumps(data), uid
    )


def names(ids, lang):
    return (
        ", ".join(
            INGREDIENTS[i][0 if lang == "ru" else 1] for i in ids if i in INGREDIENTS
        )
        or "—"
    )


def unit(value, lang):
    return "шт." if value == "шт" else value


def lines_items(items, lang):
    return "\n".join(
        f"• {i['name_' + lang]} — {i['amount']:g} {unit(i['unit'], lang)}"
        for i in items
    )


async def start_search(message, uid, lang):
    await repo.save_draft(uid, {"awaiting": "pantry"})
    await message.answer(
        t(
            lang,
            "Напишите продукты через запятую. Например: картошка, яйца, сыр. На 2, до 25 минут, без духовки.\nКоличество продуктов бот не учитывает: перед готовкой проверьте, хватит ли их.\nУсловия и исключения можно уточнить кнопкой ниже.",
            "Напишіть продукти через кому. Наприклад: картопля, яйця, сир. На 2, до 25 хвилин, без духовки.\nКількість продуктів бот не враховує: перед приготуванням перевірте, чи їх вистачить.\nУмови та виключення можна уточнити кнопкою нижче.",
        ),
        reply_markup=kb(
            [(t(lang, "Условия", "Умови"), "prefs")],
            [(t(lang, "Отмена", "Скасувати"), "cancel")],
        ),
    )


async def confirm(message, uid, lang, p):
    await repo.save_draft(uid, {"search": p})
    await save_profile(uid, p)
    text = t(lang, "Распознал: ", "Розпізнав: ") + names(p["pantry"], lang)
    text += t(
        lang,
        f"\nПорций: {p['portions']} · до {p['minutes']} мин",
        f"\nПорцій: {p['portions']} · до {p['minutes']} хв",
    )
    text += t(lang, "\nИспользовать сначала: ", "\nВикористати спочатку: ") + names(
        p["priority"], lang
    )
    await message.answer(
        text,
        reply_markup=kb(
            [(t(lang, "✅ Всё верно", "✅ Усе правильно"), "search_correct")],
            [(t(lang, "Изменить продукты", "Змінити продукти"), "search_edit")],
            [
                (t(lang, "Изменить условия", "Змінити умови"), "prefs"),
                (t(lang, "Использовать сначала", "Використати спочатку"), "priority"),
            ],
            [(t(lang, "Отмена", "Скасувати"), "cancel")],
        ),
    )


async def show_prefs(message, uid, lang):
    p = await profile(uid)
    rows = [
        [
            (t(lang, f"Порции: {n}", f"Порції: {n}"), f"pref:portions:{n}")
            for n in (1, 2, 4, 6)
        ],
        [
            (f"{n} " + t(lang, "мин", "хв"), f"pref:minutes:{n}")
            for n in (15, 30, 60, 120)
        ],
    ]
    equipment = {
        "stove": ("Плита", "Плита"),
        "oven": ("Духовка", "Духовка"),
        "kettle": ("Чайник", "Чайник"),
    }
    rows.append(
        [
            (
                ("✓ " if k in p["equipment"] else "○ ") + t(lang, *v),
                f"pref:equipment:{k}",
            )
            for k, v in equipment.items()
        ]
    )
    rows.append(
        [
            (
                ("✓ " if p["vegetarian"] else "○ ")
                + t(lang, "Без мяса и рыбы", "Без м’яса та риби"),
                "pref:vegetarian:toggle",
            )
        ]
    )
    allergy = {
        "egg": ("Яйца", "Яйця"),
        "milk": ("Молочное", "Молочне"),
        "fish": ("Рыба", "Риба"),
        "gluten": ("Глютен", "Глютен"),
    }
    for k, v in allergy.items():
        rows.append(
            [
                (
                    ("☑ " if k in p["allergens"] else "□ ")
                    + t(lang, "Исключить: ", "Виключити: ")
                    + t(lang, *v),
                    f"pref:allergens:{k}",
                )
            ]
        )
    rows += [
        [(t(lang, "Исключить продукты", "Виключити продукти"), "exclude")],
        [(t(lang, "Использовать сначала", "Використати спочатку"), "priority")],
        [(t(lang, "Подобрать рецепты", "Підібрати рецепти"), "search_correct")],
        home(lang),
    ]
    await message.answer(
        t(
            lang,
            f"⚙️ Сейчас: {p['portions']} порц., до {p['minutes']} мин.",
            f"⚙️ Зараз: {p['portions']} порц., до {p['minutes']} хв.",
        )
        + t(lang, "\nИсключения: ", "\nВиключення: ")
        + names(p["exclude"], lang)
        + t(
            lang,
            "\nФильтры учитывают состав каталога. Проверяйте этикетки и возможные следы аллергенов самостоятельно.",
            "\nФільтри враховують склад каталогу. Перевіряйте етикетки та можливі сліди алергенів самостійно.",
        ),
        reply_markup=kb(*rows),
    )


async def show_results(message, uid, lang, offset=0):
    p = await profile(uid)
    found = rank(p)
    if not found:
        return await message.answer(
            t(
                lang,
                "Подходящих рецептов нет. Измените продукты или условия.",
                "Відповідних рецептів немає. Змініть продукти або умови.",
            ),
            reply_markup=kb([(t(lang, "Изменить", "Змінити"), "prefs")], home(lang)),
        )
    rows, text = [], [t(lang, "🍳 Варианты на сегодня", "🍳 Варіанти на сьогодні")]
    for r in found[offset : offset + 4]:
        missing = [i["id"] for i in r["ingredients"] if i["id"] not in p["pantry"]]
        text.append(
            f"\n{r['title'][lang]} · {r['total_time']} "
            + t(lang, "мин", "хв")
            + t(lang, "\nДокупить: ", "\nДокупити: ")
            + names(missing, lang)
        )
        rows.append([(r["title"][lang], f"recipe:{r['id']}:{p['portions']}")])
    if offset + 4 < len(found):
        rows.append([(t(lang, "Ещё варианты", "Ще варіанти"), f"results:{offset + 4}")])
    rows += [
        [(t(lang, "Изменить продукты", "Змінити продукти"), "search_edit")],
        home(lang),
    ]
    await message.answer("\n".join(text), reply_markup=kb(*rows))


async def recipe_card(message, uid, lang, rid, portions):
    r = catalog.get_by_id(rid)
    if not r:
        return await message.answer(
            t(
                lang,
                "Рецепт больше недоступен. Откройте новое меню.",
                "Рецепт більше недоступний. Відкрийте нове меню.",
            ),
            reply_markup=menu(lang),
        )
    text = f"🍽 {r['title'][lang]}\n{r['total_time']} " + t(
        lang, f"мин · {portions} порц.", f"хв · {portions} порц."
    )
    text += "\n\n" + lines_items(groceries([rid], portions), lang)
    text += t(lang, "\nВода и соль — по необходимости.", "\nВода й сіль — за потреби.")
    text += "\n\n" + "\n\n".join(
        f"{n}. {step}" for n, step in enumerate(r["steps"][lang], 1)
    )
    await message.answer(
        text,
        reply_markup=kb(
            [
                (
                    t(lang, "▶ Готовить пошагово", "▶ Готувати покроково"),
                    f"cook:{rid}:{portions}",
                )
            ],
            [
                (
                    t(lang, "⭐ В избранное / убрать", "⭐ До обраного / прибрати"),
                    f"fav:{rid}",
                )
            ],
            [
                (
                    t(lang, "🛒 Добавить ингредиенты", "🛒 Додати інгредієнти"),
                    f"cart_recipe:{rid}:{portions}",
                )
            ],
            home(lang),
        ),
    )


async def plan_menu(message, uid, lang):
    paid = await plus.active(uid)
    rows = []
    if paid:
        for n in (3, 5, 7):
            rows.append(
                [
                    (
                        t(
                            lang,
                            f"{n} ужина · меньше продуктов",
                            f"{n} вечері · менше продуктів",
                        ),
                        f"plan_new:{n}:compact",
                    ),
                    (t(lang, "Разнообразие", "Різноманіття"), f"plan_new:{n}:variety"),
                ]
            )
    else:
        rows.append([(t(lang, "Открыть Plus / демо", "Відкрити Plus / демо"), "plus")])
    saved = await repo._fetchall(
        "SELECT id,created_at,demo FROM meal_plans WHERE user_id=$1 ORDER BY id DESC LIMIT 10",
        uid,
    )
    for r in saved:
        rows.append(
            [
                (
                    f"{'Демо ' if r['demo'] else ''}#{r['id']} · {r['created_at']:%d.%m}",
                    f"plan:{r['id']}",
                )
            ]
        )
    await message.answer(
        t(
            lang,
            "📅 Ваши планы. Учитываются текущие условия, продукты и приоритеты. «Меньше продуктов» сокращает число разных ингредиентов, а не гарантирует меньшую цену.",
            "📅 Ваші плани. Враховуються поточні умови, продукти та пріоритети. «Менше продуктів» скорочує кількість різних інгредієнтів, а не гарантує нижчу ціну.",
        ),
        reply_markup=kb(*rows, home(lang)),
    )


async def show_plan(message, uid, lang, pid):
    r = await plus.plan(uid, pid)
    if not r:
        return await message.answer(t(lang, "План не найден.", "План не знайдено."))
    body = r["body"]
    editable = await plus.active(uid) or (r["demo"] and r["swaps"] < 2)
    text = [
        t(lang, f"📅 План #{pid}", f"📅 План #{pid}"),
        t(
            lang,
            f"Порций: {body['profile']['portions']}",
            f"Порцій: {body['profile']['portions']}",
        ),
    ]
    if r["demo"]:
        text.append(
            t(
                lang,
                f"Демо · осталось замен: {max(0, 2 - r['swaps'])}",
                f"Демо · залишилося замін: {max(0, 2 - r['swaps'])}",
            )
        )
    rows = []
    for idx, rid in enumerate(body["recipes"]):
        dish = catalog.get_by_id(rid)
        text.append(
            f"{idx + 1}. {dish['title'][lang]} · {dish['total_time']} "
            + t(lang, "мин", "хв")
        )
        row = [
            (
                f"{idx + 1}. " + t(lang, "Рецепт", "Рецепт"),
                f"recipe:{rid}:{body['profile']['portions']}",
            )
        ]
        if editable:
            row.append(
                (
                    t(lang, "↻ Заменить", "↻ Замінити"),
                    f"swap:{pid}:{r['revision']}:{idx}",
                )
            )
        rows.append(row)
    all_items = groceries(body["recipes"], body["profile"]["portions"])
    text.append(
        t(
            lang,
            f"\nРазных ингредиентов: {len(all_items)}. Объёмы имеющихся продуктов неизвестны — список включает всё.",
            f"\nРізних інгредієнтів: {len(all_items)}. Обсяги наявних продуктів невідомі — список містить усе.",
        )
    )
    rows.append(
        [
            (
                t(lang, "🛒 Посмотреть общий список", "🛒 Переглянути спільний список"),
                f"plan_cart:{pid}",
            )
        ]
    )
    if await plus.active(uid):
        rows.append(
            [
                (
                    t(
                        lang,
                        "Повторить с текущими условиями",
                        "Повторити з поточними умовами",
                    ),
                    f"reuse:{pid}",
                )
            ]
        )
    rows.append(home(lang))
    await message.answer("\n".join(text), reply_markup=kb(*rows))


async def show_cart(message, uid, lang):
    items = await repo.get_shopping_list(uid)
    rows = []
    text = [t(lang, "🛒 Покупки", "🛒 Покупки")]
    for i in items[:40]:
        name = (
            names([i["ingredient_id"]], lang)
            if i["ingredient_id"] in INGREDIENTS
            else (i["ingredient_name"] or "—")
        )
        amount = format(i["amount"], "g") if i["amount"] is not None else "—"
        text.append(
            f"{'✓' if i['is_bought'] else '□'} {name} — {amount} {unit(i['unit'] or '', lang)}"
        )
        rows.append(
            [(("↩ " if i["is_bought"] else "✓ ") + name[:45], f"bought:{i['id']}")]
        )
    if not items:
        text.append(
            t(
                lang,
                "Пока пусто. Добавьте ингредиенты из рецепта или плана.",
                "Поки порожньо. Додайте інгредієнти з рецепта або плану.",
            )
        )
    rows += [
        [(t(lang, "Очистить список", "Очистити список"), "cart_clear_confirm")],
        home(lang),
    ]
    await message.answer("\n".join(text), reply_markup=kb(*rows))


@router.message(Command("start", "menu", "help"))
async def start(message: Message, lang: str):
    await repo.clear_draft(message.from_user.id)
    await message.answer(
        t(
            lang,
            "🍳 Что на ужин?\nПодберу блюда из ваших продуктов. Plus поможет спланировать несколько ужинов и собрать покупки.",
            "🍳 Що на вечерю?\nПідберу страви з ваших продуктів. Plus допоможе спланувати кілька вечерь і зібрати покупки.",
        ),
        reply_markup=menu(lang),
    )


@router.message(Command("plus"))
async def command_plus(message: Message, lang: str):
    await payments.show_plus(message, message.from_user.id, lang)


@router.message(Command("terms"))
async def command_terms(message: Message, lang: str):
    await payments.terms(message, lang)


@router.message(Command("privacy"))
async def privacy(message: Message, lang: str):
    await message.answer(
        t(
            lang,
            "Сохраняем Telegram ID, язык Telegram, условия питания, продукты, планы, покупки, избранное, историю и сведения о платежах. Рецепты загружаются с публичных страниц выбранных кулинарных сайтов без передачи Telegram ID. Сообщения не передаются внешней нейросети. Данные обрабатывают Telegram, Render и провайдер PostgreSQL. /delete_me удаляет данные питания; платёжные записи и отметка использования демо сохраняются для возвратов, сверки и защиты от повторного демо. Контакт владельца: ",
            "Зберігаємо Telegram ID, мову Telegram, умови харчування, продукти, плани, покупки, обране, історію та відомості про платежі. Рецепти завантажуються з публічних сторінок обраних кулінарних сайтів без передавання Telegram ID. Повідомлення не передаються зовнішній нейромережі. Дані обробляють Telegram, Render і провайдер PostgreSQL. /delete_me видаляє дані харчування; платіжні записи та позначка використання демо зберігаються для повернень, звірки й захисту від повторного демо. Контакт власника: ",
        )
        + (settings.support_contact or "—")
    )


@router.message(Command("delete_me"))
async def delete_me(message: Message, lang: str):
    await message.answer(
        t(
            lang,
            "Удалить продукты, условия, планы, избранное, историю и покупки? Сначала будет отключено автопродление. Платёжные записи и отметка демо останутся.",
            "Видалити продукти, умови, плани, обране, історію й покупки? Спершу буде вимкнено автоподовження. Платіжні записи та позначка демо залишаться.",
        ),
        reply_markup=kb(
            [(t(lang, "Да, удалить", "Так, видалити"), "delete_confirm")], home(lang)
        ),
    )


@router.callback_query()
async def callbacks(q: CallbackQuery, lang: str):
    if not isinstance(q.message, Message):
        return
    message, uid, data, bot = q.message, q.from_user.id, q.data or "", q.bot
    # Compatibility with the previous version's keyboards.
    data = {
        "search_edit_products": "search_edit",
        "search_edit_conditions": "prefs",
        "search_cancel": "cancel",
        "settings_main": "prefs",
        "search_more": "results:4",
    }.get(data, data)
    parts = data.split(":")
    action = parts[0]
    if data in ("home", "cancel"):
        await repo.clear_draft(uid)
        return await message.answer(
            t(lang, "Выберите действие:", "Оберіть дію:"), reply_markup=menu(lang)
        )
    if data in ("search", "search_edit"):
        return await start_search(message, uid, lang)
    if data == "search_correct":
        await repo.clear_draft(uid)
        return await show_results(message, uid, lang)
    if action == "results" and len(parts) == 2 and parts[1].isdigit():
        return await show_results(message, uid, lang, int(parts[1]))
    if data == "prefs":
        return await show_prefs(message, uid, lang)
    if action == "pref" and len(parts) == 3:
        p = await profile(uid)
        field, value = parts[1:]
        if field in ("portions", "minutes"):
            allowed = (1, 2, 4, 6) if field == "portions" else (15, 30, 60, 120)
            if not value.isdigit() or int(value) not in allowed:
                return
            p[field] = int(value)
        elif field in ("equipment", "allergens"):
            allowed = (
                {"stove", "oven", "kettle"}
                if field == "equipment"
                else {"egg", "milk", "fish", "gluten"}
            )
            if value not in allowed:
                return
            if value in p[field]:
                p[field].remove(value)
            else:
                p[field].append(value)
        elif field == "vegetarian":
            p[field] = not p[field]
        else:
            return
        await save_profile(uid, p)
        return await show_prefs(message, uid, lang)
    if data in ("exclude", "priority"):
        await repo.save_draft(uid, {"awaiting": data})
        return await message.answer(
            t(
                lang,
                "Напишите продукты через запятую; «—» очистит список. В следующем сообщении покажу, что распознано.",
                "Напишіть продукти через кому; «—» очистить список. У наступному повідомленні покажу, що розпізнано.",
            ),
            reply_markup=kb([(t(lang, "Отмена", "Скасувати"), "cancel")]),
        )
    if (
        action == "recipe"
        and len(parts) == 3
        and parts[2].isdigit()
        and 1 <= int(parts[2]) <= 8
    ):
        return await recipe_card(message, uid, lang, parts[1], int(parts[2]))
    if action == "fav" and len(parts) == 2 and catalog.get_by_id(parts[1]):
        state = await repo.toggle_favorite(uid, parts[1])
        return await message.answer(
            t(
                lang,
                "Добавлено в избранное." if state else "Убрано из избранного.",
                "Додано до обраного." if state else "Прибрано з обраного.",
            )
        )
    if data in ("favs", "history"):
        if data == "favs":
            ids = await repo.get_favorites(uid)
        else:
            ids = list(
                dict.fromkeys(h["recipe_id"] for h in await repo.get_history(uid))
            )
        p = await profile(uid)
        rows = [
            [(catalog.get_by_id(r)["title"][lang], f"recipe:{r}:{p['portions']}")]
            for r in ids
            if catalog.get_by_id(r)
        ]
        return await message.answer(
            t(
                lang,
                "Ваши рецепты:" if rows else "Пока пусто.",
                "Ваші рецепти:" if rows else "Поки порожньо.",
            ),
            reply_markup=kb(*rows[:40], home(lang)),
        )
    if (
        action == "cook"
        and len(parts) == 3
        and parts[2].isdigit()
        and 1 <= int(parts[2]) <= 8
        and catalog.get_by_id(parts[1])
    ):
        sid = secrets.token_hex(8)
        await repo._execute(
            "INSERT INTO cooking_sessions(id,user_id,recipe_id,portions) VALUES($1,$2,$3,$4)",
            sid,
            uid,
            parts[1],
            int(parts[2]),
        )
        return await cooking_step(message, uid, lang, sid, 0)
    if action == "step" and len(parts) == 3 and parts[2].isdigit():
        return await cooking_step(message, uid, lang, parts[1], int(parts[2]))
    if action == "finish" and len(parts) == 2:
        pool = await get_db_pool()
        async with pool.acquire() as c, c.transaction():
            r = await c.fetchrow(
                "UPDATE cooking_sessions SET finished=TRUE WHERE id=$1 AND user_id=$2 AND NOT finished RETURNING *",
                parts[1],
                uid,
            )
            if r:
                hid = await c.fetchval(
                    "INSERT INTO history(user_id,recipe_id,portions) VALUES($1,$2,$3) RETURNING id",
                    uid,
                    r["recipe_id"],
                    r["portions"],
                )
            else:
                return await message.answer(t(lang, "Уже сохранено.", "Уже збережено."))
        return await message.answer(
            t(lang, "Готово! Как получилось?", "Готово! Як вийшло?"),
            reply_markup=kb(
                [(str(n) + " ⭐", f"rate:{hid}:{n}") for n in (1, 2, 3, 4, 5)],
                home(lang),
            ),
        )
    if (
        action == "rate"
        and len(parts) == 3
        and all(x.isdigit() for x in parts[1:])
        and 1 <= int(parts[2]) <= 5
    ):
        await repo.rate_history(int(parts[1]), uid, int(parts[2]))
        return await message.answer(t(lang, "Оценка сохранена.", "Оцінку збережено."))
    if (
        action == "cart_recipe"
        and len(parts) == 3
        and parts[2].isdigit()
        and 1 <= int(parts[2]) <= 8
        and catalog.get_by_id(parts[1])
    ):
        source = f"recipe:{message.chat.id}:{message.message_id}:{parts[1]}:{parts[2]}"
        await plus.add_cart(uid, source, groceries([parts[1]], int(parts[2])))
        return await show_cart(message, uid, lang)
    if data == "cart":
        return await show_cart(message, uid, lang)
    if action == "bought" and len(parts) == 2 and parts[1].isdigit():
        await repo._execute(
            "UPDATE shopping_list SET is_bought=NOT is_bought WHERE id=$1 AND user_id=$2",
            int(parts[1]),
            uid,
        )
        # Invalidate old toggle keyboard so a second click cannot undo a check accidentally.
        await message.edit_reply_markup(reply_markup=None)
        return await show_cart(message, uid, lang)
    if data == "cart_clear_confirm":
        return await message.answer(
            t(lang, "Очистить все покупки?", "Очистити всі покупки?"),
            reply_markup=kb(
                [(t(lang, "Да, очистить", "Так, очистити"), "cart_clear")], home(lang)
            ),
        )
    if data == "cart_clear":
        pool = await get_db_pool()
        async with pool.acquire() as c, c.transaction():
            await c.execute("DELETE FROM shopping_list WHERE user_id=$1", uid)
            await c.execute("DELETE FROM cart_sources WHERE user_id=$1", uid)
        return await show_cart(message, uid, lang)
    if data == "plans":
        return await plan_menu(message, uid, lang)
    if data == "plus":
        return await payments.show_plus(message, uid, lang)
    if data == "buy_terms":
        await payments.terms(message, lang)
        return await message.answer(
            t(
                lang,
                "Продолжая, вы принимаете условия и автопродление.",
                "Продовжуючи, ви приймаєте умови та автоподовження.",
            ),
            reply_markup=kb(
                [
                    (
                        t(
                            lang,
                            "Принимаю — открыть счёт",
                            "Приймаю — відкрити рахунок",
                        ),
                        "buy",
                    )
                ],
                home(lang),
            ),
        )
    if data == "buy":
        return await payments.buy(message, uid, lang, bot)
    if data == "cancel_sub":
        return await message.answer(
            t(
                lang,
                "Отключить дальнейшие списания? Оплаченный доступ сохранится.",
                "Вимкнути подальші списання? Оплачений доступ збережеться.",
            ),
            reply_markup=kb(
                [(t(lang, "Отключить", "Вимкнути"), "cancel_sub_confirm")], home(lang)
            ),
        )
    if data == "cancel_sub_confirm":
        await payments.cancel(uid, bot)
        return await message.answer(
            t(
                lang,
                "Автопродление отключено. Оплаченный срок сохранён.",
                "Автоподовження вимкнено. Оплачений термін збережено.",
            )
        )
    if data == "demo" or (action == "plan_new" and len(parts) == 3):
        demo = data == "demo"
        if not demo and not await plus.active(uid):
            return await payments.show_plus(message, uid, lang)
        days, mode = (
            (3, "compact")
            if demo
            else (int(parts[1]) if parts[1].isdigit() else 0, parts[2])
        )
        try:
            body = make_plan(await profile(uid), days, mode)
        except ValueError:
            return await message.answer(
                t(
                    lang,
                    "Недостаточно подходящих рецептов. Измените условия или выберите меньше дней.",
                    "Недостатньо відповідних рецептів. Змініть умови або оберіть менше днів.",
                ),
                reply_markup=kb([(t(lang, "Условия", "Умови"), "prefs")], home(lang)),
            )
        pid = await plus.create_plan(uid, body, demo)
        if not pid:
            return await message.answer(
                t(
                    lang,
                    "Демо уже использовано или Plus закончился. Сохранённые планы:",
                    "Демо вже використано або Plus закінчився. Збережені плани:",
                ),
                reply_markup=kb([(t(lang, "Планы", "Плани"), "plans")]),
            )
        return await show_plan(message, uid, lang, pid)
    if action == "plan" and len(parts) == 2 and parts[1].isdigit():
        return await show_plan(message, uid, lang, int(parts[1]))
    if action == "swap" and len(parts) == 4 and all(x.isdigit() for x in parts[1:]):
        pid, revision, index = map(int, parts[1:])
        r = await plus.plan(uid, pid)
        if not r or not 0 <= index < len(r["body"]["recipes"]):
            return
        if r["revision"] != revision:
            await message.answer(
                t(
                    lang,
                    "Это старые кнопки. Показываю актуальный план.",
                    "Це старі кнопки. Показую актуальний план.",
                )
            )
            return await show_plan(message, uid, lang, pid)
        rid = replacement(r["body"], index)
        if not rid:
            return await message.answer(
                t(lang, "Других подходящих блюд нет.", "Інших відповідних страв немає.")
            )
        r["body"]["recipes"][index] = rid
        if not await plus.update_plan(uid, pid, revision, r["body"], swap=True):
            await message.answer(
                t(
                    lang,
                    "Изменение не применено: обновите план или проверьте Plus.",
                    "Зміну не застосовано: оновіть план або перевірте Plus.",
                )
            )
        return await show_plan(message, uid, lang, pid)
    if action == "reuse" and len(parts) == 2 and parts[1].isdigit():
        r = await plus.plan(uid, int(parts[1]))
        if not r or not await plus.active(uid):
            return await payments.show_plus(message, uid, lang)
        # Reuse the duration/mode; rebuild against CURRENT exclusions and equipment.
        try:
            body = make_plan(
                await profile(uid), len(r["body"]["recipes"]), r["body"]["mode"]
            )
        except ValueError:
            return await message.answer(
                t(
                    lang,
                    "С текущими условиями недостаточно рецептов.",
                    "З поточними умовами недостатньо рецептів.",
                )
            )
        pid = await plus.create_plan(uid, body)
        if pid:
            return await show_plan(message, uid, lang, pid)
    if (
        action in ("plan_cart", "plan_cart_add")
        and len(parts) >= 2
        and parts[1].isdigit()
    ):
        pid = int(parts[1])
        r = await plus.plan(uid, pid)
        if not r:
            return
        items = groceries(r["body"]["recipes"], r["body"]["profile"]["portions"])
        if action == "plan_cart":
            return await message.answer(
                t(
                    lang,
                    "Общий список для этого плана:\n",
                    "Спільний список для цього плану:\n",
                )
                + lines_items(items, lang),
                reply_markup=kb(
                    [
                        (
                            t(
                                lang,
                                "Добавить в покупки один раз",
                                "Додати до покупок один раз",
                            ),
                            f"plan_cart_add:{pid}:{r['revision']}",
                        )
                    ],
                    home(lang),
                ),
            )
        if len(parts) != 3 or not parts[2].isdigit() or int(parts[2]) != r["revision"]:
            return await show_plan(message, uid, lang, pid)
        # Source is plan id, not revision: swapping a dish cannot double the whole cart.
        added = await plus.add_cart(uid, f"plan:{pid}", items)
        if not added:
            await message.answer(
                t(
                    lang,
                    "Этот план уже добавлен. После замены блюда очистите покупки и добавьте актуальный план заново.",
                    "Цей план уже додано. Після заміни страви очистіть покупки й додайте актуальний план знову.",
                )
            )
        return await show_cart(message, uid, lang)
    if data == "delete_confirm":
        await payments.cancel(uid, bot)
        await repo.delete_user_data(uid)
        return await message.answer(
            t(
                lang,
                "Данные питания удалены. /start — начать заново.",
                "Дані харчування видалено. /start — почати знову.",
            )
        )
    if action == "refund" and len(parts) == 2 and uid in settings.admin_ids:
        draft = await repo.get_draft(uid) or {}
        values = draft.get("refund", [])
        if len(values) != 3 or values[2] != parts[1]:
            return
        owner, charge, _ = values
        row = await repo._fetchone(
            "SELECT * FROM plus_payments WHERE user_id=$1 AND charge_id=$2",
            owner,
            charge,
        )
        if not row:
            return
        if not row["refunded"]:
            # Telegram is the authority. An already-refunded reply is safe to reconcile.
            try:
                await bot.refund_star_payment(
                    user_id=owner, telegram_payment_charge_id=charge
                )
            except TelegramBadRequest as exc:
                if "CHARGE_ALREADY_REFUNDED" not in str(exc):
                    raise
            await plus.refund_record(owner, charge)
        await repo.clear_draft(uid)
        return await message.answer(
            "Refund recorded. Future renewals, if any, are controlled separately in Telegram."
        )
    await message.answer(
        t(
            lang,
            "Эта кнопка устарела. Откройте действие из нового меню.",
            "Ця кнопка застаріла. Відкрийте дію з нового меню.",
        ),
        reply_markup=menu(lang),
    )


async def cooking_step(message, uid, lang, sid, index):
    session = await repo._fetchone(
        "SELECT * FROM cooking_sessions WHERE id=$1 AND user_id=$2", sid, uid
    )
    if not session:
        return
    r = catalog.get_by_id(session["recipe_id"])
    if not r or not 0 <= index < len(r["steps"][lang]):
        return
    rows = []
    if index + 1 < len(r["steps"][lang]):
        rows.append([(t(lang, "Дальше →", "Далі →"), f"step:{sid}:{index + 1}")])
    else:
        rows.append([(t(lang, "✅ Приготовлено", "✅ Приготовано"), f"finish:{sid}")])
    if index:
        rows.append([(t(lang, "← Назад", "← Назад"), f"step:{sid}:{index - 1}")])
    await message.answer(
        f"{r['title'][lang]} · {index + 1}/{len(r['steps'][lang])}\n\n{r['steps'][lang][index]}",
        reply_markup=kb(*rows, home(lang)),
    )


@router.message(F.text)
async def text_input(message: Message, lang: str):
    uid = message.from_user.id
    text = message.text.strip()
    draft = await repo.get_draft(uid) or {}
    p = await profile(uid)
    # Old reply keyboards continue to work and do not get parsed as ingredients.
    old = {
        "🍳 Що приготувати?": "search",
        "🍳 Что приготовить?": "search",
        "🛒 Список покупок": "cart",
        "⚙️ Настройки": "prefs",
        "⚙️ Налаштування": "prefs",
    }
    if text in old:
        if old[text] == "search":
            return await start_search(message, uid, lang)
        if old[text] == "cart":
            return await show_cart(message, uid, lang)
        return await show_prefs(message, uid, lang)
    if text.startswith("/"):
        return await message.answer(
            t(lang, "Доступные действия:", "Доступні дії:"), reply_markup=menu(lang)
        )
    from app.tg_bot.internet import handle_text

    if await handle_text(message, lang, draft):
        return
    awaiting = draft.get("awaiting", "pantry")
    if awaiting in ("priority", "exclude"):
        found = [] if text == "—" else identify(text)
        if not found and text != "—":
            return await message.answer(
                t(
                    lang,
                    "Не распознал продукты. Попробуйте простые названия: молоко, яйца, рыба.",
                    "Не розпізнав продукти. Спробуйте прості назви: молоко, яйця, риба.",
                )
            )
        p[awaiting] = found
        await save_profile(uid, p)
        await repo.clear_draft(uid)
        await message.answer(t(lang, "Сохранено: ", "Збережено: ") + names(found, lang))
        return await show_prefs(message, uid, lang)
    p = parse(text[:1500], p)
    if not p["pantry"]:
        return await message.answer(
            t(
                lang,
                "Не распознал продукты. Напишите, например: картошка, яйца, сыр.",
                "Не розпізнав продукти. Напишіть, наприклад: картопля, яйця, сир.",
            ),
            reply_markup=menu(lang),
        )
    return await confirm(message, uid, lang, p)


@router.message()
async def unsupported(message: Message, lang: str):
    await message.answer(
        t(
            lang,
            "Пока принимаю продукты только текстом. Напишите их через запятую.",
            "Поки приймаю продукти лише текстом. Напишіть їх через кому.",
        ),
        reply_markup=menu(lang),
    )
