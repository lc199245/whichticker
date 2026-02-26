"""FastAPI application — WhichTicker: Relative Performance Analyzer."""

import os
import math
import asyncio

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import uvicorn

from config import HOST, PORT, LOOKBACK_OPTIONS
from market_data import fetch_pair_data, validate_ticker, get_price_series, search_tickers
from analysis import run_full_analysis, compute_price_ratio
from technical import compute_all_technicals, compute_individual_rsi
from ai_signal import get_ai_recommendation

# ── App Setup ────────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="WhichTicker")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# ── Request Models ───────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    ticker_a: str
    ticker_b: str
    period: str = "1y"


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Serve the main dashboard page."""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "lookback_options": LOOKBACK_OPTIONS,
    })


@app.post("/api/analyze")
async def api_analyze(body: AnalyzeRequest):
    """
    Full relative performance analysis pipeline.

    1. Fetch & align price data for both tickers
    2. Run ratio-based statistical analysis (MAs, momentum, z-score, etc.)
    3. Compute technical indicators on the price ratio
    4. Get AI recommendation from Claude
    5. Return comprehensive JSON
    """
    ticker_a = body.ticker_a.strip().upper()
    ticker_b = body.ticker_b.strip().upper()
    period   = body.period if body.period in LOOKBACK_OPTIONS else "1y"

    if not ticker_a or not ticker_b:
        return JSONResponse({"error": "Both tickers are required."}, status_code=400)
    if ticker_a == ticker_b:
        return JSONResponse({"error": "Tickers must be different."}, status_code=400)

    try:
        # 1. Fetch price data (run in thread to not block event loop)
        result = await asyncio.to_thread(fetch_pair_data, ticker_a, ticker_b, period)

        # fetch_pair_data returns (None, error_string) on failure
        if result[0] is None:
            error_msg = result[1] if len(result) > 1 else "Unknown error fetching data."
            return JSONResponse({"error": error_msg}, status_code=400)

        df_a, df_b = result
        prices_a = df_a["close"]
        prices_b = df_b["close"]

        # Also fetch full chart data for individual price charts
        chart_a = await asyncio.to_thread(get_price_series, ticker_a, period)
        chart_b = await asyncio.to_thread(get_price_series, ticker_b, period)

        # 2. Technical indicators on the price ratio (computed first so we can feed into signals)
        ratio_series = compute_price_ratio(prices_a, prices_b)
        technicals = await asyncio.to_thread(compute_all_technicals, ratio_series)

        # 3. Statistical analysis (ratio-based) — now includes tech confirmation in signal
        analysis = await asyncio.to_thread(
            run_full_analysis, prices_a, prices_b, technicals.get("confirmation")
        )

        # 3b. Individual RSI for comparison
        individual_rsi = await asyncio.to_thread(compute_individual_rsi, prices_a, prices_b)

        # 4. AI recommendation
        ai_rec = await get_ai_recommendation(
            ticker_a, ticker_b,
            analysis["statistics"],
            technicals,
            analysis["signal"],
        )

        # 5. Combine signal: stat + technical + AI
        combined_conviction = _compute_conviction(analysis, technicals, ai_rec)

        payload = _sanitize({
            "ticker_a": chart_a or {"symbol": ticker_a, "name": ticker_a, "dates": [], "prices": []},
            "ticker_b": chart_b or {"symbol": ticker_b, "name": ticker_b, "dates": [], "prices": []},
            "statistics":          analysis["statistics"],
            "ratio":               analysis["ratio"],
            "zscore":              analysis["zscore"],
            "returns":             analysis["returns"],
            "correlation_rolling": analysis["correlation_rolling"],
            "technicals":          technicals,
            "individual_rsi":      individual_rsi,
            "signal":              analysis["signal"],
            "ai_recommendation":   ai_rec,
            "combined":            combined_conviction,
        })

        return JSONResponse(payload)

    except Exception as e:
        print(f"  Analysis error ({ticker_a} / {ticker_b}): {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": f"Analysis failed: {str(e)}"}, status_code=500)


@app.get("/api/validate/{ticker}")
async def api_validate(ticker: str):
    """Check if a ticker is valid."""
    info = await asyncio.to_thread(validate_ticker, ticker.strip().upper())
    if info:
        return JSONResponse(info)
    return JSONResponse({"error": f"Ticker '{ticker}' not found."}, status_code=404)


@app.get("/api/search")
async def api_search(q: str = ""):
    """Search for tickers matching a query string."""
    query = q.strip()
    if len(query) < 1:
        return JSONResponse({"results": []})
    results = await asyncio.to_thread(search_tickers, query)
    return JSONResponse({"results": results})


# ── Helpers ──────────────────────────────────────────────────────────────────

def _sanitize(obj):
    """Recursively replace NaN / Inf / -Inf with None so JSONResponse won't crash."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj


