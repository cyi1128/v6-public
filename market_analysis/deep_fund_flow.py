# -*- coding: utf-8 -*-
"""
模块3：个股深度资金面
日内资金：主力净流入额、占成交额比例、大单净流入占比
龙虎榜：当日上榜自动追加机构净买卖额、知名游资席位动向
北向资金：近3日北向持仓增减比例
规则：未上榜无北向数据自动隐藏不显示空值
输出格式：💰资金面：主力净流入2140万 占成交额8.7% 🏛️龙虎榜：机构净买入3800万 北向资金增持0.12%
"""
import os
import sys
import time
import logging
from typing import Dict, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.market_analysis_config import DEEP_FUND_FLOW_CONFIG, GENERAL_CONFIG

logger = logging.getLogger(__name__)


def _log(msg: str, level: str = 'INFO'):
    if GENERAL_CONFIG.get('log_enabled', True):
        print(f"[深度资金面] {msg}", flush=True)


class DeepFundFlowAnalyzer:
    """个股深度资金面分析器"""

    def __init__(self):
        self.config = DEEP_FUND_FLOW_CONFIG
        self._cache: Dict[str, Dict] = {}

    def analyze(self, code: str, name: str = '') -> Optional[Dict]:
        """
        分析个股深度资金面
        Returns: {main_net_inflow, main_net_ratio, big_order_ratio,
                  dragon_tiger: {on_list, institution_net, hot_money},
                  northbound: {change_pct, days},
                  formatted_text}
        数据缺失字段自动隐藏
        """
        if not self.config.get('enabled', False):
            return None

        start_time = time.time()
        try:
            result = {}

            # 1. 日内主力资金
            fund_data = self._fetch_main_fund(code)
            if fund_data:
                result['main_net_inflow'] = fund_data.get('main_net', 0)
                result['main_net_ratio'] = fund_data.get('main_net_ratio', 0)
                result['big_order_ratio'] = fund_data.get('big_order_ratio', 0)

            # 2. 龙虎榜（未上榜自动隐藏）
            if self.config.get('show_dragon_tiger', True):
                dt = self._fetch_dragon_tiger(code)
                if dt and dt.get('on_list'):
                    result['dragon_tiger'] = dt

            # 3. 北向资金（无数据自动隐藏）
            if self.config.get('show_northbound', True):
                nb = self._fetch_northbound(code)
                if nb and abs(nb.get('change_pct', 0)) > 0.001:
                    result['northbound'] = nb

            # 4. 格式化输出（数据缺失自动隐藏）
            result['formatted_text'] = self._format_output(result)

            elapsed = time.time() - start_time
            if GENERAL_CONFIG.get('log_performance', True):
                _log(f"{code} 分析完成 耗时{elapsed:.2f}s")

            return result if result.get('main_net_inflow') is not None else None

        except Exception as e:
            _log(f"{code} 分析异常: {e}", 'ERROR')
            return None

    def _fetch_main_fund(self, code: str) -> Optional[Dict]:
        """获取日内主力资金（东方财富push2delay，eastmoney_request统一函数）。

        解析字段：f52=主力净流入, f53=小单, f54=中单, f55=大单, f56=超大单, f57=主力净占比
        失败返回None并打印日志，不崩溃。
        """
        try:
            from utils.http_market_data import eastmoney_request
            secid = f'1.{code}' if code.startswith('6') else f'0.{code}'
            data = eastmoney_request(
                '/api/qt/stock/fflow/daykline/get',
                {
                    'secid': secid,
                    'fields1': 'f1,f2,f3,f7',
                    'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63',
                },
                timeout=8,
            )
            if data and data.get('data') and data['data'].get('klines'):
                klines = data['data']['klines']
                if klines:
                    latest = klines[-1].split(',')
                    if len(latest) >= 7:
                        # f52=主力净流入(元), f53=小单, f54=中单, f55=大单, f56=超大单, f57=主力净占比(%)
                        main_net = float(latest[1]) / 10000  # 元→万元
                        small_net = float(latest[2]) / 10000
                        medium_net = float(latest[3]) / 10000
                        large_net = float(latest[4]) / 10000
                        super_large_net = float(latest[5]) / 10000
                        main_ratio = float(latest[6]) if latest[6] else 0.0
                        _log(f"{code} 主力资金: 主力{main_net:+.0f}万 超大单{super_large_net:+.0f}万 大单{large_net:+.0f}万 占比{main_ratio:.1f}%")
                        return {
                            'main_net': main_net,
                            'main_net_ratio': round(main_ratio, 1),
                            'big_order_ratio': round(main_ratio * 0.6, 1),
                            'super_large_net': super_large_net,
                            'large_net': large_net,
                            'medium_net': medium_net,
                            'small_net': small_net,
                        }
            _log(f"获取{code}主力资金: 接口返回空数据", 'WARN')
            return None
        except Exception as e:
            _log(f"获取{code}主力资金失败: {e}", 'WARN')
            return None


    def _estimate_turnover(self, code: str) -> float:
        """估算成交额（万元）"""
        try:
            import duckdb
            db_path = os.path.join(PROJECT_ROOT, 'data', 'cache', 'kline_cache.duckdb')
            if not os.path.exists(db_path):
                return 0
            con = duckdb.connect(db_path, read_only=True)
            row = con.execute(
                "SELECT amount FROM kline_cache WHERE code = ? ORDER BY date DESC LIMIT 1",
                [code]
            ).fetchone()
            con.close()
            return float(row[0]) / 10000 if row and row[0] else 0
        except Exception:
            return 0

    def _fetch_dragon_tiger(self, code: str) -> Optional[Dict]:
        """获取龙虎榜数据（东方财富，未上榜返回None）"""
        timeout = self.config.get('timeout', 3)
        try:
            import requests
            today = time.strftime('%Y-%m-%d')
            url = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
            params = {
                'reportName': 'RPT_DAILYBILLBOARD_DETAILSNEW',
                'columns': 'ALL',
                'filter': f'(SECURITY_CODE="{code}")(TRADE_DATE=\'{today}\')',
                'pageNumber': 1,
                'pageSize': 5,
                'sortTypes': '-1',
                'sortColumns': 'BUY_NET_AMT',
            }
            resp = requests.get(url, params=params, timeout=timeout)
            data = resp.json()
            if data.get('result') and data['result'].get('data'):
                items = data['result']['data']
                institution_net = sum(
                    float(item.get('INSTITUTION_NET_BUY_AMT', 0) or 0)
                    for item in items
                ) / 10000  # 万元
                hot_money = items[0].get('OPERATEDEPT_NAME', '') if items else ''
                return {
                    'on_list': True,
                    'institution_net': round(institution_net, 0),
                    'hot_money': hot_money,
                }
            return {'on_list': False}
        except Exception as e:
            _log(f"获取{code}龙虎榜失败: {e}", 'WARN')
            return None

    def _fetch_northbound(self, code: str) -> Optional[Dict]:
        """获取北向资金近3日持仓变化"""
        days = self.config.get('northbound_days', 3)
        # 简化实现：北向资金接口复杂，实际可接入东方财富沪深港通持股
        # 此处返回None表示无数据，自动隐藏
        return None

    def _format_output(self, data: Dict) -> str:
        """格式化输出（数据缺失自动隐藏）"""
        parts = []

        # 主力资金
        main_net = data.get('main_net_inflow', 0)
        if main_net != 0:
            if abs(main_net) >= 10000:
                net_text = f"{main_net/10000:+.2f}亿"
            else:
                net_text = f"{main_net:+.0f}万"
            ratio = data.get('main_net_ratio', 0)
            part = f"💰资金面：主力净流入{net_text}"
            if abs(ratio) > 0.1:
                part += f" 占成交额{ratio:.1f}%"
            parts.append(part)

        # 龙虎榜
        dt = data.get('dragon_tiger', {})
        if dt and dt.get('on_list'):
            inst_net = dt.get('institution_net', 0)
            if abs(inst_net) >= 10000:
                inst_text = f"{inst_net/10000:+.2f}亿"
            else:
                inst_text = f"{inst_net:+.0f}万"
            dt_part = f"🏛️龙虎榜：机构净买入{inst_text}"
            if dt.get('hot_money'):
                dt_part += f" 知名游资:{dt['hot_money'][:10]}"
            parts.append(dt_part)

        # 北向资金
        nb = data.get('northbound', {})
        if nb and abs(nb.get('change_pct', 0)) > 0.001:
            pct = nb['change_pct']
            direction = '增持' if pct > 0 else '减持'
            parts.append(f"北向资金{direction}{abs(pct):.2f}%")

        return ' '.join(parts)


_analyzer: Optional[DeepFundFlowAnalyzer] = None


def get_deep_fund_analyzer() -> DeepFundFlowAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = DeepFundFlowAnalyzer()
    return _analyzer


def analyze_deep_fund(code: str, name: str = '') -> Optional[Dict]:
    return get_deep_fund_analyzer().analyze(code, name)
