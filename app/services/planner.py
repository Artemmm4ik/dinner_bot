import re
from collections import Counter
from copy import deepcopy
from app.services.recipe_data import INGREDIENTS, RECIPES


def identify(text):
    text = text.lower().replace("ё", "е")
    return [
        key
        for key, data in INGREDIENTS.items()
        if re.search(r"\b(?:" + data[2] + r")\w*", text)
    ]


def defaults():
    return dict(
        portions=2,
        minutes=60,
        equipment=["stove", "oven", "kettle"],
        vegetarian=False,
        exclude=[],
        allergens=[],
        priority=[],
        pantry=[],
    )


def parse(text, profile):
    result = deepcopy(profile)
    # Only the ingredient segment, before a full stop or semicolon, describes the pantry.
    result["pantry"] = identify(re.split(r"[.;\n]", text, maxsplit=1)[0])
    m = re.search(r"(?:на|для)\s+(\d{1,2})\b", text.lower())
    if m:
        result["portions"] = min(8, max(1, int(m[1])))
    m = re.search(r"(\d{1,3})\s*(?:мин|хв)", text.lower())
    if m:
        result["minutes"] = min(180, max(5, int(m[1])))
    if re.search(r"без духов|духов\w* (?:нет|немає)", text.lower()):
        result["equipment"] = [e for e in result["equipment"] if e != "oven"]
    return result


def eligible(profile):
    out = []
    for r in RECIPES:
        ids = {i["id"] for i in r["ingredients"]}
        if r["total_time"] > profile["minutes"] or not set(r["equipment"]) <= set(
            profile["equipment"]
        ):
            continue
        if profile["vegetarian"] and not r["vegetarian"]:
            continue
        if ids & set(profile["exclude"]) or set(r["allergens"]) & set(
            profile["allergens"]
        ):
            continue
        out.append(r)
    return out


def rank(profile):
    pantry = set(profile["pantry"])
    priority = set(profile["priority"])

    def score(r):
        ids = {i["id"] for i in r["ingredients"]}
        return (
            -len(ids & priority),
            len(ids - pantry),
            -len(ids & pantry),
            r["total_time"],
            r["id"],
        )

    candidates = eligible(profile)
    # If products were supplied, show at least one meaningful match, ignoring oil alone.
    if pantry:
        candidates = [
            r
            for r in candidates
            if ({i["id"] for i in r["ingredients"]} & pantry) - {"oil"}
        ]
    return sorted(candidates, key=score)


def make_plan(profile, days, mode, avoid=()):
    if days not in (3, 5, 7) or mode not in ("compact", "variety"):
        raise ValueError("Invalid plan options")
    pool = eligible(profile)
    if len(pool) < days:
        raise ValueError("Not enough recipes with these restrictions")
    selected, used, families = [], set(profile["pantry"]), Counter()
    for _ in range(days):

        def score(r):
            ids = {i["id"] for i in r["ingredients"]}
            priority = len(ids & set(profile["priority"]))
            if mode == "compact":
                return (
                    r["id"] in avoid,
                    len(ids - used) - 2 * priority,
                    families[r["family"]],
                    r["total_time"],
                    r["id"],
                )
            return (
                r["id"] in avoid,
                families[r["family"]],
                -priority,
                len(ids - used),
                r["id"],
            )

        chosen = min(pool, key=score)
        pool.remove(chosen)
        selected.append(chosen["id"])
        used.update(i["id"] for i in chosen["ingredients"])
        families[chosen["family"]] += 1
    return dict(profile=deepcopy(profile), mode=mode, recipes=selected)


def replacement(body, index):
    choices = [r for r in eligible(body["profile"]) if r["id"] not in body["recipes"]]
    if not choices:
        return None
    rest = [
        r
        for r in RECIPES
        if r["id"] in body["recipes"] and r["id"] != body["recipes"][index]
    ]
    used = {i["id"] for r in rest for i in r["ingredients"]} | set(
        body["profile"]["pantry"]
    )
    families = Counter(r["family"] for r in rest)

    def score(r):
        missing = len({i["id"] for i in r["ingredients"]} - used)
        return (
            (missing, families[r["family"]], r["id"])
            if body["mode"] == "compact"
            else (families[r["family"]], missing, r["id"])
        )

    return min(choices, key=score)["id"]


def groceries(recipes, portions):
    result = {}
    for rid in recipes:
        r = next(r for r in RECIPES if r["id"] == rid)
        for item in r["ingredients"]:
            key = (item["id"], item["unit"])
            result.setdefault(key, dict(item, amount=0))
            result[key]["amount"] += item["amount"] * portions / r["portions"]
    # Whole eggs are purchased as whole items; round only after aggregation.
    import math

    for item in result.values():
        if item["unit"] == "шт":
            item["amount"] = math.ceil(item["amount"])
        else:
            item["amount"] = round(item["amount"], 1)
    return list(result.values())
