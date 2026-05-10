from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gateway_token: str | None = None
    creon_account_no: str | None = None
    creon_goods_code: str = "01"
    allow_live_trading: bool = False
    i_understand_loss_risk: bool = False

    @property
    def live_trading_enabled(self) -> bool:
        return self.allow_live_trading and self.i_understand_loss_risk


settings = GatewaySettings()
