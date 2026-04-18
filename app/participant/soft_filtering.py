from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Any

import httpx

from app.models.schemas import SoftCriteria

# ---------------------------------------------------------------------------
# Word sets for semantic routing
# ---------------------------------------------------------------------------

_CHEAP_WORDS = {
    "cheap", "affordable", "budget", "inexpensive", "low-cost", "low cost",
    "günstig", "preiswert", "économique", "bon marché",
}
_EXPENSIVE_WORDS = {
    "luxury", "premium", "high-end", "upscale", "exclusive",
    "luxuriös", "exklusiv", "luxueux",
}
_TRANSPORT_WORDS = {"transport", "transit", "tram", "bus", "train", "station", "metro", "subway", "sbahn", "ubahn"}
_SHOP_WORDS = {"shop", "store", "supermarket", "grocery", "market", "einkauf"}
_SCHOOL_WORDS = {"school", "schule", "école", "gymnasium", "education"}
_KINDERGARTEN_WORDS = {"kindergarten", "daycare", "nursery", "kita", "crèche"}
_PROXIMITY_WORDS = {"near", "close", "walk", "commute", "distance", "proximity", "minutes"}

# ---------------------------------------------------------------------------
# Multilingual synonym map — EN / DE / FR, including inflected forms.
# Each key is the canonical label; values are all substrings to look for.
# ---------------------------------------------------------------------------
_SYNONYMS: dict[str, list[str]] = {
    "bright": [
        # English
        "bright", "well-lit", "well lit", "sunny", "light-filled", "light filled",
        "sun-drenched", "luminous",
        # German (base + common inflections)
        "hell", "helle", "hellen", "heller", "helles",
        "licht", "lichte", "lichten", "lichter", "lichtes",
        "sonnig", "sonnige", "sonnigen", "sonniger",
        "lichtdurchflutet", "sonnendurchflutet", "lichtdurchflutete",
        # French
        "lumineux", "lumineuse", "ensoleillé", "ensoleillée",
        "clair", "claire", "bien éclairé", "bien eclaire",
    ],
    "modern": [
        # English
        "modern", "contemporary", "updated", "fresh",
        # German
        "modern", "moderne", "modernen", "moderner", "modernes",
        "zeitgemäss", "zeitgemäß", "aktuell", "aktuelle",
        # French
        "moderne", "récent", "récente", "actuel", "actuelle", "contemporain",
    ],
    "renovated": [
        # English
        "renovated", "refurbished", "restored", "new kitchen", "new bathroom",
        # German
        "renoviert", "renovierte", "renovierten",
        "saniert", "sanierte", "sanierten", "kernsaniert",
        "neuwertig", "erstbezug", "komplett renoviert",
        # French
        "rénové", "rénovée", "restauré", "restaurée", "remis à neuf",
    ],
    "quiet": [
        # English
        "quiet", "calm", "peaceful", "silent", "tranquil", "serene",
        # German
        "ruhig", "ruhige", "ruhigen", "ruhiger",
        "still", "stille", "leise", "geräuscharm",
        # French
        "calme", "tranquille", "paisible", "silencieux", "silencieuse",
    ],
    "spacious": [
        # English
        "spacious", "roomy", "generous", "large", "big",
        # German
        "geräumig", "geräumige", "geräumigen",
        "großzügig", "großzügige", "grosszügig", "grosszügige",
        "weitläufig", "weiträumig",
        # French
        "spacieux", "spacieuse", "grand", "grande", "vaste",
    ],
    "cozy": [
        # English
        "cozy", "cosy", "charming", "warm", "inviting", "homely",
        # German
        "gemütlich", "gemütliche", "gemütlichen",
        "heimelig", "wohnlich", "charmant", "charmante",
        # French
        "confortable", "douillet", "douillette", "charmant", "charmante",
    ],
    "family-friendly": [
        # English
        "family", "children", "kids", "playground", "child-friendly",
        # German
        "familie", "familien", "kinder", "kindgerecht",
        "spielplatz", "familienfreundlich", "kinderfreundlich",
        # French
        "famille", "enfants", "familial", "familiale", "aire de jeux",
    ],
    "views": [
        # English
        "view", "views", "panorama", "scenery", "mountains", "lake view", "city view",
        # German
        "aussicht", "ausblick", "panorama",
        "bergblick", "seeblick", "weitblick", "fernsicht",
        # French
        "vue", "panoramique", "vue sur le lac", "vue sur les montagnes",
    ],
    "garden": [
        # English
        "garden", "yard", "outdoor", "green space",
        # German
        "garten", "gartensitz", "gartenanteil",
        "sitzplatz", "grünfläche", "grünanlage", "aussenbereich",
        # French
        "jardin", "espace vert", "extérieur", "terrasse",
    ],
    "new build": [
        # English
        "new build", "new construction", "newly built", "brand new",
        # German
        "neubau", "neubauwohnung", "erstbezug", "neuwertig",
        # French
        "construction neuve", "neuf", "neuve",
    ],
    "pet-friendly": [
        # English
        "pet", "dog", "cat", "animal", "pets allowed",
        # German
        "haustier", "haustiere", "hund", "katze",
        "tier", "haustiererlaubt", "haustiere erlaubt",
        # French
        "animaux", "animal", "chien", "chat", "animaux admis",
    ],
    "parking": [
        # English
        "parking", "car space", "garage",
        # German
        "parkplatz", "stellplatz", "tiefgarage", "einstellplatz", "autoabstellplatz",
        # French
        "parking", "place de parc", "garage",
    ],
    "affordable": [
        # English
        "affordable", "cheap", "budget", "good value", "reasonable", "low cost",
        # German
        "günstig", "günstige", "preiswert", "erschwinglich",
        # French
        "abordable", "économique", "bon marché",
    ],
    "luxury": [
        # English
        "luxury", "premium", "high-end", "upscale", "exclusive",
        # German
        "luxus", "exklusiv", "exklusive", "hochwertig", "hochwertige",
        # French
        "luxueux", "luxueuse", "prestige", "haut de gamme",
    ],
    "balcony": [
        # English/multilingual — also a structured feature but text confirms it
        "balcony", "balcon", "balkon", "terrasse", "terrassa", "loggia",
    ],
    "elevator": [
        "elevator", "lift", "aufzug", "ascenseur",
    ],
    "fireplace": [
        "fireplace", "kamin", "cheminée", "cheminee", "offener kamin",
    ],
}

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_NOMINATIM_HEADERS = {"User-Agent": "datathon2026-robinreal/1.0 (educational, non-commercial)"}

