import os


class Settings:
    def __init__(self) -> None:
        self.database_url = os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:password@localhost:5432/offchain",
        )
        self.jwt_secret = os.getenv("JWT_SECRET", "dev-secret")
        self.jwt_algorithm = "HS256"
        self.nonce_ttl_seconds = 300
        self.access_token_ttl_seconds = 3600
        self.google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
        self.google_maps_default_country = os.getenv("GOOGLE_MAPS_DEFAULT_COUNTRY", "")
        self.google_maps_timeout_seconds = float(os.getenv("GOOGLE_MAPS_TIMEOUT_SECONDS", "8"))
        self.base_fare_wei = int(os.getenv("BASE_FARE_WEI", "200000000000000"))
        self.per_km_rate_wei = int(os.getenv("PER_KM_RATE_WEI", "70000000000000"))
        self.per_min_rate_wei = int(os.getenv("PER_MIN_RATE_WEI", "10000000000000"))
        self.service_fee_percent = float(os.getenv("SERVICE_FEE_PERCENT", "5"))
        self.min_fare_wei = int(os.getenv("MIN_FARE_WEI", "250000000000000"))
        self.surge_multiplier = float(os.getenv("SURGE_MULTIPLIER", "1.0"))
        self.ceiling_bond_percent = float(os.getenv("CEILING_BOND_PERCENT", "20"))
        self.carpool_contract_address = os.getenv(
            "CARPOOL_CONTRACT_ADDRESS",
            "0x0000000000000000000000000000000000000000",
        )
        self.treasury_private_key = os.getenv("TREASURY_PRIVATE_KEY", "")


settings = Settings()

