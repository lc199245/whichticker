"""Core relative performance analysis engine."""

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import coint, adfuller
from config import (
    RATIO_MA_SHORT, RATIO_MA_LONG, RATIO_ZSCORE_WINDOW,
    MOMENTUM_WINDOW, RELATIVE_RETURN_PERIODS,
)


# ── Price Ratio ───────────────────────────────────────────────────────────────

def compute_price_ratio(prices_a: pd.Series, prices_b: pd.Series) -> pd.Series:
    """
    Price ratio = A / B.  A rising ratio means A is outperforming B.
    Guards against division by zero / inf.
    """
    ratio = prices_a / prices_b
    ratio = ratio.replace([np.inf, -np.inf], np.nan)
    return ratio


# ── Cumulative Returns ────────────────────────────────────────────────────────

def compute_returns(prices: pd.Series) -> pd.Series:
    """Cumulative percentage return from the start of the series."""
    return ((prices / prices.iloc[0]) - 1) * 100


# ── Relative Returns over Standard Periods ────────────────────────────────────

def compute_relative_returns(prices_a: pd.Series, prices_b: pd.Series) -> dict:
    """
    Compute return differentials over 1mo, 3mo, 6mo windows.
    Returns dict keyed by period label.
    """
    result = {}
    n = len(prices_a)

    for label, days in RELATIVE_RETURN_PERIODS.items():
        if n < days + 1:
            result[label] = {"return_a": None, "return_b": None, "differential": None}
            continue

        ret_a = float((prices_a.iloc[-1] / prices_a.iloc[-days] - 1) * 100)
        ret_b = float((prices_b.iloc[-1] / prices_b.iloc[-days] - 1) * 100)

        result[label] = {
            "return_a":     round(ret_a, 2),
            "return_b":     round(ret_b, 2),
            "differential": round(ret_a - ret_b, 2),
        }

    return result


# ── Ratio Momentum (Rate of Change) ──────────────────────────────────────────

def compute_ratio_momentum(ratio: pd.Series, window: int = MOMENTUM_WINDOW) -> dict:
    """
    Rate of Change on the price ratio:  (ratio / ratio[t-window] - 1) * 100
    Also computes a linear slope over the window for direction determination.
    """
    roc = ((ratio / ratio.shift(window)) - 1) * 100
    roc = roc.replace([np.inf, -np.inf], np.nan)

    current_roc = float(roc.dropna().iloc[-1]) if len(roc.dropna()) > 0 else 0.0

    # Slope via linear regression on last `window` data points
    recent = ratio.dropna().values[-window:] if len(ratio.dropna()) >= window else ratio.dropna().values
    if len(recent) >= 5:
        x = np.arange(len(recent))
        slope = float(np.polyfit(x, recent, 1)[0])
    else:
        slope = 0.0

    direction = "UP" if slope > 0 else ("DOWN" if slope < 0 else "FLAT")

    return {
        "roc_series":    roc,
        "current_roc":   round(current_roc, 2),
        "slope":         round(slope, 6),
        "direction":     direction,
    }


# ── Ratio Moving Averages ────────────────────────────────────────────────────

def compute_ratio_ma(ratio: pd.Series) -> dict:
    """
    50-day and 200-day simple moving averages on the price ratio.
    Returns series + current values + above/below flags.
    """
    ma_short = ratio.rolling(window=RATIO_MA_SHORT).mean()
    ma_long  = ratio.rolling(window=RATIO_MA_LONG).mean()

    current_ratio = float(ratio.dropna().iloc[-1]) if len(ratio.dropna()) > 0 else None

    cur_short = float(ma_short.dropna().iloc[-1]) if len(ma_short.dropna()) > 0 else None
    cur_long  = float(ma_long.dropna().iloc[-1])  if len(ma_long.dropna()) > 0 else None

    above_short = bool(current_ratio > cur_short) if (current_ratio is not None and cur_short is not None) else None
    above_long  = bool(current_ratio > cur_long)  if (current_ratio is not None and cur_long is not None) else None

    return {
        "ma_short_series": ma_short,
        "ma_long_series":  ma_long,
        "current_ratio":   round(current_ratio, 4) if current_ratio else None,
        "ma_short":        round(cur_short, 4) if cur_short else None,
        "ma_long":         round(cur_long, 4) if cur_long else None,
        "above_ma_short":  above_short,
        "above_ma_long":   above_long,
    }


