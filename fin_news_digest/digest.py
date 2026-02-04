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
from fin_news_digest.translator import TranslatorConfig, build_translator
from fin_news_digest.utils import configure_logging
from fin_news_digest.llm_ranker import OpenAIRerankConfig, rerank_items

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

    translator = build_translator(
        TranslatorConfig(
            provider=cfg.translate_provider,
            endpoint=cfg.translate_endpoint,
            api_key=cfg.translate_api_key,
            sleep_seconds=cfg.translate_sleep_seconds,
        )
    )
    add_bilingual_fields(ranked, translator)

    sender = cfg.smtp_from or cfg.smtp_user
    if not sender:
        raise RuntimeError("SMTP_FROM or SMTP_USER must be set")

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
    )
    Path(cfg.state_file).parent.mkdir(parents=True, exist_ok=True)
    save_state(cfg.state_file, state)
