"""
Point-in-time fundamental processor.
Uses quarterly financial statements from yfinance with a filing lag
(default 45 days) to avoid lookahead bias.
"""

import logging
from datetime import timedelta
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

FILING_LAG_DAYS = 45   # Assume 10-Q/10-K filed ~45 days after quarter end


class FundamentalsProcessor:
    def __init__(self, fundamentals_raw: dict, filing_lag_days: int = FILING_LAG_DAYS):
        self.raw = fundamentals_raw
        self.lag = timedelta(days=filing_lag_days)

    def get(self, ticker: str, date: pd.Timestamp) -> dict:
        """
        Return point-in-time fundamentals for ticker on date.
        Only uses quarterly data filed on or before `date`.
        """
        base = {
            "sector": None,
            "market_cap": None,
            "revenue_yoy": None,
            "eps_yoy": None,
            "fcf_ttm": None,
            "de_ratio": None,
            "pe_ttm": None,
            "div_yield_ttm": None,
            "next_earnings_date": None,
            "has_normal_data": False,
            "has_crisis_data": False,
        }

        raw = self.raw.get(ticker)
        if not raw:
            return base

        base["sector"] = raw.get("sector")
        base["market_cap"] = raw.get("market_cap")

        cutoff = date - self.lag
        income = raw.get("quarterly_income")
        cashflow = raw.get("quarterly_cashflow")
        balance = raw.get("quarterly_balance")
        dividends = raw.get("dividends")
        close_price = None  # filled from price lookup by caller if needed

        # ── Revenue & EPS YoY ─────────────────────────────────────
        base["revenue_yoy"] = self._revenue_yoy(income, cutoff)
        base["eps_yoy"] = self._eps_yoy(income, cutoff)

        # ── FCF TTM ───────────────────────────────────────────────
        base["fcf_ttm"] = self._fcf_ttm(cashflow, cutoff)

        # ── Debt / Equity ─────────────────────────────────────────
        base["de_ratio"] = self._de_ratio(balance, cutoff)

        # ── Dividend Yield ────────────────────────────────────────
        base["div_yield_ttm"] = self._div_yield(dividends, date)

        # ── PE (trailing) ─────────────────────────────────────────
        base["pe_ttm"] = self._pe_ttm(income, cutoff, base.get("_price"))

        # ── Next earnings date ────────────────────────────────────
        base["next_earnings_date"] = self._next_earnings(raw.get("earnings_dates"), date)

        # ── Composite flags ───────────────────────────────────────
        base["has_normal_data"] = all(
            base[k] is not None
            for k in ["revenue_yoy", "eps_yoy", "sector", "market_cap"]
        )
        base["has_crisis_data"] = all(
            base[k] is not None
            for k in ["fcf_ttm", "de_ratio", "div_yield_ttm", "sector", "market_cap"]
        )

        return base

    def get_with_price(self, ticker: str, date: pd.Timestamp, current_price: float) -> dict:
        """Like get() but also computes PE using current price."""
        data = self.get(ticker, date)
        raw = self.raw.get(ticker, {})
        cutoff = date - self.lag
        data["pe_ttm"] = self._pe_ttm(raw.get("quarterly_income"), cutoff, current_price)
        return data

    # ─────────────────────────────────────────────────────────────────
    # Helper extractors
    # ─────────────────────────────────────────────────────────────────

    def _available_quarters(self, df: Optional[pd.DataFrame], cutoff: pd.Timestamp):
        """Return columns (quarter-end dates) <= cutoff, sorted descending."""
        if df is None or df.empty:
            return []
        cols = [c for c in df.columns if pd.to_datetime(c) <= cutoff]
        return sorted(cols, reverse=True)

    def _get_row(self, df: pd.DataFrame, *name_variants) -> Optional[pd.Series]:
        """Find a row in df by any of the given name variants (case-insensitive)."""
        if df is None:
            return None
        index_lower = {str(i).lower(): i for i in df.index}
        for name in name_variants:
            key = index_lower.get(name.lower())
            if key is not None:
                return df.loc[key]
        return None

    def _ttm_sum(self, df, cutoff, *name_variants) -> Optional[float]:
        """Sum of most recent 4 quarters available at cutoff."""
        quarters = self._available_quarters(df, cutoff)
        if len(quarters) < 4:
            return None
        row = self._get_row(df, *name_variants)
        if row is None:
            return None
        values = [row.get(q) for q in quarters[:4]]
        if any(v is None or (isinstance(v, float) and np.isnan(v)) for v in values):
            return None
        return float(sum(values))

    def _revenue_yoy(self, income: Optional[pd.DataFrame], cutoff: pd.Timestamp) -> Optional[float]:
        quarters = self._available_quarters(income, cutoff)
        if len(quarters) < 8:
            return None
        row = self._get_row(income, "Total Revenue", "Revenue", "Revenues")
        if row is None:
            return None
        try:
            current_ttm = sum(float(row[q]) for q in quarters[:4])
            prior_ttm = sum(float(row[q]) for q in quarters[4:8])
            if prior_ttm == 0:
                return None
            return (current_ttm - prior_ttm) / abs(prior_ttm)
        except (TypeError, ValueError):
            return None

    def _eps_yoy(self, income: Optional[pd.DataFrame], cutoff: pd.Timestamp) -> Optional[float]:
        quarters = self._available_quarters(income, cutoff)
        if len(quarters) < 8:
            return None
        row = self._get_row(
            income,
            "Basic EPS", "Diluted EPS", "EPS", "Earnings Per Share",
            "Normalized EPS", "Basic Earnings Per Share",
        )
        if row is None:
            # Fallback: derive from net income / shares
            ni_row = self._get_row(income, "Net Income", "Net Income Common Stockholders")
            sh_row = self._get_row(income, "Diluted Average Shares", "Basic Average Shares")
            if ni_row is None or sh_row is None:
                return None
            try:
                current = sum(float(ni_row[q]) / float(sh_row[q]) for q in quarters[:4])
                prior = sum(float(ni_row[q]) / float(sh_row[q]) for q in quarters[4:8])
                if prior == 0:
                    return None
                return (current - prior) / abs(prior)
            except (TypeError, ValueError, ZeroDivisionError):
                return None
        try:
            current_ttm = sum(float(row[q]) for q in quarters[:4])
            prior_ttm = sum(float(row[q]) for q in quarters[4:8])
            if prior_ttm == 0:
                return None
            return (current_ttm - prior_ttm) / abs(prior_ttm)
        except (TypeError, ValueError):
            return None

    def _fcf_ttm(self, cashflow: Optional[pd.DataFrame], cutoff: pd.Timestamp) -> Optional[float]:
        # Try directly available Free Cash Flow row first
        fcf_direct = self._ttm_sum(cashflow, cutoff, "Free Cash Flow")
        if fcf_direct is not None:
            return fcf_direct

        quarters = self._available_quarters(cashflow, cutoff)
        if len(quarters) < 4:
            return None

        opcf_row = self._get_row(
            cashflow,
            "Operating Cash Flow", "Cash From Operations",
            "Net Cash Provided By Operating Activities",
            "Total Cash From Operating Activities",
        )
        capex_row = self._get_row(
            cashflow,
            "Capital Expenditure", "Capital Expenditures",
            "Purchase Of Property Plant And Equipment",
            "Purchases Of Property Plant And Equipment",
        )
        if opcf_row is None or capex_row is None:
            return None
        try:
            opcf = sum(float(opcf_row[q]) for q in quarters[:4])
            capex = sum(float(capex_row[q]) for q in quarters[:4])
            # capex is usually negative in yfinance → FCF = opcf + capex
            return opcf + capex
        except (TypeError, ValueError):
            return None

    def _de_ratio(self, balance: Optional[pd.DataFrame], cutoff: pd.Timestamp) -> Optional[float]:
        quarters = self._available_quarters(balance, cutoff)
        if not quarters:
            return None
        latest = quarters[0]

        debt_row = self._get_row(
            balance,
            "Total Debt", "Long Term Debt And Capital Lease Obligation",
            "Long Term Debt",
        )
        equity_row = self._get_row(
            balance,
            "Stockholders Equity", "Total Stockholders Equity",
            "Common Stock Equity", "Total Equity Gross Minority Interest",
        )
        if debt_row is None or equity_row is None:
            return None
        try:
            debt = float(debt_row[latest])
            equity = float(equity_row[latest])
            if equity <= 0:
                return None
            return debt / equity
        except (TypeError, ValueError):
            return None

    def _pe_ttm(
        self,
        income: Optional[pd.DataFrame],
        cutoff: pd.Timestamp,
        price: Optional[float],
    ) -> Optional[float]:
        if price is None or price <= 0:
            return None
        quarters = self._available_quarters(income, cutoff)
        if len(quarters) < 4:
            return None
        eps_row = self._get_row(
            income,
            "Basic EPS", "Diluted EPS", "EPS", "Normalized EPS",
            "Basic Earnings Per Share",
        )
        if eps_row is None:
            return None
        try:
            ttm_eps = sum(float(eps_row[q]) for q in quarters[:4])
            if ttm_eps <= 0:
                return None
            return price / ttm_eps
        except (TypeError, ValueError):
            return None

    def _div_yield(self, dividends: Optional[pd.Series], date: pd.Timestamp) -> Optional[float]:
        # Returns TTM dividends per share; caller divides by price if needed
        # We return as a ratio (yield); price is injected by the caller if needed.
        # For backtesting we return raw TTM dividends sum; caller must divide by price.
        if dividends is None or dividends.empty:
            return None
        ttm_start = date - pd.Timedelta(days=365)
        ttm_divs = dividends[(dividends.index >= ttm_start) & (dividends.index <= date)]
        if ttm_divs.empty:
            return None
        return float(ttm_divs.sum())   # Total dividends in TTM (per share)

    def _next_earnings(self, earnings_dates: Optional[pd.DataFrame], date: pd.Timestamp) -> Optional[pd.Timestamp]:
        if earnings_dates is None or earnings_dates.empty:
            return None
        future = earnings_dates.index[earnings_dates.index > date]
        if future.empty:
            return None
        return future.min()
