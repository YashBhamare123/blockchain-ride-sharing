from datetime import UTC, datetime
import json

import httpx
from fastapi import HTTPException, status

from app.chain_sync.schemas import ChainEvent, ChainEventsWebhookRequest, ChainEventsWebhookResponse, TxStatusResponse
from app.config import settings
from app.db import Database


EVENT_TO_RIDE_STATUS = {
    "RideAccepted": "ONCHAIN_ACCEPTED",
    "RideStarted": "STARTED",
    "RideCompleted": "COMPLETED",
    "RideCancelled": "CANCELLED",
    "RideDisputed": "DISPUTED",
    "DisputeResolved": "COMPLETED",
}


class ChainSyncService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def ingest_events(self, webhook: ChainEventsWebhookRequest) -> ChainEventsWebhookResponse:
        if not self.db.pool:
            raise RuntimeError("Database is not connected")

        processed = 0
        async with self.db.pool.acquire() as connection:
            async with connection.transaction():
                for event in webhook.events:
                    inserted = await self._insert_chain_event(connection, event)
                    if not inserted:
                        continue
                    processed += 1
                    await self._upsert_tx_record(connection, event)
                    await self._apply_ride_state_from_event(connection, event)

        return ChainEventsWebhookResponse(processed=processed)

    async def get_tx_status(self, tx_hash: str) -> TxStatusResponse:
        if not self.db.pool:
            raise RuntimeError("Database is not connected")

        normalized_hash = tx_hash.lower()
        async with self.db.pool.acquire() as connection:
            row = await connection.fetchrow("SELECT * FROM tx_records WHERE tx_hash = $1", normalized_hash)
            if not row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

            if row["status"] in {"submitted", "pending"} and settings.chain_rpc_url:
                updated = await self._refresh_tx_status_from_rpc(connection, row)
                if updated:
                    row = updated

        confirmed_at = row["confirmed_at"].isoformat() if row["confirmed_at"] else None
        return TxStatusResponse(
            txHash=row["tx_hash"],
            status=row["status"],
            chainId=row["chain_id"],
            action=row["action"],
            rideRequestId=row["ride_request_id"],
            blockNumber=row["block_number"],
            confirmedAt=confirmed_at,
        )

    async def _insert_chain_event(self, connection, event: ChainEvent) -> bool:
        result = await connection.execute(
            """
            INSERT INTO chain_events(tx_hash, log_index, event_name, chain_id, ride_request_id, payload)
            VALUES($1,$2,$3,$4,$5,$6::jsonb)
            ON CONFLICT (tx_hash, log_index, event_name) DO NOTHING
            """,
            event.txHash.lower(),
            event.logIndex,
            event.eventName,
            event.chainId,
            event.rideRequestId,
            json.dumps(event.payload),
        )
        return result.endswith("1")

    async def _upsert_tx_record(self, connection, event: ChainEvent) -> None:
        tx_status = event.status or "confirmed"
        confirmed_at = datetime.now(UTC) if tx_status == "confirmed" else None
        await connection.execute(
            """
            INSERT INTO tx_records(ride_request_id, action, tx_hash, chain_id, from_wallet, status, block_number, confirmed_at)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT (tx_hash)
            DO UPDATE SET
                ride_request_id = COALESCE(EXCLUDED.ride_request_id, tx_records.ride_request_id),
                action = EXCLUDED.action,
                chain_id = EXCLUDED.chain_id,
                from_wallet = EXCLUDED.from_wallet,
                status = EXCLUDED.status,
                block_number = EXCLUDED.block_number,
                confirmed_at = COALESCE(EXCLUDED.confirmed_at, tx_records.confirmed_at)
            """,
            event.rideRequestId,
            event.action or event.eventName,
            event.txHash.lower(),
            event.chainId,
            (event.fromWallet or "0x0000000000000000000000000000000000000000").lower(),
            tx_status,
            event.blockNumber,
            confirmed_at,
        )

    async def _apply_ride_state_from_event(self, connection, event: ChainEvent) -> None:
        if not event.rideRequestId:
            return
        mapped_status = EVENT_TO_RIDE_STATUS.get(event.eventName)
        if not mapped_status:
            return
        await connection.execute(
            """
            UPDATE ride_requests
            SET status = $1,
                selected_driver_wallet = COALESCE($2, selected_driver_wallet),
                updated_at = NOW()
            WHERE id = $3
            """,
            mapped_status,
            event.driverWallet.lower() if event.driverWallet else None,
            event.rideRequestId,
        )

    async def _refresh_tx_status_from_rpc(self, connection, row):
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_getTransactionReceipt",
            "params": [row["tx_hash"]],
        }
        try:
            async with httpx.AsyncClient(timeout=6) as client:
                response = await client.post(settings.chain_rpc_url, json=payload)
                data = response.json()
        except Exception:
            return None

        receipt = data.get("result")
        if not receipt:
            return None

        tx_status = "confirmed" if receipt.get("status") == "0x1" else "failed"
        block_number = int(receipt.get("blockNumber", "0x0"), 16)
        confirmed_at = datetime.now(UTC)
        return await connection.fetchrow(
            """
            UPDATE tx_records
            SET status = $1, block_number = $2, confirmed_at = $3
            WHERE tx_hash = $4
            RETURNING *
            """,
            tx_status,
            block_number,
            confirmed_at,
            row["tx_hash"],
        )

