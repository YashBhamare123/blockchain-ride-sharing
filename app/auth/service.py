import secrets
from datetime import UTC, datetime, timedelta

import jwt
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import HTTPException, status

from app.config import settings
from app.db import Database


def wallet_message(nonce: str) -> str:
    return f"Sign this nonce to login: {nonce}"


class AuthService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def create_nonce(self, wallet: str) -> tuple[str, datetime]:
        if not self.db.pool:
            raise RuntimeError("Database is not connected")

        clean_wallet = wallet.lower()
        nonce = secrets.token_hex(16)
        expires_at = datetime.now(UTC) + timedelta(seconds=settings.nonce_ttl_seconds)

        async with self.db.pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO auth_nonces(wallet_address, nonce, expires_at, used)
                VALUES ($1, $2, $3, FALSE)
                """,
                clean_wallet,
                nonce,
                expires_at,
            )

        return nonce, expires_at

    async def verify_nonce_signature(self, wallet: str, nonce: str, signature: str) -> str:
        if not self.db.pool:
            raise RuntimeError("Database is not connected")

        clean_wallet = wallet.lower()
        async with self.db.pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT wallet_address, nonce, expires_at, used
                FROM auth_nonces
                WHERE wallet_address = $1 AND nonce = $2
                """,
                clean_wallet,
                nonce,
            )

            if not row:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid nonce")
            if row["used"]:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nonce already used")
            if row["expires_at"] < datetime.now(UTC):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nonce expired")

            message = encode_defunct(text=wallet_message(nonce))
            recovered = Account.recover_message(message, signature=signature).lower()
            if recovered != clean_wallet:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

            await connection.execute(
                """
                UPDATE auth_nonces
                SET used = TRUE
                WHERE wallet_address = $1 AND nonce = $2
                """,
                clean_wallet,
                nonce,
            )

        payload = {
            "sub": clean_wallet,
            "exp": datetime.now(UTC) + timedelta(seconds=settings.access_token_ttl_seconds),
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    def read_wallet_from_token(self, token: str) -> str:
        try:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
            return str(payload["sub"])
        except Exception as error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from error

