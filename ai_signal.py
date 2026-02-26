"""WhichTicker — Claude API integration for AI-powered relative performance recommendations."""

import json
from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL


def _build_prompt(ticker_a: str, ticker_b: str, stats: dict, technicals: dict, signal: dict) -> str:
    """Build a structured prompt for relative performance analysis."""

    coint = stats.get("cointegration", {})
    rel_ret = stats.get("relative_returns", {})

    # Helper: replace None with "N/A (insufficient data)" for cleaner prompt
    def _v(val, suffix=""):
        if val is None:
            return "N/A (insufficient data)"
        return f"{val}{suffix}"

    # Extract technical confirmation values before the f-string
    # (can't use {{}}.get() inside f-strings — {{}} becomes literal "{}" string)
    tech_conf = technicals.get("confirmation", {})
    tech_rsi = _v(tech_conf.get("rsi_value"))
    tech_macd = _v(tech_conf.get("macd_hist"))
    tech_signals = ", ".join(tech_conf.get("signals", [])) or "N/A"
    tech_direction = tech_conf.get("direction", "N/A")

    # Format relative returns
    ret_lines = []
    for period, data in rel_ret.items():
        if data.get("differential") is not None:
            ret_lines.append(
                f"  - **{period}**: {ticker_a} {data['return_a']:+.1f}% vs {ticker_b} {data['return_b']:+.1f}% "
                f"(differential: {data['differential']:+.1f}%)"
            )
        else:
            ret_lines.append(f"  - **{period}**: Insufficient data for this period")
    ret_text = "\n".join(ret_lines) if ret_lines else "  - No return data available"

    # Format above/below MA as clear text
    def _above(val):
        if val is True:
            return "Yes"
        elif val is False:
            return "No"
        return "N/A (insufficient data for this MA)"

    return f"""You are a quantitative analyst evaluating the relative performance of {ticker_a} vs {ticker_b}.
The question is: **Will {ticker_a} outperform {ticker_b} going forward?**

The price ratio (A/B) is the key metric — a rising ratio means {ticker_a} is outperforming.

## Price Ratio Analysis
- **Current Ratio (A/B)**: {_v(stats.get('current_ratio'))}
- **50-day MA of Ratio**: {_v(stats.get('ratio_ma_50'))}
- **200-day MA of Ratio**: {_v(stats.get('ratio_ma_200'))}
- **Ratio above 50d MA?**: {_above(stats.get('ratio_above_ma_50'))}
- **Ratio above 200d MA?**: {_above(stats.get('ratio_above_ma_200'))}

## Momentum
- **Rate of Change**: {_v(stats.get('momentum_roc'), '%')}
- **Momentum Direction**: {_v(stats.get('momentum_direction'))}

## Return Comparison
{ret_text}

## Statistical Context
- **Ratio Z-Score**: {_v(stats.get('current_zscore'))}
- **Pearson Correlation**: {_v(stats.get('correlation'))}
- **Hurst Exponent (ratio)**: {_v(stats.get('hurst_exponent'))} (> 0.5 = trending, good for persistence)
- **ADF p-value (ratio)**: {_v(stats.get('adf_pvalue'))} (> 0.05 = non-stationary = trend continues)
- **Cointegration p-value**: {_v(coint.get('p_value'))}

## Technical Indicators (on the ratio A/B)
- **RSI**: {tech_rsi}
- **MACD Histogram**: {tech_macd}
- **Technical Signals**: {tech_signals}
- **Technical Direction**: {tech_direction}

## Current Statistical Signal
- **Direction**: {signal.get('direction', 'N/A')}
- **Strength**: {signal.get('strength', 'N/A')}

## Your Task
Respond with a JSON object (and nothing else) containing:
{{
    "signal": "FAVOR_A" or "FAVOR_B" or "NEUTRAL",
    "conviction": <integer 1-100>,
    "recommendation": "<2-3 paragraph analysis explaining which ticker is likely to outperform and why, referencing key metrics>",
    "risk_factors": ["<risk 1>", "<risk 2>", "<risk 3>"]
}}

Where:
- FAVOR_A means: {ticker_a} is likely to outperform {ticker_b}
- FAVOR_B means: {ticker_b} is likely to outperform {ticker_a}
- NEUTRAL means: no clear relative performance edge
- conviction is 1-100 scale: 1-20 = very low, 21-40 = low, 41-60 = moderate, 61-80 = high, 81-100 = very high

Consider:
1. Is the ratio trending (above/below MAs)? Is momentum confirming?
2. What do recent return differentials show — is one consistently outperforming?
3. Does the Hurst exponent suggest the trend will persist (H > 0.5)?
4. Are technical indicators aligned with the trend direction?
5. What could reverse the trend? (sector rotation, valuation, macro events)"""


async def get_ai_recommendation(
    ticker_a: str,
    ticker_b: str,
    stats: dict,
    technicals: dict,
    signal: dict,
) -> dict:
    """
    Call Claude API for a relative performance recommendation.
    Returns a dict with signal, conviction, recommendation, risk_factors.
    Gracefully falls back if API key is missing or call fails.
    """
    if not ANTHROPIC_API_KEY:
        return {
            "signal": "N/A",
            "conviction": 0,
            "recommendation": "AI recommendation unavailable — set ANTHROPIC_API_KEY in .env to enable.",
            "risk_factors": [],
            "available": False,
        }

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        prompt = _build_prompt(ticker_a, ticker_b, stats, technicals, signal)

        message = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        # Parse the response
        text = message.content[0].text.strip()

        # Try to extract JSON from the response
        if "```" in text:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                text = text[start:end]

        result = json.loads(text)
        result["available"] = True
        result["model_used"] = ANTHROPIC_MODEL

        # Validate conviction range (1-100)
        raw_conv = int(result.get("conviction", 50))
        # Handle legacy 1-5 responses — scale up to 1-100
        if 1 <= raw_conv <= 5:
            raw_conv = raw_conv * 20
        result["conviction"] = max(1, min(100, raw_conv))

        # Map legacy BUY/SELL to new signals
        sig = result.get("signal", "NEUTRAL").upper()
        if sig == "BUY":
            result["signal"] = "FAVOR_A"
        elif sig == "SELL":
            result["signal"] = "FAVOR_B"
        elif sig not in ("FAVOR_A", "FAVOR_B", "NEUTRAL"):
            result["signal"] = "NEUTRAL"

        return result

    except json.JSONDecodeError:
        return {
            "signal": "N/A",
            "conviction": 0,
            "recommendation": text if 'text' in dir() else "Failed to parse AI response.",
            "risk_factors": [],
            "available": True,
            "model_used": ANTHROPIC_MODEL,
            "parse_error": True,
        }
    except Exception as e:
        return {
            "signal": "N/A",
            "conviction": 0,
            "recommendation": f"AI recommendation failed: {str(e)}",
            "risk_factors": [],
            "available": False,
        }
