from pydantic import BaseModel, Field


class RideCreateRequest(BaseModel):
    pickupLat: float
    pickupLng: float
    pickupAddress: str
    dropLat: float
    dropLng: float
    dropAddress: str
    distanceMeters: int | None = Field(default=None, ge=0)
    durationSeconds: int | None = Field(default=None, ge=0)
    tipType: str | None = None
    tipValue: float | None = Field(default=None, ge=0)
    tipWei: str | None = None


class RideResponse(BaseModel):
    id: str
    riderWallet: str
    pickupLat: float
    pickupLng: float
    pickupAddress: str
    dropLat: float
    dropLng: float
    dropAddress: str
    distanceMeters: int | None
    durationSeconds: int | None
    tipType: str | None
    tipValue: float | None
    tipWei: str | None
    selectedDriverWallet: str | None
    status: str
    createdAt: str
    updatedAt: str


class OpenRidesResponse(BaseModel):
    rides: list[RideResponse]

class DriverActiveRideResponse(BaseModel):
    ride: RideResponse | None


class OfferCreateRequest(BaseModel):
    etaSeconds: int = Field(ge=0)
    quotedFareWei: str
    message: str | None = None
    driverSignature: str | None = None
    driverNonce: str | None = None
    ceilingEnabled: bool = False


class OfferResponse(BaseModel):
    id: str
    rideRequestId: str
    driverWallet: str
    etaSeconds: int
    quotedFareWei: str
    message: str | None
    status: str
    createdAt: str


class OffersListResponse(BaseModel):
    offers: list[OfferResponse]


class SelectDriverRequest(BaseModel):
    offerId: str

