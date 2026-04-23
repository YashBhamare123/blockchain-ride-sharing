from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.auth.router import router as auth_router
from app.auth.service import AuthService
from app.db import Database
from app.marketplace.router import router as marketplace_router
from app.marketplace.service import MarketplaceService
from app.maps.router import router as maps_router
from app.maps.service import MapsService
from app.pricing.router import router as pricing_router
from app.pricing.service import PricingService
from app.treasury.router import router as treasury_router
from app.treasury.service import TreasurySignerService
from app.tx.router import router as tx_router
from app.tx.service import TxService


def create_app(init_db: bool = True) -> FastAPI:
    database = Database()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if init_db:
            await database.connect()
        app.state.auth_service = AuthService(database)
        app.state.maps_service = MapsService()
        app.state.pricing_service = PricingService()
        app.state.marketplace_service = MarketplaceService(database)
        app.state.tx_service = TxService(database)
        app.state.treasury_service = TreasurySignerService(database)
        yield
        if init_db:
            await database.close()

    app = FastAPI(title="Ride Sharing Backend", lifespan=lifespan)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(marketplace_router, prefix="/api/v1")
    app.include_router(maps_router, prefix="/api/v1")
    app.include_router(pricing_router, prefix="/api/v1")
    app.include_router(treasury_router, prefix="/api/v1")
    app.include_router(tx_router, prefix="/api/v1")
    return app


app = create_app()

