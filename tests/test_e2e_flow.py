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


def test_full_e2e_user_flow_happy_path() -> None:
    clean_tables()
    rider = Account.create()
    driver1 = Account.create()
    driver2 = Account.create()
    treasury = Account.create()
    settings.treasury_private_key = treasury.key.hex()

    with create_test_client() as client:
        rider_token = make_token(client, rider)
        driver1_token = make_token(client, driver1)
        driver2_token = make_token(client, driver2)

        pricing_response = client.post(
            "/api/v1/pricing/estimate",
            json={
                "distanceMeters": 6200,
                "durationSeconds": 1320,
                "tipType": "percent",
                "tipValue": 8,
                "ceilingEnabled": True,
            },
        )
        assert pricing_response.status_code == 200

        ride_response = client.post(
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
                "tipWei": "71736000000000",
            },
        )
        assert ride_response.status_code == 200
        ride_id = ride_response.json()["id"]

        offer1 = client.post(
            f"/api/v1/rides/{ride_id}/offers",
            headers={"Authorization": f"Bearer {driver1_token}"},
            json={"etaSeconds": 420, "quotedFareWei": "900000000000000", "message": "can do quickly"},
        )
        offer2 = client.post(
            f"/api/v1/rides/{ride_id}/offers",
            headers={"Authorization": f"Bearer {driver2_token}"},
            json={"etaSeconds": 480, "quotedFareWei": "860000000000000", "message": "best price"},
        )
        assert offer1.status_code == 200
        assert offer2.status_code == 200

        select = client.post(
            f"/api/v1/rides/{ride_id}/select-driver",
            headers={"Authorization": f"Bearer {rider_token}"},
            json={"offerId": offer2.json()["id"]},
        )
        assert select.status_code == 200
        assert select.json()["selectedDriverWallet"] == driver2.address.lower()

        accept_prep = client.post(
            "/api/v1/tx/accept-ride",
            headers={"Authorization": f"Bearer {rider_token}"},
            json={
                "rideId": ride_id,
                "driverSignature": "0xdriver_sig",
                "ceilingEnabled": True,
                "chainId": 11155111,
                "driverNonce": 3,
            },
        )
        assert accept_prep.status_code == 200
        assert accept_prep.json()["requiredMsgValueWei"] == "1032000000000000"

        tx_record = client.post(
            "/api/v1/tx/record",
            headers={"Authorization": f"Bearer {rider_token}"},
            json={
                "txHash": "0xaaa111",
                "chainId": 11155111,
                "action": "acceptRide",
                "rideRequestId": ride_id,
                "status": "submitted",
            },
        )
        assert tx_record.status_code == 200

        accepted_event = client.post(
            "/api/v1/webhooks/chain-events",
            json={
                "events": [
                    {
                        "eventName": "RideAccepted",
                        "txHash": "0xaaa111",
                        "chainId": 11155111,
                        "rideRequestId": ride_id,
                        "blockNumber": 1001,
                        "logIndex": 0,
                        "fromWallet": rider.address,
                        "driverWallet": driver2.address,
                    }
                ]
            },
        )
        assert accepted_event.status_code == 200
        assert accepted_event.json()["processed"] == 1

        location_write = client.post(
            f"/api/v1/rides/{ride_id}/locations",
            headers={"Authorization": f"Bearer {driver2_token}"},
            json={"lat": 12.9401, "lng": 77.6202, "heading": 90.0, "speed": 10.2},
        )
        assert location_write.status_code == 200

        location_latest = client.get(
            f"/api/v1/rides/{ride_id}/locations/latest",
            headers={"Authorization": f"Bearer {rider_token}"},
        )
        assert location_latest.status_code == 200
        assert location_latest.json()["lat"] == 12.9401

        complete_sign = client.post(
            f"/api/v1/rides/{ride_id}/complete/sign",
            headers={"Authorization": f"Bearer {driver2_token}"},
            json={"onChainRideId": 7, "finalFareWei": "860000000000000", "chainId": 11155111},
        )
        assert complete_sign.status_code == 200
        signature = complete_sign.json()["treasurySignature"]
        message_hash = _build_complete_hash(
            on_chain_ride_id=7,
            final_fare_wei=860000000000000,
            rider_wallet=rider.address.lower(),
            driver_wallet=driver2.address.lower(),
            chain_id=11155111,
        )
        recovered = Account.recover_message(encode_defunct(primitive=message_hash), signature=signature).lower()
        assert recovered == treasury.address.lower()

        completed_event = client.post(
            "/api/v1/webhooks/chain-events",
            json={
                "events": [
                    {
                        "eventName": "RideCompleted",
                        "txHash": "0xbbb222",
                        "chainId": 11155111,
                        "rideRequestId": ride_id,
                        "blockNumber": 1010,
                        "logIndex": 0,
                        "fromWallet": driver2.address,
                        "driverWallet": driver2.address,
                        "status": "confirmed",
                        "action": "completeRide",
                    }
                ]
            },
        )
        assert completed_event.status_code == 200
        assert completed_event.json()["processed"] == 1

        final_ride = client.get(
            f"/api/v1/rides/{ride_id}",
            headers={"Authorization": f"Bearer {rider_token}"},
        )
        assert final_ride.status_code == 200
        assert final_ride.json()["status"] == "COMPLETED"

        tx_status = client.get("/api/v1/tx/0xbbb222")
        assert tx_status.status_code == 200
        assert tx_status.json()["status"] == "confirmed"

        logout = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {rider_token}"})
        assert logout.status_code == 200
        assert logout.json()["success"] is True


def test_e2e_rejected_driver_paths() -> None:
    clean_tables()
    rider = Account.create()
    driver1 = Account.create()
    driver2 = Account.create()

    with create_test_client() as client:
        rider_token = make_token(client, rider)
        driver1_token = make_token(client, driver1)
        driver2_token = make_token(client, driver2)

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

        offer1 = client.post(
            f"/api/v1/rides/{ride_id}/offers",
            headers={"Authorization": f"Bearer {driver1_token}"},
            json={"etaSeconds": 300, "quotedFareWei": "850000000000000"},
        ).json()
        offer2 = client.post(
            f"/api/v1/rides/{ride_id}/offers",
            headers={"Authorization": f"Bearer {driver2_token}"},
            json={"etaSeconds": 310, "quotedFareWei": "840000000000000"},
        ).json()

        client.post(
            f"/api/v1/rides/{ride_id}/select-driver",
            headers={"Authorization": f"Bearer {rider_token}"},
            json={"offerId": offer2["id"]},
        )

        rejected_driver_location = client.post(
            f"/api/v1/rides/{ride_id}/locations",
            headers={"Authorization": f"Bearer {driver1_token}"},
            json={"lat": 12.9, "lng": 77.6},
        )
        assert rejected_driver_location.status_code == 403

        rejected_driver_sign = client.post(
            f"/api/v1/rides/{ride_id}/complete/sign",
            headers={"Authorization": f"Bearer {driver1_token}"},
            json={"onChainRideId": 8, "finalFareWei": "840000000000000", "chainId": 11155111},
        )
        assert rejected_driver_sign.status_code == 403

        tx_404 = client.get("/api/v1/tx/0xdoesnotexist")
        assert tx_404.status_code == 404
