"""
Core technical indicators.
All lookback periods are in trading days.
All series are expected to be sorted ascending (oldest first).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Optional

from src.utils.clip import clip_score

MIN_HISTORY_DAYS = 252  # 1 year minimum


# ── Moving Averages ─────────────────────────────────────────────────────────────

def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def sma_slope(series: pd.Series, period: int, lookback: int = 5) -> pd.Series:
    """Annualised slope of the SMA as a fraction of current SMA value."""
    m = sma(series, period)
    return m.diff(lookback) / m.shift(lookback)


# ── ATR (Wilder smoothing) ──────────────────────────────────────────────────────

def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    # Wilder smoothing (RMA)
    result = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return result


# ── RSI ─────────────────────────────────────────────────────────────────────────

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


# ── OBV ─────────────────────────────────────────────────────────────────────────

def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def obv_breakout_score(close: pd.Series, volume: pd.Series,
                       short_period: int = 20, long_period: int = 60) -> pd.Series:
    """
    Returns a series of OBV breakout scores (0, 60, or 100).
    20-day high breakout → 60; 60-day high breakout → 100.
    """
    obv_series = obv(close, volume)
    high_20 = obv_series.shift(1).rolling(short_period).max()
    high_60 = obv_series.shift(1).rolling(long_period).max()

    score = pd.Series(0.0, index=close.index)
    score = score.where(obv_series <= high_20, 60.0)
    score = score.where(obv_series <= high_60, 100.0)
    return score


# ── RS Rank (IBD-style) ─────────────────────────────────────────────────────────

def rs_raw(close: pd.Series) -> pd.Series:
    """
    RS_Raw = 0.40 * R_3M + 0.20 * R_6M + 0.20 * R_9M + 0.20 * R_12M
    Periods: 63, 126, 189, 252 trading days.
    """
    r3  = close / close.shift(63)  - 1
    r6  = close / close.shift(126) - 1
    r9  = close / close.shift(189) - 1
    r12 = close / close.shift(252) - 1
    return 0.40 * r3 + 0.20 * r6 + 0.20 * r9 + 0.20 * r12


def rs_rank_cross_section(rs_raw_series: pd.Series) -> pd.Series:
    """
    Cross-sectional percentile rank (1–99) of RS_Raw across universe on each date.
    Input: DataFrame column or a Series — for single-date use pass a scalar dict externally.
    """
    return rs_raw_series.rank(pct=True).clip(0.01, 0.99) * 99


def compute_rs_rank(prices_df: pd.DataFrame) -> pd.DataFrame:
    """
    prices_df: columns = tickers, index = dates (sorted ascending).
    Returns DataFrame of RS_Rank (1–99) for each ticker/date.
    """
    raw = prices_df.apply(rs_raw)
    rank_df = raw.rank(axis=1, pct=True).clip(0.01, 0.99) * 99
    return rank_df


# ── Short-Term Acceleration (STA) ───────────────────────────────────────────────

def sta(stock_close: pd.Series, spy_close: pd.Series, period: int = 20) -> pd.Series:
    """STA = Return_20D(stock) - Return_20D(SPY)"""
    r_stock = stock_close / stock_close.shift(period) - 1
    r_spy   = spy_close   / spy_close.shift(period)   - 1
    return r_stock - r_spy


def sta_percentile_cross_section(sta_series: pd.Series) -> pd.Series:
    """Cross-sectional percentile of STA (0–100)."""
    return sta_series.rank(pct=True).clip(0.0, 1.0) * 100


# ── High Proximity ──────────────────────────────────────────────────────────────

def high_proximity_score(close: pd.Series, period: int = 252) -> pd.Series:
    """
    Distance from 52-week high → score.
    -15~-10% → 30, -10~-5% → 60, within -5% / new high → 100.
    """
    high_52w = close.rolling(period, min_periods=period).max()
    dist = (close / high_52w) - 1  # negative number

    score = pd.Series(0.0, index=close.index)
    score = score.where(dist < -0.15, 30.0)
    score = score.where(dist < -0.10, 60.0)
    score = score.where(dist < -0.05, 100.0)
    # within -5% or new high
    score[dist >= -0.05] = 100.0
    return score


# ── ATR Contraction Score ────────────────────────────────────────────────────────

def atr_contraction_score(atr_series: pd.Series,
                           short_period: int = 20, long_period: int = 100) -> pd.Series:
    """
    Ratio = ATR(14) 20-day avg / ATR(14) 100-day avg.
    ≥1.0→0, 0.9~1.0→40, 0.8~0.9→70, <0.8→100.
    """
    short_avg = atr_series.rolling(short_period, min_periods=short_period).mean()
    long_avg  = atr_series.rolling(long_period,  min_periods=long_period).mean()
    ratio = short_avg / long_avg.replace(0, np.nan)

    score = pd.Series(0.0, index=atr_series.index)
    score[ratio < 1.0] = 40.0
    score[ratio < 0.9] = 70.0
    score[ratio < 0.8] = 100.0
    return score


# ── Volume Expansion Score ──────────────────────────────────────────────────────

def volume_expansion_score(volume: pd.Series, period: int = 20) -> pd.Series:
    """
    Current volume / 20-day average.
    <1.0→0, 1.0~1.5→40, 1.5~2.0→70, ≥2.0→100.
    """
    avg_vol = volume.rolling(period, min_periods=period).mean()
    ratio = volume / avg_vol.replace(0, np.nan)

    score = pd.Series(0.0, index=volume.index)
    score[ratio >= 1.0] = 40.0
    score[ratio >= 1.5] = 70.0
    score[ratio >= 2.0] = 100.0
    return score


# ── VCP check ───────────────────────────────────────────────────────────────────

def vcp_pass(close: pd.Series, high: pd.Series, volume: pd.Series,
             atr_series: pd.Series) -> pd.Series:
    """
    Boolean series: True if VCP conditions are met on that bar.
    Condition 4 (breakout volume) requires comparing today vs 20-day avg.
    Condition 5 (above MAs) checked externally via entry min conditions.
    """
    high_52w = close.rolling(252, min_periods=252).max()
    dist_from_high = (close / high_52w) - 1

    atr_ratio = (
        atr_series.rolling(20, min_periods=20).mean()
        / atr_series.rolling(100, min_periods=100).mean().replace(0, np.nan)
    )
    vol_20 = volume.rolling(20, min_periods=20).mean()
    vol_100 = volume.rolling(100, min_periods=100).mean()

    # breakout day volume
    breakout_vol = volume >= vol_20 * 1.5

    cond = (
        (atr_ratio < 0.8) &
        (vol_20 < vol_100) &
        (dist_from_high >= -0.15) &
        breakout_vol
    )
    return cond.fillna(False)
