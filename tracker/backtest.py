"""Backtest: how would both strategies have done over the past BACKTEST_YEARS?

Free data has no history of company financials, so the backtest can only use the two
price checks (20% off the 52-week high AND below the 200-day average), plus Strategy A's
price-based extra checks (bounce off the 20-day low; collapsed stocks back above their
50-day average). That makes it LESS strict than the live bot. It also uses today's S&P 500 members, which flatters
results a little (companies that collapsed and left the index are missing).

Run with:  python -m tracker.backtest
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import config as C
from . import data, portfolio, signals

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "data"


def run(prices, names: dict) -> dict:
    stocks = [c for c in prices.columns if c not in C.BENCHMARKS]
    sig = signals.price_checks_vectorized(prices[stocks])
    a_ok, drop = signals.a_checks_vectorized(prices[stocks])
    a_sig = sig & a_ok
    cols = list(sig.columns)
    # Start once there is a full year of history to measure 52-week highs against
    days = prices.index[252:]
    bench0 = {b: float(prices.loc[days[0], b]) for b in C.BENCHMARKS}
    state = portfolio.new_state(days[0].date().isoformat(), bench0)

    # Same as the live bot: a stock that stays on sale can be bought again after the cooldown
    sig_v, a_v, drop_v = sig.loc[days].values, a_sig.loc[days].values, drop.loc[days].values
    signal_count = {}
    for i, d in enumerate(days):
        row = prices.loc[d]
        todays = [cols[j] for j in sig_v[i].nonzero()[0]]
        a_idx = sorted(a_v[i].nonzero()[0], key=lambda j: -drop_v[i, j])   # deepest drop first
        day = d.date().isoformat()
        portfolio.process_day(state, day, {t: v for t, v in row.items() if v == v},
                              todays, [cols[j] for j in a_idx], names)
        n_new = sum(1 for t, v in state["last_signal"].items() if v == day)
        signal_count[day[:4]] = signal_count.get(day[:4], 0) + n_new
    trades = state["trades"]
    by_year = {y: {"signals": n, "A": 0, "B": 0} for y, n in signal_count.items()}
    for t in trades:
        if t["action"] == "buy":
            by_year[t["date"][:4]]["A" if t["strategy"] == "fixed" else "B"] += 1
    return {
        "generated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "years": C.BACKTEST_YEARS,
        "note": ("Uses only the price checks (no historical company financials are available, "
                 "so the P/E, profit and business-recovery checks are skipped) and today's "
                 "S&P 500 members, so it is less strict and somewhat more optimistic than the live bot."),
        "summary": portfolio.summary(state),
        "history": portfolio.public_history(state, every=5),
        "by_year": by_year,
        "recent_trades": list(reversed(trades[-200:])),
    }


def main():
    universe = data.get_sp500()
    prices = data.get_prices(list(universe["ticker"]) + list(C.BENCHMARKS),
                             period=f"{C.BACKTEST_YEARS + 1}y")
    result = run(prices, dict(zip(universe["ticker"], universe["name"])))
    # Keep the app light: list at most 100 open holdings per strategy
    for k in ("fixed", "rules"):
        result["summary"][k]["positions"] = result["summary"][k]["positions"][:100]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "backtest.json").write_text(json.dumps(result, indent=1))
    s = result["summary"]
    print(f"fixed: {s['fixed']['return_pct']}% vs SPY {s['fixed']['bench']['SPY']['return_pct']}%")
    print(f"rules: {s['rules']['return_pct']}% vs SPY {s['rules']['bench']['SPY']['return_pct']}%")


if __name__ == "__main__":
    main()
