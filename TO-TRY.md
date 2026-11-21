# Things to try

A running list of ideas, open questions and known issues. Newest ideas at the top of each section. Move items to **Done** when they ship, with the date.

## Ideas to test in the backtest

- **Does Strategy A's "wait for a 5% bounce" rule help?** The chance-of-profit model found that stocks that had already bounced more off their 20-day low made money slightly *less* often. Backtest A with and without the bounce check (and with a smaller bounce, e.g. 2%).
- **Let Strategy A pick by chance of profit** instead of deepest drop first. Needs the model to be trained only on data before each backtest day, so the test is fair.
- **Fell more than its sector:** only buy (or rank higher) stocks that fell much more than their sector, which points to a company-specific sale rather than a sector-wide slump.
- **Which helped A more: buy sizing or crash mode?** Both shipped together (A went from +286% to +343% in the US backtest). Run each on its own.
- **Strategy B's cooldown when it can't afford a stock:** B starts the 90-day wait even on days it had no cash to buy. Try only starting the wait when B actually buys.

## Ideas for the live bot only (no past data available)

- **Analyst opinion trend:** require that analysts' ratings aren't getting worse (Yahoo has the current trend for free).
- **Insider buying:** rank higher when company executives have recently bought shares themselves.

## Data quality and reliability

- **Check Yahoo prices against another source.** The first scan had Nvidia at $125.53 on Nov 20, 2026; the latest close found elsewhere was $150.96 on Nov 18. Not confirmed either way.
- **Backtest results move between runs** (US Strategy A went from +343% to +408% with no rule change), most likely because Yahoo returns slightly different data each time. Try saving the downloaded prices so reruns are comparable.
- **Backtests use today's index members** (survivorship bias), which flatters results, especially on the ASX. Look for historical ASX 200 / S&P 500 membership lists.
- **6 ASX 200 stocks had no Yahoo data** in the first scan (194 of 200). Check their ticker symbols.
- **Scans started by a code push don't see the newest model.** The workflow checks out the commit that triggered it, not the latest `main`. Consider `ref: main` in the checkout step so they always use the latest data.

## Done

- **Nov 21, 2026:** On sale list ranked by estimated chance of profit (`tracker/model.py`).
- **Nov 21, 2026:** ASX 200 added, with its own scans, backtest and US / ASX switch.
- **Nov 21, 2026:** Strategy B buys the biggest discounts first, not alphabetically.
- **Nov 21, 2026:** Strategy A: buys sized at 2.5% of its account; 10 buys a week when the market is 20%+ down.
- **Nov 21, 2026:** Strategy A rebuilt: $100k budget plus profits, stricter checks, +25% / −20% / 2-year sells.
- **Nov 21, 2026:** Stocks with no price on the latest day are skipped (the SanDisk bug).
