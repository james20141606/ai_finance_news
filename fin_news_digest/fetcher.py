import logging
from datetime import datetime, timezone
from typing import Iterable

import feedparser

from fin_news_digest.models import NewsItem
from fin_news_digest.source_loader import Source
from fin_news_digest.utils import strip_html, truncate

logger = logging.getLogger(__name__)


def _parse_datetime(entry: dict) -> datetime:
    if entry.get("published_parsed"):
        return datetime(*entry["published_parsed"][:6], tzinfo=timezone.utc)
    if entry.get("updated_parsed"):
        return datetime(*entry["updated_parsed"][:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _entry_summary(entry: dict) -> str:
    summary = entry.get("summary") or entry.get("description") or ""
    if not summary and entry.get("content"):
        summary = entry["content"][0].get("value", "")
    summary = strip_html(summary)
    return truncate(summary, 360)


def fetch_sources(sources: Iterable[Source]) -> list[NewsItem]:
    items: list[NewsItem] = []
    for source in sources:
        logger.info("Fetching %s", source.name)
        feed = feedparser.parse(source.url)
        if feed.bozo:
            logger.warning("Feed parse issue for %s: %s", source.name, feed.bozo_exception)
        for entry in feed.entries:
            title = strip_html(entry.get("title", ""))
            link = entry.get("link", "")
            if not title or not link:
                continue
            summary = _entry_summary(entry)
            published = _parse_datetime(entry)
            items.append(
                NewsItem(
                    title=title,
                    link=link,
                    published=published,
                    summary=summary or title,
                    source=source.name,
                    language=source.language,
                    priority=source.priority,
                )
            )
    return items
