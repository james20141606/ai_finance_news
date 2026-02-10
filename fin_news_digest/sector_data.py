import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)


def _parse_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _change_color(value: float | None) -> str:
    if value is None:
        return "#64748b"
    if value > 0:
        return "#16a34a"
    if value < 0:
        return "#dc2626"
    return "#64748b"


@dataclass
class SectorItem:
    name: str
    code: str
    change_percent: float
    change_color: str

    def __post_init__(self) -> None:
        self.change_percent = round(self.change_percent, 2)


@dataclass
class SectorRanking:
    title: str
    items: list[SectorItem]


# ---------------------------------------------------------------------------
# A-share sectors via Eastmoney
# ---------------------------------------------------------------------------

def _fetch_eastmoney_sector_list(
    fs: str,
    top_n: int,
    descending: bool = True,
) -> list[SectorItem]:
    """Fetch A-share sector rankings from Eastmoney.

    Args:
        fs: filter string, e.g. "m:90+t:2" for industry, "m:90+t:3" for concept.
        top_n: number of top sectors to return.
        descending: True for top gainers, False for top losers.
    """
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1",
        "pz": str(top_n),
        "po": "1" if descending else "0",
        "np": "1",
        "fltt": "2",
        "invt": "2",
        "fs": fs,
        "fid": "f3",
        "fields": "f12,f14,f3",
    }
    headers = {"User-Agent": _UA}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning("Eastmoney sector fetch failed (%s): %s", fs, exc)
        return []

    diff = (payload.get("data") or {}).get("diff") or []
    items: list[SectorItem] = []
    for row in diff:
        name = str(row.get("f14", "")).strip()
        code = str(row.get("f12", "")).strip()
        change_pct = _parse_float(row.get("f3"))
        if not name or change_pct is None:
            continue
        items.append(
            SectorItem(
                name=name,
                code=code,
                change_percent=change_pct,
                change_color=_change_color(change_pct),
            )
        )
    return items


def fetch_cn_industry_sectors(top_n: int = 5) -> SectorRanking:
    items = _fetch_eastmoney_sector_list("m:90+t:2", top_n)
    return SectorRanking(title="A-Share Industry Sectors 行业板块", items=items)


def fetch_cn_concept_sectors(top_n: int = 5) -> SectorRanking:
    items = _fetch_eastmoney_sector_list("m:90+t:3", top_n)
    return SectorRanking(title="A-Share Concept Sectors 概念板块", items=items)


# ---------------------------------------------------------------------------
# US sector ETFs via Stooq
# ---------------------------------------------------------------------------

_US_SECTOR_ETFS: list[tuple[str, str]] = [
    ("XLK.US", "Technology"),
    ("XLF.US", "Financial"),
    ("XLE.US", "Energy"),
    ("XLV.US", "Healthcare"),
    ("XLI.US", "Industrial"),
    ("XLY.US", "Consumer Disc."),
    ("XLP.US", "Consumer Staples"),
    ("XLU.US", "Utilities"),
    ("XLB.US", "Materials"),
    ("XLRE.US", "Real Estate"),
    ("XLC.US", "Communication"),
]


def fetch_us_sector_etfs(sleep_seconds: float = 1.0) -> SectorRanking:
    """Fetch all 11 SPDR sector ETFs from Stooq and rank by change%."""
    import csv
    import io

    items: list[SectorItem] = []
    for symbol, label in _US_SECTOR_ETFS:
        try:
            url = f"https://stooq.com/q/d/l/?s={symbol.lower()}&i=d"
            headers = {"User-Agent": _UA}
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            text = resp.text.strip()
            if not text or "No data" in text:
                continue

            reader = csv.DictReader(io.StringIO(text))
            rows = list(reader)
            if len(rows) < 2:
                continue

            latest = rows[-1]
            prev = rows[-2]
            price = _parse_float(latest.get("Close"))
            prev_price = _parse_float(prev.get("Close"))
            if price is None or prev_price is None or prev_price == 0:
                continue

            change_pct = (price - prev_price) / prev_price * 100
            items.append(
                SectorItem(
                    name=f"{label} ({symbol.replace('.US', '')})",
                    code=symbol,
                    change_percent=change_pct,
                    change_color=_change_color(change_pct),
                )
            )
        except Exception as exc:
            logger.warning("Stooq sector ETF fetch failed for %s: %s", symbol, exc)

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    items.sort(key=lambda x: x.change_percent, reverse=True)
    return SectorRanking(title="US Sector ETFs", items=items)


# ---------------------------------------------------------------------------
# Build all sector rankings
# ---------------------------------------------------------------------------

def build_sector_rankings(
    top_n: int = 5,
    sleep_seconds: float = 1.0,
) -> list[SectorRanking]:
    rankings: list[SectorRanking] = []

    us = fetch_us_sector_etfs(sleep_seconds)
    if us.items:
        rankings.append(us)

    cn_industry = fetch_cn_industry_sectors(top_n)
    if cn_industry.items:
        rankings.append(cn_industry)

    cn_concept = fetch_cn_concept_sectors(top_n)
    if cn_concept.items:
        rankings.append(cn_concept)

    return rankings
