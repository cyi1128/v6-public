"""
通达信pytdx连接工具
自动尝试多个服务器，确保连接成功
V2.9.2：新增pytdx全局熔断（连续2次空数据→60秒冷却），单台超时2秒，总超时≤5秒
"""
import threading
import time
from pytdx.hq import TdxHq_API

# V2.8.1：全局pytdx操作锁
_PYTDX_LOCK = threading.Lock()

# V2.9.2：pytdx全局熔断状态
_PYTDX_CB = {'fail_count': 0, 'cooldown_until': 0}
_PYTDX_CB_LOCK = threading.Lock()
_PYTDX_CB_THRESHOLD = 2
_PYTDX_CB_COOLDOWN = 60


def pytdx_is_circuit_open():
    """检查pytdx是否处于熔断冷却期"""
    with _PYTDX_CB_LOCK:
        if _PYTDX_CB['cooldown_until'] > time.time():
            return True
        if _PYTDX_CB['cooldown_until'] > 0:
            _PYTDX_CB['fail_count'] = 0
            _PYTDX_CB['cooldown_until'] = 0
    return False


def pytdx_record_result(success):
    """记录pytdx请求结果，触发熔断计数"""
    with _PYTDX_CB_LOCK:
        if success:
            _PYTDX_CB['fail_count'] = 0
            _PYTDX_CB['cooldown_until'] = 0
        else:
            _PYTDX_CB['fail_count'] += 1
            if _PYTDX_CB['fail_count'] >= _PYTDX_CB_THRESHOLD:
                _PYTDX_CB['cooldown_until'] = time.time() + _PYTDX_CB_COOLDOWN
                print('[pytdx熔断] 连续%d次空数据，熔断%d秒' % (_PYTDX_CB_THRESHOLD, _PYTDX_CB_COOLDOWN), flush=True)


def get_pytdx_circuit_status():
    """获取pytdx熔断状态"""
    with _PYTDX_CB_LOCK:
        return dict(_PYTDX_CB)


# 可用服务器列表（按优先级排序）
TDX_SERVERS = [
    ('180.153.18.170', 7709),
    ('119.147.212.81', 7709),
    ('112.74.214.43', 7709),
    ('221.231.141.60', 7709),
    ('101.227.73.20', 7709),
    ('101.227.77.254', 7709),
    ('14.17.75.10', 7709),
    ('59.173.18.140', 7709),
]


def get_tdx_api():
    """
    获取已连接的通达信API对象
    V2.9.2：全局熔断+单台超时2秒+总超时≤5秒+空数据快速失败
    Returns:
        TdxHq_API: 已连接的API对象，失败返回None
    """
    if pytdx_is_circuit_open():
        return None

    start_time = time.time()
    for host, port in TDX_SERVERS:
        if time.time() - start_time > 5:
            print('[pytdx] 总超时>5秒，停止尝试', flush=True)
            break
        try:
            api = TdxHq_API()
            if api.connect(host, port, time_out=2):
                data = api.get_security_bars(9, 0, '000001', 0, 3)
                if data:
                    pytdx_record_result(True)
                    return api
                api.disconnect()
                pytdx_record_result(False)
                return None
        except Exception:
            continue
    pytdx_record_result(False)
    return None


def get_daily_kline_tdx(code, count=80):
    """
    通过通达信获取日K线数据
    Args:
        code: 股票代码（6位）
        count: 获取数量
    Returns:
        list: [{'open':, 'close':, 'high':, 'low':, 'volume':}, ...]
    """
    return get_kline_tdx(code, count, period='day')


def get_kline_tdx(code, count=80, period='day'):
    """
    通过通达信获取K线数据（支持多周期）
    Args:
        code: 股票代码（6位）
        count: 获取数量
        period: 周期：'1min', '5min', '15min', '30min', '60min', 'day', 'week', 'month'
    Returns:
        list: [{'date':, 'open':, 'close':, 'high':, 'low':, 'volume':}, ...]
    """
    # 周期映射
    period_map = {
        '1min': 7,   # V2.8修复：1分钟K线
        '5min': 0,
        '15min': 1,
        '30min': 2,
        '60min': 3,
        'week': 5,
        'month': 6,
        'day': 4,    # V2.8修复：日K线（category=9会导致成交量小100倍）
    }

    category = period_map.get(period, 9)

    api = get_tdx_api()
    if not api:
        return []

    try:
        market = 1 if code.startswith(('6', '9')) else 0
        data = api.get_security_bars(category, market, code, 0, count)
        api.disconnect()

        if not data:
            return []

        return [{'date': d.get('datetime', d.get('date', '')),
                 'open': d['open'], 'close': d['close'],
                 'high': d['high'], 'low': d['low'],
                 'volume': d['vol']} for d in data]
    except Exception:
        try:
            api.disconnect()
        except Exception:
            pass
        return []


def get_minute_time_data_tdx(code):
    """
    通过通达信获取分时数据
    Args:
        code: 股票代码（6位）
    Returns:
        list: [{'time':, 'price':, 'volume':, 'avg_price':}, ...]
    """
    api = get_tdx_api()
    if not api:
        return []

    try:
        market = 1 if code.startswith(('6', '9')) else 0
        data = api.get_minute_time_data(market, code)
        api.disconnect()

        if not data:
            return []

        result = []
        total_volume = 0
        total_amount = 0

        for i, d in enumerate(data):
            price = float(d.get('price', 0))
            volume = int(d.get('vol', 0))

            total_volume += volume
            total_amount += price * volume

            avg_price = total_amount / total_volume if total_volume > 0 else price

            # 计算时间（9:30开始，每分钟一条）
            hour = 9 + (30 + i) // 60
            minute = (30 + i) % 60
            time_str = f"{hour:02d}:{minute:02d}"

            # 午休处理（11:30-13:00）
            if hour == 11 and minute > 30:
                # 下午开盘
                hour = 13
                minute = minute - 31
                time_str = f"{hour:02d}:{minute:02d}"

            result.append({
                'time': time_str,
                'price': price,
                'volume': volume,
                'avg_price': avg_price
            })

        return result
    except Exception as e:
        print(f"获取分时数据出错: {e}")
        try:
            api.disconnect()
        except Exception:
            pass
        return []


def get_stock_list_tdx():
    """
    通过通达信获取股票列表
    Returns:
        list: [{'code':, 'name':}, ...]
    """
    api = get_tdx_api()
    if not api:
        return []

    all_stocks = []
    try:
        # 沪市
        for start in range(0, 3000, 1000):
            data = api.get_security_list(1, start)
            if not data:
                break
            for s in data:
                code = s.get('code', '')
                name = s.get('name', '')
                if code and len(code) == 6 and code.startswith(('600', '601', '603', '605')):
                    all_stocks.append({'code': code, 'name': name})

        # 深市
        for start in range(0, 3000, 1000):
            data = api.get_security_list(0, start)
            if not data:
                break
            for s in data:
                code = s.get('code', '')
                name = s.get('name', '')
                if code and len(code) == 6 and code.startswith(('000', '001', '002', '003')):
                    all_stocks.append({'code': code, 'name': name})

        api.disconnect()
    except Exception:
        try:
            api.disconnect()
        except Exception:
            pass

    return all_stocks
