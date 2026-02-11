import logging
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from fin_news_digest.config import load_config
from fin_news_digest.dedupe import dedupe_items, filter_recent, rank_items
from fin_news_digest.emailer import build_message, send_email, send_email_to_each
from fin_news_digest.enrich import add_bilingual_fields
from fin_news_digest.fetcher import fetch_sources
from fin_news_digest.source_loader import load_sources
from fin_news_digest.state import filter_sent, load_state, save_state
from fin_news_digest.translator import (
    TranslatorConfig,
    build_translator,
    get_translation_stats,
    reset_translation_stats,
)
from fin_news_digest.utils import configure_logging
from fin_news_digest.llm_ranker import OpenAIRerankConfig, rerank_items
from fin_news_digest.market_data import build_market_snapshot
from fin_news_digest.news_summary import OpenAISummaryConfig, summarize_cn
from fin_news_digest.sector_data import build_sector_rankings
from fin_news_digest.sector_advisor import AdvisorConfig, generate_recommendations
from fin_news_digest.social_media import SocialMediaGroup, extract_social_media
from fin_news_digest.social_summary import SocialSummaryConfig, summarize_social_cn
from fin_news_digest.market_hotspots import HotspotsConfig, generate_market_hotspots

logger = logging.getLogger(__name__)


def _subject_for(edition_label: str) -> str:
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    return f"Global Finance Digest [{edition_label}] {date_str}"


def run_digest(edition_label: str) -> None:
    load_dotenv()
    cfg = load_config()
    configure_logging(cfg.log_level)

    if not cfg.recipients:
        raise RuntimeError("RECIPIENTS is empty")
    if not cfg.smtp_host:
        raise RuntimeError("SMTP_HOST is empty")

    sources = load_sources(cfg.sources_file)
    raw_items = fetch_sources(sources)
    recent_items = filter_recent(raw_items, cfg.lookback_hours)
    deduped = dedupe_items(recent_items)

    state = load_state(cfg.state_file)
    fresh, state = filter_sent(deduped, state, cfg.state_ttl_hours)

    if len(fresh) < cfg.min_items and cfg.fallback_lookback_hours > cfg.lookback_hours:
        logger.info(
            "Only %s items; expanding lookback to %sh",
            len(fresh),
            cfg.fallback_lookback_hours,
        )
        recent_items = filter_recent(raw_items, cfg.fallback_lookback_hours)
        deduped = dedupe_items(recent_items)
        fresh, state = filter_sent(deduped, state, cfg.state_ttl_hours)

    if len(fresh) < cfg.min_items:
        logger.warning(
            "Only %s items after fallback (min=%s). Skipping send.",
            len(fresh),
            cfg.min_items,
        )
        return

    heuristic_ranked = rank_items(fresh, cfg.max_items, edition_label)

    ranked = heuristic_ranked
    if cfg.openai_rerank and cfg.openai_api_key:
        candidates = rank_items(fresh, cfg.openai_candidates, edition_label)
        reranked = rerank_items(
            candidates,
            edition_label,
            OpenAIRerankConfig(
                api_key=cfg.openai_api_key,
                model=cfg.openai_model,
                base_url=cfg.openai_base_url,
                candidates=cfg.openai_candidates,
            ),
        )
        if reranked:
            ranked = reranked[: cfg.max_items]
    if not ranked:
        logger.warning("No items to send for %s", edition_label)
        return

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
    stats = get_translation_stats()
    if stats.translate_calls:
        cache_hit_rate = stats.cache_hits / stats.translate_calls * 100
        logger.info(
            "Translation stats for %s: calls=%s, cache_hits=%s (%.1f%%), fallbacks=%s, api_requests=%s",
            edition_label,
            stats.translate_calls,
            stats.cache_hits,
            cache_hit_rate,
            stats.fallbacks,
            stats.api_requests,
        )
    else:
        logger.info("Translation stats for %s: no translation calls", edition_label)

    # Extract social media groups
    social_groups: list[SocialMediaGroup] = []
    if cfg.social_media_section:
        social_groups = extract_social_media(ranked)

    # Generate social media summary
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

    sender = cfg.smtp_from or cfg.smtp_user
    if not sender:
        raise RuntimeError("SMTP_FROM or SMTP_USER must be set")

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

    market_snapshot = []
    if cfg.market_snapshot:
        market_snapshot = build_market_snapshot(
            cfg.alpha_vantage_api_key or "", cfg.alpha_vantage_sleep_seconds
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
            news_items=ranked[:15],
            edition_label=edition_label,
            cfg=AdvisorConfig(
                api_key=cfg.openai_api_key,
                model=cfg.openai_model,
                base_url=cfg.openai_base_url,
            ),
        )

    # Generate market hotspots
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

    send_email_to_each(
        host=cfg.smtp_host,
        port=cfg.smtp_port,
        use_tls=cfg.smtp_use_tls,
        user=cfg.smtp_user,
        password=cfg.smtp_pass,
        subject=_subject_for(edition_label),
        sender=sender,
        recipients=cfg.recipients,
        items=ranked,
        edition_label=edition_label,
        summary_cn=summary_cn,
        market_snapshot=market_snapshot,
        sector_rankings=sector_rankings,
        sector_recommendation=sector_recommendation,
        social_groups=social_groups or None,
        social_summary_cn=social_summary_cn,
        market_hotspots_cn=market_hotspots_cn,
    )
    Path(cfg.state_file).parent.mkdir(parents=True, exist_ok=True)
    save_state(cfg.state_file, state)