_TRANSIT_API = "https://transport.opendata.ch/v1"

# Distance at which proximity score reaches 0.
# 30 km covers most Swiss commuting zones.
_PROXIMITY_MAX_KM = 30.0

# Transit scoring: 0–20 min → 1.0; 60 min → 0.0
_TRANSIT_IDEAL_MINUTES = 20.0
_TRANSIT_MAX_MINUTES = 60.0

# Only fetch transit times for the N closest candidates (by haversine) to limit API calls.
_MAX_TRANSIT_CANDIDATES = 40

# Structured field thresholds (distances are in metres in the DB)
_TRANSPORT_THRESH_M = 1000.0
_SHOP_THRESH_M = 500.0
_SCHOOL_THRESH_M = 800.0
_KINDERGARTEN_THRESH_M = 600.0


# ---------------------------------------------------------------------------
# Swiss public transport — transport.opendata.ch
# ---------------------------------------------------------------------------

@lru_cache(maxsize=512)
def _nearest_station_name(lat: float, lon: float) -> str | None:
    """Return the name of the nearest Swiss public transport station."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(
                f"{_TRANSIT_API}/locations",
                params={"x": lon, "y": lat, "type": "station"},
            )
            stations = resp.json().get("stations", [])
            if stations and stations[0].get("name"):
                return stations[0]["name"]
    except Exception:
        pass
    return None


@lru_cache(maxsize=2048)
def _transit_minutes(from_station: str, to_station: str) -> float | None:
    """Return travel time in minutes between two stations, or None on failure."""
    if from_station == to_station:
        return 0.0
    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.get(
                f"{_TRANSIT_API}/connections",
                params={"from": from_station, "to": to_station, "limit": 1},
            )
            connections = resp.json().get("connections", [])
            if not connections:
                return None
            duration: str = connections[0].get("duration", "")
            # Format: "00d00:45:00"
            time_part = duration.split("d")[-1] if "d" in duration else duration
            parts = time_part.split(":")
            return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        pass
    return None


def _transit_score(minutes: float) -> float:
    if minutes <= _TRANSIT_IDEAL_MINUTES:
        return 1.0
    if minutes >= _TRANSIT_MAX_MINUTES:
        return 0.0
    return 1.0 - (minutes - _TRANSIT_IDEAL_MINUTES) / (_TRANSIT_MAX_MINUTES - _TRANSIT_IDEAL_MINUTES)


def _compute_transit_scores(
    candidates: list[dict[str, Any]],
    landmark_coords: tuple[float, float],
    landmark_station: str,
) -> dict[str, tuple[float, float | None]]:
    """Return {listing_id: (score, minutes|None)} for top N candidates by haversine distance."""
    with_dist = [
        (_haversine(landmark_coords[0], landmark_coords[1], float(c["latitude"]), float(c["longitude"])), c)
        for c in candidates
        if c.get("latitude") is not None and c.get("longitude") is not None
    ]
    with_dist.sort(key=lambda x: x[0])
    top = with_dist[:_MAX_TRANSIT_CANDIDATES]

    def _score_one(item: tuple) -> tuple[str, float, float | None]:
        dist_km, c = item
        station = _nearest_station_name(float(c["latitude"]), float(c["longitude"]))
        if station:
            minutes = _transit_minutes(station, landmark_station)
            if minutes is not None:
                return c["listing_id"], _transit_score(minutes), minutes
        return c["listing_id"], max(0.0, 1.0 - dist_km / _PROXIMITY_MAX_KM), None

    scores: dict[str, tuple[float, float | None]] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for listing_id, score, minutes in pool.map(_score_one, top):
            scores[listing_id] = (score, minutes)
    return scores


def _extract_feature_tags(listing: dict[str, Any]) -> set[str]:
    """
    Pre-compute which canonical soft-feature labels are present in a listing.
    Done once per listing so _score_preference doesn't redo the substring scan
    for every preference query.
    """
    text = _listing_text(listing)
    tags: set[str] = set()
    for tag, synonyms in _SYNONYMS.items():
        if tag in text or any(s in text for s in synonyms):
            tags.add(tag)
    return tags


def filter_soft_facts(
    candidates: list[dict[str, Any]],
    soft_facts: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Annotate every candidate with a ``soft_scores`` dict that measures how
    well it satisfies each soft preference. No candidate is removed.

    The scores are consumed by ranking.py to produce the final ordered list.
    """
    if not candidates:
        return candidates

    try:
        criteria = SoftCriteria(**soft_facts)
    except Exception:
        criteria = SoftCriteria(raw_query=soft_facts.get("raw_query", ""))

    # Nothing to score
    if not criteria.preferences and not criteria.target_landmark and not criteria.negative_signals:
        return candidates

    price_stats = _compute_price_stats(candidates)
    landmark_coords = _geocode_landmark(criteria.target_landmark) if criteria.target_landmark else None

    transit_scores: dict[str, float] = {}
    if landmark_coords:
        landmark_station = _nearest_station_name(landmark_coords[0], landmark_coords[1])
        if landmark_station:
            transit_scores = _compute_transit_scores(candidates, landmark_coords, landmark_station)

    for listing in candidates:
        listing["_feature_tags"] = _extract_feature_tags(listing)
        listing["soft_scores"] = _score_listing(listing, criteria, price_stats, landmark_coords, transit_scores)

    # Always add a price_value score so ranking can use it as a tiebreaker
    for listing in candidates:
        listing["soft_scores"]["price_value"] = _price_affordability_score(
            listing.get("price"), price_stats
        )

    return candidates


