import os

from app.database import init_db, get_session
from app.models import Source, SourceType, Item, User
from app.parser import collect_new_items_for_source
from app.security import hash_password

FEED_PATH = os.path.join(os.path.dirname(__file__), "..", "tests", "sample_feed.xml")
FEED_URL = f"file://{os.path.abspath(FEED_PATH)}"


def main():
    db_path = os.path.join(os.path.dirname(__file__), "..", "aggregator.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    init_db()
    db = get_session()

    demo_user = User(email="demo@example.com", hashed_password=hash_password("demo12345"))
    db.add(demo_user)
    db.commit()
    db.refresh(demo_user)
    print(f"Создан демо-пользователь: {demo_user.email}\n")

    source = Source(
        owner_id=demo_user.id,
        name="Тестовый блог о спортивной аналитике",
        url=FEED_URL,
        type=SourceType.RSS,
        category="спорт",
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    print(f"Добавлен источник: {source}\n")

    print("Первый запуск парсера (ожидаем 2 новых материала)")
    new_items = collect_new_items_for_source(db, source)
    for item in new_items:
        print(f"  + {item.title}\n    {item.link}\n    дата публикации: {item.published_at}\n")

    print("=== Повторный запуск парсера (ожидаем 0 новых материалов) ===")
    new_items_again = collect_new_items_for_source(db, source)
    print(f"  Новых материалов найдено: {len(new_items_again)}\n")

    print("=== Весь архив по источнику ===")
    all_items = db.query(Item).filter(Item.source_id == source.id).all()
    for item in all_items:
        status = "прочитано" if item.is_read else "не прочитано"
        print(f"  - [{status}] {item.title}")

    db.close()


if __name__ == "__main__":
    main()
