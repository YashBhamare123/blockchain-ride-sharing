from pydantic import BaseModel


class LocationUpdateRequest(BaseModel):
    lat: float
    lng: float
    heading: float | None = None
    speed: float | None = None


class LocationResponse(BaseModel):
    rideId: str
    driverWallet: str
    lat: float
    lng: float
    heading: float | None = None
    speed: float | None = None
    timestamp: str

