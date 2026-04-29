"""
Data loader for backtesting.
Expects the following CSV layout under data/:

  data/prices/<SYMBOL>.csv
    Columns: date, open, high, low, close, volume
    (adjusted for splits/dividends)

  data/prices/SPY.csv, QQQ.csv, GLD.csv, TLT.csv, ^VIX.csv
    Same format — index ETFs and VIX spot.

  data/fundamentals/fundamentals.csv
    Columns: symbol, period_end_date, filing_date, available_date,
             market_cap, revenue_growth_yoy, gross_margin, roic,
             fcf_positive, buyback_yield, fcf_yield, debt_to_equity,
             turnaround_flag, rs_rank_improving, sector, industry,
             security_type, delisting_date

  data/earnings_calendar/earnings.csv
    Columns: symbol, earnings_date, fiscal_period, timing (BMO/AMC/Unknown)

  data/market_breadth/breadth.csv
    Columns: date, pct_above_50dma, pct_above_200dma, nh_nl_ratio,
             mclellan, hy_spread, hy_spread_60d_avg, hy_spread_20d_delta,
             hy_oas_20d_change_bp, yield_10y_3m_bp
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _load_csv(path: Path, parse_dates: list[str] = ["date"]) -> Optional[pd.DataFrame]:
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=parse_dates)
    if "date" in df.columns:
        df = df.sort_values("date").set_index("date")
    return df


def load_price_history(symbol: str) -> Optional[pd.DataFrame]:
    path = _DATA_DIR / "prices" / f"{symbol}.csv"
    return _load_csv(path)


def load_all_prices(symbols: list[str]) -> dict[str, pd.DataFrame]:
    out = {}
    for sym in symbols:
        df = load_price_history(sym)
        if df is not None:
            out[sym] = df
    return out


def load_fundamentals() -> Optional[pd.DataFrame]:
    path = _DATA_DIR / "fundamentals" / "fundamentals.csv"
    df = _load_csv(path, parse_dates=["period_end_date", "filing_date", "available_date"])
    if df is not None and "date" not in df.index.names:
        # fundamentals may not have a date index
        return pd.read_csv(
            _DATA_DIR / "fundamentals" / "fundamentals.csv",
            parse_dates=["period_end_date", "filing_date", "available_date"],
        )
    return df


def load_earnings_calendar() -> Optional[pd.DataFrame]:
    path = _DATA_DIR / "earnings_calendar" / "earnings.csv"
    if not path.exists():
        return None
    return pd.read_csv(path, parse_dates=["earnings_date"])


def load_market_breadth() -> Optional[pd.DataFrame]:
    path = _DATA_DIR / "market_breadth" / "breadth.csv"
    return _load_csv(path)


def get_price_on_date(price_history: dict[str, pd.DataFrame],
                       symbol: str, date: pd.Timestamp,
                       col: str = "close") -> Optional[float]:
    df = price_history.get(symbol)
    if df is None or date not in df.index:
        return None
    return float(df.loc[date, col])


def get_rolling_mean(series: pd.Series, period: int,
                      as_of: pd.Timestamp) -> Optional[float]:
    sub = series[series.index <= as_of].tail(period)
    if len(sub) < period:
        return None
    return float(sub.mean())


def slice_up_to(df: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """Return all rows with index ≤ as_of."""
    return df[df.index <= as_of]


def history_length(price_history: dict[str, pd.DataFrame],
                    as_of: pd.Timestamp) -> dict[str, int]:
    """Number of trading days available for each symbol up to as_of."""
    return {
        sym: int((df.index <= as_of).sum())
        for sym, df in price_history.items()
    }
