from typing import Literal
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str
    database_url: str
    bot_mode: Literal["polling", "webhook"] = "polling"
    webhook_base_url: str | None = None
    webhook_secret: str | None = None
    port: int = 10000
    admin_ids: list[int] = Field(default_factory=list)
    payments_enabled: bool = False
    stars_price: int = Field(default=149, ge=1, le=10000)
    support_contact: str = ""
    log_level: str = "INFO"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_deploy(self):
        import re

        if self.bot_mode == "webhook":
            if not self.webhook_base_url or not self.webhook_base_url.startswith(
                "https://"
            ):
                raise ValueError("WEBHOOK_BASE_URL must start with https://")
            if not self.webhook_secret or not re.fullmatch(
                r"[A-Za-z0-9_-]{32,256}", self.webhook_secret
            ):
                raise ValueError("WEBHOOK_SECRET: 32–256 letters, digits, _ or -")
        if self.payments_enabled and not re.fullmatch(
            r"@[A-Za-z0-9_]{5,32}", self.support_contact
        ):
            raise ValueError(
                "Set SUPPORT_CONTACT=@your_support before enabling payments"
            )
        return self


settings = Settings()
