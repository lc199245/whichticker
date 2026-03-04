"""Market data fetching via yfinance."""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta


def _min_days_for_period(period: str) -> int:
    """Return minimum required trading days based on the lookback period."""
    return {"30d": 10, "60d": 20, "1mo": 15, "3mo": 15}.get(period, 30)


def _yf_period(period: str) -> str:
    """Map our period keys to yfinance period strings."""
    # yfinance supports: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max
    # For 30d/60d we use the day-count format directly
    return {"30d": "1mo", "60d": "3mo"}.get(period, period)


def fetch_pair_data(
    ticker_a: str, ticker_b: str, period: str = "1y"
) -> tuple[pd.DataFrame, pd.DataFrame] | tuple[None, str]:
    """
    Fetch historical close prices for two tickers and align on common dates.

    Returns (df_a, df_b) on success, or (None, error_message) on failure.
    """
    try:
        yf_period = _yf_period(period)
        hist_a = yf.Ticker(ticker_a).history(period=yf_period)
        hist_b = yf.Ticker(ticker_b).history(period=yf_period)

        failed = []
        if hist_a.empty:
            failed.append(ticker_a)
        if hist_b.empty:
            failed.append(ticker_b)
        if failed:
            return None, f"No data returned for: {', '.join(failed)}. Check that the ticker(s) are valid."

        # Align on common dates (inner join)
        close_a = hist_a[["Close"]].rename(columns={"Close": "close"})
        close_b = hist_b[["Close"]].rename(columns={"Close": "close"})
        close_a, close_b = close_a.align(close_b, join="inner")

        # Drop any rows with NaN
        mask = close_a["close"].notna() & close_b["close"].notna()
        close_a = close_a[mask]
        close_b = close_b[mask]

        # For 30d/60d, trim to exact calendar day window from today
        day_trim = {"30d": 30, "60d": 60}.get(period)
        if day_trim:
            cutoff = datetime.now() - timedelta(days=day_trim)
            close_a = close_a[close_a.index.tz_localize(None) >= cutoff]
            close_b = close_b[close_b.index.tz_localize(None) >= cutoff]

        min_days = _min_days_for_period(period)
        if len(close_a) < min_days:
            return None, f"Not enough overlapping data for {ticker_a} and {ticker_b} over the selected period (need at least {min_days} trading days, got {len(close_a)})."

        return close_a, close_b

    except Exception as e:
        print(f"  Error fetching pair data ({ticker_a}, {ticker_b}): {e}")
        return None, f"Error fetching data: {e}"


def validate_ticker(ticker: str) -> dict | None:
    """Validate that a ticker exists and return basic info."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if hist.empty:
            return None

        name = ticker.upper()
        try:
            info = t.info
            name = info.get("shortName") or info.get("longName") or ticker.upper()
        except Exception:
            pass

        return {
            "symbol": ticker.upper(),
            "name": name,
            "last_price": round(float(hist["Close"].iloc[-1]), 2),
        }
    except Exception:
        return None


def get_price_series(ticker: str, period: str = "1y") -> dict | None:
    """
    Fetch price data for a single ticker, formatted for charting.
    Returns dict with 'dates' (ISO strings) and 'prices' (floats).
    """
    try:
        hist = yf.Ticker(ticker).history(period=_yf_period(period))
        if hist.empty:
            return None
        # Trim to exact window for 30d/60d
        day_trim = {"30d": 30, "60d": 60}.get(period)
        if day_trim:
            cutoff = datetime.now() - timedelta(days=day_trim)
            hist = hist[hist.index.tz_localize(None) >= cutoff]

        dates = [d.strftime("%Y-%m-%d") for d in hist.index]
        prices = [round(float(p), 2) for p in hist["Close"]]

        name = ticker.upper()
        try:
            info = yf.Ticker(ticker).info
            name = info.get("shortName") or info.get("longName") or ticker.upper()
        except Exception:
            pass

        return {
            "symbol": ticker.upper(),
            "name": name,
            "dates": dates,
            "prices": prices,
        }
    except Exception as e:
        print(f"  Error fetching price series for {ticker}: {e}")
        return None


def search_tickers(query: str, max_results: int = 8) -> list[dict]:
    """Search for tickers matching a query string via yfinance."""
    try:
        results = []
        search = yf.Search(query, max_results=max_results)
        if hasattr(search, "quotes") and search.quotes:
            for item in search.quotes:
                results.append({
                    "symbol":   item.get("symbol", ""),
                    "name":     item.get("shortname") or item.get("longname", ""),
                    "exchange": item.get("exchange", ""),
                    "type":     item.get("quoteType", ""),
                })
        return results
    except Exception as e:
        print(f"  Search error: {e}")
        return []
