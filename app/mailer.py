import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, Optional

from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Item

TEMPLATES_DIR = Path(__file__).parent / "templates" / "email"


def render_digest_html(items: List[Item]) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("digest.html")
    return template.render(items=items)


def send_email(to_address: str, subject: str, html_body: str) -> bool:

    if not settings.SMTP_HOST or not to_address:
        print("[mailer] SMTP не настроен (см. .env) или не задан получатель.")
        print("[mailer] Ниже — тело письма, которое было бы отправлено:\n")
        print(html_body)
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.MAIL_FROM or settings.SMTP_USER
    msg["To"] = to_address
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
            server.starttls()
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(msg["From"], [to_address], msg.as_string())
        return True
    except Exception as exc:
        print(f"[mailer] Не удалось отправить письмо: {exc}")
        return False


def send_daily_digest(db: Session, items: List[Item], to_address: Optional[str] = None) -> bool:
    
    if not items:
        return False

    to_address = to_address or settings.MAIL_TO
    subject = f"Дайджест: {len(items)} новых материалов"
    html_body = render_digest_html(items)

    sent = send_email(to_address, subject, html_body)
    if sent:
        for item in items:
            item.is_sent = True
        db.commit()
    return sent
