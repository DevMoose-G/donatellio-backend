# app/settings.py

from pydantic import Field, AnyUrl
from pydantic_settings import BaseSettings
from dotenv import load_dotenv, find_dotenv

# walk up until you hit the first .env
load_dotenv(find_dotenv())

class Settings(BaseSettings):
    # Redis
    redis_url: str = Field(..., env="REDIS_URL")

    # PostgreSQL (asyncpg)
    database_url: str = Field(..., env="DATABASE_URL")
    database_sync_url: str = Field(..., env="DATABASE_SYNC_URL")

    # OpenAI
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")

    # GPU provider keys
    runpod_api_key: str = Field(..., env="RUNPOD_API_KEY")
    lambdalabs_api_key: str = Field(..., env="LAMBDALABS_API_KEY")

    # Defaults
    default_provider: str = Field("runpod", env="DEFAULT_PROVIDER")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Instantiate for import elsewhere
settings = Settings()
