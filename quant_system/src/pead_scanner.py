"""
PEAD (Post-Earnings Announcement Drift) scanner.
Handles gap measurement, event_id generation, size policy, and persistence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, Literal

import pandas as pd

from src.utils.clip import clip_score
from src.utils.persistence import is_pead_event_used, record_pead_event

EarningsTiming = Literal["BMO", "AMC", "Unknown"]


@dataclass
class EarningsEvent:
    symbol: str
    earnings_date: str        # YYYY-MM-DD (date of announcement)
    fiscal_period: Optional[str]  # e.g. "Q1FY2026"
    timing: EarningsTiming
    confirmed_dt: Optional[datetime] = None


@dataclass
class PEADCandidate:
    symbol: str
    event_id: str
    gap_pct: float            # positive = gap up
    volume_ratio: float       # vs 20-day average
    close_range_pct: float    # close position within day range (0=low, 1=high)
    rs_rank_change: float     # RS rank change since pre-earnings
    pead_flag: str            # "Healthy_PEAD" / "Overheated_PEAD" / "Pullback_PEAD"
    size_policy: str          # "Full" / "Half" / "Pullback_Half" / "Blocked"
    block_reason: Optional[str] = None
    basket: str = "Quality Growth"


def make_event_id(symbol: str, fiscal_period: Optional[str],
                   earnings_date: str,
                   confirmed_dt: Optional[datetime] = None) -> str:
    if fiscal_period:
        return f"{symbol}_{fiscal_period}_{earnings_date}"
    if confirmed_dt:
        return f"{symbol}_{confirmed_dt.date().isoformat()}"
    return f"{symbol}_{earnings_date}"


def _gap_percent(pre_close: float, post_open: float) -> float:
    if pre_close <= 0:
        return 0.0
    return (post_open / pre_close) - 1.0


def _close_range_position(open_: float, high: float, low: float, close: float) -> float:
    """Where in the day's range did the stock close? 0 = at low, 1 = at high."""
    rng = high - low
    if rng <= 0:
        return 0.5
    return (close - low) / rng


def _determine_pead_flag(gap_pct: float, overshoot_score: float) -> str:
    if overshoot_score >= 60 or gap_pct >= 0.25:
        return "Overheated_PEAD"
    if gap_pct >= 0.05:
        return "Healthy_PEAD"
    return "Pullback_PEAD"


def _determine_size_policy(gap_pct: float, overshoot_score: float,
                            market_breadth_weak: bool) -> str:
    """
    Returns size policy string per spec section 2-5.
    Healthy Risk-On + Overshoot < 60 + gap 5–15% → Full
    Gap 15–20% or some breadth weakness → Half
    Gap 20–25% → Pullback_Half (wait 3–5 days)
    Overshoot ≥ 60 or gap ≥ 25% or QQQ overheat → Blocked
    """
    if overshoot_score >= 60 or gap_pct >= 0.25:
        return "Blocked"
    if gap_pct >= 0.20:
        return "Pullback_Half"
    if gap_pct >= 0.15 or market_breadth_weak:
        return "Half"
    return "Full"


def scan_pead_candidates(
    earnings_events: list[EarningsEvent],
    price_on_date: dict[str, dict],   # symbol → {pre_close, post_open, high, low, close, volume}
    adtv_20d: dict[str, float],
    rs_rank_current: dict[str, float],
    rs_rank_pre: dict[str, float],
    regime: str,
    overshoot_score: float,
    market_breadth_weak: bool,
    basket_map: dict[str, str],
) -> list[PEADCandidate]:
    """
    Screen post-earnings gap candidates.
    Only processes events where timing != "Unknown".
    """
    results = []

    for event in earnings_events:
        sym = event.symbol

        if event.timing == "Unknown":
            results.append(PEADCandidate(
                symbol=sym,
                event_id=make_event_id(sym, event.fiscal_period, event.earnings_date),
                gap_pct=0.0, volume_ratio=0.0, close_range_pct=0.0,
                rs_rank_change=0.0,
                pead_flag="", size_policy="Blocked",
                block_reason="EARNINGS_TIME_UNKNOWN",
                basket=basket_map.get(sym, "Quality Growth"),
            ))
            continue

        event_id = make_event_id(
            sym, event.fiscal_period, event.earnings_date, event.confirmed_dt
        )

        if is_pead_event_used(event_id):
            results.append(PEADCandidate(
                symbol=sym, event_id=event_id,
                gap_pct=0.0, volume_ratio=0.0, close_range_pct=0.0,
                rs_rank_change=0.0,
                pead_flag="", size_policy="Blocked",
                block_reason="PEAD_EVENT_USED",
                basket=basket_map.get(sym, "Quality Growth"),
            ))
            continue

        prices = price_on_date.get(sym)
        if prices is None:
            continue

        gap_pct = _gap_percent(prices["pre_close"], prices["post_open"])

        # Minimum gap requirement: ≥5%
        if gap_pct < 0.05:
            continue

        vol_ratio = (
            prices["volume"] / adtv_20d[sym] if adtv_20d.get(sym, 0) > 0 else 0.0
        )
        # Require volume ≥ 2x
        if vol_ratio < 2.0:
            continue

        crp = _close_range_position(
            prices["post_open"], prices["high"], prices["low"], prices["close"]
        )
        # Require close in upper 25% of range
        if crp < 0.75:
            continue

        rs_chg = rs_rank_current.get(sym, 50) - rs_rank_pre.get(sym, 50)
        # Require RS improving
        if rs_chg <= 0:
            continue

        flag = _determine_pead_flag(gap_pct, overshoot_score)
        policy = _determine_size_policy(gap_pct, overshoot_score, market_breadth_weak)

        results.append(PEADCandidate(
            symbol=sym,
            event_id=event_id,
            gap_pct=gap_pct,
            volume_ratio=vol_ratio,
            close_range_pct=crp,
            rs_rank_change=rs_chg,
            pead_flag=flag,
            size_policy=policy,
            block_reason=None,
            basket=basket_map.get(sym, "Quality Growth"),
        ))

    return results


def register_pead_entry(event_id: str) -> None:
    """Persist the event so the same id cannot be re-entered."""
    record_pead_event(event_id, result="entered")
