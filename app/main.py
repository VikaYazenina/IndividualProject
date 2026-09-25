"""
Точка входа приложения.

Запуск для разработки:
    uvicorn app.main:app --reload

Собирает вместе:
- REST API (app/routers) — для программного доступа;
- server-rendered веб-интерфейс — страницы регистрации/входа, "Источники", "Архив", "Статистика";
- планировщик (app/scheduler) — регулярный парсинг + email-рассылка (этап 4).

ВАЖНО (исправление): раньше страницы были общими на всех посетителей —
любой видел все источники и материалы. Теперь без входа доступны только
/login и /register, а все остальные страницы требуют сессию и показывают
только данные текущего пользователя.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app import models
from app.config import settings
from app.database import init_db
from app.deps import get_current_user_optional, get_db
from app.parser import collect_new_items_for_source
from app.routers import items, sources
from app.scheduler import start_scheduler, stop_scheduler
from app.security import hash_password, verify_password

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="ContentHarvest", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# REST API (сам требует авторизации на уровне роутеров, см. app/deps.py::require_user)
app.include_router(sources.router)
app.include_router(items.router)


# ---------------------------------------------------------------------------
# Регистрация / вход / выход
# ---------------------------------------------------------------------------


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/archive")
    return templates.TemplateResponse("register.html", {"request": request, "error": None})


@app.post("/register")
def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()

    def render_error(message: str):
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": message}, status_code=400
        )

    if password != password_confirm:
        return render_error("Пароли не совпадают")
    if len(password) < 6:
        return render_error("Пароль должен быть не короче 6 символов")
    if db.query(models.User).filter(models.User.email == email).first():
        return render_error("Пользователь с таким email уже зарегистрирован")

    user = models.User(email=email, hashed_password=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)

    request.session["user_id"] = user.id
    return RedirectResponse("/sources", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    user = db.query(models.User).filter(models.User.email == email).first()

    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неверный email или пароль"},
            status_code=400,
        )

    request.session["user_id"] = user.id
    return RedirectResponse("/archive", status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ---------------------------------------------------------------------------
# Веб-интерфейс (доступен только авторизованным пользователям)
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def home():
    return RedirectResponse("/archive")


@app.get("/sources", response_class=HTMLResponse)
def sources_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse("/login")

    my_sources = (
        db.query(models.Source)
        .filter(models.Source.owner_id == user.id)
        .order_by(models.Source.created_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        "sources.html", {"request": request, "sources": my_sources, "user": user}
    )


@app.post("/sources/add")
def add_source_form(
    request: Request,
    name: str = Form(...),
    url: str = Form(...),
    type: str = Form("rss"),
    category: str = Form(""),
    html_item_selector: str = Form(""),
    html_title_selector: str = Form(""),
    html_link_selector: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse("/login")

    source = models.Source(
        owner_id=user.id,
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


def _get_owned_source_or_none(db: Session, source_id: int, user: models.User):
    source = db.get(models.Source, source_id)
    if source and source.owner_id == user.id:
        return source
    return None


@app.post("/sources/{source_id}/delete")
def delete_source_form(source_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse("/login")
    source = _get_owned_source_or_none(db, source_id, user)
    if source:
        db.delete(source)
        db.commit()
    return RedirectResponse("/sources", status_code=303)


@app.post("/sources/{source_id}/toggle")
def toggle_source_form(source_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse("/login")
    source = _get_owned_source_or_none(db, source_id, user)
    if source:
        source.is_active = not source.is_active
        db.commit()
    return RedirectResponse("/sources", status_code=303)


@app.post("/sources/{source_id}/fetch-now")
def fetch_source_now_form(source_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse("/login")
    source = _get_owned_source_or_none(db, source_id, user)
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
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse("/login")

    query = (
        db.query(models.Item)
        .join(models.Source)
        .filter(models.Source.owner_id == user.id)
    )

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
    categories = sorted(
        {
            c[0]
            for c in db.query(models.Source.category)
            .filter(models.Source.owner_id == user.id)
            .distinct()
            if c[0]
        }
    )

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
            "user": user,
        },
    )


@app.post("/items/{item_id}/read")
def toggle_read_form(item_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse("/login")
    item = (
        db.query(models.Item)
        .join(models.Source)
        .filter(models.Item.id == item_id, models.Source.owner_id == user.id)
        .first()
    )
    if item:
        item.is_read = not item.is_read
        db.commit()
    return RedirectResponse("/archive", status_code=303)


@app.post("/items/{item_id}/defer")
def toggle_defer_form(item_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse("/login")
    item = (
        db.query(models.Item)
        .join(models.Source)
        .filter(models.Item.id == item_id, models.Source.owner_id == user.id)
        .first()
    )
    if item:
        item.is_deferred = not item.is_deferred
        db.commit()
    return RedirectResponse("/archive", status_code=303)


@app.get("/stats", response_class=HTMLResponse)
def stats_page(request: Request, db: Session = Depends(get_db), days: int = 30):
    from datetime import datetime, timedelta

    from sqlalchemy import func

    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse("/login")

    since = datetime.utcnow() - timedelta(days=days)
    base = (
        db.query(models.Item)
        .join(models.Source)
        .filter(models.Source.owner_id == user.id, models.Item.fetched_at >= since)
    )
    total = base.count()
    read = base.filter(models.Item.is_read == True).count()  # noqa: E712

    by_source_rows = (
        db.query(models.Source.name, func.count(models.Item.id))
        .join(models.Item)
        .filter(models.Source.owner_id == user.id, models.Item.fetched_at >= since)
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
            "user": user,
        },
    )
