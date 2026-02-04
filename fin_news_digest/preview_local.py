import os
from pathlib import Path

from dotenv import load_dotenv

from fin_news_digest.config import load_config
from fin_news_digest.market_data import build_market_snapshot
from fin_news_digest.news_summary import OpenAISummaryConfig, summarize_cn
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

    msg = build_message(
        subject="Preview",
        sender=cfg.smtp_from or cfg.smtp_user or "preview@example.com",
        recipients=["preview@example.com"],
        items=items,
        edition_label="Preview",
        summary_cn=summary,
        market_snapshot=snapshot,
    )

    html = msg.get_body(preferencelist=("html",)).get_content()
    out = Path("/tmp/finance_digest_preview.html")
    out.write_text(html, encoding="utf-8")
    print(f"Preview saved to {out}")


if __name__ == "__main__":
    main()
