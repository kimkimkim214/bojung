"""
Market regime detector.
Priority order (v2.2 spec):
  1. CRISIS_CONFIRMED   (highest priority)
  2. CRISIS_WARNING
  3. NEUTRAL
  4. NORMAL             (lowest priority)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

REGIME_NORMAL = "NORMAL"
REGIME_NEUTRAL = "NEUTRAL"
REGIME_CRISIS_WARNING = "CRISIS_WARNING"
REGIME_CRISIS_CONFIRMED = "CRISIS_CONFIRMED"


@dataclass
class RegimeInfo:
    regime: str = REGIME_NORMAL
    vix: Optional[float] = None
    spy_close: Optional[float] = None
    spy_200dma: Optional[float] = None

    spy_200dma_near_flag: bool = False
    extreme_fear_flag: bool = False
    panic_liquidity_flag: bool = False

    @property
    def is_crisis(self) -> bool:
        return self.regime == REGIME_CRISIS_CONFIRMED

    @property
    def is_normal(self) -> bool:
        return self.regime == REGIME_NORMAL

    @property
    def is_neutral(self) -> bool:
        return self.regime == REGIME_NEUTRAL

    @property
    def is_warning(self) -> bool:
        return self.regime == REGIME_CRISIS_WARNING


class RegimeDetector:
    def __init__(
        self,
        vix_neutral_low: float = 25.0,
        vix_crisis_low: float = 30.0,
        vix_extreme_fear: float = 40.0,
        vix_panic: float = 50.0,
        spy_near_dma_pct: float = 0.02,
    ):
        self.vix_neutral_low = vix_neutral_low
        self.vix_crisis_low = vix_crisis_low
        self.vix_extreme_fear = vix_extreme_fear
        self.vix_panic = vix_panic
        self.spy_near_dma_pct = spy_near_dma_pct

    def detect(
        self,
        vix: float,
        spy_close: float,
        spy_200dma: float,
        # For intraday-aware CRISIS_WARNING (in backtest we use daily close only)
        spy_intraday: Optional[float] = None,
    ) -> RegimeInfo:
        """
        Detect market regime using end-of-day data.
        In backtest context: vix = VIX close, spy_close = SPY close.
        """
        info = RegimeInfo(vix=vix, spy_close=spy_close, spy_200dma=spy_200dma)

        if spy_200dma is None or spy_200dma == 0:
            info.regime = REGIME_NORMAL
            return info

        # ── Priority 1: CRISIS_CONFIRMED ─────────────────────────
        # End-of-day: VIX >= 30 AND SPY close < SPY 200DMA
        if vix >= self.vix_crisis_low and spy_close < spy_200dma:
            info.regime = REGIME_CRISIS_CONFIRMED

        # ── Priority 2: CRISIS_WARNING ───────────────────────────
        elif vix >= self.vix_crisis_low or spy_close < spy_200dma:
            info.regime = REGIME_CRISIS_WARNING

        # ── Priority 3: NEUTRAL ───────────────────────────────────
        elif self.vix_neutral_low <= vix < self.vix_crisis_low:
            info.regime = REGIME_NEUTRAL

        # ── Priority 4: NORMAL ────────────────────────────────────
        else:
            info.regime = REGIME_NORMAL
            # SPY_200DMA_NEAR_FLAG
            if spy_200dma > 0:
                pct_from_dma = abs(spy_close / spy_200dma - 1.0)
                info.spy_200dma_near_flag = pct_from_dma <= self.spy_near_dma_pct

        # ── VIX flags (independent of regime) ────────────────────
        info.extreme_fear_flag = vix >= self.vix_extreme_fear
        info.panic_liquidity_flag = vix >= self.vix_panic

        return info


class RegimeHistory:
    """Tracks rolling regime state for consecutive-day logic."""

    def __init__(self):
        self._history: list = []  # list of (date, RegimeInfo)

    def record(self, date: pd.Timestamp, info: RegimeInfo) -> None:
        self._history.append((date, info))

    def consecutive_crisis_confirmed(self) -> int:
        """Count consecutive trailing days in CRISIS_CONFIRMED."""
        count = 0
        for _, info in reversed(self._history):
            if info.regime == REGIME_CRISIS_CONFIRMED:
                count += 1
            else:
                break
        return count

    def consecutive_normal(self) -> int:
        """Count consecutive trailing days in NORMAL."""
        count = 0
        for _, info in reversed(self._history):
            if info.regime == REGIME_NORMAL:
                count += 1
            else:
                break
        return count

    def last_regime(self) -> Optional[str]:
        if not self._history:
            return None
        return self._history[-1][1].regime
