from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.location.schemas import LocationResponse, LocationUpdateRequest
from app.location.service import LocationService

router = APIRouter(tags=["location"])


def get_location_service(request: Request) -> LocationService:
    return request.app.state.location_service


def get_current_wallet(request: Request, authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    return request.app.state.auth_service.read_wallet_from_token(token)


@router.post("/rides/{ride_id}/locations", response_model=LocationResponse)
async def add_location(
    ride_id: str,
    payload: LocationUpdateRequest,
    wallet: str = Depends(get_current_wallet),
    location_service: LocationService = Depends(get_location_service),
) -> LocationResponse:
    return await location_service.add_location(ride_id=ride_id, wallet=wallet, payload=payload)


@router.get("/rides/{ride_id}/locations/latest", response_model=LocationResponse)
async def latest_location(
    ride_id: str,
    wallet: str = Depends(get_current_wallet),
    location_service: LocationService = Depends(get_location_service),
) -> LocationResponse:
    return await location_service.get_latest_location(ride_id=ride_id, wallet=wallet)
