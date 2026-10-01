from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def t(lang, ru, uk):
    return ru if lang == "ru" else uk


def kb(*rows):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=label, callback_data=data)
                for label, data in row
            ]
            for row in rows
        ]
    )


def menu(lang):
    return kb(
        [
            (
                t(lang, "🌐 Найти рецепт в интернете", "🌐 Знайти рецепт в інтернеті"),
                "web_search",
            )
        ],
        [(t(lang, "🔖 Сохранённые с сайтов", "🔖 Збережені із сайтів"), "web_saved")],
        [
            (
                t(
                    lang,
                    "🍳 Подбор с расчётом продуктов",
                    "🍳 Підбір з розрахунком продуктів",
                ),
                "search",
            )
        ],
        [(t(lang, "📅 План ужинов · Plus", "📅 План вечерь · Plus"), "plans")],
        [
            (t(lang, "🛒 Покупки", "🛒 Покупки"), "cart"),
            (t(lang, "⭐ Избранное", "⭐ Обране"), "favs"),
        ],
        [
            (t(lang, "🕘 История", "🕘 Історія"), "history"),
            (t(lang, "⚙️ Условия", "⚙️ Умови"), "prefs"),
        ],
        [(t(lang, "💎 Мой Plus", "💎 Мій Plus"), "plus")],
    )


def home(lang):
    return [(t(lang, "← Меню", "← Меню"), "home")]
