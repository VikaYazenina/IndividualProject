"""
Модели SQLAlchemy для сервиса агрегации контента.

User    — зарегистрированный пользователь (email + пароль)
Source  — источник контента, ПРИНАДЛЕЖИТ конкретному пользователю (owner_id)
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


class User(Base):
    """Зарегистрированный пользователь сервиса."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    sources = relationship("Source", back_populates="owner", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User id={self.id} email={self.email!r}>"


class SourceType(str, enum.Enum):
    RSS = "rss"
    HTML = "html"  # для страниц без RSS-ленты (нужен свой парсер под конкретный сайт)


class Source(Base):
    """Источник контента, за которым следит конкретный пользователь."""

    __tablename__ = "sources"
    __table_args__ = (
        # Один и тот же URL могут отслеживать РАЗНЫЕ пользователи — уникальность
        # только в пределах одного владельца, а не глобально по всей таблице.
        UniqueConstraint("owner_id", "url", name="uq_source_owner_url"),
    )

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    name = Column(String(200), nullable=False)
    url = Column(String(500), nullable=False)
    type = Column(Enum(SourceType), nullable=False, default=SourceType.RSS)
    category = Column(String(100), nullable=True)  # тэг/категория для группировки
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # CSS-селекторы для источников типа HTML (когда нет RSS)
    html_item_selector = Column(String(300), nullable=True)
    html_title_selector = Column(String(300), nullable=True)
    html_link_selector = Column(String(300), nullable=True)

    owner = relationship("User", back_populates="sources")
    items = relationship("Item", back_populates="source", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Source id={self.id} owner_id={self.owner_id} name={self.name!r}>"


class Item(Base):
    """Отдельный материал (статья/пост/апдейт), найденный в источнике."""

    __tablename__ = "items"
    __table_args__ = (UniqueConstraint("source_id", "link", name="uq_item_source_link"),)

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
