"""
Export the latest finance digest as a JSON feed file.

Usage:
    python -m fin_news_digest.export_feed [--output path/to/news-feed.json]

Architecture:
    - news-feed.json contains an "editions" array
    - Each pipeline run APPENDS a new edition (not overwrite)
    - Editions are kept for up to 90 days (configurable)
    - The blog news page displays all editions, newest first
"""

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from fin_news_digest.config import load_config
from fin_news_digest.dedupe import dedupe_items, filter_recent, rank_items
from fin_news_digest.enrich import add_bilingual_fields
from fin_news_digest.fetcher import fetch_sources
from fin_news_digest.market_data import build_market_snapshot
from fin_news_digest.news_summary import OpenAISummaryConfig, summarize_cn
from fin_news_digest.sector_data import build_sector_rankings
from fin_news_digest.sector_advisor import AdvisorConfig, generate_recommendations
from fin_news_digest.social_media import extract_social_media
from fin_news_digest.social_summary import SocialSummaryConfig, summarize_social_cn
from fin_news_digest.market_hotspots import HotspotsConfig, generate_market_hotspots
from fin_news_digest.source_loader import load_sources
from fin_news_digest.state import filter_sent, load_state, save_state
from fin_news_digest.translator import (
    TranslatorConfig,
    build_translator,
    reset_translation_stats,
)
from fin_news_digest.utils import configure_logging

logger = logging.getLogger(__name__)

KEEP_DAYS = 90  # Keep editions for 90 days


