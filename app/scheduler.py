"""
Планировщик: две независимые задачи.

1. parse_all_job   — каждые PARSE_INTERVAL_HOURS часов (по умолчанию 3) обходит
                      источники ВСЕХ пользователей. Первый запуск — через 20 секунд
                      после старта сервера.
2. send_digests_job — раз в сутки в DIGEST_HOUR (по умолчанию 9:00 по TIMEZONE)
                      отправляет каждому пользователю дайджест на его email.

Что исправлено: раньше была одна задача «раз в 24 часа от момента старта».
Таймер сбрасывался при каждом перезапуске контейнера (деплой, обновление,
перезапуск хостингом), и если сервис перезапускался чаще раза в сутки, парсинг
не выполнялся вообще. Плюс одна зависшая загрузка блокировала все последующие
запуски. Все ошибки теперь пишутся в лог через logging (print при запуске
не в терминале буферизуется и в логах хостинга может не появляться).
"""

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.database import get_session
from app.mailer import send_digest_for_user, smtp_configured
from app.models import User
from app.parser import collect_new_items_for_all_sources

logger = logging.getLogger("contentharvest")

_scheduler: BackgroundScheduler | None = None


def parse_all_job():
    db = get_session()
    try:
        results = collect_new_items_for_all_sources(db)
        total_new = sum(len(items) for items in results.values())
        logger.info("Парсинг завершён: источников %d, новых материалов %d", len(results), total_new)
    except Exception:
        logger.exception("Ошибка в задаче парсинга")
    finally:
        db.close()


def send_digests_job():
    db = get_session()
    try:
        for user in db.query(User).all():
            try:
                send_digest_for_user(db, user)
            except Exception:
                db.rollback()
                logger.exception("Ошибка при отправке дайджеста пользователю %s", user.email)
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        parse_all_job,
        "interval",
        hours=settings.PARSE_INTERVAL_HOURS,
        id="parse_all",
        next_run_time=datetime.now() + timedelta(seconds=20),
        max_instances=1,
        coalesce=True,
    )
    _scheduler.add_job(
        send_digests_job,
        CronTrigger(hour=settings.DIGEST_HOUR, minute=0, timezone=settings.TIMEZONE),
        id="send_digests",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    _scheduler.start()

    db_kind = settings.DATABASE_URL.split("://")[0]
    db_path = settings.DATABASE_URL.split("///", 1)[-1] if db_kind == "sqlite" else "(внешняя БД)"
    logger.info(
        "Планировщик запущен: парсинг каждые %s ч., дайджест в %02d:00 (%s). БД: %s %s. SMTP: %s",
        settings.PARSE_INTERVAL_HOURS,
        settings.DIGEST_HOUR,
        settings.TIMEZONE,
        db_kind,
        db_path,
        "настроен" if smtp_configured() else "НЕ НАСТРОЕН — письма отправляться не будут",
    )
    return _scheduler


def stop_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
