from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from app.locales.manager import get_text
from app.services.recipe_catalog import catalog
from app.database.repo import repo
from app.tg_bot.keyboards import recipe_details_kb, cooking_step_kb, rate_kb

router = Router()

@router.callback_query(F.data.startswith("recipe_open_"))
async def process_recipe_open(callback: CallbackQuery, lang: str):
    recipe_id = callback.data.split("recipe_open_")[1]
    recipe = catalog.get_by_id(recipe_id)
    if not recipe:
        return
        
    user_id = callback.from_user.id
    draft = await repo.get_draft(user_id)
    portions = draft['portions'] if draft else recipe['portions']
    multiplier = portions / recipe['portions']
    
    user_ings_lower = [ui.lower() for ui in draft['ingredients']] if draft else []
    
    ingredients_text = ""
    available = []
    missing = []
    has_missing = False
    
    for ing in recipe['ingredients']:
        amount = ing.get('amount')
        amount_text = f"{amount * multiplier:g} {ing['unit']}" if amount else ""
        name = ing[f'name_{lang}']
        ingredients_text += f"• {name} {amount_text}\n"
        
        if ing['req']:
            if any(name.lower() in ui or ui in name.lower() for ui in user_ings_lower):
                available.append(name)
            else:
                missing.append(name)
                has_missing = True
                
    title = recipe['title'][lang]
    available_text = ", ".join(available) if available else "-"
    missing_text = ", ".join(missing) if missing else "-"
    equipment = ", ".join(recipe.get('equipment', [])) or "-"
    
    text = get_text(lang, 'recipe_details', 
                    title=title, 
                    ingredients=ingredients_text,
                    available=available_text,
                    missing=missing_text,
                    prep_time=recipe['prep_time'],
                    total_time=recipe['total_time'],
                    equipment=equipment)
                    
    is_fav = recipe_id in await repo.get_favorites(user_id)
    kb = recipe_details_kb(lang, recipe_id, has_missing, is_fav)
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await repo.log_event(user_id, "recipe_opened", {"recipe_id": recipe_id})

@router.callback_query(F.data.startswith("cook_start_"))
async def process_cook_start(callback: CallbackQuery, lang: str):
    recipe_id = callback.data.split("cook_start_")[1]
    recipe = catalog.get_by_id(recipe_id)
    if not recipe:
        return
        
    await repo.log_event(callback.from_user.id, "cooking_started", {"recipe_id": recipe_id})
    await show_cook_step(callback, lang, recipe_id, 1)

async def show_cook_step(callback: CallbackQuery, lang: str, recipe_id: str, step: int):
    recipe = catalog.get_by_id(recipe_id)
    steps = recipe['steps'][lang]
    total = len(steps)
    
    text = get_text(lang, 'step_msg', step=step, total=total, text=steps[step-1])
    kb = cooking_step_kb(lang, recipe_id, step, total)
    
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("cook_step_"))
async def process_cook_step(callback: CallbackQuery, lang: str):
    _, _, recipe_id, step_str = callback.data.split("_")
    await show_cook_step(callback, lang, recipe_id, int(step_str))

@router.callback_query(F.data.startswith("cook_finish_"))
async def process_cook_finish(callback: CallbackQuery, lang: str):
    recipe_id = callback.data.split("cook_finish_")[1]
    user_id = callback.from_user.id
    
    draft = await repo.get_draft(user_id)
    portions = draft['portions'] if draft else 2
    
    await repo.add_history(user_id, recipe_id, portions)
    await repo.log_event(user_id, "cooked_confirmed", {"recipe_id": recipe_id})
    
    history_records = await repo.get_history(user_id)
    last_history = history_records[0] if history_records else None
    
    text = get_text(lang, 'cooking_finished') + "\n\n" + get_text(lang, 'rate_title')
    kb = rate_kb(lang, last_history['id']) if last_history else None
    
    await callback.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data.startswith("rate_"))
async def process_rate(callback: CallbackQuery, lang: str):
    parts = callback.data.split("_")
    action = parts[1]
    history_id = int(parts[2])
    
    rating = 1 if action == "like" else 0
    await repo.rate_history(history_id, callback.fromuser.id, rating)
    await repo.log_event(callback.from_user.id, "feedback_submitted", {"history_id": history_id, "rating": rating})
    
    await callback.message.edit_text(get_text(lang, 'thanks_rate'))

@router.callback_query(F.data.startswith("fav_toggle_"))
async def process_fav_toggle(callback: CallbackQuery, lang: str):
    recipe_id = callback.data.split("fav_toggle_")[1]
    user_id = callback.from_user.id
    is_fav = await repo.toggle_favorite(user_id, recipe_id)
    
    # Reload recipe details to update button
    await process_recipe_open(callback, lang)
    
@router.message(lambda msg: msg.text in ["❤️ Обране", "❤️ Избранное"])
async def btn_favs(message: Message, lang: str):
    user_id = message.from_user.id
    favs = await repo.get_favorites(user_id)
    
    if not favs:
        await message.answer(get_text(lang, 'fav_empty'))
        return
        
    text = get_text(lang, 'fav_title') + "\n"
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb_rows = []
    for recipe_id in favs:
        recipe = catalog.get_by_id(recipe_id)
        if recipe:
            title = recipe['title'][lang]
            kb_rows.append([InlineKeyboardButton(text=title, callback_data=f"recipe_open_{recipe_id}")])
            
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
