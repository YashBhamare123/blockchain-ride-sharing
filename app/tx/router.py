from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.tx.schemas import AcceptRidePrepRequest, AcceptRidePrepResponse, TxRecordCreateRequest, TxRecordResponse
from app.tx.service import TxService

router = APIRouter(tags=["tx"])


def get_tx_service(request: Request) -> TxService:
    return request.app.state.tx_service


def get_current_wallet(request: Request, authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    return request.app.state.auth_service.read_wallet_from_token(token)


@router.post("/tx/accept-ride", response_model=AcceptRidePrepResponse)
async def prepare_accept_ride(
    payload: AcceptRidePrepRequest,
    wallet: str = Depends(get_current_wallet),
    tx_service: TxService = Depends(get_tx_service),
) -> AcceptRidePrepResponse:
    return await tx_service.prepare_accept_ride(wallet, payload)


@router.post("/tx/record", response_model=TxRecordResponse)
async def record_tx(
    payload: TxRecordCreateRequest,
    wallet: str = Depends(get_current_wallet),
    tx_service: TxService = Depends(get_tx_service),
) -> TxRecordResponse:
    return await tx_service.record_tx(wallet, payload)
