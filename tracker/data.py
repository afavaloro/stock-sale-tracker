"""Downloads market data. Everything that touches the internet lives here."""
from __future__ import annotations

import io
import json
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests

SP500_CSV = ("https://raw.githubusercontent.com/datasets/"
             "s-and-p-500-companies/main/data/constituents.csv")
SP500_WIKI = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
HEADERS = {"User-Agent": "Mozilla/5.0 (stock-sale-tracker)"}


def yahoo_symbol(sym: str) -> str:
    return sym.strip().upper().replace(".", "-")   # BRK.B -> BRK-B


def get_sp500() -> pd.DataFrame:
    """Returns columns: ticker, name, sector."""
    try:
        r = requests.get(SP500_CSV, headers=HEADERS, timeout=30)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        df = df.rename(columns={"Symbol": "ticker", "Security": "name",
                                "GICS Sector": "sector"})
    except Exception:
        r = requests.get(SP500_WIKI, headers=HEADERS, timeout=30)
        df = pd.read_html(io.StringIO(r.text))[0]
        df = df.rename(columns={"Symbol": "ticker", "Security": "name",
                                "GICS Sector": "sector"})
    df["ticker"] = df["ticker"].map(yahoo_symbol)
    return df[["ticker", "name", "sector"]].drop_duplicates("ticker").reset_index(drop=True)


def get_prices(tickers: list[str], period: str = "2y") -> pd.DataFrame:
    """Daily closes adjusted for splits and dividends. Rows = dates, cols = tickers."""
    import yfinance as yf
    frames = []
    for i in range(0, len(tickers), 100):          # batches keep Yahoo happy
        chunk = tickers[i:i + 100]
        for attempt in range(3):
            try:
                raw = yf.download(chunk, period=period, auto_adjust=True,
                                  progress=False, threads=True, multi_level_index=True)
                close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]].rename(columns={"Close": chunk[0]})
                frames.append(close)
                break
            except Exception as e:                  # noqa: BLE001
                print(f"price batch {i} attempt {attempt + 1} failed: {e}")
                time.sleep(10 * (attempt + 1))
    prices = pd.concat(frames, axis=1)
    prices = prices.loc[:, ~prices.columns.duplicated()]
    prices.index = pd.to_datetime(prices.index).tz_localize(None).normalize()
    return prices.sort_index().dropna(how="all")


def _fetch_one_fundamental(ticker: str) -> dict:
    import yfinance as yf
    info = yf.Ticker(ticker).info or {}
    return {
        "eps": info.get("trailingEps"),
        "fcf": info.get("freeCashflow"),
        "revenue_growth": info.get("revenueGrowth"),
        "operating_margin": info.get("operatingMargins"),
        "current_ratio": info.get("currentRatio"),
        "debt_to_equity": info.get("debtToEquity"),
        "name": info.get("shortName"),
        "fetched": date.today().isoformat(),
    }


def get_fundamentals(tickers: list[str], cache_path: Path, max_age_days: int,
                     force: set[str] | None = None) -> dict:
    """EPS and free cash flow per ticker, cached on disk so Yahoo is asked weekly, not daily.
    Tickers in `force` (today's candidates) are always refreshed."""
    force = force or set()
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    today = date.today()
    todo = []
    for t in tickers:
        entry = cache.get(t)
        stale = (entry is None or
                 (today - datetime.fromisoformat(entry["fetched"]).date()).days > max_age_days)
        if stale or t in force:
            todo.append(t)
    print(f"fundamentals: {len(todo)} to refresh, {len(tickers) - len(todo)} cached")
    for n, t in enumerate(todo, 1):
        for attempt in range(3):
            try:
                cache[t] = _fetch_one_fundamental(t)
                break
            except Exception as e:                  # noqa: BLE001
                print(f"  {t} attempt {attempt + 1}: {e}")
                time.sleep(3 * (attempt + 1))
        time.sleep(0.25)
        if n % 50 == 0:
            print(f"  {n}/{len(todo)}")
            cache_path.write_text(json.dumps(cache))   # save progress
    cache_path.write_text(json.dumps(cache))
    return cache


def notify(topic: str | None, title: str, message: str, click_url: str | None = None):
    """Push notification through the free ntfy.sh app. Skipped if no topic is set."""
    if not topic:
        return
    headers = {"Title": title.encode("utf-8"), "Tags": "chart_with_downwards_trend"}
    if click_url:
        headers["Click"] = click_url
    try:
        requests.post(f"https://ntfy.sh/{topic}", data=message.encode("utf-8"),
                      headers=headers, timeout=20)
    except Exception as e:                          # noqa: BLE001
        print(f"notification failed: {e}")
