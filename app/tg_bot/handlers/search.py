from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from app.locales.manager import get_text
from app.services.parser import parse_input
from app.services.matcher import match_recipes
from app.services.recipe_catalog import catalog
from app.database.repo import repo
from app.tg_bot.keyboards import search_confirm_kb, recipe_list_kb

router = Router()

@router.message(lambda msg: msg.text in ["🍳 Що приготувати?", "🍳 Что приготовить?"])
async def btn_search(message: Message, lang: str):
    await message.answer(get_text(lang, 'ask_ingredients'))

@router.message(F.text & ~F.text.startswith('/'))
async def process_text(message: Message, lang: str, db_user: dict):
    # Ignore settings and menu buttons
    if message.text in ["🛒 Список покупок", "❤️ Обране", "🕘 Історія", "⚙️ Налаштування",
                        "🛒 Список покупок", "❤️ Избранное", "🕘 История", "⚙️ Настройки"]:
        return

    parsed = parse_input(message.text)
    
    # Merge with user settings if not provided
    portions = parsed['portions'] or db_user['portions'] or 2
    max_time = parsed['max_time'] or db_user['max_time']
    equipment = parsed['equipment']
    
    if db_user['equipment']:
        saved_eq = db_user['equipment'].split(',')
        equipment = list(set(equipment + saved_eq))
        
    for no_eq in parsed['no_equipment']:
        if no_eq in equipment:
            equipment.remove(no_eq)
            
    draft = {
        "ingredients": parsed['ingredients'],
        "portions": portions,
        "max_time": max_time,
        "equipment": equipment,
        "excluded": db_user['excluded_ingredients'].split(',') if db_user['excluded_ingredients'] else [],
        "allergens": db_user['allergens'].split(',') if db_user['allergens'] else [],
        "vegetarian": bool(db_user['vegetarian'])
    }
    
    await repo.save_draft(message.from_user.id, draft)
    
    eq_text = ""
    if "духовка" not in equipment:
        eq_text = get_text(lang, 'no_equipment')
        
    confirm_text = get_text(lang, 'search_confirm', 
                            ingredients=", ".join(draft['ingredients']),
                            portions=draft['portions'],
                            time=draft['max_time'] or "∞",
                            equipment_text=eq_text)
                            
    await message.answer(confirm_text, reply_markup=search_confirm_kb(lang))
    await repo.log_event(message.from_user.id, "search_submitted", draft)


@router.callback_query(F.data == "search_correct")
async def process_search_correct(callback: CallbackQuery, lang: str):
    user_id = callback.from_user.id
    draft = await repo.get_draft(user_id)
    if not draft:
        await callback.message.answer(get_text(lang, 'error_general'))
        return
        
    results = match_recipes(
        user_ingredients=draft['ingredients'],
        max_time=draft['max_time'],
        equipment=draft['equipment'],
        excluded=draft['excluded'],
        vegetarian=draft['vegetarian'],
        catalog=catalog.get_all(),
        lang=lang
    )
    
    if not results:
        await callback.message.edit_text(get_text(lang, 'no_results'))
        await repo.log_event(user_id, "no_results")
        return
        
    await repo.log_event(user_id, "results_shown", {"count": len(results)})
    
    draft['results'] = [r['id'] for r in results]
    draft['current_result_idx'] = 0
    await repo.save_draft(user_id, draft)
    
    await show_result(callback, lang, draft)

async def show_result(callback: CallbackQuery, lang: str, draft: dict):
    idx = draft['current_result_idx']
    recipe_id = draft['results'][idx]
    recipe = catalog.get_by_id(recipe_id)
    
    title = recipe['title'][lang]
    time = recipe['total_time']
    portions = draft['portions']
    
    # Calculate missing text
    # The matching already stored missing info (wait, matching didn't save it to DB, we need to re-eval or just keep it simple)
    # Let's re-eval missing for simplicity
    missing = []
    user_ings_lower = [ui.lower() for ui in draft['ingredients']]
    for ing in recipe['ingredients']:
        if ing['req']:
            name = ing[f'name_{lang}'].lower()
            if not any(name in ui or ui in name for ui in user_ings_lower):
                missing.append(ing[f'name_{lang}'])
                
    missing_text = get_text(lang, 'recipe_missing', missing=", ".join(missing)) if missing else ""
    reason = "Підходить за часом" if lang == 'uk' else "Подходит по времени"
    
    text = get_text(lang, 'recipe_card', title=title, time=time, portions=portions, missing=missing_text, reason=reason)
    
    show_more = len(draft['results']) > idx + 1
    kb = recipe_list_kb(lang, recipe_id, show_more)
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "search_more")
async def process_search_more(callback: CallbackQuery, lang: str):
    draft = await repo.get_draft(callback.from_user.id)
    if not draft or draft['current_result_idx'] + 1 >= len(draft['results']):
        await callback.message.answer(get_text(lang, 'no_more_options'))
        return
        
    draft['current_result_idx'] += 1
    await repo.save_draft(callback.from_user.id, draft)
    await show_result(callback, lang, draft)

@router.message(F.photo)
async def process_photo(message: Message, lang: str):
    await message.answer(get_text(lang, 'ask_photo'))
