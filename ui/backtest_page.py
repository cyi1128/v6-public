# -*- coding: utf-8 -*-
"""
分时做T回测页面 (JoinQuant 风格)
================================
左侧：策略代码编辑器（深色 + 语法高亮 + 行号）
右侧：回测参数 + 指标卡片 + 净值曲线 + 交易明细 + 持仓表

回测引擎：纯 Python + NumPy 自研
- 数据源：data/cache/kline_cache.duckdb (日线, read_only)
- 无分钟数据时，用每日 OHLC 近似模拟做 T
- 严格避免未来函数：所有信号均使用 t-1 收盘后的指标，在 t 日盘中触发
- 真实成本：佣金万2.5最低5元 / 印花税千1(卖出) / 过户费万0.1 / 滑点0.2%
"""
import os
import sys
import ast
import json
import copy
import traceback
from datetime import datetime

import numpy as np
import pandas as pd
import duckdb

import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
matplotlib.rcParams['axes.unicode_minus'] = False
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit,
    QSplitter, QFrame, QDateEdit, QLineEdit, QComboBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QTextEdit, QSizePolicy, QMessageBox,
    QToolBar, QGridLayout, QAbstractItemView,
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QRect, QDate, QSize,
)
from PyQt6.QtGui import (
    QColor, QFont, QPalette, QTextCharFormat, QSyntaxHighlighter,
    QTextDocument, QTextBlockUserData, QIcon, QPainter,
)

# ============================================================
# 路径
# ============================================================
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUCKDB_PATH = os.path.join(_ROOT, 'data', 'cache', 'kline_cache.duckdb')
WATCHLIST_PATH = os.path.join(_ROOT, 'data', 'watchlist.json')
STRATEGY_DIR = os.path.join(_ROOT, 'data', 'backtest_strategies')
os.makedirs(STRATEGY_DIR, exist_ok=True)

# 分钟级数据（腾讯5分钟线，独立DuckDB: data/cache/minute_kline.duckdb）
# 导入或初始化失败均降级为 None，回测自动回退到日线近似，绝不影响主程序启动
try:
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    from services import minute_kline as _mk
except Exception as _e:  # noqa
    print(f'[backtest_page] minute_kline 模块导入失败，VWAP 将使用日线近似: {_e}')
    _mk = None

BLUE = '#2f6bff'
BG = '#f0f4f9'
CARD = '#ffffff'
BORDER = '#e0e0e0'
RED = '#e53935'
GREEN = '#43a047'
TEXT = '#333333'
TEXT2 = '#888888'

# ============================================================
# 预置做T策略模板
# ============================================================
DEFAULT_STRATEGY = '''# ============================================================
# 分时做T策略模板 (ATR + VWAP + MACD 融合)
# 底仓 50% + 现金 50%，高抛低吸
# ============================================================
def initialize(context):
    # ---- 策略参数 ----
    context.atr_period   = 14        # ATR 周期
    context.vwap_window  = 20        # VWAP 滚动窗口(日线近似)
    context.macd_fast    = 8         # MACD 快线
    context.macd_slow    = 21        # MACD 慢线
    context.macd_signal  = 5         # MACD 信号线
    context.atr_mult     = 0.3       # 偏离 VWAP 的 ATR 倍数
    context.base_ratio   = 0.5       # 底仓仓位
    context.t_ratio      = 0.20      # 每次做T仓位(占持仓比例)

    # ---- 交易成本 ----
    set_order_cost(open_commission=0.00025, close_commission=0.00025,
                   min_commission=5.0, close_tax=0.001, transfer_fee=0.00001)
    set_slippage(0.002)
    set_benchmark('equal_weight')     # 等权基准

# ---- 卖出(高抛) ----
#  现价 >= VWAP + 0.3*ATR  且 MACD 死叉/顶背离
# ---- 买入(低吸) ----
#  现价 <= VWAP - 0.3*ATR  且 MACD 金叉/底背离
# ---- 风控 ----
#  防飞刀: 现价 < VWAP*0.985 暂停买入
#  防T飞 : 涨幅>=8% 锁定卖出
#  时间过滤: 09:30-09:45 暂停交易
'''


# ============================================================
# 指标计算 (纯函数)
# ============================================================
def _ema(arr, period):
    arr = np.asarray(arr, dtype=float)
    if len(arr) == 0:
        return arr
    alpha = 2.0 / (period + 1.0)
    out = np.empty_like(arr)
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = alpha * arr[i] + (1 - alpha) * out[i - 1]
    return out


