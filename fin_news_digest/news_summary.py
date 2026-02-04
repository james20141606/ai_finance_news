import json
import logging
from dataclasses import dataclass
from typing import Any

import requests

from fin_news_digest.models import NewsItem

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OpenAISummaryConfig:
    api_key: str
    model: str
    base_url: str


def build_summary_prompt(items: list[NewsItem], edition_label: str) -> str:
    lines = [
        "请根据以下金融新闻标题与摘要，写一段中文综合评价（120-180字）。",
        "要求：\n- 点出最重要的宏观/政策/市场驱动\n- 语气客观专业\n- 不要列点\n- 不要引号\n",
        f"Edition focus: {edition_label}",
        "新闻列表：",
    ]
    for item in items:
        lines.append(f"- {item.title} | {item.source} | {item.summary}")
    return "\n".join(lines)


def _response_json(schema_name: str) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name,
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                },
                "required": ["summary"],
                "additionalProperties": False,
            },
        },
    }


def summarize_cn(
    items: list[NewsItem],
    edition_label: str,
    cfg: OpenAISummaryConfig,
) -> str | None:
    if not items or not cfg.api_key:
        return None

    prompt = build_summary_prompt(items, edition_label)
    payload = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": "You output JSON only."},
            {"role": "user", "content": prompt},
        ],
        "response_format": _response_json("news_summary"),
    }

    url = f"{cfg.base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        result = json.loads(content)
        summary = result.get("summary")
        if summary:
            return summary.strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM summary failed: %s", exc)
    return None
