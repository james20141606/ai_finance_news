import html
import logging
import re
from datetime import datetime, timezone


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )


def strip_html(text: str) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


_STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "for",
    "to",
    "in",
    "on",
    "of",
    "at",
    "with",
    "from",
    "by",
}


def normalize_title(title: str) -> list[str]:
    if not title:
        return []
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", title.lower())
    tokens = [t for t in cleaned.split() if t and t not in _STOPWORDS]
    return tokens


def jaccard_similarity(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    intersection = set_a.intersection(set_b)
    union = set_a.union(set_b)
    return len(intersection) / max(len(union), 1)
