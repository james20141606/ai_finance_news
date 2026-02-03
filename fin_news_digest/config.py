import os
from dataclasses import dataclass


def _get_bool(value: str, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_int(value: str, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_float(value: str, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    recipients: list[str]
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_pass: str
    smtp_from: str
    smtp_use_tls: bool

    translate_provider: str
    translate_endpoint: str
    translate_api_key: str
    translate_sleep_seconds: float

    lookback_hours: int
    state_ttl_hours: int
    max_items: int
    sources_file: str
    state_file: str
    log_level: str


def load_config() -> Config:
    recipients_raw = os.getenv("RECIPIENTS", "")
    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]

    return Config(
        recipients=recipients,
        smtp_host=os.getenv("SMTP_HOST", ""),
        smtp_port=_get_int(os.getenv("SMTP_PORT"), 587),
        smtp_user=os.getenv("SMTP_USER", ""),
        smtp_pass=os.getenv("SMTP_PASS", ""),
        smtp_from=os.getenv("SMTP_FROM", ""),
        smtp_use_tls=_get_bool(os.getenv("SMTP_USE_TLS"), True),
        translate_provider=os.getenv("TRANSLATE_PROVIDER", "mymemory"),
        translate_endpoint=os.getenv("TRANSLATE_ENDPOINT", ""),
        translate_api_key=os.getenv("TRANSLATE_API_KEY", ""),
        translate_sleep_seconds=_get_float(os.getenv("TRANSLATE_SLEEP_SECONDS"), 1.0),
        lookback_hours=_get_int(os.getenv("LOOKBACK_HOURS"), 36),
        state_ttl_hours=_get_int(os.getenv("STATE_TTL_HOURS"), 72),
        max_items=_get_int(os.getenv("MAX_ITEMS"), 40),
        sources_file=os.getenv("SOURCES_FILE", "fin_news_digest/sources.json"),
        state_file=os.getenv("STATE_FILE", "fin_news_digest/state.json"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
