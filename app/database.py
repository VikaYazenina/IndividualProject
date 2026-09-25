"""
Подключение к базе данных.

На этапе MVP используем SQLite — этого достаточно для разработки и
тестирования. При переходе на хостинг меняем DATABASE_URL в .env на
postgres://... без изменения остального кода, т.к. вся работа идёт
через SQLAlchemy ORM.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import Base

# check_same_thread нужен только для sqlite
connect_args = (
    {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db():
    """Создаёт все таблицы, если их ещё нет."""
    Base.metadata.create_all(bind=engine)


def get_session():
    """Возвращает новую сессию для работы с БД."""
    return SessionLocal()
