# -*- coding: utf-8 -*-
"""
财务数据服务 - 营利拆解
数据源：东方财富 datacenter API (RPT_F10_FINANCE_MAINFINADATA)
支持当日缓存、超时控制、异常捕获
"""
import os
import json
import urllib.request
import urllib.parse
import ssl
from datetime import datetime

# 项目根目录
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(_PROJECT_ROOT, 'data', 'cache', 'profit_breakdown')

# SSL上下文（忽略证书验证，兼容部分环境）
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

# 请求头
_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://emweb.securities.eastmoney.com/',
    'Accept': 'application/json, text/plain, */*',
}


def _format_yi(value):
    """将数值格式化为亿单位字符串"""
    if value is None:
        return '--'
    try:
        v = float(value)
    except (TypeError, ValueError):
        return '--'
    if abs(v) >= 1e8:
        return f'{v / 1e8:.2f}亿'
    elif abs(v) >= 1e4:
        return f'{v / 1e4:.2f}万'
    else:
        return f'{v:.2f}'


def _format_pct(value, signed=True):
    """将百分比数值格式化为字符串"""
    if value is None:
        return '--'
    try:
        v = float(value)
    except (TypeError, ValueError):
        return '--'
    if signed:
        return f'{v:+.2f}%'
    return f'{v:.2f}%'


def _code_to_secucode(code6):
    """6位股票代码转为东方财富 SECUCODE 格式（如 600172.SH）"""
    code6 = str(code6).strip()
    if code6.startswith(('6', '9')):
        return f'{code6}.SH'
    elif code6.startswith(('0', '2', '3')):
        return f'{code6}.SZ'
    elif code6.startswith(('4', '8')):
        return f'{code6}.BJ'
    return f'{code6}.SH'


