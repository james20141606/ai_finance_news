import json
import logging
from dataclasses import dataclass
from typing import Any

import requests

from fin_news_digest.models import NewsItem
from fin_news_digest.sector_data import SectorRanking

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdvisorConfig:
    api_key: str
    model: str
    base_url: str


def _build_prompt(
    sector_rankings: list[SectorRanking],
    news_items: list[NewsItem],
    edition_label: str,
) -> str:
    lines = [
        "你是一位资深金融分析师。根据以下板块涨跌数据、新闻和社交信号，"
        "为投资者撰写每日值得关注的板块和个股推荐。",
        "",
        "要求：",
        "- 分别列出美股和A股各 2-3 个值得关注的板块，说明驱动因素",
        "- 针对最强势的板块，提及 1-2 个代表性标的（ETF或龙头股）",
        "- 区分看多和看空信号",
        "- 简要点评当日市场风格（成长/价值、大盘/小盘等）",
        "- 中文输出，200-350字",
        "- 语气客观专业，不要用列点符号开头，用自然段落",
        "",
        f"== 当前版本: {edition_label} ==",
        "",
    ]

    if sector_rankings:
        lines.append("== 板块涨跌排名 ==")
        for ranking in sector_rankings:
            lines.append(f"\n[{ranking.title}]")
            for i, item in enumerate(ranking.items, 1):
                lines.append(f"  {i}. {item.name} {item.change_percent:+.2f}%")
        lines.append("")

    if news_items:
        lines.append("== 今日重要新闻 ==")
        for item in news_items[:15]:
            lines.append(f"- [{item.source}] {item.title}")
            if item.summary and item.summary != item.title:
                lines.append(f"  {item.summary[:120]}")
        lines.append("")

    lines.append(
        "请综合以上信息，输出每日板块与个股推荐。"
    )
    return "\n".join(lines)


def _response_json() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "sector_advisor",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "recommendation": {"type": "string"},
                },
                "required": ["recommendation"],
                "additionalProperties": False,
            },
        },
    }


def generate_recommendations(
    sector_rankings: list[SectorRanking],
    news_items: list[NewsItem],
    edition_label: str,
    cfg: AdvisorConfig,
) -> str | None:
    if not cfg.api_key:
        logger.info("Sector advisor skipped: no API key")
        return None
    if not sector_rankings and not news_items:
        logger.info("Sector advisor skipped: no sector data or news items")
        return None

    prompt = _build_prompt(sector_rankings, news_items, edition_label)
    logger.info(
        "Sector advisor: sending prompt (%d chars, %d sectors, %d news items)",
        len(prompt),
        sum(len(r.items) for r in sector_rankings),
        len(news_items),
    )

    # Try structured JSON output first, fall back to plain text
    for use_structured in (True, False):
        payload = {
            "model": cfg.model,
            "messages": [
                {"role": "system", "content": "You output JSON only."},
                {"role": "user", "content": prompt},
            ],
        }
        if use_structured:
            payload["response_format"] = _response_json()

        url = f"{cfg.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=90)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            # Try parsing as JSON
            try:
                result = json.loads(content)
                recommendation = result.get("recommendation", "")
            except json.JSONDecodeError:
                recommendation = content
            if recommendation and recommendation.strip():
                logger.info("Sector advisor: generated %d char recommendation", len(recommendation))
                return recommendation.strip()
        except Exception as exc:
            mode = "structured" if use_structured else "plain"
            logger.warning("Sector advisor LLM failed (%s mode): %s", mode, exc)
            if use_structured:
                logger.info("Sector advisor: retrying without structured output...")
                continue
            return None
    return None
