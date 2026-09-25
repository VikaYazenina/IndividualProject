"""
API управления источниками (этап 3 плана).

Главное исправление: раньше эндпоинты отдавали ВСЕ источники всем подряд.
Теперь require_user обязателен на каждом эндпоинте, и каждый запрос
дополнительно фильтруется по owner_id == текущий пользователь.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.deps import get_db, require_user
from app.parser import collect_new_items_for_source

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("/", response_model=List[schemas.SourceOut])
def list_sources(db: Session = Depends(get_db), user: models.User = Depends(require_user)):
    return (
        db.query(models.Source)
        .filter(models.Source.owner_id == user.id)
        .order_by(models.Source.created_at.desc())
        .all()
    )


@router.post("/", response_model=schemas.SourceOut, status_code=201)
def create_source(
    payload: schemas.SourceCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_user),
):
    existing = (
        db.query(models.Source)
        .filter(models.Source.owner_id == user.id, models.Source.url == payload.url)
        .first()
    )
    if existing:
        raise HTTPException(400, "У вас уже добавлен источник с таким URL")

    source = models.Source(**payload.model_dump(), owner_id=user.id)
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def _get_owned_source_or_404(db: Session, source_id: int, user: models.User) -> models.Source:
    source = db.get(models.Source, source_id)
    if not source or source.owner_id != user.id:
        raise HTTPException(404, "Источник не найден")
    return source


@router.get("/{source_id}", response_model=schemas.SourceOut)
def get_source(
    source_id: int, db: Session = Depends(get_db), user: models.User = Depends(require_user)
):
    return _get_owned_source_or_404(db, source_id, user)


@router.patch("/{source_id}", response_model=schemas.SourceOut)
def update_source(
    source_id: int,
    payload: schemas.SourceUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_user),
):
    source = _get_owned_source_or_404(db, source_id, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(source, field, value)
    db.commit()
    db.refresh(source)
    return source


@router.delete("/{source_id}", status_code=204)
def delete_source(
    source_id: int, db: Session = Depends(get_db), user: models.User = Depends(require_user)
):
    source = _get_owned_source_or_404(db, source_id, user)
    db.delete(source)
    db.commit()


@router.post("/{source_id}/fetch", response_model=List[schemas.ItemOut])
def fetch_source_now(
    source_id: int, db: Session = Depends(get_db), user: models.User = Depends(require_user)
):
    """Ручной запуск парсинга конкретного источника (не дожидаясь планировщика)."""
    source = _get_owned_source_or_404(db, source_id, user)
    return collect_new_items_for_source(db, source)
