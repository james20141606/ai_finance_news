import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
    weekly_change_percent: float | None = None
    weekly_change_color: str = "#64748b"

    def __post_init__(self) -> None:
        self.change_percent = round(self.change_percent, 2)
        if self.weekly_change_percent is not None:
            self.weekly_change_percent = round(self.weekly_change_percent, 2)
            self.weekly_change_color = _change_color(self.weekly_change_percent)


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
# A-share weekly sector data via Eastmoney kline API
# ---------------------------------------------------------------------------

def _fetch_eastmoney_sector_weekly(
    fs: str,
    top_n: int,
    sleep_seconds: float = 0.3,
) -> list[SectorItem]:
    """Fetch top A-share sectors, then compute 5-day change from kline API."""
    # Get top sectors by daily change first (wider pool to find weekly movers)
    pool = _fetch_eastmoney_sector_list(fs, top_n * 4)
    if not pool:
        return []

    # Also fetch top losers to get a balanced view
    losers = _fetch_eastmoney_sector_list(fs, top_n * 2, descending=False)
    seen = {item.code for item in pool}
    for item in losers:
        if item.code not in seen:
            pool.append(item)
            seen.add(item.code)

    beg = (datetime.now() - timedelta(days=12)).strftime("%Y%m%d")
    end = datetime.now().strftime("%Y%m%d")

    weekly_items: list[SectorItem] = []
    for item in pool:
        try:
            url = (
                "https://push2his.eastmoney.com/api/qt/stock/kline/get"
                f"?secid=90.{item.code}&fields1=f1&fields2=f51,f53"
                f"&klt=101&fqt=1&beg={beg}&end={end}"
            )
            resp = requests.get(url, headers={"User-Agent": _UA}, timeout=15)
            resp.raise_for_status()
            klines = (resp.json().get("data") or {}).get("klines") or []
            if len(klines) < 2:
                continue

            # kline format: "date,open,close,..." — we requested f51(date),f53(close)
            # Parse the last close and the close from ~5 trading days ago
            closes = []
            for k in klines:
                parts = k.split(",")
                c = _parse_float(parts[1]) if len(parts) > 1 else None
                if c is not None:
                    closes.append(c)

            if len(closes) < 2:
                continue

            latest_close = closes[-1]
            # Use close from 5 trading days ago, or earliest available
            ref_idx = max(0, len(closes) - 6)
            ref_close = closes[ref_idx]

            if ref_close == 0:
                continue

            weekly_pct = (latest_close - ref_close) / ref_close * 100
            weekly_items.append(
                SectorItem(
                    name=item.name,
                    code=item.code,
                    change_percent=item.change_percent,
                    change_color=item.change_color,
                    weekly_change_percent=weekly_pct,
                    weekly_change_color=_change_color(weekly_pct),
                )
            )
        except Exception as exc:
            logger.warning("Eastmoney kline failed for %s: %s", item.code, exc)

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    # Sort by weekly change descending
    weekly_items.sort(key=lambda x: x.weekly_change_percent or 0, reverse=True)
    return weekly_items


def fetch_cn_industry_sectors_weekly(top_n: int = 5) -> SectorRanking:
    items = _fetch_eastmoney_sector_weekly("m:90+t:2", top_n)
    return SectorRanking(title="A-Share Industry 行业板块 (Weekly)", items=items[:top_n])


def fetch_cn_concept_sectors_weekly(top_n: int = 5) -> SectorRanking:
    items = _fetch_eastmoney_sector_weekly("m:90+t:3", top_n)
    return SectorRanking(title="A-Share Concept 概念板块 (Weekly)", items=items[:top_n])


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


def fetch_us_sector_etfs(sleep_seconds: float = 1.0) -> tuple[SectorRanking, SectorRanking]:
    """Fetch all 11 SPDR sector ETFs from Stooq. Returns (daily, weekly) rankings."""
    import csv
    import io

    daily_items: list[SectorItem] = []
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

            # Weekly: compare to 5 trading days ago
            weekly_pct = None
            ref_idx = max(0, len(rows) - 6)
            ref_price = _parse_float(rows[ref_idx].get("Close"))
            if ref_price and ref_price > 0:
                weekly_pct = (price - ref_price) / ref_price * 100

            display_name = f"{label} ({symbol.replace('.US', '')})"
            daily_items.append(
                SectorItem(
                    name=display_name,
                    code=symbol,
                    change_percent=change_pct,
                    change_color=_change_color(change_pct),
                    weekly_change_percent=weekly_pct,
                    weekly_change_color=_change_color(weekly_pct),
                )
            )
        except Exception as exc:
            logger.warning("Stooq sector ETF fetch failed for %s: %s", symbol, exc)

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    daily_sorted = sorted(daily_items, key=lambda x: x.change_percent, reverse=True)
    weekly_sorted = sorted(daily_items, key=lambda x: x.weekly_change_percent or 0, reverse=True)

    return (
        SectorRanking(title="US Sector ETFs", items=daily_sorted),
        SectorRanking(title="US Sector ETFs (Weekly)", items=weekly_sorted),
    )


# ---------------------------------------------------------------------------
# Build all sector rankings
# ---------------------------------------------------------------------------

def build_sector_rankings(
    top_n: int = 5,
    sleep_seconds: float = 1.0,
) -> tuple[list[SectorRanking], list[SectorRanking]]:
    """Returns (daily_rankings, weekly_rankings)."""
    daily: list[SectorRanking] = []
    weekly: list[SectorRanking] = []

    us_daily, us_weekly = fetch_us_sector_etfs(sleep_seconds)
    if us_daily.items:
        daily.append(us_daily)
    if us_weekly.items:
        weekly.append(us_weekly)

    cn_industry = fetch_cn_industry_sectors(top_n)
    if cn_industry.items:
        daily.append(cn_industry)

    cn_concept = fetch_cn_concept_sectors(top_n)
    if cn_concept.items:
        daily.append(cn_concept)

    cn_industry_w = fetch_cn_industry_sectors_weekly(top_n)
    if cn_industry_w.items:
        weekly.append(cn_industry_w)

    cn_concept_w = fetch_cn_concept_sectors_weekly(top_n)
    if cn_concept_w.items:
        weekly.append(cn_concept_w)

    return daily, weekly
