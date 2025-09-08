from __future__ import annotations

from typing import cast

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env",), env_prefix="", case_sensitive=False)

    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    UNIVERSALIS_BASE: AnyHttpUrl = Field(default=cast(AnyHttpUrl, "https://universalis.app/api"))
    XIVAPI_BASE: AnyHttpUrl = Field(default=cast(AnyHttpUrl, "https://xivapi.com"))

    CACHE_TTL_SHORT: int = Field(default=600, ge=0)
    CACHE_TTL_LONG: int = Field(default=43200, ge=0)

    USER_AGENT: str = Field(default="FFXIV-Broker/1.0")
    REQUESTS_RPS: int = Field(default=20, ge=1)
    RETRY_MAX: int = Field(default=3, ge=0)

    LOG_LEVEL: str = Field(default="INFO")

    # Optional whitelists (comma-separated)
    ALLOWED_WORLDS: str | None = None
    ALLOWED_DATA_CENTERS: str | None = None

    def allowed_worlds(self) -> set[str] | None:
        if not self.ALLOWED_WORLDS:
            return None
        return {w.strip() for w in self.ALLOWED_WORLDS.split(",") if w.strip()}

    def allowed_dcs(self) -> set[str] | None:
        if not self.ALLOWED_DATA_CENTERS:
            return None
        return {d.strip() for d in self.ALLOWED_DATA_CENTERS.split(",") if d.strip()}


settings = Settings()
