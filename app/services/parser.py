import re
from typing import Dict, Any


def parse_input(text: str) -> Dict[str, Any]:
    text = text.lower()

    result = {
        "ingredients": [],
        "portions": None,
        "max_time": None,
        "equipment": ["плита"],  # Default assumption
        "no_equipment": [],
    }

    # Parse portions
    port_match = re.search(r"на (\d+)", text)
    if port_match:
        result["portions"] = int(port_match.group(1))
    elif "на двох" in text or "на двоих" in text or "на 2" in text:
        result["portions"] = 2
    elif "на трьох" in text or "на троих" in text or "на 3" in text:
        result["portions"] = 3
    elif "на чотирьох" in text or "на четверых" in text or "на 4" in text:
        result["portions"] = 4

    # Parse time
    time_match = re.search(r"(\d+) (хвил|мин)", text)
    if time_match:
        result["max_time"] = int(time_match.group(1))

    # Parse equipment
    if "без духовк" in text or "духовки немає" in text or "духовки нет" in text:
        if "духовка" in result["equipment"]:
            result["equipment"].remove("духовка")
    elif "духовк" in text:
        if "духовка" not in result["equipment"]:
            result["equipment"].append("духовка")

    # Parse ingredients
    text = re.sub(r"на \S+.*?($|[,\.])", "", text)
    text = re.sub(r"\d+ (хвил|мин).*?($|[,\.])", "", text)
    text = re.sub(r"без духовк.*?($|[,\.])", "", text)
    text = re.sub(r"духовки немає.*?($|[,\.])", "", text)
    text = re.sub(r"духовки нет.*?($|[,\.])", "", text)
    text = re.sub(r"максимум.*?\d+.*?($|[,\.])", "", text)

    text = (
        text.replace("є ", "")
        .replace("есть ", "")
        .replace(" и ", ",")
        .replace(" та ", ",")
    )
    parts = [p.strip() for p in re.split(r"[,;.]", text) if p.strip()]
    if not parts or len(parts) == 1 and " " in parts[0]:
        parts = [p.strip() for p in parts[0].split() if len(p.strip()) > 2]

    result["ingredients"] = [p for p in parts if len(p) > 2]

    return result
