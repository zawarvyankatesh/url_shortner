"""Application configuration loaded from environment variables.

Every value can be overridden via an environment variable so the same image
runs unchanged locally, in kind, and in EKS. This is what lets us inject a
bad config later to deliberately trigger failures for the incident-analysis
agent to investigate.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "url-shortener"

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None
    redis_connect_timeout: float = 2.0

    base_url: str = "http://localhost:8000"
    short_code_length: int = 7
    max_code_generation_attempts: int = 5

    log_level: str = "INFO"


settings = Settings()
