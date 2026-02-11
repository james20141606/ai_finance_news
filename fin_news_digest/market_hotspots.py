import json
import logging
from dataclasses import dataclass
from typing import Any

import requests

from fin_news_digest.models import NewsItem

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HotspotsConfig:
    api_key: str
    model: str
    base_url: str


def _build_prompt(news_items: list[NewsItem], edition_label: str) -> str:
    lines = [
        "你是一位资深全球金融分析师。根据以下今日重要新闻，生成每日市场热点速览。",
        "",
        "要求：",
        "- 分为【中国市场】【美国市场】【全球市场】三个板块",
        "- 每个板块列出 2-4 个热点，用 • 开头",
        "- 每个热点一句话概括核心事件或趋势",
        "- 中文输出，总共 300-500 字",
        "- 语气客观专业",
        "",
        f"== 当前版本: {edition_label} ==",
        "",
        "== 今日重要新闻 ==",
    ]
    for item in news_items[:25]:
        lines.append(f"- [{item.source}] {item.title}")
        if item.summary and item.summary != item.title:
            lines.append(f"  {item.summary[:120]}")
    lines.append("")
    lines.append("请综合以上信息，输出每日市场热点速览。")
    return "\n".join(lines)


def _response_json() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "market_hotspots",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "hotspots": {"type": "string"},
                },
                "required": ["hotspots"],
                "additionalProperties": False,
            },
        },
    }


def generate_market_hotspots(
    news_items: list[NewsItem],
    edition_label: str,
    cfg: HotspotsConfig,
) -> str | None:
    if not cfg.api_key:
        return None
    if not news_items:
        return None

    prompt = _build_prompt(news_items, edition_label)
    payload = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": "You output JSON only."},
            {"role": "user", "content": prompt},
        ],
        "response_format": _response_json(),
    }

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
        result = json.loads(content)
        hotspots = result.get("hotspots")
        if hotspots:
            return hotspots.strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Market hotspots LLM failed: %s", exc)
    return None
