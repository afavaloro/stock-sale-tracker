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
            "fetched": "2026-11-20"} for t in uni.ticker}
for t in uni.ticker[::5]:              # crashed stocks: profitable and cheap
    fund[t] = {"eps": float(prices[t].iloc[-1] / 6), "fcf": 1e9, "fetched": "2026-11-20"}

tmp = Path(tempfile.mkdtemp())
# Simulate 30 consecutive daily runs, then re-run the last day (must not double-buy)
for k in range(30, 0, -1):
    run_daily.build(uni, prices.iloc[:DAYS - k + 1], lambda t, f: fund, tmp / "state.json", tmp / "out")
latest, trades = run_daily.build(uni, prices, lambda t, f: fund, tmp / "state.json", tmp / "out")
latest2, trades2 = run_daily.build(uni, prices, lambda t, f: fund, tmp / "state.json", tmp / "out")
assert trades2 == [] or all(t["action"] != "buy" for t in trades2), "re-run bought twice"

state = json.loads((tmp / "state.json").read_text())
assert len(state["history"]) == 30, len(state["history"])
# cooldown: no ticker bought twice within 90 days by the fixed strategy
buys = {}
for t in state["trades"]:
    if t["strategy"] == "fixed":
        assert t["ticker"] not in buys, "cooldown broken"
        buys[t["ticker"]] = t["date"]
# accounting: rules cash + positions == value
h = state["history"][-1]; lp = state["last_price"]
val = state["rules"]["cash"] + sum(p["shares"] * lp[t] for t, p in state["rules"]["positions"].items())
assert abs(val - h["rules_value"]) < 0.05
assert abs(h["fixed_invested"] - C.FIXED_AMOUNT * len(state["fixed"]["lots"])) < 0.01
for r in latest["on_sale"]:
    assert all(r["checks"].values())
print("on sale:", [r["ticker"] for r in latest["on_sale"]], "near:", len(latest["near_misses"]))
print("fixed lots:", len(state["fixed"]["lots"]), "rules positions:", len(state["rules"]["positions"]))
print(json.dumps(portfolio.summary(state)["fixed"]["bench"]))

bt = backtest.run(prices, dict(zip(uni.ticker, uni.name)))
s = bt["summary"]
print("backtest fixed", s["fixed"]["return_pct"], "signals", s["fixed"]["signals"],
      "| rules", s["rules"]["return_pct"], "closed", s["rules"]["closed_count"], "win", s["rules"]["win_rate"])
# take-profit sells must be >= +25%
for t in bt["recent_trades"]:
    if t.get("reason") == "take profit":
        assert t["pnl_pct"] >= C.TAKE_PROFIT * 100 - 0.01
(tmp / "out" / "backtest.json").write_text(json.dumps(bt))
out = Path(__file__).resolve().parent.parent / "sample_data"
shutil.rmtree(out, ignore_errors=True); shutil.copytree(tmp / "out", out)
print("ALL CHECKS PASSED ->", out)
