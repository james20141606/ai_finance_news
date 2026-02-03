import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Source:
    source_id: str
    name: str
    url: str
    language: str
    priority: int


def load_sources(path: str) -> list[Source]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    sources: list[Source] = []
    for item in data:
        sources.append(
            Source(
                source_id=item["id"],
                name=item["name"],
                url=item["url"],
                language=item.get("lang", "en"),
                priority=int(item.get("priority", 1)),
            )
        )
    return sources
