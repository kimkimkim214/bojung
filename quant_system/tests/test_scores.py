"""
Unit tests for regime score calculators.
Verifies that all score functions:
  1. Return values in [0, 100]
  2. Return expected boundary values
"""
import pytest
from src.regime_scores import (
    calc_fast_risk_score, calc_slow_risk_score,
    calc_risk_on_score, calc_overshoot_score,
    evaluate_risk_off,
)
from src.utils.clip import clip_score


# ── clip_score ───────────────────────────────────────────────────────────────────

def test_clip_score_bounds():
    assert clip_score(-10) == 0
    assert clip_score(110) == 100
    assert clip_score(50) == 50
    assert clip_score(0) == 0
    assert clip_score(100) == 100


# ── Fast Risk Score ──────────────────────────────────────────────────────────────

def test_fast_risk_all_zero():
    score = calc_fast_risk_score(
        vix=15, vix_3d_change=0.05,
        spy_3d_return=0.01,
        qqq_close=100, qqq_20dma=95,   # above MA
        gap_down_breadth=0.02,
    )
    assert 0 <= score <= 100
    assert score == 0.0  # all sub-scores zero


def test_fast_risk_max():
    score = calc_fast_risk_score(
        vix=30, vix_3d_change=0.30,
        spy_3d_return=-0.05,
        qqq_close=85, qqq_20dma=100,  # well below MA
        gap_down_breadth=0.25,
    )
    assert score == 100.0


def test_fast_risk_triggers_fast_crash():
    score = calc_fast_risk_score(
        vix=28, vix_3d_change=0.28,
        spy_3d_return=-0.045,
        qqq_close=88, qqq_20dma=100,
        gap_down_breadth=0.22,
    )
    assert score >= 75, f"Expected ≥75, got {score}"


def test_fast_risk_always_in_range():
    import random
    for _ in range(50):
        s = calc_fast_risk_score(
            vix=random.uniform(10, 50),
            vix_3d_change=random.uniform(-0.1, 0.5),
            spy_3d_return=random.uniform(-0.08, 0.05),
            qqq_close=random.uniform(50, 500),
            qqq_20dma=random.uniform(50, 500),
            gap_down_breadth=random.uniform(0, 1),
        )
        assert 0 <= s <= 100, f"Out of range: {s}"


# ── Slow Risk Score ──────────────────────────────────────────────────────────────

def test_slow_risk_benign():
    score, hy, spy = calc_slow_risk_score(
        hy_spread_now=380, hy_spread_60d_avg=400,
        hy_spread_20d_delta=10,
        spy_close=450, spy_200dma=420,
        gold_close=170, gold_100dma=180,
        gold_20d_momentum=-0.02,
        tlt_close=95, tlt_60dma=100,
        tlt_20d_momentum=-0.01,
        yield_10y_3m_spread_bp=150,
    )
    assert 0 <= score <= 100
    assert score < 50, f"Expected benign score < 50, got {score}"


def test_slow_risk_stressed():
    score, hy, spy = calc_slow_risk_score(
        hy_spread_now=600, hy_spread_60d_avg=400,
        hy_spread_20d_delta=60,
        spy_close=390, spy_200dma=450,
        gold_close=200, gold_100dma=180,
        gold_20d_momentum=0.05,
        tlt_close=110, tlt_60dma=100,
        tlt_20d_momentum=0.03,
        yield_10y_3m_spread_bp=-80,
    )
    assert score >= 70, f"Expected stressed score ≥70, got {score}"


def test_risk_off_evaluation():
    assert evaluate_risk_off(75, 65, 40) is True
    assert evaluate_risk_off(75, 50, 55) is True
    assert evaluate_risk_off(65, 65, 55) is False  # slow_risk < 70
    assert evaluate_risk_off(75, 50, 40) is False  # neither companion ≥ threshold


# ── Risk-On Score ────────────────────────────────────────────────────────────────

def test_risk_on_healthy():
    score = calc_risk_on_score(
        spy_50dma=440, spy_200dma=420, spy_50dma_slope=0.005, spy_close=450,
        vix=13, vix_20d_std=1.5,
        pct_above_50dma=0.75, pct_above_200dma=0.80,
        nh_nl_ratio=0.3, mclellan=50,
        pct_rs_above_70=0.35,
        hy_oas_20d_change_bp=-25,
    )
    assert score >= 75, f"Expected Healthy ≥75, got {score}"


def test_risk_on_weak():
    score = calc_risk_on_score(
        spy_50dma=380, spy_200dma=430,  # death cross
        spy_50dma_slope=-0.01, spy_close=370,
        vix=28, vix_20d_std=7,
        pct_above_50dma=0.30, pct_above_200dma=0.25,
        nh_nl_ratio=-0.4, mclellan=-60,
        pct_rs_above_70=0.05,
        hy_oas_20d_change_bp=45,
    )
    assert score < 35, f"Expected weak score < 35, got {score}"


# ── Overshoot Score ──────────────────────────────────────────────────────────────

def test_overshoot_calm():
    score = calc_overshoot_score(
        qqq_close=100, qqq_ma20=98, qqq_rsi=55, qqq_ret20=0.03,
        qqq_gaps=0, qqq_trend=0.03, qqq_breadth_chg=0.02, qqq_bonus=0,
        spy_close=100, spy_ma20=98, spy_rsi=55, spy_ret20=0.02,
        spy_gaps=0, spy_trend=0.02, spy_breadth_chg=0.02, spy_bonus=0,
    )
    assert score < 40, f"Expected calm score < 40, got {score}"


def test_overshoot_extreme():
    score = calc_overshoot_score(
        qqq_close=115, qqq_ma20=100, qqq_rsi=82, qqq_ret20=0.20,
        qqq_gaps=5, qqq_trend=0.20, qqq_breadth_chg=-0.15, qqq_bonus=3,
        spy_close=115, spy_ma20=100, spy_rsi=78, spy_ret20=0.18,
        spy_gaps=4, spy_trend=0.18, spy_breadth_chg=-0.12, spy_bonus=2,
    )
    assert score >= 75, f"Expected overheated score ≥75, got {score}"
