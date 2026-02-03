import logging
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass
class TranslatorConfig:
    provider: str
    endpoint: str
    api_key: str
    sleep_seconds: float


class BaseTranslator:
    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        raise NotImplementedError


class NullTranslator(BaseTranslator):
    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        return text


class LibreTranslateTranslator(BaseTranslator):
    def __init__(self, endpoint: str, api_key: str, sleep_seconds: float):
        self.endpoint = endpoint
        self.api_key = api_key
        self.sleep_seconds = sleep_seconds

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if not self.endpoint:
            return text
        payload = {
            "q": text,
            "source": source_lang,
            "target": target_lang,
            "format": "text",
        }
        if self.api_key:
            payload["api_key"] = self.api_key
        resp = requests.post(self.endpoint, json=payload, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        time.sleep(self.sleep_seconds)
        return data.get("translatedText", text)


class MyMemoryTranslator(BaseTranslator):
    def __init__(self, sleep_seconds: float):
        self.sleep_seconds = sleep_seconds

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        params = {
            "q": text,
            "langpair": f"{source_lang}|{target_lang}",
        }
        resp = requests.get(
            "https://api.mymemory.translated.net/get", params=params, timeout=20
        )
        resp.raise_for_status()
        data = resp.json()
        time.sleep(self.sleep_seconds)
        return data.get("responseData", {}).get("translatedText", text)


def build_translator(cfg: TranslatorConfig) -> BaseTranslator:
    provider = (cfg.provider or "").lower().strip()
    if provider == "libretranslate":
        return LibreTranslateTranslator(cfg.endpoint, cfg.api_key, cfg.sleep_seconds)
    if provider == "mymemory":
        return MyMemoryTranslator(cfg.sleep_seconds)
    if provider == "none":
        return NullTranslator()
    logger.warning("Unknown TRANSLATE_PROVIDER '%s', using no-op translator", cfg.provider)
    return NullTranslator()