# ── Z-Score ──────────────────────────────────────────────────────────────────

def compute_zscore(series: pd.Series, window: int = RATIO_ZSCORE_WINDOW) -> pd.Series:
    """Rolling z-score: (value - rolling_mean) / rolling_std."""
    rolling_mean = series.rolling(window=window).mean()
    rolling_std  = series.rolling(window=window).std()
    return (series - rolling_mean) / rolling_std


# ── Cointegration ────────────────────────────────────────────────────────────

def cointegration_test(prices_a: pd.Series, prices_b: pd.Series) -> dict:
    """Engle-Granger two-step cointegration test."""
    try:
        stat, pvalue, crit = coint(prices_a.values, prices_b.values)
        return {
            "test_stat":       round(float(stat), 4),
            "p_value":         round(float(pvalue), 4),
            "critical_1pct":   round(float(crit[0]), 4),
            "critical_5pct":   round(float(crit[1]), 4),
            "critical_10pct":  round(float(crit[2]), 4),
            "is_cointegrated": bool(pvalue < 0.05),
        }
    except Exception as e:
        return {
            "test_stat": None, "p_value": None,
            "critical_1pct": None, "critical_5pct": None, "critical_10pct": None,
            "is_cointegrated": False, "error": str(e),
        }


# ── Correlation ──────────────────────────────────────────────────────────────

def compute_correlation(prices_a: pd.Series, prices_b: pd.Series) -> dict:
    """Pearson correlation and rolling 60-day correlation."""
    corr = float(prices_a.corr(prices_b))
    rolling_corr = prices_a.rolling(60).corr(prices_b)
    return {
        "pearson":        round(corr, 4),
        "rolling_60d":    [round(float(v), 4) if not np.isnan(v) else None for v in rolling_corr],
    }


# ── Spread Stability (ADF on ratio) ──────────────────────────────────────────

def adf_test(series: pd.Series) -> dict:
    """Augmented Dickey-Fuller test on a series."""
    try:
        result = adfuller(series.dropna(), autolag="AIC")
        return {
            "adf_stat":     round(float(result[0]), 4),
            "adf_pvalue":   round(float(result[1]), 4),
            "is_stationary": bool(result[1] < 0.05),
        }
    except Exception:
        return {"adf_stat": None, "adf_pvalue": None, "is_stationary": False}


# ── Hurst Exponent ───────────────────────────────────────────────────────────

