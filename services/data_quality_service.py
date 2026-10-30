# -*- coding: utf-8 -*-
"""
数据质量检测服务 V1.0（V3.0）
每个数据源返回：{status, source, source_time, update_time, latency_ms, row_count, error}
"""
import os
import sys
import time
from typing import Dict, List, Optional
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class DataQualityService:
    """数据质量检测服务"""

    def __init__(self):
        self._health_status = {}
        self._history = []

    def check_kline(self, code: str = '000001', days: int = 60) -> Dict:
        result = {
            'source': 'pytdx在线', 'status': 'error', 'source_time': '',
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'latency_ms': 0, 'row_count': 0, 'error': '',
        }
        start = time.time()
        try:
            from utils.kline_fetcher import fetch_kline_pytdx
            kline = fetch_kline_pytdx(code, days=days)
            latency = int((time.time() - start) * 1000)
            if kline and len(kline) >= 5:
                result['status'] = 'ok'
                result['row_count'] = len(kline)
                result['source_time'] = kline[-1].get('date', '')
                result['latency_ms'] = latency
            else:
                result['error'] = f'K线不足({len(kline) if kline else 0}根)'
                result['latency_ms'] = latency
        except Exception as e:
            result['error'] = str(e)
            result['latency_ms'] = int((time.time() - start) * 1000)
        self._health_status['kline'] = result
        return result

    def check_stock_list(self) -> Dict:
        result = {
            'source': '通达信/pytdx', 'status': 'error', 'source_time': '',
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'latency_ms': 0, 'row_count': 0, 'error': '',
        }
        start = time.time()
        try:
            from utils.tdx_stock_list import get_full_market_quotes
            stocks = get_full_market_quotes(main_board_only=True, exclude_st=True)
            latency = int((time.time() - start) * 1000)
            if stocks and len(stocks) > 0:
                result['status'] = 'ok'
                result['row_count'] = len(stocks)
                result['latency_ms'] = latency
            else:
                result['error'] = '股票列表为空'
                result['latency_ms'] = latency
        except Exception as e:
            result['error'] = str(e)
            result['latency_ms'] = int((time.time() - start) * 1000)
        self._health_status['stock_list'] = result
        return result

    def check_news(self) -> Dict:
        result = {
            'source': '新浪7x24/新浪财经', 'status': 'error', 'source_time': '',
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'latency_ms': 0, 'row_count': 0, 'error': '',
        }
        start = time.time()
        try:
            from service.unified_data_service import get_news_service
            service = get_news_service()
            news = service.get_news(source='7x24', limit=20)
            latency = int((time.time() - start) * 1000)
            if news and len(news) > 0:
                result['status'] = 'ok'
                result['row_count'] = len(news)
                result['source_time'] = news[0].get('publish_time', '')
                result['latency_ms'] = latency
            else:
                result['error'] = '新闻为空'
                result['latency_ms'] = latency
        except Exception as e:
            result['error'] = str(e)
            result['latency_ms'] = int((time.time() - start) * 1000)
        self._health_status['news'] = result
        return result

    def check_sector(self) -> Dict:
        result = {
            'source': '新浪板块行情', 'status': 'error', 'source_time': '',
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'latency_ms': 0, 'row_count': 0, 'error': '',
        }
        start = time.time()
        try:
            from service.unified_data_service import get_sector_data_service
            service = get_sector_data_service()
            sectors = service.get_hot_sectors(limit=10)
            latency = int((time.time() - start) * 1000)
            if sectors and len(sectors) > 0:
                result['status'] = 'ok'
                result['row_count'] = len(sectors)
                result['latency_ms'] = latency
            else:
                result['status'] = 'stale'
                result['error'] = '板块数据为空或缓存过期'
                result['latency_ms'] = latency
        except Exception as e:
            result['error'] = str(e)
            result['latency_ms'] = int((time.time() - start) * 1000)
        self._health_status['sector'] = result
        return result

    def check_wechat(self) -> Dict:
        result = {
            'source': '企业微信Webhook', 'status': 'error', 'source_time': '',
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'latency_ms': 0, 'row_count': 0, 'error': '',
        }
        try:
            from utils.wechat_push import WechatPusher
            pusher = WechatPusher()
            if pusher.is_configured():
                result['status'] = 'ok'
                result['row_count'] = 1
                result['error'] = '已配置（未实际发送）'
            else:
                result['status'] = 'stale'
                result['error'] = '未配置Webhook URL'
        except Exception as e:
            result['error'] = str(e)
        self._health_status['wechat'] = result
        return result

    def check_all(self) -> Dict:
        results = {
            'kline': self.check_kline(),
            'stock_list': self.check_stock_list(),
            'news': self.check_news(),
            'sector': self.check_sector(),
            'wechat': self.check_wechat(),
        }
        ok_count = sum(1 for r in results.values() if r['status'] == 'ok')
        error_count = sum(1 for r in results.values() if r['status'] == 'error')
        stale_count = sum(1 for r in results.values() if r['status'] == 'stale')
        summary = {
            'total': len(results), 'ok': ok_count, 'error': error_count, 'stale': stale_count,
            'overall_status': 'ok' if error_count == 0 else 'error',
            'check_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'details': results,
        }
        self._history.append(summary)
        if len(self._history) > 100:
            self._history = self._history[-100:]
        return summary

    def get_health_status(self) -> Dict:
        return self._health_status

    def format_report(self, summary: Dict) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append("数据质量检测报告")
        lines.append(f"检测时间：{summary['check_time']}")
        lines.append(f"总体状态：{'✅ 正常' if summary['overall_status'] == 'ok' else '❌ 异常'}")
        lines.append(f"正常：{summary['ok']}  异常：{summary['error']}  过期：{summary['stale']}")
        lines.append("-" * 60)
        for name, detail in summary['details'].items():
            icon = '✅' if detail['status'] == 'ok' else ('⚠️' if detail['status'] == 'stale' else '❌')
            lines.append(f"{icon} {name}: {detail['source']}")
            lines.append(f"   状态:{detail['status']} 数量:{detail['row_count']} 延迟:{detail['latency_ms']}ms")
            if detail['source_time']:
                lines.append(f"   数据时间:{detail['source_time']}")
            if detail['error']:
                lines.append(f"   说明:{detail['error']}")
            lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)


def get_data_quality_service() -> DataQualityService:
    return DataQualityService()


if __name__ == '__main__':
    print("数据质量检测服务自测")
    print("=" * 60)
    service = DataQualityService()
    summary = service.check_all()
    print(service.format_report(summary))
