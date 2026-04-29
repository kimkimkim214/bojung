"""
Position sizer: computes model_qty given entry/stop/regime/caps.
Long-only cash equities only (Phase 1 paper mode).
"""
from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Optional, Literal

import pandas as pd

from src.regime_fsm import (
    is_entry_allowed, risk_per_trade, total_risk_budget,
)

# ── Constants ────────────────────────────────────────────────────────────────────

SIGNAL_INVALID = -1
SKIP = 0

BlockReason = Literal[
    "SIGNAL_INVALID",
    "GROSS_FULL",
    "RISK_BUDGET_FULL",
    "SECTOR_CAP",
    "INDUSTRY_CAP",
    "MEGACAP_CAP",
    "EARNINGS_PROXIMITY",
    "EARNINGS_TIME_UNKNOWN",
    "PEAD_EVENT_USED",
    "REGIME_BLOCK_OVERHEATED",
    "REGIME_BLOCK_RISK_OFF",
    "REGIME_BLOCK_FAST_CRASH",
    "RS_INSUFFICIENT",
    "LIQUIDITY_INSUFFICIENT",
    "PRICE_BELOW_MA",
    "QTY_LT_1",
    "LOOKBACK_INSUFFICIENT",
]


@dataclass
class CapacityState:
    gross_remaining: float       # dollars remaining for gross exposure
    total_risk_budget_remaining: float  # dollars remaining for risk budget
    sector_remaining: float      # dollars remaining for this sector
    industry_remaining: float    # dollars remaining for this industry
    megacap_remaining: float     # dollars remaining for megacap bucket


@dataclass
class SizeResult:
    symbol: str
    model_qty: int
    block_reason: Optional[str]
    risk_budget_used: float
    gross_used: float


def _regime_block_reason(regime: str) -> Optional[str]:
    if regime == "FAST_CRASH":
        return "REGIME_BLOCK_FAST_CRASH"
    if regime == "RISK_OFF":
        return "REGIME_BLOCK_RISK_OFF"
    if regime == "OVERHEATED_RISK_ON":
        return "REGIME_BLOCK_OVERHEATED"
    return None


def size_position(
    symbol: str,
    equity: float,
    entry_price: float,
    stop_price: float,
    regime: str,
    caps: CapacityState,
    config: dict,
    is_megacap: bool = False,
    days_to_earnings: Optional[int] = None,
    earnings_timing_known: bool = True,
    rs_rank: float = 99,
    above_50dma: bool = True,
    above_200dma: bool = True,
    has_sufficient_history: bool = True,
) -> SizeResult:
    """
    Compute model quantity for one position.
    Returns SizeResult with model_qty and optional block_reason.
    """

    # ── Pre-checks (before any math) ────────────────────────────────────────────

    if not has_sufficient_history:
        return SizeResult(symbol, 0, "LOOKBACK_INSUFFICIENT", 0, 0)

    block = _regime_block_reason(regime)
    if block:
        return SizeResult(symbol, 0, block, 0, 0)

    if not above_50dma or not above_200dma:
        return SizeResult(symbol, 0, "PRICE_BELOW_MA", 0, 0)

    if rs_rank < 70:
        return SizeResult(symbol, 0, "RS_INSUFFICIENT", 0, 0)

    if days_to_earnings is not None and days_to_earnings <= 5:
        return SizeResult(symbol, 0, "EARNINGS_PROXIMITY", 0, 0)

    if not earnings_timing_known:
        return SizeResult(symbol, 0, "EARNINGS_TIME_UNKNOWN", 0, 0)

    risk_per_share = entry_price - stop_price
    if risk_per_share <= 0:
        return SizeResult(symbol, 0, "SIGNAL_INVALID", 0, 0)

    if caps.gross_remaining <= 0:
        return SizeResult(symbol, 0, "GROSS_FULL", 0, 0)

    if caps.total_risk_budget_remaining <= 0:
        return SizeResult(symbol, 0, "RISK_BUDGET_FULL", 0, 0)

    # ── Quantity computation ─────────────────────────────────────────────────────

    max_pos_weight = config.get("max_position_weight", 0.10)
    rpt = risk_per_trade(regime, config)
    risk_budget_dollar = equity * rpt

    raw_qty          = risk_budget_dollar / risk_per_share
    max_weight_qty   = (equity * max_pos_weight) / entry_price
    sector_qty       = caps.sector_remaining / entry_price
    industry_qty     = caps.industry_remaining / entry_price
    gross_qty        = caps.gross_remaining / entry_price
    risk_pool_qty    = caps.total_risk_budget_remaining / risk_per_share

    megacap_qty = float("inf")
    if is_megacap and caps.megacap_remaining is not None:
        megacap_qty = caps.megacap_remaining / entry_price

    final_qty = floor(min(
        raw_qty, max_weight_qty,
        sector_qty, industry_qty,
        gross_qty, risk_pool_qty,
        megacap_qty,
    ))

    if final_qty < 1:
        # Determine most restrictive constraint
        if sector_qty < 1:
            return SizeResult(symbol, 0, "SECTOR_CAP", 0, 0)
        if industry_qty < 1:
            return SizeResult(symbol, 0, "INDUSTRY_CAP", 0, 0)
        if is_megacap and megacap_qty < 1:
            return SizeResult(symbol, 0, "MEGACAP_CAP", 0, 0)
        return SizeResult(symbol, 0, "QTY_LT_1", 0, 0)

    gross_used      = final_qty * entry_price
    risk_used       = final_qty * risk_per_share

    return SizeResult(
        symbol=symbol,
        model_qty=final_qty,
        block_reason=None,
        risk_budget_used=risk_used,
        gross_used=gross_used,
    )


def build_capacity_state(equity: float, config: dict,
                          existing_positions: pd.DataFrame,
                          regime: str) -> CapacityState:
    """
    Compute remaining capacity buckets given existing positions.
    """
    gross_cap = config.get("gross_capacity", equity)
    total_risk_pct = total_risk_budget(regime, config)
    total_risk_dollar = equity * total_risk_pct

    sector_cap_pct    = config.get("sector_capacity_pct", 0.25)
    industry_cap_pct  = config.get("industry_capacity_pct", 0.20)
    megacap_cap_pct   = config.get("megacap_capacity_pct", 0.40)

    if existing_positions.empty:
        return CapacityState(
            gross_remaining=gross_cap,
            total_risk_budget_remaining=total_risk_dollar,
            sector_remaining=equity * sector_cap_pct,
            industry_remaining=equity * industry_cap_pct,
            megacap_remaining=equity * megacap_cap_pct,
        )

    gross_used = (existing_positions["qty"] * existing_positions["entry_price"]).sum()
    risk_used  = (
        existing_positions["qty"] *
        (existing_positions["entry_price"] - existing_positions["stop_price"])
    ).sum()

    return CapacityState(
        gross_remaining=max(0, gross_cap - gross_used),
        total_risk_budget_remaining=max(0, total_risk_dollar - risk_used),
        sector_remaining=equity * sector_cap_pct,    # sector-level computed per-call
        industry_remaining=equity * industry_cap_pct,
        megacap_remaining=equity * megacap_cap_pct,
    )
