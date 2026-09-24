from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import models
from app.database import init_db
from app.deps import get_db
from app.parser import collect_new_items_for_source
from app.routers import items, sources
from app.scheduler import start_scheduler, stop_scheduler

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Content Aggregator", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


app.include_router(sources.router)
app.include_router(items.router)


@app.get("/", response_class=HTMLResponse)
def home():
    return RedirectResponse("/archive")


@app.get("/sources", response_class=HTMLResponse)
def sources_page(request: Request, db: Session = Depends(get_db)):
    all_sources = db.query(models.Source).order_by(models.Source.created_at.desc()).all()
    return templates.TemplateResponse(
        "sources.html", {"request": request, "sources": all_sources}
    )


@app.post("/sources/add")
def add_source_form(
    name: str = Form(...),
    url: str = Form(...),
    type: str = Form("rss"),
    category: str = Form(""),
    html_item_selector: str = Form(""),
    html_title_selector: str = Form(""),
    html_link_selector: str = Form(""),
    db: Session = Depends(get_db),
):
    source = models.Source(
        name=name,
        url=url,
        type=models.SourceType(type),
        category=category or None,
        html_item_selector=html_item_selector or None,
        html_title_selector=html_title_selector or None,
        html_link_selector=html_link_selector or None,
    )
    db.add(source)
    db.commit()
    return RedirectResponse("/sources", status_code=303)


@app.post("/sources/{source_id}/delete")
def delete_source_form(source_id: int, db: Session = Depends(get_db)):
    source = db.get(models.Source, source_id)
    if source:
        db.delete(source)
        db.commit()
    return RedirectResponse("/sources", status_code=303)


@app.post("/sources/{source_id}/toggle")
def toggle_source_form(source_id: int, db: Session = Depends(get_db)):
    source = db.get(models.Source, source_id)
    if source:
        source.is_active = not source.is_active
        db.commit()
    return RedirectResponse("/sources", status_code=303)


@app.post("/sources/{source_id}/fetch-now")
def fetch_source_now_form(source_id: int, db: Session = Depends(get_db)):
    source = db.get(models.Source, source_id)
    if source:
        collect_new_items_for_source(db, source)
    return RedirectResponse("/sources", status_code=303)


@app.get("/archive", response_class=HTMLResponse)
def archive_page(
    request: Request,
    db: Session = Depends(get_db),
    search: str = "",
    category: str = "",
    only_unread: bool = False,
    only_deferred: bool = False,
):
    query = db.query(models.Item).join(models.Source)

    if search:
        like = f"%{search}%"
        query = query.filter(models.Item.title.ilike(like))
    if category:
        query = query.filter(models.Source.category == category)
    if only_unread:
        query = query.filter(models.Item.is_read == False)  # noqa: E712
    if only_deferred:
        query = query.filter(models.Item.is_deferred == True)  # noqa: E712

    items_list = query.order_by(models.Item.fetched_at.desc()).limit(100).all()
    categories = sorted({c[0] for c in db.query(models.Source.category).distinct() if c[0]})

    return templates.TemplateResponse(
        "archive.html",
        {
            "request": request,
            "items": items_list,
            "categories": categories,
            "search": search,
            "category": category,
            "only_unread": only_unread,
            "only_deferred": only_deferred,
        },
    )


@app.post("/items/{item_id}/read")
def toggle_read_form(item_id: int, db: Session = Depends(get_db)):
    item = db.get(models.Item, item_id)
    if item:
        item.is_read = not item.is_read
        db.commit()
    return RedirectResponse("/archive", status_code=303)


@app.post("/items/{item_id}/defer")
def toggle_defer_form(item_id: int, db: Session = Depends(get_db)):
    item = db.get(models.Item, item_id)
    if item:
        item.is_deferred = not item.is_deferred
        db.commit()
    return RedirectResponse("/archive", status_code=303)


@app.get("/stats", response_class=HTMLResponse)
def stats_page(request: Request, db: Session = Depends(get_db), days: int = 30):
    from collections import Counter
    from datetime import datetime, timedelta
    from sqlalchemy import func

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

    return templates.TemplateResponse(
        "stats.html",
        {
            "request": request,
            "days": days,
            "total": total,
            "read": read,
            "by_source": dict(by_source_rows),
        },
    )
