from typing import Literal

from pydantic import BaseModel, Field


class PricingEstimateRequest(BaseModel):
    distanceMeters: int = Field(ge=0)
    durationSeconds: int = Field(ge=0)
    tipType: Literal["fixed", "percent"] | None = None
    tipValue: float | None = Field(default=None, ge=0)
    ceilingEnabled: bool = False


class PricingEstimateResponse(BaseModel):
    baseFareWei: int
    distanceComponentWei: int
    timeComponentWei: int
    surgeMultiplier: float
    serviceFeeWei: int
    tipWei: int
    estimatedTotalWei: int
    ceilingBondWei: int
    requiredMsgValueWei: int

