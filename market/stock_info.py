"""
股票基本信息模块
获取主营业务、行业分类、市值、换手率等
基于腾讯财经、东方财富、新浪财经API
"""
import requests
import json
import time
from typing import Dict, List, Optional


class StockInfoProvider:
    """股票基本信息提供者"""

    def __init__(self):
        self._cache = {}  # 缓存 {ts_code: info}
        self._cache_time = {}  # 缓存时间
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        })

    def _convert_code_tencent(self, ts_code: str) -> str:
        """转换为腾讯财经代码格式"""
        if '.' in ts_code:
            code, market = ts_code.split('.')
            market = market.lower()
            return f'{market}{code}'
        return ts_code

    def get_stock_info(self, ts_code: str) -> Dict:
        """
        获取股票基本信息
        返回: {name, industry, main_business, total_market_cap, float_market_cap, pe, pb, turnover_rate, ...}
        """
        # 检查缓存（30分钟有效，因为市值和换手率会变化）
        if ts_code in self._cache:
            cache_time = self._cache_time.get(ts_code, 0)
            if time.time() - cache_time < 1800:
                return self._cache[ts_code]

        result = {
            'ts_code': ts_code,
            'name': '',
            'industry': '',
            'main_business': '',
            'total_market_cap': 0,
            'float_market_cap': 0,
            'pe': 0,
            'pb': 0,
            'roe': 0,
            'eps': 0,
            'total_share': 0,
            'float_share': 0,
            'turnover_rate': 0,
        }

        # 1. 使用腾讯财经API（最稳定，字段最全）
        try:
            tencent_code = self._convert_code_tencent(ts_code)
            url = f'https://qt.gtimg.cn/q={tencent_code}'
            resp = self.session.get(url, timeout=8)
            if resp.status_code == 200:
                text = resp.content.decode('gbk', errors='ignore')
                if '=' in text and '"' in text:
                    data_str = text.split('"')[1]
                    parts = data_str.split('~')
                    if len(parts) >= 50:
                        result['name'] = parts[1]  # 名称
                        # parts[3] 当前价, parts[4] 昨收, parts[5] 今开
                        # parts[6] 成交量(手)
                        # parts[38] 换手率
                        if len(parts) > 38 and parts[38]:
                            try:
                                result['turnover_rate'] = float(parts[38])
                            except:
                                pass
                        # parts[44] 总市值(亿), parts[45] 流通市值(亿)
                        if len(parts) > 44 and parts[44]:
                            try:
                                result['total_market_cap'] = float(parts[44])
                            except:
                                pass
                        if len(parts) > 45 and parts[45]:
                            try:
                                result['float_market_cap'] = float(parts[45])
                            except:
                                pass
                        # parts[46] 市净率PB
                        if len(parts) > 46 and parts[46]:
                            try:
                                result['pb'] = float(parts[46])
                            except:
                                pass
                        # parts[52] 市盈率(动), parts[53] 市盈率(静)
                        if len(parts) > 52 and parts[52]:
                            try:
                                result['pe'] = float(parts[52])
                            except:
                                pass
                        # parts[72] 总股本(股), parts[73] 流通股本(股)
                        if len(parts) > 72 and parts[72]:
                            try:
                                result['total_share'] = float(parts[72])
                            except:
                                pass
                        if len(parts) > 73 and parts[73]:
                            try:
                                result['float_share'] = float(parts[73])
                            except:
                                pass
        except Exception as e:
            pass

        # 2. 使用东方财富API补充行业和主营业务（快速超时）
        if not result['industry'] or not result['main_business']:
            try:
                code_plain = ts_code.replace('.', '')
                url = f'https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/PageAjax?code={code_plain}'
                resp = self.session.get(url, timeout=3)
                if resp.status_code == 200:
                    data = resp.json()
                    jbzl = data.get('jbzl', [])
                    if jbzl and isinstance(jbzl, list) and len(jbzl) > 0:
                        info = jbzl[0]
                        result['industry'] = info.get('EM2016', '') or info.get('INDUSTRY', '')
                        result['main_business'] = info.get('BUSINESS_SCOPE', '') or info.get('MAIN_BUSINESS', '')
            except:
                pass

        # 3. 如果还是没有行业，使用东方财富行情API
        if not result['industry']:
            try:
                from market.providers.tdx_provider import TDXProvider
                # 不在这里调用，避免循环依赖
                pass
            except:
                pass

        # 缓存
        self._cache[ts_code] = result
        self._cache_time[ts_code] = time.time()

        return result

    def get_main_business(self, ts_code: str) -> str:
        """获取主营业务"""
        info = self.get_stock_info(ts_code)
        return info.get('main_business', '')

    def get_industry(self, ts_code: str) -> str:
        """获取所属行业"""
        info = self.get_stock_info(ts_code)
        return info.get('industry', '')

    def get_turnover_rate(self, ts_code: str) -> float:
        """获取换手率"""
        info = self.get_stock_info(ts_code)
        return info.get('turnover_rate', 0)

    def batch_get_info(self, ts_codes: List[str]) -> Dict[str, Dict]:
        """批量获取股票信息"""
        result = {}
        for code in ts_codes:
            result[code] = self.get_stock_info(code)
            time.sleep(0.1)  # 避免请求过快
        return result


# 全局单例
_stock_info_provider = None


def get_stock_info_provider() -> StockInfoProvider:
    global _stock_info_provider
    if _stock_info_provider is None:
        _stock_info_provider = StockInfoProvider()
    return _stock_info_provider
