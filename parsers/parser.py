from datetime import datetime
from typing import List, Dict, Optional

import feedparser
from sqlalchemy.orm import Session

from models import Source, Item, SourceType


def fetch_rss_entries(source: Source) -> List[Dict]:
    
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


def fetch_entries_for_source(source: Source) -> List[Dict]:
    
    if source.type == SourceType.RSS:
        return fetch_rss_entries(source)
    elif source.type == SourceType.HTML:
        # Заготовка под этап "парсинг статических страниц" (пока не реализован —
        # появится когда будем обрабатывать источники без RSS через BeautifulSoup
        # + html_item_selector / html_title_selector / html_link_selector из Source).
        raise NotImplementedError(
            "Парсинг HTML-источников будет добавлен на следующем этапе"
        )
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
    
    result = {}
    active_sources = db.query(Source).filter(Source.is_active == True).all()  # noqa: E712
    for source in active_sources:
        try:
            new_items = collect_new_items_for_source(db, source)
            result[source.name] = new_items
        except Exception as exc:
            print(f"[parser] Ошибка при обработке источника '{source.name}': {exc}")
            result[source.name] = []
    return result
