import os
from pathlib import Path

from dotenv import load_dotenv

from fin_news_digest.config import load_config
from fin_news_digest.market_data import build_market_snapshot
from fin_news_digest.news_summary import OpenAISummaryConfig, summarize_cn
from fin_news_digest.sector_data import build_sector_rankings
from fin_news_digest.sector_advisor import AdvisorConfig, generate_recommendations
from fin_news_digest.social_media import extract_social_media
from fin_news_digest.social_summary import SocialSummaryConfig, summarize_social_cn
from fin_news_digest.market_hotspots import HotspotsConfig, generate_market_hotspots
from fin_news_digest.source_loader import load_sources
from fin_news_digest.fetcher import fetch_sources
from fin_news_digest.dedupe import dedupe_items, filter_recent, rank_items
from fin_news_digest.emailer import build_message
from fin_news_digest.utils import configure_logging


def main() -> None:
    load_dotenv()
    cfg = load_config()
    configure_logging(cfg.log_level)

    sources = load_sources(cfg.sources_file)
    items = fetch_sources(sources)
    items = filter_recent(items, cfg.lookback_hours)
    items = dedupe_items(items)
    items = rank_items(items, cfg.max_items, "Preview")

    summary = None
    if cfg.openai_summary and cfg.openai_api_key:
        summary = summarize_cn(
            items[: min(12, len(items))],
            "Preview",
            OpenAISummaryConfig(
                api_key=cfg.openai_api_key,
                model=cfg.openai_model,
                base_url=cfg.openai_base_url,
            ),
        )

    snapshot = []
    if cfg.market_snapshot and cfg.alpha_vantage_api_key:
        snapshot = build_market_snapshot(
            cfg.alpha_vantage_api_key, cfg.alpha_vantage_sleep_seconds
        )

    sector_rankings = []
    if cfg.sector_ranking:
        sector_rankings, _weekly = build_sector_rankings(
            top_n=cfg.sector_top_n,
            sleep_seconds=cfg.alpha_vantage_sleep_seconds,
        )

    sector_recommendation = None
    if cfg.sector_advisor and cfg.openai_api_key:
        sector_recommendation = generate_recommendations(
            sector_rankings=sector_rankings,
            news_items=items[:15],
            edition_label="Preview",
            cfg=AdvisorConfig(
                api_key=cfg.openai_api_key,
                model=cfg.openai_model,
                base_url=cfg.openai_base_url,
            ),
        )

    social_groups = []
    if cfg.social_media_section:
        social_groups = extract_social_media(items)

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

    market_hotspots_cn = None
    if cfg.market_hotspots and cfg.openai_api_key:
        market_hotspots_cn = generate_market_hotspots(
            news_items=items[:25],
            edition_label="Preview",
            cfg=HotspotsConfig(
                api_key=cfg.openai_api_key,
                model=cfg.openai_model,
                base_url=cfg.openai_base_url,
            ),
        )

    msg = build_message(
        subject="Preview",
        sender=cfg.smtp_from or cfg.smtp_user or "preview@example.com",
        recipients=["preview@example.com"],
        items=items,
        edition_label="Preview",
        summary_cn=summary,
        market_snapshot=snapshot,
        sector_rankings=sector_rankings,
        sector_recommendation=sector_recommendation,
        social_groups=social_groups or None,
        social_summary_cn=social_summary_cn,
        market_hotspots_cn=market_hotspots_cn,
    )

    html = msg.get_body(preferencelist=("html",)).get_content()
    out = Path("/tmp/finance_digest_preview.html")
    out.write_text(html, encoding="utf-8")
    print(f"Preview saved to {out}")


if __name__ == "__main__":
    main()
