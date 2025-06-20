from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    SUPABASE_URL:str
    SUPABASE_SERVICE_ROLE_KEY:str
    FOXWAY_SUPABASE_ID:str
    FOXWAY_API_KEY:str
    KOMSA_URL:str
    KOMSA_SUPABASE_ID:str
    DIPLI_RECYCLE_API_KEY:str
    DIPLI_RECYCLE_URL:str
    DIPLI_RECYCLE_SUPABASE_ID:str
    
    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:

    return Settings() # type: ignore - Pydantic-settings handles loading from env
