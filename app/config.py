"""Application configuration loaded from environment variables.

Every value can be overridden via an environment variable so the same image
runs unchanged locally, in kind, and in EKS. This is what lets us inject a
bad config later to deliberately trigger failures for the incident-analysis
agent to investigate.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


# Each field auto-loads from an env var of the same name (REDIS_HOST -> redis_host).
# In K8s these come from the ConfigMap; the defaults below are for local runs.
class Settings(BaseSettings):
    # Also read a local .env file if present; ignore unknown keys.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "url-shortener"          # name shown in logs and the / endpoint

    # --- Redis connection (overridden by the ConfigMap in the cluster) ---
    redis_host: str = "localhost"            # in K8s this becomes the Service name "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None
    redis_connect_timeout: float = 2.0       # fail fast if Redis is unreachable

    # --- App behaviour ---
    base_url: str = "http://localhost:8000"  # prefix used to build the returned short URL
    short_code_length: int = 7               # 62^7 combos -> collisions ~impossible
    max_code_generation_attempts: int = 5    # retry budget when a code already exists

    log_level: str = "INFO"


# One shared settings object imported across the app.
settings = Settings()
