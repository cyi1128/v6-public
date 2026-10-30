"""core/scan_engine.py - 扫描引擎兼容层
V2.8：为旧UI模块提供兼容接口，实际调用AI520ScanService
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class ScanEngine:
    """扫描引擎（兼容层，实际调用AI520ScanService）"""

    def __init__(self):
        self._ai520_service = None
        self._init_service()

    def _init_service(self):
        """初始化AI520扫描服务"""
        try:
            from strategy.ai_520_scan_service import AI520ScanService
            self._ai520_service = AI520ScanService()
        except Exception as e:
            print(f"[ScanEngine] AI520服务初始化失败: {e}", flush=True)
            self._ai520_service = None

    def scan(self, scan_type='ai520', max_stocks=0):
        """执行扫描"""
        if self._ai520_service is None:
            return {'signals': [], 'total': 0}
        try:
            result = self._ai520_service.scan_market(
                scan_source='manual',
                max_stocks=max_stocks,
                use_cache=True
            )
            return result
        except Exception as e:
            print(f"[ScanEngine] 扫描失败: {e}", flush=True)
            return {'signals': [], 'total': 0, 'error': str(e)}

    def get_stock_list(self):
        """获取股票列表"""
        if self._ai520_service is None:
            return []
        try:
            return self._ai520_service.get_stock_list_from_duckdb()
        except Exception as e:
            print(f"[ScanEngine] 获取股票列表失败: {e}", flush=True)
            return []

    def analyze_stock(self, code):
        """分析单只股票"""
        if self._ai520_service is None:
            return None
        try:
            from strategy.ai_520_engine import AI520Engine
            engine = AI520Engine()
            return engine.analyze_stock(code)
        except Exception as e:
            print(f"[ScanEngine] 分析股票{code}失败: {e}", flush=True)
            return None


_scan_engine = None


def get_scan_engine():
    """获取扫描引擎单例"""
    global _scan_engine
    if _scan_engine is None:
        _scan_engine = ScanEngine()
    return _scan_engine
