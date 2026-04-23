from fastapi import HTTPException, status

from app.db import Database
from app.location.schemas import LocationResponse, LocationUpdateRequest


class LocationService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def add_location(self, ride_id: str, wallet: str, payload: LocationUpdateRequest) -> LocationResponse:
        pool = self._require_pool()
        wallet = wallet.lower()
        async with pool.acquire() as connection:
            ride = await connection.fetchrow("SELECT * FROM ride_requests WHERE id = $1", ride_id)
            if not ride:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")

            selected_driver = (ride["selected_driver_wallet"] or "").lower()
            if not selected_driver:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ride has no selected driver")
            if wallet != selected_driver:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only selected driver can post location")

            row = await connection.fetchrow(
                """
                INSERT INTO ride_locations(ride_request_id, driver_wallet, lat, lng, heading, speed)
                VALUES($1,$2,$3,$4,$5,$6)
                RETURNING ride_request_id, driver_wallet, lat, lng, heading, speed, timestamp
                """,
                ride_id,
                wallet,
                payload.lat,
                payload.lng,
                payload.heading,
                payload.speed,
            )
        return self._location_from_row(row)

    async def get_latest_location(self, ride_id: str, wallet: str) -> LocationResponse:
        pool = self._require_pool()
        wallet = wallet.lower()
        async with pool.acquire() as connection:
            ride = await connection.fetchrow("SELECT * FROM ride_requests WHERE id = $1", ride_id)
            if not ride:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")
            rider = str(ride["rider_wallet"]).lower()
            driver = (ride["selected_driver_wallet"] or "").lower()
            if wallet not in {rider, driver}:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only rider or selected driver can view location")

            row = await connection.fetchrow(
                """
                SELECT ride_request_id, driver_wallet, lat, lng, heading, speed, timestamp
                FROM ride_locations
                WHERE ride_request_id = $1
                ORDER BY timestamp DESC, id DESC
                LIMIT 1
                """,
                ride_id,
            )
            if not row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No location found for ride")
        return self._location_from_row(row)

    def _require_pool(self):
        if not self.db.pool:
            raise RuntimeError("Database is not connected")
        return self.db.pool

    def _location_from_row(self, row) -> LocationResponse:
        return LocationResponse(
            rideId=row["ride_request_id"],
            driverWallet=row["driver_wallet"],
            lat=row["lat"],
            lng=row["lng"],
            heading=row["heading"],
            speed=row["speed"],
            timestamp=row["timestamp"].isoformat(),
        )

