"""
技术指标计算工具
基于交易系统参数:
- KDJ: 13,3,3
- MACD: 8,21,5
- MA: 5, 9, 20
"""
import pandas as pd
import numpy as np


# ========== 均线指标 ==========

def calc_ma(close_prices, period):
    """计算移动平均线(最新值)"""
    if len(close_prices) < period:
        return None
    return float(np.mean(close_prices[-period:]))


def calc_ma_series(close_prices, period):
    """计算MA序列"""
    if len(close_prices) < period:
        return pd.Series([np.nan] * len(close_prices))
    return pd.Series(close_prices).rolling(window=period).mean()


def is_ma_golden_cross(ma_series_short, ma_series_long):
    """
    判断短期均线上穿长期均线(金叉)
    最近一根K线形成金叉
    """
    if len(ma_series_short) < 2 or len(ma_series_long) < 2:
        return False
    s_prev = ma_series_short.iloc[-2]
    s_curr = ma_series_short.iloc[-1]
    l_prev = ma_series_long.iloc[-2]
    l_curr = ma_series_long.iloc[-1]
    if pd.isna(s_prev) or pd.isna(s_curr) or pd.isna(l_prev) or pd.isna(l_curr):
        return False
    # 金叉: 短期均线从下方上穿长期均线
    return s_prev <= l_prev and s_curr > l_curr


def is_ma_dead_cross(ma_series_short, ma_series_long):
    """
    判断短期均线下穿长期均线(死叉)
    最近一根K线形成死叉
    """
    if len(ma_series_short) < 2 or len(ma_series_long) < 2:
        return False
    s_prev = ma_series_short.iloc[-2]
    s_curr = ma_series_short.iloc[-1]
    l_prev = ma_series_long.iloc[-2]
    l_curr = ma_series_long.iloc[-1]
    if pd.isna(s_prev) or pd.isna(s_curr) or pd.isna(l_prev) or pd.isna(l_curr):
        return False
    # 死叉: 短期均线从上方下穿长期均线
    return s_prev >= l_prev and s_curr < l_curr


def is_price_above_ma(close_price, ma_value):
    """判断股价是否在均线上方"""
    if ma_value is None or ma_value == 0:
        return False
    return close_price >= ma_value


def detect_ma_cross_in_range(ma_series_short, ma_series_long, days=20, cross_type='golden'):
    """
    检测最近N个交易日内是否出现过金叉/死叉
    
    Args:
        cross_type: 'golden' 金叉, 'dead' 死叉
    Returns:
        (是否出现, 最近一次出现的位置(倒数第几天))
    """
    n = min(days, len(ma_series_short) - 1)
    if n < 1:
        return False, -1
    
    for i in range(1, n + 1):
        idx = -i - 1
        if idx < -len(ma_series_short) + 1:
            break
        s_prev = ma_series_short.iloc[idx]
        s_curr = ma_series_short.iloc[idx + 1]
        l_prev = ma_series_long.iloc[idx]
        l_curr = ma_series_long.iloc[idx + 1]
        if pd.isna(s_prev) or pd.isna(s_curr) or pd.isna(l_prev) or pd.isna(l_curr):
            continue
        
        if cross_type == 'golden':
            if s_prev <= l_prev and s_curr > l_curr:
                return True, i
        else:
            if s_prev >= l_prev and s_curr < l_curr:
                return True, i
    
    return False, -1


# ========== MACD指标 ==========

def calc_macd(close_prices, fast=8, slow=21, signal=5):
    """
    计算MACD指标 (8,21,5)
    返回: dif(最新值), dea(最新值), macd_hist(最新值), macd_hist(序列)
    """
    close_series = pd.Series(close_prices)
    ema_fast = close_series.ewm(span=fast, adjust=False).mean()
    ema_slow = close_series.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    macd_hist = 2 * (dif - dea)
    return float(dif.iloc[-1]), float(dea.iloc[-1]), float(macd_hist.iloc[-1]), macd_hist


def calc_macd_series(close_prices, fast=8, slow=21, signal=5):
    """计算MACD完整序列"""
    close_series = pd.Series(close_prices)
    ema_fast = close_series.ewm(span=fast, adjust=False).mean()
    ema_slow = close_series.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    macd_hist = 2 * (dif - dea)
    return dif, dea, macd_hist


def is_macd_golden_cross(dif_series, dea_series):
    """判断MACD金叉(DIF上穿DEA)"""
    if len(dif_series) < 2 or len(dea_series) < 2:
        return False
    d_prev = dif_series.iloc[-2]
    d_curr = dif_series.iloc[-1]
    e_prev = dea_series.iloc[-2]
    e_curr = dea_series.iloc[-1]
    if pd.isna(d_prev) or pd.isna(d_curr) or pd.isna(e_prev) or pd.isna(e_curr):
        return False
    return d_prev <= e_prev and d_curr > e_curr


