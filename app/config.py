from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import List, Any
import json

class Settings(BaseSettings):
    bot_token: str
    admin_ids: List[int] = Field(default_factory=list)
    log_level: str = "INFO"
    
    bot_mode: str = "polling"
    webhook_base_url: str | None = None
    webhook_secret: str | None = None
    database_url: str = "postgresql://user:password@localhost/dbname"
    port: int = 10000
    payments_enabled: bool = False
    
    llm_api_key: str | None = None
    llm_provider: str | None = None

    @field_validator('admin_ids', mode='before')
    @classmethod
    def parse_admin_ids(cls, v: Any) -> List[int]:
        if isinstance(v, (int, float)):
            return [int(v)]
        if isinstance(v, str):
            if not v.strip():
                return []
            if v.startswith('[') and v.endswith(']'):
                return json.loads(v)
            return [int(x.strip()) for x in v.split(',') if x.strip()]
        return v

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
