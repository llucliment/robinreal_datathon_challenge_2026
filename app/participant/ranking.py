from __future__ import annotations

import json
from typing import Any

from app.models.schemas import ListingData, RankedListingResult, SoftCriteria

# ---------------------------------------------------------------------------
# Lazy-loaded sentence-transformers model (degrades gracefully if unavailable)
# ---------------------------------------------------------------------------

_embed_model: Any = None  # None = not yet attempted; False = import failed


def _get_embed_model() -> Any:
    global _embed_model
    if _embed_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception:
            _embed_model = False
    return _embed_model if _embed_model is not False else None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def rank_listings(
    candidates: list[dict[str, Any]],
    soft_facts: dict[str, Any],
    user_profile: dict[str, Any] | None = None,
) -> list[RankedListingResult]:
    if not candidates:
        return []

    try:
        criteria = SoftCriteria(**soft_facts)
    except Exception:
        criteria = SoftCriteria(raw_query=soft_facts.get("raw_query", ""))

    # Pre-compute semantic similarity scores if ideal_description is present
    if criteria.ideal_description:
        model = _get_embed_model()
        if model is not None:
            _add_embedding_scores(candidates, criteria.ideal_description, model)

    scored = [_score(candidate, criteria, user_profile) for candidate in candidates]
    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        RankedListingResult(
            listing_id=str(candidate["listing_id"]),
            score=round(score, 4),
            reason=reason,
            listing=_to_listing_data(candidate),
        )
        for score, reason, candidate in scored
    ]


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------

def _add_embedding_scores(
    candidates: list[dict[str, Any]],
    ideal_description: str,
    model: Any,
) -> None:
    texts = [_listing_text_for_embed(c) for c in candidates]
    import numpy as np
    ideal_emb = model.encode([ideal_description], normalize_embeddings=True)
    cand_embs = model.encode(texts, normalize_embeddings=True, batch_size=64)
    sims = (cand_embs @ ideal_emb.T).flatten()
    for i, candidate in enumerate(candidates):
        candidate["_embed_score"] = float(sims[i])


def _listing_text_for_embed(candidate: dict[str, Any]) -> str:
    parts = [
        candidate.get("title") or "",
        candidate.get("description") or "",
        candidate.get("image_description") or "",
    ]
    features = candidate.get("features")
    if isinstance(features, list):
        parts.extend(str(f) for f in features)
    return " ".join(parts)[:512]


# ---------------------------------------------------------------------------
# Per-candidate scoring
# ---------------------------------------------------------------------------

def _profile_multiplier(candidate: dict[str, Any], profile: dict[str, Any]) -> tuple[float, list[str]]:
    """Return (multiplier, boost_labels) based on user profile affinity."""
    multiplier = 1.0
    boosts: list[str] = []
    confidence = float(profile.get("confidence", 0.0))
    if confidence < 0.1:
        return 1.0, []

    # City affinity
    city = (candidate.get("city") or "").lower()
    preferred_cities = [c.lower() for c in profile.get("preferred_cities", [])]
    if city and any(city in pc or pc in city for pc in preferred_cities):
        multiplier += 0.15 * confidence
        boosts.append("preferred city")

    # Feature affinity
    features: list[str] = candidate.get("features") or []
    feature_affinity: list[str] = profile.get("feature_affinity", [])
    matched_features = [f for f in feature_affinity if f in features]
    if matched_features:
        multiplier += min(0.15, 0.05 * len(matched_features)) * confidence
        boosts.append(f"features: {', '.join(matched_features[:2])}")

    # Budget affinity
    price = candidate.get("price")
    budget = profile.get("typical_budget_chf")
    if price and budget:
        ratio = float(price) / float(budget)
        if 0.7 <= ratio <= 1.1:
            multiplier += 0.10 * confidence
            boosts.append("within budget")

    # Aesthetic / soft affinity — boost weights of matching preferences
    soft_scores: dict[str, float] = candidate.get("soft_scores") or {}
    aesthetic_prefs: list[str] = profile.get("aesthetic_preferences", [])
    for label in aesthetic_prefs:
        if label in soft_scores and soft_scores[label] > 0.5:
            multiplier += 0.05 * confidence

    # Negative pattern penalty
    text = f"{candidate.get('title', '')} {candidate.get('description', '')}".lower()
    neg_hits = sum(1 for p in profile.get("negative_patterns", []) if p.lower() in text)
    if neg_hits:
        multiplier -= 0.10 * confidence * neg_hits
        boosts.append(f"avoids {neg_hits} pattern(s)")

    return max(0.1, multiplier), boosts


