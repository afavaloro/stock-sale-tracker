"""Estimated chance of profit for an on-sale stock, learned from price history.

The backtest finds every time a stock went "on sale" on price (20%+ off its 52-week high
and below its 200-day average) and asks: if you had bought that day and followed Strategy
A's sell rules (+25%, -20%, or 2 years), would you have made money? A small logistic
regression learns how the price pattern on the day of the sale relates to that outcome.

It's trained on the older years and tested on the most recent years it hasn't seen, and
that test result is saved alongside it, so you can judge how much to trust it.
Free data has no history of company financials, so the model only uses price patterns.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C

FEATURES = ["drop", "below_sma200", "bounce", "vs_sma50", "volatility", "market_drop"]
LABELS = {
    "drop": "Fall from 52-week high",
    "below_sma200": "Distance below 200-day average",
    "bounce": "Bounce off 20-day low",
    "vs_sma50": "Price vs 50-day average",
    "volatility": "How jumpy the price is",
    "market_drop": "Whole market's fall from its high",
}
HOLD_TRADING_DAYS = round(C.A_MAX_HOLD_DAYS * 252 / 365)
GAP_TRADING_DAYS = round(C.COOLDOWN_DAYS * 252 / 365)
TEST_YEARS = 3


def feature_frames(prices: pd.DataFrame, market: pd.Series) -> dict:
    """Every feature for every stock and day (rows = dates, cols = tickers)."""
    high = prices.rolling(252, min_periods=200).max()
    sma200 = prices.rolling(C.SMA_DAYS, min_periods=C.SMA_DAYS).mean()
    sma50 = prices.rolling(C.RECOVERY_SMA_DAYS, min_periods=C.RECOVERY_SMA_DAYS).mean()
    low = prices.rolling(C.A_BOUNCE_DAYS, min_periods=C.A_BOUNCE_DAYS).min()
    vol = prices.pct_change(fill_method=None).rolling(63, min_periods=40).std() * np.sqrt(252)
    mkt = (1 - market / market.rolling(252, min_periods=200).max()).fillna(0)
    return {
        "drop": 1 - prices / high,
        "below_sma200": prices / sma200 - 1,
        "bounce": prices / low - 1,
        "vs_sma50": prices / sma50 - 1,
        "volatility": vol,
        "market_drop": pd.DataFrame(np.repeat(mkt.values[:, None], prices.shape[1], 1),
                                    index=prices.index, columns=prices.columns),
    }


def live_features(r: dict, market_drop: float) -> list[float]:
    """The same features for one stock from the daily scan's numbers."""
    return [r["drop"], r["price"] / r["sma200"] - 1, r["price"] / r["low20"] - 1,
            r["price"] / r["sma50"] - 1, r["volatility"], market_drop]


def _outcome(path: np.ndarray, p0: float):
    """1 = profit, 0 = loss under A's sell rules; None if the future isn't known yet."""
    r = path / p0
    hit = np.nonzero((r >= 1 + C.A_TAKE_PROFIT) | (r <= 1 - C.A_STOP_LOSS))[0]
    if len(hit):
        return int(r[hit[0]] >= 1 + C.A_TAKE_PROFIT)
    if len(path) >= HOLD_TRADING_DAYS and np.isfinite(r[-1]):
        return int(r[-1] > 1)
    return None


def events(prices: pd.DataFrame, on_sale: pd.DataFrame, frames: dict) -> pd.DataFrame:
    """One row per new on-sale event (not within the cooldown of the last one), with
    its features and outcome."""
    P = prices.values
    S = on_sale.reindex(columns=prices.columns).fillna(False).values
    F = {k: frames[k].values for k in FEATURES}
    rows = []
    for j in range(P.shape[1]):
        last = -10**9
        for i in np.nonzero(S[:, j])[0]:
            if i - last < GAP_TRADING_DAYS:
                continue
            last = i
            p0 = P[i, j]
            path = P[i + 1:i + 1 + HOLD_TRADING_DAYS, j]
            path = path[np.isfinite(path)]
            y = _outcome(path, p0)
            x = [F[k][i, j] for k in FEATURES]
            if y is None or not np.all(np.isfinite(x)):
                continue
            rows.append([prices.index[i]] + x + [y])
    return pd.DataFrame(rows, columns=["date"] + FEATURES + ["profit"])


def _fit(X: np.ndarray, y: np.ndarray, l2: float = 1.0):
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = np.c_[np.ones(len(X)), (X - mu) / sd]
    w = np.zeros(Z.shape[1])
    reg = np.eye(len(w)) * l2
    reg[0, 0] = 0
    for _ in range(50):                               # Newton's method
        p = 1 / (1 + np.exp(-Z @ w))
        g = Z.T @ (p - y) + reg @ w
        H = (Z * (p * (1 - p))[:, None]).T @ Z + reg
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return {"mean": mu.tolist(), "std": sd.tolist(), "intercept": float(w[0]), "coef": w[1:].tolist()}


def predict(model: dict, X) -> np.ndarray:
    X = np.atleast_2d(np.asarray(X, float))
    z = model["intercept"] + ((X - model["mean"]) / np.array(model["std"])) @ np.array(model["coef"])
    return 1 / (1 + np.exp(-z))


def _auc(y, p) -> float | None:
    """Chance the model ranks a random winner above a random loser (0.5 = coin flip)."""
    y, p = np.asarray(y), np.asarray(p)
    pos, neg = p[y == 1], p[y == 0]
    if not len(pos) or not len(neg):
        return None
    ranks = pd.Series(np.r_[pos, neg]).rank().values
    return float((ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def train(prices: pd.DataFrame, on_sale: pd.DataFrame, market: pd.Series) -> dict | None:
    stocks = list(on_sale.columns)
    ev = events(prices[stocks], on_sale, feature_frames(prices[stocks], market))
    if len(ev) < 200 or ev["profit"].nunique() < 2:
        return None
    cut = ev["date"].max() - pd.DateOffset(years=TEST_YEARS)
    tr, te = ev[ev["date"] <= cut], ev[ev["date"] > cut]
    test = None
    if len(tr) >= 200 and len(te) >= 50 and tr["profit"].nunique() == 2:
        m = _fit(tr[FEATURES].values, tr["profit"].values)
        p = predict(m, te[FEATURES].values)
        top = te.assign(p=p).sort_values("p", ascending=False)
        q = max(1, len(top) // 3)
        test = {
            "from": te["date"].min().date().isoformat(), "to": te["date"].max().date().isoformat(),
            "events": int(len(te)), "auc": round(_auc(te["profit"], p), 3),
            "base_rate_pct": round(100 * te["profit"].mean(), 1),
            "top_third_pct": round(100 * top["profit"].iloc[:q].mean(), 1),
            "bottom_third_pct": round(100 * top["profit"].iloc[-q:].mean(), 1),
        }
    model = _fit(ev[FEATURES].values, ev["profit"].values)   # final model uses everything
    model.update({
        "features": FEATURES, "labels": LABELS, "events": int(len(ev)),
        "base_rate_pct": round(100 * ev["profit"].mean(), 1), "test": test,
        "trained_to": ev["date"].max().date().isoformat(),
        "rules": f"+{C.A_TAKE_PROFIT:.0%} / -{C.A_STOP_LOSS:.0%} / {C.A_MAX_HOLD_DAYS} days",
    })
    return model
