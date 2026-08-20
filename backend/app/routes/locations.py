from fastapi import APIRouter, Query

from app.config import get_settings
from app.models.schemas import LocationSuggestionsResponse
from app.services.mapbox_service import mapbox_service


router = APIRouter(prefix=get_settings().api_prefix, tags=["locations"])


@router.get("/locations/search", response_model=LocationSuggestionsResponse)
async def search_locations(
    query: str = Query(alias="q", min_length=3, max_length=200),
    limit: int = Query(default=5, ge=1, le=5),
) -> LocationSuggestionsResponse:
    suggestions = await mapbox_service.suggest(query.strip(), limit=limit)
    return LocationSuggestionsResponse(suggestions=suggestions)
