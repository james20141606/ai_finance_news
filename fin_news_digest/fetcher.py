import logging
from datetime import datetime, timezone
from typing import Iterable

import feedparser
import requests

from fin_news_digest.models import NewsItem
from fin_news_digest.source_loader import Source
from fin_news_digest.utils import strip_html, truncate

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)

# Domains that block feedparser's default UA and need a real browser UA
_CUSTOM_UA_DOMAINS = {"reddit.com", "rsshub.app"}


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


def _needs_custom_ua(url: str) -> bool:
    for domain in _CUSTOM_UA_DOMAINS:
        if domain in url:
            return True
    return False


def _fetch_feed(url: str, source_name: str) -> feedparser.FeedParserDict:
    """Fetch a feed, using requests with a browser UA for domains that need it."""
    if _needs_custom_ua(url):
        try:
            resp = requests.get(url, headers={"User-Agent": _UA}, timeout=30)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        except Exception as exc:
            logger.warning("HTTP fetch failed for %s: %s", source_name, exc)
            feed = feedparser.parse(url)
    else:
        feed = feedparser.parse(url)
    return feed


def fetch_sources(sources: Iterable[Source]) -> list[NewsItem]:
    items: list[NewsItem] = []
    for source in sources:
        logger.info("Fetching %s", source.name)
        feed = _fetch_feed(source.url, source.name)
        if feed.bozo:
            logger.warning("Feed parse issue for %s: %s", source.name, feed.bozo_exception)
        logger.info("Fetched %d entries from %s", len(feed.entries), source.name)
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
