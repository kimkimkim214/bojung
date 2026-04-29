"""
EOD report generator.
Outputs three CSV files per trading day:
  reports/eod/YYYY-MM-DD_market_status.csv
  reports/eod/YYYY-MM-DD_candidates.csv
  reports/eod/YYYY-MM-DD_blocked.csv
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from datetime import date

import pandas as pd

from src.regime_scores import MarketScores
from src.regime_fsm import regime_label, StreakState
from src.momentum_scanner import MomentumResult
from src.position_sizer import SizeResult

_REPORT_DIR = Path(__file__).resolve().parents[1] / "reports" / "eod"
_REPORT_DIR.mkdir(parents=True, exist_ok=True)


# ── Market Status ────────────────────────────────────────────────────────────────

def _overshoot_tier(score: float) -> str:
    if score < 60:   return "Healthy (<60)"
    if score < 75:   return "Caution (60–75)"
    return "Overheated (≥75)"


def build_market_status_row(
    signal_date: date,
    execution_date: date,
    regime: str,
    scores: MarketScores,
    streaks: StreakState,
    config: dict,
    survivorship_bias_warning: bool = True,
) -> dict:
    candidate_range = config.get("candidate_count", {}).get(regime, [0, 0])
    risk_budget     = config.get("regime_total_risk_budget", {}).get(regime, 0)
    rpt             = config.get("regime_risk_per_trade", {}).get(regime, 0)

    return {
        "signal_date":        signal_date.isoformat(),
        "execution_date":     execution_date.isoformat(),
        "regime":             regime,
        "fast_risk_score":    round(scores.fast_risk, 1),
        "slow_risk_score":    round(scores.slow_risk, 1),
        "risk_on_score":      round(scores.risk_on, 1),
        "overshoot_score":    round(scores.overshoot, 1),
        "hy_spread_stress":   round(scores.hy_spread_stress, 1),
        "spy_200dma_break":   round(scores.spy_200dma_break, 1),
        "risk_off_confirmed": scores.slow_risk >= 70 and (
            scores.hy_spread_stress >= 60 or scores.spy_200dma_break >= 50
        ),
        "overshoot_tier":         _overshoot_tier(scores.overshoot),
        "allowed_position_min":   candidate_range[0],
        "allowed_position_max":   candidate_range[1],
        "allowed_risk_budget_pct": f"{risk_budget*100:.1f}%",
        "single_trade_risk_pct":   f"{rpt*100:.3f}%",
        "fast_risk_lt60_streak":   streaks.fast_risk_lt_60,
        "risk_off_confirmed_streak": streaks.risk_off_confirmed_days,
        "risk_off_release_streak": streaks.risk_off_release_days,
        "notes": "Breadth = 현재 SPX 구성 기준 (Survivorship Bias 가능)" if survivorship_bias_warning else "",
    }


def write_market_status(row: dict, signal_date: date) -> Path:
    path = _REPORT_DIR / f"{signal_date.isoformat()}_market_status.csv"
    pd.DataFrame([row]).to_csv(path, index=False)
    return path


# ── Candidates ───────────────────────────────────────────────────────────────────

def build_candidate_row(
    signal_date: date,
    execution_date: date,
    mr: MomentumResult,
    sr: SizeResult,
    pead_flag: Optional[str] = None,
) -> dict:
    return {
        "signal_date":      signal_date.isoformat(),
        "execution_date":   execution_date.isoformat(),
        "symbol":           mr.symbol,
        "basket":           mr.basket,
        "momentum_score":   round(mr.momentum_score, 2),
        "rs_rank":          round(mr.rs_rank, 1),
        "vcp_pass":         mr.vcp_pass,
        "pead_flag":        pead_flag or "None",
        "entry_type":       mr.entry_type,
        "suggested_entry":  mr.suggested_entry,
        "structural_stop":  mr.structural_stop,
        "risk_per_share":   mr.risk_per_share,
        "model_qty":        sr.model_qty,
        "blocked_reason":   sr.block_reason or "None",
    }


def write_candidates(rows: list[dict], signal_date: date) -> Path:
    path = _REPORT_DIR / f"{signal_date.isoformat()}_candidates.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


# ── Blocked ──────────────────────────────────────────────────────────────────────

def build_blocked_row(
    signal_date: date,
    execution_date: date,
    symbol: str,
    basket: Optional[str],
    block_reason: str,
    momentum_score: float = 0.0,
    rs_rank: float = 0.0,
) -> dict:
    return {
        "signal_date":    signal_date.isoformat(),
        "execution_date": execution_date.isoformat(),
        "symbol":         symbol,
        "basket":         basket or "",
        "momentum_score": round(momentum_score, 2),
        "rs_rank":        round(rs_rank, 1),
        "block_reason":   block_reason,
    }


def write_blocked(rows: list[dict], signal_date: date) -> Path:
    path = _REPORT_DIR / f"{signal_date.isoformat()}_blocked.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


# ── Console summary ──────────────────────────────────────────────────────────────

def print_market_summary(status: dict) -> None:
    print(f"\n{'='*60}")
    print(f"[Market Status — {status['signal_date']}]")
    print(f"{'='*60}")
    print(f"  Regime              : {status['regime']}")
    print(f"  Fast Risk Score     : {status['fast_risk_score']}")
    print(f"  Slow Risk Score     : {status['slow_risk_score']}")
    print(f"  Risk-On Score       : {status['risk_on_score']}")
    print(f"  Overshoot Score     : {status['overshoot_score']}")
    print(f"  Risk-Off Confirmed  : {status['risk_off_confirmed']}")
    print(f"  Overshoot Tier      : {status['overshoot_tier']}")
    print(f"  Allowed Positions   : {status['allowed_position_min']}~{status['allowed_position_max']}")
    print(f"  Risk Budget         : {status['allowed_risk_budget_pct']} / {status['single_trade_risk_pct']} per trade")
    if status.get("notes"):
        print(f"  Notes               : {status['notes']}")
    print(f"{'='*60}\n")