def is_macd_dead_cross(dif_series, dea_series):
    """判断MACD死叉(DIF下穿DEA)"""
    if len(dif_series) < 2 or len(dea_series) < 2:
        return False
    d_prev = dif_series.iloc[-2]
    d_curr = dif_series.iloc[-1]
    e_prev = dea_series.iloc[-2]
    e_curr = dea_series.iloc[-1]
    if pd.isna(d_prev) or pd.isna(d_curr) or pd.isna(e_prev) or pd.isna(e_curr):
        return False
    return d_prev >= e_prev and d_curr < e_curr


# ========== KDJ指标 ==========

def calc_kdj(high_prices, low_prices, close_prices, n=13, m1=3, m2=3):
    """
    计算KDJ指标 (13,3,3)
    返回: k(最新值), d(最新值), j(最新值)
    """
    high_series = pd.Series(high_prices)
    low_series = pd.Series(low_prices)
    close_series = pd.Series(close_prices)

    lowest_low = low_series.rolling(window=n, min_periods=1).min()
    highest_high = high_series.rolling(window=n, min_periods=1).max()

    rsv = (close_series - lowest_low) / (highest_high - lowest_low) * 100
    rsv = rsv.fillna(50)

    k = rsv.ewm(com=m1 - 1, adjust=False).mean()
    d = k.ewm(com=m2 - 1, adjust=False).mean()
    j = 3 * k - 2 * d

    return float(k.iloc[-1]), float(d.iloc[-1]), float(j.iloc[-1])


def calc_kdj_series(high_prices, low_prices, close_prices, n=13, m1=3, m2=3):
    """计算KDJ完整序列"""
    high_series = pd.Series(high_prices)
    low_series = pd.Series(low_prices)
    close_series = pd.Series(close_prices)

    lowest_low = low_series.rolling(window=n, min_periods=1).min()
    highest_high = high_series.rolling(window=n, min_periods=1).max()

    rsv = (close_series - lowest_low) / (highest_high - lowest_low) * 100
    rsv = rsv.fillna(50)

    k = rsv.ewm(com=m1 - 1, adjust=False).mean()
    d = k.ewm(com=m2 - 1, adjust=False).mean()
    j = 3 * k - 2 * d

    return k, d, j


def is_kdj_golden_cross(k_series, d_series):
    """判断KDJ金叉(K上穿D)"""
    if len(k_series) < 2 or len(d_series) < 2:
        return False
    k_prev = k_series.iloc[-2]
    k_curr = k_series.iloc[-1]
    d_prev = d_series.iloc[-2]
    d_curr = d_series.iloc[-1]
    if pd.isna(k_prev) or pd.isna(k_curr) or pd.isna(d_prev) or pd.isna(d_curr):
        return False
    return k_prev <= d_prev and k_curr > d_curr


def is_kdj_dead_cross(k_series, d_series):
    """判断KDJ死叉(K下穿D)"""
    if len(k_series) < 2 or len(d_series) < 2:
        return False
    k_prev = k_series.iloc[-2]
    k_curr = k_series.iloc[-1]
    d_prev = d_series.iloc[-2]
    d_curr = d_series.iloc[-1]
    if pd.isna(k_prev) or pd.isna(k_curr) or pd.isna(d_prev) or pd.isna(d_curr):
        return False
    return k_prev >= d_prev and k_curr < d_curr


def is_j_in_range(j_value, low=-20, high=10):
    """判断J值是否在指定区间"""
    return low <= j_value <= high


# ========== 成交量指标 ==========

def calc_volume_ratio(volumes, period=5):
    """计算量比(当前成交量/N日均量)"""
    if len(volumes) < period + 1:
        return 1.0
    avg_vol = np.mean(volumes[-period-1:-1])
    if avg_vol == 0:
        return 1.0
    return float(volumes[-1] / avg_vol)


def calc_avg_volume(volumes, period=20):
    """计算N日平均成交量"""
    if len(volumes) < period:
        return 0.0
    return float(np.mean(volumes[-period:]))


def is_volume_breakout(volumes, period=20):
    """判断成交量是否突破N日均量"""
    if len(volumes) < period + 1:
        return False
    avg_vol = np.mean(volumes[-period-1:-1])
    if avg_vol == 0:
        return False
    return volumes[-1] > avg_vol


def is_volume_breakout_multi(volumes, periods=[20, 120]):
    """判断成交量是否同时突破多个周期均量"""
    for p in periods:
        if not is_volume_breakout(volumes, p):
            return False
    return True


# ========== 价格形态 ==========

def is_consecutive_down(close_prices, days=3):
    """
    判断是否连续下跌(连续N天收盘价低于前一天)
    最近N天连续下跌
    """
    if len(close_prices) < days + 1:
        return False
    for i in range(-days, 0):
        if close_prices[i] >= close_prices[i - 1]:
            return False
    return True


def is_consecutive_up(close_prices, days=2):
    """
    判断是否连续上涨(连续N天收盘价高于前一天)
    最近N天连续上涨
    """
    if len(close_prices) < days + 1:
        return False
    for i in range(-days, 0):
        if close_prices[i] <= close_prices[i - 1]:
            return False
    return True


