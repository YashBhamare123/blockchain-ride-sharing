from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import HTTPException, status

from app.config import settings
from app.db import Database
from app.treasury.schemas import CompleteRideSignRequest, CompleteRideSignResponse


class TreasurySignerService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def sign_complete_ride(self, wallet: str, ride_id: str, payload: CompleteRideSignRequest) -> CompleteRideSignResponse:
        if not settings.treasury_private_key:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Missing treasury private key")
        if not self.db.pool:
            raise RuntimeError("Database is not connected")

        wallet = wallet.lower()

        async with self.db.pool.acquire() as connection:
            ride = await connection.fetchrow("SELECT * FROM ride_requests WHERE id = $1", ride_id)
            if not ride:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")

            rider_wallet = str(ride["rider_wallet"]).lower()
            driver_wallet = (ride["selected_driver_wallet"] or "").lower()
            if not driver_wallet:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Ride has no selected driver",
                )
            if wallet not in {rider_wallet, driver_wallet}:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only rider or selected driver can request completion signature",
                )

        message_hash = _build_complete_hash(
            on_chain_ride_id=payload.onChainRideId,
            final_fare_wei=int(payload.finalFareWei),
            rider_wallet=rider_wallet,
            driver_wallet=driver_wallet,
            chain_id=payload.chainId,
        )
        signed = Account.sign_message(encode_defunct(primitive=message_hash), settings.treasury_private_key)

        return CompleteRideSignResponse(
            treasurySignature=signed.signature.to_0x_hex(),
            onChainRideId=payload.onChainRideId,
            finalFareWei=payload.finalFareWei,
            riderWallet=rider_wallet,
            driverWallet=driver_wallet,
            chainId=payload.chainId,
        )


def _build_complete_hash(
    on_chain_ride_id: int,
    final_fare_wei: int,
    rider_wallet: str,
    driver_wallet: str,
    chain_id: int,
) -> bytes:
    from eth_utils import keccak, to_canonical_address

    packed = (
        b"COMPLETE"
        + on_chain_ride_id.to_bytes(32, byteorder="big")
        + final_fare_wei.to_bytes(32, byteorder="big")
        + to_canonical_address(rider_wallet)
        + to_canonical_address(driver_wallet)
        + chain_id.to_bytes(32, byteorder="big")
    )
    return keccak(packed)

