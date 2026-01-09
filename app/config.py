"""Application configuration"""


import os
from typing import List
from dotenv import load_dotenv

load_dotenv()



# Application settings loaded from environment variables
class Settings:
    def __init__(self):
        # Database (Supabase)
        self.supabase_url = os.getenv("SUPABASE_URL", "")
        self.supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY", "")

        # AI/LLM
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.llm_model = os.getenv("LLM_MODEL", "gpt-4-turbo")

        # Email Service
        self.resend_api_key = os.getenv("RESEND_API_KEY", "")
        self.email_from_address = os.getenv("EMAIL_FROM_ADDRESS", "bookings@example.com")
        self.email_from_name = os.getenv("EMAIL_FROM_NAME", "SickDay Agent")
        self.agent_name = os.getenv("AGENT_NAME", "SickDay Agent")
        self.email_webhook_secret = os.getenv("EMAIL_WEBHOOK_SECRET", "")

        # Background Jobs (Redis)
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.celery_broker_url = os.getenv("CELERY_BROKER_URL", self.redis_url)
        self.celery_result_backend = os.getenv("CELERY_RESULT_BACKEND", self.redis_url)

        # Application Settings
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.api_base_url = os.getenv("API_BASE_URL", "http://localhost:8000")
        self.nextjs_site_url = os.getenv("NEXTJS_SITE_URL", "http://localhost:3000")
        self.cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001")

        # Security
        self.api_secret_key = os.getenv("API_SECRET_KEY", "change-me-in-production")
        self.webhook_signing_secret = os.getenv("WEBHOOK_SIGNING_SECRET", "")

        # Monitoring
        self.sentry_dsn = os.getenv("SENTRY_DSN", "")
        self.log_level = os.getenv("LOG_LEVEL", "INFO")

        # Rate Limiting
        self.rate_limit_per_minute = int(os.getenv("RATE_LIMIT_PER_MINUTE", 60))
        self.rate_limit_per_hour = int(os.getenv("RATE_LIMIT_PER_HOUR", 1000))

        # Follow-up Settings
        self.follow_up_days_band_member = int(os.getenv("FOLLOW_UP_DAYS_BAND_MEMBER", 3))
        self.follow_up_days_venue = int(os.getenv("FOLLOW_UP_DAYS_VENUE", 5))
        self.max_follow_ups = int(os.getenv("MAX_FOLLOW_UPS", 2))

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
