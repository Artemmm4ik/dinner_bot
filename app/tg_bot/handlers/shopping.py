from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from app.locales.manager import get_text
from app.services.recipe_catalog import catalog
from app.database.repo import repo
from app.tg_bot.keyboards import shopping_kb

router = Router()

class ShoppingState(StatesGroup):
    waiting_for_custom = State()

@router.callback_query(F.data.startswith("shop_add_recipe_"))
async def process_add_missing(callback: CallbackQuery, lang: str):
    recipe_id = callback.data.split("shop_add_recipe_")[1]
    recipe = catalog.get_by_id(recipe_id)
    user_id = callback.from_user.id
    
    draft = await repo.get_draft(user_id)
    user_ings_lower = [ui.lower() for ui in draft['ingredients']] if draft else []
    
    portions = draft['portions'] if draft else recipe['portions']
    multiplier = portions / recipe['portions']
    
    for ing in recipe['ingredients']:
        if ing['req']:
            name = ing[f'name_{lang}']
            if not any(name.lower() in ui or ui in name.lower() for ui in user_ings_lower):
                amount = ing.get('amount')
                calc_amount = amount * multiplier if amount else None
                await repo.add_shopping_item(user_id, ing['id'], name, calc_amount, ing.get('unit'))
                
    await repo.log_event(user_id, "shopping_list_added", {"source": "recipe", "recipe_id": recipe_id})
    await callback.answer(get_text(lang, 'added_to_shopping'))

@router.message(lambda msg: msg.text in ["🛒 Список покупок"])
async def btn_shopping(message: Message, lang: str):
    await show_shopping_list(message, lang)

async def show_shopping_list(message_or_callback, lang: str):
    user_id = message_or_callback.from_user.id
    items = await repo.get_shopping_list(user_id)
    
    if not items:
        text = get_text(lang, 'shopping_empty')
        kb = shopping_kb(lang, False)
    else:
        # Group by ingredient_id + unit if possible, or just list
        grouped = {}
        for item in items:
            key = (item['ingredient_name'], item['unit'])
            if key not in grouped:
                grouped[key] = {"amount": 0, "is_bought": item['is_bought'], "id": item['id']}
            if item['amount']:
                grouped[key]['amount'] += item['amount']
                
        items_text = ""
        for (name, unit), data in grouped.items():
            check = "✅" if data['is_bought'] else "➖"
            amount_str = f" {data['amount']:g} {unit}" if data['amount'] else ""
            items_text += f"{check} {name}{amount_str}\n"
            
        text = get_text(lang, 'shopping_title', items=items_text)
        kb = shopping_kb(lang, True)
        
    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(text, reply_markup=kb)
    else:
        await message_or_callback.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data == "shop_add_custom")
async def process_shop_add_custom(callback: CallbackQuery, lang: str, state: FSMContext):
    await callback.message.answer(get_text(lang, 'ask_custom_shopping'))
    await state.set_state(ShoppingState.waiting_for_custom)
    await callback.answer()

@router.message(ShoppingState.waiting_for_custom)
async def process_custom_item(message: Message, lang: str, state: FSMContext):
    await repo.add_shopping_item(message.from_user.id, "custom", message.text.strip(), None, None)
    await state.clear()
    await show_shopping_list(message, lang)

@router.callback_query(F.data == "shop_clear_bought")
async def process_shop_clear_bought(callback: CallbackQuery, lang: str):
    await repo.clear_bought(callback.from_user.id)
    await show_shopping_list(callback, lang)

@router.callback_query(F.data == "shop_clear_all")
async def process_shop_clear_all(callback: CallbackQuery, lang: str):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, 'yes_clear'), callback_data="shop_confirm_clear_all")],
        [InlineKeyboardButton(text=get_text(lang, 'btn_cancel'), callback_data="shop_cancel")]
    ])
    await callback.message.edit_text(get_text(lang, 'confirm_clear_all'), reply_markup=kb)

@router.callback_query(F.data == "shop_confirm_clear_all")
async def process_shop_confirm_clear_all(callback: CallbackQuery, lang: str):
    await repo.clear_shopping_list(callback.from_user.id)
    await show_shopping_list(callback, lang)

@router.callback_query(F.data == "shop_cancel")
async def process_shop_cancel(callback: CallbackQuery, lang: str):
    await show_shopping_list(callback, lang)
