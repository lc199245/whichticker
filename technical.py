"""Technical indicators computed on the price ratio series."""

import numpy as np
import pandas as pd
from config import RSI_PERIOD, MACD_FAST, MACD_SLOW, MACD_SIGNAL, BB_PERIOD, BB_STD


def _safe_list(series: pd.Series) -> list:
    """Convert pandas Series to JSON-safe list (NaN → None)."""
    return [round(float(v), 4) if not np.isnan(v) else None for v in series]


# ── RSI ──────────────────────────────────────────────────────────────────────

def compute_rsi(series: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    """
    Relative Strength Index using Wilder's smoothing.
    """
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


# ── MACD ─────────────────────────────────────────────────────────────────────

def compute_macd(
    series: pd.Series,
    fast: int = MACD_FAST,
    slow: int = MACD_SLOW,
    signal: int = MACD_SIGNAL,
) -> dict:
    """
    MACD = fast EMA - slow EMA.
    Signal = EMA of MACD.
    Histogram = MACD - Signal.
    """
    ema_fast   = series.ewm(span=fast, adjust=False).mean()
    ema_slow   = series.ewm(span=slow, adjust=False).mean()
    macd_line  = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram  = macd_line - signal_line

    return {
        "macd_line":   macd_line,
        "signal_line": signal_line,
        "histogram":   histogram,
    }


# ── Bollinger Bands ──────────────────────────────────────────────────────────

def compute_bollinger_bands(
    series: pd.Series,
    period: int = BB_PERIOD,
    std_dev: int = BB_STD,
) -> dict:
    """
    Bollinger Bands on the ratio.
    Middle = SMA, Upper/Lower = SMA +/- std_dev * rolling_std.
    """
    middle = series.rolling(window=period).mean()
    rolling_std = series.rolling(window=period).std()
    upper = middle + std_dev * rolling_std
    lower = middle - std_dev * rolling_std

    return {
        "upper":  upper,
        "middle": middle,
        "lower":  lower,
    }


# ── Individual RSI for Comparison ─────────────────────────────────────────────

def compute_individual_rsi(prices_a: pd.Series, prices_b: pd.Series) -> dict:
    """
    Compute RSI on each individual ticker for side-by-side comparison.
    """
    rsi_a = compute_rsi(prices_a)
    rsi_b = compute_rsi(prices_b)

    current_rsi_a = float(rsi_a.dropna().iloc[-1]) if len(rsi_a.dropna()) > 0 else None
    current_rsi_b = float(rsi_b.dropna().iloc[-1]) if len(rsi_b.dropna()) > 0 else None

    return {
        "rsi_a": _safe_list(rsi_a),
        "rsi_b": _safe_list(rsi_b),
        "current_rsi_a": round(current_rsi_a, 1) if current_rsi_a is not None else None,
        "current_rsi_b": round(current_rsi_b, 1) if current_rsi_b is not None else None,
    }


# ── Technical Confirmation Signal ────────────────────────────────────────────

def technical_confirmation(rsi: pd.Series, macd: dict, ratio: pd.Series, bb: dict) -> dict:
    """
    Determine whether technical indicators confirm the relative performance signal.

    FAVORS_A (ratio bullish) if:
      - RSI > 50 on ratio (A gaining strength relative to B)
      - MACD histogram positive (upward momentum on ratio)
      - Ratio near/above upper Bollinger Band (A strongly outperforming)

    FAVORS_B (ratio bearish) if:
      - RSI < 50 on ratio
      - MACD histogram negative
      - Ratio near/below lower Bollinger Band (B strongly outperforming)
    """
    latest_rsi = rsi.dropna().iloc[-1] if len(rsi.dropna()) > 0 else 50
    latest_hist = macd["histogram"].dropna().iloc[-1] if len(macd["histogram"].dropna()) > 0 else 0
    latest_ratio = ratio.dropna().iloc[-1] if len(ratio.dropna()) > 0 else 0
    latest_upper = bb["upper"].dropna().iloc[-1] if len(bb["upper"].dropna()) > 0 else 0
    latest_lower = bb["lower"].dropna().iloc[-1] if len(bb["lower"].dropna()) > 0 else 0
    latest_middle = bb["middle"].dropna().iloc[-1] if len(bb["middle"].dropna()) > 0 else 0

    favors_a_count = 0
    favors_b_count = 0
    signals = []

    # RSI on ratio
    if latest_rsi > 60:
        favors_a_count += 1
        signals.append(f"Ratio RSI strong ({latest_rsi:.0f} > 60)")
    elif latest_rsi < 40:
        favors_b_count += 1
        signals.append(f"Ratio RSI weak ({latest_rsi:.0f} < 40)")
    elif latest_rsi > 50:
        favors_a_count += 0.5
        signals.append(f"Ratio RSI slightly bullish ({latest_rsi:.0f})")
    else:
        favors_b_count += 0.5
        signals.append(f"Ratio RSI slightly bearish ({latest_rsi:.0f})")

    # MACD
    if latest_hist > 0:
        favors_a_count += 1
        signals.append("MACD histogram positive (A momentum)")
    elif latest_hist < 0:
        favors_b_count += 1
        signals.append("MACD histogram negative (B momentum)")

    # Bollinger Band position
    if latest_ratio >= latest_upper:
        favors_a_count += 1
        signals.append("Ratio at/above upper Bollinger Band")
    elif latest_ratio <= latest_lower:
        favors_b_count += 1
        signals.append("Ratio at/below lower Bollinger Band")
    elif latest_ratio > latest_middle:
        signals.append("Ratio above BB middle (leaning A)")
    else:
        signals.append("Ratio below BB middle (leaning B)")

    if favors_a_count >= 2:
        direction = "FAVORS_A"
    elif favors_b_count >= 2:
        direction = "FAVORS_B"
    else:
        direction = "NEUTRAL"

    return {
        "direction":      direction,
        "favors_a_count": round(favors_a_count, 1),
        "favors_b_count": round(favors_b_count, 1),
        "signals":        signals,
        "rsi_value":      round(float(latest_rsi), 1),
        "macd_hist":      round(float(latest_hist), 4),
    }


# ── Master Function ──────────────────────────────────────────────────────────

def compute_all_technicals(ratio: pd.Series) -> dict:
    """
    Compute all technical indicators on the price ratio and return
    a JSON-serializable dict.
    """
    rsi  = compute_rsi(ratio)
    macd = compute_macd(ratio)
    bb   = compute_bollinger_bands(ratio)

    confirmation = technical_confirmation(rsi, macd, ratio, bb)

    return {
        "rsi": {
            "values": _safe_list(rsi),
        },
        "macd": {
            "macd_line":   _safe_list(macd["macd_line"]),
            "signal_line": _safe_list(macd["signal_line"]),
            "histogram":   _safe_list(macd["histogram"]),
        },
        "bollinger": {
            "upper":  _safe_list(bb["upper"]),
            "middle": _safe_list(bb["middle"]),
            "lower":  _safe_list(bb["lower"]),
        },
        "confirmation": confirmation,
    }
