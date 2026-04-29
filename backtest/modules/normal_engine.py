"""
Normal engine: Quality & Growth Momentum.
Operates in REGIME_NORMAL only.
"""

import logging
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .regime_detector import RegimeInfo, REGIME_NORMAL

logger = logging.getLogger(__name__)

BUY = "BUY"
SELL = "SELL"
TRIM = "TRIM"
HOLD = "HOLD"


class NormalEngine:
    def __init__(self, config):
        self.cfg = config

    # ─────────────────────────────────────────────────────────────────
    # Buy candidates
    # ─────────────────────────────────────────────────────────────────

    def get_buy_candidates(
        self,
        date: pd.Timestamp,
        universe: List[str],
        indicators: Dict,
        fundamentals: Dict,
        regime_info: RegimeInfo,
        current_positions: Dict,
        trading_calendar: pd.DatetimeIndex,
    ) -> List[dict]:
        """Return ranked list of buy candidates."""
        if regime_info.regime != REGIME_NORMAL:
            return []

        candidates = []
        for ticker in universe:
            if ticker in current_positions:
                continue  # already holding
            ind = indicators.get(ticker)
            if ind is None:
                continue
            fund = fundamentals.get(ticker, {})

            result = self._check_buy(ticker, date, ind, fund, regime_info, trading_calendar)
            if result["pass"]:
                candidates.append({
                    "ticker": ticker,
                    "reason": result["reason"],
                    "rs_rank": ind.get("rs_rank", 0),
                    "rs_score": ind.get("rs_score", 0),
                })

        # Sort by RS rank (highest first)
        candidates.sort(key=lambda x: x.get("rs_rank", 0), reverse=True)
        return candidates

    # ─────────────────────────────────────────────────────────────────
    # Sell / trim candidates
    # ─────────────────────────────────────────────────────────────────

    def get_sell_candidates(
        self,
        date: pd.Timestamp,
        positions: Dict,
        indicators: Dict,
        fundamentals: Dict,
        regime_info: RegimeInfo,
    ) -> List[dict]:
        """Return positions that should be sold/trimmed."""
        candidates = []
        for ticker, pos in positions.items():
            if pos.get("engine") != "normal":
                continue
            ind = indicators.get(ticker)
            fund = fundamentals.get(ticker, {})
            result = self._check_sell(ticker, pos, ind, fund, regime_info)
            if result["action"] in (SELL, TRIM):
                candidates.append({
                    "ticker": ticker,
                    "action": result["action"],
                    "reason": result["reason"],
                    "trim_frac": result.get("trim_frac", 1.0),
                })
        return candidates

    def get_neutral_trims(
        self,
        date: pd.Timestamp,
        positions: Dict,
        indicators: Dict,
        fundamentals: Dict,
    ) -> List[dict]:
        """In NEUTRAL: trim weak positions (no new buys)."""
        trims = []
        for ticker, pos in positions.items():
            if pos.get("engine") != "normal":
                continue
            ind = indicators.get(ticker)
            fund = fundamentals.get(ticker, {})
            if self._is_weak_for_neutral(ind, fund, pos):
                trims.append({
                    "ticker": ticker,
                    "action": TRIM,
                    "reason": "NEUTRAL_WEAK_TRIM",
                    "trim_frac": 0.5,
                })
        return trims

    def get_crisis_trims(
        self,
        positions: Dict,
        indicators: Dict,
        fundamentals: Dict,
        trim_frac: float = 0.50,
    ) -> List[dict]:
        """
        On CRISIS_CONFIRMED: trim weakest normal positions up to trim_frac.
        Priority: loss > RS weak > below SMA50 > fundamental deterioration.
        """
        scored = []
        for ticker, pos in positions.items():
            if pos.get("engine") != "normal":
                continue
            ind = indicators.get(ticker)
            fund = fundamentals.get(ticker, {})
            score = self._crisis_trim_score(ticker, pos, ind, fund)
            scored.append((ticker, score))

        # Sort worst first
        scored.sort(key=lambda x: x[1], reverse=True)

        # Trim up to 50% of normal positions count
        n_trim = max(1, len(scored) // 2)
        trims = []
        for ticker, score in scored[:n_trim]:
            trims.append({
                "ticker": ticker,
                "action": SELL,
                "reason": "CRISIS_NORMAL_TRIM",
                "trim_frac": 1.0,
            })
        return trims

    # ─────────────────────────────────────────────────────────────────
    # Internal checks
    # ─────────────────────────────────────────────────────────────────

    def _check_buy(
        self,
        ticker: str,
        date: pd.Timestamp,
        ind: dict,
        fund: dict,
        regime_info: RegimeInfo,
        trading_calendar: pd.DatetimeIndex,
    ) -> dict:
        fail = lambda r: {"pass": False, "reason": r}

        # Fundamental data required
        if not fund.get("has_normal_data"):
            return fail("MISSING_NORMAL_DATA")

        revenue_yoy = fund.get("revenue_yoy")
        eps_yoy = fund.get("eps_yoy")
        if revenue_yoy is None or revenue_yoy <= self.cfg.min_revenue_growth:
            return fail(f"REVENUE_YOY_FAIL={revenue_yoy}")
        if eps_yoy is None or eps_yoy <= self.cfg.min_eps_growth:
            return fail(f"EPS_YOY_FAIL={eps_yoy}")

        # Momentum
        ret_6m = ind.get("ret_6m")
        if ret_6m is None or ret_6m <= self.cfg.min_6m_return:
            return fail(f"6M_RETURN_FAIL={ret_6m}")

        rs_rank = ind.get("rs_rank")
        if rs_rank is None or rs_rank < (1.0 - self.cfg.rs_buy_top_pct):
            return fail(f"RS_RANK_FAIL={rs_rank}")

        # Price above SMA50
        close = ind.get("close")
        sma50 = ind.get("sma50")
        if close is None or sma50 is None or close <= sma50:
            return fail(f"BELOW_SMA50={close}/{sma50}")

        # Earnings filter
        next_earnings = fund.get("next_earnings_date")
        if next_earnings is not None:
            future_trading_days = trading_calendar[
                (trading_calendar > date) & (trading_calendar <= next_earnings)
            ]
            if len(future_trading_days) < self.cfg.earnings_buffer_days:
                return fail(f"EARNINGS_TOO_CLOSE={next_earnings}")

        return {"pass": True, "reason": "NORMAL_BUY_OK"}

    def _check_sell(self, ticker: str, pos: dict, ind: Optional[dict], fund: dict, regime_info: RegimeInfo) -> dict:
        if ind is None:
            return {"action": HOLD, "reason": "NO_INDICATOR"}

        close = ind.get("close")
        avg_cost = pos.get("avg_cost", 0)

        # Hard stop -12%
        if avg_cost and avg_cost > 0 and close:
            pnl_pct = (close - avg_cost) / avg_cost
            if pnl_pct <= self.cfg.hard_stop_loss:
                return {"action": SELL, "reason": f"HARD_STOP={pnl_pct:.2%}"}

        # Revenue or EPS turned negative
        if fund.get("has_normal_data"):
            rev = fund.get("revenue_yoy")
            eps = fund.get("eps_yoy")
            if rev is not None and rev <= 0:
                return {"action": SELL, "reason": f"REVENUE_NEGATIVE={rev:.2%}"}
            if eps is not None and eps <= 0:
                return {"action": SELL, "reason": f"EPS_NEGATIVE={eps:.2%}"}

        # 3 consecutive closes below SMA50
        below_days = ind.get("below_sma50_days", 0)
        if below_days >= self.cfg.sma50_consec_days:
            return {"action": SELL, "reason": f"BELOW_SMA50_{below_days}D"}

        # RS rank dropped outside top 40%
        rs_rank = ind.get("rs_rank")
        if rs_rank is not None and rs_rank < (1.0 - self.cfg.rs_sell_top_pct):
            return {"action": TRIM, "reason": f"RS_RANK_WEAK={rs_rank:.2f}", "trim_frac": 0.5}

        return {"action": HOLD, "reason": "HOLD"}

    def _is_weak_for_neutral(self, ind: Optional[dict], fund: dict, pos: dict) -> bool:
        if ind is None:
            return False
        rs_rank = ind.get("rs_rank")
        close = ind.get("close")
        sma50 = ind.get("sma50")
        avg_cost = pos.get("avg_cost", 0)

        rs_weak = rs_rank is not None and rs_rank < (1.0 - self.cfg.rs_sell_top_pct)
        below_sma = close is not None and sma50 is not None and close < sma50
        in_loss = avg_cost and avg_cost > 0 and close and (close - avg_cost) / avg_cost < 0

        return (rs_weak and below_sma) or (in_loss and ind.get("below_sma50_days", 0) >= self.cfg.sma50_consec_days)

    def _crisis_trim_score(self, ticker: str, pos: dict, ind: Optional[dict], fund: dict) -> int:
        """Higher = worse = trim first."""
        score = 0
        if ind is None:
            return 10
        close = ind.get("close")
        avg_cost = pos.get("avg_cost", 0)
        if avg_cost and avg_cost > 0 and close:
            if close < avg_cost:
                score += 4   # in loss
        rs_rank = ind.get("rs_rank")
        if rs_rank is not None and rs_rank < (1.0 - self.cfg.rs_sell_top_pct):
            score += 3
        if ind.get("below_sma50_days", 0) >= self.cfg.sma50_consec_days:
            score += 2
        if fund.get("revenue_yoy") is not None and fund["revenue_yoy"] <= 0:
            score += 1
        return score
