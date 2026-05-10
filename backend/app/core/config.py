from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://stock_pilot:stock_pilot@localhost:5432/stock_pilot"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.4-mini"

    broker_mode: Literal["paper", "creon", "creon_gateway"] = "paper"
    auto_execute: bool = False
    allow_live_trading: bool = False
    i_understand_loss_risk: bool = False

    max_order_krw: int = Field(default=500_000, ge=0)
    max_position_krw: int = Field(default=1_000_000, ge=0)
    max_daily_loss_krw: int = Field(default=200_000, ge=0)
    min_decision_confidence: float = Field(default=0.62, ge=0, le=1)

    creon_account_no: str | None = None
    creon_goods_code: str = "01"
    creon_order_market: str = "KRX"
    creon_gateway_url: str = "http://127.0.0.1:8765"
    creon_gateway_token: str | None = None
    creon_gateway_timeout_seconds: int = Field(default=10, ge=1, le=120)

    cors_origins: list[str] = ["http://localhost:19006", "http://localhost:8081"]

    @property
    def live_trading_enabled(self) -> bool:
        return (
            self.broker_mode in {"creon", "creon_gateway"}
            and self.allow_live_trading
            and self.i_understand_loss_risk
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
