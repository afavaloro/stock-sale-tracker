"""Backtest: how would both strategies have done over the past BACKTEST_YEARS?

Free data has no history of company financials, so the backtest can only use the two
price checks (20% off the 52-week high AND below the 200-day average). That makes it
LESS strict than the live bot. It also uses today's S&P 500 members, which flatters
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
    # Start once there is a full year of history to measure 52-week highs against
    days = prices.index[252:]
    bench0 = {b: float(prices.loc[days[0], b]) for b in C.BENCHMARKS}
    state = portfolio.new_state(days[0].date().isoformat(), bench0)

    # Same as the live bot: a stock that stays on sale can be bought again after the cooldown
    for d in days:
        row = prices.loc[d]
        todays = list(sig.columns[sig.loc[d].values])
        portfolio.process_day(state, d.date().isoformat(),
                              {t: v for t, v in row.items() if v == v}, todays, names)
    trades = state["trades"]
    by_year = {}
    for t in trades:
        if t["strategy"] == "fixed":
            y = t["date"][:4]
            by_year[y] = by_year.get(y, 0) + 1
    return {
        "generated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "years": C.BACKTEST_YEARS,
        "note": ("Uses only the two price checks (no historical financials available), "
                 "and today's S&P 500 members, so it is less strict and somewhat more "
                 "optimistic than the live bot."),
        "summary": portfolio.summary(state),
        "history": portfolio.public_history(state, every=5),
        "signals_by_year": by_year,
        "recent_trades": list(reversed(trades[-200:])),
    }


def main():
    universe = data.get_sp500()
    prices = data.get_prices(list(universe["ticker"]) + list(C.BENCHMARKS),
                             period=f"{C.BACKTEST_YEARS + 1}y")
    result = run(prices, dict(zip(universe["ticker"], universe["name"])))
    # The table of open lots can be huge in a backtest; keep the app light
    result["summary"]["fixed"]["lots"] = result["summary"]["fixed"]["lots"][:100]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "backtest.json").write_text(json.dumps(result, indent=1))
    s = result["summary"]
    print(f"fixed: {s['fixed']['return_pct']}% vs SPY {s['fixed']['bench']['SPY']['return_pct']}%")
    print(f"rules: {s['rules']['return_pct']}% vs SPY {s['rules']['bench']['SPY']['return_pct']}%")


if __name__ == "__main__":
    main()
