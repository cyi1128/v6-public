# -*- coding: utf-8 -*-
"""
今日涨停股票获取
通过东方财富涨停板接口获取涨停个股及涨停原因
"""
import requests
import datetime


def get_today_limit_up_stocks():
    """
    获取今日涨停股票列表（东方财富接口）
    Returns:
        list: [{'code':, 'name':, 'price':, 'pct_chg':, 'turnover':, 'industry':, 'reason':}, ...]
    """
    today = datetime.datetime.now().strftime('%Y%m%d')
    url = f'http://push2ex.eastmoney.com/getTopicZTPool?ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt&Pageindex=0&pagesize=200&sort=fbt:asc&date={today}'

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'http://quote.eastmoney.com/',
        }
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()

        if data.get('data') and data['data'].get('pool'):
            pool = data['data']['pool']
            results = []
            for item in pool:
                code = item.get('c', '')  # 代码
                name = item.get('n', '')  # 名称
                price = item.get('p', 0)  # 现价
                pct_chg = item.get('zdp', 0)  # 涨跌幅
                turnover = item.get('hs', 0)  # 换手率
                amount = item.get('amount', 0)  # 成交额
                reason = item.get('hybk', '')  # 行业板块/涨停原因
                lbc = item.get('lbc', 0)  # 连板数
                fbt = item.get('fbt', 0)  # 首次封板时间
                lbt = item.get('lbt', 0)  # 最后封板时间
                fund = item.get('fund', 0)  # 封单金额
                zbc = item.get('zbc', 0)  # 炸板次数
                ltsz = item.get('ltsz', 0)  # 流通市值

                # 格式化价格（东方财富返回的价格可能需要除以1000）
                if price > 1000:
                    price = price / 1000

                # 格式化封板时间 92500 -> "09:25:00"
                def _format_time(t):
                    if not t:
                        return ''
                    s = str(t).zfill(6)
                    return f"{s[:2]}:{s[2:4]}:{s[4:6]}"

                results.append({
                    'code': code,
                    'name': name,
                    'price': round(price, 2),
                    'pct_chg': round(pct_chg, 2),
                    'turnover': round(turnover, 2),
                    'amount': amount,
                    'industry': reason,
                    'reason': reason,
                    'lbc': lbc,
                    'pool': '今日涨停',
                    # 涨停强度新增字段
                    'first_limit_time': _format_time(fbt),
                    'last_limit_time': _format_time(lbt),
                    'seal_amount': fund,
                    'break_count': zbc,
                    'float_market_cap': ltsz,
                })
            return results
    except Exception as e:
        print(f"获取涨停股票失败: {e}")

    return []


def get_limit_up_reason(code):
    """
    获取单只股票涨停原因（备用）
    """
    return ''
