from fastapi import HTTPException, status

from app.config import settings
from app.db import Database
from app.tx.schemas import AcceptRidePrepRequest, AcceptRidePrepResponse, TxRecordCreateRequest, TxRecordResponse


class TxService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def prepare_accept_ride(self, rider_wallet: str, payload: AcceptRidePrepRequest) -> AcceptRidePrepResponse:
        if not self.db.pool:
            raise RuntimeError("Database is not connected")

        rider_wallet = rider_wallet.lower()

        async with self.db.pool.acquire() as connection:
            ride = await connection.fetchrow("SELECT * FROM ride_requests WHERE id = $1", payload.rideId)
            if not ride:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")
            if ride["rider_wallet"] != rider_wallet:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only ride owner can prepare acceptRide")
            if ride["status"] != "DRIVER_SELECTED":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Ride must be in DRIVER_SELECTED state before acceptRide prep",
                )

            selected_offer = await connection.fetchrow(
                """
                SELECT * FROM driver_offers
                WHERE ride_request_id = $1 AND status = 'SELECTED'
                LIMIT 1
                """,
                payload.rideId,
            )
            if not selected_offer:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No selected offer found")

        driver_wallet = str(selected_offer["driver_wallet"]).lower()
        fare_wei = int(selected_offer["quoted_fare_wei"])

        # Source of truth is what the driver actually signed at offer submission.
        # Fall back to the request payload only if the offer row is missing those values.
        offer_keys = set(selected_offer.keys())
        stored_sig = selected_offer["driver_signature"] if "driver_signature" in offer_keys else None
        stored_nonce = selected_offer["driver_nonce"] if "driver_nonce" in offer_keys else None
        stored_ceiling = selected_offer["ceiling_enabled"] if "ceiling_enabled" in offer_keys else None

        driver_signature = stored_sig or payload.driverSignature
        if stored_nonce is not None:
            driver_nonce = int(stored_nonce)
        else:
            driver_nonce = payload.driverNonce
        ceiling_enabled = bool(stored_ceiling) if stored_ceiling is not None else payload.ceilingEnabled

        # Contract does integer math: fare * BOND / 100.
        bond_percent_int = int(settings.ceiling_bond_percent)
        ceiling_bond_wei = 0
        if ceiling_enabled:
            ceiling_bond_wei = fare_wei * bond_percent_int // 100
        required_msg_value_wei = fare_wei + ceiling_bond_wei

        return AcceptRidePrepResponse(
            contractAddress=settings.carpool_contract_address,
            functionName="acceptRide",
            riderWallet=rider_wallet,
            driverWallet=driver_wallet,
            fareWei=str(fare_wei),
            ceilingEnabled=ceiling_enabled,
            ceilingBondWei=str(ceiling_bond_wei),
            requiredMsgValueWei=str(required_msg_value_wei),
            driverSignature=driver_signature,
            rideId=payload.rideId,
            chainId=payload.chainId,
            driverNonce=driver_nonce,
        )

    async def record_tx(self, wallet: str, payload: TxRecordCreateRequest) -> TxRecordResponse:
        if not self.db.pool:
            raise RuntimeError("Database is not connected")

        normalized_hash = payload.txHash.lower()
        normalized_wallet = wallet.lower()
        confirmed_at = None
        if payload.status == "confirmed":
            from datetime import UTC, datetime

            confirmed_at = datetime.now(UTC)

        async with self.db.pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO tx_records(ride_request_id, action, tx_hash, chain_id, from_wallet, status, confirmed_at)
                VALUES($1,$2,$3,$4,$5,$6,$7)
                ON CONFLICT (tx_hash)
                DO UPDATE SET
                    ride_request_id = COALESCE(EXCLUDED.ride_request_id, tx_records.ride_request_id),
                    action = EXCLUDED.action,
                    chain_id = EXCLUDED.chain_id,
                    from_wallet = EXCLUDED.from_wallet,
                    status = EXCLUDED.status,
                    confirmed_at = COALESCE(EXCLUDED.confirmed_at, tx_records.confirmed_at)
                RETURNING *
                """,
                payload.rideRequestId,
                payload.action,
                normalized_hash,
                payload.chainId,
                normalized_wallet,
                payload.status,
                confirmed_at,
            )

        return TxRecordResponse(
            txHash=row["tx_hash"],
            chainId=row["chain_id"],
            action=row["action"],
            rideRequestId=row["ride_request_id"],
            status=row["status"],
            blockNumber=row["block_number"],
            confirmedAt=row["confirmed_at"].isoformat() if row["confirmed_at"] else None,
        )

