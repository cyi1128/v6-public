# -*- coding: utf-8 -*-
"""
快速实时行情获取工具
使用腾讯财经API批量获取股票实时价格，速度快
"""
import requests
from typing import List, Dict, Optional


def get_realtime_prices_tencent(codes: List[str]) -> Dict[str, Dict]:
    """
    通过腾讯财经API批量获取实时行情（快速版）

    Args:
        codes: 股票代码列表，如 ['000001', '600000'] 或 ['000001.SZ', '600000.SH']

    Returns:
        {code: {'price':, 'change':, 'name':, 'volume':, 'amount':}, ...}
    """
    if not codes:
        return {}

    # 转换代码格式
    tencent_codes = []
    code_map = {}
    for code in codes:
        if '.' in code:
            # 000001.SZ -> sz000001
            parts = code.split('.')
            market = parts[1].lower()
            pure_code = parts[0]
        else:
            pure_code = code
            if code.startswith(('6', '9')):
                market = 'sh'
            else:
                market = 'sz'
        tencent_code = f"{market}{pure_code}"
        tencent_codes.append(tencent_code)
        code_map[tencent_code] = pure_code

    result = {}

    # 分批获取，每批最多80只
    try:
        for i in range(0, len(tencent_codes), 80):
            batch = tencent_codes[i:i+80]
            codes_str = ','.join(batch)
            url = f"https://qt.gtimg.cn/q={codes_str}"

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                continue

            text = resp.content.decode('gbk', errors='ignore')
            lines = text.strip().split(';')

            for line in lines:
                line = line.strip()
                if not line or '=' not in line:
                    continue

                try:
                    # v_sz000001="1~平安银行~000001~11.26~..."
                    key_part, value_part = line.split('=', 1)
                    tencent_code = key_part.replace('v_', '').strip()
                    value_part = value_part.strip().strip('"')

                    if not value_part:
                        continue

                    parts = value_part.split('~')
                    if len(parts) < 35:
                        continue

                    pure_code = code_map.get(tencent_code, tencent_code[2:])
                    name = parts[1]
                    price = float(parts[3]) if parts[3] else 0
                    last_close = float(parts[4]) if parts[4] else 0
                    open_price = float(parts[5]) if parts[5] else 0
                    volume = float(parts[6]) if parts[6] else 0  # 手
                    amount = float(parts[37]) if len(parts) > 37 and parts[37] else 0  # 万
                    high = float(parts[33]) if len(parts) > 33 and parts[33] else 0
                    low = float(parts[34]) if len(parts) > 34 and parts[34] else 0

                    pct_chg = 0
                    if last_close > 0:
                        pct_chg = round((price - last_close) / last_close * 100, 2)

                    # 换手率（parts[38]）
                    turnover = float(parts[38]) if len(parts) > 38 and parts[38] else 0
                    # 流通市值（亿元，parts[44]）
                    float_mv = float(parts[44]) if len(parts) > 44 and parts[44] else 0
                    # 总市值（亿元，parts[45]）
                    total_mv = float(parts[45]) if len(parts) > 45 and parts[45] else 0

                    result[pure_code] = {
                        'code': pure_code,
                        'name': name,
                        'price': price,
                        'last_close': last_close,
                        'open': open_price,
                        'high': high,
                        'low': low,
                        'volume': volume,
                        'amount': amount,
                        'pct_chg': pct_chg,
                        'change': pct_chg,
                        'turnover': turnover,
                        'market_cap': total_mv,  # 单位：亿元
                        'float_mv': float_mv,    # 单位：亿元
                    }
                except Exception:
                    continue
    except Exception:
        pass

    return result


def get_realtime_quotes_list(codes: List[str]) -> List[Dict]:
    """
    获取实时行情列表（兼容scheduler格式）

    Args:
        codes: 股票代码列表

    Returns:
        行情列表，格式与tdx_provider一致
    """
    price_dict = get_realtime_prices_tencent(codes)
    result = []
    for code, data in price_dict.items():
        result.append({
            'ts_code': code,
            'name': data['name'],
            'price': data['price'],
            'last_close': data['last_close'],
            'open': data['open'],
            'high': data['high'],
            'low': data['low'],
            'volume': data['volume'],
            'amount': data['amount'],
            'pct_chg': data['pct_chg'],
            'turnover_rate': 0,
            'total_market_cap': 0,
            'float_market_cap': 0,
        })
    return result
