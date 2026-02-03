import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def load_state(path: str) -> dict:
    state_path = Path(path)
    if not state_path.exists():
        return {"sent": {}}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"sent": {}}


def save_state(path: str, state: dict) -> None:
    Path(path).write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")


def filter_sent(items, state: dict, ttl_hours: int):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=ttl_hours)
    sent = state.get("sent", {})

    # Prune old entries
    sent = {
        link: ts for link, ts in sent.items() if datetime.fromisoformat(ts) >= cutoff
    }

    remaining = []
    for item in items:
        if item.link in sent:
            continue
        remaining.append(item)
        sent[item.link] = now.isoformat()

    state["sent"] = sent
    return remaining, state
