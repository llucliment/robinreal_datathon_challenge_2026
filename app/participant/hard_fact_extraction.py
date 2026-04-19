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

# ---------------------------------------------------------------------------
# City name → all known DB spellings
# Built from actual DB values: covers umlaut/accent variants and multi-language
# names for the same city.
# ---------------------------------------------------------------------------
_CITY_DB_VARIANTS: dict[str, list[str]] = {
    # Zürich  (877 "Zürich" + 71 "Zurich" in DB)
    "zurich":       ["Zürich", "Zurich"],
    "zürich":       ["Zürich", "Zurich"],
    "zuerich":      ["Zürich", "Zurich"],
    # Geneva  (488 "Genève" + 48 "Geneva" + 40 "Genf")
    "geneva":       ["Genève", "Geneva", "Genf"],
    "genève":       ["Genève", "Geneva", "Genf"],
    "geneve":       ["Genève", "Geneva", "Genf"],
    "genf":         ["Genf", "Genève", "Geneva"],
    # Biel/Bienne  (79 "Biel/Bienne" + 23 "Biel")
    "biel":         ["Biel/Bienne", "Biel"],
    "bienne":       ["Biel/Bienne"],
    "biel/bienne":  ["Biel/Bienne", "Biel"],
    # Cities with umlauts / accents
    "neuchatel":        ["Neuchâtel"],
    "neuchâtel":        ["Neuchâtel"],
    "delemont":         ["Delémont"],
    "delémont":         ["Delémont"],
    "délémont":         ["Delémont"],
    "dubendorf":        ["Dübendorf"],
    "dübendorf":        ["Dübendorf"],
    "emmenbrucke":      ["Emmenbrücke"],
    "emmenbrücke":      ["Emmenbrücke"],
    "bulach":           ["Bülach"],
    "bülach":           ["Bülach"],
    "koniz":            ["Köniz"],
    "köniz":            ["Köniz"],
    "anzere":           ["Anzère"],
    "anzère":           ["Anzère"],
    # German/French name pairs
    "bern":             ["Bern"],
    "berne":            ["Bern"],
    "basel":            ["Basel"],
    "bale":             ["Basel"],
    "bâle":             ["Basel"],
    "lucerne":          ["Luzern"],
    "luzern":           ["Luzern"],
    "fribourg":         ["Fribourg"],
    "freiburg":         ["Fribourg"],
    "solothurn":        ["Solothurn"],
    "soleure":          ["Solothurn"],
    "chur":             ["Chur"],
    "coire":            ["Chur"],
    "st. gallen":       ["St. Gallen"],
    "st gallen":        ["St. Gallen"],
    "saint-gall":       ["St. Gallen"],
    "saint gall":       ["St. Gallen"],
    # Cities with canton suffixes in DB
    "carouge":          ["Carouge GE"],
    "renens":           ["Renens VD"],
    "wil":              ["Wil SG"],
    # Simple pass-through (no variants, but normalise spelling)
    "lausanne":         ["Lausanne"],
    "winterthur":       ["Winterthur"],
    "lugano":           ["Lugano"],
    "thun":             ["Thun"],
    "sion":             ["Sion"],
    "nyon":             ["Nyon"],
    "yverdon":          ["Yverdon-les-Bains"],
    "yverdon-les-bains":["Yverdon-les-Bains"],
    "la chaux-de-fonds":["La Chaux-de-Fonds"],
    "chaux-de-fonds":   ["La Chaux-de-Fonds"],
    "aarau":            ["Aarau"],
    "schaffhausen":     ["Schaffhausen"],
    "uster":            ["Uster"],
    "zug":              ["Zug"],
    "bellinzona":       ["Bellinzona"],
    "locarno":          ["Locarno"],
    "lugano":           ["Lugano"],
    "crans-montana":    ["Crans-Montana"],
    "montreux":         ["Montreux"],
    "vevey":            ["Vevey"],
    "morges":           ["Morges"],
    "bulle":            ["Bulle"],
    "meyrin":           ["Meyrin"],
    "vernier":          ["Vernier"],
    "grand-lancy":      ["Grand-Lancy"],
    "le locle":         ["Le Locle"],
    "porrentruy":       ["Porrentruy"],
    "monthey":          ["Monthey"],
    "martigny":         ["Martigny"],
    "payerne":          ["Payerne"],
    "olten":            ["Olten"],
    "pully":            ["Pully"],
    "prilly":           ["Prilly"],
    "allschwil":        ["Allschwil"],
    "pratteln":         ["Pratteln"],
    "dietikon":         ["Dietikon"],
    "schlieren":        ["Schlieren"],
    "adliswil":         ["Adliswil"],
    "wallisellen":      ["Wallisellen"],
    "kriens":           ["Kriens"],
    "langenthal":       ["Langenthal"],
    "grenchen":         ["Grenchen"],
    "burgdorf":         ["Burgdorf"],
    "herisau":          ["Herisau"],
    "kreuzlingen":      ["Kreuzlingen"],
    "baar":             ["Baar"],
    "mendrisio":        ["Mendrisio"],
    "chiasso":          ["Chiasso"],
    "bellinzona":       ["Bellinzona"],
    "locarno":          ["Locarno"],
    "bioggio":          ["Bioggio"],
    "zollikofen":       ["Zollikofen"],
    "gland":            ["Gland"],
    "versoix":          ["Versoix"],
    "nyon":             ["Nyon"],
    "marly":            ["Marly"],
    "crissier":         ["Crissier"],
    "bussigny":         ["Bussigny"],
    "cointrin":         ["Cointrin"],
    "le grand-saconnex":["Le Grand-Saconnex"],
    "les acacias":      ["Les Acacias"],
    "plan-les-ouates":  ["Plan-les-Ouates"],
    "weinfelden":       ["Weinfelden"],
    "frauenfeld":       ["Frauenfeld"],
    "liestal":          ["Liestal"],
    "riehen":           ["Riehen"],
    "binningen":        ["Binningen"],
    "muttenz":          ["Muttenz"],
    "münchenbuchsee":   ["Münchenbuchsee"],
    "munchenbuchsee":   ["Münchenbuchsee"],
    "zofingen":         ["Zofingen"],
    "lyss":             ["Lyss"],
    "wabern":           ["Wabern"],
    "ostermundigen":    ["Ostermundigen"],
    "biberist":         ["Biberist"],
    "aigle":            ["Aigle"],
    "satigny":          ["Satigny"],
    "ecublens":         ["Ecublens VD"],
}


