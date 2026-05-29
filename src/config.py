from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os

load_dotenv()

class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Therapy Backend"
    VERSION: str = "1.0.0"
    API_STR: str = os.getenv("API_STR", "/api/v1")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))
    DATABASE_URL: str = os.getenv("DATABASE_URL", "mongodb://localhost:27017")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "https://aitherapy-frontend-production.up.railway.app")
    
    # OPEN AI Configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # timezone config
    TIMEZONE: str = os.getenv("TIMEZONE", "UTC")

    # Stripe Configuration
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_PUBLISHABLE_KEY: str = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    # Email / SMTP configuration (sample placeholders)
    # To use Gmail:
    # 1. Enable 2-Step Verification on the Gmail account (Account -> Security).
    # 2. Create an "App Password" (Google Account -> Security -> App passwords) and copy the 16‑character value (no spaces) as SMTP_PASSWORD.
    # 3. SMTP_USER should be the full email address (e.g. jdd8255@gmail.com).
    # 4. Leave SMTP_TLS_ENABLED = true (Gmail uses STARTTLS on port 587) OR use SSL port 465 with SMTP_SSL_ENABLED.
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", 587))
    SMTP_USER: str = os.getenv("SMTP_USER", "jdd8255@gmail.com")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "egpc wgdz mrxg gtkd")  # <-- replace with Gmail App Password
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "jdd8255@gmail.com")
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "AI Therapy Skills")
    SMTP_TLS_ENABLED: bool = os.getenv("SMTP_TLS_ENABLED", "true").lower() == "true"
    SMTP_SSL_ENABLED: bool = os.getenv("SMTP_SSL_ENABLED", "false").lower() == "true"

    # Password reset configuration
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("PASSWORD_RESET_TOKEN_EXPIRE_MINUTES", 60))
    FRONTEND_RESET_PASSWORD_PATH: str = os.getenv("FRONTEND_RESET_PASSWORD_PATH", "/reset-password")

settings = Settings()
