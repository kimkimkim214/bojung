"""
4시나리오 5분봉 백테 — paper_trader_stock.py 룰 재현
====================================================

S1: SOXL+TQQQ × BULL_FILTER_SMA=120  (검증룰 비교 기준)
S2: SOXL+TQQQ × BULL_FILTER_SMA=40
S3: 8종 풀     × BULL_FILTER_SMA=120
S4: 8종 풀     × BULL_FILTER_SMA=40

검증 통과 기준 (S1):
  - 누적 +59% 근처, Calmar 2.90 근처, MDD -20% 근처
  - 거래 수 50~150번 (4.6년)
  S1 통과해야 S2~S4 비교 의미 있음.

실행:
  cd D:\\aaabot\\jacjun
  python stock_4scenarios_final.py
"""

import os
import sys
from collections import defaultdict
from datetime import timedelta

import numpy as np
import pandas as pd

try:
    import pytz
except ImportError:
    print("pytz 필요: pip install pytz")
    sys.exit(1)


# ──────────────────────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────────────────────
DATA_DIR = r"D:\aaabot\asset_data"
DATE_FROM = "2021-05-17"
DATE_TO   = "2025-12-31"

# paper_trader_stock 파라미터 (★ 변경 금지)
INITIAL_CAPITAL    = 10_000.0
INITIAL_BUY_RATIO  = 0.70      # 초기 진입 시 자산 버킷의 70%
BUY_RATIO_OF_CASH  = 0.50      # 추매/재진입 시 asset_cash의 50%
ADD_THRESHOLD_PCT  = -5.0      # 평단 -5%면 추매
TREND_SMA          = 20        # 매도 판정 SMA (★ 고정)
MOMENTUM_LOOKBACK  = 20        # 모멘텀 룩백
WEIGHT_MIN         = 0.20
WEIGHT_MAX         = 0.70
FEE_RT             = 0.001     # 0.1%
QUICK_REENTRY_MIN  = 60        # 분
SELL_HOUR, SELL_MIN  = 15, 0   # 매도/추매 시점 (Eastern)
INIT_HOUR, INIT_MIN  = 9, 35   # 초기 진입 / 월요일 가중치 재계산

ET = pytz.timezone("US/Eastern")

POOL_2 = ["SOXL", "TQQQ"]
POOL_8 = ["SOXL", "TQQQ", "SPXL", "UPRO", "TECL", "FAS", "TNA", "LABU"]

SCENARIOS = [
    {"name": "S1: SOXL+TQQQ × SMA120", "tickers": POOL_2, "bull_sma": 120},
    {"name": "S2: SOXL+TQQQ × SMA40",  "tickers": POOL_2, "bull_sma": 40},
    {"name": "S3: 풀8종 × SMA120",     "tickers": POOL_8, "bull_sma": 120},
    {"name": "S4: 풀8종 × SMA40",      "tickers": POOL_8, "bull_sma": 40},
]


# ──────────────────────────────────────────────────────────────
# 데이터 로딩
# ──────────────────────────────────────────────────────────────
def load_5min(ticker):
    """5분봉 CSV 로딩 → 정규장 ET 필터."""
    path = os.path.join(DATA_DIR, f"{ticker}_5min_{DATE_FROM}_{DATE_TO}.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=False, errors="coerce")
    df = df.dropna(subset=["timestamp"]).copy()

    # tz 처리: naive면 UTC로 가정 → Eastern 변환 (DST 자동)
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")
    df["timestamp"] = df["timestamp"].dt.tz_convert(ET)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]

    # 정규장 09:30 ~ 16:00 ET
    hm = df.index.hour * 60 + df.index.minute
    df = df[(hm >= 9 * 60 + 30) & (hm < 16 * 60)]

    df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    return df