def calc_atr(high, low, close, period=14):
    n = len(close)
    tr = np.full(n, np.nan)
    for i in range(n):
        if i == 0:
            tr[i] = high[i] - low[i]
        else:
            tr[i] = max(high[i] - low[i],
                        abs(high[i] - close[i - 1]),
                        abs(low[i] - close[i - 1]))
    atr = np.full(n, np.nan)
    if n < period:
        return atr
    # Wilder 平滑
    atr[period - 1] = np.nanmean(tr[:period])
    for i in range(period, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def calc_rolling_vwap(high, low, close, volume, window=20):
    """滚动 VWAP：N 日典型价*成交量 加权平均"""
    typical = (high + low + close) / 3.0
    pv = typical * volume
    s_pv = pd.Series(pv).rolling(window, min_periods=1).sum().values
    s_v = pd.Series(volume).rolling(window, min_periods=1).sum().values
    vwap = np.where(s_v > 0, s_pv / np.where(s_v <= 0, 1, s_v), np.nan)
    return vwap


def calc_macd(close, fast=8, slow=21, signal=5):
    close = np.asarray(close, dtype=float)
    dif = _ema(close, fast) - _ema(close, slow)
    dea = _ema(dif, signal)
    hist = (dif - dea) * 2.0
    return dif, dea, hist


def detect_divergence(closes, difs, lookback=20):
    n = min(len(closes), lookback)
    if n < 10:
        return None
    c = closes[-n:]
    d = difs[-n:]

    def _is_low(idx):
        return 0 < idx < n - 1 and c[idx] < c[idx - 1] and c[idx] < c[idx + 1]

    def _is_high(idx):
        return 0 < idx < n - 1 and c[idx] > c[idx - 1] and c[idx] > c[idx + 1]

    lows = [i for i in range(1, n - 1) if _is_low(i)]
    highs = [i for i in range(1, n - 1) if _is_high(i)]
    if len(lows) >= 2:
        i1, i2 = lows[-2], lows[-1]
        if c[i2] < c[i1] and d[i2] > d[i1] and (n - 1 - i2) <= 3:
            return 'bottom'
    if len(highs) >= 2:
        i1, i2 = highs[-2], highs[-1]
        if c[i2] > c[i1] and d[i2] < d[i1] and (n - 1 - i2) <= 3:
            return 'top'
    return None


# ============================================================
# 数据加载
# ============================================================
def load_watchlist():
    try:
        with open(WATCHLIST_PATH, encoding='utf-8') as f:
            data = json.load(f)
        return [(d.get('code', ''), d.get('name', '')) for d in data]
    except Exception:
        return [('002902', '铭普光磁')]


def load_stock_df(code, start_date, end_date):
    """从 duckdb 读日线 (read_only)，返回按日期升序的 DataFrame"""
    con = duckdb.connect(DUCKDB_PATH, read_only=False)
    try:
        df = con.execute(
            "SELECT date, open, high, low, close, volume "
            "FROM kline_cache WHERE code=? AND date>=? AND date<=? "
            "ORDER BY date",
            [code, start_date, end_date],
        ).df()
    finally:
        con.close()
    if df.empty:
        return df
    df['date'] = df['date'].astype(str)
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    return df.reset_index(drop=True)


# ============================================================
# 回测引擎
# ============================================================
COMMISSION = 0.00025
MIN_COMMISSION = 5.0
STAMP_TAX = 0.001       # 卖出
TRANSFER_FEE = 0.00001
SLIPPAGE = 0.002


def _calc_fee(amount, is_sell):
    comm = max(amount * COMMISSION, MIN_COMMISSION)
    stamp = amount * STAMP_TAX if is_sell else 0.0
    transfer = amount * TRANSFER_FEE
    return comm + stamp + transfer


def run_backtest(start_date, end_date, init_capital, codes_names,
                 atr_mult=0.3, atr_period=14, vwap_window=20,
                 macd_fast=8, macd_slow=21, macd_signal=5,
                 progress_cb=None):
    """
    纯 Python 向量化 + 事件混合回测。
    返回 dict: nav_df, trades, positions, metrics
    """
    codes = [c for c, _n in codes_names]
    names = {c: n for c, n in codes_names}
    n_stock = len(codes)
    if n_stock == 0:
        raise ValueError('股票池为空')

    # 1. 加载所有股票数据，对齐交易日
    data = {}
    all_dates = None
    for code in codes:
        df = load_stock_df(code, start_date, end_date)
        if df.empty:
            continue
        data[code] = df
        dset = set(df['date'].tolist())
        all_dates = dset if all_dates is None else (all_dates & dset)
    if not data:
        raise ValueError('回测区间内无任何行情数据')
    trade_dates = sorted(all_dates)
    if len(trade_dates) < 30:
        raise ValueError(f'交易日过少({len(trade_dates)}天)，请扩大回测区间')

    # 按交易日对齐构造面板
    panel = {}
    for code, df in data.items():
        m = {r['date']: r for _, r in df.iterrows()}
        panel[code] = {d: m[d] for d in trade_dates if d in m}

    # 2. 预计算指标（每只股票）
    ind = {}
    for code in panel:
        rows = panel[code]
        dates = [d for d in trade_dates if d in rows]
        o = np.array([rows[d]['open'] for d in dates])
        h = np.array([rows[d]['high'] for d in dates])
        l = np.array([rows[d]['low'] for d in dates])
        c = np.array([rows[d]['close'] for d in dates])
        v = np.array([rows[d]['volume'] for d in dates])
        atr = calc_atr(h, l, c, atr_period)
        vwap = calc_rolling_vwap(h, l, c, v, vwap_window)  # 日线20日滚动近似（兜底）
        dif, dea, hist = calc_macd(c, macd_fast, macd_slow, macd_signal)

        # —— 用真实分钟级数据重算【当日VWAP】——
        # 每个交易日开盘从0重新累加：VWAP = Σ(典型价×当日5分钟成交量)/Σ(当日5分钟成交量)
        # 有分钟数据的交易日用分钟VWAP覆盖日线近似；无分钟数据的交易日保持日线兜底
        minute_days = set()   # 本股票在本次回测区间内实际使用了分钟VWAP的交易日
        if _mk is not None:
            try:
                day_vwap = _mk.load_day_vwap(code, start_date, end_date)
                n_overwrite = 0
                for k, dstr in enumerate(dates):
                    vv = day_vwap.get(dstr)
                    if vv is not None and np.isfinite(vv) and vv > 0:
                        vwap[k] = float(vv)
                        n_overwrite += 1
                        minute_days.add(dstr)
                if n_overwrite:
                    print(f'[backtest] {code}: {n_overwrite} 个交易日使用分钟级当日VWAP')
            except Exception as _e:
                print(f'[backtest] {code} 分钟VWAP加载失败，回退日线: {_e}')

        ind[code] = dict(dates=dates, open=o, high=h, low=l, close=c,
                         atr=atr, vwap=vwap, dif=dif, dea=dea, hist=hist,
                         minute_days=minute_days)

    # 汇总所有股票在本次回测区间内"实际使用了分钟VWAP"的交易日集合
    all_minute_days = set()
    for code, I in ind.items():
        all_minute_days |= I.get('minute_days', set())

    # 3. 组合状态
    cash = float(init_capital)
    # 第一天等权建底仓 50%
    base_capital = init_capital * 0.5
    per_stock_base = base_capital / n_stock
    shares = {c: 0 for c in ind}
    avg_cost = {c: 0.0 for c in ind}
    base_shares = {}

    trades = []       # 成交记录
    nav_records = []   # 每日净值
    bench_nav_records = []
    daily_pnl = []

    first_day = trade_dates[0]
    # 建底仓
    for code, I in ind.items():
        idx = I['dates'].index(first_day) if first_day in I['dates'] else 0
        px = I['open'][idx] * (1 + SLIPPAGE)
        amt = per_stock_base
        sh = int(amt // (px * 100)) * 100  # 整手
        if sh <= 0:
            continue
        cost_amt = sh * px
        fee = _calc_fee(cost_amt, is_sell=False)
        cash -= (cost_amt + fee)
        shares[code] += sh
        avg_cost[code] = (avg_cost[code] * (shares[code] - sh) + px * sh) / shares[code]
        base_shares[code] = sh
        trades.append(dict(date=first_day, time='09:31', code=code,
                           name=names.get(code, code), side='买(底仓)',
                           price=round(px, 3), qty=sh,
                           amount=round(cost_amt, 2), fee=round(fee, 2),
                           pnl=0.0,
                           mode=('minute' if first_day in all_minute_days else 'daily')))

    def mark_to_market(day):
        mv = 0.0
        for code, I in ind.items():
            if day in I['dates']:
                idx = I['dates'].index(day)
                mv += shares[code] * I['close'][idx]
        return cash + mv

    # 基准：等权买入持有（首日建仓，不再做T）
    bench_cash = init_capital
    bench_shares = {}
    bench_per = init_capital / n_stock
    for code, I in ind.items():
        idx = I['dates'].index(first_day) if first_day in I['dates'] else 0
        px = I['open'][idx]
        sh = int(bench_per // (px * 100)) * 100
        bench_shares[code] = sh
        bench_cash -= sh * px
    bench_first_value = init_capital

    def bench_value(day):
        mv = bench_cash
        for code, I in ind.items():
            if day in I['dates']:
                idx = I['dates'].index(day)
                mv += bench_shares[code] * I['close'][idx]
        return mv

    prev_total = mark_to_market(first_day)
    b_prev = bench_value(first_day)
    nav_records.append(dict(date=first_day, nav=1.0, total=prev_total))
    bench_nav_records.append(dict(date=first_day, nav=1.0))
    daily_pnl.append(0.0)

    # 4. 逐日推进（信号用 t-1 指标，t 日触发，杜绝未来函数）
    for di in range(1, len(trade_dates)):
        day = trade_dates[di]
        if progress_cb and di % 20 == 0:
            progress_cb(int(100 * di / len(trade_dates)))

        for code, I in ind.items():
            if day not in I['dates']:
                continue
            i = I['dates'].index(day)
            if i < 25:
                continue  # 指标预热不足
            prev = i - 1
            atr_v = I['atr'][prev]
            vwap_v = I['vwap'][prev]
            if not np.isfinite(atr_v) or not np.isfinite(vwap_v) or atr_v <= 0:
                continue

            # 信号判定（基于 t-1）
            d_prev, d_curr = I['dif'][prev - 1], I['dif'][prev]
            e_prev, e_curr = I['dea'][prev - 1], I['dea'][prev]
            golden = (d_prev <= e_prev) and (d_curr > e_curr)
            dead = (d_prev >= e_prev) and (d_curr < e_curr)
            div = detect_divergence(I['close'][:prev + 1], I['dif'][:prev + 1])

            sell_trigger_price = vwap_v + atr_mult * atr_v
            buy_trigger_price = vwap_v - atr_mult * atr_v

            day_open = I['open'][i]
            day_high = I['high'][i]
            day_low = I['low'][i]
            day_close = I['close'][i]
            day_ret = day_close / I['close'][prev] - 1.0

            # 风控
            knife_guard = (vwap_v * 0.985)  # 跌穿1.5%暂停买
            fly_lock = (day_ret >= 0.08)     # 涨幅>=8% 锁卖

            # --- 卖出(高抛) ---
            sell_sig = dead or (div == 'top')
            if sell_sig and day_high >= sell_trigger_price and not fly_lock:
                sh = shares[code]
                t_sh = int(sh * 0.20 // 100) * 100
                if t_sh >= 100:
                    px = sell_trigger_price * (1 - SLIPPAGE)
                    amt = t_sh * px
                    fee = _calc_fee(amt, is_sell=True)
                    cash += (amt - fee)
                    shares[code] -= t_sh
                    realized = (px - avg_cost[code]) * t_sh - fee
                    trades.append(dict(date=day, time='10:30', code=code,
                                       name=names.get(code, code), side='卖(高抛)',
                                       price=round(px, 3), qty=t_sh,
                                       amount=round(amt, 2), fee=round(fee, 2),
                                       pnl=round(realized, 2),
                                       mode=('minute' if day in all_minute_days else 'daily')))

            # --- 买入(低吸) ---
            buy_sig = golden or (div == 'bottom')
            if buy_sig and day_low <= buy_trigger_price and day_low >= knife_guard:
                # 现金可买
                px = buy_trigger_price * (1 + SLIPPAGE)
                target_val = (base_shares.get(code, 0) * px) * 0.20
                target_val = min(target_val, cash * 0.95)
                if target_val >= px * 100:
                    sh = int(target_val // (px * 100)) * 100
                    if sh >= 100:
                        amt = sh * px
                        fee = _calc_fee(amt, is_sell=False)
                        if cash >= amt + fee:
                            cash -= (amt + fee)
                            old_sh = shares[code]
                            shares[code] += sh
                            avg_cost[code] = (avg_cost[code] * old_sh + px * sh) / shares[code]
                            trades.append(dict(date=day, time='14:15', code=code,
                                               name=names.get(code, code), side='买(低吸)',
                                               price=round(px, 3), qty=sh,
                                               amount=round(amt, 2), fee=round(fee, 2),
                                               pnl=0.0,
                                               mode=('minute' if day in all_minute_days else 'daily')))

        total = mark_to_market(day)
        bval = bench_value(day)
        nav_records.append(dict(date=day, nav=total / init_capital, total=total))
        bench_nav_records.append(dict(date=day, nav=bval / bench_first_value))
        daily_pnl.append(total - prev_total)
        prev_total = total
        b_prev = bval

    # 5. 组装结果
    nav_df = pd.DataFrame(nav_records)
    bench_df = pd.DataFrame(bench_nav_records)
    nav_df['bench_nav'] = bench_df['nav']
    nav_df['excess'] = nav_df['nav'] - nav_df['bench_nav']
    nav_df['pnl'] = daily_pnl

    metrics = calc_metrics(nav_df, init_capital)

    # 期末持仓
    last_day = trade_dates[-1]
    positions = []
    for code, I in ind.items():
        if shares[code] > 0 and last_day in I['dates']:
            idx = I['dates'].index(last_day)
            close = I['close'][idx]
            mv = shares[code] * close
            float_pnl = (close - avg_cost[code]) * shares[code]
            positions.append(dict(date=last_day, code=code,
                                  name=names.get(code, code),
                                  qty=shares[code], close=round(close, 3),
                                  mv=round(mv, 2),
                                  pnl=round(float_pnl, 2)))

    n_minute_days = sum(1 for d in trade_dates if d in all_minute_days)
    n_daily_days = len(trade_dates) - n_minute_days

    return dict(nav_df=nav_df, trades=trades, positions=positions,
                metrics=metrics, dates=trade_dates,
                n_minute_days=n_minute_days, n_daily_days=n_daily_days)


def calc_metrics(nav_df, init_capital):
    nav = nav_df['nav'].values
    bench = nav_df['bench_nav'].values
    ret = np.diff(nav) / nav[:-1]
    bret = np.diff(bench) / bench[:-1]
    if len(ret) == 0:
        return dict()

    total_ret = nav[-1] / nav[0] - 1.0
    bench_ret = bench[-1] / bench[0] - 1.0
    n_days = len(nav)
    ann = (1 + total_ret) ** (252.0 / max(n_days, 1)) - 1.0
    b_ann = (1 + bench_ret) ** (252.0 / max(n_days, 1)) - 1.0

    # Alpha/Beta
    if len(ret) > 2 and np.std(bret) > 1e-9:
        cov = np.cov(ret, bret)[0, 1]
        beta = cov / np.var(bret)
        alpha_daily = np.mean(ret) - beta * np.mean(bret)
        alpha = alpha_daily * 252.0
    else:
        beta = 0.0
        alpha = 0.0

    # Sharpe / Sortino
    std = np.std(ret)
    sharpe = np.mean(ret) / std * np.sqrt(252) if std > 1e-9 else 0.0
    downside = ret[ret < 0]
    dstd = np.std(downside) if len(downside) > 1 else 1e-9
    sortino = np.mean(ret) / dstd * np.sqrt(252) if dstd > 1e-9 else 0.0

    # 信息比率
    excess_ret = ret - bret
    e_std = np.std(excess_ret)
    info_ratio = np.mean(excess_ret) / e_std * np.sqrt(252) if e_std > 1e-9 else 0.0

    # 最大回撤
    peak = np.maximum.accumulate(nav)
    dd = (nav - peak) / peak
    max_dd = dd.min()

    # 胜率（日度）
    win_days = np.sum(ret > 0)
    win_rate = win_days / len(ret) if len(ret) > 0 else 0.0

    return dict(
        total_ret=total_ret, ann_ret=ann, bench_ret=bench_ret,
        excess=total_ret - bench_ret, alpha=alpha, beta=beta,
        sharpe=sharpe, sortino=sortino, info_ratio=info_ratio,
        max_dd=max_dd, win_rate=win_rate,
        vol=np.std(ret) * np.sqrt(252), b_vol=np.std(bret) * np.sqrt(252),
        n_days=n_days,
    )


# ============================================================
# 代码编辑器：语法高亮
# ============================================================
class PythonHighlighter(QSyntaxHighlighter):
    KEYWORDS = [
        'def', 'class', 'return', 'if', 'elif', 'else', 'for', 'while',
        'import', 'from', 'as', 'with', 'try', 'except', 'finally', 'raise',
        'lambda', 'pass', 'break', 'continue', 'and', 'or', 'not', 'in',
        'is', 'None', 'True', 'False', 'yield', 'global', 'nonlocal',
    ]

    def __init__(self, document):
        super().__init__(document)
        self.rules = []

        kw = QTextCharFormat()
        kw.setForeground(QColor('#569cd6'))
        kw.setFontWeight(QFont.Weight.Bold)
        self.rules.append((r'\b\w+\b', kw))  # placeholder, replaced below

        # 关键词
        fmt_kw = QTextCharFormat()
        fmt_kw.setForeground(QColor('#569cd6'))
        fmt_kw.setFontWeight(QFont.Weight.Bold)
        self.rules = [(r'\b' + w + r'\b', fmt_kw) for w in self.KEYWORDS]

        # 字符串
        fmt_str = QTextCharFormat()
        fmt_str.setForeground(QColor('#ce9178'))
        self.rules.append((r'"[^"\\]*(\\.[^"\\]*)*"', fmt_str))
        self.rules.append((r"'[^'\\]*(\\.[^'\\]*)*'", fmt_str))

        # 注释
        fmt_com = QTextCharFormat()
        fmt_com.setForeground(QColor('#6a9955'))
        fmt_com.setFontItalic(True)
        self.rules.append((r'#\[^\n]*', fmt_com))

        # 数字
        fmt_num = QTextCharFormat()
        fmt_num.setForeground(QColor('#b5cea8'))
        self.rules.append((r'\b[0-9]+\.?[0-9]*\b', fmt_num))

        # 函数调用
        fmt_func = QTextCharFormat()
        fmt_func.setForeground(QColor('#dcdcaa'))
        self.rules.append((r'\b[A-Za-z_]\w*(?=\()', fmt_func))

        import re
        self._re = re

    def highlightBlock(self, text):
        for pat, fmt in self.rules:
            it = self._re.finditer(pat, text)
            for m in it:
                self.setFormat(m.start(), m.end() - m.start(), fmt)


# ============================================================
# 代码编辑器（行号）
# ============================================================
class _LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self):
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self._editor.paint_line_numbers(event)


class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self._update_line_number_area_width(0)
        # 深色主题
        self.setStyleSheet(
            'QPlainTextEdit{background:#1e1e1e;color:#d4d4d4;'
            'font-family:Consolas,"Courier New";font-size:13px;}')
        f = QFont('Consolas')
        f.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(f)
        self.highlighter = PythonHighlighter(self.document())

    def line_number_area_width(self):
        digits = max(3, len(str(max(1, self.blockCount()))))
        return 22 + self.fontMetrics().horizontalAdvance('9') * digits

    def _update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(),
                                         self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def paint_line_numbers(self, event):
        p = QPainter(self.line_number_area)
        p.fillRect(event.rect(), QColor('#252526'))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                num = str(block_number + 1)
                p.setPen(QColor('#858585'))
                p.drawText(0, top, self.line_number_area.width() - 6,
                           self.fontMetrics().height(),
                           Qt.AlignmentFlag.AlignRight, num)
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1
        p.end()


# ============================================================
# 指标卡片
# ============================================================
class MetricCard(QFrame):
    def __init__(self, title, value='--'):
        super().__init__()
        self.setStyleSheet(
            f'QFrame{{background:{CARD};border:1px solid {BORDER};border-radius:10px;}}')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        self.title_lb = QLabel(title)
        self.title_lb.setStyleSheet(f'color:{TEXT2};font-size:11px;background:transparent;')
        self.value_lb = QLabel(value)
        self.value_lb.setStyleSheet(f'color:{TEXT};font-size:18px;font-weight:bold;background:transparent;')
        lay.addWidget(self.title_lb)
        lay.addWidget(self.value_lb)

    def set_value(self, text, color=None):
        self.value_lb.setText(text)
        c = color or TEXT
        self.value_lb.setStyleSheet(f'color:{c};font-size:18px;font-weight:bold;background:transparent;')


# ============================================================
# 图表
# ============================================================
class BacktestChart(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(6, 3.2), dpi=90)
        self.ax1 = self.fig.add_subplot(211)
        self.ax2 = self.fig.add_subplot(212, sharex=self.ax1)
        self.fig.subplots_adjust(hspace=0.35, left=0.08, right=0.97, top=0.95, bottom=0.08)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def plot(self, nav_df):
        self.ax1.clear()
        self.ax2.clear()
        x = range(len(nav_df))
        self.ax1.plot(x, nav_df['nav'].values, color=RED, label='策略净值', lw=1.6)
        self.ax1.plot(x, nav_df['bench_nav'].values, color='#888888',
                      label='基准(等权)', lw=1.3)
        self.ax1.plot(x, nav_df['excess'].values + 1.0, color=BLUE,
                      label='超额(平移)', lw=1.0, ls='--')
        self.ax1.legend(loc='upper left', fontsize=8)
        self.ax1.set_ylabel('净值')
        self.ax1.grid(alpha=0.2)

        colors = [GREEN if v >= 0 else RED for v in nav_df['pnl'].values]
        self.ax2.bar(x, nav_df['pnl'].values, color=colors, width=1.0)
        self.ax2.axhline(0, color='#999', lw=0.6)
        self.ax2.set_ylabel('每日盈亏')
        self.ax2.grid(alpha=0.2)

        # x 轴日期刻度
        n = len(nav_df)
        step = max(1, n // 8)
        ticks = list(range(0, n, step))
        labels = [nav_df['date'].iloc[i][5:] for i in ticks]
        self.ax2.set_xticks(ticks)
        self.ax2.set_xticklabels(labels, rotation=30, fontsize=7)
        self.fig.autofmt_xdate(rotation=30)
        self.draw()


# ============================================================
# 后台回测线程
# ============================================================
class BacktestWorker(QThread):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    done = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, start, end, capital, codes_names):
        super().__init__()
        self.start_date = start
        self.end_date = end
        self.capital = capital
        self.codes_names = codes_names

    def run(self):
        try:
            self.log.emit(f'开始回测 {self.start_date} ~ {self.end_date}，'
                          f'初始资金 {self.capital:.0f} 元，'
                          f'股票池 {len(self.codes_names)} 只')
            self.progress.emit(5)

            # —— 后台线程刷新分钟级数据（腾讯5分钟线），不阻塞UI主线程；
            #    任何失败都降级为日线近似，绝不中断回测 ——
            if _mk is not None:
                try:
                    self.log.emit('正在后台刷新分钟级数据（腾讯5分钟线）…')
                    codes = [c for c, _n in self.codes_names]
                    st = _mk.download_all(codes)
                    self.log.emit(
                        f"分钟数据就绪：{st.get('n_stock',0)} 只 / {st.get('total_rows',0)} 条 "
                        f"({st.get('date_min')} ~ {st.get('date_max')})")
                except Exception as e:
                    self.log.emit(f'分钟数据刷新失败，VWAP 回退日线近似：{e}')

            res = run_backtest(self.start_date, self.end_date, self.capital,
                               self.codes_names,
                               progress_cb=lambda p: self.progress.emit(p))
            self.progress.emit(100)
            self.log.emit(f'回测完成：共 {len(res["trades"])} 笔成交，'
                          f'{len(res["dates"])} 个交易日')
            self.done.emit(res)
        except Exception as e:
            self.failed.emit(f'{e}\n{traceback.format_exc()}')


# ============================================================
# 后台刷新分钟数据线程（腾讯5分钟线）
# ============================================================
class MinuteRefreshWorker(QThread):
    """独立刷新分钟数据线程，不阻塞主UI；失败不影响已有数据回测。"""
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    done = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, codes):
        super().__init__()
        self.codes = codes

    def run(self):
        try:
            if _mk is None:
                self.failed.emit('minute_kline 模块未加载，无法刷新')
                return
            self.log.emit(f'开始刷新分钟数据，共 {len(self.codes)} 只股票（每只最新640根5分钟bar）…')
            self.progress.emit(5)
            st = _mk.download_all(
                self.codes,
                progress_cb=lambda d, t, c: self.progress.emit(int(10 + 85 * d / max(t, 1))),
                log_cb=lambda m: self.log.emit(m),
            )
            self.progress.emit(100)
            self.log.emit(
                f"分钟数据刷新完成：{st.get('n_stock',0)} 只 / {st.get('total_rows',0)} 条 "
                f"({st.get('date_min')} ~ {st.get('date_max')})")
            self.done.emit(st)
        except Exception as e:
            self.failed.emit(f'{type(e).__name__}: {e}')


# ============================================================
# 主页面
# ============================================================
class BacktestPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._refresh_worker = None
        self._minute_cov = None   # minute_kline.duckdb 当前覆盖范围 dict
        self._build_ui()
        # 初始化分钟数据覆盖范围，并把默认回测区间自动对齐到覆盖范围
        self.refresh_minute_coverage(initial_align=True)

    # ---------- UI 构建 ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        # 左：代码编辑器
        left = QFrame()
        left.setStyleSheet(f'background:{CARD};border:1px solid {BORDER};border-radius:10px;')
        llay = QVBoxLayout(left)
        llay.setContentsMargins(8, 8, 8, 8)

        # 顶部按钮行
        topbar = QHBoxLayout()
        self.saved_lb = QLabel('● 已保存')
        self.saved_lb.setStyleSheet(f'color:{GREEN};font-size:11px;')
        topbar.addWidget(self.saved_lb)
        topbar.addStretch()
        self.btn_compile = QPushButton('编译运行')
        self.btn_compile.setStyleSheet(
            f'QPushButton{{background:{BLUE};color:white;border:none;'
            f'border-radius:6px;padding:6px 14px;}}'
            f'QPushButton:hover{{background:#1f53d0;}}')
        self.btn_compile.clicked.connect(self.on_compile)
        topbar.addWidget(self.btn_compile)

        self.btn_save = QPushButton('保存修改')
        self.btn_save.setStyleSheet(
            f'QPushButton{{background:#ffffff;color:{TEXT};border:1px solid {BLUE};'
            f'border-radius:6px;padding:6px 14px;}}')
        self.btn_save.clicked.connect(self.on_save)
        topbar.addWidget(self.btn_save)

        self.btn_clone = QPushButton('克隆策略')
        self.btn_clone.setStyleSheet(
            f'QPushButton{{background:#ffffff;color:{TEXT};border:1px solid {BORDER};'
            f'border-radius:6px;padding:6px 14px;}}')
        self.btn_clone.clicked.connect(self.on_clone)
        topbar.addWidget(self.btn_clone)
        llay.addLayout(topbar)

        self.editor = CodeEditor()
        self.editor.setPlainText(DEFAULT_STRATEGY)
        llay.addWidget(self.editor, 1)

        # 日志面板
        log_lb = QLabel('日志')
        log_lb.setStyleSheet(f'color:{TEXT2};font-size:11px;')
        llay.addWidget(log_lb)
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumHeight(130)
        self.log_edit.setStyleSheet(
            'QTextEdit{background:#1e1e1e;color:#d4d4d4;border:1px solid #333;'
            'font-family:Consolas;font-size:12px;}')
        llay.addWidget(self.log_edit)

        # 右：结果区
        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(8)

        # 分钟数据刷新按钮 + 覆盖范围标签（任务二/任务一）
        refresh_row = QHBoxLayout()
        self.btn_refresh_minute = QPushButton('🔄 刷新分钟数据')
        self.btn_refresh_minute.setStyleSheet(
            f'QPushButton{{background:#ffffff;color:{TEXT};border:1px solid {BLUE};'
            f'border-radius:6px;padding:5px 12px;}}'
            f'QPushButton:hover{{background:#eaf1ff;}}'
            f'QPushButton:disabled{{color:#999;border-color:#cccccc;}}')
        self.btn_refresh_minute.clicked.connect(self.on_refresh_minute)
        refresh_row.addWidget(self.btn_refresh_minute)

        self.minute_coverage_label = QLabel('📡 分钟数据覆盖：查询中…')
        self.minute_coverage_label.setStyleSheet(f'color:{TEXT2};font-size:11px;')
        self.minute_coverage_label.setWordWrap(True)
        refresh_row.addWidget(self.minute_coverage_label)
        refresh_row.addStretch()
        rlay.addLayout(refresh_row)

        # 参数行
        param_row = QHBoxLayout()
        param_row.addWidget(QLabel('开始:'))
        self.dt_start = QDateEdit(QDate(2025, 1, 1))
        self.dt_start.setCalendarPopup(True)
        self.dt_start.setDisplayFormat('yyyy-MM-dd')
        param_row.addWidget(self.dt_start)

        param_row.addWidget(QLabel('结束:'))
        self.dt_end = QDateEdit(QDate(2025, 9, 10))
        self.dt_end.setCalendarPopup(True)
        self.dt_end.setDisplayFormat('yyyy-MM-dd')
        param_row.addWidget(self.dt_end)

        param_row.addWidget(QLabel('初始资金:'))
        self.ed_capital = QLineEdit('300000')
        self.ed_capital.setMaximumWidth(110)
        param_row.addWidget(self.ed_capital)

        param_row.addWidget(QLabel('频率:'))
        self.cb_freq = QComboBox()
        self.cb_freq.addItems(['分钟', '日线'])
        param_row.addWidget(self.cb_freq)

        param_row.addStretch()
        self.btn_run = QPushButton('▶ 运行回测')
        self.btn_run.setStyleSheet(
            f'QPushButton{{background:{BLUE};color:white;border:none;'
            f'border-radius:6px;padding:8px 20px;font-weight:bold;}}'
            f'QPushButton:hover{{background:#1f53d0;}}')
        self.btn_run.clicked.connect(self.on_run)
        param_row.addWidget(self.btn_run)
        rlay.addLayout(param_row)

        # 指标卡片
        cards = QHBoxLayout()
        cards.setSpacing(8)
        self.card_ret = MetricCard('策略收益')
        self.card_bench = MetricCard('基准收益')
        self.card_alpha = MetricCard('Alpha')
        self.card_sharpe = MetricCard('Sharpe')
        self.card_dd = MetricCard('最大回撤')
        self.card_win = MetricCard('胜率')
        for c in [self.card_ret, self.card_bench, self.card_alpha,
                  self.card_sharpe, self.card_dd, self.card_win]:
            cards.addWidget(c)
        cards.addStretch()
        self.precision_label = QLabel('')
        self.precision_label.setStyleSheet(f'color:{TEXT2};font-size:12px;font-weight:bold;')
        cards.addWidget(self.precision_label)
        rlay.addLayout(cards)

        # 图表
        self.chart = BacktestChart()
        self.chart.setMinimumHeight(260)
        rlay.addWidget(self.chart, 2)

        # 表格区
        tab_splitter = QSplitter(Qt.Orientation.Vertical)
        self.table_trade = QTableWidget(0, 10)
        self.table_trade.setHorizontalHeaderLabels(
            ['日期', '时间', '标的', '名称', '方向', '价格', '数量', '金额', '手续费', '备注'])
        self.table_trade.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_trade.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_position = QTableWidget(0, 6)
        self.table_position.setHorizontalHeaderLabels(
            ['日期', '代码', '名称', '数量', '收盘价', '市值/浮盈'])
        self.table_position.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_position.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tab_splitter.addWidget(self.table_trade)
        tab_splitter.addWidget(self.table_position)
        tab_splitter.setSizes([220, 160])
        rlay.addWidget(tab_splitter, 2)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([560, 760])

    # ---------- 分钟数据覆盖范围（任务一/任务二共用） ----------
    def refresh_minute_coverage(self, initial_align=False):
        """
        查询 minute_kline.duckdb 覆盖范围（read_only），更新 minute_coverage_label。
        initial_align=True 时，把日期选择器自动对齐到 [date_min, date_max]。
        """
        cov = None
        if _mk is not None:
            try:
                cov = _mk.get_coverage_stats()
            except Exception as e:
                self.log(f'查询分钟数据覆盖失败: {e}')
                cov = None
        self._minute_cov = cov

        if not cov or not cov.get('date_min') or not cov.get('date_max'):
            self.minute_coverage_label.setText('📡 分钟数据覆盖：暂无数据')
            self.minute_coverage_label.setStyleSheet(f'color:#999;font-size:11px;')
            return

        self.minute_coverage_label.setText(
            f"📡 分钟数据覆盖：{cov['date_min']} ~ {cov['date_max']}"
            f"（共 {cov['n_days']} 个交易日）")
        self.minute_coverage_label.setStyleSheet(f'color:{GREEN};font-size:11px;')
        self.log(f"分钟数据覆盖：{cov['date_min']} ~ {cov['date_max']}，"
                 f"{cov['n_days']} 个交易日 / {cov['n_stock']} 只股票")

        if initial_align:
            try:
                dmin = cov['date_min']
                dmax = cov['date_max']
                sy, sm, sd = int(dmin[0:4]), int(dmin[5:7]), int(dmin[8:10])
                ey, em, ed = int(dmax[0:4]), int(dmax[5:7]), int(dmax[8:10])
                self.dt_start.setDate(QDate(sy, sm, sd))
                self.dt_end.setDate(QDate(ey, em, ed))
                self.log(f"已自动对齐回测默认区间为 {dmin} ~ {dmax}")
            except Exception as e:
                self.log(f'自动对齐日期失败: {e}')

    # ---------- 刷新分钟数据（任务二） ----------
    def on_refresh_minute(self):
        if self._refresh_worker and self._refresh_worker.isRunning():
            return
        codes_names = load_watchlist()
        if not codes_names:
            QMessageBox.warning(self, '错误', '自选股为空，无法刷新分钟数据')
            return
        codes = [c for c, _n in codes_names]
        self.btn_refresh_minute.setEnabled(False)
        self.btn_refresh_minute.setText('⏳ 刷新中...')
        self.log(f'开始刷新分钟数据，股票池 {len(codes)} 只…')

        self._refresh_worker = MinuteRefreshWorker(codes)
        self._refresh_worker.log.connect(self.log)
        self._refresh_worker.done.connect(self.on_refresh_minute_done)
        self._refresh_worker.failed.connect(self.on_refresh_minute_failed)
        self._refresh_worker.start()

    def on_refresh_minute_done(self, st):
        self.btn_refresh_minute.setEnabled(True)
        self.btn_refresh_minute.setText('🔄 刷新分钟数据')
        # 重新查询覆盖范围并更新标签
        self.refresh_minute_coverage(initial_align=False)
        cov = self._minute_cov or {}
        dmin = cov.get('date_min') or '?'
        dmax = cov.get('date_max') or '?'
        QMessageBox.information(
            self, '刷新成功',
            f'✅ 刷新成功！最新覆盖范围：{dmin} ~ {dmax}')

    def on_refresh_minute_failed(self, err):
        self.btn_refresh_minute.setEnabled(True)
        self.btn_refresh_minute.setText('🔄 刷新分钟数据')
        self.log(f'分钟数据刷新失败: {err}')
        QMessageBox.warning(
            self, '刷新失败',
            f'❌ 刷新失败，请检查网络或稍后重试\n\n{err}\n\n已有数据不受影响，可继续回测。')

    # ---------- 日志 ----------
    def log(self, msg):
        ts = datetime.now().strftime('%H:%M:%S')
        self.log_edit.append(f'[{ts}] {msg}')

    # ---------- 编译 ----------
    def on_compile(self):
        code = self.editor.toPlainText()
        try:
            ast.parse(code)
            self.log('编译成功，准备回测')
            QMessageBox.information(self, '编译', '编译成功，准备回测')
        except SyntaxError as e:
            self.log(f'语法错误: 第{e.lineno}行 {e.msg}')
            QMessageBox.warning(self, '语法错误',
                                f'第 {e.lineno} 行: {e.msg}')

    # ---------- 保存 ----------
    def on_save(self):
        code = self.editor.toPlainText()
        path = os.path.join(STRATEGY_DIR, 't_strategy_001.py')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(code)
        self.saved_lb.setText('● 已保存')
        self.saved_lb.setStyleSheet(f'color:{GREEN};font-size:11px;')
        self.log(f'策略已保存到 {path}')

    # ---------- 克隆 ----------
    def on_clone(self):
        code = self.editor.toPlainText()
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        path = os.path.join(STRATEGY_DIR, f't_strategy_clone_{ts}.py')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(code)
        self.log(f'已克隆策略到 {path}')
        QMessageBox.information(self, '克隆', f'已克隆为 t_strategy_clone_{ts}.py')

    # ---------- 运行回测 ----------
    def on_run(self):
        if self._worker and self._worker.isRunning():
            return
        try:
            capital = float(self.ed_capital.text().strip())
            if capital < 1 or capital > 1e8:
                raise ValueError('初始资金需在 1 ~ 1亿 之间')
        except Exception as e:
            QMessageBox.warning(self, '参数错误', str(e))
            return

        start = self.dt_start.date().toString('yyyy-MM-dd')
        end = self.dt_end.date().toString('yyyy-MM-dd')
        codes_names = load_watchlist()
        if not codes_names:
            QMessageBox.warning(self, '错误', '自选股为空')
            return

        # 任务一：用户手动选日期超出分钟数据覆盖范围时，弹非阻断式确认
        cov = getattr(self, '_minute_cov', None)
        if cov and cov.get('date_min') and cov.get('date_max'):
            if start < cov['date_min'] or end > cov['date_max']:
                ret = QMessageBox.question(
                    self, '区间超出分钟数据覆盖',
                    '⚠️ 所选区间超出分钟数据覆盖范围，超出部分将回退日线近似模式，是否继续？',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes)
                if ret != QMessageBox.StandardButton.Yes:
                    self.log('用户取消回测（区间超出分钟数据覆盖）')
                    return

        self.btn_run.setEnabled(False)
        self.btn_run.setText('回测中...')
        self.log(f'参数: {start} ~ {end}, 资金 {capital:.0f}, 股票池 {len(codes_names)} 只')

        self._worker = BacktestWorker(start, end, capital, codes_names)
        self._worker.log.connect(self.log)
        self._worker.done.connect(self.on_done)
        self._worker.failed.connect(self.on_failed)
        self._worker.start()

    def on_failed(self, err):
        self.btn_run.setEnabled(True)
        self.btn_run.setText('▶ 运行回测')
        self.log(f'回测失败: {err.splitlines()[0]}')
        QMessageBox.critical(self, '回测失败', err[:800])

    def on_done(self, res):
        self.btn_run.setEnabled(True)
        self.btn_run.setText('▶ 运行回测')
        m = res['metrics']
        if not m:
            self.log('无回测结果')
            return

        def pct(x):
            return f'{x*100:.2f}%'

        def num(x):
            return f'{x:.2f}'

        self.card_ret.set_value(pct(m['total_ret']), RED if m['total_ret'] >= 0 else GREEN)
        self.card_bench.set_value(pct(m['bench_ret']), TEXT)
        self.card_alpha.set_value(num(m['alpha']), RED if m['alpha'] >= 0 else GREEN)
        self.card_sharpe.set_value(num(m['sharpe']), TEXT)
        self.card_dd.set_value(pct(m['max_dd']), GREEN)
        self.card_win.set_value(pct(m['win_rate']), TEXT)

        self.log(
            f"年化 {pct(m['ann_ret'])} | 超额 {pct(m['excess'])} | "
            f"Beta {num(m['beta'])} | Sortino {num(m['sortino'])} | "
            f"IR {num(m['info_ratio'])} | 波动 {pct(m['vol'])}")

        # 图表
        self.chart.plot(res['nav_df'])

        # —— 任务三：精度标签 ——
        n_m = int(res.get('n_minute_days', 0))
        n_d = int(res.get('n_daily_days', 0))
        if n_d == 0 and n_m > 0:
            self.precision_label.setText('🟢 分钟级精度')
            self.precision_label.setStyleSheet(
                'color:#43a047;font-size:12px;font-weight:bold;')
        elif n_m == 0 and n_d == 0:
            self.precision_label.setText('')
        else:
            self.precision_label.setText(f'🟡 混合精度（{n_m}天分钟 + {n_d}天日线）')
            self.precision_label.setStyleSheet(
                'color:#f57c00;font-size:12px;font-weight:bold;')
        self.log(f"精度统计：{n_m} 天分钟级 + {n_d} 天日线近似")

        # 交易表（10列：日期/时间/标的/名称/方向/价格/数量/金额/手续费/备注）
        # 日线近似触发的交易：灰色字体，备注写 [日线近似]；分钟级触发：正常字体，备注写 [分钟级]
        trades = res['trades']
        self.table_trade.setRowCount(len(trades))
        GRAY = QColor('#9e9e9e')
        for r, t in enumerate(trades):
            mode = t.get('mode', 'daily')
            note = '[分钟级]' if mode == 'minute' else '[日线近似]'
            is_daily = (mode != 'minute')
            vals = [t['date'], t['time'], t['code'], t['name'], t['side'],
                    f"{t['price']:.3f}", str(t['qty']),
                    f"{t['amount']:.2f}", f"{t['fee']:.2f}", note]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                if is_daily:
                    item.setForeground(GRAY)
                elif c == 4:
                    item.setForeground(QColor(RED if '卖' in v else GREEN))
                self.table_trade.setItem(r, c, item)

        # 持仓表
        positions = res['positions']
        self.table_position.setRowCount(len(positions))
        for r, p in enumerate(positions):
            vals = [p['date'], p['code'], p['name'], str(p['qty']),
                    f"{p['close']:.3f}",
                    f"市值{p['mv']:.0f} / 浮盈{p['pnl']:.0f}"]
            for c, v in enumerate(vals):
                self.table_position.setItem(r, c, QTableWidgetItem(str(v)))

        self.log(f'结果已展示：{len(trades)} 笔交易，{len(positions)} 只持仓')
