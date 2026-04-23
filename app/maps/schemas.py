from pydantic import BaseModel, Field


class LatLng(BaseModel):
    lat: float
    lng: float


class AutocompleteItem(BaseModel):
    placeId: str
    description: str
    mainText: str = ""
    secondaryText: str = ""


class AutocompleteResponse(BaseModel):
    predictions: list[AutocompleteItem]


class PlaceDetailsResponse(BaseModel):
    placeId: str
    name: str
    formattedAddress: str
    location: LatLng


class RouteEstimateRequest(BaseModel):
    origin: LatLng
    destination: LatLng
    travelMode: str = Field(default="DRIVE")


class RouteEstimateResponse(BaseModel):
    distanceMeters: int
    durationSeconds: int
    polyline: str

