"""
Entry point for the Phase 1 EOD Scanner (backtest mode).

Usage:
  python main_eod_scan.py --start 2023-01-01 --end 2024-12-31
  python main_eod_scan.py --date 2024-06-14          # single day
  python main_eod_scan.py --help
"""
from __future__ import annotations

import argparse
import logging
import sys
import yaml
from pathlib import Path

import pandas as pd

# Ensure project root is on sys.path when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.backtest_engine import run_backtest, summarize_backtest
from src.data_loader import load_all_prices

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parent / "config"

MARKET_SYMBOLS = ["SPY", "QQQ", "GLD", "TLT", "^VIX"]

DEFAULT_STOCK_SYMBOLS = [
    # Replace with your actual universe; these are illustrative
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN",
    "AVGO", "LLY", "JPM", "UNH", "XOM", "V", "MA",
    "HD", "PG", "COST", "ABBV", "MRK", "CVX", "CRM",
]


def _load_yaml(name: str) -> dict:
    path = _CONFIG_DIR / name
    if not path.exists():
        log.warning(f"Config not found: {path}")
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _load_stock_symbols() -> list[str]:
    """
    Load the stock universe from data/fundamentals/fundamentals.csv if available,
    otherwise fall back to the built-in default list.
    """
    fund_path = Path(__file__).resolve().parent / "data" / "fundamentals" / "fundamentals.csv"
    if fund_path.exists():
        df = pd.read_csv(fund_path)
        if "symbol" in df.columns:
            return df["symbol"].dropna().unique().tolist()
    return DEFAULT_STOCK_SYMBOLS


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Quant System — Phase 1 EOD Scanner (backtest mode)"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--date",  help="Single date (YYYY-MM-DD)")
    group.add_argument("--start", help="Start date for range (YYYY-MM-DD)")

    parser.add_argument("--end",    default=None, help="End date (default: same as --start or today)")
    parser.add_argument("--quiet",  action="store_true", help="Suppress per-day console output")
    parser.add_argument("--summary", action="store_true", help="Print regime summary table at end")
    args = parser.parse_args()

    if args.date:
        start = end = args.date
    else:
        start = args.start
        end   = args.end or args.start

    # Load configs
    costs_cfg  = _load_yaml("costs.yaml")
    regime_cfg = _load_yaml("regime_thresholds.yaml")
    paper_cfg  = _load_yaml("phase1_paper.yaml").get("paper_trading", {})
    basket_cfg = _load_yaml("basket_rules.yaml")

    # Merge all config into one dict for convenience
    full_config = {**costs_cfg, **regime_cfg, **basket_cfg}

    stock_symbols = _load_stock_symbols()
    log.info(f"Universe: {len(stock_symbols)} symbols | {start} → {end}")

    results = run_backtest(
        start_date=start,
        end_date=end,
        market_symbols=MARKET_SYMBOLS,
        stock_symbols=stock_symbols,
        config=full_config,
        paper_config=paper_cfg,
        print_daily=not args.quiet,
    )

    if args.summary or args.date:
        df = summarize_backtest(results)
        print("\n" + "=" * 80)
        print("BACKTEST SUMMARY")
        print("=" * 80)
        print(df.to_string(index=False))
        print(f"\nTotal trading days processed: {len(results)}")
        if not df.empty:
            print("\nRegime distribution:")
            print(df["regime"].value_counts().to_string())

    reports_dir = Path(__file__).resolve().parent / "reports" / "eod"
    print(f"\nReports saved to: {reports_dir}")


if __name__ == "__main__":
    main()
