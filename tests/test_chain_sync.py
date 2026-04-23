import asyncio
import os

import asyncpg
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

from app.auth.service import wallet_message
from app.main import create_app

TEST_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/offchain",
)


def clean_tables() -> None:
    async def _clean() -> None:
        conn = await asyncpg.connect(TEST_DB_URL)
        try:
            await conn.execute("DELETE FROM chain_events")
            await conn.execute("DELETE FROM tx_records")
            await conn.execute("DELETE FROM ride_locations")
            await conn.execute("DELETE FROM driver_offers")
            await conn.execute("DELETE FROM ride_requests")
            await conn.execute("DELETE FROM auth_nonces")
            await conn.execute("DELETE FROM users")
        finally:
            await conn.close()

    asyncio.run(_clean())


def create_test_client() -> TestClient:
    app = create_app(init_db=True)
    return TestClient(app)


def make_token(client: TestClient, account) -> str:
    wallet = account.address
    nonce_response = client.post("/api/v1/auth/nonce", json={"wallet": wallet})
    nonce = nonce_response.json()["nonce"]
    signature = Account.sign_message(encode_defunct(text=wallet_message(nonce)), account.key).signature.to_0x_hex()
    verify_response = client.post(
        "/api/v1/auth/verify",
        json={"wallet": wallet, "nonce": nonce, "signature": signature},
    )
    return verify_response.json()["accessToken"]


def create_ride(client: TestClient, rider_token: str) -> str:
    ride_response = client.post(
        "/api/v1/rides",
        headers={"Authorization": f"Bearer {rider_token}"},
        json={
            "pickupLat": 12.9716,
            "pickupLng": 77.5946,
            "pickupAddress": "MG Road",
            "dropLat": 12.9352,
            "dropLng": 77.6245,
            "dropAddress": "Koramangala",
        },
    )
    return ride_response.json()["id"]


def test_chain_event_webhook_updates_ride_and_tx_status() -> None:
    clean_tables()
    rider = Account.create()

    with create_test_client() as client:
        rider_token = make_token(client, rider)
        ride_id = create_ride(client, rider_token)

        webhook_response = client.post(
            "/api/v1/webhooks/chain-events",
            json={
                "events": [
                    {
                        "eventName": "RideAccepted",
                        "txHash": "0xabc123",
                        "chainId": 11155111,
                        "rideRequestId": ride_id,
                        "blockNumber": 12345,
                        "logIndex": 0,
                        "fromWallet": rider.address,
                        "driverWallet": "0x00000000000000000000000000000000000000d1",
                    }
                ]
            },
        )
        assert webhook_response.status_code == 200
        assert webhook_response.json()["processed"] == 1

        ride_response = client.get(
            f"/api/v1/rides/{ride_id}",
            headers={"Authorization": f"Bearer {rider_token}"},
        )
        assert ride_response.status_code == 200
        ride = ride_response.json()
        assert ride["status"] == "ONCHAIN_ACCEPTED"
        assert ride["selectedDriverWallet"] == "0x00000000000000000000000000000000000000d1"

        tx_status_response = client.get("/api/v1/tx/0xabc123")
        assert tx_status_response.status_code == 200
        tx_status = tx_status_response.json()
        assert tx_status["status"] == "confirmed"
        assert tx_status["chainId"] == 11155111
        assert tx_status["rideRequestId"] == ride_id


def test_chain_event_webhook_is_idempotent_for_duplicates() -> None:
    clean_tables()

    with create_test_client() as client:
        payload = {
            "events": [
                {
                    "eventName": "RideStarted",
                    "txHash": "0xdef456",
                    "chainId": 11155111,
                    "logIndex": 1,
                    "fromWallet": "0x00000000000000000000000000000000000000a1",
                }
            ]
        }
        first = client.post("/api/v1/webhooks/chain-events", json=payload)
        second = client.post("/api/v1/webhooks/chain-events", json=payload)

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["processed"] == 1
        assert second.json()["processed"] == 0