def detect_consecutive_down_in_range(close_prices, days_range=10, min_days=3):
    """
    检测最近N个交易日内是否出现过连续下跌
    
    Returns:
        (是否出现, 连续天数)
    """
    n = min(days_range, len(close_prices) - 1)
    if n < min_days:
        return False, 0
    
    max_consecutive = 0
    current_streak = 0
    
    for i in range(-n, 0):
        if close_prices[i] < close_prices[i - 1]:
            current_streak += 1
            max_consecutive = max(max_consecutive, current_streak)
        else:
            current_streak = 0
    
    return max_consecutive >= min_days, max_consecutive


def is_price_near_ma(close_price, ma_value, threshold=0.02):
    """
    判断股价是否接近均线
    threshold: 偏离比例阈值(默认2%)
    """
    if ma_value is None or ma_value == 0:
        return False
    diff_ratio = abs(close_price - ma_value) / ma_value
    return diff_ratio <= threshold


# ========== 涨停统计 ==========

def _lu_pct(code, base=9.8) -> float:
    """[CYB-GATE] 按板性返回判涨停阈值（%）。

    base 是本模块的历史口径（默认 9.8）。code 为空时**原样返回 base**，
    因此所有老调用方（不传 code）的行为与改动前完全一致；
    只有显式传入 code 才会按板性 +10 / +20。
    """
    c = str(code or '')
    if not c:
        return base
    if c.startswith(('300', '301', '688', '689')):
        return base + 10.0
    if c.startswith(('8', '4', '920')):
        return base + 20.0
    return base


def calc_limit_up_count(close_prices, pct_changes, days=252, code=None):
    """
    统计N日内涨停次数（按板性；code 为空时沿用旧口径 9.8%）
    """
    count = 0
    check_days = min(days, len(pct_changes))
    for i in range(-check_days, 0):
        if pct_changes[i] >= _lu_pct(code):
            count += 1
    return count


def is_yesterday_limit_up(pct_changes, code=None):
    """判断前一天是否涨停"""
    if len(pct_changes) < 2:
        return False
    return pct_changes[-2] >= _lu_pct(code)


# ========== RSI指标 ==========

def calc_rsi(close_prices, period=14):
    """
    计算RSI相对强弱指标（最新值）
    Args:
        close_prices: 收盘价列表
        period: 周期，默认14
    Returns:
        float: RSI值 (0-100)
    """
    if len(close_prices) < period + 1:
        return 50.0

    closes = pd.Series(close_prices)
    delta = closes.diff()

    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    val = rsi.iloc[-1]
    if pd.isna(val):
        return 50.0
    return float(val)


# ========== 振幅指标 ==========

def calc_amplitude(high, low, prev_close):
    """
    计算当日振幅
    振幅 = (最高价 - 最低价) / 昨收 × 100%
    """
    if prev_close <= 0:
        return 0
    return round((high - low) / prev_close * 100, 2)


# ========== 周成交量比 ==========

def calc_week_volume_ratio(volumes):
    """
    计算周成交量/近5日成交量比
    周成交量 = 最近5个交易日成交量之和
    近5个交易日成交量 = 最近5个交易日成交量之和（其实是一样的，这里用近10日/近5日）
    这里解释为：最近5日成交量 / 之前5日成交量（量能放大倍数）
    """
    if len(volumes) < 10:
        return 1.0

    recent_5 = sum(volumes[-5:])
    prev_5 = sum(volumes[-10:-5])

    if prev_5 == 0:
        return 1.0
    return round(recent_5 / prev_5, 2)


# ========== 区间统计 ==========

def calc_high_price(high_prices, days=168):
    """计算近N日最高价(8个月约168个交易日)"""
    check_days = min(days, len(high_prices))
    if check_days == 0:
        return 0
    return float(max(high_prices[-check_days:]))


def calc_low_price(low_prices, days=10):
    """计算近N日最低价"""
    check_days = min(days, len(low_prices))
    if check_days == 0:
        return 0
    return float(min(low_prices[-check_days:]))


# ========== 兼容旧接口 ==========

def is_ma_bullish(ma5, ma10, ma20):
    """判断均线多头排列 MA5 > MA10 > MA20(兼容旧代码)"""
    if ma5 is None or ma10 is None or ma20 is None:
        return False
    return ma5 > ma10 > ma20


def is_macd_red_expanding(macd_hist_series):
    """判断MACD红柱是否扩大(兼容旧代码)"""
    if len(macd_hist_series) < 3:
        return False
    h1 = macd_hist_series.iloc[-1]
    h2 = macd_hist_series.iloc[-2]
    return h1 > 0 and h2 > 0 and h1 > h2


def is_kdj_golden_cross_low(k_values, d_values, k_threshold=50):
    """判断KDJ低位金叉(兼容旧代码)"""
    return is_kdj_golden_cross(k_values, d_values)


def calc_avg_price(prices, volumes):
    """计算分时均价线"""
    if len(prices) == 0 or len(volumes) == 0:
        return 0
    total_amount = sum(p * v for p, v in zip(prices, volumes))
    total_volume = sum(volumes)
    if total_volume == 0:
        return prices[-1] if prices else 0
    return total_amount / total_volume
