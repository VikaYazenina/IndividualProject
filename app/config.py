"""
Центральная точка конфигурации. Значения берутся из переменных окружения
(в т.ч. из файла .env — см. .env.example) и один раз собираются в объект Settings.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _default_database_url() -> str:
    # На Amvera постоянное хранилище смонтировано в /data. Всё, что лежит вне
    # него (в т.ч. файл рядом с кодом), стирается при каждом пересборе/перезапуске
    # контейнера — вместе с пользователями, источниками и архивом.
    if os.path.isdir("/data") and os.access("/data", os.W_OK):
        return "sqlite:////data/aggregator.db"
    return "sqlite:///aggregator.db"


class Settings:
    # База данных
    DATABASE_URL: str = os.getenv("DATABASE_URL") or _default_database_url()

    # Подпись сессионных cookie (авторизация). На проде ОБЯЗАТЕЛЬНО задать свой
    # длинный случайный SECRET_KEY — иначе сессии легко подделать.
    SECRET_KEY: str = os.getenv("SECRET_KEY", "insecure-dev-key-change-me")

    # SMTP: учётка, от имени которой сервис шлёт письма. Получатель каждого
    # дайджеста — email пользователя из регистрации.
    # Порт 465 -> SSL с самого начала, любой другой (587, 25) -> STARTTLS.
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    MAIL_FROM: str = os.getenv("MAIL_FROM", "")

    # Планировщик: парсинг источников и отправка дайджеста — две отдельные задачи.
    PARSE_INTERVAL_HOURS: float = float(os.getenv("PARSE_INTERVAL_HOURS", "3"))
    DIGEST_HOUR: int = int(os.getenv("DIGEST_HOUR", "9"))  # во сколько слать дайджест
    TIMEZONE: str = os.getenv("TIMEZONE", "Europe/Moscow")


settings = Settings()
