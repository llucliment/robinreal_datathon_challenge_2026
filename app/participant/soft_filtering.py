from __future__ import annotations

import math
import re
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

# Synonym expansion for text-based scoring
_SYNONYMS: dict[str, list[str]] = {
    "bright": ["bright", "light", "sunny", "luminous", "hell", "licht", "sonnig", "lumineux", "ensoleillé"],
    "modern": ["modern", "contemporary", "renovated", "renoviert", "récent", "modernisé", "updated", "aktuell"],
    "quiet": ["quiet", "calm", "peaceful", "ruhig", "calme", "tranquil", "tranquille", "silent"],
    "spacious": ["spacious", "large", "roomy", "geräumig", "grand", "großzügig", "vaste"],
    "cozy": ["cozy", "cosy", "gemütlich", "charming", "charmant", "confortable", "warm"],
    "renovated": ["renovated", "refurbished", "renoviert", "saniert", "rénové", "restored", "new kitchen"],
    "family-friendly": ["family", "children", "kids", "familie", "kinder", "familienfreundlich", "playground"],
    "views": ["view", "views", "panorama", "aussicht", "vue", "panoramique", "scenery", "mountains"],
    "garden": ["garden", "garten", "jardin", "outdoor", "yard", "terrace", "terrasse"],
    "new build": ["new build", "neubau", "new construction", "newly built", "erstbezug"],
    "pet-friendly": ["pet", "dog", "cat", "animal", "haustier", "tier"],
}

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_NOMINATIM_HEADERS = {"User-Agent": "datathon2026-robinreal/1.0 (educational, non-commercial)"}

# Distance at which proximity score reaches 0.
# 30 km covers most Swiss commuting zones.
_PROXIMITY_MAX_KM = 30.0

# Structured field thresholds (distances are in metres in the DB)
_TRANSPORT_THRESH_M = 1000.0
_SHOP_THRESH_M = 500.0
_SCHOOL_THRESH_M = 800.0
_KINDERGARTEN_THRESH_M = 600.0


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

    for listing in candidates:
        listing["soft_scores"] = _score_listing(listing, criteria, price_stats, landmark_coords)

    return candidates


# ---------------------------------------------------------------------------
# Per-listing scoring
# ---------------------------------------------------------------------------

def _score_listing(
    listing: dict[str, Any],
    criteria: SoftCriteria,
    price_stats: dict[str, float],
    landmark_coords: tuple[float, float] | None,
) -> dict[str, float]:
    text = _listing_text(listing)
    scores: dict[str, float] = {}

    for pref in criteria.preferences:
        scores[pref.label] = _score_preference(
            pref.label.lower(), listing, text, price_stats, landmark_coords
        )

    # Always add a proximity score when a landmark was resolved so ranking.py
    # can use it independently of the per-preference labels.
    if landmark_coords is not None:
        lat = listing.get("latitude")
        lon = listing.get("longitude")
        if lat is not None and lon is not None:
            dist_km = _haversine(landmark_coords[0], landmark_coords[1], float(lat), float(lon))
            scores["proximity_to_landmark"] = max(0.0, 1.0 - dist_km / _PROXIMITY_MAX_KM)
        else:
            scores["proximity_to_landmark"] = 0.0

    # Negative-signal penalty: fraction of negative terms found in listing text.
    if criteria.negative_signals:
        hits = sum(1 for sig in criteria.negative_signals if sig.lower() in text)
        scores["negative_signal_penalty"] = hits / len(criteria.negative_signals)

    return scores


def _score_preference(
    label: str,
    listing: dict[str, Any],
    text: str,
    price_stats: dict[str, float],
    landmark_coords: tuple[float, float] | None,
) -> float:
    # ── price-relative scoring ────────────────────────────────────────────
    if any(w in label for w in _CHEAP_WORDS):
        return _price_affordability_score(listing.get("price"), price_stats)
    if any(w in label for w in _EXPENSIVE_WORDS):
        return 1.0 - _price_affordability_score(listing.get("price"), price_stats)

    # ── structured proximity fields ───────────────────────────────────────
    if any(w in label for w in _TRANSPORT_WORDS):
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

    # ── geocoded landmark proximity ───────────────────────────────────────
    if landmark_coords and any(w in label for w in _PROXIMITY_WORDS):
        lat = listing.get("latitude")
        lon = listing.get("longitude")
        if lat is not None and lon is not None:
            dist_km = _haversine(landmark_coords[0], landmark_coords[1], float(lat), float(lon))
            return max(0.0, 1.0 - dist_km / _PROXIMITY_MAX_KM)

    # ── text-based scoring (fallback for all other labels) ────────────────
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
    parts = [listing.get("title") or "", listing.get("description") or ""]
    features = listing.get("features")
    if isinstance(features, list):
        parts.extend(str(f) for f in features)
    return " ".join(parts).lower()


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
    """Return (lat, lon) for a landmark using the Nominatim API, or None on failure."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(
                _NOMINATIM_URL,
                params={"q": f"{landmark} Switzerland", "format": "json", "limit": 1},
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
