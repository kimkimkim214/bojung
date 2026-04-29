"""
Momentum scanner: VCP check + Momentum Score + STA adjustment.
All scores clipped to [0, 100] at output.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd
import numpy as np

from src.utils.clip import clip_score
from src.indicators import (
    sma, atr, obv_breakout_score, high_proximity_score,
    atr_contraction_score, volume_expansion_score, vcp_pass,
    rs_raw, compute_rs_rank, sta, sta_percentile_cross_section,
    MIN_HISTORY_DAYS,
)

# ── Data structures ──────────────────────────────────────────────────────────────

@dataclass
class StockFeatures:
    symbol: str
    rs_rank: float           # 1–99
    rs_rank_normalized: float  # 0–100
    obv_breakout: float      # 0, 60, or 100
    high_proximity: float    # 0–100
    atr_contraction: float   # 0–100
    volume_expansion: float  # 0–100
    sta_value: float
    sta_percentile: float    # 0–100
    vcp_ok: bool
    atr_14: float            # current ATR value
    price: float
    price_50dma: float
    price_200dma: float
    high_52w: float
    adtv_20d: float


@dataclass
class MomentumResult:
    symbol: str
    momentum_score: float    # 0–100 (STA adjusted, clipped)
    rs_rank: float
    vcp_pass: bool
    entry_type: str          # "VCP_Breakout" / "RS_Breakout" / "Pullback"
    suggested_entry: float
    structural_stop: float
    risk_per_share: float
    atr_14: float
    basket: str
    block_reason: Optional[str] = None


# ── Momentum Score ───────────────────────────────────────────────────────────────

def calc_momentum_score(f: StockFeatures) -> float:
    base = (
        0.35 * f.rs_rank_normalized
      + 0.20 * f.obv_breakout
      + 0.20 * f.high_proximity
      + 0.15 * f.atr_contraction
      + 0.10 * f.volume_expansion
    )
    # STA adjustment
    if f.sta_value < 0:
        base -= 10.0
    elif f.sta_percentile >= 70:
        base += 10.0

    return clip_score(base)


def _structural_stop(price: float, atr14: float, basket: str,
                      swing_low: Optional[float] = None,
                      vcp_box_low: Optional[float] = None) -> float:
    """
    Determine structural stop: ATR multiple based on basket risk profile.
    Uses the most logical support level available.
    """
    mult_map = {
        "Shareholder Yield": 1.5,
        "Quality Growth": 2.0,
        "Turnaround": 2.5,
    }
    mult = mult_map.get(basket, 2.0)
    atr_stop = price - mult * atr14

    candidates = [atr_stop]
    if swing_low and swing_low > 0:
        candidates.append(swing_low)
    if vcp_box_low and vcp_box_low > 0:
        candidates.append(vcp_box_low)

    # Use the highest (least aggressive) logical stop
    return max(c for c in candidates if c > 0)


def _entry_type(vcp_ok: bool, high_proximity: float, sta_value: float) -> str:
    if vcp_ok:
        return "VCP_Breakout"
    if high_proximity >= 100:
        return "RS_Breakout"
    return "Pullback"


# ── Main scanner function ────────────────────────────────────────────────────────

def scan_momentum_candidates(
    candidates_df: pd.DataFrame,
    price_history: dict[str, pd.DataFrame],  # symbol → OHLCV DataFrame
    spy_close: pd.Series,                     # SPY close history
    regime: str,
    config: dict,
) -> list[MomentumResult]:
    """
    For each candidate, compute momentum score and entry parameters.
    price_history[sym]: DataFrame with columns [open, high, low, close, volume], index=date.
    """
    results = []

    for _, row in candidates_df.iterrows():
        sym = row["symbol"]
        basket = row.get("basket", "Quality Growth")

        hist = price_history.get(sym)
        if hist is None or len(hist) < MIN_HISTORY_DAYS:
            results.append(MomentumResult(
                symbol=sym, momentum_score=0, rs_rank=0, vcp_pass=False,
                entry_type="", suggested_entry=0, structural_stop=0,
                risk_per_share=0, atr_14=0, basket=basket,
                block_reason="LOOKBACK_INSUFFICIENT",
            ))
            continue

        close  = hist["close"]
        high   = hist["high"]
        low    = hist["low"]
        volume = hist["volume"]

        atr14 = atr(high, low, close, 14)
        ma50  = close.rolling(50).mean()
        ma200 = close.rolling(200).mean()

        cur_price   = float(close.iloc[-1])
        cur_atr14   = float(atr14.iloc[-1])
        cur_ma50    = float(ma50.iloc[-1]) if not pd.isna(ma50.iloc[-1]) else 0.0
        cur_ma200   = float(ma200.iloc[-1]) if not pd.isna(ma200.iloc[-1]) else 0.0
        high_52w    = float(close.rolling(252).max().iloc[-1])

        # RS Rank (cross-sectional not available here; use stored value)
        rs_rank_val = float(row.get("rs_rank", 50))
        rs_norm = (rs_rank_val / 99.0) * 100.0

        # OBV breakout
        obv_score = float(obv_breakout_score(close, volume).iloc[-1])

        # High proximity
        hp_score = float(high_proximity_score(close).iloc[-1])

        # ATR contraction
        ac_score = float(atr_contraction_score(atr14).iloc[-1])

        # Volume expansion
        ve_score = float(volume_expansion_score(volume).iloc[-1])

        # STA
        spy_aligned = spy_close.reindex(close.index, method="ffill")
        sta_series = sta(close, spy_aligned)
        sta_val = float(sta_series.iloc[-1]) if not pd.isna(sta_series.iloc[-1]) else 0.0

        # STA percentile requires universe — use 50 as neutral default in single-stock context
        sta_pct = float(row.get("sta_percentile", 50))

        # VCP
        vcp_ok = bool(vcp_pass(close, high, volume, atr14).iloc[-1])

        features = StockFeatures(
            symbol=sym,
            rs_rank=rs_rank_val,
            rs_rank_normalized=rs_norm,
            obv_breakout=obv_score,
            high_proximity=hp_score,
            atr_contraction=ac_score,
            volume_expansion=ve_score,
            sta_value=sta_val,
            sta_percentile=sta_pct,
            vcp_ok=vcp_ok,
            atr_14=cur_atr14,
            price=cur_price,
            price_50dma=cur_ma50,
            price_200dma=cur_ma200,
            high_52w=high_52w,
            adtv_20d=float(row.get("adtv_20d", 0)),
        )

        mom_score = calc_momentum_score(features)

        # Entry price: use current close as suggested entry (pivot / breakout)
        entry_price = cur_price
        stop_price = _structural_stop(
            entry_price, cur_atr14, basket,
            swing_low=float(low.rolling(20).min().iloc[-1]),
        )
        rps = entry_price - stop_price

        etype = _entry_type(vcp_ok, hp_score, sta_val)

        results.append(MomentumResult(
            symbol=sym,
            momentum_score=mom_score,
            rs_rank=rs_rank_val,
            vcp_pass=vcp_ok,
            entry_type=etype,
            suggested_entry=round(entry_price, 2),
            structural_stop=round(stop_price, 2),
            risk_per_share=round(rps, 4),
            atr_14=round(cur_atr14, 4),
            basket=basket,
            block_reason=None,
        ))

    # Sort by momentum score descending
    results.sort(key=lambda r: r.momentum_score, reverse=True)
    return results


def apply_candidate_limit(results: list[MomentumResult],
                           regime: str, config: dict) -> list[MomentumResult]:
    """Trim results to regime-appropriate candidate count (max)."""
    limit_map = config.get("candidate_count", {})
    limits = limit_map.get(regime, [0, 20])
    max_count = limits[1]
    return [r for r in results if r.block_reason is None][:max_count]
