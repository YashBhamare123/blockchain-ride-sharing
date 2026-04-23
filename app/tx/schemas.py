from pydantic import BaseModel, Field


class AcceptRidePrepRequest(BaseModel):
    rideId: str
    driverSignature: str
    ceilingEnabled: bool = False
    chainId: int | None = Field(default=None, ge=1)
    driverNonce: int | None = Field(default=None, ge=0)


class AcceptRidePrepResponse(BaseModel):
    contractAddress: str
    functionName: str
    riderWallet: str
    driverWallet: str
    fareWei: str
    ceilingEnabled: bool
    ceilingBondWei: str
    requiredMsgValueWei: str
    driverSignature: str
    rideId: str
    chainId: int | None
    driverNonce: int | None


class TxRecordCreateRequest(BaseModel):
    txHash: str
    chainId: int = Field(ge=1)
    action: str
    rideRequestId: str | None = None
    status: str = "submitted"


class TxRecordResponse(BaseModel):
    txHash: str
    chainId: int
    action: str
    rideRequestId: str | None = None
    status: str
    blockNumber: int | None = None
    confirmedAt: str | None = None

