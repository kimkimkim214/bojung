"""
Trading calendar utilities (NYSE business days).
Uses pandas_market_calendars when available, falls back to USFederalHolidayCalendar.
"""
from __future__ import annotations

import pandas as pd
from datetime import date, datetime
from typing import Union

DateLike = Union[str, date, datetime, pd.Timestamp]


def _get_nyse_calendar():
    try:
        import pandas_market_calendars as mcal
        return mcal.get_calendar("NYSE")
    except ImportError:
        return None


_NYSE_CAL = _get_nyse_calendar()


def _us_bday_offset():
    from pandas.tseries.offsets import CustomBusinessDay
    from pandas.tseries.holiday import USFederalHolidayCalendar
    return CustomBusinessDay(calendar=USFederalHolidayCalendar())


def _to_ts(d: DateLike) -> pd.Timestamp:
    return pd.Timestamp(d)


def get_trading_days(start: DateLike, end: DateLike) -> pd.DatetimeIndex:
    """Return all NYSE trading days in [start, end] inclusive."""
    s, e = _to_ts(start), _to_ts(end)
    if _NYSE_CAL is not None:
        schedule = _NYSE_CAL.schedule(start_date=s, end_date=e)
        return schedule.index.normalize()
    # fallback
    return pd.date_range(s, e, freq=_us_bday_offset())


def next_trading_day(d: DateLike) -> pd.Timestamp:
    """Return the next NYSE trading day after d."""
    ts = _to_ts(d)
    candidate = ts + pd.Timedelta(days=1)
    # advance until we land on a trading day
    days = get_trading_days(candidate, candidate + pd.Timedelta(days=10))
    return days[0]


def is_trading_day(d: DateLike) -> bool:
    ts = _to_ts(d)
    days = get_trading_days(ts, ts)
    return len(days) > 0 and days[0].date() == ts.date()


def trading_days_between(start: DateLike, end: DateLike) -> int:
    """Number of trading days in (start, end] (exclusive start, inclusive end)."""
    days = get_trading_days(start, end)
    # exclude start if it matches
    s = _to_ts(start).date()
    return sum(1 for d in days if d.date() > s)


def nth_prev_trading_day(d: DateLike, n: int) -> pd.Timestamp:
    """Return the trading day n sessions before d."""
    ts = _to_ts(d)
    days = get_trading_days(ts - pd.Timedelta(days=n * 2 + 20), ts)
    days = [x for x in days if x.date() < ts.date()]
    if len(days) < n:
        raise ValueError(f"Not enough trading history before {d} for n={n}")
    return days[-n]


def trading_days_lookback(end: DateLike, n: int) -> pd.DatetimeIndex:
    """Return a DatetimeIndex of the last n trading days up to and including end."""
    ts = _to_ts(end)
    days = get_trading_days(ts - pd.Timedelta(days=n * 2 + 20), ts)
    days = [x for x in days if x.date() <= ts.date()]
    return pd.DatetimeIndex(days[-n:])