# ---------------------------------------------------------------------------
# Per-listing scoring
# ---------------------------------------------------------------------------

def _score_listing(
    listing: dict[str, Any],
    criteria: SoftCriteria,
    price_stats: dict[str, float],
    landmark_coords: tuple[float, float] | None,
    transit_scores: dict[str, tuple[float, float | None]] | None = None,
) -> dict[str, float]:
    text = _listing_text(listing)
    feature_tags: set[str] = listing.get("_feature_tags") or set()
    scores: dict[str, float] = {}
    transit_scores = transit_scores or {}

    for pref in criteria.preferences:
        scores[pref.label] = _score_preference(
            pref.label.lower(), listing, text, feature_tags, price_stats, landmark_coords, transit_scores
        )

    # proximity_to_landmark: use transit time if available, fall back to haversine.
    if landmark_coords is not None:
        listing_id = listing.get("listing_id")
        if listing_id in transit_scores:
            score, minutes = transit_scores[listing_id]
            scores["proximity_to_landmark"] = score
            if minutes is not None:
                scores["transit_minutes_to_landmark"] = minutes
        else:
            lat = listing.get("latitude")
            lon = listing.get("longitude")
            if lat is not None and lon is not None:
                dist_km = _haversine(landmark_coords[0], landmark_coords[1], float(lat), float(lon))
                scores["proximity_to_landmark"] = max(0.0, 1.0 - dist_km / _PROXIMITY_MAX_KM)
            else:
                scores["proximity_to_landmark"] = 0.0

    # Negative-signal penalty: fraction of negative terms found in listing text.
    if criteria.negative_signals:
        hits = sum(
            1 for sig in criteria.negative_signals
            if sig.lower() in text or sig.lower() in feature_tags
        )
        scores["negative_signal_penalty"] = hits / len(criteria.negative_signals)

    return scores


