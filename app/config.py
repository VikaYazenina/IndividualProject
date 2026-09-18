"""
Центральная точка конфигурации. Значения берутся из переменных окружения
(в т.ч. из файла .env — см. .env.example) и один раз собираются в объект Settings.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # База данных
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///aggregator.db")

    # SMTP для email-рассылки (этап 4)
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    MAIL_FROM: str = os.getenv("MAIL_FROM", "")
    MAIL_TO: str = os.getenv("MAIL_TO", "")

    # Планировщик (этап 4)
    PARSE_INTERVAL_HOURS: int = int(os.getenv("PARSE_INTERVAL_HOURS", "24"))


settings = Settings()
