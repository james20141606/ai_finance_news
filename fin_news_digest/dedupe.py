import logging
from datetime import datetime, timedelta, timezone

from fin_news_digest.models import NewsItem
from fin_news_digest.utils import jaccard_similarity, normalize_title

logger = logging.getLogger(__name__)


def _within_lookback(item: NewsItem, lookback_hours: int) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    return item.published >= cutoff


def filter_recent(items: list[NewsItem], lookback_hours: int) -> list[NewsItem]:
    return [item for item in items if _within_lookback(item, lookback_hours)]


def dedupe_items(items: list[NewsItem], similarity_threshold: float = 0.86) -> list[NewsItem]:
    deduped: list[NewsItem] = []
    normalized = []

    for item in items:
        tokens = normalize_title(item.title)
        is_dup = False
        for idx, existing in enumerate(normalized):
            similarity = jaccard_similarity(tokens, existing)
            if similarity >= similarity_threshold:
                is_dup = True
                # Prefer higher priority source or more recent timestamp
                current = deduped[idx]
                if (item.priority, item.published) > (current.priority, current.published):
                    deduped[idx] = item
                    normalized[idx] = tokens
                break
        if not is_dup:
            deduped.append(item)
            normalized.append(tokens)

    logger.info("Deduped %s -> %s", len(items), len(deduped))
    return deduped


_BJ_KEYWORDS = {
    "china",
    "chinese",
    "beijing",
    "shanghai",
    "shenzhen",
    "hong kong",
    "hongkong",
    "rmb",
    "yuan",
    "pboc",
    "a-share",
    "a shares",
    "china stocks",
    "china economy",
    "cn",
    "中国",
    "中资",
    "人民币",
    "央行",
    "港股",
    "沪深",
    "上证",
    "深证",
    "A股",
}

_NY_KEYWORDS = {
    "u.s.",
    "us ",
    "united states",
    "america",
    "fed",
    "federal reserve",
    "wall street",
    "s&p",
    "nasdaq",
    "dow",
    "treasury",
    "cpi",
    "jobs report",
    "nfp",
    "sec",
    "white house",
}


def _keyword_boost(text: str, keywords: set[str]) -> float:
    score = 0.0
    for keyword in keywords:
        if keyword in text:
            score += 1.0
    return score


def _edition_boost(item: NewsItem, edition_label: str) -> float:
    if not edition_label:
        return 0.0
    text = f"{item.title} {item.summary}"
    text_lower = text.lower()
    if edition_label.startswith("BJ"):
        return _keyword_boost(text_lower, _BJ_KEYWORDS)
    if edition_label.startswith("NY"):
        return _keyword_boost(text_lower, _NY_KEYWORDS)
    return 0.0


def rank_items(
    items: list[NewsItem],
    max_items: int,
    edition_label: str = "",
) -> list[NewsItem]:
    items.sort(
        key=lambda x: (x.priority + _edition_boost(x, edition_label), x.published),
        reverse=True,
    )
    return items[:max_items]