def hurst_exponent(series: pd.Series) -> float:
    """
    Estimate Hurst exponent via R/S (rescaled range) method.
    H < 0.5 → mean-reverting, H = 0.5 → random walk, H > 0.5 → trending.
    For relative performance, H > 0.5 is desirable (trends persist).
    """
    ts = series.dropna().values
    n = len(ts)
    if n < 20:
        return float("nan")

    max_k = min(n // 2, 100)
    lags = range(2, max_k)
    rs_values = []

    for lag in lags:
        n_subseries = n // lag
        if n_subseries < 1:
            break
        rs_list = []
        for i in range(n_subseries):
            sub = ts[i * lag : (i + 1) * lag]
            mean_sub = np.mean(sub)
            deviations = np.cumsum(sub - mean_sub)
            r = np.max(deviations) - np.min(deviations)
            s = np.std(sub, ddof=1)
            if s > 0:
                rs_list.append(r / s)
        if rs_list:
            rs_values.append((np.log(lag), np.log(np.mean(rs_list))))

    if len(rs_values) < 5:
        return float("nan")

    log_lags, log_rs = zip(*rs_values)
    poly = np.polyfit(log_lags, log_rs, 1)
    return round(float(poly[0]), 4)


# ── Signal Generation ────────────────────────────────────────────────────────

def generate_signals(
    zscore: pd.Series,
    momentum: dict,
    ma_info: dict,
    tech_confirmation: dict | None = None,
) -> dict:
    """
    Generate relative performance signal from ratio analysis + technicals.

    Uses 6 inputs:
      1. Ratio vs 50d MA
      2. Ratio vs 200d MA
      3. Momentum direction (ROC slope)
      4. RSI on ratio (> 50 favors A, < 50 favors B)
      5. MACD histogram on ratio (positive favors A, negative favors B)
      6. Bollinger Band position

    FAVOR_A: majority of inputs favor A
    FAVOR_B: majority of inputs favor B
    NEUTRAL: mixed signals

    Returns signal direction, strength, and summary.
    """
    current_z = float(zscore.dropna().iloc[-1]) if len(zscore.dropna()) > 0 else 0.0
    mom_dir   = momentum.get("direction", "FLAT")
    above_short = ma_info.get("above_ma_short")
    above_long  = ma_info.get("above_ma_long")

    tech = tech_confirmation or {}

    # Count signals favoring A vs B
    favor_a_count = 0
    favor_b_count = 0
    details = []

    # 1. MA position signals
    if above_short is True:
        favor_a_count += 1
        details.append(f"Ratio above {RATIO_MA_SHORT}d MA")
    elif above_short is False:
        favor_b_count += 1
        details.append(f"Ratio below {RATIO_MA_SHORT}d MA")

    if above_long is True:
        favor_a_count += 1
        details.append(f"Ratio above {RATIO_MA_LONG}d MA")
    elif above_long is False:
        favor_b_count += 1
        details.append(f"Ratio below {RATIO_MA_LONG}d MA")

    # 2. Momentum
    if mom_dir == "UP":
        favor_a_count += 1
        details.append("Momentum positive (ratio rising)")
    elif mom_dir == "DOWN":
        favor_b_count += 1
        details.append("Momentum negative (ratio falling)")

    # 3. RSI on ratio
    rsi_val = tech.get("rsi_value")
    if rsi_val is not None:
        if rsi_val > 60:
            favor_a_count += 1
            details.append(f"RSI strong at {rsi_val:.0f} (favors A)")
        elif rsi_val < 40:
            favor_b_count += 1
            details.append(f"RSI weak at {rsi_val:.0f} (favors B)")
        elif rsi_val > 50:
            favor_a_count += 0.5
            details.append(f"RSI leaning bullish ({rsi_val:.0f})")
        else:
            favor_b_count += 0.5
            details.append(f"RSI leaning bearish ({rsi_val:.0f})")

    # 4. MACD histogram on ratio
    macd_hist = tech.get("macd_hist")
    if macd_hist is not None:
        if macd_hist > 0:
            favor_a_count += 1
            details.append("MACD positive (A momentum)")
        elif macd_hist < 0:
            favor_b_count += 1
            details.append("MACD negative (B momentum)")

    # Z-score extremes (informational, not scored)
    if current_z > 1.5:
        details.append("Ratio z-score elevated — A may be extended")
    elif current_z < -1.5:
        details.append("Ratio z-score depressed — B may be extended")

    # Determine direction — need majority of scored inputs
    total_inputs = favor_a_count + favor_b_count
    max_possible = 5  # 2 MAs + momentum + RSI + MACD

    if favor_a_count >= 3 and favor_a_count > favor_b_count:
        direction = "FAVOR_A"
        strength = min(favor_a_count / max_possible, 1.0)
        detail = "A is outperforming B — " + "; ".join(details)
    elif favor_b_count >= 3 and favor_b_count > favor_a_count:
        direction = "FAVOR_B"
        strength = min(favor_b_count / max_possible, 1.0)
        detail = "B is outperforming A — " + "; ".join(details)
    elif favor_a_count >= 2 and favor_a_count > favor_b_count:
        direction = "FAVOR_A"
        strength = min(favor_a_count / max_possible, 1.0)
        detail = "A slightly outperforming B — " + "; ".join(details)
    elif favor_b_count >= 2 and favor_b_count > favor_a_count:
        direction = "FAVOR_B"
        strength = min(favor_b_count / max_possible, 1.0)
        detail = "B slightly outperforming A — " + "; ".join(details)
    else:
        direction = "NEUTRAL"
        strength = 0.0
        detail = "No clear outperformance trend — " + "; ".join(details) if details else "Insufficient data for signal"

    return {
        "direction":       direction,
        "current_zscore":  round(current_z, 4),
        "strength":        round(float(strength), 2),
        "detail":          detail,
        "favor_a_count":   round(favor_a_count, 1),
        "favor_b_count":   round(favor_b_count, 1),
    }


# ── Master Orchestrator ─────────────────────────────────────────────────────

def run_full_analysis(
    prices_a: pd.Series,
    prices_b: pd.Series,
    tech_confirmation: dict | None = None,
) -> dict:
    """
    Run the complete relative performance analysis pipeline.

    Parameters
    ----------
    prices_a, prices_b : aligned price series
    tech_confirmation  : optional dict from technical_confirmation()
                         (RSI, MACD, BB on the ratio) — fed into signal generation
    """

    # 1. Price ratio
    ratio = compute_price_ratio(prices_a, prices_b)

    # 2. Moving averages on ratio
    ma_info = compute_ratio_ma(ratio)

    # 3. Z-score on ratio
    zscore = compute_zscore(ratio)

    # 4. Momentum
    momentum = compute_ratio_momentum(ratio)

    # 5. Cumulative returns
    returns_a = compute_returns(prices_a)
    returns_b = compute_returns(prices_b)

    # 6. Relative returns (1mo, 3mo, 6mo)
    rel_returns = compute_relative_returns(prices_a, prices_b)

    # 7. Correlation
    corr = compute_correlation(prices_a, prices_b)

    # 8. ADF on ratio (is ratio stationary or trending?)
    adf = adf_test(ratio)

    # 9. Hurst on ratio
    hurst = hurst_exponent(ratio)

    # 10. Cointegration (still useful context)
    coint_result = cointegration_test(prices_a, prices_b)

    # 11. Signals (now includes RSI + MACD from technicals)
    signals = generate_signals(zscore, momentum, ma_info, tech_confirmation)

    # Serialize for charting
    dates = [d.strftime("%Y-%m-%d") for d in ratio.index]

    def _safe_list(s):
        return [round(float(v), 4) if not np.isnan(v) else None for v in s]

    ratio_vals   = _safe_list(ratio)
    zscore_vals  = _safe_list(zscore)
    ma_short_vals = _safe_list(ma_info["ma_short_series"])
    ma_long_vals  = _safe_list(ma_info["ma_long_series"])
    returns_a_vals = _safe_list(returns_a)
    returns_b_vals = _safe_list(returns_b)
    corr_rolling = corr.pop("rolling_60d")

    return {
        "statistics": {
            "current_ratio":      ma_info["current_ratio"],
            "ratio_ma_50":        ma_info["ma_short"],
            "ratio_ma_200":       ma_info["ma_long"],
            "ratio_above_ma_50":  ma_info["above_ma_short"],
            "ratio_above_ma_200": ma_info["above_ma_long"],
            "momentum_roc":       momentum["current_roc"],
            "momentum_direction": momentum["direction"],
            "relative_returns":   rel_returns,
            "correlation":        corr["pearson"],
            "hurst_exponent":     hurst,
            "adf_pvalue":         adf["adf_pvalue"],
            "is_stationary":      adf["is_stationary"],
            "current_zscore":     signals["current_zscore"],
            "cointegration":      coint_result,
        },
        "ratio": {
            "dates":  dates,
            "values": ratio_vals,
            "ma_50":  ma_short_vals,
            "ma_200": ma_long_vals,
        },
        "zscore": {
            "dates":  dates,
            "values": zscore_vals,
        },
        "returns": {
            "dates":     dates,
            "returns_a": returns_a_vals,
            "returns_b": returns_b_vals,
        },
        "correlation_rolling": {
            "dates":  dates,
            "values": corr_rolling,
        },
        "signal": signals,
    }
