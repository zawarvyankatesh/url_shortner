"""Agent configuration from environment variables.

Non-secret values come from a ConfigMap; secrets (LLM_API_KEY, SMTP_PASSWORD)
come from a Kubernetes Secret. Nothing sensitive is hard-coded here.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Prometheus (read-only queries) ---
    prometheus_url: str = "http://prometheus.monitoring.svc:9090"

    # --- LLM (Azure OpenAI-compatible proxy) ---
    llm_endpoint: str = "https://ai-framework1:8085"
    llm_api_version: str = "2024-02-15-preview"
    llm_model: str = "gpt-4.1"
    llm_api_key: str = ""
    llm_ntnet_user: str = "vyankatz@amdocs.com"
    # Internal proxies often use self-signed certs; set true if it has a valid CA.
    llm_verify_ssl: bool = False
    llm_timeout: float = 90.0
    llm_temperature: float = 0.2

    # --- Email (SMTP) ---
    mail_to: str = "vyankatz@amdocs.com"
    mail_from: str = "incident-agent@amdocs.com"
    smtp_host: str = ""
    smtp_port: int = 25
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = False

    # --- Context collection limits ---
    log_tail_lines: int = 100

    log_level: str = "INFO"


settings = Settings()
