"""All tunable settings in one place. Edit these to change how the bot behaves."""

# --- What counts as "on sale" (all four checks must pass) -------------------
MIN_DROP_FROM_HIGH = 0.20      # 1. price at least 20% below its 52-week high
SMA_DAYS = 200                 # 2. price below its 200-day average
PE_DISCOUNT_VS_SECTOR = 0.15   # 3. P/E at least 15% below its sector's median P/E
REQUIRE_POSITIVE_FCF = True    # 4. profitable (EPS > 0) and positive free cash flow

COOLDOWN_DAYS = 90             # buy any one stock at most once per 90 days

# --- Markets ----------------------------------------------------------------------
# Each market has its own stock list, benchmark funds (ETFs, so dividends are included)
# and output folder. The first benchmark is the market's main index: it's what Strategy
# A watches for crash mode. All rules and dollar amounts are the same in every market,
# in that market's currency.
MARKETS = {
    "us": {
        "name": "S&P 500", "currency": "US$", "dir": "",
        "benchmarks": {"SPY": "S&P 500", "QQQ": "Nasdaq-100", "DIA": "Dow Jones"},
    },
    "asx": {
        "name": "ASX 200", "currency": "A$", "dir": "asx",
        "benchmarks": {"STW.AX": "ASX 200", "SFY.AX": "ASX 50", "ISO.AX": "Small Ords"},
    },
}
BENCHMARKS = MARKETS["us"]["benchmarks"]   # kept for older code paths

# --- Strategy A: choosy, $100k budget, profits recycled ----------------------
# A only ever spends its starting cash plus money from sales (profits included).
A_START_BALANCE = 100_000.0
A_POSITION_PCT = 0.025         # each buy is 2.5% of A's current value (cash + holdings),
                               #   so buys grow as the account grows ($2,500 at the start)
A_MIN_POSITION = 1_000.0       # skip a buy if less cash than this is left
A_TAKE_PROFIT = 0.25           # sell when a holding is up 25%
A_STOP_LOSS = 0.20             # ...or down 20%
A_MAX_HOLD_DAYS = 730          # ...or after 2 years, whichever comes first
A_MAX_BUYS_PER_WEEK = 5        # at most 5 new buys a week, deepest discounts first
A_CRASH_DROP = 0.20            # when the S&P 500 (SPY) itself is 20%+ off its high...
A_CRASH_BUYS_PER_WEEK = 10     # ...allow up to 10 buys a week instead

# Extra checks a stock must pass (on top of the four above) before A buys it
A_BOUNCE_DAYS = 20             # "stopped falling": price at least 5% above
A_BOUNCE_FROM_LOW = 0.05       #   its lowest close of the past 20 trading days

# Collapsed stocks (60%+ below their high) must also pass a recovery check:
COLLAPSE_DROP = 0.60
RECOVERY_SMA_DAYS = 50                 # price back above its 50-day average
RECOVERY_MIN_REVENUE_GROWTH = -0.10    # sales not shrinking more than 10% a year
RECOVERY_MIN_OPERATING_MARGIN = 0.0    # core business still makes money
RECOVERY_MIN_CURRENT_RATIO = 1.0       # can cover its bills for the next year
RECOVERY_MAX_DEBT_TO_EQUITY = 200.0    # debt at most 2x equity (Yahoo reports this in %)
# (Current ratio and debt are skipped when Yahoo doesn't report them, e.g. for banks.)

# --- Strategy B: starting balance with buy/sell rules ------------------------
START_BALANCE = 100_000.0
POSITION_PCT = 0.05            # each buy = 5% of the starting balance ($5,000)
MIN_POSITION = 1_000.0         # skip a buy if less cash than this is left
TAKE_PROFIT = 0.25             # sell when a position is up 25%
MAX_HOLD_DAYS = 730            # ...or after 2 years, whichever comes first

# --- Backtest -----------------------------------------------------------------
BACKTEST_YEARS = 10

# --- Housekeeping ---------------------------------------------------------------
FUNDAMENTALS_MAX_AGE_DAYS = 7  # re-download company financials weekly
NEAR_MISS_LIMIT = 25           # how many "3 of 4 checks" stocks to show
