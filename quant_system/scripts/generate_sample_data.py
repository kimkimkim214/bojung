"""
Generate synthetic sample data for local testing.
Run from the project root:
  python scripts/generate_sample_data.py

Creates:
  data/prices/<symbol>.csv  — synthetic OHLCV
  data/fundamentals/fundamentals.csv
  data/market_breadth/breadth.csv
  data/earnings_calendar/earnings.csv
"""
from __future__ import annotations

import sys
import random
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.calendar import get_trading_days

random.seed(42)
np.random.seed(42)

START = "2022-01-01"
END   = "2024-12-31"
TRADING_DAYS = get_trading_days(START, END)

STOCK_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN",
    "AVGO", "LLY", "JPM", "UNH", "XOM", "V", "MA",
    "HD", "PG", "COST", "ABBV", "MRK", "CVX", "CRM",
    "ANET", "PANW", "DXCM", "ENPH", "AXON", "CRWD",
    "SMCI", "ARM", "APP", "CELH",
]

MARKET_SYMBOLS = {
    "SPY":  (430, 0.0003, 0.010),
    "QQQ":  (360, 0.0004, 0.012),
    "GLD":  (175, 0.0001, 0.007),
    "TLT":  (95,  -0.0002, 0.009),
    "^VIX": (20,  0.0000, 0.05),
}


def make_prices(n: int, start: float, drift: float, vol: float) -> pd.DataFrame:
    log_ret = np.random.normal(drift, vol, n)
    close = start * np.exp(np.cumsum(log_ret))
    high  = close * (1 + np.abs(np.random.normal(0, 0.005, n)))
    low   = close * (1 - np.abs(np.random.normal(0, 0.005, n)))
    open_ = close * np.exp(-log_ret)   # prev close approximately
    volume = np.random.lognormal(16, 0.4, n).astype(int)
    df = pd.DataFrame({
        "date":   TRADING_DAYS[:n],
        "open":   open_.round(2),
        "high":   high.round(2),
        "low":    low.round(2),
        "close":  close.round(2),
        "volume": volume,
    })
    df["low"] = df[["low", "close", "open"]].min(axis=1)
    df["high"] = df[["high", "close", "open"]].max(axis=1)
    return df


def write_price_csv(symbol: str, df: pd.DataFrame) -> None:
    out = ROOT / "data" / "prices" / f"{symbol}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"  {out.name}")


def generate_market_prices() -> None:
    print("Generating market ETF + VIX prices...")
    n = len(TRADING_DAYS)
    for sym, (start, drift, vol) in MARKET_SYMBOLS.items():
        df = make_prices(n, start, drift, vol)
        if sym == "^VIX":
            df["close"] = df["close"].clip(lower=10, upper=80)
            df["open"] = df["close"].shift(1).fillna(df["close"])
            df["high"] = df[["close", "open"]].max(axis=1) * 1.02
            df["low"]  = df[["close", "open"]].min(axis=1) * 0.98
        write_price_csv(sym, df)


def generate_stock_prices() -> None:
    print("Generating stock prices...")
    n = len(TRADING_DAYS)
    for sym in STOCK_UNIVERSE:
        start = random.uniform(30, 400)
        drift = random.uniform(-0.0002, 0.0008)
        vol   = random.uniform(0.012, 0.025)
        df = make_prices(n, start, drift, vol)
        write_price_csv(sym, df)


def generate_fundamentals() -> None:
    print("Generating fundamentals.csv...")
    rows = []
    for sym in STOCK_UNIVERSE:
        rows.append({
            "symbol":             sym,
            "period_end_date":    "2023-09-30",
            "filing_date":        "2023-11-05",
            "available_date":     "2023-11-06",
            "market_cap":         random.randint(10, 3000) * 1_000_000_000,
            "revenue_growth_yoy": round(random.uniform(-0.05, 0.40), 3),
            "gross_margin":       round(random.uniform(0.25, 0.75), 3),
            "roic":               round(random.uniform(0.05, 0.35), 3),
            "fcf_positive":       True,
            "buyback_yield":      round(random.uniform(0.0, 0.04), 4),
            "fcf_yield":          round(random.uniform(0.01, 0.06), 4),
            "debt_to_equity":     round(random.uniform(0.1, 2.5), 2),
            "turnaround_flag":    random.random() < 0.15,
            "rs_rank_improving":  random.random() < 0.5,
            "sector":             random.choice(["Technology", "Healthcare", "Financials",
                                                 "Consumer Discretionary", "Energy", "Industrials"]),
            "industry":           random.choice(["Software", "Semiconductors", "Banks",
                                                 "Biotech", "Oil & Gas", "Retail"]),
            "security_type":      "COMMON",
            "delisting_date":     None,
        })
    df = pd.DataFrame(rows)
    out = ROOT / "data" / "fundamentals" / "fundamentals.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"  {out.name}  ({len(rows)} symbols)")


def generate_breadth() -> None:
    print("Generating market_breadth/breadth.csv...")
    n = len(TRADING_DAYS)
    df = pd.DataFrame({
        "date":              TRADING_DAYS,
        "pct_above_50dma":   np.clip(np.random.normal(0.60, 0.15, n), 0, 1).round(3),
        "pct_above_200dma":  np.clip(np.random.normal(0.65, 0.12, n), 0, 1).round(3),
        "nh_nl_ratio":       np.random.normal(0.1, 0.3, n).round(3),
        "mclellan":          np.random.normal(10, 40, n).round(1),
        "hy_spread":         np.clip(np.random.normal(400, 60, n), 250, 800).round(1),
        "hy_spread_60d_avg": 400.0,
        "hy_spread_20d_delta": np.random.normal(0, 20, n).round(1),
        "hy_oas_20d_change_bp": np.random.normal(0, 15, n).round(1),
        "yield_10y_3m_bp":   np.random.normal(100, 80, n).round(1),
    })
    out = ROOT / "data" / "market_breadth" / "breadth.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"  {out.name}")


def generate_earnings_calendar() -> None:
    print("Generating earnings_calendar/earnings.csv...")
    rows = []
    quarters = ["Q1FY2023", "Q2FY2023", "Q3FY2023", "Q4FY2023",
                "Q1FY2024", "Q2FY2024", "Q3FY2024", "Q4FY2024"]
    earnings_dates = [
        "2023-02-02", "2023-05-04", "2023-08-03", "2023-11-02",
        "2024-02-01", "2024-05-02", "2024-08-01", "2024-10-31",
    ]
    for sym in STOCK_UNIVERSE:
        for qtr, dt in zip(quarters, earnings_dates):
            rows.append({
                "symbol":        sym,
                "earnings_date": dt,
                "fiscal_period": f"{sym}_{qtr}",
                "timing":        random.choice(["BMO", "AMC"]),
            })
    df = pd.DataFrame(rows)
    out = ROOT / "data" / "earnings_calendar" / "earnings.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"  {out.name}  ({len(rows)} events)")


if __name__ == "__main__":
    print(f"Generating sample data for {len(TRADING_DAYS)} trading days...")
    generate_market_prices()
    generate_stock_prices()
    generate_fundamentals()
    generate_breadth()
    generate_earnings_calendar()
    print("\nDone. Run the scanner with:")
    print("  python main_eod_scan.py --date 2024-06-14 --summary")
    print("  python main_eod_scan.py --start 2024-01-01 --end 2024-03-31 --summary")
