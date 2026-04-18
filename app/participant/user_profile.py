from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.harness.user_interactions import (
    get_interactions,
    get_profile,
    needs_regen,
    save_profile,
)

logger = logging.getLogger(__name__)

_PROFILE_TOOL = {
    "name": "set_user_profile",
    "description": "Record inferred user preferences from their interaction history.",
    "input_schema": {
        "type": "object",
        "required": [
            "preferred_cities", "preferred_cantons", "aesthetic_preferences",
            "feature_affinity", "negative_patterns", "confidence", "summary",
        ],
        "properties": {
            "preferred_cities": {
                "type": "array", "items": {"type": "string"},
                "description": "Cities the user has repeatedly searched or clicked on.",
            },
            "preferred_cantons": {
                "type": "array", "items": {"type": "string"},
                "description": "Swiss cantons (2-letter codes) preferred by the user.",
            },
            "typical_budget_chf": {
                "type": "integer",
                "description": "Estimated monthly budget in CHF based on price ranges queried.",
            },
            "min_rooms": {"type": "number", "description": "Minimum rooms typically searched."},
            "max_rooms": {"type": "number", "description": "Maximum rooms typically searched."},
            "offer_type": {
                "type": "string", "enum": ["RENT", "SALE"],
                "description": "Whether the user is searching to rent or buy. Omit if unclear.",
            },
            "aesthetic_preferences": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "bright", "modern", "renovated", "quiet", "spacious",
                        "cozy", "family-friendly", "views", "garden", "new build",
                        "pet-friendly", "luxury", "affordable",
                    ],
                },
                "description": "Aesthetic or lifestyle labels the user has shown affinity for.",
            },
            "feature_affinity": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "balcony", "elevator", "parking", "garage", "fireplace",
                        "child_friendly", "pets_allowed", "new_build",
                        "wheelchair_accessible", "private_laundry", "minergie_certified",
                    ],
                },
                "description": "Structural features that appear frequently in listings the user engaged with.",
            },
            "negative_patterns": {
                "type": "array", "items": {"type": "string"},
                "description": "Things the user has avoided or expressed dislike for.",
            },
            "confidence": {
                "type": "number",
                "description": "0.0–1.0. Low if few interactions; high if strong consistent pattern.",
            },
            "summary": {
                "type": "string",
                "description": "One sentence summarising the user's real-estate profile.",
            },
        },
    },
}


def get_or_generate_profile(db_path: Path, user_id: str) -> dict[str, Any] | None:
    """Return a cached profile or generate a fresh one via Claude if stale."""
    if not needs_regen(db_path, user_id):
        return get_profile(db_path, user_id)

    interactions = get_interactions(db_path, user_id, limit=200)
    if not interactions:
        return None

    profile = _generate_profile(user_id, interactions)
    if profile:
        save_profile(db_path, user_id, profile, len(interactions))
        logger.info("Generated profile for user %s (%d interactions)", user_id, len(interactions))
    return profile


def _generate_profile(user_id: str, interactions: list[dict[str, Any]]) -> dict[str, Any] | None:
    try:
        import anthropic
        client = anthropic.Anthropic()

        history_text = _format_interactions(interactions)

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=(
                "You are a real-estate preference analyst. "
                "Given a user's interaction history with a Swiss property search engine, "
                "infer their preferences as accurately as possible. "
                "Look for recurring patterns: locations, price ranges, room counts, "
                "amenities, and aesthetic terms that appear consistently. "
                "Be conservative with confidence if the history is short or inconsistent."
            ),
            tools=[_PROFILE_TOOL],
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": (
                f"Analyse the interaction history for user '{user_id}' "
                f"and infer their real-estate preferences:\n\n{history_text}"
            )}],
        )

        for block in response.content:
            if block.type == "tool_use":
                profile = dict(block.input)
                profile["user_id"] = user_id
                return profile

    except Exception as exc:
        logger.warning("Profile generation failed for user %s: %s", user_id, exc)
    return None


def _format_interactions(interactions: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for ix in interactions:
        event = ix["event_type"]
        ts = ix["created_at"][:16]
        if event == "search" and ix.get("query"):
            lines.append(f"[{ts}] SEARCH: {ix['query']}")
        elif event == "click" and ix.get("listing_id"):
            lines.append(f"[{ts}] CLICK:  listing {ix['listing_id']}")
        elif event == "favorite" and ix.get("listing_id"):
            lines.append(f"[{ts}] FAV:    listing {ix['listing_id']}")
        elif event == "hide" and ix.get("listing_id"):
            lines.append(f"[{ts}] HIDE:   listing {ix['listing_id']}")
    return "\n".join(lines) if lines else "(no interactions yet)"
