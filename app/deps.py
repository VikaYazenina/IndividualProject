"""
FastAPI-зависимости: сессия БД на запрос + текущий пользователь по сессии.

Раньше источники и материалы были общими на всех посетителей сайта —
любой видел чужие источники. Теперь каждый Source привязан к owner_id,
и все запросы к БД в роутерах фильтруются по текущему пользователю.
"""

from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import User


def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


def get_current_user_optional(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """Возвращает текущего пользователя по сессии, либо None, если гость."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, user_id)


def require_user(
    request: Request, db: Session = Depends(get_db)
) -> User:
    """
    Для REST API: требует авторизации, иначе 401.
    Веб-страницы используют get_current_user_optional и сами делают redirect на /login,
    т.к. HTML-страницам нужнее человеко-читаемый редирект, а не JSON-ошибка.
    """
    user = get_current_user_optional(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    return user
