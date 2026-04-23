import asyncio
import os

import asyncpg
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

from app.auth.service import wallet_message
from app.config import settings
from app.main import create_app
from app.treasury.service import _build_complete_hash

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


def setup_selected_ride(client: TestClient, rider_token: str, driver_token: str) -> tuple[str, str, str]:
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
    ride = ride_response.json()
    ride_id = ride["id"]
    rider_wallet = ride["riderWallet"]

    offer_response = client.post(
        f"/api/v1/rides/{ride_id}/offers",
        headers={"Authorization": f"Bearer {driver_token}"},
        json={"etaSeconds": 420, "quotedFareWei": "900000000000000"},
    )
    offer = offer_response.json()
    selected_driver_wallet = offer["driverWallet"]

    client.post(
        f"/api/v1/rides/{ride_id}/select-driver",
        headers={"Authorization": f"Bearer {rider_token}"},
        json={"offerId": offer["id"]},
    )
    return ride_id, rider_wallet, selected_driver_wallet


def test_complete_sign_generates_treasury_recoverable_signature() -> None:
    clean_tables()
    rider = Account.create()
    driver = Account.create()
    treasury = Account.create()
    settings.treasury_private_key = treasury.key.hex()

    with create_test_client() as client:
        rider_token = make_token(client, rider)
        driver_token = make_token(client, driver)
        ride_id, rider_wallet, driver_wallet = setup_selected_ride(client, rider_token, driver_token)

        sign_response = client.post(
            f"/api/v1/rides/{ride_id}/complete/sign",
            headers={"Authorization": f"Bearer {driver_token}"},
            json={
                "onChainRideId": 5,
                "finalFareWei": "900000000000000",
                "chainId": 11155111,
            },
        )
        assert sign_response.status_code == 200
        body = sign_response.json()
        signature = body["treasurySignature"]

        hash_bytes = _build_complete_hash(
            on_chain_ride_id=5,
            final_fare_wei=900000000000000,
            rider_wallet=rider_wallet,
            driver_wallet=driver_wallet,
            chain_id=11155111,
        )
        recovered = Account.recover_message(encode_defunct(primitive=hash_bytes), signature=signature).lower()
        assert recovered == treasury.address.lower()


def test_complete_sign_forbidden_for_unrelated_wallet() -> None:
    clean_tables()
    rider = Account.create()
    driver = Account.create()
    unrelated = Account.create()
    treasury = Account.create()
    settings.treasury_private_key = treasury.key.hex()

    with create_test_client() as client:
        rider_token = make_token(client, rider)
        driver_token = make_token(client, driver)
        unrelated_token = make_token(client, unrelated)
        ride_id, _, _ = setup_selected_ride(client, rider_token, driver_token)

        response = client.post(
            f"/api/v1/rides/{ride_id}/complete/sign",
            headers={"Authorization": f"Bearer {unrelated_token}"},
            json={"onChainRideId": 6, "finalFareWei": "900000000000000", "chainId": 11155111},
        )
        assert response.status_code == 403
