#!/usr/bin/env python3
"""
Quantamental Backtest v2.2 — Main Entry Point

Usage:
    python backtest/main_backtest.py
    python backtest/main_backtest.py --start 2020-01-01 --end 2023-12-31
    python backtest/main_backtest.py --start 2019-01-01 --end 2024-12-31 --capital 100000
    python backtest/main_backtest.py --refresh   # force re-download data
    python backtest/main_backtest.py --tickers AAPL MSFT NVDA GOOGL AMZN COST UNH

Online data source: yfinance (no CSV required)
"""

import argparse
import logging
import os
import sys

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.config_backtest import BacktestConfig
from backtest.modules.simulator import BacktestSimulator


def setup_logging(verbose: bool = True) -> None:
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=level,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("backtest/results/backtest.log", mode="w"),
        ],
    )
    # Quiet noisy third-party loggers
    for noisy in ["yfinance", "peewee", "urllib3", "requests"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Quantamental Backtest v2.2 — online data (yfinance)"
    )
    parser.add_argument("--start", default="2019-01-01", help="Backtest start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2024-12-31", help="Backtest end date (YYYY-MM-DD)")
    parser.add_argument("--capital", type=float, default=100_000.0, help="Initial capital (USD)")
    parser.add_argument("--tickers", nargs="*", help="Override universe tickers")
    parser.add_argument("--refresh", action="store_true", help="Force re-download all data")
    parser.add_argument("--quiet", action="store_true", help="Reduce log output")

    # Regime overrides
    parser.add_argument("--vix-neutral", type=float, default=25.0, help="VIX threshold for NEUTRAL")
    parser.add_argument("--vix-crisis", type=float, default=30.0, help="VIX threshold for CRISIS")

    # Portfolio overrides
    parser.add_argument("--max-holdings", type=int, default=10)
    parser.add_argument("--max-weight", type=float, default=0.10, help="Max single position weight")
    parser.add_argument("--slippage", type=float, default=0.001, help="Slippage pct (0.001 = 0.1%)")

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Ensure results directory exists before logging
    os.makedirs("backtest/results", exist_ok=True)
    setup_logging(verbose=not args.quiet)

    logger = logging.getLogger("main_backtest")
    logger.info("Starting Quantamental Backtest v2.2")

    # Build config
    cfg = BacktestConfig(
        start_date=args.start,
        end_date=args.end,
        initial_capital=args.capital,
        vix_neutral_low=args.vix_neutral,
        vix_crisis_low=args.vix_crisis,
        max_holdings=args.max_holdings,
        max_position_weight=args.max_weight,
        slippage_pct=args.slippage,
        verbose=not args.quiet,
    )

    if args.tickers:
        cfg.universe = args.tickers
        logger.info("Universe overridden: %s", cfg.universe)

    # Inject refresh flag into fetcher
    if args.refresh:
        logger.info("Force refresh: data cache will be cleared")

    # Run simulation
    simulator = BacktestSimulator(cfg)

    # Patch force_refresh if needed
    if args.refresh:
        original_fetch = simulator.fetcher.fetch_all
        def fetch_with_refresh(*a, **kw):
            kw["force_refresh"] = True
            return original_fetch(*a, **kw)
        simulator.fetcher.fetch_all = fetch_with_refresh

    try:
        metrics = simulator.run()
        logger.info("Backtest complete. Results in: %s", cfg.results_dir)
        return metrics
    except KeyboardInterrupt:
        logger.info("Backtest interrupted by user.")
        sys.exit(0)
    except Exception as e:
        logger.exception("Backtest failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