def _score_preference(
    label: str,
    listing: dict[str, Any],
    text: str,
    feature_tags: set[str],
    price_stats: dict[str, float],
    landmark_coords: tuple[float, float] | None,
    transit_scores: dict[str, tuple[float, float | None]] | None = None,
) -> float:
    transit_scores = transit_scores or {}

    # ── price-relative scoring ────────────────────────────────────────────
    if any(w in label for w in _CHEAP_WORDS):
        return _price_affordability_score(listing.get("price"), price_stats)
    if any(w in label for w in _EXPENSIVE_WORDS):
        return 1.0 - _price_affordability_score(listing.get("price"), price_stats)

    # ── transport: transit time to landmark beats distance to nearest stop ─
    if any(w in label for w in _TRANSPORT_WORDS):
        listing_id = listing.get("listing_id")
        if landmark_coords and listing_id in transit_scores:
            return transit_scores[listing_id][0]
        dist = listing.get("distance_public_transport")
        if dist is not None:
            return max(0.0, 1.0 - float(dist) / _TRANSPORT_THRESH_M)

    if any(w in label for w in _SHOP_WORDS):
        dist = listing.get("distance_shop")
        if dist is not None:
            return max(0.0, 1.0 - float(dist) / _SHOP_THRESH_M)

    if any(w in label for w in _SCHOOL_WORDS):
        dist = listing.get("distance_school_1")
        if dist is not None:
            return max(0.0, 1.0 - float(dist) / _SCHOOL_THRESH_M)

    if any(w in label for w in _KINDERGARTEN_WORDS):
        dist = listing.get("distance_kindergarten")
        if dist is not None:
            return max(0.0, 1.0 - float(dist) / _KINDERGARTEN_THRESH_M)

    # ── landmark proximity: transit time > haversine ──────────────────────
    if landmark_coords and any(w in label for w in _PROXIMITY_WORDS):
        listing_id = listing.get("listing_id")
        if listing_id in transit_scores:
            return transit_scores[listing_id]
        lat = listing.get("latitude")
        lon = listing.get("longitude")
        if lat is not None and lon is not None:
            dist_km = _haversine(landmark_coords[0], landmark_coords[1], float(lat), float(lon))
            return max(0.0, 1.0 - dist_km / _PROXIMITY_MAX_KM)

    # ── pre-extracted feature tag (canonical label hit) ──────────────────
    for tag in feature_tags:
        if tag in label or label in tag or _words_overlap(label, tag):
            return 1.0

    # ── text-based scoring (last resort for labels outside the synonym map) ─
    return _text_match_score(label, text)


