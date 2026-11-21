"""Simulated investing. The same engine runs the live daily portfolio and the backtest.

Both strategies start with cash, buy with it, and put the money from every sale (profit
or loss) back into cash. Neither ever gets new money from outside.

Strategy A ("fixed"): A_START_BALANCE, A_POSITION_PCT of its current value per buy. Only buys stocks that also
  pass A's extra checks (bounced off the low, recovery check for collapsed stocks),
  at most A_MAX_BUYS_PER_WEEK a week (A_CRASH_BUYS_PER_WEEK when the S&P 500 is
  A_CRASH_DROP or more below its high), deepest discounts first.
  Sells at +A_TAKE_PROFIT, -A_STOP_LOSS, or after A_MAX_HOLD_DAYS.
Strategy B ("rules"): START_BALANCE, POSITION_PCT of it per buy, buys every on-sale
  signal while cash lasts. Sells at +TAKE_PROFIT or after MAX_HOLD_DAYS.

Each is compared with putting its starting balance into each benchmark on day one.
"""
from __future__ import annotations

from datetime import date

from . import config as C


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _week(day: str) -> str:
    y, w, _ = _d(day).isocalendar()
    return f"{y}-W{w:02d}"


def _book(start: float, bench_prices: dict) -> dict:
    return {"start": start, "cash": start, "positions": {},
            "bench_shares": {b: start / bench_prices[b] for b in C.BENCHMARKS}}


def new_state(start_day: str, bench_prices: dict) -> dict:
    fixed = _book(C.A_START_BALANCE, bench_prices)
    fixed.update({"last_buy": {}, "week": None, "week_buys": 0})
    return {
        "version": 2,
        "start_date": start_day,
        "fixed": fixed,
        "rules": _book(C.START_BALANCE, bench_prices),
        "last_signal": {},          # B's cooldown: last day each ticker went on sale
        "last_price": {},
        "trades": [],
        "history": [],
    }


def _sell(book, strategy, t, pos, p, day, reason, held, names, today):
    gain = p / pos["price"] - 1
    proceeds = pos["shares"] * p
    book["cash"] += proceeds
    del book["positions"][t]
    today.append({"date": day, "ticker": t, "name": names.get(t, t),
                  "strategy": strategy, "action": "sell", "reason": reason,
                  "price": round(p, 2), "amount": round(proceeds, 2),
                  "pnl": round(proceeds - pos["cost"], 2),
                  "pnl_pct": round(gain * 100, 1), "held_days": held})


def _buy(book, strategy, t, p, size, day, names, today):
    book["cash"] -= size
    book["positions"][t] = {"date": day, "price": p, "shares": size / p, "cost": size}
    today.append({"date": day, "ticker": t, "name": names.get(t, t),
                  "strategy": strategy, "action": "buy", "price": round(p, 2),
                  "amount": round(size, 2)})


