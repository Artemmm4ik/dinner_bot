from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from app.locales.manager import get_text
from app.tg_bot.keyboards import main_menu_kb, settings_kb, lang_kb
from app.database.repo import repo

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message, lang: str):
    await repo.log_event(message.from_user.id, "start")
    await message.answer(get_text(lang, 'welcome'), reply_markup=main_menu_kb(lang))

@router.message(Command("privacy"))
async def cmd_privacy(message: Message, lang: str):
    await message.answer(get_text(lang, 'privacy_msg'))

@router.message(Command("delete_me"))
async def cmd_delete_me(message: Message, lang: str):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, 'btn_yes_delete'), callback_data="delete_confirm")]
    ])
    await message.answer(get_text(lang, 'delete_confirm'), reply_markup=kb)

@router.callback_query(F.data == "delete_confirm")
async def process_delete(callback: CallbackQuery, lang: str):
    await repo.delete_user_data(callback.from_user.id)
    await callback.message.edit_text(get_text(lang, 'deleted_msg'))
    await callback.answer()

@router.message(lambda msg: msg.text in ["⚙️ Налаштування", "⚙️ Настройки"])
async def btn_settings(message: Message, lang: str):
    await message.answer(get_text(lang, 'settings_title'), reply_markup=settings_kb(lang))

@router.callback_query(F.data == "settings_lang")
async def settings_lang(callback: CallbackQuery, lang: str):
    await callback.message.edit_text(get_text(lang, 'lang_title'), reply_markup=lang_kb(lang))
    await callback.answer()

@router.callback_query(F.data.startswith("lang_"))
async def process_lang(callback: CallbackQuery, lang: str):
    mode_action = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    if mode_action == "auto":
        await repo.update_user_language(user_id, 'auto')
    else:
        await repo.update_user_language(user_id, 'manual', manual_lang=mode_action)
    
    # Reload lang
    db_user = await repo.get_user(user_id)
    if db_user['language_mode'] == 'auto':
        new_lang = db_user['last_tg_language'] or 'uk'
    else:
        new_lang = db_user['manual_language']
        
    await callback.message.edit_text(get_text(new_lang, 'settings_title'), reply_markup=settings_kb(new_lang))
    await callback.message.answer(get_text(new_lang, 'menu_title'), reply_markup=main_menu_kb(new_lang))
    await callback.answer()

@router.callback_query(F.data == "settings_main")
async def settings_main(callback: CallbackQuery, lang: str):
    await callback.message.edit_text(get_text(lang, 'settings_title'), reply_markup=settings_kb(lang))
    await callback.answer()
