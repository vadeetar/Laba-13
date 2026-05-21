from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    nats_url: str = "nats://nats:4222"
    redis_url: str = "redis://redis:6379"
    secret_key: str = "dev-secret-change-me"
    otel_exporter_otlp_endpoint: str = "http://jaeger:4318"
    request_timeout: float = 5.0
    max_retries: int = 3
    queue_scale_threshold: int = 10
    log_file: str = "/app/logs/orchestrator.log"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
