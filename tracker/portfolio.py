"""Simulated investing. The same engine runs the live daily portfolio and the backtest.

Strategy A ("fixed"): every time a stock goes on sale, invest FIXED_AMOUNT in it and,
  for comparison, the same amount in each benchmark ETF on the same day.
Strategy B ("rules"): start with START_BALANCE in cash. Buy POSITION_PCT of the starting
  balance on each signal while cash lasts. Sell at +TAKE_PROFIT or after MAX_HOLD_DAYS.
  Compared with putting START_BALANCE into each benchmark on the start date.
"""
from __future__ import annotations

from datetime import date

from . import config as C


def _d(s: str) -> date:
    return date.fromisoformat(s)


def new_state(start_day: str, bench_prices: dict) -> dict:
    return {
        "start_date": start_day,
        "fixed": {"lots": []},
        "rules": {
            "cash": C.START_BALANCE,
            "positions": {},
            "bench_shares": {b: C.START_BALANCE / bench_prices[b] for b in C.BENCHMARKS},
        },
        "last_signal": {},
        "last_price": {},
        "trades": [],
        "history": [],
    }


def process_day(state: dict, day: str, prices: dict, signals: list[str],
                names: dict | None = None) -> list[dict]:
    """Advance the simulation by one trading day. Returns the trades made today."""
    names = names or {}
    lp = state["last_price"]
    for t, p in prices.items():
        if p is not None and p == p and p > 0:
            lp[t] = float(p)
    px = lambda t: lp.get(t)                         # noqa: E731
    today = []

    # 1. Strategy B sells
    rules = state["rules"]
    for t, pos in list(rules["positions"].items()):
        p = px(t)
        if p is None:
            continue
        gain = p / pos["price"] - 1
        held = (_d(day) - _d(pos["date"])).days
        reason = ("take profit" if gain >= C.TAKE_PROFIT else
                  "max hold" if held >= C.MAX_HOLD_DAYS else None)
        if reason:
            proceeds = pos["shares"] * p
            rules["cash"] += proceeds
            del rules["positions"][t]
            today.append({"date": day, "ticker": t, "name": names.get(t, t),
                          "strategy": "rules", "action": "sell", "reason": reason,
                          "price": round(p, 2), "amount": round(proceeds, 2),
                          "pnl": round(proceeds - pos["cost"], 2),
                          "pnl_pct": round(gain * 100, 1), "held_days": held})

    # 2. Buys on new signals (respecting the cooldown)
    for t in sorted(signals):
        p = px(t)
        last = state["last_signal"].get(t)
        if p is None or (last and (_d(day) - _d(last)).days < C.COOLDOWN_DAYS):
            continue
        state["last_signal"][t] = day

        lot = {"ticker": t, "date": day, "price": p, "shares": C.FIXED_AMOUNT / p,
               "cost": C.FIXED_AMOUNT,
               "bench_shares": {b: C.FIXED_AMOUNT / px(b) for b in C.BENCHMARKS}}
        state["fixed"]["lots"].append(lot)
        today.append({"date": day, "ticker": t, "name": names.get(t, t),
                      "strategy": "fixed", "action": "buy", "price": round(p, 2),
                      "amount": C.FIXED_AMOUNT})

        size = min(C.START_BALANCE * C.POSITION_PCT, rules["cash"])
        if t not in rules["positions"] and size >= C.MIN_POSITION:
            rules["cash"] -= size
            rules["positions"][t] = {"date": day, "price": p, "shares": size / p, "cost": size}
            today.append({"date": day, "ticker": t, "name": names.get(t, t),
                          "strategy": "rules", "action": "buy", "price": round(p, 2),
                          "amount": round(size, 2)})

    state["trades"].extend(today)

    # 3. Daily snapshot
    lots = state["fixed"]["lots"]
    snap = {
        "date": day,
        "fixed_invested": round(sum(l["cost"] for l in lots), 2),
        "fixed_value": round(sum(l["shares"] * (px(l["ticker"]) or l["price"]) for l in lots), 2),
        "fixed_bench": {b: round(sum(l["bench_shares"][b] for l in lots) * px(b), 2)
                        for b in C.BENCHMARKS},
        "rules_value": round(rules["cash"] + sum(
            pos["shares"] * (px(t) or pos["price"]) for t, pos in rules["positions"].items()), 2),
        "rules_bench": {b: round(s * px(b), 2) for b, s in rules["bench_shares"].items()},
    }
    hist = state["history"]
    if hist and hist[-1]["date"] == day:
        hist[-1] = snap
    else:
        hist.append(snap)
    return today


def summary(state: dict) -> dict:
    """Headline numbers for the app."""
    if not state["history"]:
        return {}
    h = state["history"][-1]
    pct = lambda v, base: round((v / base - 1) * 100, 2) if base else 0.0   # noqa: E731
    inv = h["fixed_invested"]
    lp = state["last_price"]
    open_lots = [{
        "ticker": l["ticker"], "date": l["date"], "buy": round(l["price"], 2),
        "now": round(lp.get(l["ticker"], l["price"]), 2),
        "pct": pct(lp.get(l["ticker"], l["price"]), l["price"]),
    } for l in state["fixed"]["lots"]]
    positions = [{
        "ticker": t, "date": p["date"], "buy": round(p["price"], 2),
        "now": round(lp.get(t, p["price"]), 2), "value": round(p["shares"] * lp.get(t, p["price"]), 2),
        "pct": pct(lp.get(t, p["price"]), p["price"]),
    } for t, p in state["rules"]["positions"].items()]
    closed = [t for t in state["trades"] if t["strategy"] == "rules" and t["action"] == "sell"]
    return {
        "as_of": h["date"], "start_date": state["start_date"],
        "fixed": {
            "invested": inv, "value": h["fixed_value"], "return_pct": pct(h["fixed_value"], inv),
            "signals": len(state["fixed"]["lots"]),
            "bench": {b: {"value": v, "return_pct": pct(v, inv)} for b, v in h["fixed_bench"].items()},
            "lots": sorted(open_lots, key=lambda x: x["date"], reverse=True),
        },
        "rules": {
            "start": C.START_BALANCE, "value": h["rules_value"],
            "cash": round(state["rules"]["cash"], 2),
            "return_pct": pct(h["rules_value"], C.START_BALANCE),
            "bench": {b: {"value": v, "return_pct": pct(v, C.START_BALANCE)}
                      for b, v in h["rules_bench"].items()},
            "positions": sorted(positions, key=lambda x: x["date"], reverse=True),
            "closed_count": len(closed),
            "win_rate": round(100 * sum(1 for t in closed if t["pnl"] > 0) / len(closed), 1) if closed else None,
        },
    }


def public_history(state: dict, every: int = 1) -> list[dict]:
    """History for charts; `every` thins it (e.g. 5 = weekly) to keep files small."""
    h = state["history"]
    if every <= 1 or len(h) <= 2:
        return h
    return h[::every] + ([h[-1]] if (len(h) - 1) % every else [])