def build_daily(df5, bull_sma):
    """정규장 일봉 → SMA. sma_prev = 직전 일봉 값 (룩어헤드 방지)."""
    g = df5.groupby(df5.index.normalize())
    daily = pd.DataFrame({
        "Open":  g["Open"].first(),
        "Close": g["Close"].last(),
    })
    daily["SMA_TREND"]      = daily["Close"].rolling(TREND_SMA).mean()
    daily["SMA_BULL"]       = daily["Close"].rolling(bull_sma).mean()
    daily["SMA_TREND_PREV"] = daily["SMA_TREND"].shift(1)
    daily["SMA_BULL_PREV"]  = daily["SMA_BULL"].shift(1)
    daily["SMA_TREND_PP"]   = daily["SMA_TREND"].shift(2)  # 추세 방향용
    return daily


# ──────────────────────────────────────────────────────────────
# 룰 함수 (paper_trader_stock 재현)
# ──────────────────────────────────────────────────────────────
def is_bull_market(price, sma_bull_prev):
    """약세장 필터: 가격 > 직전 일봉 SMA_BULL."""
    if sma_bull_prev is None or np.isnan(sma_bull_prev):
        return False
    return price > sma_bull_prev


def is_trend_strong(price, sma_trend_prev, sma_trend_pp):
    """추세 강함: 가격 > SMA20(prev) AND SMA20 상승."""
    if any(v is None or np.isnan(v) for v in (sma_trend_prev, sma_trend_pp)):
        return False
    return (price > sma_trend_prev) and (sma_trend_prev > sma_trend_pp)


def should_sell(price, today_open, sma_trend_prev, sma_trend_pp):
    """매도: 가격 > 당일 시가 AND 추세 약함."""
    if today_open is None or np.isnan(today_open):
        return False
    if price <= today_open:
        return False
    return not is_trend_strong(price, sma_trend_prev, sma_trend_pp)


def compute_weights(tickers, daily_map, ref_date):
    """
    모멘텀 기반 가중치.
    - 종목별 수익률 = (close_t / close_{t-LOOKBACK}) - 1
    - 양수만 살리고 sum=1로 정규화
    - [MIN, MAX] 클램프 → 다시 정규화
    - 모든 모멘텀이 0 이하면 동등 가중
    """
    raw = {}
    for t in tickers:
        d = daily_map[t]
        # ref_date 이전의 가장 최근 일봉
        idx = d.index.searchsorted(pd.Timestamp(ref_date), side="right") - 1
        if idx < MOMENTUM_LOOKBACK:
            raw[t] = 0.0
            continue
        c_now  = d["Close"].iloc[idx]
        c_back = d["Close"].iloc[idx - MOMENTUM_LOOKBACK]
        raw[t] = (c_now / c_back) - 1.0 if c_back > 0 else 0.0

    pos = {t: max(0.0, v) for t, v in raw.items()}
    s = sum(pos.values())
    if s <= 0:
        w = {t: 1.0 / len(tickers) for t in tickers}
    else:
        w = {t: v / s for t, v in pos.items()}

    # 클램프 + 재정규화
    w = {t: min(WEIGHT_MAX, max(WEIGHT_MIN, v)) for t, v in w.items()}
    s = sum(w.values())
    if s > 0:
        w = {t: v / s for t, v in w.items()}
    return w


# ──────────────────────────────────────────────────────────────
# 백테 엔진
# ──────────────────────────────────────────────────────────────
class AssetState:
    __slots__ = ("shares", "avg_cost", "asset_cash",
                 "last_sell_time", "last_sell_price",
                 "initial_bucket", "last_close")

    def __init__(self, bucket):
        self.shares = 0.0
        self.avg_cost = 0.0
        self.asset_cash = bucket          # 이 자산에 할당된 현금
        self.initial_bucket = bucket
        self.last_sell_time = None
        self.last_sell_price = None
        self.last_close = None


