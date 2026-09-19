from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Aegis Search & Research Engine"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Database URLs
    DATABASE_URL: str = "postgresql+asyncpg://aegis:aegis_password@localhost:5432/aegis"
    SYNC_DATABASE_URL: str = "postgresql+psycopg2://aegis:aegis_password@localhost:5432/aegis"
    FALLBACK_SQLITE_URL: str = "sqlite+aiosqlite:///./aegis_local.db"
    USE_SQLITE_FALLBACK: bool = True

    # Derived Storage Services
    OPENSEARCH_URL: str = "http://localhost:9200"
    QDRANT_URL: str = "http://localhost:6333"
    REDIS_URL: str = "redis://localhost:6379/0"
    OLLAMA_URL: str = "http://localhost:11434"

    # Security & CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
