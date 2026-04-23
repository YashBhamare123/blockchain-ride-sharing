from fastapi import APIRouter, Depends, Query, Request

from app.maps.schemas import (
    AutocompleteResponse,
    PlaceDetailsResponse,
    RouteEstimateRequest,
    RouteEstimateResponse,
)
from app.maps.service import MapsService

router = APIRouter(tags=["maps"])


def get_maps_service(request: Request) -> MapsService:
    return request.app.state.maps_service


@router.get("/maps/autocomplete", response_model=AutocompleteResponse)
async def autocomplete(
    q: str = Query(..., min_length=2),
    country: str | None = Query(default=None),
    maps_service: MapsService = Depends(get_maps_service),
) -> AutocompleteResponse:
    return await maps_service.autocomplete(query=q, country=country)


@router.get("/maps/place/{place_id}", response_model=PlaceDetailsResponse)
async def place_details(
    place_id: str,
    maps_service: MapsService = Depends(get_maps_service),
) -> PlaceDetailsResponse:
    return await maps_service.place_details(place_id=place_id)


@router.post("/routes/estimate", response_model=RouteEstimateResponse)
async def route_estimate(
    payload: RouteEstimateRequest,
    maps_service: MapsService = Depends(get_maps_service),
) -> RouteEstimateResponse:
    return await maps_service.route_estimate(payload=payload)