def run_backtest(tickers, bull_sma, label):
    print(f"\n[{label}] 데이터 로딩...")
    data_5m = {}
    daily   = {}
    for t in tickers:
        d5 = load_5min(t)
        data_5m[t] = d5
        daily[t]   = build_daily(d5, bull_sma)
        print(f"  {t}: 5min {len(d5):>7,}봉 / 일봉 {len(daily[t]):>5}")

    # 초기 가중치 — 첫 거래일 기준
    all_first = min(d.index.min() for d in data_5m.values())
    init_weights = compute_weights(tickers, daily, all_first.date())
    print(f"  초기 가중치: {{ " + ", ".join(f'{t}:{w:.2f}' for t, w in init_weights.items()) + " }}")

    # 각 자산: bucket = 초기 자본 × 가중치
    states = {t: AssetState(INITIAL_CAPITAL * init_weights[t]) for t in tickers}

    # 이벤트 정렬 (종목별 독립 timestamp)
    events = []
    for t in tickers:
        for ts, row in data_5m[t].iterrows():
            events.append((ts, t, row))
    events.sort(key=lambda x: (x[0], x[1]))
    print(f"  총 이벤트: {len(events):,}")

    trades = []           # (date, ticker, action, price, shares, pnl_pct)
    daily_equity = {}     # date → equity
    today_opens = defaultdict(dict)   # date → {ticker: open}
    last_rebalance_date = None
    last_loop_date = None

    for ts, t, row in events:
        date = ts.date()
        st = states[t]
        st.last_close = row["Close"]

        # 오늘 시가 기록 (장 첫 봉의 Open)
        if t not in today_opens[date]:
            today_opens[date][t] = row["Open"]

        d_info = _sma_lookup(daily[t], date)
        if d_info is None:
            continue

        price = row["Close"]
        sma_trend_prev = d_info["sma_trend_prev"]
        sma_trend_pp   = d_info["sma_trend_pp"]
        sma_bull_prev  = d_info["sma_bull_prev"]
        today_open     = today_opens[date].get(t)

        h, m, wd = ts.hour, ts.minute, ts.weekday()

        # 09:35 — 초기 진입 + (월요일이면) 가중치 재계산
        if h == INIT_HOUR and m == INIT_MIN:
            if wd == 0 and last_rebalance_date != date:
                _rebalance_buckets(states, tickers, daily, date)
                last_rebalance_date = date

            if st.shares <= 0 and is_bull_market(price, sma_bull_prev) \
                              and is_trend_strong(price, sma_trend_prev, sma_trend_pp):
                _buy(st, price, ts, t, trades,
                     cash_use=st.asset_cash * INITIAL_BUY_RATIO, action="INIT")

        # 15:00 — 매도/추매 (30분 봉)
        elif h == SELL_HOUR and m == SELL_MIN:
            if st.shares > 0:
                if should_sell(price, today_open, sma_trend_prev, sma_trend_pp):
                    _sell(st, price, ts, t, trades)
                else:
                    drawdown_pct = (price / st.avg_cost - 1.0) * 100.0
                    if drawdown_pct <= ADD_THRESHOLD_PCT and st.asset_cash > 0:
                        _buy(st, price, ts, t, trades,
                             cash_use=st.asset_cash * BUY_RATIO_OF_CASH, action="ADD")

        # 그 외 5분 — 빠른 재진입
        else:
            if st.shares <= 0 and st.last_sell_time is not None:
                if (ts - st.last_sell_time) <= timedelta(minutes=QUICK_REENTRY_MIN):
                    if price > st.last_sell_price \
                       and is_trend_strong(price, sma_trend_prev, sma_trend_pp) \
                       and is_bull_market(price, sma_bull_prev) \
                       and st.asset_cash > 0:
                        _buy(st, price, ts, t, trades,
                             cash_use=st.asset_cash * BUY_RATIO_OF_CASH, action="REENTRY")

        # 일일 자산 평가 (날짜 바뀔 때 직전 날짜 기록)
        if last_loop_date is not None and date != last_loop_date:
            daily_equity[last_loop_date] = _eval_equity(states)
        last_loop_date = date

    if last_loop_date is not None:
        daily_equity[last_loop_date] = _eval_equity(states)

    return _summarize(label, daily_equity, trades, tickers)


