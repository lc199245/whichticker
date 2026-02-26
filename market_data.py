"""Market data fetching via yfinance."""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta


def _min_days_for_period(period: str) -> int:
    """Return minimum required trading days based on the lookback period."""
    short_periods = {"1mo", "3mo"}
    return 15 if period in short_periods else 30


def fetch_pair_data(
    ticker_a: str, ticker_b: str, period: str = "1y"
) -> tuple[pd.DataFrame, pd.DataFrame] | tuple[None, str]:
    """
    Fetch historical close prices for two tickers and align on common dates.

    Returns (df_a, df_b) on success, or (None, error_message) on failure.
    """
    try:
        hist_a = yf.Ticker(ticker_a).history(period=period)
        hist_b = yf.Ticker(ticker_b).history(period=period)

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
        hist = yf.Ticker(ticker).history(period=period)
        if hist.empty:
            return None

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
