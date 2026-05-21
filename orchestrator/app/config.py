from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    nats_url: str = "nats://localhost:4222"
    redis_url: str = "redis://localhost:6379"
    secret_key: str
    
    class Config:
        env_file = ".env"

settings = Settings()
