"""The 'on sale' test. Pure calculations, no internet."""
from __future__ import annotations

import math

import pandas as pd

from . import config as C


def price_metrics(prices: pd.DataFrame) -> pd.DataFrame:
    """One row per ticker for the latest day: price, 52-week high, drop, 200-day average."""
    rows = []
    for t in prices.columns:
        s = prices[t].dropna()
        if len(s) < C.SMA_DAYS:
            continue
        price = float(s.iloc[-1])
        high = float(s.iloc[-252:].max())
        sma = float(s.iloc[-C.SMA_DAYS:].mean())
        rows.append({"ticker": t, "price": price, "high52": high,
                     "drop": 1 - price / high, "sma200": sma,
                     "as_of": s.index[-1].date().isoformat()})
    return pd.DataFrame(rows).set_index("ticker")


def price_checks_vectorized(prices: pd.DataFrame) -> pd.DataFrame:
    """True where checks 1 and 2 pass, for every day (used by the backtest)."""
    high = prices.rolling(252, min_periods=200).max()
    sma = prices.rolling(C.SMA_DAYS, min_periods=C.SMA_DAYS).mean()
    return (prices <= high * (1 - C.MIN_DROP_FROM_HIGH)) & (prices < sma)


def _num(x):
    try:
        x = float(x)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


def evaluate(metrics: pd.DataFrame, universe: pd.DataFrame, fundamentals: dict) -> list[dict]:
    """Runs all four checks for every stock and returns one record per stock."""
    uni = universe.set_index("ticker")
    df = metrics.join(uni, how="inner")

    # P/E from today's price and trailing earnings; sector medians from profitable companies
    eps = df.index.map(lambda t: _num((fundamentals.get(t) or {}).get("eps")))
    df["eps"] = list(eps)
    df["pe"] = [p / e if e and e > 0 else None for p, e in zip(df["price"], df["eps"])]
    sector_pe = df.dropna(subset=["pe"]).groupby("sector")["pe"].median().to_dict()

    out = []
    for t, r in df.iterrows():
        f = fundamentals.get(t) or {}
        fcf = _num(f.get("fcf"))
        pe = _num(r["pe"])
        spe = sector_pe.get(r["sector"])
        checks = {
            "drop": r["drop"] >= C.MIN_DROP_FROM_HIGH,
            "below_sma": r["price"] < r["sma200"],
            "cheap": bool(pe and spe and pe <= spe * (1 - C.PE_DISCOUNT_VS_SECTOR)),
            "quality": bool((r["eps"] or 0) > 0 and
                            (fcf is not None and fcf > 0 or not C.REQUIRE_POSITIVE_FCF)),
        }
        out.append({
            "ticker": t, "name": r["name"], "sector": r["sector"],
            "price": round(r["price"], 2), "high52": round(r["high52"], 2),
            "drop_pct": round(r["drop"] * 100, 1), "sma200": round(r["sma200"], 2),
            "pe": round(pe, 1) if pe else None,
            "sector_pe": round(spe, 1) if spe else None,
            "fcf": fcf, "checks": checks, "score": sum(checks.values()),
        })
    return out
