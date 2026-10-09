"""
Подключение к базе данных.

SQLite подходит для MVP. При переходе на Postgres меняем DATABASE_URL —
остальной код не меняется, т.к. вся работа идёт через SQLAlchemy ORM.
"""

import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import Base

logger = logging.getLogger("contentharvest")

# check_same_thread нужен только для sqlite
connect_args = (
    {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Колонки, добавленные после первого релиза. create_all() не умеет менять уже
# существующие таблицы, поэтому добавляем недостающие вручную — без потери данных.
_SOURCE_NEW_COLUMNS = {
    "last_checked_at": "TIMESTAMP",
    "last_error": "VARCHAR(500)",
    "last_found_count": "INTEGER",
    "last_new_count": "INTEGER",
}


def _add_missing_columns():
    inspector = inspect(engine)
    if "sources" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("sources")}
    with engine.begin() as conn:
        for name, ddl in _SOURCE_NEW_COLUMNS.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE sources ADD COLUMN {name} {ddl}"))
                logger.info("Миграция БД: добавлена колонка sources.%s", name)


def init_db():
    """Создаёт таблицы, если их нет, и дополняет старые недостающими колонками."""
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


def get_session():
    """Возвращает новую сессию для работы с БД."""
    return SessionLocal()
