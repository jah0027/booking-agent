"""Application configuration"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )
    
    # Database (Supabase)
    supabase_url: str
    supabase_service_key: str
    
    # AI/LLM
    openai_api_key: str = ""
    gemini_api_key: str = ""
    llm_model: str = "gpt-4-turbo"
    
    # Email Service
    resend_api_key: str = ""
    email_from_address: str = "bookings@example.com"
    email_from_name: str = "SickDay Agent"
    agent_name: str = "SickDay Agent"
    email_webhook_secret: str = ""
    
    # Background Jobs (Redis)
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"
    
    # Application Settings
    environment: str = "development"
    api_base_url: str = "http://localhost:8000"
    nextjs_site_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000,http://localhost:3001"
    
    # Security
    api_secret_key: str = "change-me-in-production"
    webhook_signing_secret: str = "change-me-in-production"
    
    # Monitoring
    sentry_dsn: str = ""
    log_level: str = "INFO"
    
    # Rate Limiting
    rate_limit_per_minute: int = 60
    rate_limit_per_hour: int = 1000
    
    # Follow-up Settings
    follow_up_days_band_member: int = 3
    follow_up_days_venue: int = 5
    max_follow_ups: int = 2
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins into a list"""
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.environment.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development"""
        return self.environment.lower() == "development"


# Global settings instance
settings = Settings()
