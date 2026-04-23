from pydantic import BaseModel, Field


class CompleteRideSignRequest(BaseModel):
    onChainRideId: int = Field(ge=0)
    finalFareWei: str
    chainId: int = Field(ge=1)


class CompleteRideSignResponse(BaseModel):
    treasurySignature: str
    onChainRideId: int
    finalFareWei: str
    riderWallet: str
    driverWallet: str
    chainId: int

