from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # Keycloak / JWT
    KEYCLOAK_JWKS_URL: str = "http://keycloak:8080/realms/factory/protocol/openid-connect/certs"
    KEYCLOAK_AUDIENCE: str = "factory-ai-brain"

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # Downstream services (v2.3 consolidated architecture)
    KNOWLEDGE_ENGINE_URL: str = "http://knowledge-engine:8001"
    TELEMETRY_AGGREGATOR_URL: str = "http://telemetry-aggregator:8002"

    # Auth
    AUTH_ENABLED: bool = False

    # Redis
    REDIS_URL: str = "redis://:ikb_redis_2024@redis:6379/0"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
