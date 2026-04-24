import os

import httpx
from eth_account import Account
from eth_utils import keccak, to_canonical_address, to_checksum_address
from fastapi import HTTPException, status

from app.config import settings


def _build_register_driver_calldata(driver_address: str) -> bytes:
    """
    Encodes the calldata for registerDriver(address d, bytes32 id, bytes32 doc).
    We derive id and doc deterministically from the driver address so the owner
    doesn't have to supply them — they can be overridden later via governance.
    """
    # Function selector: keccak256("registerDriver(address,bytes32,bytes32)")[:4]
    selector = keccak(text="registerDriver(address,bytes32,bytes32)")[:4]

    # ABI-encode the three params (each slot is 32 bytes)
    addr_bytes = b"\x00" * 12 + to_canonical_address(driver_address)  # address left-padded to 32
    # Use keccak of the address as the id hash (unique per driver)
    id_hash = keccak(to_canonical_address(driver_address))
    # Use keccak of (address + "doc") as the doc hash — placeholder
    doc_hash = keccak(to_canonical_address(driver_address) + b"doc")

    return selector + addr_bytes + id_hash + doc_hash


class AdminService:
    def __init__(self) -> None:
        pass

    async def register_driver_onchain(self, driver_address: str) -> str:
        """
        Calls registerDriver(driverAddress, id, doc) on-chain using the owner
        (treasury) private key. Returns the submitted tx hash.
        """
        private_key = settings.treasury_private_key
        if not private_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="TREASURY_PRIVATE_KEY not configured",
            )

        rpc_url = settings.chain_rpc_url.strip()
        if not rpc_url:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="CHAIN_RPC_URL not configured — add it to backend/.env",
            )

        contract_address = settings.carpool_contract_address
        if not contract_address or contract_address == "0x0000000000000000000000000000000000000000":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="CARPOOL_CONTRACT_ADDRESS not configured",
            )
        contract_address = to_checksum_address(settings.carpool_contract_address)

        account = Account.from_key(private_key)

        async with httpx.AsyncClient(timeout=60.0) as client:
            # 1. Get nonce for the owner account
            nonce_resp = await client.post(rpc_url, json={
                "jsonrpc": "2.0", "id": 1, "method": "eth_getTransactionCount",
                "params": [account.address, "pending"],
            })
            nonce_resp.raise_for_status()
            nonce = int(nonce_resp.json()["result"], 16)

            # 2. Get current gas price
            gas_resp = await client.post(rpc_url, json={
                "jsonrpc": "2.0", "id": 2, "method": "eth_gasPrice", "params": [],
            })
            gas_resp.raise_for_status()
            gas_price = int(gas_resp.json()["result"], 16)

            # 3. Get chain ID
            chain_resp = await client.post(rpc_url, json={
                "jsonrpc": "2.0", "id": 3, "method": "eth_chainId", "params": [],
            })
            chain_resp.raise_for_status()
            chain_id = int(chain_resp.json()["result"], 16)

            # 4. Build calldata
            calldata = _build_register_driver_calldata(driver_address)

            # 5. Sign the transaction
            tx = {
                "to": contract_address,
                "data": "0x" + calldata.hex(),
                "gas": 200_000,
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": chain_id,
                "value": 0,
            }
            signed = account.sign_transaction(tx)

            # 6. Broadcast
            send_resp = await client.post(rpc_url, json={
                "jsonrpc": "2.0", "id": 4, "method": "eth_sendRawTransaction",
                "params": ["0x" + signed.raw_transaction.hex()],
            })
            send_resp.raise_for_status()
            result = send_resp.json()

            if "error" in result:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"RPC error: {result['error'].get('message', result['error'])}",
                )

            return result["result"]  # tx hash
