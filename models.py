"""
Модели SQLAlchemy для сервиса агрегации контента.

Source  — источник контента (RSS-лента или страница для парсинга)
Item    — конкретный материал, найденный в источнике
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Enum,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class SourceType(str, enum.Enum):
    RSS = "rss"
    HTML = "html"  # для страниц без RSS-ленты (нужен свой парсер под конкретный сайт)


class Source(Base):
    """Источник контента, за которым следит пользователь."""

    __tablename__ = "sources"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    url = Column(String(500), nullable=False, unique=True)
    type = Column(Enum(SourceType), nullable=False, default=SourceType.RSS)
    category = Column(String(100), nullable=True)  # тэг/категория для группировки
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # На будущее: CSS-селекторы для источников типа HTML (когда нет RSS)
    html_item_selector = Column(String(300), nullable=True)
    html_title_selector = Column(String(300), nullable=True)
    html_link_selector = Column(String(300), nullable=True)

    items = relationship("Item", back_populates="source", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Source id={self.id} name={self.name!r} type={self.type}>"


class Item(Base):
    """Отдельный материал (статья/пост/апдейт), найденный в источнике."""

    __tablename__ = "items"
    __table_args__ = (UniqueConstraint("link", name="uq_item_link"),)

    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)

    title = Column(String(500), nullable=False)
    link = Column(String(700), nullable=False)
    summary = Column(Text, nullable=True)

    published_at = Column(DateTime, nullable=True)   # дата публикации на источнике
    fetched_at = Column(DateTime, default=datetime.utcnow)  # когда мы это нашли

    is_read = Column(Boolean, default=False)
    is_deferred = Column(Boolean, default=False)      # "отложенное прочтение" -> попадёт в следующее письмо
    is_sent = Column(Boolean, default=False)           # уже включено в рассылку

    source = relationship("Source", back_populates="items")

    def __repr__(self):
        return f"<Item id={self.id} title={self.title[:40]!r}>"
