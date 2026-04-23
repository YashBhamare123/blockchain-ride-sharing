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


def clean_auth_nonce_table() -> None:
    async def _clean() -> None:
        conn = await asyncpg.connect(TEST_DB_URL)
        try:
            await conn.execute("DELETE FROM auth_nonces")
        finally:
            await conn.close()

    asyncio.run(_clean())


def create_test_client() -> TestClient:
    app = create_app(init_db=True)
    return TestClient(app)


def test_nonce_endpoint_returns_nonce_and_expiry() -> None:
    clean_auth_nonce_table()
    with create_test_client() as client:
        response = client.post("/api/v1/auth/nonce", json={"wallet": "0x0000000000000000000000000000000000000abc"})
        body = response.json()
        assert response.status_code == 200
        assert len(body["nonce"]) > 0
        assert "expiresAt" in body


def test_verify_endpoint_returns_access_token_for_valid_signature() -> None:
    clean_auth_nonce_table()
    account = Account.create()
    wallet = account.address

    with create_test_client() as client:
        nonce_response = client.post("/api/v1/auth/nonce", json={"wallet": wallet})
        nonce = nonce_response.json()["nonce"]

        message = encode_defunct(text=wallet_message(nonce))
        signed = Account.sign_message(message, account.key)

        verify_response = client.post(
            "/api/v1/auth/verify",
            json={"wallet": wallet, "nonce": nonce, "signature": signed.signature.to_0x_hex()},
        )
        assert verify_response.status_code == 200
        assert len(verify_response.json()["accessToken"]) > 0


def test_me_endpoint_returns_wallet_from_bearer_token() -> None:
    clean_auth_nonce_table()
    account = Account.create()
    wallet = account.address

    with create_test_client() as client:
        nonce_response = client.post("/api/v1/auth/nonce", json={"wallet": wallet})
        nonce = nonce_response.json()["nonce"]

        message = encode_defunct(text=wallet_message(nonce))
        signed = Account.sign_message(message, account.key)

        verify_response = client.post(
            "/api/v1/auth/verify",
            json={"wallet": wallet, "nonce": nonce, "signature": signed.signature.to_0x_hex()},
        )
        token = verify_response.json()["accessToken"]

        me_response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_response.status_code == 200
        assert me_response.json()["wallet"] == wallet.lower()
