"""All tunable settings in one place. Edit these to change how the bot behaves."""

# --- What counts as "on sale" (all four checks must pass) -------------------
MIN_DROP_FROM_HIGH = 0.20      # 1. price at least 20% below its 52-week high
SMA_DAYS = 200                 # 2. price below its 200-day average
PE_DISCOUNT_VS_SECTOR = 0.15   # 3. P/E at least 15% below its sector's median P/E
REQUIRE_POSITIVE_FCF = True    # 4. profitable (EPS > 0) and positive free cash flow

COOLDOWN_DAYS = 90             # buy any one stock at most once per 90 days

# --- Benchmarks (ETFs that track the key indexes) ----------------------------
BENCHMARKS = {
    "SPY": "S&P 500",
    "QQQ": "Nasdaq-100",
    "DIA": "Dow Jones",
}

# --- Strategy A: fixed dollars per signal ------------------------------------
FIXED_AMOUNT = 1_000.0         # invest $1,000 every time a stock goes on sale

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
