from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import List, Any
import json

class Settings(BaseSettings):
    bot_token: str
    database_path: str = "./data/dinner_bot.sqlite3"
    admin_ids: List[int] = Field(default_factory=list)
    log_level: str = "INFO"
    
    llm_api_key: str | None = None
    llm_provider: str | None = None

    @field_validator('admin_ids', mode='before')
    @classmethod
    def parse_admin_ids(cls, v: Any) -> List[int]:
        if isinstance(v, str):
            if not v.strip():
                return []
            if v.startswith('[') and v.endswith(']'):
                return json.loads(v)
            return [int(x.strip()) for x in v.split(',') if x.strip()]
        return v

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
