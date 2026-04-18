from __future__ import annotations

import re
from typing import Any

from app.models.schemas import HardFilters

# ---------------------------------------------------------------------------
# Feature keyword lookup for the rule-based fallback
# ---------------------------------------------------------------------------
_FEATURE_KEYWORDS: dict[str, list[str]] = {
    "balcony": ["balcony", "balcon", "balkon", "terrace", "terrasse", "terrazza"],
    "elevator": ["elevator", "lift", "aufzug", "ascenseur"],
    "parking": ["parking", "parkplatz", "stellplatz"],
    "garage": ["garage"],
    "fireplace": ["fireplace", "kamin", "cheminée", "cheminee"],
    "child_friendly": ["child-friendly", "child friendly", "family-friendly", "family friendly", "kinderfreundlich"],
    "pets_allowed": ["pets allowed", "pet-friendly", "pet friendly", "haustiere", "animaux"],
    "new_build": ["new build", "neubau", "new construction"],
    "wheelchair_accessible": ["wheelchair", "rollstuhl", "barrierfrei"],
    "private_laundry": ["laundry", "washing machine", "waschmaschine"],
    "minergie_certified": ["minergie"],
}

_SWISS_CITIES: set[str] = {
    "zurich", "zürich", "geneva", "genève", "genf", "basel", "bern", "berne",
    "lausanne", "winterthur", "lucerne", "luzern", "st. gallen", "st gallen",
    "lugano", "biel", "bienne", "thun", "schaffhausen", "fribourg", "freiburg",
    "chur", "neuchâtel", "neuchatel", "sion", "zug", "uster", "aarau",
}

_CANTON_CODES: set[str] = {
    "zh", "ge", "be", "bs", "bl", "ag", "sg", "ti", "vs", "lu",
    "zg", "fr", "ne", "vd", "gr", "so", "sz", "ar", "ai", "gl",
    "sh", "tg", "ur", "ow", "nw", "ju",
}

_CANTON_NAMES: dict[str, str] = {
    "zurich": "ZH", "zürich": "ZH",
    "geneva": "GE", "genève": "GE", "genf": "GE",
    "bern": "BE", "berne": "BE",
    "vaud": "VD", "waadt": "VD",
    "aargau": "AG",
    "st. gallen": "SG", "st gallen": "SG",
    "ticino": "TI", "tessin": "TI",
    "valais": "VS", "wallis": "VS",
    "lucerne": "LU", "luzern": "LU",
    "zug": "ZG",
    "fribourg": "FR", "freiburg": "FR",
    "neuchâtel": "NE", "neuchatel": "NE",
}

_LLM_FEATURES = [
    "balcony", "elevator", "parking", "garage", "fireplace",
    "child_friendly", "pets_allowed", "new_build",
    "wheelchair_accessible", "private_laundry", "minergie_certified",
]


def extract_hard_facts(query: str) -> HardFilters:
    try:
        return _extract_with_llm(query)
    except Exception:
        return _extract_with_rules(query)


# ---------------------------------------------------------------------------
# LLM-based extraction (primary)
# ---------------------------------------------------------------------------

def _extract_with_llm(query: str) -> HardFilters:
    import anthropic

    client = anthropic.Anthropic()

    tool = {
        "name": "set_hard_filters",
        "description": (
            "Record the hard constraints from a Swiss real-estate search query. "
            "Only include fields the user explicitly requires."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Swiss city names required by the user (standard spelling)",
                },
                "postal_code": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Swiss 4-digit postal codes explicitly stated as a location "
                        "(e.g. 'PLZ 8001', 'postal code 8050'). "
                        "NEVER extract price amounts (e.g. '2800 CHF'), room counts, "
                        "or years as postal codes."
                    ),
                },
                "canton": {
                    "type": "string",
                    "description": "Swiss canton abbreviation if explicitly stated (e.g. 'ZH', 'GE')",
                },
                "min_price": {
                    "type": "integer",
                    "description": "Minimum price in CHF",
                },
                "max_price": {
                    "type": "integer",
                    "description": "Maximum price in CHF (e.g. 'under 2800 CHF' → 2800)",
                },
                "min_rooms": {
                    "type": "number",
                    "description": "Minimum rooms. A studio = 1. '3 rooms' → 3.0.",
                },
                "max_rooms": {
                    "type": "number",
                    "description": (
                        "Maximum rooms. '3 rooms' → 3.5 (Swiss half-room convention). "
                        "'4 rooms' → 4.5. Only set equal to min_rooms if the user "
                        "specifies an exact half-room value like '3.5-Zimmer'."
                    ),
                },
                "features": {
                    "type": "array",
                    "items": {"type": "string", "enum": _LLM_FEATURES},
                    "description": "Amenities the user explicitly requires (not just prefers)",
                },
                "offer_type": {
                    "type": "string",
                    "enum": ["RENT", "SALE"],
                    "description": "Rent or buy intent",
                },
            },
            "required": [],
        },
    }

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=(
            "You extract hard constraints from Swiss real-estate search queries. "
            "Hard constraints are strict requirements: city, price limits, room count, "
            "required amenities, rent vs buy. "
            "Do NOT extract soft preferences such as 'bright', 'modern', 'quiet', "
            "'nice views', 'good transport', 'close to schools' — those are ranking "
            "signals, not filters. Only set a field when the user clearly requires it.\n\n"
            "IMPORTANT — Swiss room convention: listings use half-room increments "
            "(1.5, 2.5, 3.5, 4.5 Zimmer). When a user says '3 rooms' or '3-room', "
            "set min_rooms=3.0 and max_rooms=3.5 to include standard 3.5-Zimmer flats. "
            "When a user says '4 rooms', set min_rooms=4.0 and max_rooms=4.5. "
            "Only set max_rooms strictly equal to min_rooms if the user explicitly "
            "says 'exactly' or specifies a half-room themselves (e.g. '3.5-Zimmer')."
        ),
        tools=[tool],
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": query}],
    )

    for block in response.content:
        if block.type == "tool_use":
            data: dict[str, Any] = block.input
            return HardFilters(
                city=data.get("city") or None,
                postal_code=data.get("postal_code") or None,
                canton=data.get("canton") or None,
                min_price=data.get("min_price"),
                max_price=data.get("max_price"),
                min_rooms=data.get("min_rooms"),
                max_rooms=data.get("max_rooms"),
                features=data.get("features") or None,
                offer_type=data.get("offer_type"),
            )

    return HardFilters()


