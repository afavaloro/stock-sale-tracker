"""Backtest: how would both strategies have done over the past BACKTEST_YEARS?

Free data has no history of company financials, so the backtest can only use the two
price checks (20% off the 52-week high AND below the 200-day average), plus Strategy A's
price-based extra checks (bounce off the 20-day low; collapsed stocks back above their
50-day average). That makes it LESS strict than the live bot. It also uses today's index members, which
flatters results a little (companies that collapsed and left the index are missing).

Run with:  python -m tracker.backtest              (S&P 500)
           python -m tracker.backtest --market asx
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from . import config as C
from . import data, portfolio, signals

from .run_daily import paths


def run(prices, names: dict, market: str = "us") -> dict:
    M = C.MARKETS[market]
    BENCH = M["benchmarks"]
    stocks = [c for c in prices.columns if c not in BENCH]
    sig = signals.price_checks_vectorized(prices[stocks])
    a_ok, drop = signals.a_checks_vectorized(prices[stocks])
    a_sig = sig & a_ok
    cols = list(sig.columns)
    main_idx = prices[next(iter(BENCH))]
    mkt_drop = (1 - main_idx / main_idx.rolling(252, min_periods=200).max()).fillna(0)
    # Start once there is a full year of history to measure 52-week highs against,
    # and every benchmark fund has a price
    days = prices.index[252:]
    days = days[prices.loc[days, list(BENCH)].notna().all(axis=1).values]
    bench0 = {b: float(prices.loc[days[0], b]) for b in BENCH}
    state = portfolio.new_state(days[0].date().isoformat(), bench0)

    # Same as the live bot: a stock that stays on sale can be bought again after the cooldown
    sig_v, a_v, drop_v = sig.loc[days].values, a_sig.loc[days].values, drop.loc[days].values
    signal_count = {}
    for i, d in enumerate(days):
        row = prices.loc[d]
        todays = [cols[j] for j in sorted(sig_v[i].nonzero()[0], key=lambda j: -drop_v[i, j])]
        a_idx = sorted(a_v[i].nonzero()[0], key=lambda j: -drop_v[i, j])   # deepest drop first
        day = d.date().isoformat()
        portfolio.process_day(state, day, {t: v for t, v in row.items() if v == v},
                              todays, [cols[j] for j in a_idx], names,
                              market_drop=float(mkt_drop.loc[d]))
        n_new = sum(1 for t, v in state["last_signal"].items() if v == day)
        signal_count[day[:4]] = signal_count.get(day[:4], 0) + n_new
    trades = state["trades"]
    by_year = {y: {"signals": n, "A": 0, "B": 0} for y, n in signal_count.items()}
    for t in trades:
        if t["action"] == "buy":
            by_year[t["date"][:4]]["A" if t["strategy"] == "fixed" else "B"] += 1
    return {
        "generated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "years": C.BACKTEST_YEARS, "market": market, "market_name": M["name"],
        "currency": M["currency"],
        "note": ("Uses only the price checks (no historical company financials are available, "
                 "so the P/E, profit and business-recovery checks are skipped) and today's "
                 f"{M['name']} members, so it is less strict and somewhat more optimistic than the live bot."),
        "summary": portfolio.summary(state),
        "history": portfolio.public_history(state, every=5),
        "by_year": by_year,
        "recent_trades": list(reversed(trades[-200:])),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=list(C.MARKETS), default="us")
    market = ap.parse_args().market
    M = C.MARKETS[market]
    OUT, _ = paths(market)
    universe = data.get_universe(market)
    prices = data.get_prices(list(universe["ticker"]) + list(M["benchmarks"]),
                             period=f"{C.BACKTEST_YEARS + 1}y")
    result = run(prices, dict(zip(universe["ticker"], universe["name"])), market)
    # Keep the app light: list at most 100 open holdings per strategy
    for k in ("fixed", "rules"):
        result["summary"][k]["positions"] = result["summary"][k]["positions"][:100]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "backtest.json").write_text(json.dumps(result, indent=1))
    s = result["summary"]
    b0 = next(iter(M["benchmarks"]))
    print(f"A: {s['fixed']['return_pct']}% vs {b0} {s['fixed']['bench'][b0]['return_pct']}%")
    print(f"B: {s['rules']['return_pct']}% vs {b0} {s['rules']['bench'][b0]['return_pct']}%")


if __name__ == "__main__":
    main()
