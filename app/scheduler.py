"""
Планировщик регулярного парсинга и рассылки (этап 4 плана).

Раньше был один общий дайджест на всех посетителей сайта, и слать его было
некуда — email нигде не собирался. Теперь: обходим источники ВСЕХ
пользователей одним махом (это дёшево — просто HTTP-запросы), а письма
формируем и шлём КАЖДОМУ пользователю отдельно, только по его источникам,
на его email из регистрации.
"""

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.database import get_session
from app.mailer import send_daily_digest
from app.models import Item, Source, User
from app.parser import collect_new_items_for_all_sources

_scheduler: BackgroundScheduler | None = None


def run_daily_job():
    """Один цикл: спарсить источники всех пользователей + отправить каждому свой дайджест."""
    db = get_session()
    try:
        # Парсим один раз все активные источники (не важно, чьи) — результат
        # уже лежит в БД, дальше просто раскладываем его по пользователям.
        results_by_source_id = collect_new_items_for_all_sources(db)

        users = db.query(User).all()
        for user in users:
            user_source_ids = {
                s.id for s in db.query(Source).filter(Source.owner_id == user.id).all()
            }
            new_items = [
                item
                for source_id, items in results_by_source_id.items()
                if source_id in user_source_ids
                for item in items
            ]

            # Отложенные материалы этого пользователя возвращаются в дайджест ещё раз
            deferred_items = (
                db.query(Item)
                .join(Source)
                .filter(
                    Source.owner_id == user.id,
                    Item.is_deferred == True,  # noqa: E712
                    Item.is_sent == True,  # noqa: E712
                )
                .all()
            )

            digest_items = new_items + [i for i in deferred_items if i not in new_items]

            if digest_items:
                send_daily_digest(db, digest_items, to_address=user.email)
                print(f"[scheduler] {user.email}: дайджест {len(digest_items)} материалов")
    except Exception as exc:
        # Ошибка в одном цикле не должна "убивать" весь процесс планировщика
        print(f"[scheduler] Ошибка при выполнении задачи: {exc}")
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    """Запускает планировщик (идемпотентно — повторный вызов ничего не сломает)."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        run_daily_job,
        "interval",
        hours=settings.PARSE_INTERVAL_HOURS,
        id="daily_parse_job",
    )
    _scheduler.start()
    print(f"[scheduler] Запущен, интервал: {settings.PARSE_INTERVAL_HOURS} ч.")
    return _scheduler


def stop_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
