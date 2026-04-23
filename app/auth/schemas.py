from pydantic import BaseModel


class NonceRequest(BaseModel):
    wallet: str


class NonceResponse(BaseModel):
    nonce: str
    expiresAt: str


class VerifyRequest(BaseModel):
    wallet: str
    nonce: str
    signature: str


class VerifyResponse(BaseModel):
    accessToken: str
    tokenType: str = "Bearer"


class MeResponse(BaseModel):
    wallet: str


class LogoutResponse(BaseModel):
    success: bool = True

