# -*- coding: utf-8 -*-
"""
独立K线获取工具 - pytdx在线（主）+ 腾讯财经（备）+ 新浪财经（第三备）
不依赖通达信本地数据文件，全部使用在线接口获取最新日K线数据。
"""
import json
import os
import requests
import time
import threading
from datetime import datetime
from typing import List, Dict, Optional

# V2.8.1：全局pytdx操作锁，防止多线程竞争导致WinError 10038和进程崩溃
_PYTDX_LOCK = threading.Lock()

# pytdx在线服务器列表（按优先级排序）
PYTDX_SERVERS = [
    ('180.153.18.170', 7709),
    ('119.147.212.81', 7709),
    ('221.231.141.60', 7709),
    ('101.227.73.20', 7709),
    ('14.17.75.11', 7709),
]


def _get_pytdx_market(code: str) -> int:
    """根据股票代码判断pytdx市场：0=深市，1=沪市"""
    code = code.strip()
    if code.startswith(('60', '68', '9', '11', '13')):
        return 1  # 沪市
    return 0  # 深市


def _fetch_kline_pytdx_internal(code: str, days: int = 300) -> Optional[List[Dict]]:
    """
    从pytdx在线服务器获取日K线数据

    Args:
        code: 股票代码（如000001、600000）
        days: 获取最近N根K线

    Returns:
        List[Dict]，每根K线包含：date, open, close, high, low, volume
        失败返回None
    """
    try:
        from pytdx.hq import TdxHq_API
    except ImportError:
        print(f"[KLINE PYTDX] {code} pytdx未安装", flush=True)
        return None

    market = _get_pytdx_market(code)
    api = TdxHq_API()

    last_error = None
    for host, port in PYTDX_SERVERS:
        try:
            if not api.connect(host, port, time_out=5):
                last_error = f"连接{host}:{port}失败"
                continue

            # pytdx的get_security_bars最多一次返回800根
            # category=4 日K, market=0深市/1沪市
            count = min(days, 800)
            bars = api.get_security_bars(
                category=4, market=market, code=code, start=0, count=count
            )

            if bars and len(bars) > 0:
                result = []
                for bar in bars:
                    try:
                        year = bar.get('year', 0)
                        month = bar.get('month', 0)
                        day = bar.get('day', 0)
                        if year > 0 and month > 0 and day > 0:
                            date_str = f"{year}-{month:02d}-{day:02d}"
                        else:
                            dt = bar.get('datetime', '')
                            date_str = str(dt)[:10] if dt else ''

                        result.append({
                            "date": date_str,
                            "open": float(bar.get('open', 0)),
                            "close": float(bar.get('close', 0)),
                            "high": float(bar.get('high', 0)),
                            "low": float(bar.get('low', 0)),
                            "volume": float(bar.get('vol', 0)),  # 手
                        })
                    except (ValueError, TypeError):
                        continue

                api.disconnect()
                if result:
                    print(f"[KLINE PYTDX] {code} pytdx在线获取成功: {len(result)}根, 最新={result[-1].get('date','')}", flush=True)
                    return result[-days:] if len(result) > days else result
                last_error = "解析后无有效K线"
            else:
                last_error = "返回空数据"
                api.disconnect()
                # V2.9.0：服务器可连但无数据返回（已失效服务器），
                # 立即降级HTTP源，避免逐个服务器超时（约20s/只）
                print(f"[KLINE PYTDX] {code} 服务器{host}可连但无数据，快速降级HTTP源", flush=True)
                return None

        except Exception as e:
            last_error = f"{host}:{port} 异常: {e}"
            try:
                api.disconnect()
            except Exception:
                pass
            continue

    print(f"[KLINE PYTDX] {code} pytdx在线获取失败: {last_error}", flush=True)
    return None


def fetch_kline_pytdx(code: str, days: int = 300) -> Optional[List[Dict]]:
    """
    从pytdx在线服务器获取日K线数据（线程安全版本）
    V2.8.1：添加全局线程锁保护，防止多线程竞争导致WinError 10038和进程崩溃
    """
    with _PYTDX_LOCK:
        return _fetch_kline_pytdx_internal(code, days)


class _WafBlockedFetcherError(Exception):
    """腾讯WAF拦截（501），重试无意义，立即切换数据源"""


def _get_prefix(code: str) -> str:
    """根据股票代码生成前缀：沪市sh，深市sz"""
    code = code.strip()
    return 'sh' if code.startswith(('60', '68', '9', '11', '13')) else 'sz'


