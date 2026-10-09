"""
Формирование и отправка email-дайджеста.

Что исправлено:
- Раньше в письмо попадали только материалы, найденные в ТЕКУЩЕМ запуске
  парсера. Если письмо не уходило (SMTP не настроен или сбой), эти материалы
  оставались is_sent=False и больше никогда не попадали ни в одно письмо.
  Теперь дайджест = все ещё не отправленные и не прочитанные материалы
  пользователя (не больше DIGEST_LIMIT штук за раз), плюс отложенные.
- Порт 465 (Яндекс, Mail.ru) требует SSL с первого байта; STARTTLS там не работает.
- Причина неудачи возвращается наружу и показывается в интерфейсе.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import List, Tuple

from jinja2 import Environment, FileSystemLoader
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Item, Source, User

logger = logging.getLogger("contentharvest")

TEMPLATES_DIR = Path(__file__).parent / "templates" / "email"
DIGEST_LIMIT = 50


def render_digest_html(items: List[Item]) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    return env.get_template("digest.html").render(items=items)


def smtp_configured() -> bool:
    return bool(settings.SMTP_HOST and (settings.MAIL_FROM or settings.SMTP_USER))


def send_email(to_address: str, subject: str, html_body: str) -> Tuple[bool, str]:
    """Возвращает (успех, сообщение). Сообщение — причина неудачи или пустая строка."""
    if not to_address:
        return False, "Не указан адрес получателя"
    if not smtp_configured():
        return False, "SMTP не настроен: задайте переменные SMTP_HOST, SMTP_USER, SMTP_PASSWORD"

    sender = settings.MAIL_FROM or settings.SMTP_USER
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_address
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    use_ssl = settings.SMTP_PORT == 465
    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    try:
        with smtp_class(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
            if not use_ssl:
                server.ehlo()
                server.starttls()
                server.ehlo()
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(sender, [to_address], msg.as_string())
        return True, ""
    except smtplib.SMTPAuthenticationError:
        return False, "SMTP отклонил логин/пароль (для Яндекса и Mail.ru нужен пароль приложения)"
    except Exception as exc:
        logger.exception("Ошибка отправки письма")
        return False, f"Ошибка отправки: {type(exc).__name__}: {exc}"


def build_digest_items(db: Session, user: User) -> List[Item]:
    return (
        db.query(Item)
        .join(Source)
        .filter(
            Source.owner_id == user.id,
            or_(
                (Item.is_sent == False) & (Item.is_read == False),  # noqa: E712
                Item.is_deferred == True,  # noqa: E712
            ),
        )
        .order_by(Item.fetched_at.desc())
        .limit(DIGEST_LIMIT)
        .all()
    )


def send_digest_for_user(db: Session, user: User) -> Tuple[bool, str]:
    """
    Собирает и отправляет дайджест одному пользователю на его email.
    Возвращает (успех, сообщение для пользователя).
    """
    items = build_digest_items(db, user)
    if not items:
        return False, "Нет новых материалов для дайджеста"

    ok, error = send_email(
        user.email, f"ContentHarvest: {len(items)} новых материалов", render_digest_html(items)
    )
    if not ok:
        logger.warning("Дайджест для %s не отправлен: %s", user.email, error)
        return False, error

    for item in items:
        item.is_sent = True
        item.is_deferred = False  # напоминание «отложенного» сработало один раз
    db.commit()
    logger.info("Дайджест отправлен: %s, материалов: %d", user.email, len(items))
    return True, f"Дайджест из {len(items)} материалов отправлен на {user.email}"
