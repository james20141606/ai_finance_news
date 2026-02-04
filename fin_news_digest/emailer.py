import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from jinja2 import Template

from fin_news_digest.models import NewsItem
from fin_news_digest.market_data import MarketSection

logger = logging.getLogger(__name__)


def _render_template(path: str, context: dict) -> str:
    template_text = Path(path).read_text(encoding="utf-8")
    return Template(template_text).render(**context)


def build_message(
    subject: str,
    sender: str,
    recipients: list[str],
    items: list[NewsItem],
    edition_label: str,
    summary_cn: str | None = None,
    market_snapshot: list[MarketSection] | None = None,
) -> EmailMessage:
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    context = {
        "items": items,
        "edition_label": edition_label,
        "date_str": date_str,
        "count": len(items),
        "summary_cn": summary_cn,
        "market_snapshot": market_snapshot or [],
    }
    text_body = _render_template("fin_news_digest/templates/email.txt", context)
    html_body = _render_template("fin_news_digest/templates/email.html", context)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    return msg


def send_email(
    host: str,
    port: int,
    use_tls: bool,
    user: str,
    password: str,
    message: EmailMessage,
) -> None:
    logger.info("Sending email via %s:%s", host, port)
    with smtplib.SMTP(host, port, timeout=30) as server:
        if use_tls:
            server.starttls()
        if user:
            server.login(user, password)
        server.send_message(message)


def send_email_to_each(
    host: str,
    port: int,
    use_tls: bool,
    user: str,
    password: str,
    subject: str,
    sender: str,
    recipients: list[str],
    items: list[NewsItem],
    edition_label: str,
    summary_cn: str | None = None,
    market_snapshot: list[MarketSection] | None = None,
) -> None:
    logger.info("Sending individualized emails to %s recipients", len(recipients))
    with smtplib.SMTP(host, port, timeout=30) as server:
        if use_tls:
            server.starttls()
        if user:
            server.login(user, password)
        for recipient in recipients:
            message = build_message(
                subject=subject,
                sender=sender,
                recipients=[recipient],
                items=items,
                edition_label=edition_label,
                summary_cn=summary_cn,
                market_snapshot=market_snapshot,
            )
            server.send_message(message)
