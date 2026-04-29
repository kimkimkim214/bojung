"""
Regime FSM: update_streaks → resolve_regime.
Must be called AFTER calculate_all_scores().
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.regime_scores import MarketScores, evaluate_risk_off

REGIME = Literal[
    "FAST_CRASH",
    "RISK_OFF",
    "WARNING",
    "CAUTION",
    "NORMAL_RISK_ON",
    "HEALTHY_RISK_ON",
    "OVERHEAT_CAUTION",
    "OVERHEATED_RISK_ON",
]

ALL_REGIMES: list[str] = [
    "FAST_CRASH", "RISK_OFF", "WARNING", "CAUTION",
    "NORMAL_RISK_ON", "HEALTHY_RISK_ON", "OVERHEAT_CAUTION", "OVERHEATED_RISK_ON",
]


@dataclass
class StreakState:
    # consecutive days Fast Risk < 60 (counts toward FAST_CRASH release)
    fast_risk_lt_60: int = 0
    # consecutive days risk-off confirmed (counts toward RISK_OFF entry)
    risk_off_confirmed_days: int = 0
    # consecutive days risk-off NOT confirmed (counts toward RISK_OFF release)
    risk_off_release_days: int = 0


def update_streaks(prev_streaks: StreakState, scores: MarketScores,
                   prev_regime: str) -> StreakState:
    """
    Increment / reset streak counters based on today's scores.
    Must be called BEFORE resolve_regime().
    """
    s = StreakState()

    # Fast Crash release streak
    if scores.fast_risk < 60:
        s.fast_risk_lt_60 = prev_streaks.fast_risk_lt_60 + 1
    else:
        s.fast_risk_lt_60 = 0

    # Risk-Off entry streak
    risk_off_confirmed = evaluate_risk_off(
        scores.slow_risk, scores.hy_spread_stress, scores.spy_200dma_break
    )
    if risk_off_confirmed:
        s.risk_off_confirmed_days = prev_streaks.risk_off_confirmed_days + 1
        s.risk_off_release_days   = 0
    else:
        s.risk_off_confirmed_days = 0
        # Risk-Off release: only increments when we were in RISK_OFF
        if prev_regime == "RISK_OFF":
            s.risk_off_release_days = prev_streaks.risk_off_release_days + 1
        else:
            s.risk_off_release_days = 0

    return s


def resolve_regime(prev_regime: str, scores: MarketScores,
                   streaks: StreakState) -> str:
    """
    Determine today's regime using the hierarchical FSM.
    Expects scores and streaks already computed for today.
    """

    # ── 1순위: Fast Crash ───────────────────────────────────────────────────────
    if scores.fast_risk >= 75:
        return "FAST_CRASH"
    if prev_regime == "FAST_CRASH":
        if streaks.fast_risk_lt_60 < 2:
            return "FAST_CRASH"

    # ── 2순위: Risk-Off ─────────────────────────────────────────────────────────
    risk_off_confirmed = evaluate_risk_off(
        scores.slow_risk, scores.hy_spread_stress, scores.spy_200dma_break
    )
    if risk_off_confirmed and streaks.risk_off_confirmed_days >= 2:
        return "RISK_OFF"
    if prev_regime == "RISK_OFF":
        if streaks.risk_off_release_days < 2:
            return "RISK_OFF"

    # ── 3순위: Risk-On 분기 (히스테리시스) ─────────────────────────────────────
    healthy_threshold = 65 if prev_regime == "HEALTHY_RISK_ON" else 75
    is_strong_risk_on = scores.risk_on >= healthy_threshold

    if is_strong_risk_on:
        if scores.overshoot >= 75:
            return "OVERHEATED_RISK_ON"
        if scores.overshoot >= 60:
            return "OVERHEAT_CAUTION"
        return "HEALTHY_RISK_ON"

    # ── 4순위: Normal Risk-On (히스테리시스) ───────────────────────────────────
    normal_threshold = 45 if prev_regime == "NORMAL_RISK_ON" else 55
    if scores.risk_on >= normal_threshold:
        return "NORMAL_RISK_ON"

    # ── 5순위: Caution (히스테리시스) ──────────────────────────────────────────
    caution_threshold = 25 if prev_regime == "CAUTION" else 35
    if scores.risk_on >= caution_threshold:
        return "CAUTION"

    return "WARNING"


def regime_label(regime: str) -> str:
    labels = {
        "FAST_CRASH":       "Fast Crash  🔴",
        "RISK_OFF":         "Risk-Off    🟠",
        "WARNING":          "Warning     🟡",
        "CAUTION":          "Caution     🟡",
        "NORMAL_RISK_ON":   "Normal      🟢",
        "HEALTHY_RISK_ON":  "Healthy     🟢",
        "OVERHEAT_CAUTION": "Overheat ⚠️  🟡",
        "OVERHEATED_RISK_ON": "Overheated 🔴",
    }
    return labels.get(regime, regime)


def is_entry_allowed(regime: str) -> bool:
    return regime not in {"FAST_CRASH", "RISK_OFF", "OVERHEATED_RISK_ON"}


def risk_per_trade(regime: str, config: dict) -> float:
    return config.get("regime_risk_per_trade", {}).get(regime, 0.0)


def total_risk_budget(regime: str, config: dict) -> float:
    return config.get("regime_total_risk_budget", {}).get(regime, 0.0)
