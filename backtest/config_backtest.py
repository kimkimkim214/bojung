from dataclasses import dataclass, field
from typing import List


@dataclass
class BacktestConfig:
    # ── Backtest period ───────────────────────────────────────────
    start_date: str = "2019-01-01"
    end_date: str = "2024-12-31"

    # ── Universe ──────────────────────────────────────────────────
    universe: List[str] = field(default_factory=lambda: [
        # Large-cap tech / AI
        "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA",
        # Semiconductors (SOXX-like)
        "AVGO", "AMD", "QCOM", "TXN", "AMAT", "LRCX", "KLAC", "MU",
        # Cloud / Software
        "CRM", "ADBE", "ORCL", "NOW", "PANW",
        # Consumer / Healthcare
        "COST", "WMT", "HD", "PG", "JNJ", "UNH", "AMGN",
        # Financials (will be sector-filtered by crisis engine)
        "V", "MA", "JPM",
    ])

    # ── Capital ───────────────────────────────────────────────────
    initial_capital: float = 100_000.0

    # ── Regime thresholds ─────────────────────────────────────────
    vix_neutral_low: float = 25.0       # VIX >= 25  → NEUTRAL
    vix_crisis_low: float = 30.0        # VIX >= 30  → CRISIS
    vix_extreme_fear: float = 40.0
    vix_panic: float = 50.0
    spy_near_dma_pct: float = 0.02      # abs(SPY/200DMA - 1) <= 2%

    # ── Normal engine ─────────────────────────────────────────────
    rs_buy_top_pct: float = 0.20        # top 20% RS rank to buy
    rs_sell_top_pct: float = 0.40       # sell if outside top 40%
    min_revenue_growth: float = 0.0
    min_eps_growth: float = 0.0
    min_6m_return: float = 0.0
    hard_stop_loss: float = -0.12       # -12% from avg cost
    earnings_buffer_days: int = 3       # no new buy within 3 trading days of earnings
    sma50_consec_days: int = 3          # sell after 3 consecutive closes below SMA50

    # ── Crisis engine ─────────────────────────────────────────────
    crisis_drawdown_trigger: float = -0.15   # -15% from individual 200D high
    fcf_min: float = 0.0
    de_max: float = 1.0
    pe_min: float = 0.0
    pe_max: float = 25.0
    div_yield_min: float = 0.0
    div_yield_max: float = 0.10
    high_div_risk_threshold: float = 0.07
    crisis_price_warn_pct: float = -0.25    # -25% warning from first entry

    # DCA schedule (trading days from first entry)
    crisis_stage1_frac: float = 0.30
    crisis_stage2_days: int = 10
    crisis_stage2_frac: float = 0.30
    crisis_stage3_days: int = 20
    crisis_stage3_frac: float = 0.40

    # Crisis harvest: individual stock > 200DMA for N consecutive closes
    crisis_harvest_consec_days: int = 3

    # ── Portfolio limits ──────────────────────────────────────────
    max_exposure_normal: float = 0.80
    max_exposure_neutral: float = 0.60
    max_position_weight: float = 0.10
    max_holdings: int = 10
    max_holdings_near_flag: int = 5
    near_flag_weight_mult: float = 0.50

    # Crisis 50% trim of normal positions on CRISIS_CONFIRMED
    crisis_normal_trim_frac: float = 0.50

    # ── Execution simulation ──────────────────────────────────────
    slippage_pct: float = 0.001         # 0.1% slippage
    partial_fill_rate: float = 1.0      # 1.0 = always fully filled (set < 1 to simulate partials)
    max_daily_orders: int = 20
    max_orders_per_symbol: int = 3

    # ── Loss limits ───────────────────────────────────────────────
    max_daily_loss_pct: float = -0.03   # realized P&L basis
    max_weekly_loss_pct: float = -0.07
    unrealized_warn_pct: float = -0.05

    # ── Fundamental staleness ─────────────────────────────────────
    fundamental_max_age_days: int = 14

    # ── Reporting lag for quarterly filings (days after quarter end)
    filing_lag_days: int = 45

    # ── Excluded sectors (crisis + normal) ───────────────────────
    excluded_sectors: List[str] = field(default_factory=lambda: [
        "Financial Services", "Financials",
        "Utilities",
        "Real Estate",
    ])

    # ── Output ────────────────────────────────────────────────────
    results_dir: str = "backtest/results"
    cache_dir: str = "backtest/data_cache"
    verbose: bool = True
