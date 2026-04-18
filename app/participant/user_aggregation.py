"""
Merges the current query's soft preferences with a user's historical preferences.

Strategy:
- Current query preferences are kept at their full extracted weight.
- Historical preferences NOT in the current query are added at a decayed weight
  so the system "remembers" what the user cared about in past sessions.
- Preferences seen more frequently in history get a small boost.
- The most-used landmark from history is carried forward if none is in the current query.
- Time decay: a preference from 7 days ago contributes ~50% of its original weight.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from app.models.schemas import SoftCriteria, WeightedPreference

_DECAY_HALFLIFE_DAYS = 7.0   # weight halves every 7 days
_MAX_HISTORICAL_WEIGHT = 0.5  # historical prefs never outweigh current ones
_MIN_USEFUL_WEIGHT = 0.1      # prefs below this are noise, skip them


def merge_with_history(
    current: SoftCriteria,
    history: list[dict[str, Any]],
) -> SoftCriteria:
    """Return a new SoftCriteria that blends current + historical signals."""
    if not history:
        return current

    now = datetime.now(timezone.utc)

    # Accumulate decayed weights from history
    label_weight: dict[str, float] = {}
    label_count: dict[str, int] = {}
    seen_landmarks: list[str] = []

    for entry in history:
        decay = _time_decay(entry.get("created_at", ""), now)
        soft = entry.get("soft_facts", {})

        for pref in soft.get("preferences", []):
            label = pref.get("label", "").strip()
            weight = float(pref.get("weight", 0.0))
            if not label:
                continue
            label_weight[label] = label_weight.get(label, 0.0) + weight * decay
            label_count[label] = label_count.get(label, 0) + 1

        landmark = (soft.get("target_landmark") or "").strip()
        if landmark:
            seen_landmarks.append(landmark)

    current_labels = {p.label for p in current.preferences}
    n_sessions = max(1, len(history))

    merged = list(current.preferences)

    for label, accumulated in label_weight.items():
        if label in current_labels:
            continue  # current query always wins

        # Normalise by number of sessions, then add a repeat-frequency bonus
        base = accumulated / n_sessions
        frequency_bonus = min(0.1, (label_count[label] - 1) * 0.03)
        historical_w = min(_MAX_HISTORICAL_WEIGHT, base + frequency_bonus)

        if historical_w >= _MIN_USEFUL_WEIGHT:
            merged.append(WeightedPreference(label=label, weight=round(historical_w, 3)))

    # Carry forward the most-used landmark when the current query has none
    landmark = current.target_landmark
    if not landmark and seen_landmarks:
        landmark = max(set(seen_landmarks), key=seen_landmarks.count)

    return SoftCriteria(
        preferences=merged,
        negative_signals=current.negative_signals,
        target_landmark=landmark,
        ideal_description=current.ideal_description,
        raw_query=current.raw_query,
    )


def _time_decay(created_at_str: str, now: datetime) -> float:
    try:
        ts = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        days_ago = max(0.0, (now - ts).total_seconds() / 86400)
    except Exception:
        days_ago = _DECAY_HALFLIFE_DAYS  # unknown age → half weight

    return math.exp(-math.log(2) * days_ago / _DECAY_HALFLIFE_DAYS)
