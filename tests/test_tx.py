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


def setup_selected_ride(client: TestClient, rider_token: str, driver_token: str) -> tuple[str, str]:
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
        json={"etaSeconds": 420, "quotedFareWei": "900000000000000"},
    )
    offer_id = offer_response.json()["id"]

    client.post(
        f"/api/v1/rides/{ride_id}/select-driver",
        headers={"Authorization": f"Bearer {rider_token}"},
        json={"offerId": offer_id},
    )
    return ride_id, "900000000000000"


def test_prepare_accept_ride_happy_path() -> None:
    clean_tables()
    rider = Account.create()
    driver = Account.create()

    with create_test_client() as client:
        rider_token = make_token(client, rider)
        driver_token = make_token(client, driver)
        ride_id, selected_fare = setup_selected_ride(client, rider_token, driver_token)

        response = client.post(
            "/api/v1/tx/accept-ride",
            headers={"Authorization": f"Bearer {rider_token}"},
            json={
                "rideId": ride_id,
                "driverSignature": "0xabc123",
                "ceilingEnabled": True,
                "chainId": 11155111,
                "driverNonce": 0,
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["functionName"] == "acceptRide"
        assert body["rideId"] == ride_id
        assert body["fareWei"] == selected_fare
        assert body["ceilingBondWei"] == "180000000000000"
        assert body["requiredMsgValueWei"] == "1080000000000000"


def test_prepare_accept_ride_forbidden_for_non_owner() -> None:
    clean_tables()
    rider = Account.create()
    driver = Account.create()
    other = Account.create()

    with create_test_client() as client:
        rider_token = make_token(client, rider)
        driver_token = make_token(client, driver)
        other_token = make_token(client, other)
        ride_id, _ = setup_selected_ride(client, rider_token, driver_token)

        response = client.post(
            "/api/v1/tx/accept-ride",
            headers={"Authorization": f"Bearer {other_token}"},
            json={"rideId": ride_id, "driverSignature": "0xabc123"},
        )
        assert response.status_code == 403
