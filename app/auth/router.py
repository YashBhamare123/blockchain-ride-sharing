from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.auth.schemas import LogoutResponse, MeResponse, NonceRequest, NonceResponse, VerifyRequest, VerifyResponse
from app.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


@router.post("/nonce", response_model=NonceResponse)
async def nonce(payload: NonceRequest, auth_service: AuthService = Depends(get_auth_service)) -> NonceResponse:
    nonce_value, expires_at = await auth_service.create_nonce(payload.wallet)
    return NonceResponse(nonce=nonce_value, expiresAt=expires_at.isoformat())


@router.post("/verify", response_model=VerifyResponse)
async def verify(payload: VerifyRequest, auth_service: AuthService = Depends(get_auth_service)) -> VerifyResponse:
    token = await auth_service.verify_nonce_signature(payload.wallet, payload.nonce, payload.signature)
    return VerifyResponse(accessToken=token)


@router.get("/me", response_model=MeResponse)
async def me(
    authorization: str | None = Header(default=None),
    auth_service: AuthService = Depends(get_auth_service),
) -> MeResponse:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    wallet = auth_service.read_wallet_from_token(token)
    return MeResponse(wallet=wallet)


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    authorization: str | None = Header(default=None),
    auth_service: AuthService = Depends(get_auth_service),
) -> LogoutResponse:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    await auth_service.revoke_session(token)
    return LogoutResponse()