def fetch_kline_tencent(code: str, days: int = 300, timeout: int = 10) -> Optional[List[Dict]]:
    """
    从腾讯财经获取日K线数据（前复权）

    Args:
        code: 股票代码（如000001、600000）
        days: 获取最近N根K线
        timeout: 请求超时秒数

    Returns:
        List[Dict]，每根K线包含：date, open, close, high, low, volume
        失败返回None
    """
    symbol = f"{_get_prefix(code)}{code}"
    # V2.9.5修复（2026-09-18实测）：fqkline/get 必须使用 web.ifzq.gtimg.cn 前缀，
    # 无前缀 ifzq.gtimg.cn 实测返回 HTTP 501 Not Implemented（V2.9.4改反了，已回正）
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,{days},qfq"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://gu.qq.com/",
    }

    last_error = None
    for attempt in range(2):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            # 【V2.9.6修复】腾讯WAF 501（waf.tencent.com挑战页）：重试无意义，立即失败切新浪
            if resp.status_code == 501 and 'waf.tencent' in resp.text:
                raise _WafBlockedFetcherError(code)
            resp.raise_for_status()
            data = resp.json()

            kline_data = data.get('data', {}).get(symbol, {})
            # 腾讯返回 qfqday（前复权）或 day（不复权）
            klines = kline_data.get('qfqday') or kline_data.get('day') or []

            if not klines:
                last_error = f"klines为空, keys={list(kline_data.keys())}"
                continue

            result = []
            for line in klines:
                if len(line) < 6:
                    continue
                try:
                    # 腾讯格式: [日期, 开盘, 收盘, 最高, 最低, 成交量]
                    result.append({
                        "date": str(line[0]),           # 日期 YYYY-MM-DD
                        "open": float(line[1]),         # 开盘
                        "close": float(line[2]),        # 收盘
                        "high": float(line[3]),         # 最高
                        "low": float(line[4]),          # 最低
                        "volume": float(line[5]) * 100,  # 成交量：手→股（×100），与缓存单位一致
                    })
                except (ValueError, IndexError):
                    continue

            if result:
                return result
            last_error = "解析后无有效K线"

        except requests.exceptions.Timeout:
            last_error = "请求超时"
        except requests.exceptions.RequestException as e:
            last_error = f"请求异常: {e}"
        except Exception as e:
            last_error = f"解析异常: {e}"

        if attempt < 1:
            time.sleep(0.8)

    print(f"[KLINE TX] {code} 腾讯财经获取失败: {last_error}", flush=True)
    return None


def fetch_kline_sina(code: str, days: int = 300, timeout: int = 10) -> Optional[List[Dict]]:
    """
    从新浪财经获取日K线数据（备用接口）

    Args:
        code: 股票代码
        days: 获取最近N根K线
        timeout: 请求超时秒数

    Returns:
        List[Dict]，失败返回None
    """
    symbol = f"{_get_prefix(code)}{code}"
    # 【V2.9.6修复】新浪有两个K线域名：
    #  - money.finance.sina.com.cn/json_v2.php：2026-09-18 实测被限流（HTTP 456）
    #  - quotes.sina.cn/cn/api/jsonp_v2.php：实测 200 可用（返回 JSONP，需剥壳）
    datelen = max(days, 10)
    url = f"https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_=/CN_MarketDataService.getKLineData?symbol={symbol}&scale=240&ma=no&datalen={datelen}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://finance.sina.com.cn/",
    }

    last_error = None
    for attempt in range(2):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            import json
            # JSONP 剥壳: /*...*/ var _=([...]);
            _t = resp.text
            _start = _t.find('([')
            _end = _t.rfind('])')
            if _start < 0 or _end < 0:
                last_error = "JSONP格式异常"
                continue
            data = json.loads(_t[_start + 1:_end + 1])

            if not data or not isinstance(data, list):
                last_error = "返回数据格式错误"
                continue

            result = []
            for item in data:
                try:
                    result.append({
                        "date": str(item.get('day', '')),
                        "open": float(item.get('open', 0)),
                        "close": float(item.get('close', 0)),
                        "high": float(item.get('high', 0)),
                        "low": float(item.get('low', 0)),
                        "volume": float(item.get('volume', 0)),
                    })
                except (ValueError, TypeError):
                    continue

            if result:
                # 只取最近days根
                return result[-days:] if len(result) > days else result
            last_error = "解析后无有效K线"

        except requests.exceptions.Timeout:
            last_error = "请求超时"
        except requests.exceptions.RequestException as e:
            last_error = f"请求异常: {e}"
        except Exception as e:
            last_error = f"解析异常: {e}"

        if attempt < 1:
            time.sleep(0.8)

    print(f"[KLINE SINA] {code} 新浪财经获取失败: {last_error}", flush=True)
    return None


