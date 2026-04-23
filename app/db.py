import asyncpg

from app.config import settings


class Database:
    def __init__(self) -> None:
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(settings.database_url)
        await self._create_tables()

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()
            self.pool = None

    async def _create_tables(self) -> None:
        if not self.pool:
            return
        async with self.pool.acquire() as connection:
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    wallet_address TEXT PRIMARY KEY,
                    role TEXT NOT NULL DEFAULT 'rider',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS auth_nonces (
                    wallet_address TEXT NOT NULL,
                    nonce TEXT NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL,
                    used BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (wallet_address, nonce)
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    jwt_id TEXT PRIMARY KEY,
                    wallet_address TEXT NOT NULL REFERENCES users(wallet_address) ON DELETE CASCADE,
                    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    expires_at TIMESTAMPTZ NOT NULL,
                    revoked BOOLEAN NOT NULL DEFAULT FALSE
                );

                CREATE TABLE IF NOT EXISTS drivers (
                    wallet_address TEXT PRIMARY KEY REFERENCES users(wallet_address) ON DELETE CASCADE,
                    availability TEXT NOT NULL DEFAULT 'offline',
                    current_status TEXT NOT NULL DEFAULT 'verified',
                    last_lat DOUBLE PRECISION,
                    last_lng DOUBLE PRECISION,
                    last_seen_at TIMESTAMPTZ,
                    rating_avg DOUBLE PRECISION NOT NULL DEFAULT 0,
                    rating_count INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS ride_requests (
                    id TEXT PRIMARY KEY,
                    rider_wallet TEXT NOT NULL REFERENCES users(wallet_address),
                    pickup_lat DOUBLE PRECISION NOT NULL,
                    pickup_lng DOUBLE PRECISION NOT NULL,
                    pickup_address TEXT NOT NULL,
                    drop_lat DOUBLE PRECISION NOT NULL,
                    drop_lng DOUBLE PRECISION NOT NULL,
                    drop_address TEXT NOT NULL,
                    distance_meters INTEGER,
                    duration_seconds INTEGER,
                    tip_type TEXT,
                    tip_value DOUBLE PRECISION,
                    tip_wei TEXT,
                    selected_driver_wallet TEXT,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS driver_offers (
                    id TEXT PRIMARY KEY,
                    ride_request_id TEXT NOT NULL REFERENCES ride_requests(id) ON DELETE CASCADE,
                    driver_wallet TEXT NOT NULL REFERENCES users(wallet_address),
                    eta_seconds INTEGER NOT NULL,
                    quoted_fare_wei TEXT NOT NULL,
                    message TEXT,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS ride_locations (
                    id BIGSERIAL PRIMARY KEY,
                    ride_request_id TEXT NOT NULL REFERENCES ride_requests(id) ON DELETE CASCADE,
                    driver_wallet TEXT NOT NULL REFERENCES users(wallet_address),
                    lat DOUBLE PRECISION NOT NULL,
                    lng DOUBLE PRECISION NOT NULL,
                    heading DOUBLE PRECISION,
                    speed DOUBLE PRECISION,
                    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS tx_records (
                    id BIGSERIAL PRIMARY KEY,
                    ride_request_id TEXT,
                    action TEXT NOT NULL,
                    tx_hash TEXT UNIQUE NOT NULL,
                    chain_id INTEGER NOT NULL,
                    from_wallet TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'submitted',
                    block_number BIGINT,
                    confirmed_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS chain_events (
                    id BIGSERIAL PRIMARY KEY,
                    tx_hash TEXT NOT NULL,
                    log_index INTEGER NOT NULL DEFAULT 0,
                    event_name TEXT NOT NULL,
                    chain_id INTEGER NOT NULL,
                    ride_request_id TEXT,
                    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE(tx_hash, log_index, event_name)
                );

                CREATE INDEX IF NOT EXISTS idx_ride_requests_status_created_at
                    ON ride_requests(status, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_driver_offers_ride_request_status
                    ON driver_offers(ride_request_id, status);

                CREATE INDEX IF NOT EXISTS idx_tx_records_status_created_at
                    ON tx_records(status, created_at DESC);
                """
            )

