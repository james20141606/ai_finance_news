import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable

import requests

logger = logging.getLogger(__name__)


@dataclass
class TranslatorConfig:
    provider: str
    endpoint: str
    api_key: str
    sleep_seconds: float
    max_retries: int
    backoff_base_seconds: float
    backoff_max_seconds: float
    cache_max_entries: int


_MISSING = object()


class TranslationCache:
    def __init__(self, max_entries: int) -> None:
        self.max_entries = max_entries
        self._data: OrderedDict[tuple[str, str, str, str, str], str] = OrderedDict()

    def resize(self, max_entries: int) -> None:
        self.max_entries = max_entries
        while len(self._data) > self.max_entries:
            self._data.popitem(last=False)

    def get(self, key: tuple[str, str, str, str, str]) -> str | object:
        if key not in self._data:
            return _MISSING
        self._data.move_to_end(key)
        return self._data[key]

    def set(self, key: tuple[str, str, str, str, str], value: str) -> None:
        if self.max_entries <= 0:
            return
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = value
        if len(self._data) > self.max_entries:
            self._data.popitem(last=False)


_TRANSLATION_CACHE = TranslationCache(2048)


def _cache_key(
    provider: str, endpoint: str, source_lang: str, target_lang: str, text: str
) -> tuple[str, str, str, str, str]:
    return provider, endpoint, source_lang, target_lang, text


def _should_retry_status(status_code: int) -> bool:
    return status_code in {408, 429} or 500 <= status_code < 600


def _retry_delay(attempt: int, base: float, max_seconds: float) -> float:
    return min(max_seconds, base * (2**attempt))


def _retry_after_seconds(resp: requests.Response) -> float | None:
    retry_after = resp.headers.get("Retry-After", "").strip()
    if retry_after.isdigit():
        return float(retry_after)
    return None


def _request_with_retries(
    request_fn: Callable[[], requests.Response],
    provider_label: str,
    max_retries: int,
    backoff_base_seconds: float,
    backoff_max_seconds: float,
) -> requests.Response | None:
    attempt = 0
    while True:
        try:
            resp = request_fn()
        except requests.RequestException as exc:
            if attempt >= max_retries:
                logger.warning(
                    "Translation request failed for %s after %s attempts: %s",
                    provider_label,
                    attempt + 1,
                    exc,
                )
                return None
            delay = _retry_delay(attempt, backoff_base_seconds, backoff_max_seconds)
            logger.warning(
                "Translation request error for %s (attempt %s/%s): %s. Retrying in %.1fs",
                provider_label,
                attempt + 1,
                max_retries + 1,
                exc,
                delay,
            )
            time.sleep(delay)
            attempt += 1
            continue

        if _should_retry_status(resp.status_code):
            if attempt >= max_retries:
                logger.warning(
                    "Translation request for %s failed with status %s after %s attempts",
                    provider_label,
                    resp.status_code,
                    attempt + 1,
                )
                return None
            delay = _retry_after_seconds(resp) or _retry_delay(
                attempt, backoff_base_seconds, backoff_max_seconds
            )
            delay = min(backoff_max_seconds, max(delay, backoff_base_seconds))
            logger.warning(
                "Translation request for %s returned %s (attempt %s/%s). Retrying in %.1fs",
                provider_label,
                resp.status_code,
                attempt + 1,
                max_retries + 1,
                delay,
            )
            time.sleep(delay)
            attempt += 1
            continue

        if not resp.ok:
            logger.warning(
                "Translation request for %s failed with status %s. Returning original text.",
                provider_label,
                resp.status_code,
            )
            return None
        return resp


class BaseTranslator:
    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        raise NotImplementedError


class NullTranslator(BaseTranslator):
    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        return text


class LibreTranslateTranslator(BaseTranslator):
    def __init__(
        self,
        endpoint: str,
        api_key: str,
        sleep_seconds: float,
        max_retries: int,
        backoff_base_seconds: float,
        backoff_max_seconds: float,
    ):
        self.endpoint = endpoint
        self.api_key = api_key
        self.sleep_seconds = sleep_seconds
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.backoff_max_seconds = backoff_max_seconds
        self.provider_label = "libretranslate"

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if not self.endpoint:
            return text
        if not text:
            return text
        cache_key = _cache_key(
            self.provider_label, self.endpoint, source_lang, target_lang, text
        )
        cached = _TRANSLATION_CACHE.get(cache_key)
        if cached is not _MISSING:
            return cached
        payload = {
            "q": text,
            "source": source_lang,
            "target": target_lang,
            "format": "text",
        }
        if self.api_key:
            payload["api_key"] = self.api_key

        def _request() -> requests.Response:
            return requests.post(self.endpoint, json=payload, timeout=20)

        resp = _request_with_retries(
            _request,
            self.provider_label,
            self.max_retries,
            self.backoff_base_seconds,
            self.backoff_max_seconds,
        )
        if resp is None:
            result = text
        else:
            try:
                data = resp.json()
            except ValueError:
                logger.warning(
                    "Translation response from %s was not valid JSON. Returning original text.",
                    self.provider_label,
                )
                result = text
            else:
                result = data.get("translatedText", text) or text
            time.sleep(self.sleep_seconds)
        _TRANSLATION_CACHE.set(cache_key, result)
        return result


class MyMemoryTranslator(BaseTranslator):
    def __init__(
        self,
        sleep_seconds: float,
        max_retries: int,
        backoff_base_seconds: float,
        backoff_max_seconds: float,
    ):
        self.sleep_seconds = sleep_seconds
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.backoff_max_seconds = backoff_max_seconds
        self.provider_label = "mymemory"

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if not text:
            return text
        cache_key = _cache_key(
            self.provider_label,
            "https://api.mymemory.translated.net/get",
            source_lang,
            target_lang,
            text,
        )
        cached = _TRANSLATION_CACHE.get(cache_key)
        if cached is not _MISSING:
            return cached
        params = {
            "q": text,
            "langpair": f"{source_lang}|{target_lang}",
        }

        def _request() -> requests.Response:
            return requests.get(
                "https://api.mymemory.translated.net/get", params=params, timeout=20
            )

        resp = _request_with_retries(
            _request,
            self.provider_label,
            self.max_retries,
            self.backoff_base_seconds,
            self.backoff_max_seconds,
        )
        if resp is None:
            result = text
        else:
            try:
                data = resp.json()
            except ValueError:
                logger.warning(
                    "Translation response from %s was not valid JSON. Returning original text.",
                    self.provider_label,
                )
                result = text
            else:
                result = data.get("responseData", {}).get("translatedText", text) or text
            time.sleep(self.sleep_seconds)
        _TRANSLATION_CACHE.set(cache_key, result)
        return result


def build_translator(cfg: TranslatorConfig) -> BaseTranslator:
    _TRANSLATION_CACHE.resize(cfg.cache_max_entries)
    provider = (cfg.provider or "").lower().strip()
    if provider == "libretranslate":
        return LibreTranslateTranslator(
            cfg.endpoint,
            cfg.api_key,
            cfg.sleep_seconds,
            cfg.max_retries,
            cfg.backoff_base_seconds,
            cfg.backoff_max_seconds,
        )
    if provider == "mymemory":
        return MyMemoryTranslator(
            cfg.sleep_seconds,
            cfg.max_retries,
            cfg.backoff_base_seconds,
            cfg.backoff_max_seconds,
        )
    if provider == "none":
        return NullTranslator()
    logger.warning("Unknown TRANSLATE_PROVIDER '%s', using no-op translator", cfg.provider)
    return NullTranslator()
