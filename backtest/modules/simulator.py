"""
Core backtest simulator.
Runs day-by-day simulation applying regime detection, signal generation,
portfolio construction, risk gating, and execution simulation.
"""

import logging
from copy import deepcopy
from typing import Dict, List, Optional

import pandas as pd
from tqdm import tqdm

from .data_fetcher import DataFetcher
from .indicators import IndicatorEngine
from .fundamentals_processor import FundamentalsProcessor
from .regime_detector import RegimeDetector, RegimeHistory, REGIME_NORMAL, REGIME_NEUTRAL, REGIME_CRISIS_CONFIRMED
from .normal_engine import NormalEngine
from .crisis_engine import CrisisEngine
from .portfolio_manager import PortfolioManager
from .risk_manager import RiskManager, ExecutionState
from .execution_sim import ExecutionSimulator
from .reporter import BacktestReporter

logger = logging.getLogger(__name__)

# Days of the week for weekly P&L reset
WEEKDAY_MONDAY = 0


class BacktestSimulator:
    def __init__(self, config):
        self.cfg = config

        # Components
        self.fetcher = DataFetcher(cache_dir=config.cache_dir)
        self.regime_detector = RegimeDetector(
            vix_neutral_low=config.vix_neutral_low,
            vix_crisis_low=config.vix_crisis_low,
            vix_extreme_fear=config.vix_extreme_fear,
            vix_panic=config.vix_panic,
            spy_near_dma_pct=config.spy_near_dma_pct,
        )
        self.normal_engine = NormalEngine(config)
        self.crisis_engine = CrisisEngine(config)
        self.portfolio_manager = PortfolioManager(config)
        self.risk_manager = RiskManager(config)
        self.execution_sim = ExecutionSimulator(config)
        self.reporter = BacktestReporter(config.results_dir)

        # State (initialized in run())
        self.prices: Dict = {}
        self.vix: pd.Series = None
        self.fundamentals: Dict = {}
        self.indicator_engine: IndicatorEngine = None
        self.fund_processor: FundamentalsProcessor = None

    # ─────────────────────────────────────────────────────────────────
    # Main entry
    # ─────────────────────────────────────────────────────────────────

    def run(self) -> dict:
        logger.info("=== Quantamental Backtest v2.2 ===")
        logger.info("Period: %s → %s", self.cfg.start_date, self.cfg.end_date)
        logger.info("Universe: %d tickers", len(self.cfg.universe))

        # ── 1. Fetch data ─────────────────────────────────────────
        self.prices, self.vix, self.fundamentals = self.fetcher.fetch_all(
            self.cfg.universe,
            self.cfg.start_date,
            self.cfg.end_date,
        )

        # ── 2. Pre-compute indicators ─────────────────────────────
        self.indicator_engine = IndicatorEngine(self.prices)
        self.indicator_engine.build(self.cfg.universe)

        # ── 3. Initialize fundamental processor ──────────────────
        self.fund_processor = FundamentalsProcessor(
            self.fundamentals,
            filing_lag_days=self.cfg.filing_lag_days,
        )

        # ── 4. Get trading calendar ───────────────────────────────
        all_trading_days = self.indicator_engine.get_trading_days()
        start = pd.Timestamp(self.cfg.start_date)
        end = pd.Timestamp(self.cfg.end_date)
        trading_days = all_trading_days[(all_trading_days >= start) & (all_trading_days <= end)]

        if len(trading_days) == 0:
            raise ValueError("No trading days in the specified period")
        logger.info("Trading days: %d", len(trading_days))

        # ── 5. Initialize portfolio state ─────────────────────────
        portfolio_state = {
            "cash": self.cfg.initial_capital,
            "positions": {},
            "portfolio_value": self.cfg.initial_capital,
        }
        execution_state = ExecutionState(initial_capital=self.cfg.initial_capital)
        regime_history = RegimeHistory()
        crisis_entries: Dict = {}  # {ticker: entry record}
        above_200dma_tracker: Dict[str, int] = {}  # {ticker: consecutive days above 200DMA}

        # ── 6. Recording ──────────────────────────────────────────
        portfolio_history: List[dict] = []
        trades: List[dict] = []
        regime_history_log: List[dict] = []
        prev_week = None

        # ── 7. Day-by-day simulation ──────────────────────────────
        for date in tqdm(trading_days, desc="Simulating", disable=not self.cfg.verbose):
            # Reset daily execution state
            execution_state.reset_daily()

            # Reset weekly P&L on Monday
            if prev_week is not None and date.dayofweek == WEEKDAY_MONDAY:
                execution_state.reset_weekly()
            prev_week = date.isocalendar()[1]

            # ── Current prices ────────────────────────────────────
            current_prices = self.portfolio_manager.get_current_prices(
                self.cfg.universe + ["SPY"], self.prices, date
            )

            # ── SPY indicators for regime detection ───────────────
            spy_ind = self.indicator_engine.lookup("SPY", date)
            if spy_ind is None or spy_ind["sma200"] is None:
                continue  # not enough history yet

            vix_close = self._get_vix(date)
            if vix_close is None:
                continue

            spy_close = spy_ind["close"]
            spy_200dma = spy_ind["sma200"]

            # ── Regime detection ──────────────────────────────────
            regime_info = self.regime_detector.detect(vix_close, spy_close, spy_200dma)
            regime_history.record(date, regime_info)
            regime_history_log.append({
                "date": date,
                "regime": regime_info.regime,
                "vix": round(vix_close, 2),
                "spy": round(spy_close, 2),
                "spy_200dma": round(spy_200dma, 2),
                "spy_near_flag": regime_info.spy_200dma_near_flag,
                "extreme_fear": regime_info.extreme_fear_flag,
            })

            # ── Per-ticker indicators and fundamentals ────────────
            indicators: Dict = {}
            fundamentals: Dict = {}
            for ticker in self.cfg.universe:
                ind = self.indicator_engine.lookup(ticker, date)
                if ind:
                    indicators[ticker] = ind
                price = current_prices.get(ticker)
                fund = self.fund_processor.get_with_price(ticker, date, price or 0)
                fundamentals[ticker] = fund

            # ── Update above-200DMA consecutive tracker ───────────
            for ticker, pos in portfolio_state["positions"].items():
                if pos.get("engine") == "crisis":
                    ind = indicators.get(ticker)
                    if ind and ind.get("close") and ind.get("sma200"):
                        if ind["close"] > ind["sma200"]:
                            above_200dma_tracker[ticker] = above_200dma_tracker.get(ticker, 0) + 1
                        else:
                            above_200dma_tracker[ticker] = 0

            # ── Update unrealized P&L warning ────────────────────
            unrealized_pnl = self._compute_unrealized_pnl(portfolio_state, current_prices)
            if portfolio_state["portfolio_value"] > 0:
                unrealized_pct = unrealized_pnl / portfolio_state["portfolio_value"]
                self.risk_manager.update_unrealized_warning(execution_state, unrealized_pct)

            # ── Generate signals ──────────────────────────────────
            sell_candidates = []
            buy_candidates = []
            crisis_buys = []

            # Always check for sells (hard stops, fundamentals)
            sell_candidates = self.normal_engine.get_sell_candidates(
                date, portfolio_state["positions"], indicators, fundamentals, regime_info
            )

            # Crisis fundamental sells
            crisis_fund_sells = self.crisis_engine.get_fundamental_sells(
                portfolio_state["positions"], fundamentals, crisis_entries
            )
            sell_candidates.extend(crisis_fund_sells)

            # Crisis harvest (exit to normal)
            if regime_info.is_normal:
                harvest_candidates = []
                for ticker, pos in portfolio_state["positions"].items():
                    if pos.get("engine") == "crisis":
                        days_above = above_200dma_tracker.get(ticker, 0)
                        if days_above >= self.cfg.crisis_harvest_consec_days:
                            harvest_candidates.append({
                                "ticker": ticker,
                                "action": "SELL",
                                "reason": f"CRISIS_HARVEST_{days_above}D_ABOVE_200DMA",
                                "trim_frac": 1.0,
                            })
                sell_candidates.extend(harvest_candidates)

            if regime_info.is_normal:
                buy_candidates = self.normal_engine.get_buy_candidates(
                    date, self.cfg.universe, indicators, fundamentals, regime_info,
                    portfolio_state["positions"], all_trading_days
                )

            elif regime_info.is_neutral:
                # Trim weak positions
                neutral_trims = self.normal_engine.get_neutral_trims(
                    date, portfolio_state["positions"], indicators, fundamentals
                )
                sell_candidates.extend(neutral_trims)

            elif regime_info.is_crisis:
                # Trim normal positions (50%, worst first, only once per CRISIS entry)
                # Track whether we've done the crisis trim
                if not portfolio_state.get("crisis_trim_done"):
                    crisis_trims = self.normal_engine.get_crisis_trims(
                        portfolio_state["positions"], indicators, fundamentals,
                        trim_frac=self.cfg.crisis_normal_trim_frac,
                    )
                    sell_candidates.extend(crisis_trims)
                    if crisis_trims:
                        portfolio_state["crisis_trim_done"] = True

                # Crisis DCA buys
                crisis_buys = self.crisis_engine.get_buy_candidates(
                    date, self.cfg.universe, indicators, fundamentals,
                    regime_info, crisis_entries, portfolio_state["positions"]
                )

            elif regime_info.is_warning:
                pass  # No new buys, no forced sells

            # Reset crisis_trim_done when not in crisis
            if not regime_info.is_crisis:
                portfolio_state.pop("crisis_trim_done", None)

            # ── Build orders ──────────────────────────────────────
            orders = self.portfolio_manager.build_orders(
                date=date,
                buy_candidates=buy_candidates,
                sell_candidates=sell_candidates,
                crisis_buys=crisis_buys,
                portfolio_state=portfolio_state,
                regime_info=regime_info,
                current_prices=current_prices,
                crisis_entries=crisis_entries,
            )

            # ── Risk gate ─────────────────────────────────────────
            approved_orders = []
            for order in orders:
                approved, reason = self.risk_manager.check_order(
                    order, portfolio_state, execution_state
                )
                if approved:
                    approved_orders.append(order)
                    execution_state.record_order(order.ticker)
                else:
                    logger.debug("Order BLOCKED %s: %s", order, reason)

            # ── Execute ───────────────────────────────────────────
            fills, skipped = self.execution_sim.execute(
                approved_orders, current_prices, portfolio_state["positions"]
            )

            # ── Apply fills ───────────────────────────────────────
            if fills:
                portfolio_state = self.execution_sim.apply_fills(fills, portfolio_state)

                for fill in fills:
                    execution_state.record_realized_pnl(fill.pnl, portfolio_state["portfolio_value"])
                    trades.append({
                        "date": str(date.date()),
                        "ticker": fill.ticker,
                        "side": fill.side,
                        "qty": fill.filled_qty,
                        "price": round(fill.fill_price, 4),
                        "value": round(fill.value, 2),
                        "pnl": round(fill.pnl, 2),
                        "engine": fill.engine,
                        "stage": fill.stage,
                        "reason": fill.reason,
                        "regime": regime_info.regime,
                    })

                    # Update crisis_entries
                    if fill.side == "BUY" and fill.engine == "crisis":
                        entry = crisis_entries.get(fill.ticker)
                        if entry is None:
                            crisis_entries[fill.ticker] = self.crisis_engine.create_entry_record(
                                fill.ticker, date, fill.fill_price, fill.value / self.cfg.crisis_stage1_frac, vix_close
                            )
                        else:
                            stage = fill.stage or 2
                            crisis_entries[fill.ticker] = self.crisis_engine.update_entry_record(
                                entry, stage, date, fill.fill_price, fill.value, vix_close
                            )

                    # Remove crisis entry on full sell
                    if fill.side == "SELL" and fill.ticker not in portfolio_state["positions"]:
                        crisis_entries.pop(fill.ticker, None)
                        above_200dma_tracker.pop(fill.ticker, None)

            # ── Recalculate portfolio value ───────────────────────
            self.execution_sim.recalculate_portfolio_value(portfolio_state, current_prices)

            # ── Check kill switch ─────────────────────────────────
            if portfolio_state["portfolio_value"] > 0:
                daily_pct = execution_state.daily_realized_pnl / portfolio_state["portfolio_value"]
                weekly_pct = execution_state.weekly_realized_pnl / portfolio_state["portfolio_value"]
                kill_reason = self.risk_manager.check_kill_switch(
                    execution_state, daily_pct, weekly_pct, execution_state.daily_order_count
                )
                if kill_reason:
                    logger.warning("KILL SWITCH: %s on %s", kill_reason, date.date())

            # ── Record daily snapshot ─────────────────────────────
            portfolio_history.append({
                "date": date,
                "portfolio_value": round(portfolio_state["portfolio_value"], 2),
                "cash": round(portfolio_state["cash"], 2),
                "n_positions": len(portfolio_state["positions"]),
                "regime": regime_info.regime,
                "vix": round(vix_close, 2),
                "daily_realized_pnl": round(execution_state.daily_realized_pnl, 2),
                "n_orders_today": execution_state.daily_order_count,
            })

        # ── 8. Generate report ────────────────────────────────────
        spy_prices = pd.Series(
            {date: self.prices["SPY"].loc[date, "Close"]
             for date in trading_days if date in self.prices.get("SPY", pd.DataFrame()).index},
            dtype=float,
        ) if "SPY" in self.prices else None

        self.reporter.regime_history_data = regime_history_log
        metrics = self.reporter.generate(
            portfolio_history=portfolio_history,
            trades=trades,
            regime_history=regime_history_log,
            benchmark_prices=spy_prices,
            config=self.cfg,
        )
        return metrics

    # ─────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────

    def _get_vix(self, date: pd.Timestamp) -> Optional[float]:
        if self.vix is None:
            return None
        if date in self.vix.index:
            return float(self.vix.loc[date])
        prior = self.vix.index[self.vix.index <= date]
        if prior.empty:
            return None
        return float(self.vix.loc[prior[-1]])

    def _compute_unrealized_pnl(self, portfolio_state: dict, prices: Dict[str, float]) -> float:
        total = 0.0
        for ticker, pos in portfolio_state["positions"].items():
            price = prices.get(ticker, pos.get("avg_cost", 0))
            total += pos["qty"] * (price - pos["avg_cost"])
        return total
