from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from app.locales.manager import get_text


def main_menu_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_text(lang, "btn_search"))],
            [
                KeyboardButton(text=get_text(lang, "btn_shopping")),
                KeyboardButton(text=get_text(lang, "btn_favs")),
            ],
            [
                KeyboardButton(text=get_text(lang, "btn_history")),
                KeyboardButton(text=get_text(lang, "btn_settings")),
            ],
        ],
        resize_keyboard=True,
    )


def settings_kb(lang: str) -> InlineKeyboardMarkup:
    # We removed the Language button entirely from the settings.
    # Currently it is empty or can contain other future settings.
    return InlineKeyboardMarkup(
        inline_keyboard=[
            # [InlineKeyboardButton(text="Placeholder for other settings", callback_data="placeholder")]
        ]
    )


def search_confirm_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_text(lang, "btn_correct"), callback_data="search_correct"
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_text(lang, "btn_edit_ing"), callback_data="search_edit_ing"
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_text(lang, "btn_edit_cond"),
                    callback_data="search_edit_cond",
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_text(lang, "btn_cancel"), callback_data="search_cancel"
                )
            ],
        ]
    )


def recipe_list_kb(lang: str, recipe_id: str, show_more: bool) -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton(
                text=get_text(lang, "btn_open_recipe"),
                callback_data=f"recipe_open_{recipe_id}",
            )
        ]
    ]
    if show_more:
        kb.append(
            [
                InlineKeyboardButton(
                    text=get_text(lang, "btn_more_options"), callback_data="search_more"
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=kb)


def recipe_details_kb(
    lang: str, recipe_id: str, has_missing: bool, is_fav: bool
) -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton(
                text=get_text(lang, "btn_start_cooking"),
                callback_data=f"cook_start_{recipe_id}",
            )
        ]
    ]
    if has_missing:
        kb.append(
            [
                InlineKeyboardButton(
                    text=get_text(lang, "btn_add_shopping"),
                    callback_data=f"shop_add_recipe_{recipe_id}",
                )
            ]
        )

    fav_text = get_text(lang, "btn_rm_fav") if is_fav else get_text(lang, "btn_add_fav")
    kb.append(
        [InlineKeyboardButton(text=fav_text, callback_data=f"fav_toggle_{recipe_id}")]
    )

    return InlineKeyboardMarkup(inline_keyboard=kb)


def cooking_step_kb(
    lang: str, recipe_id: str, step: int, total: int
) -> InlineKeyboardMarkup:
    row = []
    if step > 1:
        row.append(
            InlineKeyboardButton(
                text=get_text(lang, "btn_prev"),
                callback_data=f"cook_step_{recipe_id}_{step - 1}",
            )
        )
    if step < total:
        row.append(
            InlineKeyboardButton(
                text=get_text(lang, "btn_next"),
                callback_data=f"cook_step_{recipe_id}_{step + 1}",
            )
        )
    else:
        row.append(
            InlineKeyboardButton(
                text=get_text(lang, "btn_finish_cooking"),
                callback_data=f"cook_finish_{recipe_id}",
            )
        )

    return InlineKeyboardMarkup(inline_keyboard=[row])


def rate_kb(lang: str, history_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_text(lang, "btn_like"),
                    callback_data=f"rate_like_{history_id}",
                ),
                InlineKeyboardButton(
                    text=get_text(lang, "btn_dislike"),
                    callback_data=f"rate_dislike_{history_id}",
                ),
            ]
        ]
    )


def shopping_kb(lang: str, has_items: bool) -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton(
                text=get_text(lang, "btn_add_custom"), callback_data="shop_add_custom"
            )
        ]
    ]
    if has_items:
        kb.append(
            [
                InlineKeyboardButton(
                    text=get_text(lang, "btn_clear_bought"),
                    callback_data="shop_clear_bought",
                )
            ]
        )
        kb.append(
            [
                InlineKeyboardButton(
                    text=get_text(lang, "btn_clear_all"), callback_data="shop_clear_all"
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=kb)
