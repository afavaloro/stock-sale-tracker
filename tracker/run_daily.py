"""Daily job: scan the S&P 500, update both simulated portfolios, write the app's data.

Run with:  python -m tracker.run_daily
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from . import config as C
from . import data, portfolio, signals

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "data"
CACHE = ROOT / "cache"


def build(universe, prices, fundamentals_fn, state_path: Path, out_dir: Path):
    """Core of the daily run. Data comes in as arguments so it can be tested offline."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tickers = list(universe["ticker"])
    # Skip stocks with no price on the latest day, so nothing is judged on a stale price
    last_row = prices.iloc[-1]
    tickers = [t for t in tickers if t in prices.columns and last_row.get(t) == last_row.get(t)]
    metrics = signals.price_metrics(prices[tickers])
    as_of = prices.index[-1].date().isoformat()

    # Only stocks that already passed the price checks need fresh financials today
    candidates = set(metrics[(metrics["drop"] >= C.MIN_DROP_FROM_HIGH) &
                             (metrics["price"] < metrics["sma200"])].index)
    fundamentals = fundamentals_fn(list(metrics.index), candidates)

    results = signals.evaluate(metrics, universe, fundamentals)
    on_sale = sorted([r for r in results if r["score"] == 4], key=lambda r: -r["drop_pct"])
    near = sorted([r for r in results if r["score"] == 3], key=lambda r: -r["drop_pct"])
    names = dict(zip(universe["ticker"], universe["name"]))

    bench = signals.price_metrics(prices[[b for b in C.BENCHMARKS if b in prices.columns]])

    # Portfolio
    last = prices.iloc[-1]
    today_prices = {t: float(v) for t, v in last.items() if v == v}
    if state_path.exists():
        state = json.loads(state_path.read_text())
    else:
        state = portfolio.new_state(as_of, {b: today_prices[b] for b in C.BENCHMARKS})
    if state.get("version") != 2:          # older format: start the simulation over
        state = portfolio.new_state(as_of, {b: today_prices[b] for b in C.BENCHMARKS})
    already = bool(state["history"]) and state["history"][-1]["date"] == as_of
    prev_signal_dates = dict(state["last_signal"])
    a_candidates = [r["ticker"] for r in on_sale if r["a_pick"]]   # already deepest-drop first
    trades = portfolio.process_day(state, as_of, today_prices,
                                   [] if already else [r["ticker"] for r in on_sale],
                                   [] if already else a_candidates, names)
    a_buys = {t["ticker"] for t in trades if t["action"] == "buy" and t["strategy"] == "fixed"}
    state_path.write_text(json.dumps(state))

    for r in on_sale:
        r["new_today"] = state["last_signal"].get(r["ticker"]) == as_of
        r["last_signal"] = prev_signal_dates.get(r["ticker"])
        r["a_bought_today"] = r["ticker"] in a_buys

    latest = {
        "as_of": as_of,
        "generated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "universe_size": len(results),
        "rules": {
            "min_drop_pct": C.MIN_DROP_FROM_HIGH * 100, "sma_days": C.SMA_DAYS,
            "pe_discount_pct": C.PE_DISCOUNT_VS_SECTOR * 100, "cooldown_days": C.COOLDOWN_DAYS,
            "start_balance": C.START_BALANCE,
            "a_start_balance": C.A_START_BALANCE, "a_position": C.A_POSITION,
            "a_take_profit_pct": C.A_TAKE_PROFIT * 100, "a_stop_loss_pct": C.A_STOP_LOSS * 100,
            "a_max_hold_days": C.A_MAX_HOLD_DAYS, "a_max_buys_per_week": C.A_MAX_BUYS_PER_WEEK,
            "a_bounce_pct": C.A_BOUNCE_FROM_LOW * 100, "a_bounce_days": C.A_BOUNCE_DAYS,
            "collapse_pct": C.COLLAPSE_DROP * 100, "recovery_sma_days": C.RECOVERY_SMA_DAYS,
            "recovery_min_revenue_growth_pct": C.RECOVERY_MIN_REVENUE_GROWTH * 100,
            "recovery_max_debt_to_equity_pct": C.RECOVERY_MAX_DEBT_TO_EQUITY,
            "position_pct": C.POSITION_PCT * 100, "take_profit_pct": C.TAKE_PROFIT * 100,
            "max_hold_days": C.MAX_HOLD_DAYS,
        },
        "counts": {k: sum(1 for r in results if r["checks"][k]) for k in
                   ("drop", "below_sma", "cheap", "quality")},
        "a_picks": len(a_candidates),
        "on_sale": on_sale,
        "near_misses": near[:C.NEAR_MISS_LIMIT],
        "benchmarks": {b: {"name": n, "price": round(today_prices.get(b, 0), 2),
                           "drop_pct": round(float(bench.loc[b, "drop"]) * 100, 1)
                           if b in bench.index else None}
                       for b, n in C.BENCHMARKS.items()},
    }
    (out_dir / "latest.json").write_text(json.dumps(latest, indent=1))
    pf = {"summary": portfolio.summary(state), "history": portfolio.public_history(state),
          "trades": list(reversed(state["trades"][-300:]))}
    (out_dir / "portfolio.json").write_text(json.dumps(pf, indent=1))
    return latest, trades


def main():
    CACHE.mkdir(exist_ok=True)
    universe = data.get_sp500()
    print(f"universe: {len(universe)} stocks")
    prices = data.get_prices(list(universe["ticker"]) + list(C.BENCHMARKS), period="2y")
    print(f"prices: {prices.shape[1]} tickers through {prices.index[-1].date()}")

    def fundamentals_fn(tickers, force):
        return data.get_fundamentals(tickers, CACHE / "fundamentals.json",
                                     C.FUNDAMENTALS_MAX_AGE_DAYS, force)

    latest, trades = build(universe, prices, fundamentals_fn, CACHE / "portfolio_state.json", OUT)
    print(f"on sale: {len(latest['on_sale'])}, near misses: {len(latest['near_misses'])}, "
          f"trades today: {len(trades)}")

    new = [r for r in latest["on_sale"] if r["new_today"]]
    if new:
        lines = [f"{r['ticker']} {r['name']}: ${r['price']} ({r['drop_pct']}% off high, P/E {r['pe']})"
                 + (" · bought by A" if r["a_bought_today"] else "") for r in new[:10]]
        data.notify(os.environ.get("NTFY_TOPIC"),
                    f"{len(new)} S&P 500 stock{'s' if len(new) > 1 else ''} on sale",
                    "\n".join(lines), os.environ.get("APP_URL"))


if __name__ == "__main__":
    main()
