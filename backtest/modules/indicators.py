"""
Pre-computes all daily technical indicators for the universe.
Results stored as DataFrames indexed by date for O(1) lookup during simulation.
"""

import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# RS score weights per spec
RS_WEIGHT_3M = 0.5
RS_WEIGHT_6M = 0.3
RS_WEIGHT_12M = 0.2

TRADING_DAYS_3M = 63
TRADING_DAYS_6M = 126
TRADING_DAYS_12M = 252


class IndicatorEngine:
    """
    Precomputes and stores all daily technical indicators.
    Call build() once at backtest start, then lookup() per simulation day.
    """

    def __init__(self, prices: Dict[str, pd.DataFrame]):
        self.prices = prices
        self._data: Dict[str, pd.DataFrame] = {}   # {ticker: indicator_df}
        self._rs_rank: Dict[str, pd.Series] = {}   # {ticker: daily rs_rank 0-100}

    def build(self, universe: list) -> None:
        logger.info("Pre-computing indicators for %d tickers...", len(universe))
        valid_tickers = [t for t in universe if t in self.prices]

        # Step 1: per-ticker indicators
        rs_scores: Dict[str, pd.Series] = {}
        for ticker in valid_tickers:
            df = self._compute_ticker(ticker)
            if df is not None:
                self._data[ticker] = df
                rs_scores[ticker] = df["rs_score"]

        # Step 2: cross-sectional RS rank (0=worst, 100=best)
        if rs_scores:
            combined = pd.DataFrame(rs_scores)
            for ticker in combined.columns:
                self._rs_rank[ticker] = combined.rank(axis=1, pct=True)[ticker]

        logger.info("Indicators ready for %d tickers", len(self._data))

    def lookup(self, ticker: str, date: pd.Timestamp) -> Optional[dict]:
        """Return indicator snapshot for ticker on date. None if unavailable."""
        df = self._data.get(ticker)
        if df is None:
            return None
        if date not in df.index:
            # Find most recent prior date
            prior = df.index[df.index <= date]
            if prior.empty:
                return None
            date = prior[-1]

        row = df.loc[date]
        rs_rank = None
        if ticker in self._rs_rank:
            rr = self._rs_rank[ticker]
            if date in rr.index:
                rs_rank = rr.loc[date]
            else:
                prior = rr.index[rr.index <= date]
                if not prior.empty:
                    rs_rank = rr.loc[prior[-1]]

        return {
            "close": row["close"],
            "sma50": row["sma50"],
            "sma200": row["sma200"],
            "high_200d": row["high_200d"],
            "ret_3m": row["ret_3m"],
            "ret_6m": row["ret_6m"],
            "ret_12m": row["ret_12m"],
            "rs_score": row["rs_score"],
            "rs_rank": rs_rank,         # percentile 0-1
            "below_sma50_days": row["below_sma50_days"],
        }

    def get_trading_days(self) -> pd.DatetimeIndex:
        """Return SPY trading calendar."""
        spy_prices = self.prices.get("SPY")
        if spy_prices is None:
            raise RuntimeError("SPY price data missing")
        return spy_prices.index

    def get_spy_indicators(self, date: pd.Timestamp) -> Optional[dict]:
        return self.lookup("SPY", date)

    # ─────────────────────────────────────────────────────────────────

    def _compute_ticker(self, ticker: str) -> Optional[pd.DataFrame]:
        df = self.prices[ticker].copy()
        close = df["Close"]

        if len(close) < 200:
            logger.debug("Skipping %s: insufficient history (%d days)", ticker, len(close))
            return None

        result = pd.DataFrame(index=close.index)
        result["close"] = close
        result["sma50"] = close.rolling(50).mean()
        result["sma200"] = close.rolling(200).mean()
        result["high_200d"] = close.rolling(200).max()

        result["ret_3m"] = close.pct_change(TRADING_DAYS_3M)
        result["ret_6m"] = close.pct_change(TRADING_DAYS_6M)
        result["ret_12m"] = close.pct_change(TRADING_DAYS_12M)

        # RS composite score
        result["rs_score"] = (
            RS_WEIGHT_3M * result["ret_3m"].fillna(0)
            + RS_WEIGHT_6M * result["ret_6m"].fillna(0)
            + RS_WEIGHT_12M * result["ret_12m"].fillna(0)
        )
        # Mask until we have full 3M history
        result.loc[result["ret_3m"].isna(), "rs_score"] = np.nan

        # Consecutive days below SMA50
        below = (close < result["sma50"]).astype(int)
        consec = below * 0
        for i in range(1, len(below)):
            if below.iloc[i]:
                consec.iloc[i] = consec.iloc[i - 1] + 1
            else:
                consec.iloc[i] = 0
        result["below_sma50_days"] = consec

        return result
