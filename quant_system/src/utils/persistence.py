"""
State persistence — saves/restores regime history, PEAD events, and positions to CSV.
All state lives in the state/ directory relative to the project root.
"""
from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd

_STATE_DIR = Path(__file__).resolve().parents[2] / "state"
_STATE_DIR.mkdir(parents=True, exist_ok=True)

REGIME_HISTORY_PATH = _STATE_DIR / "regime_history.csv"
PEAD_EVENTS_PATH = _STATE_DIR / "pead_events_used.csv"
POSITIONS_PATH = _STATE_DIR / "positions.csv"


# ── Regime history ─────────────────────────────────────────────────────────────

def load_regime_history() -> pd.DataFrame:
    if REGIME_HISTORY_PATH.exists():
        return pd.read_csv(REGIME_HISTORY_PATH, parse_dates=["signal_date"])
    cols = [
        "signal_date", "regime",
        "fast_risk_score", "slow_risk_score", "risk_on_score", "overshoot_score",
        "fast_risk_lt_60_streak", "risk_off_confirmed_streak", "risk_off_release_streak",
    ]
    return pd.DataFrame(columns=cols)


def append_regime_history(row: dict) -> None:
    df = load_regime_history()
    new = pd.DataFrame([row])
    df = pd.concat([df, new], ignore_index=True)
    df.to_csv(REGIME_HISTORY_PATH, index=False)


def get_last_regime_state(history: pd.DataFrame) -> dict:
    """Return last streaks + regime from saved history, or defaults."""
    if history.empty:
        return {
            "regime": "NORMAL_RISK_ON",
            "fast_risk_lt_60_streak": 0,
            "risk_off_confirmed_streak": 0,
            "risk_off_release_streak": 0,
        }
    last = history.iloc[-1]
    return {
        "regime": last["regime"],
        "fast_risk_lt_60_streak": int(last.get("fast_risk_lt_60_streak", 0)),
        "risk_off_confirmed_streak": int(last.get("risk_off_confirmed_streak", 0)),
        "risk_off_release_streak": int(last.get("risk_off_release_streak", 0)),
    }


# ── PEAD events ────────────────────────────────────────────────────────────────

def load_pead_events() -> pd.DataFrame:
    if PEAD_EVENTS_PATH.exists():
        return pd.read_csv(PEAD_EVENTS_PATH, parse_dates=["used_at"])
    return pd.DataFrame(columns=["event_id", "used_at", "result"])


def is_pead_event_used(event_id: str) -> bool:
    df = load_pead_events()
    return event_id in df["event_id"].values


def record_pead_event(event_id: str, result: str = "entered") -> None:
    df = load_pead_events()
    if event_id in df["event_id"].values:
        return
    new = pd.DataFrame([{"event_id": event_id, "used_at": datetime.utcnow(), "result": result}])
    df = pd.concat([df, new], ignore_index=True)
    df.to_csv(PEAD_EVENTS_PATH, index=False)


# ── Positions (Phase 1 = paper) ────────────────────────────────────────────────

def load_positions() -> pd.DataFrame:
    if POSITIONS_PATH.exists():
        return pd.read_csv(POSITIONS_PATH, parse_dates=["entry_date"])
    cols = [
        "symbol", "basket", "entry_date", "entry_price", "stop_price",
        "qty", "cost_basis", "highest_close", "r_multiple",
        "pyramid_count", "earnings_event_id",
    ]
    return pd.DataFrame(columns=cols)


def save_positions(df: pd.DataFrame) -> None:
    df.to_csv(POSITIONS_PATH, index=False)
