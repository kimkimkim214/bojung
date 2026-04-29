"""
Risk manager: pre-trade risk gate.
Mirrors the production system's pre_trade_risk_check().
"""

import logging
from typing import Dict, List, Optional

import pandas as pd

from .portfolio_manager import Order

logger = logging.getLogger(__name__)


class ExecutionState:
    """Tracks intraday execution counters and loss limits."""

    def __init__(self, initial_capital: float):
        self.initial_capital = initial_capital
        self.daily_order_count: int = 0
        self.orders_by_symbol: Dict[str, int] = {}
        self.daily_realized_pnl: float = 0.0
        self.weekly_realized_pnl: float = 0.0
        self.daily_unrealized_pnl_pct: float = 0.0
        self.kill_switch: bool = False
        self.monitor_only: bool = False
        self.unrealized_warn_triggered: bool = False

    def reset_daily(self):
        self.daily_order_count = 0
        self.orders_by_symbol = {}
        self.daily_realized_pnl = 0.0
        self.daily_unrealized_pnl_pct = 0.0
        self.unrealized_warn_triggered = False
        # kill_switch resets each day
        self.kill_switch = False
        self.monitor_only = False

    def reset_weekly(self):
        self.weekly_realized_pnl = 0.0

    def record_order(self, ticker: str):
        self.daily_order_count += 1
        self.orders_by_symbol[ticker] = self.orders_by_symbol.get(ticker, 0) + 1

    def record_realized_pnl(self, pnl: float, portfolio_value: float):
        self.daily_realized_pnl += pnl
        self.weekly_realized_pnl += pnl


class RiskManager:
    def __init__(self, config):
        self.cfg = config

    def check_order(
        self,
        order: Order,
        portfolio_state: dict,
        execution_state: ExecutionState,
    ) -> tuple:
        """
        Returns (approved: bool, reason: str).
        All checks must pass for approval.
        """
        pv = portfolio_state["portfolio_value"]
        cash = portfolio_state["cash"]
        positions = portfolio_state["positions"]

        # Kill switch
        if execution_state.kill_switch or execution_state.monitor_only:
            return False, "KILL_SWITCH_ACTIVE"

        # Daily order count
        if execution_state.daily_order_count >= self.cfg.max_daily_orders:
            return False, f"MAX_DAILY_ORDERS={execution_state.daily_order_count}"

        # Per-symbol order count
        sym_count = execution_state.orders_by_symbol.get(order.ticker, 0)
        if sym_count >= self.cfg.max_orders_per_symbol:
            return False, f"MAX_SYMBOL_ORDERS={sym_count}"

        # Daily loss limit (realized)
        if pv > 0:
            daily_loss_pct = execution_state.daily_realized_pnl / pv
            if daily_loss_pct <= self.cfg.max_daily_loss_pct:
                return False, f"MAX_DAILY_LOSS={daily_loss_pct:.2%}"

        # Weekly loss limit (realized)
        if pv > 0:
            weekly_loss_pct = execution_state.weekly_realized_pnl / pv
            if weekly_loss_pct <= self.cfg.max_weekly_loss_pct:
                return False, f"MAX_WEEKLY_LOSS={weekly_loss_pct:.2%}"

        # Order value limit
        order_value = order.qty * order.limit_price
        max_order_val = pv * 0.05
        if order_value > max_order_val:
            return False, f"ORDER_TOO_LARGE={order_value:.0f}>{max_order_val:.0f}"

        # BUY-specific checks
        if order.side == "BUY":
            # Minimum 1 share
            if order.qty < 1:
                return False, "QTY_ZERO"

            # Cash availability
            if order_value > cash:
                return False, f"INSUFFICIENT_CASH={cash:.0f}<{order_value:.0f}"

            # Unrealized drawdown warning → reduce buy size (handled upstream by halving qty)
            if execution_state.unrealized_warn_triggered:
                max_buy = pv * 0.02  # 2% max per buy when warning active
                if order_value > max_buy:
                    return False, f"UNREALIZED_WARN_LIMIT={order_value:.0f}>{max_buy:.0f}"

            # Position weight check
            current_pos_value = 0
            if order.ticker in positions:
                pos = positions[order.ticker]
                current_pos_value = pos["qty"] * order.limit_price
            new_pos_value = current_pos_value + order_value
            if pv > 0 and new_pos_value / pv > self.cfg.max_position_weight * 1.2:
                return False, f"POSITION_WEIGHT_EXCEED={new_pos_value/pv:.2%}"

            # Total exposure check
            current_stock_value = sum(
                pos["qty"] * order.limit_price  # approximate with order price
                for t, pos in positions.items()
            )
            new_total = current_stock_value + order_value
            max_exp = self.cfg.max_exposure_normal
            if pv > 0 and new_total / pv > max_exp * 1.05:  # 5% buffer
                return False, f"MAX_EXPOSURE={new_total/pv:.2%}>{max_exp:.0%}"

        return True, "PASS"

    def update_unrealized_warning(
        self,
        execution_state: ExecutionState,
        unrealized_pnl_pct: float,
    ) -> bool:
        """Check and update unrealized drawdown warning. Returns True if triggered."""
        if unrealized_pnl_pct <= self.cfg.unrealized_warn_pct:
            if not execution_state.unrealized_warn_triggered:
                logger.warning(
                    "UNREALIZED_WARN triggered: %.2f%% (threshold: %.2f%%)",
                    unrealized_pnl_pct * 100,
                    self.cfg.unrealized_warn_pct * 100,
                )
            execution_state.unrealized_warn_triggered = True
        else:
            execution_state.unrealized_warn_triggered = False
        return execution_state.unrealized_warn_triggered

    def check_kill_switch(
        self,
        execution_state: ExecutionState,
        daily_realized_pct: float,
        weekly_realized_pct: float,
        daily_order_count: int,
    ) -> Optional[str]:
        """Returns kill reason if kill switch should activate, else None."""
        if daily_realized_pct <= self.cfg.max_daily_loss_pct:
            execution_state.kill_switch = True
            return f"DAILY_LOSS_LIMIT={daily_realized_pct:.2%}"
        if weekly_realized_pct <= self.cfg.max_weekly_loss_pct:
            execution_state.kill_switch = True
            return f"WEEKLY_LOSS_LIMIT={weekly_realized_pct:.2%}"
        if daily_order_count >= self.cfg.max_daily_orders:
            execution_state.monitor_only = True
            return f"MAX_DAILY_ORDERS={daily_order_count}"
        return None
