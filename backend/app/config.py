from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    # Database
    database_url: str = "sqlite:///./pcdealtracker.db"

    # Cache / Redis
    redis_url: str = "redis://localhost:6379"
    cache_enabled: bool = False

    # Scraping settings
    scrape_interval_hours: int = 6
    scrape_scheduler_enabled: bool = False
    max_concurrent_scrapers: int = 10
    request_delay_seconds: int = 2
    scraper_headless: bool = False
    scraper_user_data_dir: str | None = None
    scraper_browser_executable: str | None = None
    scraper_browser_major_version: int | None = None
    scraper_page_timeout_seconds: int = 15
    scraper_challenge_timeout_seconds: int = 45

    # API settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = True
    api_cors_origins: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
            "http://localhost:8080",
            "http://127.0.0.1:8080",
        ]
    )

    # Logging
    log_level: str = "INFO"
    log_file: str = "logs/pcdealtracker.log"

    # Security
    secret_key: str = "your-secret-key-here"
    review_api_key: str = "change-me"

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug_value(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return True

        normalized = str(value).strip().lower()
        truthy = {"1", "true", "yes", "on", "debug", "development", "dev"}
        falsy = {"0", "false", "no", "off", "release", "production", "prod"}

        if normalized in truthy:
            return True
        if normalized in falsy:
            return False

        raise ValueError(f"Unsupported debug value: {value!r}")

    @field_validator("api_cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return []
            if normalized.startswith("[") and normalized.endswith("]"):
                normalized = normalized[1:-1]
            return [origin.strip().strip("'\"") for origin in normalized.split(",") if origin.strip()]
        raise ValueError("api_cors_origins must be a list or comma-separated string")


settings = Settings()
