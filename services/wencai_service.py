# -*- coding: utf-8 -*-
"""
同花顺问财真实筛选服务 V1.0（V3.0）
- 复用现有WencaiAIService（pywencai）
- 查询模板配置中心
- 缓存机制（同query当天缓存）
- 失败显示"问财数据暂不可用"，不返回假数据
- 记录query/query_time/result_count/stocks/source/error
"""
import os
import sys
import json
import time
from typing import Dict, List, Optional
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class WencaiService:
    """同花顺问财真实筛选服务"""

    SERVICE_NAME = "同花顺问财"
    CACHE_TTL_SECONDS = 3600  # 缓存1小时

    # 查询模板配置中心
    QUERY_TEMPLATES = {
        'limit_up_pullback': {
            'name': '涨停回调启动',
            'query': '主板非ST，近20日有涨停，当前处于回调，重新站上5日线，成交量放大，距离20日高点较近',
            'description': '20日涨停记忆+回调+重新站MA5+放量',
        },
        'limit_up_memory': {
            'name': '涨停记忆回调',
            'query': '主板非ST，近20日有涨停，当前涨幅0.3%到7%，没有一字板，回调后重新启动，成交量放大，所属板块有联动',
            'description': '20日涨停+涨幅0.3-7%+回调启动+板块联动',
        },
        'ma_golden_cross': {
            'name': '均线多头金叉',
            'query': '主板非ST，MA5大于MA10大于MA20，成交量大于5日均量，KDJ低位金叉，价格接近20日均线，今日阳线',
            'description': 'MA多头+放量+KDJ低位金叉+接近MA20',
        },
        'low_position_start': {
            'name': '低位启动',
            'query': '主板非ST，近20日跌幅小于10%，当前价格处于20日区间下沿，今日放量阳线，站上5日线，KDJ低位向上',
            'description': '低位+放量阳线+站MA5+KDJ低位',
        },
        'volume_breakout': {
            'name': '放量突破',
            'query': '主板非ST，今日成交量大于5日均量1.5倍，今日阳线，收盘价突破前5日最高价，涨幅小于7%，非ST',
            'description': '放量1.5倍+阳线+突破前高+涨幅<7%',
        },
    }

    def __init__(self):
        self._ai_service = None
        self._cache = {}  # query_key -> {data, time, count}
        self._query_history = []
        self._stats = {'total_queries': 0, 'success': 0, 'failed': 0, 'cache_hit': 0}
        self._init_service()

    def _init_service(self):
        """初始化问财AI服务"""
        try:
            from strategy.wencai_ai import WencaiAIService
            self._ai_service = WencaiAIService()
            if self._ai_service.is_available():
                print(f"[WencaiService] 同花顺问财服务初始化成功")
            else:
                print(f"[WencaiService] 问财服务不可用（pywencai未安装或初始化失败）")
        except Exception as e:
            print(f"[WencaiService] 初始化失败: {e}")
            self._ai_service = None

    def is_available(self) -> bool:
        """检查问财服务是否可用"""
        return self._ai_service is not None and self._ai_service.is_available()

    def get_templates(self) -> Dict:
        """获取查询模板列表"""
        return self.QUERY_TEMPLATES.copy()

    def _make_cache_key(self, query: str) -> str:
        return f"{datetime.now().strftime('%Y%m%d')}_{query}"

    def _is_cache_valid(self, cache_key: str) -> bool:
        if cache_key not in self._cache:
            return False
        cache_time = self._cache[cache_key]['time']
        return (time.time() - cache_time) < self.CACHE_TTL_SECONDS

    def query(self, query_str: str, use_cache: bool = True) -> Dict:
        """
        执行问财查询（真实数据）

        Returns:
            {
                'status': 'ok/error/cache',
                'query': 查询语句,
                'query_time': 查询时间,
                'result_count': 返回股票数量,
                'stocks': 股票列表,
                'source': '同花顺问财',
                'error': 错误信息（失败时）,
                'latency_ms': 延迟毫秒
            }
        """
        self._stats['total_queries'] += 1
        cache_key = self._make_cache_key(query_str)

        # 缓存检查
        if use_cache and self._is_cache_valid(cache_key):
            self._stats['cache_hit'] += 1
            cached = self._cache[cache_key]
            return {
                'status': 'cache',
                'query': query_str,
                'query_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'result_count': cached['count'],
                'stocks': cached['data'],
                'source': '同花顺问财(缓存)',
                'error': '',
                'latency_ms': 0,
            }

        # 可用性检查
        if not self.is_available():
            self._stats['failed'] += 1
            error_msg = '问财数据暂不可用（pywencai未安装或初始化失败）'
            self._query_history.append({
                'query': query_str, 'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'status': 'error', 'count': 0, 'error': error_msg,
            })
            return {
                'status': 'error', 'query': query_str,
                'query_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'result_count': 0, 'stocks': [], 'source': '同花顺问财',
                'error': error_msg, 'latency_ms': 0,
            }

        # 执行查询
        start = time.time()
        try:
            stocks = self._ai_service.query_stocks(query_str)
            latency = int((time.time() - start) * 1000)

            if stocks is None:
                stocks = []

            self._stats['success'] += 1

            # 写入缓存
            self._cache[cache_key] = {
                'data': stocks,
                'time': time.time(),
                'count': len(stocks),
            }

            self._query_history.append({
                'query': query_str, 'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'status': 'ok', 'count': len(stocks), 'latency_ms': latency,
            })

            return {
                'status': 'ok', 'query': query_str,
                'query_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'result_count': len(stocks), 'stocks': stocks,
                'source': '同花顺问财', 'error': '', 'latency_ms': latency,
            }

        except Exception as e:
            latency = int((time.time() - start) * 1000)
            self._stats['failed'] += 1
            error_msg = f'问财查询失败: {str(e)}'
            self._query_history.append({
                'query': query_str, 'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'status': 'error', 'count': 0, 'error': error_msg,
            })
            return {
                'status': 'error', 'query': query_str,
                'query_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'result_count': 0, 'stocks': [], 'source': '同花顺问财',
                'error': error_msg, 'latency_ms': latency,
            }

    def query_by_template(self, template_key: str, use_cache: bool = True) -> Dict:
        """按模板查询"""
        if template_key not in self.QUERY_TEMPLATES:
            return {
                'status': 'error', 'query': '', 'query_time': '',
                'result_count': 0, 'stocks': [], 'source': '同花顺问财',
                'error': f'未知模板: {template_key}', 'latency_ms': 0,
            }
        template = self.QUERY_TEMPLATES[template_key]
        result = self.query(template['query'], use_cache=use_cache)
        result['template_name'] = template['name']
        result['template_key'] = template_key
        return result

    def check_stock_in_results(self, stock_code: str, query_result: Dict) -> bool:
        """检查股票是否在问财结果中"""
        if not query_result or query_result.get('status') not in ('ok', 'cache'):
            return False
        stocks = query_result.get('stocks', [])
        for stock in stocks:
            code = str(stock.get('code', stock.get('股票代码', ''))).strip()
            if code == stock_code or code.endswith(stock_code):
                return True
        return False

    def get_stock_wencai_score(self, stock_code: str, templates: Optional[List[str]] = None) -> Dict:
        """
        获取股票的问财评分（匹配多少个模板）

        Returns:
            {'score': 0-100, 'matched_templates': [], 'match_count': N, 'status': 'ok/error'}
        """
        if templates is None:
            templates = list(self.QUERY_TEMPLATES.keys())

        if not self.is_available():
            return {'score': 0, 'matched_templates': [], 'match_count': 0,
                    'status': 'error', 'error': '问财数据暂不可用'}

        match_count = 0
        matched = []
        for tpl_key in templates:
            result = self.query_by_template(tpl_key, use_cache=True)
            if result.get('status') in ('ok', 'cache') and self.check_stock_in_results(stock_code, result):
                match_count += 1
                matched.append(tpl_key)

        # 评分：匹配1个模板30分，2个50分，3个70分，4个85分，5个100分
        score_map = {0: 0, 1: 30, 2: 50, 3: 70, 4: 85, 5: 100}
        score = score_map.get(min(match_count, 5), 100)

        return {
            'score': score,
            'matched_templates': matched,
            'match_count': match_count,
            'total_templates': len(templates),
            'status': 'ok',
        }

    def get_stats(self) -> Dict:
        return self._stats.copy()

    def get_history(self, limit: int = 20) -> List[Dict]:
        return self._query_history[-limit:]

    def clear_cache(self):
        self._cache.clear()
        print("[WencaiService] 缓存已清空")


