from __future__ import annotations

import os

from fastapi import APIRouter

from app.config import get_settings
from app.harness.search_service import query_from_filters, query_from_text
from app.models.schemas import (
    HealthResponse,
    ListingsQueryRequest,
    ListingsResponse,
    ListingsSearchRequest,
)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/health/detailed")
def health_detailed() -> dict:
    key = os.getenv("ANTHROPIC_API_KEY", "")
    return {
        "status": "ok",
        "anthropic_key_set": bool(key),
        "anthropic_key_prefix": key[:12] + "..." if key else "(not set)",
    }


@router.post("/listings", response_model=ListingsResponse)
def listings(request: ListingsQueryRequest) -> ListingsResponse:
    settings = get_settings()
    return query_from_text(
        db_path=settings.db_path,
        query=request.query,
        user_id=request.user_id,
        limit=request.limit,
        offset=request.offset,
    )


@router.post("/listings/search/filter", response_model=ListingsResponse)
def listings_search(request: ListingsSearchRequest) -> ListingsResponse:
    settings = get_settings()
    return query_from_filters(
        db_path=settings.db_path,
        hard_facts=request.hard_filters,
    )
