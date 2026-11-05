from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    mongodb_uri: str
    mongodb_database: str = "dependency_aware_mcp"

    ollama_model: str
    ollama_auditor_model: str | None = None

    ollama_base_url: str = "http://localhost:11434"

    mcp_url: str = "http://127.0.0.1:8001/mcp"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()