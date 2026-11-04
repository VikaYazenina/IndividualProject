import os
from dotenv import load_dotenv

load_dotenv()


def _default_database_url() -> str:
    if os.path.isdir("/data") and os.access("/data", os.W_OK):
        return "sqlite:////data/aggregator.db"
    return "sqlite:///aggregator.db"


class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL") or _default_database_url()

    SECRET_KEY: str = os.getenv("SECRET_KEY", "insecure-dev-key-change-me")

    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    MAIL_FROM: str = os.getenv("MAIL_FROM", "")

    
    PARSE_INTERVAL_HOURS: float = float(os.getenv("PARSE_INTERVAL_HOURS", "3"))
    DIGEST_HOUR: int = int(os.getenv("DIGEST_HOUR", "9"))  # во сколько слать дайджест
    TIMEZONE: str = os.getenv("TIMEZONE", "Europe/Moscow")


settings = Settings()
