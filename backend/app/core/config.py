from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server-side settings. Values come from environment variables prefixed PDM_ or a .env file."""

    model_config = SettingsConfigDict(env_prefix="PDM_", env_file=".env", extra="ignore")

    app_name: str = "Industrial Predictive Maintenance Platform"
    database_url: str = "postgresql+psycopg://pdm:pdm@localhost:5432/pdm"
    # The platform must run without Ollama (GEN-04); LLM features are opt-in.
    llm_enabled: bool = False
    # 'dev' trusts X-PDM-User/X-PDM-Role headers; replaced by real authentication in T028 (D-010).
    auth_mode: str = "dev"
    # Server-side JSON file describing data sources (configs, layouts, credential references).
    datasources_file: str | None = None
    models_dir: str = "var/models"  # trained-model registry (T022); relative to the backend folder


@lru_cache
def get_settings() -> Settings:
    return Settings()
