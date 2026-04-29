"""
Unit tests for position sizer.
Tests: size_position(), block reasons, quantity caps.
"""
import pytest
from src.position_sizer import (
    size_position, build_capacity_state, CapacityState,
    SIGNAL_INVALID, SKIP,
)
import pandas as pd


def make_caps(
    gross=100_000, risk_budget=10_000,
    sector=25_000, industry=20_000, megacap=40_000,
) -> CapacityState:
    return CapacityState(
        gross_remaining=gross,
        total_risk_budget_remaining=risk_budget,
        sector_remaining=sector,
        industry_remaining=industry,
        megacap_remaining=megacap,
    )


PAPER_CONFIG = {
    "equity": 100_000,
    "gross_capacity": 100_000,
    "regime_risk_per_trade": {
        "HEALTHY_RISK_ON": 0.0125,
        "NORMAL_RISK_ON": 0.010,
        "CAUTION": 0.005,
        "FAST_CRASH": 0.0,
        "RISK_OFF": 0.0,
        "OVERHEATED_RISK_ON": 0.0,
    },
    "regime_total_risk_budget": {
        "HEALTHY_RISK_ON": 0.10,
        "NORMAL_RISK_ON": 0.07,
        "CAUTION": 0.025,
    },
    "max_position_weight": 0.10,
}


def test_basic_healthy():
    r = size_position(
        symbol="AAPL", equity=100_000,
        entry_price=100, stop_price=95,
        regime="HEALTHY_RISK_ON",
        caps=make_caps(),
        config=PAPER_CONFIG,
    )
    assert r.block_reason is None
    assert r.model_qty > 0
    # Risk = qty * (100 - 95) ≤ equity * 1.25%
    assert r.model_qty * 5 <= 100_000 * 0.0125


def test_signal_invalid_when_stop_above_entry():
    r = size_position(
        symbol="TSLA", equity=100_000,
        entry_price=100, stop_price=110,  # stop > entry!
        regime="HEALTHY_RISK_ON",
        caps=make_caps(), config=PAPER_CONFIG,
    )
    assert r.block_reason == "SIGNAL_INVALID"
    assert r.model_qty == 0


def test_regime_block_fast_crash():
    r = size_position(
        symbol="META", equity=100_000,
        entry_price=300, stop_price=285,
        regime="FAST_CRASH",
        caps=make_caps(), config=PAPER_CONFIG,
    )
    assert r.block_reason == "REGIME_BLOCK_FAST_CRASH"


def test_regime_block_risk_off():
    r = size_position(
        symbol="NVDA", equity=100_000,
        entry_price=200, stop_price=190,
        regime="RISK_OFF",
        caps=make_caps(), config=PAPER_CONFIG,
    )
    assert r.block_reason == "REGIME_BLOCK_RISK_OFF"


def test_regime_block_overheated():
    r = size_position(
        symbol="AMZN", equity=100_000,
        entry_price=150, stop_price=142,
        regime="OVERHEATED_RISK_ON",
        caps=make_caps(), config=PAPER_CONFIG,
    )
    assert r.block_reason == "REGIME_BLOCK_OVERHEATED"


def test_gross_full():
    r = size_position(
        symbol="AAPL", equity=100_000,
        entry_price=100, stop_price=95,
        regime="HEALTHY_RISK_ON",
        caps=make_caps(gross=0),   # no capacity
        config=PAPER_CONFIG,
    )
    assert r.block_reason == "GROSS_FULL"


def test_earnings_proximity_block():
    r = size_position(
        symbol="MSFT", equity=100_000,
        entry_price=300, stop_price=285,
        regime="HEALTHY_RISK_ON",
        caps=make_caps(), config=PAPER_CONFIG,
        days_to_earnings=3,
    )
    assert r.block_reason == "EARNINGS_PROXIMITY"


def test_rs_rank_insufficient():
    r = size_position(
        symbol="XYZ", equity=100_000,
        entry_price=50, stop_price=47,
        regime="HEALTHY_RISK_ON",
        caps=make_caps(), config=PAPER_CONFIG,
        rs_rank=65,   # below 70
    )
    assert r.block_reason == "RS_INSUFFICIENT"


def test_price_below_ma():
    r = size_position(
        symbol="XYZ", equity=100_000,
        entry_price=50, stop_price=47,
        regime="HEALTHY_RISK_ON",
        caps=make_caps(), config=PAPER_CONFIG,
        above_50dma=False,
    )
    assert r.block_reason == "PRICE_BELOW_MA"


def test_lookback_insufficient():
    r = size_position(
        symbol="NEWCO", equity=100_000,
        entry_price=50, stop_price=47,
        regime="HEALTHY_RISK_ON",
        caps=make_caps(), config=PAPER_CONFIG,
        has_sufficient_history=False,
    )
    assert r.block_reason == "LOOKBACK_INSUFFICIENT"


def test_max_position_weight_cap():
    # Entry $100, equity $100k → max 10% = $10k = 100 shares
    r = size_position(
        symbol="AAPL", equity=100_000,
        entry_price=100, stop_price=1,   # tiny risk/share → raw_qty very large
        regime="HEALTHY_RISK_ON",
        caps=make_caps(risk_budget=10_000_000),   # no risk constraint
        config=PAPER_CONFIG,
    )
    assert r.model_qty <= 100   # capped at 10% weight


def test_build_capacity_state_empty_positions():
    caps = build_capacity_state(
        equity=100_000,
        config=PAPER_CONFIG,
        existing_positions=pd.DataFrame(),
        regime="HEALTHY_RISK_ON",
    )
    assert caps.gross_remaining == 100_000
    assert caps.total_risk_budget_remaining == pytest.approx(10_000, rel=0.01)
