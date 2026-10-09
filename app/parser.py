"""
Модуль парсинга источников.

Что исправлено по сравнению с первой версией:
- feedparser.parse(url) не имел таймаута: один «зависший» сайт блокировал весь
  фоновый обход навсегда. Теперь скачиваем через requests с таймаутом.
- Если вместо RSS-ленты указана обычная страница сайта, раньше получался
  пустой результат без единого сообщения. Теперь: сначала пробуем найти
  ссылку на ленту в <head> страницы, а если не нашли — сохраняем понятную
  причину в source.last_error, и она видна в интерфейсе.
- Дубли ссылок внутри одной ленты роняли сохранение всей пачки.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.models import Item, Source, SourceType

logger = logging.getLogger("contentharvest")

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ContentHarvest/1.0; personal feed reader)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html;q=0.8, */*;q=0.5",
}
REQUEST_TIMEOUT = 15


class FetchError(Exception):
    """Источник не удалось обработать. Текст ошибки показывается пользователю."""


def _download(url: str) -> bytes:
    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else "?"
        raise FetchError(f"Сайт ответил ошибкой HTTP {code}")
    except requests.RequestException as exc:
        raise FetchError(f"Не удалось подключиться к сайту: {type(exc).__name__}")
    return response.content


def _discover_feed_url(html: bytes, base_url: str) -> Optional[str]:
    """Ищет в <head> страницы ссылку на RSS/Atom-ленту."""
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("link", href=True):
        rel = " ".join(link.get("rel", [])).lower()
        kind = (link.get("type") or "").lower()
        if "alternate" in rel and ("rss" in kind or "atom" in kind):
            return urljoin(base_url, link["href"])
    return None


def fetch_rss_entries(source: Source) -> List[Dict]:
    """Скачивает и разбирает RSS/Atom-ленту. При проблемах бросает FetchError."""
    if source.url.startswith("file://"):
        parsed = feedparser.parse(source.url)  # локальные файлы — для демо и тестов
    else:
        content = _download(source.url)
        parsed = feedparser.parse(content)

        if not parsed.version:
            # Это не лента. Возможно, пользователь указал адрес обычной страницы.
            feed_url = _discover_feed_url(content, source.url)
            if feed_url and feed_url != source.url:
                logger.info("Источник '%s': найдена лента %s", source.name, feed_url)
                parsed = feedparser.parse(_download(feed_url))

    if not parsed.version:
        raise FetchError(
            "По этому адресу нет RSS/Atom-ленты. Укажите прямую ссылку на ленту "
            "или добавьте источник как «HTML» с CSS-селекторами."
        )

    entries = []
    for entry in parsed.entries:
        link = (entry.get("link") or "").strip()
        if not link:
            continue
        entries.append(
            {
                "title": (entry.get("title") or "Без заголовка").strip(),
                "link": link,
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
    # В summary у многих лент лежит HTML — оставляем только текст
    text = BeautifulSoup(raw_summary or "", "html.parser").get_text(" ", strip=True)
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0] + "…"
    return text


def fetch_html_entries(source: Source) -> List[Dict]:
    """Парсит HTML-страницу по CSS-селекторам пользователя. При проблемах бросает FetchError."""
    if not source.html_item_selector:
        raise FetchError("Для HTML-источника не задан селектор блока материала")

    content = _download(source.url)
    soup = BeautifulSoup(content, "html.parser")

    try:
        blocks = soup.select(source.html_item_selector)
    except Exception:
        raise FetchError("Некорректный CSS-селектор блока материала")

    if not blocks:
        raise FetchError(
            f"Селектор «{source.html_item_selector}» не нашёл ни одного блока на странице "
            "(возможно, сайт подгружает материалы через JavaScript)"
        )

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
                "title": title or "Без заголовка",
                "link": urljoin(source.url, href),
                "summary": "",
                "published_at": None,
            }
        )
    return entries


def fetch_entries_for_source(source: Source) -> List[Dict]:
    if source.type == SourceType.RSS:
        return fetch_rss_entries(source)
    if source.type == SourceType.HTML:
        return fetch_html_entries(source)
    raise FetchError(f"Неизвестный тип источника: {source.type}")


def filter_new_entries(db: Session, source: Source, entries: List[Dict]) -> List[Dict]:
    """Оставляет записи, которых ещё нет в БД, и убирает дубли внутри самой пачки."""
    if not entries:
        return []

    seen = {link for (link,) in db.query(Item.link).filter(Item.source_id == source.id).all()}
    fresh = []
    for entry in entries:
        link = entry["link"][:700]
        if link in seen:
            continue
        seen.add(link)
        fresh.append(entry)
    return fresh


def save_new_items(db: Session, source: Source, new_entries: List[Dict]) -> List[Item]:
    items = []
    for entry in new_entries:
        item = Item(
            source_id=source.id,
            title=entry["title"][:500],
            link=entry["link"][:700],
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
    """
    Проверяет один источник, сохраняет новые материалы и записывает результат
    проверки в сам источник (last_checked_at / last_error / last_*_count).
    Никогда не бросает исключений наружу — ошибка попадает в source.last_error.
    """
    source.last_checked_at = datetime.utcnow()
    try:
        entries = fetch_entries_for_source(source)
        new_entries = filter_new_entries(db, source, entries)
        items = save_new_items(db, source, new_entries)

        source.last_error = None
        source.last_found_count = len(entries)
        source.last_new_count = len(items)
        db.commit()
        logger.info("Источник '%s': в источнике %d, новых %d", source.name, len(entries), len(items))
        return items

    except FetchError as exc:
        db.rollback()
        _record_failure(db, source, str(exc))
        logger.warning("Источник '%s' (%s): %s", source.name, source.url, exc)
        return []
    except Exception as exc:
        db.rollback()
        _record_failure(db, source, f"Внутренняя ошибка: {type(exc).__name__}")
        logger.exception("Источник '%s': непредвиденная ошибка", source.name)
        return []


def _record_failure(db: Session, source: Source, message: str):
    source.last_checked_at = datetime.utcnow()
    source.last_error = message[:500]
    source.last_found_count = 0
    source.last_new_count = 0
    db.commit()


def collect_new_items_for_all_sources(db: Session) -> Dict[int, List[Item]]:
    """Обходит ВСЕ активные источники всех пользователей. Ключ результата — source.id."""
    result = {}
    for source in db.query(Source).filter(Source.is_active == True).all():  # noqa: E712
        result[source.id] = collect_new_items_for_source(db, source)
    return result
