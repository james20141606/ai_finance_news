import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

logger = logging.getLogger(__name__)


@dataclass
class MarketItem:
    name: str
    symbol: str
    price: float | None
    change: float | None
    change_percent: float | None
    currency: str
    as_of: str
    change_color: str


@dataclass
class MarketSection:
    title: str
    items: list[MarketItem]


def _sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def _change_color(value: float | None) -> str:
    if value is None:
        return "#64748b"
    if value > 0:
        return "#16a34a"
    if value < 0:
        return "#dc2626"
    return "#64748b"


def _parse_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_alpha_vantage_quote(
    symbol: str,
    api_key: str,
    sleep_seconds: float,
) -> MarketItem | None:
    url = (
        "https://www.alphavantage.co/query"
        f"?function=GLOBAL_QUOTE&symbol={symbol}&apikey={api_key}"
    )
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    quote = data.get("Global Quote", {})
    if not quote:
        logger.warning("Alpha Vantage empty quote for %s", symbol)
        return None

    price = _parse_float(quote.get("05. price"))
    change = _parse_float(quote.get("09. change"))
    change_pct_raw = quote.get("10. change percent", "").replace("%", "")
    change_pct = _parse_float(change_pct_raw)
    as_of = quote.get("07. latest trading day", "")

    _sleep(sleep_seconds)

    return MarketItem(
        name=symbol,
        symbol=symbol,
        price=price,
        change=change,
        change_percent=change_pct,
        currency="USD",
        as_of=as_of,
        change_color=_change_color(change),
    )


def fetch_alpha_vantage_metal(
    metal_symbol: str,
    api_key: str,
    sleep_seconds: float,
) -> MarketItem | None:
    url = (
        "https://www.alphavantage.co/query"
        f"?function=GOLD_SILVER_HISTORY&symbol={metal_symbol}"
        f"&interval=daily&apikey={api_key}"
    )
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    series = data.get("data") or data.get("Time Series (Daily)")
    if not series:
        logger.warning("Alpha Vantage metal history empty for %s", metal_symbol)
        return None

    # Alpha Vantage metals history returns list under key "data"
    if isinstance(series, list):
        series_sorted = sorted(series, key=lambda x: x.get("date", ""), reverse=True)
        latest = series_sorted[0]
        prev = series_sorted[1] if len(series_sorted) > 1 else None
        price = _parse_float(latest.get("value"))
        prev_price = _parse_float(prev.get("value")) if prev else None
        as_of = latest.get("date", "")
    else:
        # Fallback for dict-based series
        dates = sorted(series.keys(), reverse=True)
        latest = series[dates[0]]
        prev = series[dates[1]] if len(dates) > 1 else None
        price = _parse_float(latest.get("4. close"))
        prev_price = _parse_float(prev.get("4. close")) if prev else None
        as_of = dates[0]

    change = price - prev_price if (price is not None and prev_price is not None) else None
    change_pct = (
        (change / prev_price * 100) if (change is not None and prev_price) else None
    )

    _sleep(sleep_seconds)

    name = "Gold" if metal_symbol in {"GOLD", "XAU"} else "Silver"
    return MarketItem(
        name=name,
        symbol=metal_symbol,
        price=price,
        change=change,
        change_percent=change_pct,
        currency="USD",
        as_of=as_of,
        change_color=_change_color(change),
    )


def fetch_coingecko_prices() -> list[MarketItem]:
    url = (
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=bitcoin,ethereum&vs_currencies=usd"
        "&include_24hr_change=true&include_last_updated_at=true"
    )
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    items = []
    for coin_id, name in [("bitcoin", "BTC"), ("ethereum", "ETH")]:
        info = data.get(coin_id, {})
        price = _parse_float(info.get("usd"))
        change_pct = _parse_float(info.get("usd_24h_change"))
        as_of = info.get("last_updated_at")
        as_of_str = (
            datetime.utcfromtimestamp(as_of).strftime("%Y-%m-%d %H:%M UTC")
            if as_of
            else ""
        )
        change = None
        if price is not None and change_pct is not None:
            change = price * (change_pct / 100)
        items.append(
            MarketItem(
                name=name,
                symbol=name,
                price=price,
                change=change,
                change_percent=change_pct,
                currency="USD",
                as_of=as_of_str,
                change_color=_change_color(change_pct),
            )
        )

    return items


def _format_name(symbol: str, label: str | None) -> str:
    return label or symbol


def build_market_snapshot(
    api_key: str,
    sleep_seconds: float,
) -> list[MarketSection]:
    if not api_key:
        return []

    # ETF proxies for indices (cost-effective and available via Alpha Vantage)
    us_symbols = [("SPY", "S&P 500"), ("QQQ", "Nasdaq 100"), ("DIA", "Dow Jones")]
    eu_symbols = [("VGK", "Europe"), ("FEZ", "Euro Stoxx 50"), ("EWU", "UK FTSE")]
    cn_symbols = [("FXI", "China Large Cap"), ("KWEB", "China Tech"), ("ASHR", "China A-Shares")]

    def fetch_group(symbols: list[tuple[str, str]]) -> list[MarketItem]:
        results = []
        for symbol, label in symbols:
            item = fetch_alpha_vantage_quote(symbol, api_key, sleep_seconds)
            if item:
                item.name = _format_name(symbol, label)
                results.append(item)
        return results

    sections = [
        MarketSection(title="US Major Markets", items=fetch_group(us_symbols)),
        MarketSection(title="Europe Major Markets", items=fetch_group(eu_symbols)),
        MarketSection(title="China Major Markets", items=fetch_group(cn_symbols)),
    ]

    metals = []
    for metal in ["GOLD", "SILVER"]:
        item = fetch_alpha_vantage_metal(metal, api_key, sleep_seconds)
        if item:
            metals.append(item)
    if metals:
        sections.append(MarketSection(title="Gold & Silver", items=metals))

    crypto = fetch_coingecko_prices()
    if crypto:
        sections.append(MarketSection(title="Crypto", items=crypto))

    return sections
