from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server-side settings. Values come from environment variables prefixed PDM_ or a .env file."""

    model_config = SettingsConfigDict(env_prefix="PDM_", env_file=".env", extra="ignore")

    app_name: str = "Industrial Predictive Maintenance Platform"
    database_url: str = "postgresql+psycopg://pdm:pdm@localhost:5432/pdm"
    # The platform must run without Ollama (GEN-04); LLM features are opt-in.
    llm_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
