import csv
import io
from collections import Counter
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app import models, schemas
from app.deps import get_db

router = APIRouter(prefix="/api/items", tags=["items"])


@router.get("/", response_model=List[schemas.ItemOut])
def list_items(
    db: Session = Depends(get_db),
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
    """Расширенный поиск и фильтрация по архиву материалов."""
    query = db.query(models.Item).join(models.Source)

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

    return (
        query.order_by(models.Item.fetched_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.patch("/{item_id}/read", response_model=schemas.ItemOut)
def mark_read(item_id: int, read: bool = True, db: Session = Depends(get_db)):
    item = db.get(models.Item, item_id)
    if not item:
        raise HTTPException(404, "Материал не найден")
    item.is_read = read
    db.commit()
    db.refresh(item)
    return item


@router.patch("/{item_id}/defer", response_model=schemas.ItemOut)
def mark_deferred(item_id: int, deferred: bool = True, db: Session = Depends(get_db)):
    """Отложенное прочтение — материал повторно попадёт в следующее письмо."""
    item = db.get(models.Item, item_id)
    if not item:
        raise HTTPException(404, "Материал не найден")
    item.is_deferred = deferred
    db.commit()
    db.refresh(item)
    return item


@router.get("/export")
def export_items(db: Session = Depends(get_db), format: str = "csv"):
    """Экспорт всего архива в CSV."""
    if format != "csv":
        raise HTTPException(400, "Поддерживается только format=csv")

    items = db.query(models.Item).order_by(models.Item.fetched_at.desc()).all()

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
def get_stats(db: Session = Depends(get_db), days: int = 30):
    """Аналитика потребления: сколько материалов собрано/прочитано за период."""
    since = datetime.utcnow() - timedelta(days=days)

    total = db.query(models.Item).filter(models.Item.fetched_at >= since).count()
    read = (
        db.query(models.Item)
        .filter(models.Item.fetched_at >= since, models.Item.is_read == True)  # noqa: E712
        .count()
    )

    by_source_rows = (
        db.query(models.Source.name, func.count(models.Item.id))
        .join(models.Item)
        .filter(models.Item.fetched_at >= since)
        .group_by(models.Source.name)
        .all()
    )

    return {
        "period_days": days,
        "collected": total,
        "read": read,
        "by_source": dict(by_source_rows),
    }
