from copy import deepcopy
import pytest
from app.services.planner import (
    defaults,
    identify,
    parse,
    rank,
    make_plan,
    replacement,
    groceries,
    eligible,
)
from app.services.recipe_data import RECIPES, INGREDIENTS
from app.locales.manager import detect_language


@pytest.mark.parametrize(
    "code,expected",
    [
        ("uk", "uk"),
        ("uk-UA", "uk"),
        ("ru", "ru"),
        ("ru-RU", "ru"),
        ("en", "uk"),
        (None, "uk"),
    ],
)
def test_language(code, expected):
    assert detect_language(code) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("картошка, яйца, сыр", {"potato", "egg", "cheese"}),
        ("картопля, яйця, курка", {"potato", "egg", "chicken"}),
        ("помидоры, огурцы, фета", {"tomato", "cucumber", "feta"}),
        ("", set()),
    ],
)
def test_ingredient_recognition(text, expected):
    assert set(identify(text)) == expected


def test_parser_conditions_and_pantry_separation():
    p = parse("Картошка, яйца. На 4, максимум 30 минут, без духовки", defaults())
    assert p["portions"] == 4 and p["minutes"] == 30
    assert "oven" not in p["equipment"]
    assert p["pantry"] == ["egg", "potato"]


def test_catalog_has_real_unique_recipes():
    assert len(RECIPES) == 36
    assert len({r["id"] for r in RECIPES}) == 36
    assert len({r["title"]["ru"] for r in RECIPES}) == 36
    for r in RECIPES:
        assert r["ingredients"] and r["steps"]["ru"] and r["steps"]["uk"]
        assert not r["title"]["ru"].startswith("Рецепт ")
        for i in r["ingredients"]:
            assert i["amount"] > 0 and i["id"] in INGREDIENTS
        expected = {INGREDIENTS[i["id"]][4] for i in r["ingredients"]} - {""}
        assert set(r["allergens"]) == expected


def test_strict_allergy_time_equipment_and_exclusion_filters():
    p = defaults()
    p.update(
        minutes=30,
        equipment=["stove"],
        allergens=["milk", "egg"],
        exclude=["tomato"],
        vegetarian=True,
    )
    for r in eligible(p):
        assert not set(r["allergens"]) & {"milk", "egg"}
        assert (
            r["vegetarian"]
            and r["total_time"] <= 30
            and set(r["equipment"]) <= {"stove"}
        )
        assert "tomato" not in {i["id"] for i in r["ingredients"]}


def test_ranking_does_not_recommend_unrelated_food():
    p = defaults()
    p["pantry"] = ["chicken"]
    result = rank(p)
    assert result and all(
        "chicken" in {i["id"] for i in r["ingredients"]} for r in result
    )


@pytest.mark.parametrize("mode", ["compact", "variety"])
@pytest.mark.parametrize("days", [3, 5, 7])
def test_plan_distinct_and_valid(mode, days):
    p = defaults()
    p["allergens"] = ["milk"]
    p["exclude"] = ["fish"]
    before = deepcopy(p)
    plan = make_plan(p, days, mode)
    assert p == before
    assert len(set(plan["recipes"])) == days
    assert set(plan["recipes"]) <= {r["id"] for r in eligible(p)}
    swap = replacement(plan, 0)
    assert swap not in plan["recipes"]


def test_impossible_plan_does_not_relax_restrictions():
    p = defaults()
    p["minutes"] = 1
    with pytest.raises(ValueError):
        make_plan(p, 7, "compact")


def test_shopping_aggregates_and_scales():
    items = {i["id"]: i for i in groceries(["eggs_1", "omelet_1"], 4)}
    assert items["egg"]["amount"] == 16
    assert items["oil"]["amount"] == 30
    assert items["tomato"]["amount"] == 500
