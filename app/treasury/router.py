from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.treasury.schemas import CompleteRideSignRequest, CompleteRideSignResponse
from app.treasury.service import TreasurySignerService

router = APIRouter(tags=["treasury"])


def get_treasury_service(request: Request) -> TreasurySignerService:
    return request.app.state.treasury_service


def get_current_wallet(request: Request, authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    return request.app.state.auth_service.read_wallet_from_token(token)


@router.post("/rides/{ride_id}/complete/sign", response_model=CompleteRideSignResponse)
async def sign_complete_ride(
    ride_id: str,
    payload: CompleteRideSignRequest,
    wallet: str = Depends(get_current_wallet),
    treasury_service: TreasurySignerService = Depends(get_treasury_service),
) -> CompleteRideSignResponse:
    return await treasury_service.sign_complete_ride(wallet=wallet, ride_id=ride_id, payload=payload)