def _compute_conviction(analysis: dict, technicals: dict, ai_rec: dict) -> dict:
    """
    Combine statistical, technical, and AI signals into a 0-100 conviction score.

    Granular scoring with continuous values — not just binary pass/fail.

    Statistical (40 pts max):
      1. Ratio vs 50d MA  (0-10)  — distance from MA adds granularity
      2. Ratio vs 200d MA (0-10)  — distance from MA adds granularity
      3. Momentum ROC     (0-10)  — magnitude matters
      4. Return diff      (0-10)  — size of differential matters

    Technical (30 pts max):
      5. RSI on ratio     (0-10)  — distance from 50 adds granularity
      6. MACD histogram   (0-10)  — magnitude matters
      7. Bollinger Band   (0-10)  — position within band

    Context (30 pts max):
      8.  Correlation      (0-10) — higher = more meaningful
      9.  Hurst exponent   (0-10) — distance from 0.5 = persistence
      10. Tech confirms    (0-10) — alignment bonus

    Final = 60% stat/tech score + 40% AI score (when available).
    """
    stat_signal = analysis["signal"]["direction"]
    tech_conf   = technicals.get("confirmation", {})
    tech_dir    = tech_conf.get("direction", "NEUTRAL")
    ai_signal   = ai_rec.get("signal", "N/A")
    ai_conv     = ai_rec.get("conviction", 0)  # now 0-100

    stats = analysis["statistics"]

    def _score_for_direction(favor_a: bool):
        """Score 10 criteria (0-10 each, 100 max) from one direction's perspective."""
        score = 0.0
        above_50  = stats.get("ratio_above_ma_50")
        above_200 = stats.get("ratio_above_ma_200")
        mom_dir   = stats.get("momentum_direction")
        mom_roc   = stats.get("momentum_roc")

        # --- Statistical (4 × 10 = 40 pts) ---

        # 1. 50d MA (0-10): aligned = base 5, plus up to 5 more for distance
        ratio_val = stats.get("current_ratio")
        ma_50_val = stats.get("ratio_ma_50")
        if ratio_val is not None and ma_50_val is not None and ma_50_val != 0:
            pct_from_ma = (ratio_val - ma_50_val) / ma_50_val * 100
            if favor_a and pct_from_ma > 0:
                score += min(10, 5 + min(abs(pct_from_ma) * 2, 5))
            elif not favor_a and pct_from_ma < 0:
                score += min(10, 5 + min(abs(pct_from_ma) * 2, 5))
            elif favor_a and pct_from_ma <= 0:
                score += max(0, 2 - abs(pct_from_ma))  # close but wrong side
            elif not favor_a and pct_from_ma >= 0:
                score += max(0, 2 - abs(pct_from_ma))

        # 2. 200d MA (0-10): same logic, slightly more weight for long-term
        ma_200_val = stats.get("ratio_ma_200")
        if ratio_val is not None and ma_200_val is not None and ma_200_val != 0:
            pct_from_ma = (ratio_val - ma_200_val) / ma_200_val * 100
            if favor_a and pct_from_ma > 0:
                score += min(10, 5 + min(abs(pct_from_ma) * 1.5, 5))
            elif not favor_a and pct_from_ma < 0:
                score += min(10, 5 + min(abs(pct_from_ma) * 1.5, 5))
            elif favor_a and pct_from_ma <= 0:
                score += max(0, 2 - abs(pct_from_ma))
            elif not favor_a and pct_from_ma >= 0:
                score += max(0, 2 - abs(pct_from_ma))

        # 3. Momentum ROC (0-10): direction match + magnitude
        if mom_roc is not None:
            abs_roc = abs(mom_roc)
            if favor_a and mom_roc > 0:
                score += min(10, 4 + min(abs_roc * 1.5, 6))
            elif not favor_a and mom_roc < 0:
                score += min(10, 4 + min(abs_roc * 1.5, 6))
            elif mom_dir == "FLAT":
                score += 2  # flat = slight ambiguity

        # 4. Return differential (0-10): largest available differential
        rel_ret = stats.get("relative_returns", {})
        best_diff = None
        for period in ["1mo", "3mo", "6mo"]:
            d = rel_ret.get(period, {}).get("differential")
            if d is not None:
                best_diff = d
                break
        if best_diff is not None:
            abs_diff = abs(best_diff)
            if favor_a and best_diff > 0:
                score += min(10, 3 + min(abs_diff * 0.7, 7))
            elif not favor_a and best_diff < 0:
                score += min(10, 3 + min(abs_diff * 0.7, 7))

        # --- Technical (3 × 10 = 30 pts) ---

        # 5. RSI on ratio (0-10): distance from 50
        rsi_val = tech_conf.get("rsi_value")
        if rsi_val is not None:
            rsi_dev = rsi_val - 50  # positive = favors A, negative = favors B
            if favor_a and rsi_dev > 0:
                score += min(10, 3 + min(abs(rsi_dev) * 0.4, 7))
            elif not favor_a and rsi_dev < 0:
                score += min(10, 3 + min(abs(rsi_dev) * 0.4, 7))
            elif abs(rsi_dev) < 5:
                score += 2  # near neutral, slight credit

        # 6. MACD histogram (0-10): sign + magnitude
        macd_hist = tech_conf.get("macd_hist")
        if macd_hist is not None:
            if favor_a and macd_hist > 0:
                score += min(10, 5 + min(abs(macd_hist) * 50, 5))
            elif not favor_a and macd_hist < 0:
                score += min(10, 5 + min(abs(macd_hist) * 50, 5))

        # 7. Bollinger Band / overall tech count (0-10)
        fa = tech_conf.get("favors_a_count", 0)
        fb = tech_conf.get("favors_b_count", 0)
        total_tech = fa + fb if (fa + fb) > 0 else 1
        if favor_a and fa > fb:
            score += min(10, (fa / total_tech) * 10)
        elif not favor_a and fb > fa:
            score += min(10, (fb / total_tech) * 10)
        elif fa == fb and fa > 0:
            score += 3  # tied signals

        # --- Context (3 × 10 = 30 pts) ---

        # 8. Correlation (0-10): higher abs correlation = more meaningful pair
        corr = stats.get("correlation", 0) or 0
        score += min(10, abs(corr) * 10)

        # 9. Hurst exponent (0-10): >0.5 = trending
        hurst = stats.get("hurst_exponent")
        if hurst is not None:
            if hurst > 0.5:
                score += min(10, (hurst - 0.5) * 20)  # 0.5→0, 0.6→2, 0.75→5, 1.0→10
            else:
                score += max(0, hurst * 4)  # some credit for near-0.5

        # 10. Technical direction confirms (0-10): alignment bonus
        target_dir = "FAVORS_A" if favor_a else "FAVORS_B"
        if tech_dir == target_dir:
            score += 10
        elif tech_dir == "NEUTRAL":
            score += 3

        return round(score, 1)

    # Determine final direction
    if stat_signal in ("FAVOR_A", "FAVOR_B"):
        final_direction = stat_signal
    elif ai_signal in ("FAVOR_A", "FAVOR_B"):
        final_direction = ai_signal
    else:
        final_direction = "NEUTRAL"

    # Score from the winning direction's perspective (max 100)
    favor_a = (final_direction == "FAVOR_A")
    stat_score = _score_for_direction(favor_a) if final_direction != "NEUTRAL" else 0
    max_stat = 100

    # Tech confirms?
    tech_confirms = (
        (final_direction == "FAVOR_A" and tech_dir == "FAVORS_A") or
        (final_direction == "FAVOR_B" and tech_dir == "FAVORS_B")
    )

    # Scale stat score to 0-100 percentage
    stat_pct = round((stat_score / max_stat) * 100)

    # Final conviction: 60% stat/tech + 40% AI (when available), or 100% stat if no AI
    if ai_conv > 0:
        final_conviction = round(stat_pct * 0.6 + ai_conv * 0.4)
    else:
        final_conviction = stat_pct

    final_conviction = max(1, min(100, final_conviction))

    # If neutral, conviction is 0
    if final_direction == "NEUTRAL":
        final_conviction = 0

    return {
        "direction":       final_direction,
        "conviction":      final_conviction,
        "stat_score":      stat_score,
        "stat_pct":        stat_pct,
        "stat_max":        max_stat,
        "tech_confirms":   tech_confirms,
        "ai_conviction":   ai_conv,
    }


# ── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    is_dev = os.getenv("RAILWAY_ENVIRONMENT") is None
    print()
    print("  +==========================================+")
    print("  |    WhichTicker                           |")
    print("  |    Relative Performance Analyzer         |")
    print(f"  |    http://localhost:{PORT}                  |")
    print("  +==========================================+")
    print()
    uvicorn.run("app:app", host=HOST, port=PORT, reload=is_dev)
