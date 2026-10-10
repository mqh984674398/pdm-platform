from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server-side settings. Values come from environment variables prefixed PDM_ or a .env file."""

    model_config = SettingsConfigDict(env_prefix="PDM_", env_file=".env", extra="ignore")

    app_name: str = "Industrial Predictive Maintenance Platform"
    database_url: str = "postgresql+psycopg://pdm:pdm@localhost:5432/pdm"
    # The platform must run without Ollama (GEN-04); LLM features are opt-in.
    llm_enabled: bool = False
    # 'local' = accounts and signed session cookies (deployment); 'dev' trusts X-PDM-User/X-PDM-Role
    # headers and is for development and tests only (D-010).
    auth_mode: str = "dev"
    # HMAC key for session cookies in 'local' mode; at least 32 characters, kept server-side.
    secret_key: str = ""
    # Mark session cookies Secure (set when the LAN server is behind HTTPS).
    cookie_secure: bool = False
    # Built frontend served by the API server on one port (deployment); unset in development.
    static_dir: str | None = None
    # SEC-06: non-simulated data sources stay disabled until the user's explicit approval (G4).
    production_data_approved: bool = False
    # Server-side JSON file describing data sources (configs, layouts, credential references).
    datasources_file: str | None = None
    models_dir: str = "var/models"  # trained-model registry (T022); relative to the backend folder


@lru_cache
def get_settings() -> Settings:
    return Settings()
