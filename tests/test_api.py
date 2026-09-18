import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.deps import get_db
from app.main import app


@pytest.fixture()
def client():
    # StaticPool: TestClient обращается к приложению из разных потоков,
    # без него каждое подключение к ":memory:" получало бы отдельную (пустую) БД.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_create_and_list_source(client):
    response = client.post(
        "/api/sources/",
        json={"name": "Тестовый источник", "url": "https://example.com/rss", "type": "rss", "category": "спорт"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Тестовый источник"
    assert body["category"] == "спорт"

    response = client.get("/api/sources/")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_duplicate_source_url_rejected(client):
    payload = {"name": "A", "url": "https://example.com/feed", "type": "rss"}
    first = client.post("/api/sources/", json=payload)
    assert first.status_code == 201

    second = client.post("/api/sources/", json={**payload, "name": "B"})
    assert second.status_code == 400


def test_delete_source(client):
    created = client.post(
        "/api/sources/", json={"name": "Удалить меня", "url": "https://example.com/x", "type": "rss"}
    ).json()

    response = client.delete(f"/api/sources/{created['id']}")
    assert response.status_code == 204

    response = client.get(f"/api/sources/{created['id']}")
    assert response.status_code == 404


def test_items_stats_endpoint_empty(client):
    response = client.get("/api/items/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["collected"] == 0
    assert body["read"] == 0


def test_web_pages_render(client):
    for path in ["/archive", "/sources", "/stats"]:
        response = client.get(path)
        assert response.status_code == 200
        assert "<html" in response.text.lower()
