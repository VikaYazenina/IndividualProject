from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.deps import get_db
from app.parser import collect_new_items_for_source

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("/", response_model=List[schemas.SourceOut])
def list_sources(db: Session = Depends(get_db)):
    return db.query(models.Source).order_by(models.Source.created_at.desc()).all()


@router.post("/", response_model=schemas.SourceOut, status_code=201)
def create_source(payload: schemas.SourceCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Source).filter(models.Source.url == payload.url).first()
    if existing:
        raise HTTPException(400, "Источник с таким URL уже добавлен")

    source = models.Source(**payload.model_dump())
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.get("/{source_id}", response_model=schemas.SourceOut)
def get_source(source_id: int, db: Session = Depends(get_db)):
    source = db.get(models.Source, source_id)
    if not source:
        raise HTTPException(404, "Источник не найден")
    return source


@router.patch("/{source_id}", response_model=schemas.SourceOut)
def update_source(source_id: int, payload: schemas.SourceUpdate, db: Session = Depends(get_db)):
    source = db.get(models.Source, source_id)
    if not source:
        raise HTTPException(404, "Источник не найден")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(source, field, value)

    db.commit()
    db.refresh(source)
    return source


@router.delete("/{source_id}", status_code=204)
def delete_source(source_id: int, db: Session = Depends(get_db)):
    source = db.get(models.Source, source_id)
    if not source:
        raise HTTPException(404, "Источник не найден")
    db.delete(source)
    db.commit()


@router.post("/{source_id}/fetch", response_model=List[schemas.ItemOut])
def fetch_source_now(source_id: int, db: Session = Depends(get_db)):
    
    source = db.get(models.Source, source_id)
    if not source:
        raise HTTPException(404, "Источник не найден")
    return collect_new_items_for_source(db, source)
