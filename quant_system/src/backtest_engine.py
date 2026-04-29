"""
Backtesting engine — runs EOD scan over a historical date range.
Enforces the mandatory call order: scores → streaks → regime → candidates → report.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from src.utils.calendar import get_trading_days, next_trading_day
from src.utils.persistence import (
    load_regime_history, get_last_regime_state, append_regime_history,
    load_pead_events, load_positions,
)
from src.indicators import (
    sma, sma_slope, atr, rsi, obv, compute_rs_rank,
    sta, sta_percentile_cross_section,
    obv_breakout_score, high_proximity_score,
    atr_contraction_score, volume_expansion_score, vcp_pass,
    MIN_HISTORY_DAYS,
)
from src.regime_scores import (
    MarketScores,
    calc_fast_risk_score, calc_slow_risk_score,
    calc_risk_on_score, calc_overshoot_score,
)
from src.regime_fsm import StreakState, update_streaks, resolve_regime
from src.universe_builder import build_universe, filter_entry_candidates
from src.momentum_scanner import (
    scan_momentum_candidates, apply_candidate_limit, MomentumResult,
)
from src.position_sizer import (
    size_position, build_capacity_state, SizeResult, CapacityState,
)
from src.eod_report import (
    build_market_status_row, write_market_status,
    build_candidate_row, write_candidates,
    build_blocked_row, write_blocked,
    print_market_summary,
)
from src.data_loader import (
    load_all_prices, load_fundamentals, load_earnings_calendar,
    load_market_breadth, slice_up_to, history_length, get_price_on_date,
)

log = logging.getLogger(__name__)


@dataclass
class EODState:
    signal_date: date
    execution_date: date
    regime: str
    scores: MarketScores
    streaks: StreakState
    candidates: list[dict] = field(default_factory=list)
    blocked: list[dict] = field(default_factory=list)
    market_status: dict = field(default_factory=dict)


def _safe_float(v, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None and not (isinstance(v, float) and np.isnan(v)) else default
    except Exception:
        return default


def _compute_market_scores(
    as_of: pd.Timestamp,
    market_prices: dict[str, pd.DataFrame],
    breadth_df: Optional[pd.DataFrame],
) -> MarketScores:
    """
    Compute all 4 regime scores for a given date using available market data.
    Uses a best-effort approach when optional data is missing.
    """

    def px(sym: str, col: str = "close", lag: int = 0) -> float:
        df = market_prices.get(sym)
        if df is None:
            return 0.0
        sub = df[df.index <= as_of]
        if len(sub) <= lag:
            return 0.0
        return _safe_float(sub[col].iloc[-(1 + lag)])

    def series_up_to(sym: str, col: str = "close") -> pd.Series:
        df = market_prices.get(sym)
        if df is None:
            return pd.Series(dtype=float)
        return df[df.index <= as_of][col]

    # ── VIX ─────────────────────────────────────────────────────────────────────
    vix_series = series_up_to("^VIX")
    vix_now   = _safe_float(vix_series.iloc[-1]) if len(vix_series) >= 1 else 20.0
    vix_3d_ago = _safe_float(vix_series.iloc[-4]) if len(vix_series) >= 4 else vix_now
    vix_3d_change = (vix_now / vix_3d_ago - 1) if vix_3d_ago > 0 else 0.0
    vix_20d_std = _safe_float(vix_series.tail(20).std()) if len(vix_series) >= 20 else 3.0

    # ── SPY ─────────────────────────────────────────────────────────────────────
    spy_series = series_up_to("SPY")
    spy_now    = _safe_float(spy_series.iloc[-1]) if len(spy_series) else 0.0
    spy_3d_ago = _safe_float(spy_series.iloc[-4]) if len(spy_series) >= 4 else spy_now
    spy_3d_ret = (spy_now / spy_3d_ago - 1) if spy_3d_ago > 0 else 0.0
    spy_ma20   = _safe_float(spy_series.rolling(20).mean().iloc[-1]) if len(spy_series) >= 20 else spy_now
    spy_ma50   = _safe_float(spy_series.rolling(50).mean().iloc[-1]) if len(spy_series) >= 50 else spy_now
    spy_ma200  = _safe_float(spy_series.rolling(200).mean().iloc[-1]) if len(spy_series) >= 200 else spy_now
    spy_slope50 = _safe_float(
        (spy_ma50 - _safe_float(spy_series.rolling(50).mean().iloc[-6])) / spy_ma50
    ) if len(spy_series) >= 55 else 0.0

    # ── QQQ ─────────────────────────────────────────────────────────────────────
    qqq_series = series_up_to("QQQ")
    qqq_now    = _safe_float(qqq_series.iloc[-1]) if len(qqq_series) else 0.0
    qqq_ma20   = _safe_float(qqq_series.rolling(20).mean().iloc[-1]) if len(qqq_series) >= 20 else qqq_now
    qqq_ma200  = _safe_float(qqq_series.rolling(200).mean().iloc[-1]) if len(qqq_series) >= 200 else qqq_now
    qqq_ret20  = (qqq_now / _safe_float(qqq_series.iloc[-21]) - 1) if len(qqq_series) >= 21 else 0.0
    qqq_rsi14  = _safe_float(rsi(qqq_series, 14).iloc[-1]) if len(qqq_series) >= 14 else 50.0
    qqq_trend20 = qqq_ret20

    # ── GLD / TLT ───────────────────────────────────────────────────────────────
    gld_series  = series_up_to("GLD")
    gld_now     = _safe_float(gld_series.iloc[-1]) if len(gld_series) else 0.0
    gld_100dma  = _safe_float(gld_series.rolling(100).mean().iloc[-1]) if len(gld_series) >= 100 else gld_now
    gld_mom20   = (gld_now / _safe_float(gld_series.iloc[-21]) - 1) if len(gld_series) >= 21 else 0.0

    tlt_series  = series_up_to("TLT")
    tlt_now     = _safe_float(tlt_series.iloc[-1]) if len(tlt_series) else 0.0
    tlt_60dma   = _safe_float(tlt_series.rolling(60).mean().iloc[-1]) if len(tlt_series) >= 60 else tlt_now
    tlt_mom20   = (tlt_now / _safe_float(tlt_series.iloc[-21]) - 1) if len(tlt_series) >= 21 else 0.0

    # ── Breadth data (from breadth CSV or defaults) ──────────────────────────────
    if breadth_df is not None and as_of in breadth_df.index:
        brow = breadth_df.loc[as_of]
        hy_spread      = _safe_float(brow.get("hy_spread", 400))
        hy_spread_60a  = _safe_float(brow.get("hy_spread_60d_avg", 400))
        hy_spread_20d  = _safe_float(brow.get("hy_spread_20d_delta", 0))
        hy_oas_20d     = _safe_float(brow.get("hy_oas_20d_change_bp", 0))
        yield_10y_3m   = _safe_float(brow.get("yield_10y_3m_bp", 150))
        pct_50dma      = _safe_float(brow.get("pct_above_50dma", 0.6))
        pct_200dma     = _safe_float(brow.get("pct_above_200dma", 0.6))
        nh_nl          = _safe_float(brow.get("nh_nl_ratio", 0.0))
        mclellan       = _safe_float(brow.get("mclellan", 0.0))
    else:
        # Neutral defaults when breadth data unavailable
        hy_spread, hy_spread_60a, hy_spread_20d = 400.0, 400.0, 0.0
        hy_oas_20d, yield_10y_3m = 0.0, 150.0
        pct_50dma, pct_200dma, nh_nl, mclellan = 0.6, 0.6, 0.0, 0.0

    # Gap-down breadth: approximate using SPY single-day return as proxy
    gap_down_breadth = max(0.0, min(1.0, max(0.0, -spy_3d_ret) * 3))

    # ── Score computation ────────────────────────────────────────────────────────
    fast_risk = calc_fast_risk_score(
        vix=vix_now,
        vix_3d_change=vix_3d_change,
        spy_3d_return=spy_3d_ret,
        qqq_close=qqq_now,
        qqq_20dma=qqq_ma20,
        gap_down_breadth=gap_down_breadth,
    )

    slow_risk, hy_stress, spy_200_break = calc_slow_risk_score(
        hy_spread_now=hy_spread,
        hy_spread_60d_avg=hy_spread_60a,
        hy_spread_20d_delta=hy_spread_20d,
        spy_close=spy_now,
        spy_200dma=spy_ma200,
        gold_close=gld_now,
        gold_100dma=gld_100dma,
        gold_20d_momentum=gld_mom20,
        tlt_close=tlt_now,
        tlt_60dma=tlt_60dma,
        tlt_20d_momentum=tlt_mom20,
        yield_10y_3m_spread_bp=yield_10y_3m,
    )

    # RS above-70 count: rough proxy
    pct_rs_above_70 = min(1.0, max(0.0, pct_50dma * 0.7))

    spy_rsi14 = _safe_float(rsi(spy_series, 14).iloc[-1]) if len(spy_series) >= 14 else 50.0
    spy_ret20 = (spy_now / _safe_float(spy_series.iloc[-21]) - 1) if len(spy_series) >= 21 else 0.0

    risk_on = calc_risk_on_score(
        spy_50dma=spy_ma50, spy_200dma=spy_ma200,
        spy_50dma_slope=spy_slope50, spy_close=spy_now,
        vix=vix_now, vix_20d_std=vix_20d_std,
        pct_above_50dma=pct_50dma, pct_above_200dma=pct_200dma,
        nh_nl_ratio=nh_nl, mclellan=mclellan,
        pct_rs_above_70=pct_rs_above_70,
        hy_oas_20d_change_bp=hy_oas_20d,
    )

    # Breadth 10-day change (proxy)
    breadth_10d_chg = 0.0
    if breadth_df is not None:
        sub_b = breadth_df[breadth_df.index <= as_of]["pct_above_50dma"].tail(11)
        if len(sub_b) >= 11:
            breadth_10d_chg = float(sub_b.iloc[-1] - sub_b.iloc[0])

    # Gap days count in last 20 for QQQ (approximate)
    qqq_high = series_up_to("QQQ", "high") if "QQQ" in market_prices else pd.Series(dtype=float)
    qqq_low  = series_up_to("QQQ", "low")  if "QQQ" in market_prices else pd.Series(dtype=float)
    qqq_open = series_up_to("QQQ", "open") if "QQQ" in market_prices else pd.Series(dtype=float)
    qqq_gaps_20 = 0
    if len(qqq_open) >= 2 and len(qqq_series) >= 2:
        prev_close = qqq_series.shift(1).tail(20)
        open_vals  = qqq_open.tail(20)
        gap_pcts   = (open_vals / prev_close - 1).dropna()
        qqq_gaps_20 = int((gap_pcts.abs() >= 0.01).sum())

    spy_gaps_20 = 0
    spy_open = series_up_to("SPY", "open") if "SPY" in market_prices else pd.Series(dtype=float)
    if len(spy_open) >= 2 and len(spy_series) >= 2:
        prev_close = spy_series.shift(1).tail(20)
        open_vals  = spy_open.tail(20)
        gap_pcts   = (open_vals / prev_close - 1).dropna()
        spy_gaps_20 = int((gap_pcts.abs() >= 0.01).sum())

    overshoot = calc_overshoot_score(
        qqq_close=qqq_now, qqq_ma20=qqq_ma20, qqq_rsi=qqq_rsi14,
        qqq_ret20=qqq_ret20, qqq_gaps=qqq_gaps_20,
        qqq_trend=qqq_trend20, qqq_breadth_chg=breadth_10d_chg, qqq_bonus=0,
        spy_close=spy_now, spy_ma20=spy_ma20, spy_rsi=spy_rsi14,
        spy_ret20=spy_ret20, spy_gaps=spy_gaps_20,
        spy_trend=spy_ret20, spy_breadth_chg=breadth_10d_chg, spy_bonus=0,
    )

    return MarketScores(
        fast_risk=fast_risk,
        slow_risk=slow_risk,
        risk_on=risk_on,
        overshoot=overshoot,
        hy_spread_stress=hy_stress,
        spy_200dma_break=spy_200_break,
    )


def run_eod(
    signal_date: pd.Timestamp,
    prev_regime: str,
    prev_streaks: StreakState,
    market_prices: dict[str, pd.DataFrame],
    stock_prices: dict[str, pd.DataFrame],
    fundamentals: Optional[pd.DataFrame],
    breadth_df: Optional[pd.DataFrame],
    earnings_df: Optional[pd.DataFrame],
    config: dict,
    paper_config: dict,
    print_summary: bool = True,
) -> EODState:
    """
    Core EOD processing function. Enforced order:
      1. scores → 2. streaks → 3. regime → 4. candidates → 5. reports
    """
    sig_date = signal_date.date()
    exec_date = next_trading_day(signal_date).date()

    # ── 1. Scores ────────────────────────────────────────────────────────────────
    scores = _compute_market_scores(signal_date, market_prices, breadth_df)

    # ── 2. Streaks ───────────────────────────────────────────────────────────────
    streaks = update_streaks(prev_streaks, scores, prev_regime)

    # ── 3. Regime ────────────────────────────────────────────────────────────────
    regime = resolve_regime(prev_regime, scores, streaks)

    # ── 4. Candidates ────────────────────────────────────────────────────────────
    candidate_rows: list[dict] = []
    blocked_rows: list[dict]   = []

    equity = paper_config.get("equity", 100_000)

    if fundamentals is not None and not fundamentals.empty:
        # Build cross-sectional RS Rank for all symbols on this date
        sym_list = list(stock_prices.keys())
        close_matrix = pd.DataFrame({
            sym: stock_prices[sym][stock_prices[sym].index <= signal_date]["close"]
            for sym in sym_list
            if sym in stock_prices and not stock_prices[sym].empty
        })
        rs_rank_df = compute_rs_rank(close_matrix) if len(close_matrix) > 5 else pd.DataFrame()
        rs_rank_today = (
            rs_rank_df.iloc[-1] if not rs_rank_df.empty else pd.Series(dtype=float)
        )

        # STA cross-section
        spy_close_hist = (
            market_prices["SPY"][market_prices["SPY"].index <= signal_date]["close"]
            if "SPY" in market_prices else pd.Series(dtype=float)
        )
        sta_vals = {}
        for sym in sym_list:
            df = stock_prices.get(sym)
            if df is None or len(df) < 20:
                continue
            sub = df[df.index <= signal_date]["close"]
            spy_aligned = spy_close_hist.reindex(sub.index, method="ffill")
            sta_s = sta(sub, spy_aligned)
            if not sta_s.empty and not pd.isna(sta_s.iloc[-1]):
                sta_vals[sym] = float(sta_s.iloc[-1])

        sta_series = pd.Series(sta_vals)
        sta_pct = sta_percentile_cross_section(sta_series) if not sta_series.empty else pd.Series(dtype=float)

        # Price lookups
        hist_len = history_length(stock_prices, signal_date)

        price_on_date = {
            sym: float(stock_prices[sym][stock_prices[sym].index <= signal_date]["close"].iloc[-1])
            for sym in sym_list
            if sym in stock_prices
            and not stock_prices[sym][stock_prices[sym].index <= signal_date].empty
        }
        price_200dma = {}
        price_50dma  = {}
        adtv_20d_map = {}

        for sym in sym_list:
            df = stock_prices.get(sym)
            if df is None:
                continue
            sub = df[df.index <= signal_date]["close"]
            vol_sub = df[df.index <= signal_date]["volume"] if "volume" in df.columns else pd.Series(dtype=float)

            if len(sub) >= 200:
                price_200dma[sym] = float(sub.rolling(200).mean().iloc[-1])
            if len(sub) >= 50:
                price_50dma[sym] = float(sub.rolling(50).mean().iloc[-1])
            if len(vol_sub) >= 20:
                px_last = price_on_date.get(sym, 0)
                adtv_20d_map[sym] = float(vol_sub.tail(20).mean()) * px_last

        # Build universe
        fund_indexed = fundamentals.set_index("symbol") if "symbol" in fundamentals.columns else fundamentals

        universe_df = build_universe(
            fundamentals=fund_indexed,
            price_on_date=pd.Series(price_on_date),
            price_200dma=pd.Series(price_200dma),
            adtv_20d=pd.Series(adtv_20d_map),
            listing_days=pd.Series({sym: hist_len.get(sym, 0) for sym in sym_list}),
            rs_rank=rs_rank_today,
            trade_date=signal_date,
            history_length=pd.Series(hist_len),
        )

        # Collect universe-level blocked reasons
        if not universe_df.empty:
            blocked_uni = universe_df[universe_df["block_reason"].notna()]
            for _, brow in blocked_uni.iterrows():
                blocked_rows.append(build_blocked_row(
                    sig_date, exec_date,
                    brow["symbol"], brow.get("basket"),
                    str(brow["block_reason"]),
                ))

        # Filter to entry candidates
        if not universe_df.empty and not universe_df[universe_df["block_reason"].isna()].empty:
            cands_df = filter_entry_candidates(
                universe_df,
                rs_rank=rs_rank_today,
                price_50dma=pd.Series(price_50dma),
                price_200dma=pd.Series(price_200dma),
                price=pd.Series(price_on_date),
            )

            # Add STA percentile to candidates
            if not cands_df.empty:
                cands_df["sta_percentile"] = cands_df["symbol"].map(sta_pct).fillna(50)

            # Run momentum scan
            momentum_results = scan_momentum_candidates(
                candidates_df=cands_df,
                price_history={
                    sym: stock_prices[sym][stock_prices[sym].index <= signal_date]
                    for sym in cands_df["symbol"].tolist()
                    if sym in stock_prices
                },
                spy_close=spy_close_hist,
                regime=regime,
                config=paper_config,
            )

            # Apply candidate limit
            top_candidates = apply_candidate_limit(momentum_results, regime, paper_config)

            # Size positions
            positions = load_positions()
            caps = build_capacity_state(equity, paper_config, positions, regime)

            for mr in momentum_results:
                is_top = mr in top_candidates
                sr = size_position(
                    symbol=mr.symbol,
                    equity=equity,
                    entry_price=mr.suggested_entry,
                    stop_price=mr.structural_stop,
                    regime=regime,
                    caps=caps,
                    config=paper_config,
                    rs_rank=mr.rs_rank,
                    above_50dma=True,
                    above_200dma=True,
                    has_sufficient_history=mr.block_reason != "LOOKBACK_INSUFFICIENT",
                )

                row = build_candidate_row(sig_date, exec_date, mr, sr)

                if sr.block_reason or mr.block_reason or not is_top:
                    reason = mr.block_reason or sr.block_reason or "SCORE_BELOW_THRESHOLD"
                    blocked_rows.append(build_blocked_row(
                        sig_date, exec_date, mr.symbol, mr.basket, reason,
                        mr.momentum_score, mr.rs_rank,
                    ))
                else:
                    candidate_rows.append(row)

    # ── 5. Reports ────────────────────────────────────────────────────────────────
    status_row = build_market_status_row(
        sig_date, exec_date, regime, scores, streaks, paper_config,
        survivorship_bias_warning=True,
    )

    write_market_status(status_row, sig_date)
    write_candidates(candidate_rows, sig_date)
    write_blocked(blocked_rows, sig_date)

    if print_summary:
        print_market_summary(status_row)
        if candidate_rows:
            print(f"  Candidates ({len(candidate_rows)}):")
            for r in candidate_rows[:10]:
                print(f"    {r['symbol']:6s} {r['basket']:20s} score={r['momentum_score']:.1f}"
                      f"  RS={r['rs_rank']:.0f}  entry={r['suggested_entry']:.2f}"
                      f"  stop={r['structural_stop']:.2f}  qty={r['model_qty']}")

    # Persist regime state
    append_regime_history({
        "signal_date":              sig_date.isoformat(),
        "regime":                   regime,
        "fast_risk_score":          scores.fast_risk,
        "slow_risk_score":          scores.slow_risk,
        "risk_on_score":            scores.risk_on,
        "overshoot_score":          scores.overshoot,
        "fast_risk_lt_60_streak":   streaks.fast_risk_lt_60,
        "risk_off_confirmed_streak": streaks.risk_off_confirmed_days,
        "risk_off_release_streak":  streaks.risk_off_release_days,
    })

    return EODState(
        signal_date=sig_date,
        execution_date=exec_date,
        regime=regime,
        scores=scores,
        streaks=streaks,
        candidates=candidate_rows,
        blocked=blocked_rows,
        market_status=status_row,
    )


def run_backtest(
    start_date: str,
    end_date: str,
    market_symbols: list[str],
    stock_symbols: list[str],
    config: dict,
    paper_config: dict,
    print_daily: bool = False,
) -> list[EODState]:
    """
    Run EOD scan over a date range.
    Loads all price data upfront, then iterates trading days.
    """
    log.info(f"Loading market price data: {market_symbols}")
    market_prices = load_all_prices(market_symbols)

    log.info(f"Loading stock price data: {len(stock_symbols)} symbols")
    stock_prices = load_all_prices(stock_symbols)

    fundamentals = load_fundamentals()
    breadth_df   = load_market_breadth()
    earnings_df  = load_earnings_calendar()

    trading_days = get_trading_days(start_date, end_date)
    log.info(f"Backtesting {len(trading_days)} trading days: {start_date} → {end_date}")

    # Load initial state from persistence
    hist = load_regime_history()
    last_state = get_last_regime_state(hist)
    prev_regime  = last_state["regime"]
    prev_streaks = StreakState(
        fast_risk_lt_60=last_state["fast_risk_lt_60_streak"],
        risk_off_confirmed_days=last_state["risk_off_confirmed_streak"],
        risk_off_release_days=last_state["risk_off_release_streak"],
    )

    results: list[EODState] = []

    for ts in trading_days:
        try:
            state = run_eod(
                signal_date=ts,
                prev_regime=prev_regime,
                prev_streaks=prev_streaks,
                market_prices=market_prices,
                stock_prices=stock_prices,
                fundamentals=fundamentals,
                breadth_df=breadth_df,
                earnings_df=earnings_df,
                config=config,
                paper_config=paper_config,
                print_summary=print_daily,
            )
            prev_regime  = state.regime
            prev_streaks = state.streaks
            results.append(state)
        except Exception as e:
            log.error(f"Error on {ts.date()}: {e}", exc_info=True)
            continue

    log.info(f"Backtest complete. {len(results)} days processed.")
    return results


def summarize_backtest(results: list[EODState]) -> pd.DataFrame:
    """Return a summary DataFrame with one row per trading day."""
    rows = []
    for s in results:
        rows.append({
            "signal_date":    s.signal_date,
            "execution_date": s.execution_date,
            "regime":         s.regime,
            "fast_risk":      s.scores.fast_risk,
            "slow_risk":      s.scores.slow_risk,
            "risk_on":        s.scores.risk_on,
            "overshoot":      s.scores.overshoot,
            "n_candidates":   len(s.candidates),
            "n_blocked":      len(s.blocked),
        })
    return pd.DataFrame(rows)