def fetch_kline_eastmoney(code: str, days: int = 300, timeout: int = 10) -> Optional[List[Dict]]:
    """
    东方财富K线接口（保留作为第三备用，当前网络环境下不稳定）
    """
    # 沪市1.代码，深市0.代码
    secid = f"1.{code}" if code.startswith(('60', '68', '9')) else f"0.{code}"
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "1",
        "end": "20500101",
        "lmt": str(days),
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://quote.eastmoney.com/",
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        klines = data.get("data", {}).get("klines", [])
        if not klines:
            return None
        result = []
        for line in klines:
            parts = line.split(",")
            if len(parts) < 7:
                continue
            try:
                result.append({
                    "date": parts[0],
                    "open": float(parts[1]),
                    "close": float(parts[2]),
                    "high": float(parts[3]),
                    "low": float(parts[4]),
                    "volume": float(parts[5]) * 100,  # 手→股
                })
            except (ValueError, IndexError):
                continue
        return result if result else None
    except Exception as e:
        print(f"[KLINE EM] {code} 东方财富获取失败: {e}", flush=True)
        return None


_TODAY_EXPECT = {'key': None, 'val': True}


def _kline_last_date(kline) -> str:
    """取最后一根K线的日期，统一成 YYYY-MM-DD；取不到返回空串"""
    if not kline:
        return ''
    d = str(kline[-1].get('date', '')).strip()
    if len(d) == 8 and d.isdigit():
        d = '%s-%s-%s' % (d[:4], d[4:6], d[6:8])
    return d


def _today_bar_expected() -> bool:
    """今天是否「本该」已有当日K线：工作日 + 不在休市表里 + 已过 09:30。
    结果按分钟缓存，避免批量拉取时反复读文件。"""
    now = datetime.now()
    key = now.strftime('%Y-%m-%d %H:%M')
    if _TODAY_EXPECT.get('key') == key:
        return _TODAY_EXPECT['val']
    val = True
    if now.weekday() >= 5:
        val = False
    elif (now.hour, now.minute) < (9, 30):
        val = False
    else:
        try:
            p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'data', 'market_holidays.json')
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    js = json.load(f)
                hols = set(js.get('holidays') or []) if isinstance(js, dict) else set(js or [])
                if now.strftime('%Y-%m-%d') in hols:
                    val = False
        except Exception:
            pass
    _TODAY_EXPECT['key'] = key
    _TODAY_EXPECT['val'] = val
    return val


def fetch_kline(code: str, days: int = 300) -> Optional[List[Dict]]:
    """
    统一K线获取入口：pytdx在线 → 腾讯财经 → 新浪财经 → 东方财富
    不使用通达信本地数据文件，全部使用在线接口。

    V2.9.7（2026-10-12）：改为「新鲜度优先」。
    实测盘中（2026-10-12 13:44）：pytdx 服务器可连但无数据；新浪日线末根只到
    2026-10-09（不含当天未收盘bar）；腾讯 fqkline 末根已是 2026-10-12。
    旧顺序把新浪排在腾讯前面且「够根数就返回」，导致盘中永远拿不到当天的 bar ——
    K线缓存与控盘选股的数据日因此一直停在上一交易日。
    现在：优先返回「末根=今天」的那一份；都不够新时才退回「末根<今天」的那一份。
    非交易日 / 开盘前不做这种追求，保持一次命中即返回，不额外多发请求。

    Args:
        code: 股票代码
        days: 获取最近N根K线

    Returns:
        List[Dict]，失败返回None
    """
    need = min(days, 20)
    today = datetime.now().strftime('%Y-%m-%d')
    expect_today = _today_bar_expected()
    fallback = None

    for fetcher in (fetch_kline_pytdx, fetch_kline_tencent,
                    fetch_kline_sina, fetch_kline_eastmoney):
        try:
            kline = fetcher(code, days=days)
        except Exception:
            kline = None
        if not kline or len(kline) < need:
            continue
        if not expect_today or _kline_last_date(kline) >= today:
            return kline            # 已含今天（或今天本来就不该有）→ 直接用
        if fallback is None:
            fallback = kline        # 记下第一份「能用但不够新」的

    return fallback


if __name__ == "__main__":
    # 测试
    for code in ["000001", "600000", "002594"]:
        kline = fetch_kline(code, days=10)
        if kline:
            print(f"{code}: 成功 {len(kline)}根, 最新={kline[-1]['date']}, 源=腾讯/新浪/东方财富")
        else:
            print(f"{code}: 全部接口失败")
        time.sleep(0.5)
