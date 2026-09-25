"""
API работы с материалами (этапы 3, 6, 9 плана).

Как и в sources.py — раньше данные были общими на всех. Теперь каждый
запрос джойнит Source и фильтрует по Source.owner_id == текущий пользователь.
"""

import csv
import io
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app import models, schemas
from app.deps import get_db, require_user

router = APIRouter(prefix="/api/items", tags=["items"])


def _owned_items_query(db: Session, user: models.User):
    return db.query(models.Item).join(models.Source).filter(models.Source.owner_id == user.id)


@router.get("/", response_model=List[schemas.ItemOut])
def list_items(
    db: Session = Depends(get_db),
    user: models.User = Depends(require_user),
    source_id: Optional[int] = None,
    category: Optional[str] = None,
    is_read: Optional[bool] = None,
    is_deferred: Optional[bool] = None,
    search: Optional[str] = Query(None, description="Поиск по заголовку и описанию"),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    """Расширенный поиск и фильтрация по архиву материалов текущего пользователя."""
    query = _owned_items_query(db, user)

    if source_id is not None:
        query = query.filter(models.Item.source_id == source_id)
    if category:
        query = query.filter(models.Source.category == category)
    if is_read is not None:
        query = query.filter(models.Item.is_read == is_read)
    if is_deferred is not None:
        query = query.filter(models.Item.is_deferred == is_deferred)
    if search:
        like = f"%{search}%"
        query = query.filter(or_(models.Item.title.ilike(like), models.Item.summary.ilike(like)))
    if date_from:
        query = query.filter(models.Item.published_at >= date_from)
    if date_to:
        query = query.filter(models.Item.published_at <= date_to)

    return query.order_by(models.Item.fetched_at.desc()).offset(offset).limit(limit).all()


def _get_owned_item_or_404(db: Session, item_id: int, user: models.User) -> models.Item:
    item = _owned_items_query(db, user).filter(models.Item.id == item_id).first()
    if not item:
        raise HTTPException(404, "Материал не найден")
    return item


@router.patch("/{item_id}/read", response_model=schemas.ItemOut)
def mark_read(
    item_id: int,
    read: bool = True,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_user),
):
    item = _get_owned_item_or_404(db, item_id, user)
    item.is_read = read
    db.commit()
    db.refresh(item)
    return item


@router.patch("/{item_id}/defer", response_model=schemas.ItemOut)
def mark_deferred(
    item_id: int,
    deferred: bool = True,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_user),
):
    item = _get_owned_item_or_404(db, item_id, user)
    item.is_deferred = deferred
    db.commit()
    db.refresh(item)
    return item


@router.get("/export")
def export_items(
    db: Session = Depends(get_db),
    user: models.User = Depends(require_user),
    format: str = "csv",
):
    """Экспорт архива текущего пользователя в CSV."""
    if format != "csv":
        raise HTTPException(400, "Поддерживается только format=csv")

    items = _owned_items_query(db, user).order_by(models.Item.fetched_at.desc()).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "источник", "заголовок", "ссылка", "дата публикации", "прочитано"])
    for item in items:
        writer.writerow(
            [item.id, item.source.name, item.title, item.link, item.published_at, item.is_read]
        )
    buf.seek(0)

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=items.csv"},
    )


@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    user: models.User = Depends(require_user),
    days: int = 30,
):
    """Аналитика потребления текущего пользователя за период."""
    since = datetime.utcnow() - timedelta(days=days)

    base = _owned_items_query(db, user).filter(models.Item.fetched_at >= since)
    total = base.count()
    read = base.filter(models.Item.is_read == True).count()  # noqa: E712

    by_source_rows = (
        db.query(models.Source.name, func.count(models.Item.id))
        .join(models.Item)
        .filter(models.Source.owner_id == user.id, models.Item.fetched_at >= since)
        .group_by(models.Source.name)
        .all()
    )

    return {
        "period_days": days,
        "collected": total,
        "read": read,
        "by_source": dict(by_source_rows),
    }
