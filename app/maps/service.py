import re

import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.maps.schemas import (
    AutocompleteItem,
    AutocompleteResponse,
    LatLng,
    PlaceDetailsResponse,
    RouteEstimateRequest,
    RouteEstimateResponse,
)


class MapsService:
    async def autocomplete(self, query: str, country: str | None = None) -> AutocompleteResponse:
        if not settings.google_maps_api_key:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Missing Google API key")

        params = {"input": query, "key": settings.google_maps_api_key}
        country_code = country or settings.google_maps_default_country
        if country_code:
            params["components"] = f"country:{country_code}"

        async with httpx.AsyncClient(timeout=settings.google_maps_timeout_seconds) as client:
            response = await client.get("https://maps.googleapis.com/maps/api/place/autocomplete/json", params=params)
            data = response.json()

        predictions = [
            AutocompleteItem(
                placeId=item.get("place_id", ""),
                description=item.get("description", ""),
                mainText=item.get("structured_formatting", {}).get("main_text", ""),
                secondaryText=item.get("structured_formatting", {}).get("secondary_text", ""),
            )
            for item in data.get("predictions", [])
        ]
        return AutocompleteResponse(predictions=predictions)

    async def place_details(self, place_id: str) -> PlaceDetailsResponse:
        if not settings.google_maps_api_key:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Missing Google API key")

        params = {
            "place_id": place_id,
            "fields": "place_id,name,formatted_address,geometry/location",
            "key": settings.google_maps_api_key,
        }
        async with httpx.AsyncClient(timeout=settings.google_maps_timeout_seconds) as client:
            response = await client.get("https://maps.googleapis.com/maps/api/place/details/json", params=params)
            data = response.json()

        result = data.get("result", {})
        location = result.get("geometry", {}).get("location", {})
        return PlaceDetailsResponse(
            placeId=result.get("place_id", ""),
            name=result.get("name", ""),
            formattedAddress=result.get("formatted_address", ""),
            location=LatLng(lat=location.get("lat", 0.0), lng=location.get("lng", 0.0)),
        )

    async def route_estimate(self, payload: RouteEstimateRequest) -> RouteEstimateResponse:
        if not settings.google_maps_api_key:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Missing Google API key")

        body = {
            "origin": {
                "location": {
                    "latLng": {"latitude": payload.origin.lat, "longitude": payload.origin.lng}
                }
            },
            "destination": {
                "location": {
                    "latLng": {"latitude": payload.destination.lat, "longitude": payload.destination.lng}
                }
            },
            "travelMode": payload.travelMode,
        }
        headers = {
            "X-Goog-Api-Key": settings.google_maps_api_key,
            "X-Goog-FieldMask": "routes.distanceMeters,routes.duration,routes.polyline.encodedPolyline",
        }

        async with httpx.AsyncClient(timeout=settings.google_maps_timeout_seconds) as client:
            response = await client.post("https://routes.googleapis.com/directions/v2:computeRoutes", json=body, headers=headers)
            data = response.json()

        first_route = (data.get("routes") or [{}])[0]
        duration_seconds = _parse_duration_seconds(first_route.get("duration", "0s"))
        return RouteEstimateResponse(
            distanceMeters=int(first_route.get("distanceMeters", 0)),
            durationSeconds=duration_seconds,
            polyline=first_route.get("polyline", {}).get("encodedPolyline", ""),
        )


def _parse_duration_seconds(value: str) -> int:
    match = re.match(r"^(\d+)s$", value or "")
    if not match:
        return 0
    return int(match.group(1))

