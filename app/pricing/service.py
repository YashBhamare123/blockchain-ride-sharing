from app.config import settings
from app.pricing.schemas import PricingEstimateRequest, PricingEstimateResponse


class PricingService:
    def estimate(self, payload: PricingEstimateRequest) -> PricingEstimateResponse:
        distance_km = payload.distanceMeters / 1000
        duration_min = payload.durationSeconds / 60

        distance_component = int(distance_km * settings.per_km_rate_wei)
        time_component = int(duration_min * settings.per_min_rate_wei)
        base_fare = settings.base_fare_wei + distance_component + time_component

        surged = int(base_fare * settings.surge_multiplier)
        fare_after_min = max(surged, settings.min_fare_wei)

        service_fee = int(fare_after_min * (settings.service_fee_percent / 100))
        subtotal = fare_after_min + service_fee

        tip = self._compute_tip(subtotal=subtotal, tip_type=payload.tipType, tip_value=payload.tipValue)
        estimated_total = subtotal + tip

        ceiling_bond = 0
        if payload.ceilingEnabled:
            ceiling_bond = int(fare_after_min * (settings.ceiling_bond_percent / 100))

        required_msg_value = fare_after_min + ceiling_bond

        return PricingEstimateResponse(
            baseFareWei=fare_after_min,
            distanceComponentWei=distance_component,
            timeComponentWei=time_component,
            surgeMultiplier=settings.surge_multiplier,
            serviceFeeWei=service_fee,
            tipWei=tip,
            estimatedTotalWei=estimated_total,
            ceilingBondWei=ceiling_bond,
            requiredMsgValueWei=required_msg_value,
        )

    def _compute_tip(self, subtotal: int, tip_type: str | None, tip_value: float | None) -> int:
        if not tip_type or tip_value is None:
            return 0
        if tip_type == "fixed":
            return int(tip_value)
        if tip_type == "percent":
            return int(subtotal * (tip_value / 100))
        return 0

