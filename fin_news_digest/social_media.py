from dataclasses import dataclass, field

from fin_news_digest.models import NewsItem

SOCIAL_CATEGORIES = {"twitter", "xueqiu", "reddit"}

PLATFORM_LABELS = {
    "twitter": "Twitter / X",
    "xueqiu": "\u96ea\u7403 Xueqiu",
    "reddit": "Reddit",
}

PLATFORM_ORDER = ["twitter", "xueqiu", "reddit"]


@dataclass
class SocialMediaGroup:
    platform: str
    platform_key: str
    items: list[NewsItem] = field(default_factory=list)


def extract_social_media(
    items: list[NewsItem],
) -> list[SocialMediaGroup]:
    """Group items whose source_category is a social platform.

    Returns a list of SocialMediaGroup sorted by PLATFORM_ORDER.
    The original *items* list is NOT modified (social items remain in the
    main news flow as well).
    """
    buckets: dict[str, list[NewsItem]] = {}
    for item in items:
        cat = item.source_category
        if cat in SOCIAL_CATEGORIES:
            buckets.setdefault(cat, []).append(item)

    groups: list[SocialMediaGroup] = []
    for key in PLATFORM_ORDER:
        if key in buckets:
            groups.append(
                SocialMediaGroup(
                    platform=PLATFORM_LABELS.get(key, key),
                    platform_key=key,
                    items=buckets[key],
                )
            )
    return groups
