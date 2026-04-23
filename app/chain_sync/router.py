from fastapi import APIRouter, Depends, Request

from app.chain_sync.schemas import ChainEventsWebhookRequest, ChainEventsWebhookResponse, TxStatusResponse
from app.chain_sync.service import ChainSyncService

router = APIRouter(tags=["chain-sync"])


def get_chain_sync_service(request: Request) -> ChainSyncService:
    return request.app.state.chain_sync_service


@router.post("/webhooks/chain-events", response_model=ChainEventsWebhookResponse)
async def ingest_chain_events(
    payload: ChainEventsWebhookRequest,
    chain_sync_service: ChainSyncService = Depends(get_chain_sync_service),
) -> ChainEventsWebhookResponse:
    return await chain_sync_service.ingest_events(payload)


@router.get("/tx/{tx_hash}", response_model=TxStatusResponse)
async def get_tx_status(
    tx_hash: str,
    chain_sync_service: ChainSyncService = Depends(get_chain_sync_service),
) -> TxStatusResponse:
    return await chain_sync_service.get_tx_status(tx_hash)