def get_wencai_service() -> WencaiService:
    return WencaiService()


if __name__ == '__main__':
    print("=" * 60)
    print("同花顺问财服务 V1.0 自测")
    print("=" * 60)

    service = WencaiService()
    print(f"\n问财服务可用性：{'✅ 可用' if service.is_available() else '❌ 不可用'}")

    templates = service.get_templates()
    print(f"\n查询模板数量：{len(templates)}")
    for key, tpl in templates.items():
        print(f"  - {key}: {tpl['name']}")

    if service.is_available():
        print("\n执行测试查询（涨停回调启动模板）...")
        result = service.query_by_template('limit_up_pullback', use_cache=False)
        print(f"查询状态：{result['status']}")
        print(f"返回股票数量：{result['result_count']}")
        print(f"延迟：{result['latency_ms']}ms")
        if result.get('error'):
            print(f"错误：{result['error']}")
        if result['stocks']:
            print(f"\n前5只股票：")
            for i, stock in enumerate(result['stocks'][:5]):
                code = stock.get('code', stock.get('股票代码', '未知'))
                name = stock.get('name', stock.get('股票简称', '未知'))
                print(f"  {i+1}. {code} {name}")

        print(f"\n查询统计：{service.get_stats()}")
    else:
        print("\n⚠️ 问财服务不可用，跳过实际查询测试")
        print("原因：pywencai未安装或初始化失败")
        print("安装方式：pip install pywencai")

    print("\n同花顺问财服务自测完成。")
