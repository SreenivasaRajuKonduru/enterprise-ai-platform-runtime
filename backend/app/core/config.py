from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    redis_url: str

    ollama_url: str = (
        "http://host.docker.internal:11434/api/generate"
    )
    ollama_model: str = "llama3.2"
    ollama_timeout_seconds: float = 90.0

    circuit_breaker_enabled: bool = True
    circuit_breaker_failure_threshold: int = Field(
        default=5,
        ge=1,
    )
    circuit_breaker_recovery_timeout_seconds: int = Field(
        default=30,
        ge=1,
    )
    circuit_breaker_half_open_max_calls: int = Field(
        default=1,
        ge=1,
    )
    circuit_breaker_success_threshold: int = Field(
        default=2,
        ge=1,
    )
    circuit_breaker_state_ttl_seconds: int = Field(
        default=86400,
        ge=60,
    )
    circuit_breaker_lock_timeout_seconds: int = Field(
        default=5,
        ge=1,
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()