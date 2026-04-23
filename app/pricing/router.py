from fastapi import APIRouter, Depends, Request

from app.pricing.schemas import PricingEstimateRequest, PricingEstimateResponse
from app.pricing.service import PricingService

router = APIRouter(tags=["pricing"])


def get_pricing_service(request: Request) -> PricingService:
    return request.app.state.pricing_service


@router.post("/pricing/estimate", response_model=PricingEstimateResponse)
async def estimate_pricing(
    payload: PricingEstimateRequest,
    pricing_service: PricingService = Depends(get_pricing_service),
) -> PricingEstimateResponse:
    return pricing_service.estimate(payload)
