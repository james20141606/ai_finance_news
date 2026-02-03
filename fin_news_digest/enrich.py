import logging

from fin_news_digest.models import NewsItem
from fin_news_digest.translator import BaseTranslator
from fin_news_digest.utils import truncate

logger = logging.getLogger(__name__)


def _lang_pair(language: str) -> tuple[str, str]:
    if language.lower().startswith("zh"):
        return "zh-CN", "en"
    return "en", "zh-CN"


def add_bilingual_fields(items: list[NewsItem], translator: BaseTranslator) -> None:
    for item in items:
        source_lang, target_lang = _lang_pair(item.language)
        if source_lang == "en":
            item.title_en = item.title
            item.summary_en = item.summary
            item.title_zh = truncate(
                translator.translate(item.title, source_lang, target_lang), 200
            )
            item.summary_zh = truncate(
                translator.translate(item.summary, source_lang, target_lang), 360
            )
        else:
            item.title_zh = item.title
            item.summary_zh = item.summary
            item.title_en = truncate(
                translator.translate(item.title, source_lang, target_lang), 200
            )
            item.summary_en = truncate(
                translator.translate(item.summary, source_lang, target_lang), 360
            )
