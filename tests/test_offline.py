"""Runs the whole pipeline on made-up prices, so it can be checked without internet.
python -m tests.test_offline"""
import json, shutil, tempfile
from pathlib import Path
import numpy as np, pandas as pd
from tracker import config as C, portfolio, run_daily, backtest

rng = np.random.default_rng(7)
N, DAYS = 60, 252 * 4
idx = pd.bdate_range(end="2026-11-20", periods=DAYS)
sectors = ["Tech", "Health", "Energy", "Financials"]
uni = pd.DataFrame({"ticker": [f"T{i:02d}" for i in range(N)],
                    "name": [f"Company {i}" for i in range(N)],
                    "sector": [sectors[i % 4] for i in range(N)]})
cols = {}
for i, t in enumerate(uni.ticker):
    r = rng.normal(0.0004, 0.018, DAYS)
    if i % 5 == 0:                     # every 5th stock has a crash in the last 6 months
        r[-120:-60] -= 0.006
    cols[t] = 50 * np.exp(np.cumsum(r))
for b, drift in [("SPY", .0004), ("QQQ", .0005), ("DIA", .0003)]:
    cols[b] = 400 * np.exp(np.cumsum(rng.normal(drift, .01, DAYS)))
prices = pd.DataFrame(cols, index=idx)
fund = {t: {"eps": float(rng.uniform(-1, 4)), "fcf": float(rng.uniform(-1e8, 5e9)),
            "revenue_growth": float(rng.uniform(-.2, .2)), "operating_margin": float(rng.uniform(-.05, .3)),
            "current_ratio": float(rng.uniform(.6, 2.5)), "debt_to_equity": float(rng.uniform(20, 300)),
            "fetched": "2026-11-20"} for t in uni.ticker}
for t in uni.ticker[::5]:              # crashed stocks: profitable and cheap
    fund[t] = {"eps": float(prices[t].iloc[-1] / 6), "fcf": 1e9, "revenue_growth": .05,
               "operating_margin": .15, "current_ratio": 1.5, "debt_to_equity": 80, "fetched": "2026-11-20"}

tmp = Path(tempfile.mkdtemp())
# Simulate 30 consecutive daily runs, then re-run the last day (must not double-buy)
for k in range(30, 0, -1):
    run_daily.build(uni, prices.iloc[:DAYS - k + 1], lambda t, f: fund, tmp / "state.json", tmp / "out")
latest, trades = run_daily.build(uni, prices, lambda t, f: fund, tmp / "state.json", tmp / "out")
latest2, trades2 = run_daily.build(uni, prices, lambda t, f: fund, tmp / "state.json", tmp / "out")
assert trades2 == [] or all(t["action"] != "buy" for t in trades2), "re-run bought twice"

state = json.loads((tmp / "state.json").read_text())
assert len(state["history"]) == 30, len(state["history"])
# cooldown: no ticker bought twice within 90 days by either strategy (30 days simulated)
buys = {}
for t in state["trades"]:
    if t["action"] == "buy":
        key = t["strategy"] + ":" + t["ticker"]
        assert key not in buys, "cooldown broken"
        buys[key] = t["date"]


def check_books(state):
    """Cash + holdings == value, cash never negative, A never spends more than it has."""
    h = state["history"][-1]; lp = state["last_price"]
    for k, start in (("rules", C.START_BALANCE), ("fixed", C.A_START_BALANCE)):
        book = state[k]
        val = book["cash"] + sum(p["shares"] * lp[t] for t, p in book["positions"].items())
        assert abs(val - h[f"{k}_value"]) < 0.05, k
        assert book["cash"] >= -0.01, k
        # money in = start + all sale proceeds; money out = all buys
        tr = [t for t in state["trades"] if t["strategy"] == k]
        spent = sum(t["amount"] for t in tr if t["action"] == "buy")
        got = sum(t["amount"] for t in tr if t["action"] == "sell")
        assert spent <= start + got + 0.05, f"{k} spent more than its cash"
    a = [t for t in state["trades"] if t["strategy"] == "fixed"]
    weeks = {}
    for t in a:
        if t["action"] == "buy":
            assert t["amount"] >= C.A_MIN_POSITION - 0.01
            wk = portfolio._week(t["date"]); weeks[wk] = weeks.get(wk, 0) + 1
            assert weeks[wk] <= C.A_CRASH_BUYS_PER_WEEK, "weekly limit broken"
        elif t["reason"] == "stop loss":
            assert t["pnl_pct"] <= -C.A_STOP_LOSS * 100 + 0.01
        elif t["reason"] == "take profit":
            assert t["pnl_pct"] >= C.A_TAKE_PROFIT * 100 - 0.01


check_books(state)
for r in latest["on_sale"]:
    assert all(r["checks"].values())
    if r["a_pick"]:
        assert r["a_checks"]["bounce"]
        if r["drop_pct"] >= C.COLLAPSE_DROP * 100:
            assert r["a_checks"]["recovery"]
