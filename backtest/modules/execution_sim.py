"""
Execution simulator.
Simulates order fills with slippage and optional partial fills.
All fills use close price (end-of-day execution approximation).
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .portfolio_manager import Order

logger = logging.getLogger(__name__)


@dataclass
class Fill:
    ticker: str
    side: str
    requested_qty: int
    filled_qty: int
    fill_price: float
    value: float                    # filled_qty * fill_price
    pnl: float = 0.0                # realized P&L for SELL fills
    status: str = "FILLED"          # FILLED / PARTIALLY_FILLED / UNFILLED
    reason: str = ""
    engine: str = "normal"
    stage: Optional[int] = None


class ExecutionSimulator:
    def __init__(self, config):
        self.cfg = config

    def execute(
        self,
        orders: List[Order],
        current_prices: Dict[str, float],
        positions: Dict,             # current positions for P&L calc
    ) -> Tuple[List[Fill], List[dict]]:
        """
        Execute orders against current prices.
        Returns (fills, skipped_orders).

        In backtest: we use close price + slippage.
        Partial fill rate is configurable (default 1.0 = always full fill).
        """
        fills: List[Fill] = []
        skipped: List[dict] = []

        for order in orders:
            price = current_prices.get(order.ticker)
            if price is None:
                skipped.append({"order": order, "reason": "NO_PRICE"})
                continue

            # Slippage: buy higher, sell lower
            if order.side == "BUY":
                fill_price = price * (1 + self.cfg.slippage_pct)
            else:
                fill_price = price * (1 - self.cfg.slippage_pct)

            # Partial fill simulation
            filled_qty = int(order.qty * self.cfg.partial_fill_rate)
            if filled_qty < 1 and order.qty >= 1:
                filled_qty = 1  # always fill at least 1 if order was approved

            status = "FILLED" if filled_qty == order.qty else "PARTIALLY_FILLED"
            value = filled_qty * fill_price

            # Realized P&L for sells
            pnl = 0.0
            if order.side == "SELL":
                pos = positions.get(order.ticker)
                if pos and pos.get("avg_cost", 0) > 0:
                    pnl = filled_qty * (fill_price - pos["avg_cost"])

            fills.append(Fill(
                ticker=order.ticker,
                side=order.side,
                requested_qty=order.qty,
                filled_qty=filled_qty,
                fill_price=fill_price,
                value=value,
                pnl=pnl,
                status=status,
                reason=order.reason,
                engine=order.engine,
                stage=order.stage,
            ))

        return fills, skipped

    def apply_fills(
        self,
        fills: List[Fill],
        portfolio_state: dict,
    ) -> dict:
        """
        Apply fills to portfolio state. Returns updated portfolio_state.
        portfolio_state = {
            'cash': float,
            'positions': {ticker: {'qty': int, 'avg_cost': float, 'engine': str, 'above_200dma_days': int}},
            'portfolio_value': float,   # will be recalculated
        }
        """
        cash = portfolio_state["cash"]
        positions = dict(portfolio_state["positions"])

        for fill in fills:
            if fill.filled_qty == 0:
                continue

            if fill.side == "BUY":
                cash -= fill.value
                if fill.ticker in positions:
                    pos = positions[fill.ticker]
                    new_qty = pos["qty"] + fill.filled_qty
                    new_cost = (pos["qty"] * pos["avg_cost"] + fill.value) / new_qty
                    positions[fill.ticker] = {
                        **pos,
                        "qty": new_qty,
                        "avg_cost": new_cost,
                    }
                else:
                    positions[fill.ticker] = {
                        "qty": fill.filled_qty,
                        "avg_cost": fill.fill_price,
                        "engine": fill.engine,
                        "stage": fill.stage,
                        "above_200dma_days": 0,
                    }

            elif fill.side == "SELL":
                cash += fill.value
                pos = positions.get(fill.ticker)
                if pos:
                    new_qty = pos["qty"] - fill.filled_qty
                    if new_qty <= 0:
                        del positions[fill.ticker]
                    else:
                        positions[fill.ticker] = {**pos, "qty": new_qty}

        portfolio_state["cash"] = cash
        portfolio_state["positions"] = positions
        return portfolio_state

    def recalculate_portfolio_value(
        self,
        portfolio_state: dict,
        current_prices: Dict[str, float],
    ) -> float:
        stock_value = sum(
            pos["qty"] * current_prices.get(ticker, pos["avg_cost"])
            for ticker, pos in portfolio_state["positions"].items()
        )
        total = portfolio_state["cash"] + stock_value
        portfolio_state["portfolio_value"] = total
        return total
