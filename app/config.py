from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_version: str = "1.0.0"
    docs_enabled: bool = True
    cors_origins: str = "*"

    @field_validator("cors_origins")
    @classmethod
    def cors_origins_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("CORS_ORIGINS must not be blank — use '*' for open or a comma-separated list of origins")
        return v

    @property
    def docs_url(self) -> str | None:
        return "/docs" if self.docs_enabled else None

    @property
    def redoc_url(self) -> str | None:
        return "/redoc" if self.docs_enabled else None

    @property
    def cors_origins_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

# Backward-compatible module-level names — app/main.py imports these unchanged
APP_VERSION  = settings.app_version
DOCS_URL     = settings.docs_url
REDOC_URL    = settings.redoc_url
CORS_ORIGINS = settings.cors_origins_list
