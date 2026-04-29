"""
Regime score calculators: Fast Risk, Slow Risk, Risk-On, Overshoot.
All functions clip output to [0, 100].
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.utils.clip import clip_score


@dataclass
class MarketScores:
    fast_risk: float
    slow_risk: float
    risk_on: float
    overshoot: float
    # sub-components used in FSM
    hy_spread_stress: float
    spy_200dma_break: float


# ── Fast Risk Score ─────────────────────────────────────────────────────────────

def _vix_level_score(vix: float) -> float:
    if vix < 18:   return 0.0
    if vix < 22:   return 30.0
    if vix < 25:   return 60.0
    return 100.0


def _vix_3d_change_score(pct_change: float) -> float:
    """pct_change as a fraction (e.g. 0.15 = 15%)."""
    if pct_change < 0.10:  return 0.0
    if pct_change < 0.20:  return 40.0
    if pct_change < 0.25:  return 70.0
    return 100.0


def _spy_3d_return_score(ret: float) -> float:
    """ret as a fraction (negative = down)."""
    if ret >= -0.02:  return 0.0
    if ret >= -0.04:  return 50.0
    return 100.0


def _qqq_20dma_break_score(close: float, ma20: float) -> float:
    ratio = (close / ma20) - 1 if ma20 else 0.0
    if ratio >= 0.01:   return 0.0
    if ratio >= -0.01:  return 40.0
    return 100.0


def _gap_down_breadth_score(pct_gap_down: float) -> float:
    """Fraction of S&P500 stocks that gap down ≥2%."""
    if pct_gap_down < 0.05:  return 0.0
    if pct_gap_down < 0.10:  return 30.0
    if pct_gap_down < 0.20:  return 60.0
    return 100.0


def calc_fast_risk_score(
    vix: float,
    vix_3d_change: float,
    spy_3d_return: float,
    qqq_close: float,
    qqq_20dma: float,
    gap_down_breadth: float,
) -> float:
    s = (
        0.30 * _vix_level_score(vix)
      + 0.25 * _vix_3d_change_score(vix_3d_change)
      + 0.20 * _spy_3d_return_score(spy_3d_return)
      + 0.15 * _qqq_20dma_break_score(qqq_close, qqq_20dma)
      + 0.10 * _gap_down_breadth_score(gap_down_breadth)
    )
    return clip_score(s)


# ── Slow Risk Score ─────────────────────────────────────────────────────────────

def _hy_spread_stress_score(spread_now: float, spread_60d_avg: float,
                             spread_20d_delta: float) -> float:
    if spread_now <= spread_60d_avg:  return 0.0
    excess = spread_now - spread_60d_avg
    if excess <= 50 and spread_20d_delta < 50:  return 30.0
    if excess <= 150 and spread_20d_delta < 50: return 60.0
    return 100.0  # >150bp or 20-day Δ≥50bp


def _spy_200dma_break_score(spy_close: float, spy_200dma: float) -> float:
    ratio = (spy_close / spy_200dma) - 1 if spy_200dma else 0.0
    if ratio >= 0.03:   return 0.0
    if ratio >= -0.03:  return 50.0
    return 100.0


def _gold_spy_rs_score(gold_close: float, gold_100dma: float,
                        gold_momentum: float) -> float:
    """gold_momentum: 20-day return of gold, positive = rising."""
    if gold_close < gold_100dma:  return 0.0
    if gold_momentum <= 0:        return 50.0
    return 100.0


def _tlt_spy_rs_score(tlt_close: float, tlt_60dma: float,
                       tlt_momentum: float) -> float:
    if tlt_close < tlt_60dma:   return 0.0
    if tlt_momentum <= 0:       return 50.0
    return 100.0


def _yield_structure_score(spread_10y_3m: float) -> float:
    """10Y - 3M spread in basis points."""
    if spread_10y_3m > 100:   return 0.0
    if spread_10y_3m >= 0:    return 40.0
    if spread_10y_3m >= -50:  return 70.0
    return 100.0


def calc_slow_risk_score(
    hy_spread_now: float,
    hy_spread_60d_avg: float,
    hy_spread_20d_delta: float,
    spy_close: float,
    spy_200dma: float,
    gold_close: float,
    gold_100dma: float,
    gold_20d_momentum: float,
    tlt_close: float,
    tlt_60dma: float,
    tlt_20d_momentum: float,
    yield_10y_3m_spread_bp: float,
) -> tuple[float, float, float]:
    """Returns (slow_risk_score, hy_spread_stress_score, spy_200dma_break_score)."""
    hy  = _hy_spread_stress_score(hy_spread_now, hy_spread_60d_avg, hy_spread_20d_delta)
    spy = _spy_200dma_break_score(spy_close, spy_200dma)
    gld = _gold_spy_rs_score(gold_close, gold_100dma, gold_20d_momentum)
    tlt = _tlt_spy_rs_score(tlt_close, tlt_60dma, tlt_20d_momentum)
    yld = _yield_structure_score(yield_10y_3m_spread_bp)

    score = (
        0.30 * hy
      + 0.25 * spy
      + 0.20 * gld
      + 0.15 * tlt
      + 0.10 * yld
    )
    return clip_score(score), clip_score(hy), clip_score(spy)


# ── Risk-On Score ───────────────────────────────────────────────────────────────

def _index_trend_score(spy_50dma: float, spy_200dma: float,
                        spy_50dma_slope: float, spy_close: float) -> float:
    if spy_50dma < spy_200dma or spy_50dma_slope < 0:  return 0.0
    if abs(spy_50dma_slope) < 0.001:                    return 40.0
    if spy_close < spy_50dma:                           return 70.0
    return 100.0


def _vix_stability_score(vix: float, vix_20d_std: float) -> float:
    if vix > 25 or vix_20d_std > 5:   return 0.0
    if vix >= 20:                       return 40.0
    if vix >= 15 and vix_20d_std <= 3: return 70.0
    if vix < 15 and vix_20d_std < 2:  return 100.0
    return 40.0


def _market_breadth_score(pct_above_50dma: float, pct_above_200dma: float,
                           nh_nl_ratio: float, mclellan: float) -> float:
    """Average of 4 sub-indicators, each normalised 0–100."""
    def norm(v: float, lo: float, hi: float) -> float:
        return clip_score((v - lo) / (hi - lo) * 100 if hi != lo else 50.0)

    s1 = norm(pct_above_50dma,  0.0,  1.0)
    s2 = norm(pct_above_200dma, 0.0,  1.0)
    s3 = norm(nh_nl_ratio,      -1.0, 1.0)
    s4 = norm(mclellan,         -100.0, 100.0)
    return clip_score((s1 + s2 + s3 + s4) / 4.0)


def _breakout_expansion_score(pct_rs_above_70: float) -> float:
    if pct_rs_above_70 < 0.10:  return 0.0
    if pct_rs_above_70 < 0.20:  return 40.0
    if pct_rs_above_70 < 0.30:  return 70.0
    return 100.0


def _credit_stability_score(hy_oas_20d_change_bp: float) -> float:
    """Positive = rising (risk), negative = falling (stable)."""
    if hy_oas_20d_change_bp >= 30:    return 0.0
    if hy_oas_20d_change_bp > -20:   return 50.0
    return 100.0


def calc_risk_on_score(
    spy_50dma: float, spy_200dma: float, spy_50dma_slope: float, spy_close: float,
    vix: float, vix_20d_std: float,
    pct_above_50dma: float, pct_above_200dma: float,
    nh_nl_ratio: float, mclellan: float,
    pct_rs_above_70: float,
    hy_oas_20d_change_bp: float,
) -> float:
    it = _index_trend_score(spy_50dma, spy_200dma, spy_50dma_slope, spy_close)
    vs = _vix_stability_score(vix, vix_20d_std)
    mb = _market_breadth_score(pct_above_50dma, pct_above_200dma, nh_nl_ratio, mclellan)
    be = _breakout_expansion_score(pct_rs_above_70)
    cs = _credit_stability_score(hy_oas_20d_change_bp)

    score = (
        0.25 * it
      + 0.20 * vs
      + 0.20 * mb
      + 0.20 * be
      + 0.15 * cs
    )
    return clip_score(score)


# ── Overshoot Score ─────────────────────────────────────────────────────────────

def _ma_extension_score(close: float, ma20: float) -> float:
    ext = (close / ma20 - 1) if ma20 else 0.0
    if ext < 0.03:   return 0.0
    if ext < 0.06:   return 30.0
    if ext < 0.10:   return 60.0
    return 100.0


def _rsi14_score(rsi_val: float) -> float:
    if rsi_val <= 60:  return 0.0
    if rsi_val <= 70:  return 30.0
    if rsi_val <= 75:  return 60.0
    return 100.0


def _return_acceleration_score(ret_20d: float) -> float:
    if ret_20d < 0.05:   return 0.0
    if ret_20d < 0.10:   return 30.0
    if ret_20d < 0.15:   return 60.0
    return 100.0


def _gap_score(gap_days_in_20: int) -> float:
    if gap_days_in_20 <= 1:  return 0.0
    if gap_days_in_20 == 2:  return 30.0
    if gap_days_in_20 == 3:  return 60.0
    return 100.0


def _breadth_divergence_score(index_trend: float,
                               breadth_10d_change: float) -> float:
    """index_trend: recent 20d return of index. breadth_10d_change: Δ%above50dma over 10d."""
    if index_trend <= 0:             return 0.0
    if breadth_10d_change >= 0:      return 0.0
    if breadth_10d_change >= -0.05:  return 40.0
    if breadth_10d_change >= -0.10:  return 70.0
    return 100.0


def _calc_per_index_overshoot(
    close: float, ma20: float, rsi_val: float,
    ret_20d: float, gap_days: int, index_trend: float, breadth_10d_change: float,
    bonus_flags: int = 0,
) -> float:
    s = (
        0.30 * _ma_extension_score(close, ma20)
      + 0.25 * _rsi14_score(rsi_val)
      + 0.20 * _return_acceleration_score(ret_20d)
      + 0.15 * _gap_score(gap_days)
      + 0.10 * _breadth_divergence_score(index_trend, breadth_10d_change)
    )
    s += bonus_flags * 10.0
    return clip_score(s)


def calc_overshoot_score(
    qqq_close: float, qqq_ma20: float, qqq_rsi: float, qqq_ret20: float,
    qqq_gaps: int, qqq_trend: float, qqq_breadth_chg: float, qqq_bonus: int,
    spy_close: float, spy_ma20: float, spy_rsi: float, spy_ret20: float,
    spy_gaps: int, spy_trend: float, spy_breadth_chg: float, spy_bonus: int,
    use_max: bool = False,
) -> float:
    qqq_os = _calc_per_index_overshoot(
        qqq_close, qqq_ma20, qqq_rsi, qqq_ret20, qqq_gaps, qqq_trend, qqq_breadth_chg, qqq_bonus
    )
    spy_os = _calc_per_index_overshoot(
        spy_close, spy_ma20, spy_rsi, spy_ret20, spy_gaps, spy_trend, spy_breadth_chg, spy_bonus
    )
    if use_max:
        return clip_score(max(qqq_os, spy_os))
    return clip_score(0.65 * qqq_os + 0.35 * spy_os)


def evaluate_risk_off(slow_risk_score: float,
                       hy_spread_stress: float,
                       spy_200dma_break: float) -> bool:
    return (
        slow_risk_score >= 70
        and (hy_spread_stress >= 60 or spy_200dma_break >= 50)
    )
