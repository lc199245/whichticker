"""Configuration for WhichTicker — Relative Performance Analyzer."""

import os

# ── Load .env ────────────────────────────────────────────────────────────────
def _load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, val = line.partition("=")
                        val = val.strip().strip('"').strip("'")
                        key = key.strip()
                        if val:  # Only set if value is non-empty
                            os.environ[key] = val
    except Exception:
        pass

_load_env()

# ── Anthropic API ────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = "claude-haiku-4-5"

# ── Lookback Options ─────────────────────────────────────────────────────────
DEFAULT_LOOKBACK = "1y"
LOOKBACK_OPTIONS = {
    "1mo": "1 Month",
    "3mo": "3 Months",
    "6mo": "6 Months",
    "1y":  "1 Year",
    "2y":  "2 Years",
    "5y":  "5 Years",
}

# ── Ratio / Relative Performance Parameters ──────────────────────────────────
RATIO_MA_SHORT = 50       # short moving average on price ratio
RATIO_MA_LONG  = 200      # long moving average on price ratio
RATIO_ZSCORE_WINDOW = 20  # rolling window for z-score of ratio
MOMENTUM_WINDOW = 20      # lookback for momentum (rate of change)
RELATIVE_RETURN_PERIODS = {   # periods for return differential comparison
    "1mo": 21,
    "3mo": 63,
    "6mo": 126,
}

# ── Technical Indicator Parameters ───────────────────────────────────────────
RSI_PERIOD   = 14
MACD_FAST    = 12
MACD_SLOW    = 26
MACD_SIGNAL  = 9
BB_PERIOD    = 20
BB_STD       = 2

# ── Server ───────────────────────────────────────────────────────────────────
HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "8060"))  # Railway sets PORT dynamically
