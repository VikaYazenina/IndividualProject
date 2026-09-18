import http.server
import os
import threading

import pytest

from app.database import Base
from app.models import Source, SourceType, Item
from app.parser import collect_new_items_for_source
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TESTS_DIR = os.path.dirname(__file__)
FEED_PATH = os.path.join(TESTS_DIR, "sample_feed.xml")
FEED_URL = f"file://{FEED_PATH}"


@pytest.fixture(scope="module")
def local_http_server():
    """Локальный HTTP-сервер, отдающий файлы из папки tests/ — для проверки HTML-парсинга."""
    handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(
        *args, directory=TESTS_DIR, **kwargs
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture()
def db_session():
    """Изолированная in-memory БД для каждого теста."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def sample_source(db_session):
    source = Source(name="Тестовый источник", url=FEED_URL, type=SourceType.RSS, category="спорт")
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


def test_collect_new_items_finds_two_entries(db_session, sample_source):
    new_items = collect_new_items_for_source(db_session, sample_source)
    assert len(new_items) == 2
    titles = {item.title for item in new_items}
    assert "Как читать xG-статистику в футболе" in titles


def test_collect_new_items_is_idempotent(db_session, sample_source):
    collect_new_items_for_source(db_session, sample_source)
    second_run = collect_new_items_for_source(db_session, sample_source)
    assert second_run == []

    total_items = db_session.query(Item).filter(Item.source_id == sample_source.id).count()
    assert total_items == 2


def test_html_parser_finds_entries(db_session, local_http_server):
    """Проверяет парсинг статической HTML-страницы через заданные CSS-селекторы."""
    source = Source(
        name="Тестовый сайт без RSS",
        url=f"{local_http_server}/sample_page.html",
        type=SourceType.HTML,
        html_item_selector=".post-card",
        html_title_selector=".post-title",
        html_link_selector="a.post-link",
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    new_items = collect_new_items_for_source(db_session, source)
    assert len(new_items) == 2
    titles = {item.title for item in new_items}
    assert "Разбор тактики 4-3-3 в современном футболе" in titles
    # Относительная ссылка должна быть превращена в абсолютную
    assert all(item.link.startswith("http://127.0.0.1") for item in new_items)


def test_html_parser_without_selector_returns_empty(db_session, local_http_server):
    """Без html_item_selector источник HTML-типа должен просто пропускаться, а не падать."""
    source = Source(
        name="Источник без селектора",
        url=f"{local_http_server}/sample_page.html",
        type=SourceType.HTML,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    new_items = collect_new_items_for_source(db_session, source)
    assert new_items == []
