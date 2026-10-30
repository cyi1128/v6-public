# -*- coding: utf-8 -*-
"""
大盘指数监控和板块强弱分析
"""
import requests
import time
from utils.indicators import calc_kdj_series, calc_macd_series


class MarketAnalyzer:
    """大盘分析器"""

    # 主要指数代码（腾讯财经）
    INDEX_CODES = {
        'sh': {'code': 'sh000001', 'name': '上证指数'},
        'sz': {'code': 'sz399001', 'name': '深证成指'},
        'cyb': {'code': 'sz399006', 'name': '创业板指'},
    }

    def get_index_quotes(self):
        """获取主要指数实时行情"""
        results = []
        try:
            codes = ','.join([v['code'] for v in self.INDEX_CODES.values()])
            url = f'https://qt.gtimg.cn/q={codes}'
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, headers=headers, timeout=5)
            resp.encoding = 'gbk'

            for line in resp.text.strip().split(';'):
                if not line or '=' not in line:
                    continue
                parts = line.split('"')
                if len(parts) < 2:
                    continue
                data = parts[1].split('~')
                if len(data) < 35:
                    continue

                name = data[1]
                code = data[2]
                price = float(data[3]) if data[3] else 0
                prev_close = float(data[4]) if data[4] else 0
                pct_chg = float(data[32]) if data[32] else 0
                volume = float(data[36]) if len(data) > 36 and data[36] else 0
                amount = float(data[37]) if len(data) > 37 and data[37] else 0

                results.append({
                    'name': name,
                    'code': code,
                    'price': price,
                    'prev_close': prev_close,
                    'pct_chg': pct_chg,
                    'volume': volume,
                    'amount': amount,
                })
        except Exception as e:
            print(f"获取指数行情失败: {e}")

        return results

    def get_market_sentiment(self, index_quotes):
        """计算市场情绪"""
        if not index_quotes:
            return '未知'

        # 简单情绪判断：根据三大指数涨跌
        up_count = sum(1 for idx in index_quotes if idx['pct_chg'] > 0)
        avg_pct = sum(idx['pct_chg'] for idx in index_quotes) / len(index_quotes)

        if up_count >= 2 and avg_pct > 1:
            return '强势'
        elif up_count >= 2 and avg_pct > 0:
            return '偏强'
        elif up_count <= 1 and avg_pct < -1:
            return '弱势'
        elif up_count <= 1 and avg_pct < 0:
            return '偏弱'
        else:
            return '震荡'


class SectorAnalyzer:
    """板块强弱分析器"""

    def get_sector_ranking(self):
        """
        获取行业板块涨幅排名
        使用东方财富板块数据
        注意：重试/缓存/降级逻辑在resonance_signals.py层处理，这里只做单次请求
        """
        sectors = []
        try:
            url = 'https://push2delay.eastmoney.com/api/qt/clist/get'
            params = {
                'pn': 1,
                'pz': 50,
                'po': 1,
                'np': 1,
                'fltt': 2,
                'invt': 2,
                'fid': 'f3',
                'fs': 'm:90+t:2',  # 行业板块
                'fields': 'f2,f3,f4,f8,f12,f14,f20,f21,f62,f128,f136,f152',
            }
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://quote.eastmoney.com/',
                'Accept': 'application/json, text/plain, */*',
            }
            resp = requests.get(url, params=params, headers=headers, timeout=3)
            data = resp.json()

            if data.get('data') and data['data'].get('diff'):
                for item in data['data']['diff']:
                    sectors.append({
                        'code': item.get('f12', ''),
                        'name': item.get('f14', ''),
                        'price': item.get('f2', 0),
                        'pct_chg': item.get('f3', 0),
                        'change': item.get('f4', 0),
                        'turnover': item.get('f8', 0),
                        'volume': item.get('f20', 0),
                        'amount': item.get('f21', 0),
                        'net_inflow': item.get('f62', 0),
                        'up_count': item.get('f128', 0),
                        'down_count': item.get('f136', 0),
                        'leader': item.get('f152', ''),
                    })
        except Exception as e:
            # 静默失败，由上层resonance_signals.py处理重试和降级
            pass
        return sectors

    def get_top10_sectors(self, sectors):
        """获取强势板块TOP10"""
        sorted_sectors = sorted(sectors, key=lambda x: x.get('pct_chg', 0), reverse=True)
        return sorted_sectors[:10]

    def get_weak10_sectors(self, sectors):
        """获取弱势板块TOP10"""
        sorted_sectors = sorted(sectors, key=lambda x: x.get('pct_chg', 0))
        return sorted_sectors[:10]


_market_analyzer = None
_sector_analyzer = None


def get_market_analyzer():
    global _market_analyzer
    if _market_analyzer is None:
        _market_analyzer = MarketAnalyzer()
    return _market_analyzer


def get_sector_analyzer():
    global _sector_analyzer
    if _sector_analyzer is None:
        _sector_analyzer = SectorAnalyzer()
    return _sector_analyzer