def _sma_lookup(daily_df, date):
    """date 직전 일봉의 SMA 정보 반환 (룩어헤드 방지)."""
    target = pd.Timestamp(date).normalize()
    if daily_df.index.tz is not None:
        target = target.tz_localize(daily_df.index.tz)
    idx = daily_df.index.searchsorted(target, side="left") - 1
    if idx < 0:
        return None
    row = daily_df.iloc[idx]
    if pd.isna(row["SMA_TREND_PREV"]) or pd.isna(row["SMA_BULL_PREV"]):
        return None
    return {
        "sma_trend":      row["SMA_TREND"],
        "sma_trend_prev": row["SMA_TREND"],     # 직전 일봉의 SMA
        "sma_trend_pp":   row["SMA_TREND_PREV"],
        "sma_bull":       row["SMA_BULL"],
        "sma_bull_prev":  row["SMA_BULL"],
    }


def _buy(st, price, ts, ticker, trades, cash_use, action):
    if cash_use <= 0 or price <= 0:
        return
    cash_after_fee = cash_use * (1 - FEE_RT)
    qty = cash_after_fee / price
    if qty <= 0:
        return
    new_shares = st.shares + qty
    new_cost = (st.avg_cost * st.shares + price * qty) / new_shares if new_shares > 0 else price
    st.shares = new_shares
    st.avg_cost = new_cost
    st.asset_cash -= cash_use
    trades.append((ts, ticker, action, price, qty, None))


def _sell(st, price, ts, ticker, trades):
    if st.shares <= 0:
        return
    proceeds = st.shares * price * (1 - FEE_RT)
    pnl_pct = (price / st.avg_cost - 1.0) * 100.0 if st.avg_cost > 0 else 0.0
    st.asset_cash += proceeds
    trades.append((ts, ticker, "SELL", price, st.shares, pnl_pct))
    st.shares = 0.0
    st.avg_cost = 0.0
    st.last_sell_time = ts
    st.last_sell_price = price


def _rebalance_buckets(states, tickers, daily_map, date):
    """월요일 09:35 가중치 재계산. shares는 그대로 두고 asset_cash만 재분배."""
    total_cash = sum(s.asset_cash for s in states.values())
    if total_cash <= 0:
        return
    w = compute_weights(tickers, daily_map, date)
    for t in tickers:
        states[t].asset_cash = total_cash * w[t]


def _eval_equity(states):
    total = 0.0
    for s in states.values():
        px = s.last_close if s.last_close is not None else s.avg_cost
        total += s.asset_cash + s.shares * (px if px else 0)
    return total


def _summarize(label, daily_equity, trades, tickers):
    if not daily_equity:
        return {"label": label, "error": "no data"}

    eq = pd.Series(daily_equity).sort_index()
    eq.index = pd.to_datetime(eq.index)
    eq = eq[eq > 0]

    final = eq.iloc[-1]
    cum_ret = final / INITIAL_CAPITAL - 1.0

    days = (eq.index[-1] - eq.index[0]).days
    years = max(days / 365.25, 1e-9)
    cagr = (final / INITIAL_CAPITAL) ** (1 / years) - 1

    running_max = eq.cummax()
    dd = eq / running_max - 1.0
    mdd = dd.min()

    calmar = (cagr / abs(mdd)) if mdd < 0 else float("inf")

    # 거래 통계
    sell_trades = [t for t in trades if t[2] == "SELL"]
    wins = [t for t in sell_trades if (t[5] or 0) > 0]
    win_rate = len(wins) / len(sell_trades) if sell_trades else 0.0

    n_trades = len(trades)
    n_sells = len(sell_trades)

    print(f"\n{label}")
    print(f"  기간:    {eq.index[0].date()} ~ {eq.index[-1].date()}  ({years:.2f}년)")
    print(f"  누적:    {cum_ret*100:+.2f}%")
    print(f"  CAGR:    {cagr*100:+.2f}%")
    print(f"  MDD:     {mdd*100:+.2f}%")
    print(f"  Calmar:  {calmar:.2f}")
    print(f"  거래:    {n_trades} (매도 {n_sells})")
    print(f"  승률:    {win_rate*100:.1f}%")

    return {
        "label": label,
        "cum": cum_ret,
        "cagr": cagr,
        "mdd": mdd,
        "calmar": calmar,
        "trades": n_trades,
        "sells": n_sells,
        "win_rate": win_rate,
        "years": years,
    }


