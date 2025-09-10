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

    # Optional bootstrap of local catalog file at startup (id->name JSON)
    CATALOG_BOOTSTRAP_PATH: str | None = Field(default="data/catalog_names_en.json")

    # Advice tuning (weights, thresholds)
    ADVICE_W_ROI: float = Field(default=0.7, ge=0.0)
    ADVICE_W_SPD: float = Field(default=0.5, ge=0.0)
    ADVICE_W_PPD: float = Field(default=0.4, ge=0.0)
    ADVICE_SPD_NORM: float = Field(default=10.0, gt=0.0)
    ADVICE_PPD_NORM: float = Field(default=50000.0, gt=0.0)
    ADVICE_PENALTY_SATURO: float = Field(default=0.2, ge=0.0)
    ADVICE_PENALTY_INSTABILE: float = Field(default=0.2, ge=0.0)
    ADVICE_PENALTY_COMP: float = Field(default=0.1, ge=0.0)
    ADVICE_RISK_LOW: float = Field(default=0.3, ge=0.0, le=1.0)
    ADVICE_RISK_MED: float = Field(default=0.6, ge=0.0, le=1.0)
    ADVICE_SATURATION_MULT: float = Field(default=5.0, gt=0.0)
    FLIP_THRESHOLD: float = Field(default=0.7, gt=0.0, le=1.0)

    # Suspicious detection (anti-scam)
    ADVICE_SUSPECT_ROI: float = Field(default=10.0, ge=0.0)  # 1000%+
    ADVICE_SUSPECT_CV: float = Field(default=1.5, ge=0.0)
    ADVICE_SUSPECT_ABS_PROFIT: int = Field(default=200_000, ge=0)  # gil/unit
    ADVICE_MIN_SALES_SAFE: int = Field(default=5, ge=0)

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
