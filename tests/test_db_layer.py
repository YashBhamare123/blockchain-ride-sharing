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
            await conn.execute("DELETE FROM sessions")
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


def create_selected_ride(client: TestClient, rider_token: str, driver_token: str) -> str:
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
    ride_id = ride_response.json()["id"]

    offer_response = client.post(
        f"/api/v1/rides/{ride_id}/offers",
        headers={"Authorization": f"Bearer {driver_token}"},
        json={"etaSeconds": 350, "quotedFareWei": "800000000000000"},
    )
    offer_id = offer_response.json()["id"]

    client.post(
        f"/api/v1/rides/{ride_id}/select-driver",
        headers={"Authorization": f"Bearer {rider_token}"},
        json={"offerId": offer_id},
    )
    return ride_id


def test_logout_revokes_session_record() -> None:
    clean_tables()
    rider = Account.create()

    with create_test_client() as client:
        token = make_token(client, rider)
        logout_response = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert logout_response.status_code == 200
        assert logout_response.json()["success"] is True

        async def _check() -> int:
            conn = await asyncpg.connect(TEST_DB_URL)
            try:
                row = await conn.fetchrow("SELECT COUNT(*) AS c FROM sessions WHERE revoked = TRUE")
                return int(row["c"])
            finally:
                await conn.close()

        revoked_count = asyncio.run(_check())
        assert revoked_count >= 1


def test_location_stream_write_and_latest_read() -> None:
    clean_tables()
    rider = Account.create()
    driver = Account.create()

    with create_test_client() as client:
        rider_token = make_token(client, rider)
        driver_token = make_token(client, driver)
        ride_id = create_selected_ride(client, rider_token, driver_token)

        post_response = client.post(
            f"/api/v1/rides/{ride_id}/locations",
            headers={"Authorization": f"Bearer {driver_token}"},
            json={"lat": 12.9361, "lng": 77.6121, "heading": 135.5, "speed": 7.2},
        )
        assert post_response.status_code == 200

        latest_response = client.get(
            f"/api/v1/rides/{ride_id}/locations/latest",
            headers={"Authorization": f"Bearer {rider_token}"},
        )
        assert latest_response.status_code == 200
        latest = latest_response.json()
        assert latest["rideId"] == ride_id
        assert latest["lat"] == 12.9361
        assert latest["lng"] == 77.6121


def test_tx_record_persist_and_read_status() -> None:
    clean_tables()
    rider = Account.create()

    with create_test_client() as client:
        rider_token = make_token(client, rider)
        record_response = client.post(
            "/api/v1/tx/record",
            headers={"Authorization": f"Bearer {rider_token}"},
            json={
                "txHash": "0xfeed1234",
                "chainId": 11155111,
                "action": "acceptRide",
                "status": "submitted",
            },
        )
        assert record_response.status_code == 200
        assert record_response.json()["txHash"] == "0xfeed1234"

        status_response = client.get("/api/v1/tx/0xfeed1234")
        assert status_response.status_code == 200
        body = status_response.json()
        assert body["txHash"] == "0xfeed1234"
        assert body["status"] in {"submitted", "pending"}