# ---------------------------------------------------------------------------
# Price stats
# ---------------------------------------------------------------------------

def _compute_price_stats(candidates: list[dict[str, Any]]) -> dict[str, float]:
    prices = [float(c["price"]) for c in candidates if c.get("price") is not None]
    if not prices:
        return {}
    mean = sum(prices) / len(prices)
    variance = sum((p - mean) ** 2 for p in prices) / len(prices)
    return {
        "mean": mean,
        "std": math.sqrt(variance),
        "min": min(prices),
        "max": max(prices),
    }


def _price_affordability_score(price: Any, stats: dict[str, float]) -> float:
    """1.0 = very cheap relative to the candidate pool; 0.0 = very expensive."""
    if price is None or not stats or stats.get("std", 0.0) == 0.0:
        return 0.5
    z = (float(price) - stats["mean"]) / stats["std"]
    # z = -2 → 1.0 (very cheap); z = 0 → 0.5 (average); z = +2 → 0.0 (very expensive)
    return max(0.0, min(1.0, 0.5 - z / 4.0))


# ---------------------------------------------------------------------------
# Text matching
# ---------------------------------------------------------------------------

def _listing_text(listing: dict[str, Any]) -> str:
    parts = [
        listing.get("title") or "",
        listing.get("description") or "",
        listing.get("image_description") or "",
    ]
    features = listing.get("features")
    if isinstance(features, list):
        parts.extend(str(f) for f in features)
    return " ".join(parts).lower()


def _words_overlap(a: str, b: str) -> bool:
    """True if the two labels share at least one significant word (>3 chars)."""
    words_a = {w for w in a.split() if len(w) > 3}
    words_b = {w for w in b.split() if len(w) > 3}
    return bool(words_a & words_b)


def _text_match_score(label: str, text: str) -> float:
    """Keyword/synonym overlap score in [0, 1]."""
    if label in text:
        return 1.0

    synonyms = _SYNONYMS.get(label, [])
    if synonyms:
        hits = sum(1 for s in synonyms if s in text)
        # At least half the synonyms matching → 1.0; one match → partial
        return min(1.0, hits / max(1, len(synonyms) / 2))

    # Multi-word label: score by fraction of significant words found
    words = [w for w in label.split() if len(w) > 3]
    if words:
        return sum(1 for w in words if w in text) / len(words)

    return 0.0


# ---------------------------------------------------------------------------
# Nominatim geocoding (cached per process)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=64)
def _geocode_landmark(landmark: str) -> tuple[float, float] | None:
    """Return (lat, lon) for a landmark using Nominatim; retries without 'Switzerland' on miss."""
    queries = [f"{landmark} Switzerland", landmark]
    try:
        with httpx.Client(timeout=5.0) as client:
            for q in queries:
                resp = client.get(
                    _NOMINATIM_URL,
                    params={"q": q, "format": "json", "limit": 1},
                    headers=_NOMINATIM_HEADERS,
                )
                data = resp.json()
                if data:
                    return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Haversine distance
# ---------------------------------------------------------------------------

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