# ──────────────────────────────────────────────────────────────
# 보고서
# ──────────────────────────────────────────────────────────────
def print_report(results):
    print("\n" + "=" * 68)
    print("4시나리오 5분봉 백테 결과")
    print("=" * 68)
    print(f"{'시나리오':<28}{'누적':>10}{'CAGR':>9}{'MDD':>9}{'Calmar':>9}{'거래':>7}{'승률':>7}")
    print("-" * 68)
    for r in results:
        if "error" in r:
            print(f"{r['label']:<28}  ERROR: {r['error']}")
            continue
        print(f"{r['label']:<28}"
              f"{r['cum']*100:>9.1f}%"
              f"{r['cagr']*100:>8.1f}%"
              f"{r['mdd']*100:>8.1f}%"
              f"{r['calmar']:>9.2f}"
              f"{r['trades']:>7}"
              f"{r['win_rate']*100:>6.1f}%")

    # 검증
    s1 = next((r for r in results if r["label"].startswith("S1") and "error" not in r), None)
    if s1:
        print("\n[시뮬 신뢰도]")
        print(f"  S1 백테 기록(+59%/Calmar 2.90, MDD-20%) 대비:")
        print(f"    누적:    {s1['cum']*100:+.1f}%  (기준 +59%)")
        print(f"    Calmar:  {s1['calmar']:.2f}    (기준 2.90)")
        print(f"    MDD:     {s1['mdd']*100:+.1f}%  (기준 -20%)")
        print(f"    거래:    {s1['trades']}        (기준 50~150)")
        ok = (0.20 < s1["cum"] < 2.0) and (s1["calmar"] >= 0.5) and (s1["trades"] >= 10)
        print(f"  → {'신뢰 가능 ✓' if ok else '결함 의심 ✗  S1 통과 못함 — 디버깅 우선'}")

    # 변경 요소 분리
    by = {r["label"][:2]: r for r in results if "error" not in r}
    print("\n[변경 요소 분리]")
    if "S2" in by and "S1" in by:
        print(f"  S2 vs S1 (SMA40 효과만):  Calmar {by['S2']['calmar']:.2f} vs {by['S1']['calmar']:.2f}, "
              f"MDD {by['S2']['mdd']*100:+.1f}% vs {by['S1']['mdd']*100:+.1f}%")
    if "S3" in by and "S1" in by:
        print(f"  S3 vs S1 (풀 확장만):     Calmar {by['S3']['calmar']:.2f} vs {by['S1']['calmar']:.2f}, "
              f"MDD {by['S3']['mdd']*100:+.1f}% vs {by['S1']['mdd']*100:+.1f}%")
    if "S4" in by and "S1" in by:
        print(f"  S4 vs S1 (둘 다):         Calmar {by['S4']['calmar']:.2f} vs {by['S1']['calmar']:.2f}, "
              f"MDD {by['S4']['mdd']*100:+.1f}% vs {by['S1']['mdd']*100:+.1f}%")

    # 종합 판정 (Calmar 기준)
    print("\n[종합 판정]")
    s1_calmar = by.get("S1", {}).get("calmar", 0)
    winners = [r for k, r in by.items() if k != "S1" and r["calmar"] > s1_calmar]
    if winners:
        print(f"  ✓ 검증룰 초과 시나리오 (Calmar {s1_calmar:.2f} 초과):")
        for w in sorted(winners, key=lambda r: -r["calmar"]):
            print(f"      {w['label']}  Calmar {w['calmar']:.2f}")
    else:
        print(f"  ✗ 검증룰 S1 (Calmar {s1_calmar:.2f})이 최강 — 변형 폐기 권장")


# ──────────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────────
def main():
    results = []
    for sc in SCENARIOS:
        try:
            r = run_backtest(sc["tickers"], sc["bull_sma"], sc["name"])
        except Exception as e:
            print(f"\n[{sc['name']}] ERROR: {e}")
            r = {"label": sc["name"], "error": str(e)}
        results.append(r)
    print_report(results)


if __name__ == "__main__":
    main()