def _load_existing_feed(path: str) -> dict:
    """Load existing feed file, return empty structure if not found."""
    p = Path(path)
    if not p.exists():
        return {"editions": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        # Handle old single-edition format: migrate to editions array
        if "editions" not in data and "items" in data:
            return {"editions": [data]}
        return data
    except (json.JSONDecodeError, KeyError):
        return {"editions": []}


def _prune_old_editions(feed: dict, keep_days: int) -> dict:
    """Remove editions older than keep_days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).isoformat()
    feed["editions"] = [
        e for e in feed["editions"]
        if e.get("updated_at", "") >= cutoff
    ]
    return feed


def export_feed(output_path: str = "news-feed.json", edition_label: str = "Web") -> None:
    load_dotenv()
    cfg = load_config()
    configure_logging(cfg.log_level)

    sources = load_sources(cfg.sources_file)
    raw_items = fetch_sources(sources)
    recent_items = filter_recent(raw_items, cfg.lookback_hours)
    deduped = dedupe_items(recent_items)

    # Use state to avoid duplicates across runs
    state = load_state(cfg.state_file)
    fresh, state = filter_sent(deduped, state, cfg.state_ttl_hours)

    if len(fresh) < cfg.min_items and cfg.fallback_lookback_hours > cfg.lookback_hours:
        recent_items = filter_recent(raw_items, cfg.fallback_lookback_hours)
        deduped = dedupe_items(recent_items)
        fresh, state = filter_sent(deduped, state, cfg.state_ttl_hours)

    ranked = rank_items(fresh, cfg.max_items, edition_label)

    if not ranked:
        logger.warning("No items to export for this edition")
        return

    # Enrich with translations
    reset_translation_stats()
    translator = build_translator(
        TranslatorConfig(
            provider=cfg.translate_provider,
            endpoint=cfg.translate_endpoint,
            api_key=cfg.translate_api_key,
            sleep_seconds=cfg.translate_sleep_seconds,
            max_retries=cfg.translate_max_retries,
            backoff_base_seconds=cfg.translate_backoff_base_seconds,
            backoff_max_seconds=cfg.translate_backoff_max_seconds,
            cache_max_entries=cfg.translate_cache_max_entries,
        )
    )
    add_bilingual_fields(ranked, translator)

    # Optional: Chinese summary
    summary_cn = None
    if cfg.openai_summary and cfg.openai_api_key:
        summary_cn = summarize_cn(
            ranked[: min(12, len(ranked))],
            edition_label,
            OpenAISummaryConfig(
                api_key=cfg.openai_api_key,
                model=cfg.openai_model,
                base_url=cfg.openai_base_url,
            ),
        )

    # Optional: Market snapshot
    market_snapshot = []
    if cfg.market_snapshot:
        market_snapshot = build_market_snapshot(
            cfg.alpha_vantage_api_key or "", cfg.alpha_vantage_sleep_seconds
        )

    # Optional: Sector rankings
    sector_rankings = []
    if cfg.sector_ranking:
        sector_rankings = build_sector_rankings(
            top_n=cfg.sector_top_n,
            sleep_seconds=cfg.alpha_vantage_sleep_seconds,
        )

    # Optional: Sector recommendations
    sector_recommendation = None
    if cfg.sector_advisor and cfg.openai_api_key:
        sector_recommendation = generate_recommendations(
            sector_rankings=sector_rankings,
            news_items=ranked[:15],
            edition_label=edition_label,
            cfg=AdvisorConfig(
                api_key=cfg.openai_api_key,
                model=cfg.openai_model,
                base_url=cfg.openai_base_url,
            ),
        )

    # Optional: Social media extraction
    social_groups = []
    if cfg.social_media_section:
        social_groups = extract_social_media(ranked)

    # Optional: Social media summary
    social_summary_cn = None
    if cfg.social_media_summary and cfg.openai_api_key and social_groups:
        social_summary_cn = summarize_social_cn(
            social_groups,
            SocialSummaryConfig(
                api_key=cfg.openai_api_key,
                model=cfg.openai_model,
                base_url=cfg.openai_base_url,
            ),
        )

    # Optional: Market hotspots
    market_hotspots_cn = None
    if cfg.market_hotspots and cfg.openai_api_key:
        market_hotspots_cn = generate_market_hotspots(
            news_items=ranked[:25],
            edition_label=edition_label,
            cfg=HotspotsConfig(
                api_key=cfg.openai_api_key,
                model=cfg.openai_model,
                base_url=cfg.openai_base_url,
            ),
        )

    # Build this edition
    now = datetime.now(timezone.utc)
    edition = {
        "updated_at": now.isoformat(),
        "edition_label": edition_label,
        "summary_cn": summary_cn,
        "market_hotspots_cn": market_hotspots_cn,
        "social_summary_cn": social_summary_cn,
        "sector_recommendation": sector_recommendation,
        "market_snapshot": [
            {
                "title": section.title,
                "items": [
                    {
                        "name": item.name,
                        "symbol": item.symbol,
                        "price": item.price,
                        "change": item.change,
                        "change_percent": item.change_percent,
                        "currency": item.currency,
                        "change_color": item.change_color,
                    }
                    for item in section.items
                ],
            }
            for section in market_snapshot
        ],
        "sector_rankings": [
            {
                "title": ranking.title,
                "items": [
                    {
                        "name": item.name,
                        "change_percent": item.change_percent,
                        "change_color": item.change_color,
                    }
                    for item in ranking.items
                ],
            }
            for ranking in sector_rankings
        ],
        "items": [
            {
                "title": item.title,
                "title_en": item.title_en,
                "title_zh": item.title_zh,
                "link": item.link,
                "published": item.published.isoformat() if item.published else None,
                "summary_en": item.summary_en,
                "summary_zh": item.summary_zh,
                "source": item.source,
                "language": item.language,
                "priority": item.priority,
                "source_category": item.source_category,
            }
            for item in ranked
        ],
        "social_media": [
            {
                "platform": group.platform,
                "platform_key": group.platform_key,
                "items": [
                    {
                        "title": item.title,
                        "title_en": item.title_en,
                        "title_zh": item.title_zh,
                        "link": item.link,
                        "source": item.source,
                    }
                    for item in group.items[:5]
                ],
            }
            for group in social_groups
        ],
    }

    # Load existing feed, append new edition, prune old ones
    feed = _load_existing_feed(output_path)
    feed["editions"].append(edition)
    feed = _prune_old_editions(feed, KEEP_DAYS)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(
        json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    save_state(cfg.state_file, state)
    logger.info(
        "Exported %d items as edition '%s'. Total editions: %d",
        len(ranked), edition_label, len(feed["editions"]),
    )

    # Generate RSS feed alongside JSON
    rss_path = str(Path(output_path).with_suffix(".xml"))
    _generate_rss(feed, rss_path)


def _generate_rss(feed: dict, rss_path: str) -> None:
    """Generate RSS XML from the editions feed."""
    from xml.etree.ElementTree import Element, SubElement, tostring

    rss = Element("rss", version="2.0")
    rss.set("xmlns:atom", "http://www.w3.org/2005/Atom")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = "WonderLand Finance News"
    SubElement(channel, "link").text = "https://www.cmwonderland.com/news/"
    SubElement(channel, "description").text = (
        "Global financial headlines, updated twice daily."
    )
    SubElement(channel, "language").text = "en-us"

    # Self-referencing atom link for RSS readers
    atom_link = SubElement(channel, "{http://www.w3.org/2005/Atom}link")
    atom_link.set("href", "https://raw.githubusercontent.com/james20141606/ai_finance_news/main/news-feed.xml")
    atom_link.set("rel", "self")
    atom_link.set("type", "application/rss+xml")

    editions = feed.get("editions", [])
    # Sort newest first, take recent editions
    editions_sorted = sorted(
        editions, key=lambda e: e.get("updated_at", ""), reverse=True
    )

    for edition in editions_sorted[:10]:
        updated_at = edition.get("updated_at", "")
        label = edition.get("edition_label", "Edition")

        # Add summary as an item if present
        if edition.get("summary_cn"):
            item_el = SubElement(channel, "item")
            SubElement(item_el, "title").text = f"[{label}] Daily Outlook"
            SubElement(item_el, "description").text = edition["summary_cn"]
            SubElement(item_el, "pubDate").text = updated_at
            SubElement(item_el, "guid", isPermaLink="false").text = (
                f"outlook-{updated_at}"
            )

        # Add news items
        for news in edition.get("items", []):
            item_el = SubElement(channel, "item")
            title = news.get("title_en") or news.get("title", "")
            title_zh = news.get("title_zh", "")
            if title_zh:
                title = f"{title} | {title_zh}"
            SubElement(item_el, "title").text = title

            desc_parts = []
            if news.get("summary_en"):
                desc_parts.append(news["summary_en"])
            if news.get("summary_zh"):
                desc_parts.append(news["summary_zh"])
            SubElement(item_el, "description").text = "\n\n".join(desc_parts)

            if news.get("link"):
                SubElement(item_el, "link").text = news["link"]
            if news.get("published"):
                SubElement(item_el, "pubDate").text = news["published"]
            SubElement(item_el, "guid", isPermaLink="false").text = (
                news.get("link", "") or f"news-{updated_at}-{title[:50]}"
            )
            if news.get("source"):
                SubElement(item_el, "source", url="").text = news["source"]

    xml_str = tostring(rss, encoding="unicode", xml_declaration=False)
    xml_out = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str
    Path(rss_path).write_text(xml_out, encoding="utf-8")
    logger.info("Generated RSS feed: %s", rss_path)


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "news-feed.json"
    export_feed(output)
