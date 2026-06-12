from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Redis — set REDIS_URL for Railway/remote, or use individual fields for local
    redis_url: str = ""
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    # SMTP
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_name: str = "MyApp"
    smtp_from_email: str = ""

    # SendGrid
    use_sendgrid: bool = False
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = ""
    sendgrid_from_name: str = "MyApp"

    # Resend
    use_resend: bool = False
    resend_api_key: str = ""
    resend_from_email: str = ""
    resend_from_name: str = "MyApp"

    # OTP behaviour
    otp_length: int = 6
    otp_expire_seconds: int = 300       # 5 min TTL in Redis
    otp_max_attempts: int = 5           # brute-force lock
    otp_cooldown_seconds: int = 60      # resend rate-limit

    # App
    app_env: str = "development"
    secret_key: str = "change-me"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()