"""Тесты модуля парсинга. Сеть не используется: загрузка страниц подменяется."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import parser
from app.models import Base, Source, SourceType, User

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Test</title>
<item><title>First</title><link>https://example.com/1</link>
<description>&lt;p&gt;Hello&lt;/p&gt;</description></item>
<item><title>Second</title><link>https://example.com/2</link></item>
<item><title>Duplicate</title><link>https://example.com/2</link></item>
</channel></rss>"""

HTML = b"""<html><body>
<div class="post"><a class="t" href="/a1">News A</a></div>
<div class="post"><a class="t" href="/a2">News B</a></div>
</body></html>"""


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture()
def user(db):
    obj = User(email="test@example.com", hashed_password="x")
    db.add(obj)
    db.commit()
    return obj


def make_source(db, user, **kwargs):
    params = dict(
        owner_id=user.id,
        name="Test",
        url="https://example.com/feed.xml",
        type=SourceType.RSS,
    )
    params.update(kwargs)
    source = Source(**params)
    db.add(source)
    db.commit()
    return source


def test_rss_new_items_are_saved_once(db, user, monkeypatch):
    monkeypatch.setattr(parser, "_download", lambda url: RSS)
    source = make_source(db, user)

    first = parser.collect_new_items_for_source(db, source)
    assert [item.title for item in first] == ["First", "Second"]  # дубль ссылки отброшен
    assert source.last_error is None
    assert source.last_found_count == 3

    second = parser.collect_new_items_for_source(db, source)
    assert second == []
    assert source.last_new_count == 0


def test_html_in_summary_is_cleaned(db, user, monkeypatch):
    monkeypatch.setattr(parser, "_download", lambda url: RSS)
    source = make_source(db, user)
    items = parser.collect_new_items_for_source(db, source)
    assert items[0].summary == "Hello"


def test_clean_summary_truncates_long_text():
    result = parser._clean_summary("слово " * 200, max_len=20)
    assert result.endswith("…")
    assert len(result) <= 21


def test_page_without_feed_gives_readable_error(db, user, monkeypatch):
    monkeypatch.setattr(parser, "_download", lambda url: b"<html><head></head><body>hi</body></html>")
    source = make_source(db, user)
    assert parser.collect_new_items_for_source(db, source) == []
    assert "RSS" in source.last_error


def test_network_error_is_saved_in_source(db, user, monkeypatch):
    def broken(url):
        raise parser.FetchError("Не удалось подключиться к сайту: ConnectionError")

    monkeypatch.setattr(parser, "_download", broken)
    source = make_source(db, user)
    assert parser.collect_new_items_for_source(db, source) == []
    assert "подключиться" in source.last_error


def test_html_source_by_css_selectors(db, user, monkeypatch):
    monkeypatch.setattr(parser, "_download", lambda url: HTML)
    source = make_source(
        db,
        user,
        url="https://example.com/news",
        type=SourceType.HTML,
        html_item_selector=".post",
        html_title_selector=".t",
        html_link_selector=".t",
    )
    items = parser.collect_new_items_for_source(db, source)
    assert [item.link for item in items] == [
        "https://example.com/a1",
        "https://example.com/a2",
    ]


def test_html_source_without_selector_gives_error(db, user):
    source = make_source(db, user, type=SourceType.HTML)
    assert parser.collect_new_items_for_source(db, source) == []
    assert "селектор" in source.last_error
