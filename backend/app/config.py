import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./pcdealtracker.db"
    
    # Redis
    redis_url: str = "redis://localhost:6379"
    
    # Scraping settings
    scrape_interval_hours: int = 6
    max_concurrent_scrapers: int = 10
    request_delay_seconds: int = 2
    
    # API settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = True
    
    # Logging
    log_level: str = "INFO"
    log_file: str = "logs/pcdealtracker.log"
    
    # Security
    secret_key: str = "your-secret-key-here"
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()