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
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.get(User, user_id)
    if user is None:
        request.session.clear()
    return user


def require_user(
    request: Request, db: Session = Depends(get_db)
) -> User:
    
    user = get_current_user_optional(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    return user
