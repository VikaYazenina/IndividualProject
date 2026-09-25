"""
Модуль парсинга источников.

Этап 2 плана: "написание модуля для получения RSS-лент",
"создание функции, возвращающей новые материалы для любого источника".

Логика:
1. fetch_rss_entries(source)      — скачивает и разбирает RSS/Atom-ленту
2. filter_new_entries(...)        — оставляет только те записи, которых ещё нет в БД
3. save_new_items(...)            — сохраняет новые записи как объекты Item
4. collect_new_items_for_source() — точка входа: "дай мне всё новое из этого источника"
"""

from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.models import Source, Item, SourceType

REQUEST_HEADERS = {"User-Agent": "ContentAggregatorBot/1.0 (+personal use)"}
REQUEST_TIMEOUT = 10


def fetch_rss_entries(source: Source) -> List[Dict]:
    """
    Скачивает RSS/Atom-ленту источника и возвращает список записей
    в унифицированном виде: title, link, summary, published_at.
    """
    parsed = feedparser.parse(source.url)

    if parsed.bozo and not parsed.entries:
        return []

    entries = []
    for entry in parsed.entries:
        entries.append(
            {
                "title": entry.get("title", "Без заголовка").strip(),
                "link": entry.get("link", "").strip(),
                "summary": _clean_summary(entry.get("summary", "")),
                "published_at": _parse_date(entry),
            }
        )
    return entries


def _parse_date(entry) -> Optional[datetime]:
    time_struct = entry.get("published_parsed") or entry.get("updated_parsed")
    if time_struct is None:
        return None
    return datetime(*time_struct[:6])


def _clean_summary(raw_summary: str, max_len: int = 500) -> str:
    text = raw_summary.strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0] + "…"
    return text


def fetch_html_entries(source: Source) -> List[Dict]:
    if not source.html_item_selector:
        print(f"[parser] У источника '{source.name}' не задан html_item_selector — пропускаю")
        return []

    try:
        response = requests.get(source.url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"[parser] Не удалось загрузить '{source.url}': {exc}")
        return []

    soup = BeautifulSoup(response.content, "html.parser")
    blocks = soup.select(source.html_item_selector)

    entries = []
    for block in blocks:
        title_el = block.select_one(source.html_title_selector) if source.html_title_selector else block
        link_el = block.select_one(source.html_link_selector) if source.html_link_selector else block

        title = title_el.get_text(strip=True) if title_el else "Без заголовка"

        href = None
        if link_el is not None:
            href = link_el.get("href") or (link_el.find("a").get("href") if link_el.find("a") else None)
        if not href:
            continue

        entries.append(
            {
                "title": title,
                "link": urljoin(source.url, href),
                "summary": "",
                "published_at": None,
            }
        )
    return entries


def fetch_entries_for_source(source: Source) -> List[Dict]:
    if source.type == SourceType.RSS:
        return fetch_rss_entries(source)
    elif source.type == SourceType.HTML:
        return fetch_html_entries(source)
    else:
        raise ValueError(f"Неизвестный тип источника: {source.type}")


def filter_new_entries(db: Session, source: Source, entries: List[Dict]) -> List[Dict]:
    if not entries:
        return []

    existing_links = {
        link for (link,) in db.query(Item.link).filter(Item.source_id == source.id).all()
    }
    return [e for e in entries if e["link"] and e["link"] not in existing_links]


def save_new_items(db: Session, source: Source, new_entries: List[Dict]) -> List[Item]:
    items = []
    for entry in new_entries:
        item = Item(
            source_id=source.id,
            title=entry["title"],
            link=entry["link"],
            summary=entry["summary"],
            published_at=entry["published_at"],
        )
        db.add(item)
        items.append(item)

    if items:
        db.commit()
        for item in items:
            db.refresh(item)

    return items


def collect_new_items_for_source(db: Session, source: Source) -> List[Item]:
    entries = fetch_entries_for_source(source)
    new_entries = filter_new_entries(db, source, entries)
    return save_new_items(db, source, new_entries)


def collect_new_items_for_all_sources(db: Session) -> Dict[str, List[Item]]:
    """Проходит по ВСЕМ активным источникам всех пользователей (используется планировщиком)."""
    result = {}
    active_sources = db.query(Source).filter(Source.is_active == True).all()  # noqa: E712
    for source in active_sources:
        try:
            new_items = collect_new_items_for_source(db, source)
            result[source.id] = new_items
        except Exception as exc:
            print(f"[parser] Ошибка при обработке источника '{source.name}': {exc}")
            result[source.id] = []
    return result
