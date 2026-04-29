"""
Online data fetcher using yfinance.
Downloads price history + quarterly fundamentals, caches to disk.
"""

import os
import pickle
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
import yfinance as yf
from tqdm import tqdm

logger = logging.getLogger(__name__)


class DataFetcher:
    def __init__(self, cache_dir: str = "backtest/data_cache"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    # ─────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────

    def fetch_all(
        self,
        universe: List[str],
        start_date: str,
        end_date: str,
        force_refresh: bool = False,
    ) -> Tuple[Dict[str, pd.DataFrame], Dict[str, pd.Series], Dict]:
        """
        Returns:
            prices      : {ticker: OHLCV DataFrame}  (includes SPY, ^VIX)
            vix_series  : Date-indexed VIX close Series
            fundamentals: {ticker: quarterly fundamental dict}
        """
        cache_key = f"{'-'.join(sorted(universe))}_{start_date}_{end_date}"
        cache_file = os.path.join(self.cache_dir, f"data_{abs(hash(cache_key))}.pkl")

        if not force_refresh and os.path.exists(cache_file):
            logger.info("Loading cached data from %s", cache_file)
            with open(cache_file, "rb") as f:
                return pickle.load(f)

        logger.info("Fetching online data for %d tickers...", len(universe))
        prices = self._fetch_prices(universe, start_date, end_date)
        vix_series = self._fetch_vix(start_date, end_date)
        fundamentals = self._fetch_fundamentals(universe)

        result = (prices, vix_series, fundamentals)
        with open(cache_file, "wb") as f:
            pickle.dump(result, f)
        logger.info("Data cached to %s", cache_file)
        return result

    # ─────────────────────────────────────────────────────────────────
    # Price data
    # ─────────────────────────────────────────────────────────────────

    def _fetch_prices(self, universe: List[str], start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        # Add 300-day buffer for indicator warmup (SMA200, etc.)
        buffer_start = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=300)).strftime("%Y-%m-%d")

        # Always include SPY
        all_tickers = list(set(universe + ["SPY"]))

        logger.info("Downloading OHLCV for %d symbols (%s to %s)...", len(all_tickers), buffer_start, end_date)
        raw = yf.download(all_tickers, start=buffer_start, end=end_date, auto_adjust=True, progress=False)

        prices: Dict[str, pd.DataFrame] = {}
        if isinstance(raw.columns, pd.MultiIndex):
            # Multiple tickers → MultiIndex columns (Price, Ticker)
            for ticker in all_tickers:
                try:
                    df = raw.xs(ticker, axis=1, level=1).copy()
                    df.index = pd.to_datetime(df.index)
                    df = df.dropna(subset=["Close"])
                    if not df.empty:
                        prices[ticker] = df
                except Exception:
                    pass
        else:
            # Single ticker
            raw.index = pd.to_datetime(raw.index)
            raw = raw.dropna(subset=["Close"])
            if not raw.empty:
                prices[all_tickers[0]] = raw

        logger.info("Price data loaded for %d symbols", len(prices))
        return prices

    def _fetch_vix(self, start_date: str, end_date: str) -> pd.Series:
        buffer_start = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=300)).strftime("%Y-%m-%d")
        logger.info("Downloading VIX...")
        vix = yf.download("^VIX", start=buffer_start, end=end_date, auto_adjust=True, progress=False)
        if isinstance(vix.columns, pd.MultiIndex):
            vix = vix.xs("^VIX", axis=1, level=1)
        vix.index = pd.to_datetime(vix.index)
        return vix["Close"].dropna()

    # ─────────────────────────────────────────────────────────────────
    # Fundamental data
    # ─────────────────────────────────────────────────────────────────

    def _fetch_fundamentals(self, universe: List[str]) -> Dict:
        fundamentals = {}
        for ticker in tqdm(universe, desc="Fetching fundamentals"):
            fundamentals[ticker] = self._fetch_single_fundamental(ticker)
        return fundamentals

    def _fetch_single_fundamental(self, ticker: str) -> dict:
        result = {
            "quarterly_income": None,
            "quarterly_cashflow": None,
            "quarterly_balance": None,
            "dividends": None,
            "sector": None,
            "market_cap": None,
            "earnings_dates": None,
        }
        try:
            t = yf.Ticker(ticker)

            result["quarterly_income"] = self._safe_df(t.quarterly_income_stmt)
            result["quarterly_cashflow"] = self._safe_df(t.quarterly_cashflow)
            result["quarterly_balance"] = self._safe_df(t.quarterly_balance_sheet)

            divs = t.dividends
            if divs is not None and not divs.empty:
                divs.index = pd.to_datetime(divs.index).tz_localize(None)
                result["dividends"] = divs

            info = t.info or {}
            result["sector"] = info.get("sector") or info.get("sectorKey")
            result["market_cap"] = info.get("marketCap")

            # Historical earnings dates
            try:
                ed = t.get_earnings_dates(limit=40)
                if ed is not None and not ed.empty:
                    ed.index = pd.to_datetime(ed.index).tz_localize(None)
                    result["earnings_dates"] = ed
            except Exception:
                pass

        except Exception as e:
            logger.warning("Fundamental fetch failed for %s: %s", ticker, e)

        return result

    @staticmethod
    def _safe_df(df) -> Optional[pd.DataFrame]:
        if df is None or df.empty:
            return None
        df = df.copy()
        df.columns = pd.to_datetime(df.columns).tz_localize(None)
        return df
