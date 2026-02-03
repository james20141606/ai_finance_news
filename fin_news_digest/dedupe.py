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


def rank_items(items: list[NewsItem], max_items: int) -> list[NewsItem]:
    items.sort(key=lambda x: (x.priority, x.published), reverse=True)
    return items[:max_items]
