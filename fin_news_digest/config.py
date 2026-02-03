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


def _env(primary: str, fallback: str) -> str:
    value = os.getenv(primary, "")
    if value:
        return value
    return os.getenv(fallback, "")


def load_config() -> Config:
    recipients_raw = _env("RECIPIENTS", "FIN_RECIPIENTS")
    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]

    return Config(
        recipients=recipients,
        smtp_host=_env("SMTP_HOST", "FIN_SMTP_HOST"),
        smtp_port=_get_int(_env("SMTP_PORT", "FIN_SMTP_PORT"), 587),
        smtp_user=_env("SMTP_USER", "FIN_SMTP_USER"),
        smtp_pass=_env("SMTP_PASS", "FIN_SMTP_PASS"),
        smtp_from=_env("SMTP_FROM", "FIN_SMTP_FROM"),
        smtp_use_tls=_get_bool(_env("SMTP_USE_TLS", "FIN_SMTP_USE_TLS"), True),
        translate_provider=_env("TRANSLATE_PROVIDER", "FIN_TRANSLATE_PROVIDER") or "mymemory",
        translate_endpoint=_env("TRANSLATE_ENDPOINT", "FIN_TRANSLATE_ENDPOINT"),
        translate_api_key=_env("TRANSLATE_API_KEY", "FIN_TRANSLATE_API_KEY"),
        translate_sleep_seconds=_get_float(os.getenv("TRANSLATE_SLEEP_SECONDS"), 1.0),
        lookback_hours=_get_int(os.getenv("LOOKBACK_HOURS"), 36),
        state_ttl_hours=_get_int(os.getenv("STATE_TTL_HOURS"), 72),
        max_items=_get_int(os.getenv("MAX_ITEMS"), 40),
        sources_file=os.getenv("SOURCES_FILE", "fin_news_digest/sources.json"),
        state_file=os.getenv("STATE_FILE", "fin_news_digest/state.json"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
