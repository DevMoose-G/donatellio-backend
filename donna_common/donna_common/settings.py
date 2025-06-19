from dotenv import find_dotenv, load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

# walk up until you hit the first .env
load_dotenv(find_dotenv())


class Settings(BaseSettings):
    debug: bool = Field(False, env="DEBUG")

    redis_url: str = Field(..., env="REDIS_URL")

    database_url: str = Field(..., env="DATABASE_URL")
    database_sync_url: str = Field(..., env="DATABASE_SYNC_URL")  # for alembic upgrades

    openai_api_key: str = Field(..., env="OPENAI_API_KEY")

    runpod_api_key: str = Field(..., env="RUNPOD_API_KEY")

    static_dir: str = Field(..., env="STATIC_DIR")
    blender_exe_path: str = Field(..., env="BLENDER_EXE_PATH")

    default_provider: str = Field("runpod", env="DEFAULT_PROVIDER")

    replicate_api_token: str = Field(..., env="REPLICATE_API_TOKEN")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Instantiate for import elsewhere
settings = Settings()
