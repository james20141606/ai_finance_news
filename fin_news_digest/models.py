from dataclasses import dataclass
from datetime import datetime


@dataclass
class NewsItem:
    title: str
    link: str
    published: datetime
    summary: str
    source: str
    language: str
    priority: int

    title_en: str | None = None
    title_zh: str | None = None
    summary_en: str | None = None
    summary_zh: str | None = None
