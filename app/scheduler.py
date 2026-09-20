from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.database import get_session
from app.mailer import send_daily_digest
from app.models import Item
from app.parser import collect_new_items_for_all_sources

_scheduler: BackgroundScheduler | None = None


def run_daily_job():
    db = get_session()
    try:
        results = collect_new_items_for_all_sources(db)
        new_items = [item for items in results.values() for item in items]

        deferred_items = (
            db.query(Item)
            .filter(Item.is_deferred == True, Item.is_sent == True)  # noqa: E712
            .all()
        )

        digest_items = new_items + [i for i in deferred_items if i not in new_items]

        if digest_items:
            send_daily_digest(db, digest_items)
            print(f"[scheduler] Дайджест сформирован: {len(digest_items)} материалов")
        else:
            print("[scheduler] Новых материалов нет, дайджест не отправлен")
    except Exception as exc:
        print(f"[scheduler] Ошибка при выполнении задачи: {exc}")
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
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
