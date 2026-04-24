import uuid

from fastapi import HTTPException, status

from app.db import Database
from app.marketplace.schemas import OfferCreateRequest, OfferResponse, RideCreateRequest, RideResponse

ACTIVE_DRIVER_RIDE_STATUSES = ("DRIVER_SELECTED", "ONCHAIN_ACCEPTED", "STARTED")
COMPLETABLE_RIDE_STATUSES = ACTIVE_DRIVER_RIDE_STATUSES
CANCELLABLE_STATUSES = ("OPEN", "DRIVER_SELECTED", "ONCHAIN_ACCEPTED", "STARTED")


class MarketplaceService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def create_ride(self, rider_wallet: str, payload: RideCreateRequest) -> RideResponse:
        pool = self._require_pool()
        ride_id = str(uuid.uuid4())
        rider_wallet = rider_wallet.lower()

        async with pool.acquire() as connection:
            await self._ensure_user(connection, rider_wallet, "rider")
            row = await connection.fetchrow(
                """
                INSERT INTO ride_requests(
                    id, rider_wallet,
                    pickup_lat, pickup_lng, pickup_address,
                    drop_lat, drop_lng, drop_address,
                    distance_meters, duration_seconds,
                    tip_type, tip_value, tip_wei,
                    status
                )
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,'OPEN')
                RETURNING *
                """,
                ride_id,
                rider_wallet,
                payload.pickupLat,
                payload.pickupLng,
                payload.pickupAddress,
                payload.dropLat,
                payload.dropLng,
                payload.dropAddress,
                payload.distanceMeters,
                payload.durationSeconds,
                payload.tipType,
                payload.tipValue,
                payload.tipWei,
            )
        return self._ride_from_row(row)

    async def get_ride(self, ride_id: str) -> RideResponse:
        pool = self._require_pool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow("SELECT * FROM ride_requests WHERE id = $1", ride_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")
        return self._ride_from_row(row)

    async def list_open_rides(self, limit: int, offset: int) -> list[RideResponse]:
        pool = self._require_pool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT * FROM ride_requests
                WHERE status = 'OPEN'
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )
        return [self._ride_from_row(row) for row in rows]

    async def get_driver_active_ride(self, driver_wallet: str) -> RideResponse | None:
        pool = self._require_pool()
        driver_wallet = driver_wallet.lower()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT * FROM ride_requests
                WHERE selected_driver_wallet = $1
                  AND status = ANY($2::text[])
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                driver_wallet,
                list(ACTIVE_DRIVER_RIDE_STATUSES),
            )
        if not row:
            return None
        return self._ride_from_row(row)

    async def create_offer(self, ride_id: str, driver_wallet: str, payload: OfferCreateRequest) -> OfferResponse:
        pool = self._require_pool()
        driver_wallet = driver_wallet.lower()
        offer_id = str(uuid.uuid4())
        async with pool.acquire() as connection:
            await self._ensure_user(connection, driver_wallet, "driver")
            ride = await connection.fetchrow("SELECT * FROM ride_requests WHERE id = $1", ride_id)
            if not ride:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")
            if ride["status"] != "OPEN":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ride is not open for offers")

            duplicate = await connection.fetchrow(
                """
                SELECT id FROM driver_offers
                WHERE ride_request_id = $1 AND driver_wallet = $2 AND status = 'PENDING'
                """,
                ride_id,
                driver_wallet,
            )
            if duplicate:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Driver already has a pending offer")

            row = await connection.fetchrow(
                """
                INSERT INTO driver_offers(
                    id, ride_request_id, driver_wallet,
                    eta_seconds, quoted_fare_wei, message, status,
                    driver_signature, driver_nonce, ceiling_enabled
                )
                VALUES($1,$2,$3,$4,$5,$6,'PENDING',$7,$8,$9)
                RETURNING *
                """,
                offer_id,
                ride_id,
                driver_wallet,
                payload.etaSeconds,
                payload.quotedFareWei,
                payload.message,
                payload.driverSignature,
                payload.driverNonce,
                payload.ceilingEnabled,
            )
        return self._offer_from_row(row)

    async def list_offers(self, ride_id: str) -> list[OfferResponse]:
        pool = self._require_pool()
        async with pool.acquire() as connection:
            ride = await connection.fetchrow("SELECT id FROM ride_requests WHERE id = $1", ride_id)
            if not ride:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")
            rows = await connection.fetch(
                """
                SELECT * FROM driver_offers
                WHERE ride_request_id = $1
                ORDER BY created_at ASC
                """,
                ride_id,
            )
        return [self._offer_from_row(row) for row in rows]

    async def select_driver(self, ride_id: str, rider_wallet: str, offer_id: str) -> RideResponse:
        pool = self._require_pool()
        rider_wallet = rider_wallet.lower()
        async with pool.acquire() as connection:
            async with connection.transaction():
                ride = await connection.fetchrow("SELECT * FROM ride_requests WHERE id = $1 FOR UPDATE", ride_id)
                if not ride:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")
                if ride["rider_wallet"] != rider_wallet:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only ride owner can select a driver")
                if ride["status"] != "OPEN":
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ride is not open")

                offer = await connection.fetchrow(
                    """
                    SELECT * FROM driver_offers
                    WHERE id = $1 AND ride_request_id = $2
                    FOR UPDATE
                    """,
                    offer_id,
                    ride_id,
                )
                if not offer:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found for this ride")
                if offer["status"] != "PENDING":
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Offer is not pending")

                await connection.execute(
                    """
                    UPDATE driver_offers
                    SET status = CASE WHEN id = $1 THEN 'SELECTED' ELSE 'REJECTED' END
                    WHERE ride_request_id = $2 AND status = 'PENDING'
                    """,
                    offer_id,
                    ride_id,
                )
                updated_ride = await connection.fetchrow(
                    """
                    UPDATE ride_requests
                    SET status = 'DRIVER_SELECTED',
                        selected_driver_wallet = $1,
                        updated_at = NOW()
                    WHERE id = $2
                    RETURNING *
                    """,
                    offer["driver_wallet"],
                    ride_id,
                )
        return self._ride_from_row(updated_ride)
    async def complete_ride(self, ride_id: str, driver_wallet: str) -> RideResponse:
        pool = self._require_pool()
        driver_wallet = driver_wallet.lower()
        async with pool.acquire() as connection:
            async with connection.transaction():
                ride = await connection.fetchrow("SELECT * FROM ride_requests WHERE id = $1 FOR UPDATE", ride_id)
                if not ride:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")

                selected_driver = (ride["selected_driver_wallet"] or "").lower()
                if not selected_driver:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ride has no selected driver")
                if selected_driver != driver_wallet:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only selected driver can complete ride")
                if ride["status"] == "COMPLETED":
                    return self._ride_from_row(ride)
                if ride["status"] not in COMPLETABLE_RIDE_STATUSES:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Ride cannot be completed in its current state",
                    )

                updated_ride = await connection.fetchrow(
                    """
                    UPDATE ride_requests
                    SET status = 'COMPLETED',
                        updated_at = NOW()
                    WHERE id = $1
                    RETURNING *
                    """,
                    ride_id,
                )
        return self._ride_from_row(updated_ride)

    async def onchain_accept(self, ride_id: str, rider_wallet: str) -> RideResponse:
        """Called by the rider after the acceptRide blockchain tx is confirmed."""
        pool = self._require_pool()
        rider_wallet = rider_wallet.lower()
        async with pool.acquire() as connection:
            async with connection.transaction():
                ride = await connection.fetchrow("SELECT * FROM ride_requests WHERE id = $1 FOR UPDATE", ride_id)
                if not ride:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")
                if ride["rider_wallet"] != rider_wallet:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the rider can confirm on-chain acceptance")
                if ride["status"] == "ONCHAIN_ACCEPTED":
                    return self._ride_from_row(ride)
                if ride["status"] != "DRIVER_SELECTED":
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Ride must be DRIVER_SELECTED to confirm on-chain (current: {ride['status']})",
                    )
                updated_ride = await connection.fetchrow(
                    """
                    UPDATE ride_requests
                    SET status = 'ONCHAIN_ACCEPTED',
                        updated_at = NOW()
                    WHERE id = $1
                    RETURNING *
                    """,
                    ride_id,
                )
        return self._ride_from_row(updated_ride)

    async def cancel_ride(self, ride_id: str, wallet: str) -> RideResponse:
        pool = self._require_pool()
        wallet = wallet.lower()
        async with pool.acquire() as connection:
            async with connection.transaction():
                ride = await connection.fetchrow("SELECT * FROM ride_requests WHERE id = $1 FOR UPDATE", ride_id)
                if not ride:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")
                if ride["status"] == "CANCELLED":
                    return self._ride_from_row(ride)
                if ride["status"] not in CANCELLABLE_STATUSES:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Ride cannot be cancelled in status '{ride['status']}'",
                    )
                is_rider = ride["rider_wallet"] == wallet
                is_driver = (ride["selected_driver_wallet"] or "").lower() == wallet
                if not is_rider and not is_driver:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorised to cancel this ride")

                updated_ride = await connection.fetchrow(
                    """
                    UPDATE ride_requests
                    SET status = 'CANCELLED',
                        updated_at = NOW()
                    WHERE id = $1
                    RETURNING *
                    """,
                    ride_id,
                )
        return self._ride_from_row(updated_ride)

    def _require_pool(self):
        if not self.db.pool:
            raise RuntimeError("Database is not connected")
        return self.db.pool

    async def _ensure_user(self, connection, wallet: str, role: str) -> None:
        await connection.execute(
            """
            INSERT INTO users(wallet_address, role)
            VALUES ($1, $2)
            ON CONFLICT (wallet_address) DO NOTHING
            """,
            wallet,
            role,
        )

    def _ride_from_row(self, row) -> RideResponse:
        return RideResponse(
            id=row["id"],
            riderWallet=row["rider_wallet"],
            pickupLat=row["pickup_lat"],
            pickupLng=row["pickup_lng"],
            pickupAddress=row["pickup_address"],
            dropLat=row["drop_lat"],
            dropLng=row["drop_lng"],
            dropAddress=row["drop_address"],
            distanceMeters=row["distance_meters"],
            durationSeconds=row["duration_seconds"],
            tipType=row["tip_type"],
            tipValue=row["tip_value"],
            tipWei=row["tip_wei"],
            selectedDriverWallet=row["selected_driver_wallet"],
            status=row["status"],
            createdAt=row["created_at"].isoformat(),
            updatedAt=row["updated_at"].isoformat(),
        )

    def _offer_from_row(self, row) -> OfferResponse:
        return OfferResponse(
            id=row["id"],
            rideRequestId=row["ride_request_id"],
            driverWallet=row["driver_wallet"],
            etaSeconds=row["eta_seconds"],
            quotedFareWei=row["quoted_fare_wei"],
            message=row["message"],
            status=row["status"],
            createdAt=row["created_at"].isoformat(),
        )

