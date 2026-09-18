"""FastAPI-зависимость: одна сессия БД на один запрос."""

from app.database import get_session


def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()
