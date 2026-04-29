"""
Unit tests for EOD report builder.
Tests: column presence, block reason codes, file creation.
"""
import pytest
from datetime import date
from pathlib import Path
import pandas as pd

from src.regime_scores import MarketScores
from src.regime_fsm import StreakState
from src.momentum_scanner import MomentumResult
from src.position_sizer import SizeResult
from src.eod_report import (
    build_market_status_row, build_candidate_row,
    build_blocked_row, _overshoot_tier,
)

PAPER_CONFIG = {
    "candidate_count": {
        "HEALTHY_RISK_ON": [12, 20],
        "NORMAL_RISK_ON": [8, 15],
    },
    "regime_total_risk_budget": {"HEALTHY_RISK_ON": 0.10},
    "regime_risk_per_trade": {"HEALTHY_RISK_ON": 0.0125},
}

SIG = date(2024, 6, 14)
EXE = date(2024, 6, 17)

SCORES = MarketScores(
    fast_risk=25, slow_risk=22, risk_on=82, overshoot=45,
    hy_spread_stress=30, spy_200dma_break=20,
)
STREAKS = StreakState()


def test_market_status_has_all_required_keys():
    row = build_market_status_row(SIG, EXE, "HEALTHY_RISK_ON", SCORES, STREAKS, PAPER_CONFIG)
    required = [
        "signal_date", "execution_date", "regime",
        "fast_risk_score", "slow_risk_score", "risk_on_score", "overshoot_score",
        "risk_off_confirmed", "overshoot_tier",
        "allowed_position_min", "allowed_position_max",
        "allowed_risk_budget_pct", "single_trade_risk_pct",
    ]
    for key in required:
        assert key in row, f"Missing key: {key}"


def test_overshoot_tier_labels():
    assert _overshoot_tier(30) == "Healthy (<60)"
    assert _overshoot_tier(60) == "Caution (60–75)"
    assert _overshoot_tier(75) == "Overheated (≥75)"
    assert _overshoot_tier(59.9) == "Healthy (<60)"
    assert _overshoot_tier(74.9) == "Caution (60–75)"


def test_risk_off_confirmed_true():
    scores_risk_off = MarketScores(
        fast_risk=30, slow_risk=75, risk_on=40, overshoot=20,
        hy_spread_stress=65, spy_200dma_break=30,
    )
    row = build_market_status_row(SIG, EXE, "RISK_OFF", scores_risk_off, STREAKS, PAPER_CONFIG)
    assert row["risk_off_confirmed"] is True


def test_risk_off_confirmed_false():
    row = build_market_status_row(SIG, EXE, "HEALTHY_RISK_ON", SCORES, STREAKS, PAPER_CONFIG)
    assert row["risk_off_confirmed"] is False


def test_candidate_row_has_14_required_columns():
    mr = MomentumResult(
        symbol="AAPL", momentum_score=78.5, rs_rank=88,
        vcp_pass=True, entry_type="VCP_Breakout",
        suggested_entry=182.50, structural_stop=175.00,
        risk_per_share=7.50, atr_14=6.20,
        basket="Quality Growth",
    )
    sr = SizeResult(symbol="AAPL", model_qty=16, block_reason=None,
                    risk_budget_used=120, gross_used=2920)

    row = build_candidate_row(SIG, EXE, mr, sr, pead_flag=None)

    required_cols = [
        "signal_date", "execution_date", "symbol", "basket",
        "momentum_score", "rs_rank", "vcp_pass", "pead_flag",
        "entry_type", "suggested_entry", "structural_stop",
        "risk_per_share", "model_qty", "blocked_reason",
    ]
    for col in required_cols:
        assert col in row, f"Missing column: {col}"

    assert row["signal_date"] == SIG.isoformat()
    assert row["execution_date"] == EXE.isoformat()
    assert row["model_qty"] == 16
    assert row["blocked_reason"] == "None"


def test_blocked_row_structure():
    row = build_blocked_row(SIG, EXE, "NEWCO", "Quality Growth", "LOOKBACK_INSUFFICIENT")
    assert row["block_reason"] == "LOOKBACK_INSUFFICIENT"
    assert row["symbol"] == "NEWCO"
    assert row["signal_date"] == SIG.isoformat()


VALID_BLOCK_REASONS = {
    "SIGNAL_INVALID", "GROSS_FULL", "RISK_BUDGET_FULL",
    "SECTOR_CAP", "INDUSTRY_CAP", "MEGACAP_CAP",
    "EARNINGS_PROXIMITY", "EARNINGS_TIME_UNKNOWN", "PEAD_EVENT_USED",
    "REGIME_BLOCK_OVERHEATED", "REGIME_BLOCK_RISK_OFF", "REGIME_BLOCK_FAST_CRASH",
    "RS_INSUFFICIENT", "LIQUIDITY_INSUFFICIENT", "PRICE_BELOW_MA",
    "QTY_LT_1", "LOOKBACK_INSUFFICIENT",
}

@pytest.mark.parametrize("reason", list(VALID_BLOCK_REASONS))
def test_all_17_block_reasons_valid(reason):
    row = build_blocked_row(SIG, EXE, "SYM", "Quality Growth", reason)
    assert row["block_reason"] == reason


def test_market_status_signal_execution_date_different():
    row = build_market_status_row(SIG, EXE, "NORMAL_RISK_ON", SCORES, STREAKS, PAPER_CONFIG)
    assert row["signal_date"] != row["execution_date"]
    assert row["signal_date"] == "2024-06-14"
    assert row["execution_date"] == "2024-06-17"
