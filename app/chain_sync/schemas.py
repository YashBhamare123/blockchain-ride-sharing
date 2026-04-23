from pydantic import BaseModel, Field


class ChainEvent(BaseModel):
    eventName: str
    txHash: str
    chainId: int = Field(ge=1)
    rideRequestId: str | None = None
    blockNumber: int | None = None
    logIndex: int = Field(default=0, ge=0)
    fromWallet: str | None = None
    action: str | None = None
    status: str | None = None
    riderWallet: str | None = None
    driverWallet: str | None = None
    payload: dict = Field(default_factory=dict)


class ChainEventsWebhookRequest(BaseModel):
    events: list[ChainEvent]


class ChainEventsWebhookResponse(BaseModel):
    processed: int


class TxStatusResponse(BaseModel):
    txHash: str
    status: str
    chainId: int
    action: str
    rideRequestId: str | None = None
    blockNumber: int | None = None
    confirmedAt: str | None = None

