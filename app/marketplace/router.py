from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.marketplace.schemas import (
    OfferCreateRequest,
    OfferResponse,
    OffersListResponse,
    OpenRidesResponse,
    RideCreateRequest,
    RideResponse,
    SelectDriverRequest,
)
from app.marketplace.service import MarketplaceService

router = APIRouter(tags=["marketplace"])


def get_marketplace_service(request: Request) -> MarketplaceService:
    return request.app.state.marketplace_service


def get_current_wallet(request: Request, authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    return request.app.state.auth_service.read_wallet_from_token(token)


@router.post("/rides", response_model=RideResponse)
async def create_ride(
    payload: RideCreateRequest,
    wallet: str = Depends(get_current_wallet),
    marketplace_service: MarketplaceService = Depends(get_marketplace_service),
) -> RideResponse:
    return await marketplace_service.create_ride(wallet, payload)


@router.get("/rides/{ride_id}", response_model=RideResponse)
async def get_ride(
    ride_id: str,
    _wallet: str = Depends(get_current_wallet),
    marketplace_service: MarketplaceService = Depends(get_marketplace_service),
) -> RideResponse:
    return await marketplace_service.get_ride(ride_id)


@router.get("/driver-feed/open-rides", response_model=OpenRidesResponse)
async def open_rides(
    limit: int = 20,
    offset: int = 0,
    _wallet: str = Depends(get_current_wallet),
    marketplace_service: MarketplaceService = Depends(get_marketplace_service),
) -> OpenRidesResponse:
    rides = await marketplace_service.list_open_rides(limit=limit, offset=offset)
    return OpenRidesResponse(rides=rides)


@router.post("/rides/{ride_id}/offers", response_model=OfferResponse)
async def create_offer(
    ride_id: str,
    payload: OfferCreateRequest,
    wallet: str = Depends(get_current_wallet),
    marketplace_service: MarketplaceService = Depends(get_marketplace_service),
) -> OfferResponse:
    return await marketplace_service.create_offer(ride_id, wallet, payload)


@router.get("/rides/{ride_id}/offers", response_model=OffersListResponse)
async def list_offers(
    ride_id: str,
    _wallet: str = Depends(get_current_wallet),
    marketplace_service: MarketplaceService = Depends(get_marketplace_service),
) -> OffersListResponse:
    offers = await marketplace_service.list_offers(ride_id)
    return OffersListResponse(offers=offers)


@router.post("/rides/{ride_id}/select-driver", response_model=RideResponse)
async def select_driver(
    ride_id: str,
    payload: SelectDriverRequest,
    wallet: str = Depends(get_current_wallet),
    marketplace_service: MarketplaceService = Depends(get_marketplace_service),
) -> RideResponse:
    return await marketplace_service.select_driver(ride_id, wallet, payload.offerId)
