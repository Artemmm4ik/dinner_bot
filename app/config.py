from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List

class Settings(BaseSettings):
    bot_token: str
    database_path: str = "./data/dinner_bot.sqlite3"
    admin_ids: List[int] = Field(default_factory=list)
    log_level: str = "INFO"
    
    llm_api_key: str | None = None
    llm_provider: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
