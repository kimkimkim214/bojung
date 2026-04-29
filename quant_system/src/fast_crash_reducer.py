"""
Fast Crash position reduction logic with tier-based priority.
Tier assignment uses an `assigned` set to prevent double-counting.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class PositionAction:
    symbol: str
    action: str        # "CLOSE" / "REDUCE_50" / "REDUCE_25" / "TIGHTEN_TRAIL" / "BLOCK_NEW"
    tier: str
    reason: str


def fast_crash_reduce(
    positions: pd.DataFrame,
    fast_risk_score: float,
) -> list[PositionAction]:
    """
    Assign each position to exactly one tier (highest priority first).
    Returns a list of PositionAction describing what to do with each position.

    positions columns expected:
      symbol, basket, pnl_pct, beta_spy, days_to_earnings,
      downside_beta, rs_rank_5d_change, rs_rank, r_multiple
    """
    if positions.empty:
        return []

    assigned: set[str] = set()
    tier_members: dict[str, list[str]] = {
        "tier1": [], "tier2": [], "tier3": [],
        "tier4": [], "tier5": [], "tier6": [],
    }

    def assign(sym: str, tier: str) -> None:
        if sym not in assigned:
            tier_members[tier].append(sym)
            assigned.add(sym)

    for _, row in positions.iterrows():
        sym = row["symbol"]
        # Tier 1: Turnaround basket
        if row.get("basket") == "Turnaround":
            assign(sym, "tier1")
            continue
        # Tier 2: losing + high beta
        if row.get("pnl_pct", 0) < 0 and row.get("beta_spy", 0) > 1.3:
            assign(sym, "tier2")
            continue
        # Tier 3: earnings within 5 days
        if 0 <= row.get("days_to_earnings", 999) <= 5:
            assign(sym, "tier3")
            continue
        # Tier 4: high downside beta
        if row.get("downside_beta", 0) >= 1.3:
            assign(sym, "tier4")
            continue
        # Tier 5: RS Rank dropped ≥10 in 5 days
        if row.get("rs_rank_5d_change", 0) <= -10:
            assign(sym, "tier5")
            continue
        # Tier 6: core leader (last to trim)
        if row.get("rs_rank", 0) >= 85 and row.get("r_multiple", 0) >= 1.0:
            assign(sym, "tier6")

    actions: list[PositionAction] = []

    if fast_risk_score >= 75:
        for tier in ["tier1", "tier2", "tier3"]:
            for sym in tier_members[tier]:
                actions.append(PositionAction(sym, "CLOSE", tier,
                                              f"Fast Crash ≥75: close {tier}"))
        for tier in ["tier4", "tier5"]:
            for sym in tier_members[tier]:
                actions.append(PositionAction(sym, "REDUCE_50", tier,
                                              f"Fast Crash ≥75: reduce 50% {tier}"))
        for sym in tier_members["tier6"]:
            actions.append(PositionAction(sym, "TIGHTEN_TRAIL", "tier6",
                                          "Fast Crash ≥75: tighten trail (ATR×1.5)"))

    elif fast_risk_score >= 60:
        for tier in ["tier1", "tier2", "tier3"]:
            for sym in tier_members[tier]:
                actions.append(PositionAction(sym, "REDUCE_50", tier,
                                              f"Fast Crash 60–75: reduce 50% {tier}"))
        for tier in ["tier4", "tier5"]:
            for sym in tier_members[tier]:
                actions.append(PositionAction(sym, "REDUCE_25", tier,
                                              f"Fast Crash 60–75: reduce 25% {tier}"))
        for sym in tier_members["tier6"]:
            actions.append(PositionAction(sym, "BLOCK_NEW", "tier6",
                                          "Fast Crash 60–75: block new only"))

    return actions
