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


def test_marketplace_happy_path_create_offer_select() -> None:
    clean_tables()
    rider = Account.create()
    driver1 = Account.create()
    driver2 = Account.create()

    with create_test_client() as client:
        rider_token = make_token(client, rider)
        driver1_token = make_token(client, driver1)
        driver2_token = make_token(client, driver2)

        create_ride_response = client.post(
            "/api/v1/rides",
            headers={"Authorization": f"Bearer {rider_token}"},
            json={
                "pickupLat": 12.9716,
                "pickupLng": 77.5946,
                "pickupAddress": "MG Road, Bengaluru",
                "dropLat": 12.9352,
                "dropLng": 77.6245,
                "dropAddress": "Koramangala, Bengaluru",
                "distanceMeters": 6200,
                "durationSeconds": 1320,
                "tipType": "percent",
                "tipValue": 8,
                "tipWei": "70000000000000",
            },
        )
        assert create_ride_response.status_code == 200
        ride = create_ride_response.json()
        ride_id = ride["id"]
        assert ride["status"] == "OPEN"

        feed_response = client.get(
            "/api/v1/driver-feed/open-rides",
            headers={"Authorization": f"Bearer {driver1_token}"},
        )
        assert feed_response.status_code == 200
        assert any(item["id"] == ride_id for item in feed_response.json()["rides"])

        offer1_response = client.post(
            f"/api/v1/rides/{ride_id}/offers",
            headers={"Authorization": f"Bearer {driver1_token}"},
            json={"etaSeconds": 420, "quotedFareWei": "900000000000000", "message": "Can reach fast"},
        )
        assert offer1_response.status_code == 200
        offer1 = offer1_response.json()

        offer2_response = client.post(
            f"/api/v1/rides/{ride_id}/offers",
            headers={"Authorization": f"Bearer {driver2_token}"},
            json={"etaSeconds": 480, "quotedFareWei": "860000000000000", "message": "Best price"},
        )
        assert offer2_response.status_code == 200
        offer2 = offer2_response.json()

        offers_response = client.get(
            f"/api/v1/rides/{ride_id}/offers",
            headers={"Authorization": f"Bearer {rider_token}"},
        )
        assert offers_response.status_code == 200
        offers = offers_response.json()["offers"]
        assert len(offers) == 2

        select_response = client.post(
            f"/api/v1/rides/{ride_id}/select-driver",
            headers={"Authorization": f"Bearer {rider_token}"},
            json={"offerId": offer2["id"]},
        )
        assert select_response.status_code == 200
        selected_ride = select_response.json()
        assert selected_ride["status"] == "DRIVER_SELECTED"
        assert selected_ride["selectedDriverWallet"] == driver2.address.lower()

        offers_after = client.get(
            f"/api/v1/rides/{ride_id}/offers",
            headers={"Authorization": f"Bearer {rider_token}"},
        ).json()["offers"]
        status_by_id = {item["id"]: item["status"] for item in offers_after}
        assert status_by_id[offer2["id"]] == "SELECTED"
        assert status_by_id[offer1["id"]] == "REJECTED"


def test_only_ride_owner_can_select_driver() -> None:
    clean_tables()
    rider = Account.create()
    other_user = Account.create()
    driver = Account.create()

    with create_test_client() as client:
        rider_token = make_token(client, rider)
        other_token = make_token(client, other_user)
        driver_token = make_token(client, driver)

        ride_response = client.post(
            "/api/v1/rides",
            headers={"Authorization": f"Bearer {rider_token}"},
            json={
                "pickupLat": 12.9716,
                "pickupLng": 77.5946,
                "pickupAddress": "A",
                "dropLat": 12.9352,
                "dropLng": 77.6245,
                "dropAddress": "B",
            },
        )
        ride_id = ride_response.json()["id"]

        offer_response = client.post(
            f"/api/v1/rides/{ride_id}/offers",
            headers={"Authorization": f"Bearer {driver_token}"},
            json={"etaSeconds": 450, "quotedFareWei": "800000000000000"},
        )
        offer_id = offer_response.json()["id"]

        forbidden_response = client.post(
            f"/api/v1/rides/{ride_id}/select-driver",
            headers={"Authorization": f"Bearer {other_token}"},
            json={"offerId": offer_id},
        )
        assert forbidden_response.status_code == 403