def fetch_profit_breakdown(code6, timeout=10):
    """
    获取股票营利拆解数据（营业收入、归母净利润、毛利率、净利率等）

    数据源：东方财富 datacenter API
    接口：https://datacenter.eastmoney.com/securities/api/data/v1/get
          ?reportName=RPT_F10_FINANCE_MAINFINADATA

    当日缓存：data/cache/profit_breakdown/{code6}_{YYYYMMDD}.json

    Args:
        code6: 6位股票代码（如 '600172'）
        timeout: 网络超时秒数

    Returns:
        dict: 营利拆解数据，结构如下：
        {
            'period': '2026中报',           # 本期报告期名称
            'prev_period': '2026一季报',     # 上期报告期名称
            'revenue': '8.07亿',             # 营业收入-本期
            'revenue_yoy': '+15.48%',        # 营业收入-同比
            'revenue_prev': '3.95亿',        # 营业收入-上期
            'rev_yoy_cur': '+15.48%',        # 营收同比-本期
            'rev_yoy_prev': '+23.63%',       # 营收同比-上期
            'net_profit': '-2.22亿',          # 归母净利润-本期
            'net_profit_yoy': '+25.74%',     # 归母净利润-同比
            'net_profit_prev': '-0.97亿',    # 归母净利润-上期
            'np_yoy_cur': '+25.74%',         # 净利润同比-本期
            'np_yoy_prev': '+42.34%',        # 净利润同比-上期
            'gross_margin': '16.02%',        # 毛利率-本期
            'gross_margin_chg': '+3.89pp',   # 毛利率-同比变化(百分点)
            'gross_margin_prev': '12.13%',   # 毛利率-上期
            'net_margin': '-28.72%',         # 净利率-本期
            'net_margin_chg': '-4.71pp',     # 净利率-同比变化(百分点)
            'net_margin_prev': '-24.01%',    # 净利率-上期
        }
        失败或无数据时返回空 dict {}
    """
    code6 = str(code6).strip()
    if not code6 or len(code6) < 6:
        return {}

    # 提取6位数字代码
    import re
    m = re.search(r'(\d{6})', code6)
    if not m:
        return {}
    code6 = m.group(1)

    # 1. 当日缓存
    today = datetime.now().strftime('%Y%m%d')
    cache_file = os.path.join(CACHE_DIR, f'{code6}_{today}.json')
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached = json.load(f)
            if isinstance(cached, dict):
                print(f'[营利拆解] {code6} 命中当日缓存', flush=True)
                return cached
        except Exception as e:
            print(f'[营利拆解] {code6} 缓存读取失败: {e}', flush=True)

    # 2. 构造请求
    secucode = _code_to_secucode(code6)
    params = {
        'reportName': 'RPT_F10_FINANCE_MAINFINADATA',
        'columns': 'ALL',
        'filter': f'(SECUCODE="{secucode}")',
        'pageNumber': '1',
        'pageSize': '8',
        'sortTypes': '-1',
        'sortColumns': 'REPORT_DATE',
    }
    url = 'https://datacenter.eastmoney.com/securities/api/data/v1/get?' + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, headers=_HEADERS)

    # 3. 发起请求
    try:
        resp = urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX)
        raw = resp.read().decode('utf-8-sig')
        data = json.loads(raw)
    except Exception as e:
        print(f'[营利拆解] {code6} 接口请求失败: {e}', flush=True)
        return {}

    # 4. 解析数据
    if not data.get('success'):
        print(f'[营利拆解] {code6} 接口返回失败: {data.get("message", "")}', flush=True)
        return {}

    result = data.get('result') or {}
    items = result.get('data') or []
    if not items or not isinstance(items, list):
        print(f'[营利拆解] {code6} 无财务数据', flush=True)
        return {}

    # 取最近两期
    cur = items[0]
    prev = items[1] if len(items) > 1 else {}

    def _get(item, key):
        """安全获取字段值"""
        v = item.get(key)
        if v is None or v == '':
            return None
        return v

    # 报告期
    period_name = str(_get(cur, 'REPORT_DATE_NAME') or '--')
    prev_period_name = str(_get(prev, 'REPORT_DATE_NAME') or '--')

    # 营业收入
    rev = _get(cur, 'TOTALOPERATEREVE')
    rev_yoy = _get(cur, 'TOTALOPERATEREVETZ')
    rev_prev = _get(prev, 'TOTALOPERATEREVE')
    rev_yoy_prev = _get(prev, 'TOTALOPERATEREVETZ')

    # 归母净利润
    np = _get(cur, 'PARENTNETPROFIT')
    np_yoy = _get(cur, 'PARENTNETPROFITTZ')
    np_prev = _get(prev, 'PARENTNETPROFIT')
    np_yoy_prev = _get(prev, 'PARENTNETPROFITTZ')

    # 毛利率
    gm = _get(cur, 'XSMLL')
    gm_prev = _get(prev, 'XSMLL')

    # 净利率
    nm = _get(cur, 'XSJLL')
    nm_prev = _get(prev, 'XSJLL')

    # 计算毛利率/净利率同比变化（百分点）
    gm_chg = '--'
    if gm is not None and gm_prev is not None:
        try:
            diff = float(gm) - float(gm_prev)
            gm_chg = f'{diff:+.2f}pp'
        except (TypeError, ValueError):
            pass

    nm_chg = '--'
    if nm is not None and nm_prev is not None:
        try:
            diff = float(nm) - float(nm_prev)
            nm_chg = f'{diff:+.2f}pp'
        except (TypeError, ValueError):
            pass

    # 组装结果
    result_dict = {
        'period': period_name,
        'prev_period': prev_period_name,
        # 营业收入
        'revenue': _format_yi(rev),
        'revenue_yoy': _format_pct(rev_yoy),
        'revenue_prev': _format_yi(rev_prev),
        # 营收同比
        'rev_yoy_cur': _format_pct(rev_yoy),
        'rev_yoy_prev': _format_pct(rev_yoy_prev),
        # 归母净利润
        'net_profit': _format_yi(np),
        'net_profit_yoy': _format_pct(np_yoy),
        'net_profit_prev': _format_yi(np_prev),
        # 净利润同比
        'np_yoy_cur': _format_pct(np_yoy),
        'np_yoy_prev': _format_pct(np_yoy_prev),
        # 毛利率
        'gross_margin': _format_pct(gm, signed=False),
        'gross_margin_chg': gm_chg,
        'gross_margin_prev': _format_pct(gm_prev, signed=False),
        # 净利率
        'net_margin': _format_pct(nm, signed=False),
        'net_margin_chg': nm_chg,
        'net_margin_prev': _format_pct(nm_prev, signed=False),
    }

    # 5. 写当日缓存
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(result_dict, f, ensure_ascii=False, indent=2)
        print(f'[营利拆解] {code6} 缓存已保存 ({period_name})', flush=True)
    except Exception as e:
        print(f'[营利拆解] {code6} 缓存写入失败: {e}', flush=True)

    return result_dict