# A's live buys must all be A picks
picks = {r["ticker"] for r in latest["on_sale"] if r["a_pick"]}
assert all(t["ticker"] in picks for t in trades if t["strategy"] == "fixed" and t["action"] == "buy")
print("on sale:", [r["ticker"] for r in latest["on_sale"]], "A picks:", sorted(picks), "near:", len(latest["near_misses"]))
print("A holdings:", len(state["fixed"]["positions"]), "B holdings:", len(state["rules"]["positions"]))
print(json.dumps(portfolio.summary(state)["fixed"]["bench"]))

# recovery check on its own
from tracker import signals
good = {"revenue_growth": .02, "operating_margin": .1, "current_ratio": 1.2, "debt_to_equity": 90}
assert signals.recovery_check(10, 9, good)
assert not signals.recovery_check(10, 11, good), "must be back above 50-day average"
assert not signals.recovery_check(10, 9, {**good, "revenue_growth": -.3})
assert not signals.recovery_check(10, 9, {**good, "operating_margin": -.01})
assert not signals.recovery_check(10, 9, {**good, "debt_to_equity": 350})
assert not signals.recovery_check(10, 9, {**good, "revenue_growth": None})
assert signals.recovery_check(10, 9, {**good, "current_ratio": None, "debt_to_equity": None}), "banks"

# B buys in the order given (biggest discount first), not alphabetically
st = portfolio.new_state("2026-01-05", {b: 100.0 for b in C.BENCHMARKS})
st["rules"]["cash"] = C.START_BALANCE * C.POSITION_PCT        # room for one buy
tr = portfolio.process_day(st, "2026-01-05", {b: 100.0 for b in C.BENCHMARKS} | {"ZZZ": 5.0, "AAA": 5.0}, ["ZZZ", "AAA"])
assert [t["ticker"] for t in tr if t["strategy"] == "rules"] == ["ZZZ"], tr

# buy size grows with the account; crash mode raises the weekly limit
st = portfolio.new_state("2026-01-05", {b: 100.0 for b in C.BENCHMARKS})
st["fixed"]["cash"] = 200_000.0
px0 = {b: 100.0 for b in C.BENCHMARKS} | {f"X{i}": 10.0 for i in range(12)}
tr = portfolio.process_day(st, "2026-01-05", px0, [], [f"X{i}" for i in range(12)])
assert sum(t["action"] == "buy" for t in tr) == C.A_MAX_BUYS_PER_WEEK
assert abs(tr[0]["amount"] - 200_000 * C.A_POSITION_PCT) < 0.01, tr[0]["amount"]
st = portfolio.new_state("2026-01-05", {b: 100.0 for b in C.BENCHMARKS})
tr = portfolio.process_day(st, "2026-01-05", px0, [], [f"X{i}" for i in range(12)], market_drop=0.25)
assert sum(t["action"] == "buy" for t in tr) == C.A_CRASH_BUYS_PER_WEEK

bt = backtest.run(prices, dict(zip(uni.ticker, uni.name)))
s = bt["summary"]
print("backtest A", s["fixed"]["return_pct"], "buys", s["fixed"]["buys"], "closed", s["fixed"]["closed_count"],
      "| B", s["rules"]["return_pct"], "buys", s["rules"]["buys"], "closed", s["rules"]["closed_count"],
      "win", s["rules"]["win_rate"])
print("by year", bt["by_year"])
assert s["fixed"]["buys"] > 0 and s["fixed"]["closed_count"] > 0, "A never traded in the backtest"
assert s["fixed"]["buys"] < s["rules"]["buys"] * 3
for t in bt["recent_trades"]:
    if t.get("reason") == "take profit" and t["strategy"] == "rules":
        assert t["pnl_pct"] >= C.TAKE_PROFIT * 100 - 0.01
(tmp / "out" / "backtest.json").write_text(json.dumps(bt))

# Same pipeline for the ASX: same prices, ASX tickers and benchmark funds
asx_b = list(C.MARKETS["asx"]["benchmarks"])
ren = {t: t + ".AX" for t in uni.ticker} | dict(zip(["SPY", "QQQ", "DIA"], asx_b))
p_asx = prices.rename(columns=ren)
u_asx = uni.assign(ticker=uni.ticker + ".AX")
f_asx = {t + ".AX": v for t, v in fund.items()}
la, ta = run_daily.build(u_asx, p_asx, lambda t, f: f_asx, tmp / "asx_state.json", tmp / "out" / "asx", "asx")
assert la["market"] == "asx" and set(la["benchmarks"]) == set(asx_b)
assert la["on_sale"] and all(r["ticker"].endswith(".AX") for r in la["on_sale"])
check_books(json.loads((tmp / "asx_state.json").read_text()))
bta = backtest.run(p_asx, dict(zip(u_asx.ticker, u_asx.name)), "asx")
assert bta["summary"]["fixed"]["return_pct"] == bt["summary"]["fixed"]["return_pct"], "ASX run should match US on same prices"
(tmp / "out" / "asx" / "backtest.json").write_text(json.dumps(bta))
print("ASX:", len(la["on_sale"]), "on sale,", la["a_picks"], "A picks; backtest A", bta["summary"]["fixed"]["return_pct"])
out = Path(__file__).resolve().parent.parent / "sample_data"
shutil.rmtree(out, ignore_errors=True); shutil.copytree(tmp / "out", out)
print("ALL CHECKS PASSED ->", out)
