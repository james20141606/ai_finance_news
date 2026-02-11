import json
import logging
from dataclasses import dataclass
from typing import Any

import requests

from fin_news_digest.social_media import SocialMediaGroup

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SocialSummaryConfig:
    api_key: str
    model: str
    base_url: str


def _build_prompt(groups: list[SocialMediaGroup]) -> str:
    lines = [
        "请根据以下社交媒体帖子/讨论，撰写一段中文社媒热议总结（150-250字）。",
        "要求：",
        "- 按平台分段概括（Twitter / 雪球 / Reddit）",
        "- 关注KOL观点共识与分歧",
        "- 提及热门话题和情绪倾向",
        "- 语气客观简洁",
        "",
    ]
    for group in groups:
        lines.append(f"== {group.platform} ==")
        for item in group.items[:10]:
            lines.append(f"- [{item.source}] {item.title}")
            if item.summary and item.summary != item.title:
                lines.append(f"  {item.summary[:120]}")
        lines.append("")
    return "\n".join(lines)


def _response_json() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "social_summary",
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


def summarize_social_cn(
    groups: list[SocialMediaGroup],
    cfg: SocialSummaryConfig,
) -> str | None:
    if not groups or not cfg.api_key:
        return None

    total_items = sum(len(g.items) for g in groups)
    if total_items == 0:
        return None

    prompt = _build_prompt(groups)
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
        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        result = json.loads(content)
        summary = result.get("summary")
        if summary:
            return summary.strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Social media summary LLM failed: %s", exc)
    return None
