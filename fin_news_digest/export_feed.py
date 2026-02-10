"""
Export the latest finance digest as a JSON feed file.

Usage:
    python -m fin_news_digest.export_feed [--output path/to/news-feed.json]

This generates a JSON file suitable for rendering in a web page.
It fetches, deduplicates, and ranks items the same way the email digest does,
but outputs JSON instead of sending an email.
"""

import json
import logging
import sys
from datetime import datetime, timezone
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
from fin_news_digest.source_loader import load_sources
from fin_news_digest.state import filter_sent, load_state, save_state
from fin_news_digest.translator import (
    TranslatorConfig,
    build_translator,
    reset_translation_stats,
)
from fin_news_digest.utils import configure_logging

logger = logging.getLogger(__name__)


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
        logger.warning("No items to export")
        # Write empty feed
        feed = {"updated_at": datetime.now(timezone.utc).isoformat(), "items": []}
        Path(output_path).write_text(json.dumps(feed, ensure_ascii=False, indent=2))
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

    # Build JSON feed
    now = datetime.now(timezone.utc)
    feed = {
        "updated_at": now.isoformat(),
        "edition_label": edition_label,
        "summary_cn": summary_cn,
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
            }
            for item in ranked
        ],
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8")
    save_state(cfg.state_file, state)
    logger.info("Exported %d items to %s", len(ranked), output_path)


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "news-feed.json"
    export_feed(output)
