from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration. All environment handling goes through here —
    no module should read os.environ directly."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="COZYPDFS_", extra="ignore")

    database_url: str = "sqlite:///./data/cozypdfs.db"

    storage_backend: str = "local"
    storage_local_root: str = "./data/storage"
    storage_local_base_url: str = "/storage"

    cookie_secret: str = "dev-secret-change-me"

    max_upload_size_mb: int = 100
    max_page_count: int = 2000
    retain_original_pdfs: bool = True

    job_poll_interval: float = 1.0
    job_concurrency: int = 1
    job_timeout_seconds: float = 300.0

    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
