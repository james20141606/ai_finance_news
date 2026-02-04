import json
import logging
from dataclasses import dataclass
from typing import Any

import requests

from fin_news_digest.models import NewsItem

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OpenAIRerankConfig:
    api_key: str
    model: str
    base_url: str
    candidates: int


def _build_prompt(items: list[NewsItem], edition_label: str) -> str:
    lines = [
        "You are a financial news editor. Rank items by importance and market impact.",
        "Edition focus:",
        f"- {edition_label}",
        "Rules:",
        "- Prefer major policy decisions, macro releases, central bank actions, market-moving company news.",
        "- Prefer high-impact, timely, and reputable sources.",
        "- Avoid duplicated or low-signal items.",
        "- Output JSON only.",
        "Items:",
    ]
    for idx, item in enumerate(items, start=1):
        lines.append(
            f"[{idx}] {item.title} | {item.source} | {item.summary}"
        )
    lines.append(
        "Return JSON with: order (array of item ids) and scores (map id->0-100)."
    )
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
                    "order": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                    "scores": {
                        "type": "object",
                        "additionalProperties": {"type": "number"},
                    },
                },
                "required": ["order", "scores"],
                "additionalProperties": False,
            },
        },
    }


def rerank_items(
    items: list[NewsItem],
    edition_label: str,
    cfg: OpenAIRerankConfig,
) -> list[NewsItem] | None:
    if not items:
        return []
    if not cfg.api_key:
        return None

    candidates = items[: cfg.candidates]
    prompt = _build_prompt(candidates, edition_label)

    payload = {
        "model": cfg.model,
        "messages": [
            {
                "role": "system",
                "content": "You are a strict JSON-only ranking engine.",
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": _response_json("news_ranker"),
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
        order = result.get("order", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM rerank failed, fallback to heuristic: %s", exc)
        return None

    if not order:
        return None

    id_to_item = {idx: item for idx, item in enumerate(candidates, start=1)}
    ranked: list[NewsItem] = []
    for idx in order:
        item = id_to_item.get(idx)
        if item is not None:
            ranked.append(item)

    # Append any missing items in original order
    for item in candidates:
        if item not in ranked:
            ranked.append(item)

    return ranked
