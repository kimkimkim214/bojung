"""
Unit tests for the Regime FSM.
Tests: update_streaks, resolve_regime, FSM transitions, hysteresis.
"""
import pytest
from src.regime_scores import MarketScores
from src.regime_fsm import StreakState, update_streaks, resolve_regime


def make_scores(fast=20, slow=20, risk_on=80, overshoot=30,
                hy=30, spy200=20) -> MarketScores:
    return MarketScores(
        fast_risk=fast, slow_risk=slow,
        risk_on=risk_on, overshoot=overshoot,
        hy_spread_stress=hy, spy_200dma_break=spy200,
    )


def zero_streaks() -> StreakState:
    return StreakState()


# ── update_streaks ────────────────────────────────────────────────────────────────

def test_streak_fast_crash_release_increments():
    prev = StreakState(fast_risk_lt_60=1)
    scores = make_scores(fast=50)  # < 60
    new = update_streaks(prev, scores, "FAST_CRASH")
    assert new.fast_risk_lt_60 == 2


def test_streak_fast_crash_release_resets_when_above_60():
    prev = StreakState(fast_risk_lt_60=3)
    scores = make_scores(fast=65)  # ≥ 60
    new = update_streaks(prev, scores, "FAST_CRASH")
    assert new.fast_risk_lt_60 == 0


def test_streak_risk_off_confirm_increments():
    prev = StreakState(risk_off_confirmed_days=1)
    # slow_risk ≥ 70 AND hy_spread_stress ≥ 60
    scores = make_scores(slow=75, hy=65)
    new = update_streaks(prev, scores, "NORMAL_RISK_ON")
    assert new.risk_off_confirmed_days == 2
    assert new.risk_off_release_days == 0


def test_streak_risk_off_release_increments_only_in_risk_off():
    prev = StreakState(risk_off_release_days=0)
    scores = make_scores(slow=40)   # not confirmed
    new = update_streaks(prev, scores, "RISK_OFF")
    assert new.risk_off_release_days == 1

    new2 = update_streaks(prev, scores, "NORMAL_RISK_ON")
    assert new2.risk_off_release_days == 0  # not in RISK_OFF, don't count


# ── resolve_regime ────────────────────────────────────────────────────────────────

def test_fast_crash_immediate_entry():
    scores = make_scores(fast=80)
    regime = resolve_regime("NORMAL_RISK_ON", scores, zero_streaks())
    assert regime == "FAST_CRASH"


def test_fast_crash_held_before_2_day_release():
    scores = make_scores(fast=50)  # < 75, < 60 → would release
    streaks = StreakState(fast_risk_lt_60=1)  # only 1 day, need 2
    regime = resolve_regime("FAST_CRASH", scores, streaks)
    assert regime == "FAST_CRASH"


def test_fast_crash_released_after_2_days():
    scores = make_scores(fast=50, risk_on=80)
    streaks = StreakState(fast_risk_lt_60=2)
    regime = resolve_regime("FAST_CRASH", scores, streaks)
    assert regime != "FAST_CRASH"
    assert regime == "HEALTHY_RISK_ON"


def test_risk_off_needs_2_day_confirm():
    # Day 1: confirmed but streak only 1
    scores = make_scores(slow=75, hy=65)
    streaks = StreakState(risk_off_confirmed_days=1)
    regime = resolve_regime("NORMAL_RISK_ON", scores, streaks)
    assert regime != "RISK_OFF"


def test_risk_off_enters_after_2_days():
    scores = make_scores(slow=75, hy=65, risk_on=30)
    streaks = StreakState(risk_off_confirmed_days=2)
    regime = resolve_regime("NORMAL_RISK_ON", scores, streaks)
    assert regime == "RISK_OFF"


def test_risk_off_held_before_2_day_release():
    scores = make_scores(slow=40, risk_on=80)  # conditions resolved
    streaks = StreakState(risk_off_release_days=1)
    regime = resolve_regime("RISK_OFF", scores, streaks)
    assert regime == "RISK_OFF"


def test_risk_off_released_after_2_days():
    scores = make_scores(slow=40, risk_on=80)
    streaks = StreakState(risk_off_release_days=2)
    regime = resolve_regime("RISK_OFF", scores, streaks)
    assert regime != "RISK_OFF"


def test_healthy_risk_on():
    scores = make_scores(risk_on=80, overshoot=40)
    regime = resolve_regime("NORMAL_RISK_ON", scores, zero_streaks())
    assert regime == "HEALTHY_RISK_ON"


def test_overheated_risk_on():
    scores = make_scores(risk_on=85, overshoot=80)
    regime = resolve_regime("NORMAL_RISK_ON", scores, zero_streaks())
    assert regime == "OVERHEATED_RISK_ON"


def test_overheat_caution():
    scores = make_scores(risk_on=80, overshoot=65)
    regime = resolve_regime("NORMAL_RISK_ON", scores, zero_streaks())
    assert regime == "OVERHEAT_CAUTION"


def test_hysteresis_healthy_stays_at_65():
    scores = make_scores(risk_on=68, overshoot=40)
    # From HEALTHY_RISK_ON, threshold drops to 65
    regime = resolve_regime("HEALTHY_RISK_ON", scores, zero_streaks())
    assert regime == "HEALTHY_RISK_ON"

    # From NORMAL_RISK_ON, threshold is 75 → should NOT be Healthy
    regime2 = resolve_regime("NORMAL_RISK_ON", scores, zero_streaks())
    assert regime2 != "HEALTHY_RISK_ON"


def test_hysteresis_normal_stays_at_45():
    scores = make_scores(risk_on=48, overshoot=40)
    regime = resolve_regime("NORMAL_RISK_ON", scores, zero_streaks())
    assert regime == "NORMAL_RISK_ON"

    regime2 = resolve_regime("CAUTION", scores, zero_streaks())
    assert regime2 != "NORMAL_RISK_ON"


def test_caution_regime():
    scores = make_scores(risk_on=38, overshoot=20)
    regime = resolve_regime("WARNING", scores, zero_streaks())
    assert regime == "CAUTION"


def test_warning_regime():
    scores = make_scores(risk_on=20, overshoot=10)
    regime = resolve_regime("CAUTION", scores, zero_streaks())
    assert regime == "WARNING"


# ── Priority ordering ────────────────────────────────────────────────────────────

def test_fast_crash_overrides_healthy():
    # Even with great risk-on score, Fast Crash wins at 1st priority
    scores = make_scores(fast=80, risk_on=99, overshoot=10)
    regime = resolve_regime("HEALTHY_RISK_ON", scores, zero_streaks())
    assert regime == "FAST_CRASH"
