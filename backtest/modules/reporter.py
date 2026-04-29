"""
Backtest reporter.
Computes performance metrics and generates output files + charts.
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from tabulate import tabulate

logger = logging.getLogger(__name__)

REGIME_COLORS = {
    "NORMAL": "#2ecc71",
    "NEUTRAL": "#f39c12",
    "CRISIS_WARNING": "#e67e22",
    "CRISIS_CONFIRMED": "#e74c3c",
}


class BacktestReporter:
    def __init__(self, results_dir: str):
        self.results_dir = results_dir
        os.makedirs(results_dir, exist_ok=True)

    # ─────────────────────────────────────────────────────────────────
    # Main entry
    # ─────────────────────────────────────────────────────────────────

    def generate(
        self,
        portfolio_history: List[dict],
        trades: List[dict],
        regime_history: List[dict],
        benchmark_prices: Optional[pd.Series] = None,
        config=None,
    ) -> dict:
        df = pd.DataFrame(portfolio_history)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()

        metrics = self._compute_metrics(df, trades, benchmark_prices)
        self._print_summary(metrics)
        self._save_json(metrics, trades, portfolio_history, regime_history)
        self._save_csvs(df, trades)
        self._plot_all(df, regime_history, benchmark_prices, metrics)

        logger.info("Report saved to %s", self.results_dir)
        return metrics

    # ─────────────────────────────────────────────────────────────────
    # Metrics
    # ─────────────────────────────────────────────────────────────────

    def _compute_metrics(
        self,
        df: pd.DataFrame,
        trades: List[dict],
        benchmark: Optional[pd.Series],
    ) -> dict:
        pv = df["portfolio_value"]
        returns = pv.pct_change().dropna()

        total_return = (pv.iloc[-1] / pv.iloc[0]) - 1
        n_years = (pv.index[-1] - pv.index[0]).days / 365.25
        cagr = (1 + total_return) ** (1 / n_years) - 1 if n_years > 0 else 0

        sharpe = self._sharpe(returns)
        max_dd, dd_start, dd_end = self._max_drawdown(pv)
        sortino = self._sortino(returns)
        calmar = cagr / abs(max_dd) if max_dd != 0 else 0

        # Trade stats
        sell_trades = [t for t in trades if t["side"] == "SELL"]
        wins = [t for t in sell_trades if t.get("pnl", 0) > 0]
        losses = [t for t in sell_trades if t.get("pnl", 0) <= 0]
        win_rate = len(wins) / len(sell_trades) if sell_trades else 0
        avg_win = np.mean([t["pnl"] for t in wins]) if wins else 0
        avg_loss = np.mean([t["pnl"] for t in losses]) if losses else 0
        profit_factor = abs(sum(t["pnl"] for t in wins) / sum(t["pnl"] for t in losses)) if losses and sum(t["pnl"] for t in losses) != 0 else float("inf")

        # Regime breakdown
        regime_counts: Dict[str, int] = {}
        for rh in self.regime_history_data if hasattr(self, "regime_history_data") else []:
            r = rh.get("regime", "UNKNOWN")
            regime_counts[r] = regime_counts.get(r, 0) + 1

        # Benchmark
        benchmark_metrics = {}
        if benchmark is not None:
            bm = benchmark.reindex(pv.index, method="ffill").dropna()
            bm_returns = bm.pct_change().dropna()
            bm_total = (bm.iloc[-1] / bm.iloc[0]) - 1 if len(bm) > 1 else 0
            bm_cagr = (1 + bm_total) ** (1 / n_years) - 1 if n_years > 0 else 0
            bm_sharpe = self._sharpe(bm_returns)
            bm_dd, _, _ = self._max_drawdown(bm)
            benchmark_metrics = {
                "bm_total_return": round(bm_total * 100, 2),
                "bm_cagr": round(bm_cagr * 100, 2),
                "bm_sharpe": round(bm_sharpe, 3),
                "bm_max_drawdown": round(bm_dd * 100, 2),
                "excess_return": round((cagr - bm_cagr) * 100, 2),
            }

        return {
            "period_start": str(pv.index[0].date()),
            "period_end": str(pv.index[-1].date()),
            "initial_capital": round(float(pv.iloc[0]), 2),
            "final_value": round(float(pv.iloc[-1]), 2),
            "total_return_pct": round(total_return * 100, 2),
            "cagr_pct": round(cagr * 100, 2),
            "sharpe": round(sharpe, 3),
            "sortino": round(sortino, 3),
            "calmar": round(calmar, 3),
            "max_drawdown_pct": round(max_dd * 100, 2),
            "max_dd_start": str(dd_start.date()) if dd_start else None,
            "max_dd_end": str(dd_end.date()) if dd_end else None,
            "total_trades": len(trades),
            "sell_trades": len(sell_trades),
            "win_rate_pct": round(win_rate * 100, 2),
            "avg_win_usd": round(avg_win, 2),
            "avg_loss_usd": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2),
            "regime_distribution": regime_counts,
            **benchmark_metrics,
        }

    def _sharpe(self, returns: pd.Series, risk_free_daily: float = 0.0) -> float:
        excess = returns - risk_free_daily
        std = excess.std()
        if std == 0:
            return 0.0
        return float(excess.mean() / std * np.sqrt(252))

    def _sortino(self, returns: pd.Series) -> float:
        neg = returns[returns < 0]
        downside_std = neg.std() if not neg.empty else 0
        if downside_std == 0:
            return 0.0
        return float(returns.mean() / downside_std * np.sqrt(252))

    def _max_drawdown(self, equity: pd.Series):
        roll_max = equity.cummax()
        drawdown = equity / roll_max - 1
        idx = drawdown.idxmin()
        if idx is None:
            return 0.0, None, None
        dd_val = float(drawdown.loc[idx])
        peak_idx = equity[:idx].idxmax() if len(equity[:idx]) > 0 else idx
        return dd_val, peak_idx, idx

    # ─────────────────────────────────────────────────────────────────
    # Output
    # ─────────────────────────────────────────────────────────────────

    def _print_summary(self, metrics: dict) -> None:
        rows = [
            ["Period", f"{metrics['period_start']} → {metrics['period_end']}"],
            ["Initial Capital", f"${metrics['initial_capital']:,.0f}"],
            ["Final Value", f"${metrics['final_value']:,.0f}"],
            ["Total Return", f"{metrics['total_return_pct']:.2f}%"],
            ["CAGR", f"{metrics['cagr_pct']:.2f}%"],
            ["Sharpe", f"{metrics['sharpe']:.3f}"],
            ["Sortino", f"{metrics['sortino']:.3f}"],
            ["Calmar", f"{metrics['calmar']:.3f}"],
            ["Max Drawdown", f"{metrics['max_drawdown_pct']:.2f}%"],
            ["Total Trades", metrics["total_trades"]],
            ["Win Rate", f"{metrics['win_rate_pct']:.1f}%"],
            ["Profit Factor", f"{metrics['profit_factor']:.2f}"],
        ]
        if "bm_cagr" in metrics:
            rows.append(["SPY CAGR (benchmark)", f"{metrics['bm_cagr']:.2f}%"])
            rows.append(["Excess Return (vs SPY)", f"{metrics['excess_return']:.2f}%"])

        print("\n" + "=" * 55)
        print("  BACKTEST RESULTS — Quantamental v2.2")
        print("=" * 55)
        print(tabulate(rows, tablefmt="simple"))
        print("=" * 55 + "\n")

    def _save_json(self, metrics, trades, portfolio_history, regime_history):
        out = {
            "generated_at": datetime.now().isoformat(),
            "metrics": metrics,
            "trades": trades[-200:],  # last 200 trades
            "regime_summary": self._regime_summary(regime_history),
        }
        path = os.path.join(self.results_dir, "backtest_results.json")
        with open(path, "w") as f:
            json.dump(out, f, indent=2, default=str)
        logger.info("Results JSON saved: %s", path)

    def _save_csvs(self, df: pd.DataFrame, trades: List[dict]) -> None:
        df.to_csv(os.path.join(self.results_dir, "portfolio_history.csv"))
        pd.DataFrame(trades).to_csv(os.path.join(self.results_dir, "trades.csv"), index=False)

    def _regime_summary(self, regime_history: List[dict]) -> dict:
        counts: Dict[str, int] = {}
        for rh in regime_history:
            r = rh.get("regime", "UNKNOWN")
            counts[r] = counts.get(r, 0) + 1
        total = sum(counts.values()) or 1
        return {k: {"days": v, "pct": round(v / total * 100, 1)} for k, v in counts.items()}

    # ─────────────────────────────────────────────────────────────────
    # Plots
    # ─────────────────────────────────────────────────────────────────

    def _plot_all(self, df, regime_history, benchmark, metrics):
        fig, axes = plt.subplots(4, 1, figsize=(14, 18))
        fig.suptitle("Quantamental Backtest v2.2", fontsize=14, fontweight="bold")

        pv = df["portfolio_value"]
        regime_df = pd.DataFrame(regime_history).set_index("date") if regime_history else pd.DataFrame()
        if not regime_df.empty:
            regime_df.index = pd.to_datetime(regime_df.index)

        # ── Plot 1: Equity curve ──────────────────────────────────
        ax1 = axes[0]
        norm = pv / pv.iloc[0] * 100
        ax1.plot(norm.index, norm.values, color="#2980b9", linewidth=1.5, label="Strategy")
        if benchmark is not None:
            bm = benchmark.reindex(pv.index, method="ffill").dropna()
            bm_norm = bm / bm.iloc[0] * 100
            ax1.plot(bm_norm.index, bm_norm.values, color="#95a5a6", linewidth=1, label="SPY", linestyle="--")
        self._shade_regimes(ax1, regime_df, pv.index[0], pv.index[-1])
        ax1.set_title(f"Equity Curve  (Total: {metrics['total_return_pct']:.1f}%  CAGR: {metrics['cagr_pct']:.1f}%  Sharpe: {metrics['sharpe']:.2f})")
        ax1.set_ylabel("Indexed (base=100)")
        ax1.legend(loc="upper left", fontsize=8)
        ax1.grid(alpha=0.3)

        # ── Plot 2: Drawdown ──────────────────────────────────────
        ax2 = axes[1]
        roll_max = pv.cummax()
        dd = (pv / roll_max - 1) * 100
        ax2.fill_between(dd.index, dd.values, 0, color="#e74c3c", alpha=0.5)
        ax2.set_title(f"Drawdown  (Max: {metrics['max_drawdown_pct']:.1f}%)")
        ax2.set_ylabel("Drawdown (%)")
        ax2.grid(alpha=0.3)

        # ── Plot 3: Regime timeline ───────────────────────────────
        ax3 = axes[2]
        if not regime_df.empty and "regime" in regime_df.columns:
            regime_map = {"NORMAL": 3, "NEUTRAL": 2, "CRISIS_WARNING": 1, "CRISIS_CONFIRMED": 0}
            regime_numeric = regime_df["regime"].map(regime_map).dropna()
            colors = [REGIME_COLORS.get(r, "#bdc3c7") for r in regime_df["regime"]]
            ax3.bar(regime_df.index, [1] * len(regime_df), color=colors, width=1.5, align="center")
            # Legend patches
            from matplotlib.patches import Patch
            legend_elements = [Patch(facecolor=v, label=k) for k, v in REGIME_COLORS.items()]
            ax3.legend(handles=legend_elements, loc="upper right", fontsize=7, ncol=2)
        ax3.set_title("Market Regime")
        ax3.set_yticks([])
        ax3.grid(alpha=0.3)

        # ── Plot 4: Holdings and cash ─────────────────────────────
        ax4 = axes[3]
        if "n_positions" in df.columns:
            ax4.plot(df.index, df["n_positions"], color="#8e44ad", linewidth=1, label="# Positions")
            ax4.set_ylabel("# Positions", color="#8e44ad")
            ax4b = ax4.twinx()
            cash_pct = (df["cash"] / df["portfolio_value"] * 100).clip(0, 100)
            ax4b.fill_between(df.index, cash_pct.values, alpha=0.3, color="#27ae60", label="Cash %")
            ax4b.set_ylabel("Cash %", color="#27ae60")
        ax4.set_title("Positions & Cash")
        ax4.grid(alpha=0.3)

        for ax in axes:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=7)

        plt.tight_layout()
        path = os.path.join(self.results_dir, "backtest_chart.png")
        plt.savefig(path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        logger.info("Chart saved: %s", path)

    def _shade_regimes(self, ax, regime_df, start, end):
        if regime_df.empty or "regime" not in regime_df.columns:
            return
        prev_regime = None
        prev_date = start
        for date, row in regime_df.iterrows():
            regime = row["regime"]
            if regime != prev_regime and prev_regime is not None:
                color = REGIME_COLORS.get(prev_regime, "#bdc3c7")
                if prev_regime != "NORMAL":
                    ax.axvspan(prev_date, date, alpha=0.08, color=color)
            prev_regime = regime
            prev_date = date
        if prev_regime and prev_regime != "NORMAL":
            ax.axvspan(prev_date, end, alpha=0.08, color=REGIME_COLORS.get(prev_regime, "#bdc3c7"))
