"""
Fundamental universe builder.
Applies garbage filters, liquidity conditions, PiT rule, and basket assignment.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from src.indicators import MIN_HISTORY_DAYS

# ── Constants ───────────────────────────────────────────────────────────────────

MIN_MARKET_CAP_USD    = 500_000_000    # $500M
MIN_ADTV_USD          = 10_000_000     # $10M
MIN_LISTING_DAYS      = 252            # 1 year
MIN_PRICE             = 5.0
EXCLUDED_TYPES        = {"ETF", "ETN", "ADR", "PREFERRED", "SPAC", "CEF", "WARRANT"}


@dataclass
class UniverseStock:
    symbol: str
    basket: str   # "Quality Growth", "Shareholder Yield", "Turnaround"
    market_cap: float
    adtv_20d: float
    listing_days: int
    price: float
    above_200dma: bool
    rs_rank_improving: bool   # for Turnaround
    sector: str
    industry: str
    is_megacap: bool          # top-10 by market cap in universe


def _pit_available(row: pd.Series, trade_date: pd.Timestamp) -> bool:
    """Check if filing data is available by trade_date (PiT rule)."""
    avail = row.get("available_date")
    if pd.isna(avail):
        return False
    return pd.Timestamp(avail) <= trade_date


def _passes_garbage_filter(row: pd.Series) -> tuple[bool, str]:
    security_type = str(row.get("security_type", "")).upper()
    if any(t in security_type for t in EXCLUDED_TYPES):
        return False, f"EXCLUDED_TYPE:{security_type}"
    if row.get("delisting_date") is not None:
        return False, "DELISTING"
    return True, ""


def _passes_liquidity(row: pd.Series, price: float) -> tuple[bool, str]:
    if row.get("market_cap", 0) < MIN_MARKET_CAP_USD:
        return False, "LIQUIDITY_INSUFFICIENT"
    if row.get("adtv_20d", 0) < MIN_ADTV_USD:
        return False, "LIQUIDITY_INSUFFICIENT"
    if row.get("listing_days", 0) < MIN_LISTING_DAYS:
        return False, "LOOKBACK_INSUFFICIENT"
    if price < MIN_PRICE:
        return False, "LIQUIDITY_INSUFFICIENT"
    return True, ""


def _assign_basket(row: pd.Series) -> Optional[str]:
    """
    Simplified basket assignment.
    In production: connect to fundamental DB and apply all conditions.
    """
    # Turnaround: recovering above 200DMA, RS improving, but NOT yet Quality Growth
    if row.get("turnaround_flag", False):
        return "Turnaround"
    # Shareholder Yield
    if row.get("buyback_yield", 0) >= 0.01 and row.get("fcf_yield", 0) >= 0.03:
        return "Shareholder Yield"
    # Quality Growth (default for high-quality names)
    return "Quality Growth"


def build_universe(
    fundamentals: pd.DataFrame,
    price_on_date: pd.Series,   # index = symbol, value = close price
    price_200dma: pd.Series,
    adtv_20d: pd.Series,
    listing_days: pd.Series,
    rs_rank: pd.Series,
    trade_date: pd.Timestamp,
    history_length: pd.Series,  # number of available trading days per symbol
) -> pd.DataFrame:
    """
    Returns a DataFrame of universe stocks that pass all filters.
    Columns: symbol, basket, market_cap, adtv_20d, price, above_200dma,
             sector, industry, is_megacap, block_reason
    """
    rows = []

    for symbol, row in fundamentals.iterrows():
        price = price_on_date.get(symbol, 0.0)

        # PiT check
        if not _pit_available(row, trade_date):
            continue

        # Garbage filter
        ok, reason = _passes_garbage_filter(row)
        if not ok:
            continue

        # History / lookback check
        hist_len = history_length.get(symbol, 0)
        if hist_len < MIN_HISTORY_DAYS:
            rows.append({
                "symbol": symbol, "basket": None, "block_reason": "LOOKBACK_INSUFFICIENT",
                "price": price, "market_cap": row.get("market_cap", 0),
                "adtv_20d": adtv_20d.get(symbol, 0), "sector": row.get("sector", ""),
                "industry": row.get("industry", ""), "is_megacap": False,
                "above_200dma": False, "rs_rank_improving": False,
            })
            continue

        # Liquidity
        ok, reason = _passes_liquidity(row, price)
        if not ok:
            rows.append({
                "symbol": symbol, "basket": None, "block_reason": reason,
                "price": price, "market_cap": row.get("market_cap", 0),
                "adtv_20d": adtv_20d.get(symbol, 0), "sector": row.get("sector", ""),
                "industry": row.get("industry", ""), "is_megacap": False,
                "above_200dma": False, "rs_rank_improving": False,
            })
            continue

        basket = _assign_basket(row)
        above_200 = price > price_200dma.get(symbol, float("inf"))

        rows.append({
            "symbol": symbol,
            "basket": basket,
            "block_reason": None,
            "price": price,
            "market_cap": row.get("market_cap", 0),
            "adtv_20d": adtv_20d.get(symbol, 0),
            "sector": row.get("sector", ""),
            "industry": row.get("industry", ""),
            "is_megacap": False,
            "above_200dma": above_200,
            "rs_rank_improving": row.get("rs_rank_improving", False),
            "listing_days": listing_days.get(symbol, 0),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Mark top-10 megacaps
    if "market_cap" in df.columns:
        top10_thresh = df["market_cap"].nlargest(10).min()
        df["is_megacap"] = df["market_cap"] >= top10_thresh

    return df


def filter_entry_candidates(universe: pd.DataFrame, rs_rank: pd.Series,
                              price_50dma: pd.Series, price_200dma: pd.Series,
                              price: pd.Series) -> pd.DataFrame:
    """
    Apply minimum entry conditions from config.
    Returns subset that could be entry candidates (further momentum scoring needed).
    """
    df = universe[universe["block_reason"].isna()].copy()
    if df.empty:
        return df

    df["rs_rank"] = df["symbol"].map(rs_rank)
    df["price"]   = df["symbol"].map(price)
    df["price_50dma"]  = df["symbol"].map(price_50dma)
    df["price_200dma"] = df["symbol"].map(price_200dma)

    df["above_50dma"]  = df["price"] > df["price_50dma"]
    df["above_200dma"] = df["price"] > df["price_200dma"]

    mask = (
        (df["rs_rank"] >= 70) &
        df["above_50dma"] &
        df["above_200dma"]
    )
    return df[mask].copy()
