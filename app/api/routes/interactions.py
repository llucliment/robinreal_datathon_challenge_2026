from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.harness.user_interactions import log_interaction
from app.models.schemas import InteractionEvent, UserProfile
from app.participant.user_profile import get_or_generate_profile

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/{user_id}/interactions", status_code=204)
def record_interaction(user_id: str, event: InteractionEvent) -> None:
    """Log a click, favorite or hide event for a listing."""
    if event.event_type not in {"click", "favorite", "hide"}:
        raise HTTPException(status_code=422, detail="event_type must be click, favorite or hide")
    settings = get_settings()
    log_interaction(
        settings.db_path,
        user_id=user_id,
        event_type=event.event_type,
        listing_id=event.listing_id,
        query=event.query,
        session_id=event.session_id,
    )


@router.get("/{user_id}/profile", response_model=UserProfile)
def get_profile(user_id: str) -> UserProfile:
    """Return the inferred preference profile for a user (generates if stale)."""
    settings = get_settings()
    profile = get_or_generate_profile(settings.db_path, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Not enough interactions to build a profile yet.")
    return UserProfile(**profile)