def process_day(state: dict, day: str, prices: dict, signals: list[str],
                a_candidates: list[str] | None = None,
                names: dict | None = None, market_drop: float = 0.0) -> list[dict]:
    """Advance the simulation by one trading day. Returns the trades made today.

    signals: every stock on sale today (B buys these).
    a_candidates: the on-sale stocks that also pass A's extra checks, best first.
    market_drop: how far SPY is below its 52-week high (0.25 = 25%).
    """
    names = names or {}
    a_candidates = a_candidates or []
    lp = state["last_price"]
    for t, p in prices.items():
        if p is not None and p == p and p > 0:
            lp[t] = float(p)
    px = lambda t: lp.get(t)                         # noqa: E731
    today = []
    A, B = state["fixed"], state["rules"]

    # 1. Sells (first, so the cash can be reused today)
    for t, pos in list(B["positions"].items()):
        p = px(t)
        if p is None:
            continue
        gain, held = p / pos["price"] - 1, (_d(day) - _d(pos["date"])).days
        reason = ("take profit" if gain >= C.TAKE_PROFIT else
                  "max hold" if held >= C.MAX_HOLD_DAYS else None)
        if reason:
            _sell(B, "rules", t, pos, p, day, reason, held, names, today)
    for t, pos in list(A["positions"].items()):
        p = px(t)
        if p is None:
            continue
        gain, held = p / pos["price"] - 1, (_d(day) - _d(pos["date"])).days
        reason = ("take profit" if gain >= C.A_TAKE_PROFIT else
                  "stop loss" if gain <= -C.A_STOP_LOSS else
                  "max hold" if held >= C.A_MAX_HOLD_DAYS else None)
        if reason:
            _sell(A, "fixed", t, pos, p, day, reason, held, names, today)

    # 2. Strategy B buys every new signal (respecting the cooldown) while cash lasts
    for t in sorted(signals):
        p = px(t)
        last = state["last_signal"].get(t)
        if p is None or (last and (_d(day) - _d(last)).days < C.COOLDOWN_DAYS):
            continue
        state["last_signal"][t] = day
        size = min(C.START_BALANCE * C.POSITION_PCT, B["cash"])
        if t not in B["positions"] and size >= C.MIN_POSITION:
            _buy(B, "rules", t, p, size, day, names, today)

    # 3. Strategy A buys its best candidates, up to the weekly limit
    wk = _week(day)
    if A["week"] != wk:
        A["week"], A["week_buys"] = wk, 0
    limit = C.A_CRASH_BUYS_PER_WEEK if market_drop >= C.A_CRASH_DROP else C.A_MAX_BUYS_PER_WEEK
    a_value = A["cash"] + sum(pos["shares"] * (px(t) or pos["price"]) for t, pos in A["positions"].items())
    for t in a_candidates:
        if A["week_buys"] >= limit:
            break
        p = px(t)
        last = A["last_buy"].get(t)
        if p is None or t in A["positions"] or (last and (_d(day) - _d(last)).days < C.COOLDOWN_DAYS):
            continue
        size = min(a_value * C.A_POSITION_PCT, A["cash"])
        if size < C.A_MIN_POSITION:
            break
        _buy(A, "fixed", t, p, size, day, names, today)
        A["last_buy"][t] = day
        A["week_buys"] += 1

    state["trades"].extend(today)

    # 4. Daily snapshot
    def value(book):
        return round(book["cash"] + sum(pos["shares"] * (px(t) or pos["price"])
                                        for t, pos in book["positions"].items()), 2)
    snap = {
        "date": day,
        "fixed_value": value(A),
        "fixed_bench": {b: round(s * px(b), 2) for b, s in A["bench_shares"].items()},
        "rules_value": value(B),
        "rules_bench": {b: round(s * px(b), 2) for b, s in B["bench_shares"].items()},
    }
    hist = state["history"]
    if hist and hist[-1]["date"] == day:
        hist[-1] = snap
    else:
        hist.append(snap)
    return today


def _book_summary(state: dict, key: str, value: float, bench: dict) -> dict:
    book, lp = state[key], state["last_price"]
    start = book["start"]
    pct = lambda v, base: round((v / base - 1) * 100, 2) if base else 0.0   # noqa: E731
    positions = [{
        "ticker": t, "date": p["date"], "buy": round(p["price"], 2),
        "now": round(lp.get(t, p["price"]), 2), "value": round(p["shares"] * lp.get(t, p["price"]), 2),
        "pct": pct(lp.get(t, p["price"]), p["price"]),
    } for t, p in book["positions"].items()]
    trades = [t for t in state["trades"] if t["strategy"] == key]
    closed = [t for t in trades if t["action"] == "sell"]
    return {
        "start": start, "value": value, "cash": round(book["cash"], 2),
        "return_pct": pct(value, start),
        "bench": {b: {"value": v, "return_pct": pct(v, start)} for b, v in bench.items()},
        "positions": sorted(positions, key=lambda x: x["date"], reverse=True),
        "buys": sum(1 for t in trades if t["action"] == "buy"),
        "closed_count": len(closed),
        "win_rate": round(100 * sum(1 for t in closed if t["pnl"] > 0) / len(closed), 1) if closed else None,
    }


def summary(state: dict) -> dict:
    """Headline numbers for the app."""
    if not state["history"]:
        return {}
    h = state["history"][-1]
    return {
        "as_of": h["date"], "start_date": state["start_date"],
        "fixed": _book_summary(state, "fixed", h["fixed_value"], h["fixed_bench"]),
        "rules": _book_summary(state, "rules", h["rules_value"], h["rules_bench"]),
    }


def public_history(state: dict, every: int = 1) -> list[dict]:
    """History for charts; `every` thins it (e.g. 5 = weekly) to keep files small."""
    h = state["history"]
    if every <= 1 or len(h) <= 2:
        return h
    return h[::every] + ([h[-1]] if (len(h) - 1) % every else [])
