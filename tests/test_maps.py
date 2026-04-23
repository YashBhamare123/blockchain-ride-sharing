from fastapi.testclient import TestClient

from app.main import create_app
from app.maps.router import get_maps_service
from app.maps.schemas import (
    AutocompleteItem,
    AutocompleteResponse,
    LatLng,
    PlaceDetailsResponse,
    RouteEstimateRequest,
    RouteEstimateResponse,
)


class FakeMapsService:
    async def autocomplete(self, query: str, country: str | None = None) -> AutocompleteResponse:
        return AutocompleteResponse(
            predictions=[
                AutocompleteItem(
                    placeId="place_1",
                    description=f"{query} test place",
                    mainText="Test Place",
                    secondaryText=country or "NA",
                )
            ]
        )

    async def place_details(self, place_id: str) -> PlaceDetailsResponse:
        return PlaceDetailsResponse(
            placeId=place_id,
            name="Test Place",
            formattedAddress="123 Test Street",
            location=LatLng(lat=12.34, lng=56.78),
        )

    async def route_estimate(self, payload: RouteEstimateRequest) -> RouteEstimateResponse:
        return RouteEstimateResponse(distanceMeters=1200, durationSeconds=420, polyline="encoded_polyline")


def create_test_client() -> TestClient:
    app = create_app(init_db=False)
    fake_service = FakeMapsService()
    app.dependency_overrides[get_maps_service] = lambda: fake_service
    return TestClient(app)


def test_autocomplete_endpoint() -> None:
    with create_test_client() as client:
        response = client.get("/api/v1/maps/autocomplete", params={"q": "indiranagar", "country": "in"})
        body = response.json()
        assert response.status_code == 200
        assert len(body["predictions"]) == 1
        assert body["predictions"][0]["placeId"] == "place_1"


def test_place_details_endpoint() -> None:
    with create_test_client() as client:
        response = client.get("/api/v1/maps/place/place_1")
        body = response.json()
        assert response.status_code == 200
        assert body["placeId"] == "place_1"
        assert body["location"]["lat"] == 12.34


def test_route_estimate_endpoint() -> None:
    with create_test_client() as client:
        response = client.post(
            "/api/v1/routes/estimate",
            json={
                "origin": {"lat": 12.9716, "lng": 77.5946},
                "destination": {"lat": 12.9352, "lng": 77.6245},
                "travelMode": "DRIVE",
            },
        )
        body = response.json()
        assert response.status_code == 200
        assert body["distanceMeters"] == 1200
        assert body["durationSeconds"] == 420
