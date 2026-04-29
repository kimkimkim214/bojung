"""
Portfolio manager.
Converts buy/sell signals into target portfolio and order list.
Respects exposure limits, position weight limits, and holdings count limits.
"""

import logging
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .regime_detector import RegimeInfo, REGIME_NORMAL, REGIME_NEUTRAL, REGIME_CRISIS_CONFIRMED

logger = logging.getLogger(__name__)


class Order:
    def __init__(
        self,
        ticker: str,
        side: str,                 # "BUY" or "SELL"
        qty: int,
        limit_price: float,
        reason: str,
        engine: str = "normal",    # "normal" or "crisis"
        stage: Optional[int] = None,
    ):
        self.ticker = ticker
        self.side = side
        self.qty = qty
        self.limit_price = limit_price
        self.reason = reason
        self.engine = engine
        self.stage = stage
        self.value = qty * limit_price

    def __repr__(self):
        return f"Order({self.side} {self.qty}x{self.ticker}@{self.limit_price:.2f} [{self.reason}])"


class PortfolioManager:
    def __init__(self, config):
        self.cfg = config

    def build_orders(
        self,
        date: pd.Timestamp,
        buy_candidates: List[dict],
        sell_candidates: List[dict],
        crisis_buys: List[dict],
        portfolio_state: dict,
        regime_info: RegimeInfo,
        current_prices: Dict[str, float],
        crisis_entries: Dict,
    ) -> List[Order]:
        """
        Build concrete order list from signals.
        portfolio_state = {
            'cash': float,
            'positions': {ticker: {'qty': int, 'avg_cost': float, 'engine': str}},
            'portfolio_value': float,
        }
        """
        orders: List[Order] = []
        portfolio_value = portfolio_state["portfolio_value"]
        cash = portfolio_state["cash"]

        # ── Step 1: Sell orders (always first) ───────────────────
        for sig in sell_candidates:
            ticker = sig["ticker"]
            pos = portfolio_state["positions"].get(ticker)
            if pos is None:
                continue
            price = current_prices.get(ticker)
            if price is None:
                continue
            trim_frac = sig.get("trim_frac", 1.0)
            qty = max(1, int(pos["qty"] * trim_frac))
            orders.append(Order(
                ticker=ticker,
                side="SELL",
                qty=qty,
                limit_price=price * (1 - self.cfg.slippage_pct),
                reason=sig["reason"],
                engine=pos.get("engine", "normal"),
            ))

        # ── Step 2: Normal buy orders ─────────────────────────────
        if regime_info.regime == REGIME_NORMAL:
            normal_orders = self._build_normal_buys(
                buy_candidates, portfolio_state, regime_info, current_prices, portfolio_value, cash
            )
            orders.extend(normal_orders)

        # ── Step 3: Crisis buy orders ─────────────────────────────
        if regime_info.regime == REGIME_CRISIS_CONFIRMED:
            crisis_orders = self._build_crisis_buys(
                crisis_buys, portfolio_state, current_prices, portfolio_value, crisis_entries
            )
            orders.extend(crisis_orders)

        return orders

    # ─────────────────────────────────────────────────────────────────
    # Normal buy builder
    # ─────────────────────────────────────────────────────────────────

    def _build_normal_buys(
        self,
        candidates: List[dict],
        portfolio_state: dict,
        regime_info: RegimeInfo,
        prices: Dict[str, float],
        portfolio_value: float,
        cash: float,
    ) -> List[Order]:
        orders = []
        positions = portfolio_state["positions"]

        # Determine effective limits
        if regime_info.spy_200dma_near_flag:
            max_holdings = self.cfg.max_holdings_near_flag
            weight_mult = self.cfg.near_flag_weight_mult
        else:
            max_holdings = self.cfg.max_holdings
            weight_mult = 1.0

        normal_positions = {k: v for k, v in positions.items() if v.get("engine") == "normal"}
        available_slots = max_holdings - len(normal_positions)
        if available_slots <= 0:
            return []

        max_exposure = self.cfg.max_exposure_normal
        current_stock_value = sum(
            pos["qty"] * prices.get(t, 0)
            for t, pos in positions.items()
        )
        max_invest = portfolio_value * max_exposure - current_stock_value
        if max_invest <= 0:
            return []

        available_cash = min(cash, max_invest)
        slot_budget = available_cash / max(available_slots, 1)
        target_weight = min(self.cfg.max_position_weight, 1.0 / max_holdings)
        target_weight *= weight_mult

        used_slots = 0
        for cand in candidates:
            if used_slots >= available_slots:
                break
            ticker = cand["ticker"]
            if ticker in positions:
                continue
            price = prices.get(ticker)
            if price is None or price <= 0:
                continue

            target_value = min(
                portfolio_value * target_weight,
                slot_budget,
                self.cfg.initial_capital * 0.05,  # initial hard cap
            )
            qty = int(target_value / price)
            if qty < 1:
                logger.debug("SKIP %s: budget %.0f < price %.2f", ticker, target_value, price)
                continue

            orders.append(Order(
                ticker=ticker,
                side="BUY",
                qty=qty,
                limit_price=price * (1 + self.cfg.slippage_pct),
                reason=cand["reason"],
                engine="normal",
            ))
            used_slots += 1

        return orders

    # ─────────────────────────────────────────────────────────────────
    # Crisis buy builder
    # ─────────────────────────────────────────────────────────────────

    def _build_crisis_buys(
        self,
        candidates: List[dict],
        portfolio_state: dict,
        prices: Dict[str, float],
        portfolio_value: float,
        crisis_entries: Dict,
    ) -> List[Order]:
        orders = []
        positions = portfolio_state["positions"]
        cash = portfolio_state["cash"]

        for cand in candidates:
            ticker = cand["ticker"]
            stage = cand["stage"]
            stage_frac = cand["stage_frac"]
            price = prices.get(ticker)
            if price is None or price <= 0:
                continue

            entry = crisis_entries.get(ticker)
            if entry is None:
                # New position: allocate budget
                per_position_budget = portfolio_value * self.cfg.max_position_weight * 0.5
                allocated = min(per_position_budget, cash * 0.3)
            else:
                allocated = entry.get("allocated_budget", 0)

            stage_budget = allocated * stage_frac
            qty = int(stage_budget / price)
            if qty < 1:
                logger.debug("SKIP CRISIS %s stage%d: budget %.0f < price %.2f", ticker, stage, stage_budget, price)
                continue
            if stage_budget > cash:
                continue

            orders.append(Order(
                ticker=ticker,
                side="BUY",
                qty=qty,
                limit_price=price * (1 + self.cfg.slippage_pct),
                reason=f"CRISIS_STAGE{stage}",
                engine="crisis",
                stage=stage,
            ))

        return orders

    # ─────────────────────────────────────────────────────────────────
    # Utility
    # ─────────────────────────────────────────────────────────────────

    def get_current_prices(self, tickers: List[str], prices_df: Dict[str, pd.DataFrame], date: pd.Timestamp) -> Dict[str, float]:
        result = {}
        for ticker in tickers:
            df = prices_df.get(ticker)
            if df is None:
                continue
            if date in df.index:
                result[ticker] = float(df.loc[date, "Close"])
            else:
                prior = df.index[df.index <= date]
                if not prior.empty:
                    result[ticker] = float(df.loc[prior[-1], "Close"])
        return result