# ---------------------------------------------------------------------------
# Rule-based extraction (fallback)
# ---------------------------------------------------------------------------

def _extract_with_rules(query: str) -> HardFilters:
    q = query.lower()
    return HardFilters(
        city=_detect_cities(q) or None,
        postal_code=_detect_postal_codes(q) or None,
        canton=_detect_canton(q),
        min_price=_detect_price(q)[0],
        max_price=_detect_price(q)[1],
        min_rooms=_detect_rooms(q)[0],
        max_rooms=_detect_rooms(q)[1],
        features=_detect_features(q) or None,
        offer_type=_detect_offer_type(q),
    )


def _detect_cities(q: str) -> list[str]:
    return [c.title() for c in _SWISS_CITIES if c in q]


def _detect_postal_codes(q: str) -> list[str]:
    # Strip price amounts before scanning so "under 2800 CHF" doesn't yield postal code 2800
    q_clean = re.sub(r"\d[\d\s']*\s*(?:chf|fr\.?|francs?|franken)\b", "", q, flags=re.IGNORECASE)
    q_clean = re.sub(r"(?:chf|fr\.?)\s*\d[\d\s']*", "", q_clean, flags=re.IGNORECASE)
    q_clean = re.sub(
        r"(?:under|over|max(?:imum)?|min(?:imum)?|up\s+to|at\s+most|at\s+least|"
        r"bis(?:zu)?|ab|unter|über|mindestens)\s+\d+",
        "",
        q_clean,
        flags=re.IGNORECASE,
    )
    candidates = re.findall(r"\b(\d{4})\b", q_clean)
    return [c for c in candidates if 1000 <= int(c) <= 9999]


def _detect_canton(q: str) -> str | None:
    for name, code in _CANTON_NAMES.items():
        if name in q:
            return code
    match = re.search(r"\b(" + "|".join(_CANTON_CODES) + r")\b", q)
    return match.group(1).upper() if match else None


def _detect_price(q: str) -> tuple[int | None, int | None]:
    min_price: int | None = None
    max_price: int | None = None

    def parse_int(s: str) -> int:
        return int(s.replace("'", "").replace(" ", ""))

    m = re.search(
        r"(?:under|less\s+than|fewer\s+than|no\s+more\s+than|not\s+more\s+than"
        r"|max(?:imum)?|up\s+to|bis(?:zu)?|at\s+most)\s*(?:chf\s*)?(\d[\d\s']*)",
        q,
    )
    if m:
        max_price = parse_int(m.group(1))

    m = re.search(
        r"(?:at\s+least|from|min(?:imum)?|ab|mindestens)\s*(?:chf\s*)?(\d[\d\s']*)",
        q,
    )
    if m:
        min_price = parse_int(m.group(1))

    if min_price is None and max_price is None:
        m = re.search(r"(?:chf\s*)?(\d[\d\s']*)\s*[-–]\s*(\d[\d\s']*)\s*(?:chf)?", q)
        if m:
            min_price = parse_int(m.group(1))
            max_price = parse_int(m.group(2))

    return min_price, max_price


def _detect_rooms(q: str) -> tuple[float | None, float | None]:
    m = re.search(r"(\d+(?:[.,]\d)?)\s*[-\s]?(?:room|zimmer|pièce|piece|zi\b)", q)
    if m:
        rooms = float(m.group(1).replace(",", "."))
        # If the user specified a half-room themselves (e.g. "3.5-Zimmer"), use exact.
        # Otherwise add 0.5 to max to cover Swiss half-room listings (3.5-Zimmer for a
        # "3-room" request, 4.5-Zimmer for a "4-room" request, etc.)
        if rooms != int(rooms):
            return rooms, rooms
        return rooms, rooms + 0.5
    if "studio" in q:
        return 1.0, 1.5
    return None, None


def _detect_features(q: str) -> list[str]:
    return [feat for feat, kws in _FEATURE_KEYWORDS.items() if any(kw in q for kw in kws)]


def _detect_offer_type(q: str) -> str | None:
    if any(w in q for w in ["rent", "miete", "mieten", "louer", "location"]):
        return "RENT"
    if any(w in q for w in ["buy", "sale", "kaufen", "kauf", "acheter", "for sale"]):
        return "SALE"
    return None
