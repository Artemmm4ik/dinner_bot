from typing import List, Dict, Any

def match_recipes(
    user_ingredients: List[str], 
    max_time: int | None, 
    equipment: List[str],
    excluded: List[str],
    vegetarian: bool,
    catalog: List[Dict[str, Any]],
    lang: str = 'uk'
) -> List[Dict[str, Any]]:
    results = []
    
    for r in catalog:
        # Check hard constraints
        if max_time and r['total_time'] > max_time:
            continue
            
        if vegetarian and not r['vegetarian']:
            continue
            
        # Check equipment
        req_equipment = r.get('equipment', [])
        if any(eq not in equipment for eq in req_equipment):
            continue
            
        # Check excluded ingredients
        recipe_ing_names = [i[f'name_{lang}'].lower() for i in r['ingredients']]
        if any(ex in recipe_ing_names for ex in excluded):
            continue
            
        # Match ingredients
        missing = []
        user_ings_lower = [ui.lower() for ui in user_ingredients]
        for ing in r['ingredients']:
            if ing['req']:
                name = ing[f'name_{lang}'].lower()
                # Simple substring match
                if not any(name in ui or ui in name for ui in user_ings_lower):
                    missing.append(ing[f'name_{lang}'])
        
        # We allow up to 2 missing required ingredients
        if len(missing) <= 2:
            r_copy = dict(r)
            r_copy['missing_count'] = len(missing)
            r_copy['missing_names'] = missing
            results.append(r_copy)
            
    # Sort by minimum missing, then by time
    results.sort(key=lambda x: (x['missing_count'], x['total_time']))
    return results[:3]
