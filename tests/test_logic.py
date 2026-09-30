import pytest
from app.services.parser import parse_input
from app.services.matcher import match_recipes
from app.services.recipe_catalog import catalog
from app.locales.manager import detect_language

def test_language_detection():
    assert detect_language('uk') == 'uk'
    assert detect_language('uk-UA') == 'uk'
    assert detect_language('ru') == 'ru'
    assert detect_language('ru-RU') == 'ru'
    assert detect_language('en') == 'uk'  # default fallback
    assert detect_language(None) == 'uk'

def test_parser_basic():
    text = "Є картопля, яйця, сир і курка. На двох, максимум 25 хвилин, духовки немає."
    res = parse_input(text)
    assert res['portions'] == 2
    assert res['max_time'] == 25
    assert "духовка" not in res['equipment']
    assert "картопля" in res['ingredients']
    assert "яйця" in res['ingredients']

def test_parser_ru():
    text = "Есть картошка, яйца, сыр. На 4, максимум 30 минут, без духовки"
    res = parse_input(text)
    assert res['portions'] == 4
    assert res['max_time'] == 30
    assert "картошка" in res['ingredients']
    assert "яйца" in res['ingredients']
    
def test_matcher():
    recipes = [
        {
            "id": "1",
            "title": {"uk": "Тест 1", "ru": "Тест 1"},
            "total_time": 20,
            "vegetarian": True,
            "equipment": ["плита"],
            "ingredients": [
                {"req": True, "name_uk": "картопля", "name_ru": "картошка"},
                {"req": True, "name_uk": "яйце", "name_ru": "яйцо"}
            ]
        },
        {
            "id": "2",
            "title": {"uk": "Тест 2", "ru": "Тест 2"},
            "total_time": 40,
            "vegetarian": False,
            "equipment": ["духовка"],
            "ingredients": [
                {"req": True, "name_uk": "курка", "name_ru": "курица"}
            ]
        }
    ]
    
    # Test time limit
    res1 = match_recipes(["картопля", "яйце"], max_time=25, equipment=["плита", "духовка"], excluded=[], vegetarian=False, catalog=recipes, lang='uk')
    assert len(res1) == 1
    assert res1[0]['id'] == "1"
    
    # Test equipment limit
    res2 = match_recipes(["курка"], max_time=50, equipment=["плита"], excluded=[], vegetarian=False, catalog=recipes, lang='uk')
    assert len(res2) == 1  # No oven

    # Test vegetarian limit
    res3 = match_recipes(["курка"], max_time=50, equipment=["плита", "духовка"], excluded=[], vegetarian=True, catalog=recipes, lang='uk')
    assert len(res3) == 1  # Not vegetarian
    
def test_catalog_validity():
    all_recipes = catalog.get_all()
    assert len(all_recipes) == 30
    for r in all_recipes:
        assert 'id' in r
        assert 'title' in r and 'uk' in r['title'] and 'ru' in r['title']
        assert 'ingredients' in r
        assert 'steps' in r and 'uk' in r['steps']
