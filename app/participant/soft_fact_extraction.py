from __future__ import annotations

import logging
from typing import Any

from app.models.schemas import SoftCriteria, WeightedPreference

logger = logging.getLogger(__name__)

# Weight hints communicated to the model:
# 1.0  — "must", "need", "require", "essential"
# 0.7  — "really want", "important", "definitely"
# 0.4  — "ideally", "prefer", "would like"
# 0.2  — "nice if", "if possible", "bonus"


def extract_soft_facts(query: str) -> dict[str, Any]:
    if not query.strip():
        return SoftCriteria(raw_query=query).model_dump()
    try:
        return _extract_with_llm(query)
    except Exception as exc:
        logger.warning("soft_fact_extraction LLM call failed: %s", exc)
        return SoftCriteria(raw_query=query).model_dump()


def _extract_with_llm(query: str) -> dict[str, Any]:
    import anthropic

    client = anthropic.Anthropic()

    tool = {
        "name": "set_soft_criteria",
        "description": "Record qualitative preferences extracted from a real-estate query.",
        "input_schema": {
            "type": "object",
            "required": ["reasoning", "preferences", "negative_signals", "ideal_description"],
            "properties": {
                "reasoning": {
                    "type": "string",
                    "description": (
                        "Step-by-step chain-of-thought: which phrases signal soft preferences, "
                        "how strong each is, what the user wants to avoid, and whether any "
                        "landmark or commute destination is mentioned."
                    ),
                },
                "preferences": {
                    "type": "array",
                    "description": "Qualitative preferences with importance weights.",
                    "items": {
                        "type": "object",
                        "required": ["label", "weight"],
                        "properties": {
                            "label": {
                                "type": "string",
                                "enum": [
                                    "bright", "modern", "renovated", "quiet", "spacious",
                                    "cozy", "family-friendly", "views", "garden", "new build",
                                    "pet-friendly", "parking", "affordable", "luxury",
                                    "balcony", "elevator", "fireplace",
                                    "transport", "shop", "school", "kindergarten",
                                ],
                                "description": (
                                    "Canonical soft-feature label. Pick the single closest "
                                    "match from the enum list; do not combine labels."
                                ),
                            },
                            "weight": {
                                "type": "number",
                                "description": (
                                    "Importance 0.0–1.0. "
                                    "1.0 = 'must have' / 'need'; "
                                    "0.7 = 'really want' / 'important'; "
                                    "0.4 = 'ideally' / 'prefer'; "
                                    "0.2 = 'nice if' / 'if possible'."
                                ),
                            },
                        },
                    },
                },
                "negative_signals": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Things the user explicitly wants to avoid, "
                        "e.g. 'ground floor', 'near motorway', 'dark apartment'."
                    ),
                },
                "target_landmark": {
                    "type": "string",
                    "description": (
                        "Named commute destination mentioned by the user "
                        "(e.g. 'ETH Zurich', 'Zurich HB', 'Google Zurich office'). "
                        "Omit if not mentioned."
                    ),
                },
                "ideal_description": {
                    "type": "string",
                    "description": (
                        "Exactly 2 sentences describing the perfect listing for this user. "
                        "Written in the style of a listing description so it can be used "
                        "for semantic similarity ranking against real listing texts."
                    ),
                },
            },
        },
    }

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=(
            "You extract soft, qualitative preferences from Swiss real-estate search queries.\n\n"
            "Soft preferences are subjective signals about ambiance, style, neighbourhood feel, "
            "proximity hints, and lifestyle — NOT hard filters like price, rooms, or city.\n\n"
            "Always fill the 'reasoning' field first to think through the query before deciding "
            "on labels, weights, and negative signals. This is your chain-of-thought scratchpad.\n\n"
            "Weight guidance:\n"
            "  1.0 → 'must', 'need', 'require', 'essential'\n"
            "  0.7 → 'really want', 'important', 'definitely'\n"
            "  0.4 → 'ideally', 'prefer', 'would like'\n"
            "  0.2 → 'nice if', 'if possible', 'bonus'\n\n"
            "Do NOT repeat hard constraints (price, rooms, city) in the preferences list."
        ),
        tools=[tool],
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": query}],
    )

    for block in response.content:
        if block.type == "tool_use":
            data: dict[str, Any] = block.input
            preferences = [
                WeightedPreference(
                    label=p["label"],
                    weight=float(p["weight"]),
                )
                for p in data.get("preferences", [])
                if isinstance(p, dict) and "label" in p and "weight" in p
            ]
            criteria = SoftCriteria(
                preferences=preferences,
                negative_signals=[s for s in data.get("negative_signals", []) if s],
                target_landmark=data.get("target_landmark") or None,
                ideal_description=data.get("ideal_description", ""),
                raw_query=query,
            )
            return criteria.model_dump()

    return SoftCriteria(raw_query=query).model_dump()
