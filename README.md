# S&P 500 Sale Tracker

A bot that scans every S&P 500 stock each weekday after the market closes, flags companies that are **on sale**, and runs two simulated portfolios against the S&P 500 (SPY), Nasdaq-100 (QQQ) and Dow (DIA). Results show up in a phone app you add to your home screen.

Everything runs free on GitHub. Your phone and computer don't need to be on.

> This is a learning tool, not financial advice. Simulated results ignore fees and taxes, and past performance doesn't predict future returns.

## When is a stock "on sale"?

All four checks must pass at the same time:

1. At least **20% below its 52-week high**
2. **Below its 200-day average price**
3. **P/E at least 15% below its sector's median P/E**
4. **Profitable with positive free cash flow**

Any one stock is bought at most once every 90 days. You can change every number in [`tracker/config.py`](tracker/config.py).

## The two simulated strategies

- **A · Choosy:** $100,000 in cash, and it only ever spends that plus money from its sales (so profits are reinvested). Each buy is $2,500, at most 5 new buys a week, biggest discounts first. On top of the four checks, a stock must have **stopped falling** (at least 5% above its lowest close of the past 20 trading days). A stock that has **collapsed** (60%+ below its high) must also pass a **recovery check**: price back above its 50-day average, sales not shrinking more than 10% a year, a positive operating margin, a current ratio of at least 1, and debt no more than 2× equity. A holding is sold at +25%, at −20%, or after 2 years.
- **B · Buys every sale:** $100,000 in cash. Each buy is $5,000, on every stock that goes on sale while cash lasts. A holding is sold when it's up 25% or after 2 years.

Both are compared with putting $100,000 into each index on day one.

## One-time setup (about 10 minutes, all doable on a phone)

1. **Turn on the app's web address:** in this repository go to **Settings → Pages**. Under *Build and deployment*, set **Source = Deploy from a branch**, **Branch = `main`**, folder **`/docs`**, then tap **Save**. After a minute or two the app is live at `https://YOUR-USERNAME.github.io/stock-sale-tracker/`.
2. **Let the bot save its results:** go to **Settings → Actions → General → Workflow permissions**, choose **Read and write permissions**, and tap **Save**.
3. **Run the first scan:** go to **Actions → Daily scan → Run workflow**. It takes 10–20 minutes the first time, because it downloads the financials for 500 companies. After that it runs on its own every weekday at 2:20 PM Pacific.
4. **Run the backtest:** go to **Actions → Backtest → Run workflow**. This tests the rules on the last 10 years and refreshes itself every Saturday.
5. **Add the app to your home screen:** open the app address in Safari (iPhone) or Chrome (Android), then tap **Share → Add to Home Screen** (iPhone) or **⋮ → Add to Home screen** (Android).

### Optional: push notifications for new sales

1. Install the free **ntfy** app ([iPhone](https://apps.apple.com/app/ntfy/id1625396347) / [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy)).
2. Make up a hard-to-guess topic name, like `sale-tracker-7f3k9q2`. Anyone who knows the name can read the alerts, so treat it like a password. In ntfy, tap **+** and subscribe to that topic.
3. In this repository, go to **Settings → Secrets and variables → Actions → New repository secret**. Set the name to `NTFY_TOPIC` and the value to your topic name.

You'll then get an alert whenever a stock newly goes on sale.

## Good to know

- **Data source:** Yahoo Finance, through the free `yfinance` library. Prices are adjusted for splits and dividends, so the comparisons include dividends. Yahoo occasionally rate-limits; if a run fails, run it again from the Actions tab.
- **The backtest is less strict than the live bot.** Free data has no history of company financials, so the backtest uses only checks 1 and 2, plus Strategy A's price-based checks (the bounce, and the 50-day average part of the recovery check). It also uses today's S&P 500 members, which makes past results look somewhat better than they really were.
- **GitHub pauses scheduled jobs in repositories with no activity for 60 days.** The bot's daily commits normally count as activity. If the scans ever stop, open **Actions** and re-enable the workflow.
- **To start the simulation over,** delete `cache/portfolio_state.json` and run the daily scan.
- **Changing the bot's code re-runs it.** Any change under `tracker/` (including `config.py`) automatically re-runs the daily scan and the backtest, so the app reflects the new rules about 15 minutes later.

## Files

| Path | What it does |
|---|---|
| `tracker/config.py` | Every rule and setting |
| `tracker/data.py` | Downloads prices, the S&P 500 list and financials; sends alerts |
| `tracker/signals.py` | The four "on sale" checks |
| `tracker/portfolio.py` | The simulated portfolios |
| `tracker/run_daily.py` | The daily job |
| `tracker/backtest.py` | The 10-year backtest |
| `docs/` | The phone app (GitHub Pages serves this folder) |
| `.github/workflows/` | The schedules that run the bot |
| `tests/test_offline.py` | Checks the logic on simulated prices: `python -m tests.test_offline` |