def _score(
    candidate: dict[str, Any],
    criteria: SoftCriteria,
    user_profile: dict[str, Any] | None = None,
) -> tuple[float, str, dict[str, Any]]:
    soft_scores: dict[str, float] = candidate.get("soft_scores") or {}
    # contributions: (weighted_score, label, raw_score)
    contributions: list[tuple[float, str, float]] = []

    total_weight = sum(p.weight for p in criteria.preferences) or 1.0

    # ── per-preference weighted scores ───────────────────────────────────
    for pref in criteria.preferences:
        raw = soft_scores.get(pref.label, 0.0)
        contributions.append((raw * pref.weight, pref.label, raw))

    # ── semantic similarity (ideal_description embedding) ────────────────
    embed_score = candidate.get("_embed_score")
    if embed_score is not None:
        contributions.append((embed_score * 1.0, "semantic match", embed_score))
        total_weight += 1.0

    # ── landmark proximity bonus ──────────────────────────────────────────
    proximity = soft_scores.get("proximity_to_landmark")
    if proximity is not None:
        contributions.append((proximity * 1.0, "proximity to landmark", proximity))
        total_weight += 1.0
        transit_min = soft_scores.get("transit_minutes_to_landmark")
        if transit_min is not None:
            contributions.append((0.0, "transit_minutes_to_landmark", transit_min))

    # ── price_value as constant tiebreaker (weight 0.2) ──────────────────
    price_value = soft_scores.get("price_value")
    if price_value is not None:
        contributions.append((price_value * 0.2, "price value", price_value))
        total_weight += 0.2

    # ── negative signal penalty ──────────────────────────────────────────
    penalty = soft_scores.get("negative_signal_penalty", 0.0)

    raw_sum = sum(ws for ws, _, _ in contributions)
    score = (raw_sum / total_weight) * (1.0 - penalty)

    # Apply user profile multiplier
    profile_boosts: list[str] = []
    if user_profile:
        multiplier, profile_boosts = _profile_multiplier(candidate, user_profile)
        score *= multiplier

    score = min(1.0, score)
    has_landmark = bool(criteria.target_landmark)
    reason = _build_reason(contributions, penalty, profile_boosts, has_landmark=has_landmark)

    # Clean up internal keys before returning the candidate for ListingData
    candidate.pop("_feature_tags", None)
    candidate.pop("_embed_score", None)

    return score, reason, candidate


def _build_reason(
    contributions: list[tuple[float, str, float]],
    penalty: float,
    profile_boosts: list[str] | None = None,
    has_landmark: bool = False,
) -> str:
    if not contributions and penalty == 0.0:
        return "Matched hard filters only."

    # Separate user preferences from internal signals
    internal = {"price value", "semantic match", "proximity to landmark", "transit_minutes_to_landmark"}
    pref_items = [(label, raw) for _, label, raw in contributions if label not in internal]
    price_raw = next((raw for _, label, raw in contributions if label == "price value"), None)
    proximity_raw = next((raw for _, label, raw in contributions if label == "proximity to landmark"), None)

    strong   = [label for label, raw in pref_items if raw >= 0.65]
    moderate = [label for label, raw in pref_items if 0.35 <= raw < 0.65]
    missing  = [label for label, raw in pref_items if raw < 0.35]

    parts: list[str] = []

    if strong:
        parts.append("+ " + ", ".join(strong[:3]))
    if moderate:
        parts.append("~ " + ", ".join(moderate[:2]))
    if missing:
        parts.append("- " + ", ".join(missing[:3]))

    if proximity_raw is not None and has_landmark:
        transit_min = next((raw for _, label, raw in contributions if label == "transit_minutes_to_landmark"), None)
        if transit_min is not None:
            parts.append(f"~{int(transit_min)} min by transit")
        else:
            km_approx = round((1.0 - proximity_raw) * 30, 1)
            parts.append(f"~{km_approx} km from landmark")

    if price_raw is not None:
        if price_raw >= 0.65:
            parts.append("great value")
        elif price_raw <= 0.35:
            parts.append("pricey")

    if penalty > 0.0:
        pct = int(penalty * 100)
        parts.append(f"−{pct}% avoidance")

    if profile_boosts:
        parts.append("profile: " + ", ".join(profile_boosts))

    return " | ".join(parts) if parts else "Matched hard filters; no strong soft signals."


# ---------------------------------------------------------------------------
# Listing data helpers
# ---------------------------------------------------------------------------

def _to_listing_data(candidate: dict[str, Any]) -> ListingData:
    return ListingData(
        id=str(candidate["listing_id"]),
        title=candidate["title"],
        description=candidate.get("description"),
        street=candidate.get("street"),
        city=candidate.get("city"),
        postal_code=candidate.get("postal_code"),
        canton=candidate.get("canton"),
        latitude=candidate.get("latitude"),
        longitude=candidate.get("longitude"),
        price_chf=candidate.get("price"),
        rooms=candidate.get("rooms"),
        living_area_sqm=_coerce_int(candidate.get("area")),
        available_from=candidate.get("available_from"),
        image_urls=_coerce_image_urls(candidate.get("image_urls")),
        hero_image_url=candidate.get("hero_image_url"),
        original_listing_url=candidate.get("original_url"),
        features=candidate.get("features") or [],
        offer_type=candidate.get("offer_type"),
        object_category=candidate.get("object_category"),
        object_type=candidate.get("object_type"),
    )


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _coerce_image_urls(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return None