def _expand_cities(cities: list[str]) -> list[str]:
    """Map any user-input city spelling to all known DB spellings for that city."""
    expanded: list[str] = []
    seen: set[str] = set()
    for city in cities:
        variants = _CITY_DB_VARIANTS.get(city.lower())
        if variants:
            for v in variants:
                if v not in seen:
                    expanded.append(v)
                    seen.add(v)
        else:
            # Unknown city: pass as-is so the SQL still gets a chance to match
            if city not in seen:
                expanded.append(city)
                seen.add(city)
    return expanded


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

    client = anthropic.Anthropic(timeout=5.0)

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
                "min_area": {
                    "type": "integer",
                    "description": "Minimum living area in square metres (e.g. 'at least 80 sqm' → 80)",
                },
                "max_area": {
                    "type": "integer",
                    "description": "Maximum living area in square metres",
                },
                "available_before": {
                    "type": "string",
                    "description": (
                        "Latest acceptable availability date in ISO format YYYY-MM-DD. "
                        "Set when the user says 'available by July 2026', 'from September', etc. "
                        "Use the first day of the stated month when only month/year is given."
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
            raw_cities: list[str] = data.get("city") or []
            return HardFilters(
                city=_expand_cities(raw_cities) or None,
                postal_code=data.get("postal_code") or None,
                canton=data.get("canton") or None,
                min_price=data.get("min_price"),
                max_price=data.get("max_price"),
                min_rooms=data.get("min_rooms"),
                max_rooms=data.get("max_rooms"),
                min_area=data.get("min_area"),
                max_area=data.get("max_area"),
                available_before=data.get("available_before"),
                features=data.get("features") or None,
                offer_type=data.get("offer_type") or "RENT",
            )

    return HardFilters(offer_type="RENT")


# ---------------------------------------------------------------------------
# Rule-based extraction (fallback)
# ---------------------------------------------------------------------------

def _extract_with_rules(query: str) -> HardFilters:
    q = query.lower()
    price = _detect_price(q)
    rooms = _detect_rooms(q)
    area = _detect_area(q)
    return HardFilters(
        city=_detect_cities(q) or None,
        postal_code=_detect_postal_codes(q) or None,
        canton=_detect_canton(q),
        min_price=price[0],
        max_price=price[1],
        min_rooms=rooms[0],
        max_rooms=rooms[1],
        min_area=area[0],
        max_area=area[1],
        available_before=_detect_available_before(q),
        features=_detect_features(q) or None,
        offer_type=_detect_offer_type(q) or "RENT",
    )


def _detect_cities(q: str) -> list[str]:
    matched = [c for c in _SWISS_CITIES if c in q]
    return _expand_cities([c.title() for c in matched])


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


_ROOM_UNIT = r"(?:room|zimmer|pièce|piece|bedroom|zi\b)"


def _detect_rooms(q: str) -> tuple[float | None, float | None]:
    # Range: "3 to 5 rooms" / "between 3 and 5 rooms" / "3-5 Zimmer"
    m = re.search(
        r"(?:between\s+)?(\d+(?:[.,]\d)?)\s*(?:to|and|bis|-)\s*(\d+(?:[.,]\d)?)"
        r"\s*[-\s]?" + _ROOM_UNIT,
        q,
    )
    if m:
        lo = float(m.group(1).replace(",", "."))
        hi = float(m.group(2).replace(",", "."))
        return lo, hi + (0.5 if hi == int(hi) else 0.0)

    # Minimum: "at least 3 rooms" / "minimum 3 bedrooms" / "mindestens 3 Zimmer"
    m = re.search(
        r"(?:at\s+least|minimum|mindestens|min\.?|au\s+moins)\s+(\d+(?:[.,]\d)?)"
        r"\s*[-\s]?" + _ROOM_UNIT,
        q,
    )
    if m:
        rooms = float(m.group(1).replace(",", "."))
        return rooms, None

    # Exact / plain "N rooms" / "N-room"
    m = re.search(r"(\d+(?:[.,]\d)?)\s*[-\s]?" + _ROOM_UNIT, q)
    if m:
        rooms = float(m.group(1).replace(",", "."))
        # Half-room specified explicitly → exact match; otherwise extend by 0.5
        if rooms != int(rooms):
            return rooms, rooms
        return rooms, rooms + 0.5

    if "studio" in q:
        return 1.0, 1.5
    return None, None


def _detect_area(q: str) -> tuple[int | None, int | None]:
    _SQM = r"(?:sqm|m²|m2|square\s+m(?:eters?|etres?)|qm)"
    min_area: int | None = None
    max_area: int | None = None

    m = re.search(
        r"(?:at\s+least|min(?:imum)?|mindestens)\s+(\d+)\s*" + _SQM, q
    )
    if m:
        min_area = int(m.group(1))

    m = re.search(
        r"(?:under|less\s+than|max(?:imum)?|up\s+to|at\s+most)\s+(\d+)\s*" + _SQM, q
    )
    if m:
        max_area = int(m.group(1))

    # Plain "80 sqm" with no qualifier → treat as minimum
    if min_area is None and max_area is None:
        m = re.search(r"(\d+)\s*" + _SQM, q)
        if m:
            min_area = int(m.group(1))

    return min_area, max_area


_MONTH_NUM: dict[str, int] = {
    "january": 1, "jan": 1, "januar": 1,
    "february": 2, "feb": 2, "februar": 2,
    "march": 3, "mar": 3, "märz": 3,
    "april": 4, "apr": 4,
    "may": 5, "mai": 5,
    "june": 6, "jun": 6, "juni": 6,
    "july": 7, "jul": 7, "juli": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9,
    "october": 10, "oct": 10, "oktober": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12, "dezember": 12,
}


def _detect_available_before(q: str) -> str | None:
    # ISO date present verbatim
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", q)
    if m:
        return m.group(1)

    # "by/from/available [in] <month> <year>" or "<month> <year>"
    month_pat = "|".join(_MONTH_NUM)
    m = re.search(
        rf"(?:by|from|available(?:\s+from)?|ab|bis|dès|dès le)?\s*(?:in\s+)?({month_pat})\s+(\d{{4}})",
        q,
    )
    if m:
        month_num = _MONTH_NUM[m.group(1)]
        return f"{m.group(2)}-{month_num:02d}-01"

    return None


def _detect_features(q: str) -> list[str]:
    return [feat for feat, kws in _FEATURE_KEYWORDS.items() if any(kw in q for kw in kws)]


def _detect_offer_type(q: str) -> str | None:
    if any(w in q for w in ["rent", "miete", "mieten", "louer", "location"]):
        return "RENT"
    if any(w in q for w in ["buy", "sale", "kaufen", "kauf", "acheter", "for sale"]):
        return "SALE"
    return None
