from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


GATEWAY_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = GATEWAY_DIR.parent


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", GATEWAY_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gateway_token: str | None = None
    creon_account_no: str | None = None
    creon_goods_code: str = "01"
    allow_live_trading: bool = False
    i_understand_loss_risk: bool = False
    creon_quote_retry_count: int = Field(default=1, ge=0, le=5)
    creon_quote_retry_backoff_seconds: float = Field(default=0.25, ge=0, le=5)
    creon_com_lock_timeout_seconds: float = Field(default=15, ge=1, le=120)

    @property
    def live_trading_enabled(self) -> bool:
        return self.allow_live_trading and self.i_understand_loss_risk


settings = GatewaySettings()
