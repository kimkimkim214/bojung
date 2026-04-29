"""
Crisis engine: Deep Value & Survival.
Operates in REGIME_CRISIS_CONFIRMED only.
Time-based DCA: Stage1 → Stage2 (10 trading days) → Stage3 (20 trading days).
"""

import logging
from typing import Dict, List, Optional

import pandas as pd

from .regime_detector import RegimeInfo, REGIME_NORMAL, REGIME_CRISIS_CONFIRMED

logger = logging.getLogger(__name__)


class CrisisEngine:
    def __init__(self, config):
        self.cfg = config

    # ─────────────────────────────────────────────────────────────────
    # Candidate scan
    # ─────────────────────────────────────────────────────────────────

    def get_buy_candidates(
        self,
        date: pd.Timestamp,
        universe: List[str],
        indicators: Dict,
        fundamentals: Dict,
        regime_info: RegimeInfo,
        crisis_entries: Dict,      # {ticker: entry record}
        current_positions: Dict,
    ) -> List[dict]:
        """Return list of crisis buy candidates with DCA stage info."""
        if regime_info.regime != REGIME_CRISIS_CONFIRMED:
            return []

        candidates = []
        for ticker in universe:
            ind = indicators.get(ticker)
            fund = fundamentals.get(ticker, {})
            entry = crisis_entries.get(ticker)

            result = self._check_buy(ticker, date, ind, fund, entry, current_positions)
            if result["eligible"]:
                candidates.append({
                    "ticker": ticker,
                    "stage": result["stage"],
                    "stage_frac": result["stage_frac"],
                    "reason": result["reason"],
                    "priority_score": result["priority_score"],
                    "high_div_risk_flag": result.get("high_div_risk_flag", False),
                })

        # Sort: lower priority score = better (drawdown desc, FCF margin desc, etc.)
        candidates.sort(key=lambda x: (-x["priority_score"], x["high_div_risk_flag"]))
        return candidates

    # ─────────────────────────────────────────────────────────────────
    # Harvest check (exit to normal)
    # ─────────────────────────────────────────────────────────────────

    def get_harvest_candidates(
        self,
        date: pd.Timestamp,
        positions: Dict,
        indicators: Dict,
        regime_info: RegimeInfo,
        consecutive_normal_days: int,
    ) -> List[dict]:
        """
        Harvest crisis positions when:
        - regime returned to NORMAL
        - individual stock close > individual stock 200DMA for N consecutive days
        """
        if regime_info.regime != REGIME_NORMAL:
            return []

        harvests = []
        for ticker, pos in positions.items():
            if pos.get("engine") != "crisis":
                continue
            ind = indicators.get(ticker)
            if ind is None:
                continue
            close = ind.get("close")
            sma200 = ind.get("sma200")
            if close is None or sma200 is None:
                continue

            # Check consecutive days above individual 200DMA
            above_200dma_days = self._get_above_200dma_streak(ticker, date, indicators)
            if above_200dma_days >= self.cfg.crisis_harvest_consec_days:
                harvests.append({
                    "ticker": ticker,
                    "action": "HARVEST",
                    "reason": f"CRISIS_HARVEST_NORMAL_RETURN_{above_200dma_days}D",
                })

        return harvests

    # ─────────────────────────────────────────────────────────────────
    # Fundamental deterioration sell
    # ─────────────────────────────────────────────────────────────────

    def get_fundamental_sells(
        self,
        positions: Dict,
        fundamentals: Dict,
        crisis_entries: Dict,
    ) -> List[dict]:
        """Sell crisis positions whose fundamentals have deteriorated."""
        sells = []
        for ticker, pos in positions.items():
            if pos.get("engine") != "crisis":
                continue
            fund = fundamentals.get(ticker, {})
            reason = self._check_fundamental_deterioration(ticker, fund, crisis_entries.get(ticker))
            if reason:
                sells.append({
                    "ticker": ticker,
                    "action": "SELL",
                    "reason": reason,
                })
        return sells

    # ─────────────────────────────────────────────────────────────────
    # DCA entry record management
    # ─────────────────────────────────────────────────────────────────

    def create_entry_record(
        self,
        ticker: str,
        date: pd.Timestamp,
        price: float,
        budget: float,
        vix: float,
    ) -> dict:
        return {
            "engine": "crisis",
            "entry_stage": 1,
            "first_entry_date": str(date.date()),
            "last_entry_date": str(date.date()),
            "first_entry_price": price,
            "allocated_budget": budget,
            "used_budget": budget * self.cfg.crisis_stage1_frac,
            "last_entry_vix": vix,
            "price_warning_triggered": False,
            "stage2_done": False,
            "stage3_done": False,
        }

    def update_entry_record(
        self,
        entry: dict,
        stage: int,
        date: pd.Timestamp,
        price: float,
        spent: float,
        vix: float,
    ) -> dict:
        entry = dict(entry)
        entry["entry_stage"] = stage
        entry["last_entry_date"] = str(date.date())
        entry["last_entry_vix"] = vix
        entry["used_budget"] = entry.get("used_budget", 0) + spent
        if stage == 2:
            entry["stage2_done"] = True
        elif stage == 3:
            entry["stage3_done"] = True
        return entry

    def check_price_warning(self, entry: dict, current_price: float) -> bool:
        first_price = entry.get("first_entry_price")
        if first_price is None or first_price <= 0:
            return False
        pct = (current_price - first_price) / first_price
        return pct <= self.cfg.crisis_price_warn_pct

    # ─────────────────────────────────────────────────────────────────
    # Internals
    # ─────────────────────────────────────────────────────────────────

    def _check_buy(
        self,
        ticker: str,
        date: pd.Timestamp,
        ind: Optional[dict],
        fund: dict,
        entry: Optional[dict],
        positions: Dict,
    ) -> dict:
        fail = lambda r: {"eligible": False, "reason": r, "stage": None, "stage_frac": 0, "priority_score": 0}

        if ind is None:
            return fail("NO_INDICATOR")

        # Sector filter
        sector = fund.get("sector", "")
        if sector and any(ex.lower() in sector.lower() for ex in self.cfg.excluded_sectors):
            return fail(f"EXCLUDED_SECTOR={sector}")

        # Fundamental checks (crisis engine)
        if not fund.get("has_crisis_data"):
            return fail("MISSING_CRISIS_DATA")

        fcf = fund.get("fcf_ttm")
        if fcf is None or fcf <= self.cfg.fcf_min:
            return fail(f"FCF_FAIL={fcf}")

        de = fund.get("de_ratio")
        if de is None or de >= self.cfg.de_max:
            return fail(f"DE_FAIL={de}")

        # PE check requires price
        close = ind.get("close")
        pe = fund.get("pe_ttm")
        if pe is None or not (self.cfg.pe_min < pe < self.cfg.pe_max):
            return fail(f"PE_FAIL={pe}")

        # Dividend yield: need to convert TTM dividends to yield
        div_ttm = fund.get("div_yield_ttm")  # raw TTM div per share
        if div_ttm is None or close is None or close <= 0:
            div_yield = None
        else:
            div_yield = div_ttm / close
        if div_yield is None or not (self.cfg.div_yield_min < div_yield <= self.cfg.div_yield_max):
            return fail(f"DIV_YIELD_FAIL={div_yield}")

        # Drawdown from 200D high
        high_200d = ind.get("high_200d")
        if high_200d is None or high_200d <= 0 or close is None:
            return fail("NO_200D_HIGH")
        drawdown = (close - high_200d) / high_200d
        if drawdown > self.cfg.crisis_drawdown_trigger:
            return fail(f"DRAWDOWN_INSUFFICIENT={drawdown:.2%}")

        # High dividend risk flag
        high_div_risk = div_yield >= self.cfg.high_div_risk_threshold

        # Determine DCA stage
        stage, stage_frac = self._determine_stage(ticker, date, entry, positions)
        if stage is None:
            return fail("DCA_COMPLETE_OR_BLOCKED")

        # Price warning: block additional stages
        if entry and self.check_price_warning(entry, close):
            if stage > 1:
                return fail(f"PRICE_WARNING_BLOCK_STAGE{stage}")

        # Priority score (higher = better candidate)
        priority_score = self._priority_score(drawdown, fcf, de, pe, fund.get("market_cap", 0))

        return {
            "eligible": True,
            "stage": stage,
            "stage_frac": stage_frac,
            "reason": f"CRISIS_BUY_STAGE{stage}",
            "priority_score": priority_score,
            "high_div_risk_flag": high_div_risk,
        }

    def _determine_stage(
        self,
        ticker: str,
        date: pd.Timestamp,
        entry: Optional[dict],
        positions: Dict,
    ):
        """
        Returns (stage, frac) for the appropriate DCA stage, or (None, 0) if blocked.
        """
        if entry is None:
            # No entry yet → Stage 1
            return 1, self.cfg.crisis_stage1_frac

        # Convert first_entry_date to Timestamp
        try:
            first_date = pd.Timestamp(entry["first_entry_date"])
        except Exception:
            return None, 0

        days_elapsed = (date - first_date).days  # calendar days

        stage2_done = entry.get("stage2_done", False)
        stage3_done = entry.get("stage3_done", False)

        if not stage2_done and days_elapsed >= self.cfg.crisis_stage2_days:
            return 2, self.cfg.crisis_stage2_frac
        elif not stage3_done and days_elapsed >= self.cfg.crisis_stage3_days:
            return 3, self.cfg.crisis_stage3_frac
        elif stage2_done and stage3_done:
            return None, 0   # DCA complete
        else:
            return None, 0   # Not yet time

    def _priority_score(
        self,
        drawdown: float,
        fcf: float,
        de: float,
        pe: float,
        market_cap: Optional[float],
    ) -> float:
        # Higher is better. Weights follow spec priority.
        score = 0.0
        score += abs(drawdown) * 40          # larger drawdown → higher priority
        score += min(fcf / 1e9, 10) * 10    # FCF in billions, cap at 10
        score += (1.0 - min(de, 1.0)) * 5   # lower D/E
        score += (1.0 - pe / 25.0) * 5      # lower PE
        if market_cap:
            score += min(market_cap / 1e12, 3) * 2   # larger cap (trillion) slightly preferred
        return score

    def _check_fundamental_deterioration(self, ticker: str, fund: dict, entry: Optional[dict]) -> Optional[str]:
        fcf = fund.get("fcf_ttm")
        if fcf is not None and fcf <= 0:
            return f"CRISIS_SELL_FCF_NEGATIVE={fcf:.1f}"
        de = fund.get("de_ratio")
        if de is not None and de >= self.cfg.de_max:
            return f"CRISIS_SELL_DE_HIGH={de:.2f}"
        return None

    def _get_above_200dma_streak(self, ticker: str, date: pd.Timestamp, indicators: Dict) -> int:
        """
        In a full implementation, this would check the last N days.
        Here we return 1 if currently above (simulation approximation).
        The backtest simulator tracks this properly via position metadata.
        """
        ind = indicators.get(ticker)
        if ind is None:
            return 0
        close = ind.get("close")
        sma200 = ind.get("sma200")
        if close is None or sma200 is None:
            return 0
        return 1 if close > sma200 else 0
