"""
市场行情数据模块
获取大盘指数、涨跌家数等真实行情数据
主数据源：东方财富
备用数据源：新浪财经
"""

import requests
import time
import json
from datetime import datetime


class MarketDataProvider:
    """市场行情数据提供者"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://quote.eastmoney.com/',
        })
        self._cache = {}
        self._cache_time = {}

    def _is_cache_valid(self, key, ttl=30):
        """检查缓存是否有效"""
        if key in self._cache_time:
            return time.time() - self._cache_time[key] < ttl
        return False

    def get_shanghai_index(self):
        """获取上证指数数据（点位、涨跌幅、涨跌家数）"""
        cache_key = 'sh_index'
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]

        try:
            # 东方财富接口
            url = 'http://push2delay.eastmoney.com/api/qt/stock/get'
            params = {
                'secid': '1.000001',  # 上证指数
                'fields': 'f43,f44,f45,f46,f47,f48,f50,f51,f52,f57,f58,f60,f107,f116,f117,f168,f169,f170',
                'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
            }
            response = self.session.get(url, params=params, timeout=5)
            data = response.json()

            if data.get('data'):
                d = data['data']
                # f43: 最新价, f170: 涨跌幅
                price = d.get('f43', 0) / 100 if d.get('f43') else 0
                pct_chg = d.get('f170', 0) / 100 if d.get('f170') else 0

                result = {
                    'name': '上证指数',
                    'price': price,
                    'pct_chg': pct_chg,
                    'change': price - (price / (1 + pct_chg / 100)) if pct_chg != 0 else 0,
                    'high': d.get('f44', 0) / 100 if d.get('f44') else 0,
                    'low': d.get('f45', 0) / 100 if d.get('f45') else 0,
                    'open': d.get('f46', 0) / 100 if d.get('f46') else 0,
                    'volume': d.get('f47', 0),
                    'amount': d.get('f48', 0),
                }

                # 获取涨跌家数
                count_data = self._get_sh_count()
                result.update(count_data)

                self._cache[cache_key] = result
                self._cache_time[cache_key] = time.time()
                return result

        except Exception as e:
            print(f"东方财富上证接口失败: {e}")

        # 备用：新浪财经
        try:
            url = 'https://hq.sinajs.cn/list=sh000001'
            response = self.session.get(url, timeout=5)
            text = response.text
            parts = text.split('"')[1].split(',')

            if len(parts) >= 4:
                price = float(parts[3])
                last_close = float(parts[2])
                pct_chg = ((price - last_close) / last_close * 100) if last_close > 0 else 0

                result = {
                    'name': '上证指数',
                    'price': price,
                    'pct_chg': pct_chg,
                    'change': price - last_close,
                    'high': float(parts[4]) if len(parts) > 4 else 0,
                    'low': float(parts[5]) if len(parts) > 5 else 0,
                    'open': float(parts[1]) if len(parts) > 1 else 0,
                    'volume': float(parts[8]) if len(parts) > 8 else 0,
                    'amount': float(parts[9]) if len(parts) > 9 else 0,
                    'up_count': 0,
                    'flat_count': 0,
                    'down_count': 0,
                }

                self._cache[cache_key] = result
                self._cache_time[cache_key] = time.time()
                return result

        except Exception as e:
            print(f"新浪上证接口失败: {e}")

        return None

    def _get_sh_count(self):
        """获取沪市涨跌家数
        从全市场行情数据统计涨(>0)/平(=0)/跌(<0)的家数。
        调用 utils.http_market_data.get_full_market_quotes_http() 获取全市场行情。
        获取失败返回全0并打印日志。
        """
        try:
            import sys
            import os
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if project_root not in sys.path:
                sys.path.insert(0, project_root)
            from utils.http_market_data import get_full_market_quotes_http

            # 获取全市场行情（仅沪市主板+科创板）
            quotes = get_full_market_quotes_http(main_board_only=False)
            if not quotes:
                print("[MarketData] 全市场行情获取为空，涨跌家数返回0", flush=True)
                return {'up_count': 0, 'flat_count': 0, 'down_count': 0}

            # 筛选沪市股票（60/68开头）并统计涨跌
            up = 0
            flat = 0
            down = 0
            for q in quotes:
                code = q.get('code', '')
                if not (code.startswith('60') or code.startswith('68')):
                    continue
                pct = q.get('pct_chg', 0)
                if pct > 0:
                    up += 1
                elif pct == 0:
                    flat += 1
                else:
                    down += 1

            return {
                'up_count': up,
                'flat_count': flat,
                'down_count': down,
            }
        except Exception as e:
            print(f"[MarketData] 获取涨跌家数失败: {e}", flush=True)
            return {
                'up_count': 0,
                'flat_count': 0,
                'down_count': 0,
            }

    def get_shenzhen_index(self):
        """获取深证成指数据"""
        cache_key = 'sz_index'
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]

        try:
            # 东方财富接口
            url = 'http://push2delay.eastmoney.com/api/qt/stock/get'
            params = {
                'secid': '0.399001',  # 深证成指
                'fields': 'f43,f44,f45,f46,f47,f48,f50,f51,f52,f57,f58,f60,f107,f116,f117,f168,f169,f170',
                'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
            }
            response = self.session.get(url, params=params, timeout=5)
            data = response.json()

            if data.get('data'):
                d = data['data']
                price = d.get('f43', 0) / 100 if d.get('f43') else 0
                pct_chg = d.get('f170', 0) / 100 if d.get('f170') else 0

                result = {
                    'name': '深证成指',
                    'price': price,
                    'pct_chg': pct_chg,
                    'change': price - (price / (1 + pct_chg / 100)) if pct_chg != 0 else 0,
                    'high': d.get('f44', 0) / 100 if d.get('f44') else 0,
                    'low': d.get('f45', 0) / 100 if d.get('f45') else 0,
                    'open': d.get('f46', 0) / 100 if d.get('f46') else 0,
                    'volume': d.get('f47', 0),
                    'amount': d.get('f48', 0),
                    'up_count': 0,
                    'flat_count': 0,
                    'down_count': 0,
                }

                self._cache[cache_key] = result
                self._cache_time[cache_key] = time.time()
                return result

        except Exception as e:
            print(f"东方财富深证接口失败: {e}")

        # 备用：新浪财经
        try:
            url = 'https://hq.sinajs.cn/list=sz399001'
            response = self.session.get(url, timeout=5)
            text = response.text
            parts = text.split('"')[1].split(',')

            if len(parts) >= 4:
                price = float(parts[3])
                last_close = float(parts[2])
                pct_chg = ((price - last_close) / last_close * 100) if last_close > 0 else 0

                result = {
                    'name': '深证成指',
                    'price': price,
                    'pct_chg': pct_chg,
                    'change': price - last_close,
                    'high': float(parts[4]) if len(parts) > 4 else 0,
                    'low': float(parts[5]) if len(parts) > 5 else 0,
                    'open': float(parts[1]) if len(parts) > 1 else 0,
                    'volume': float(parts[8]) if len(parts) > 8 else 0,
                    'amount': float(parts[9]) if len(parts) > 9 else 0,
                    'up_count': 0,
                    'flat_count': 0,
                    'down_count': 0,
                }

                self._cache[cache_key] = result
                self._cache_time[cache_key] = time.time()
                return result

        except Exception as e:
            print(f"新浪深证接口失败: {e}")

        return None

    def get_stock_sector_concept(self, code):
        """获取股票所属板块和概念"""
        cache_key = f'sector_{code}'
        if self._is_cache_valid(cache_key, ttl=3600):  # 缓存1小时
            return self._cache[cache_key]

        try:
            # 东方财富个股资料接口
            market = 'SH' if code.startswith('6') else 'SZ'
            url = f'https://emweb.securities.eastmoney.com/PC_HSF10/CoreConception/PageAjax?code={market}{code}'
            response = self.session.get(url, timeout=10)
            data = response.json()

            result = {
                'industry': '--',
                'sector': '--',
                'concepts': [],
            }

            # 所属行业
            if data.get('sshy') and len(data['sshy']) > 0:
                result['industry'] = data['sshy'][0].get('BOARD_NAME', '--')

            # 所属板块
            if data.get('bk') and len(data['bk']) > 0:
                sectors = [item.get('BOARD_NAME', '') for item in data['bk'][:3]]
                result['sector'] = '、'.join([s for s in sectors if s])

            # 概念题材
            if data.get('gn') and len(data['gn']) > 0:
                concepts = [item.get('BOARD_NAME', '') for item in data['gn'][:5]]
                result['concepts'] = [c for c in concepts if c]

            self._cache[cache_key] = result
            self._cache_time[cache_key] = time.time()
            return result

        except Exception as e:
            print(f"获取板块概念失败 {code}: {e}")

        return {
            'industry': '--',
            'sector': '--',
            'concepts': [],
        }

    def check_connection(self):
        """检查数据连接状态"""
        try:
            sh = self.get_shanghai_index()
            sz = self.get_shenzhen_index()
            if sh and sz:
                return {
                    'status': '正常',
                    'source': '东方财富/新浪财经',
                    'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                }
        except Exception as e:
            print(f"连接检查失败: {e}")

        return {
            'status': '异常',
            'source': '无',
            'last_update': '--',
        }


# 单例
_market_data_provider = None


def get_market_data_provider():
    global _market_data_provider
    if _market_data_provider is None:
        _market_data_provider = MarketDataProvider()
    return _market_data_provider
