# -*- coding: utf-8 -*-
"""
三日回调 + 今日放量突破模型 - 监控大厅适配层（STR-NEW-012）

零侵入设计：
- 不修改monitor_hall.py、real_scan_service.py等任何原有文件
- 复用现有RealScanService的get_main_board_stocks()和get_kline()
- 复用现有fetch_kline_pytdx作为K线数据源
- 作为独立信号源，可在监控大厅中通过import接入

接入方式（在监控大厅中可选接入，不强制）：
    from strategy.strategy_3day_adapter import Strategy3DayAdapter
    adapter = Strategy3DayAdapter()
    signals = adapter.scan(max_stocks=100)
"""
import os
import sys
from typing import Dict, List, Optional, Callable
from datetime import datetime

# 项目路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from strategy.strategy_3day_callback_breakout import (
    Strategy3DayCallbackBreakout,
    Strategy3DayBacktest,
)


class Strategy3DayAdapter:
    """三日回调模型 - 监控大厅适配层"""

    SIGNAL_SOURCE_NAME = "三日回调突破"
    SIGNAL_SOURCE_ID = "STR-NEW-012"

    def __init__(self, use_real_scan_service: bool = True):
        """
        初始化适配层。

        Args:
            use_real_scan_service: 是否使用RealScanService（推荐，有K线缓存）
        """
        self.strategy = Strategy3DayCallbackBreakout()
        self.backtest_engine = Strategy3DayBacktest(self.strategy)
        self._use_real_scan_service = use_real_scan_service
        self._scan_service = None
        self._kline_provider = None
        self._last_scan_time = None
        self._last_signals = []
        self._scan_logs = []

    def _get_scan_service(self):
        """获取RealScanService单例（延迟导入，避免循环依赖）"""
        if self._scan_service is None:
            try:
                from ui.real_scan_service import get_real_scan_service
                self._scan_service = get_real_scan_service()
            except Exception as e:
                print(f"[三日回调Adapter] RealScanService获取失败: {e}，将使用直接K线接口", flush=True)
                self._scan_service = None
        return self._scan_service

    def _get_kline_provider(self) -> Callable:
        """获取K线提供函数"""
        if self._kline_provider is not None:
            return self._kline_provider

        service = self._get_scan_service()
        if service is not None and hasattr(service, 'get_kline'):
            # 使用RealScanService的get_kline（有缓存）
            def kline_provider(code, days=30):
                try:
                    return service.get_kline(code, days=days, use_cache=True)
                except Exception:
                    return self._fetch_kline_direct(code, days)
            self._kline_provider = kline_provider
        else:
            # 直接使用fetch_kline_pytdx
            self._kline_provider = self._fetch_kline_direct

        return self._kline_provider

    def _fetch_kline_direct(self, code: str, days: int = 30) -> List[Dict]:
        """直接使用fetch_kline_pytdx获取K线"""
        try:
            from utils.kline_fetcher import fetch_kline_pytdx
            return fetch_kline_pytdx(code, days=days) or []
        except Exception as e:
            print(f"[三日回调Adapter] K线获取失败 {code}: {e}", flush=True)
            return []

    def get_main_board_stocks(self, max_count: int = 3000) -> List[Dict]:
        """
        获取主板股票列表（复用现有接口）。
        排除ST/*ST、科创板688、创业板300/301、北交所8xx。
        """
        service = self._get_scan_service()
        if service is not None and hasattr(service, 'get_main_board_stocks'):
            try:
                stocks = service.get_main_board_stocks(max_count=max_count)
                if stocks:
                    return stocks
            except Exception as e:
                print(f"[三日回调Adapter] RealScanService股票列表失败: {e}", flush=True)

        # 备用：直接使用tdx_stock_list
        try:
            from utils.tdx_stock_list import get_full_market_quotes
            all_stocks = get_full_market_quotes(main_board_only=True, exclude_st=True)
            # 过滤
            filtered = []
            for s in all_stocks:
                code = str(s.get('code', ''))
                name = str(s.get('name', ''))
                # 排除ST
                if 'ST' in name.upper() or '*ST' in name:
                    continue
                # 排除科创板688
                if code.startswith('688'):
                    continue
                # 排除创业板300/301
                if code.startswith('300') or code.startswith('301'):
                    continue
                # 排除北交所8xx
                if code.startswith('8'):
                    continue
                # 只保留沪市60开头和深市00开头
                if code.startswith('60') or code.startswith('00'):
                    filtered.append({'code': code, 'name': name})
            return filtered[:max_count]
        except Exception as e:
            print(f"[三日回调Adapter] 直接股票列表失败: {e}", flush=True)
            return []

    def scan(self, max_stocks: int = 100, days: int = 30, verbose: bool = False) -> List[Dict]:
        """
        执行扫描。

        Args:
            max_stocks: 最大扫描股票数（0表示全部主板）
            days: K线天数
            verbose: 是否输出详细条件日志

        Returns:
            信号列表
        """
        self.strategy.clear_logs()
        self._scan_logs = []

        print(f"[三日回调Adapter] 开始扫描，max_stocks={max_stocks}, days={days}", flush=True)

        # 1. 获取股票列表
        stocks = self.get_main_board_stocks(max_count=max_stocks if max_stocks > 0 else 3000)
        if not stocks:
            self._scan_logs.append("[三日回调Adapter] 股票列表为空，扫描终止")
            print("[三日回调Adapter] 股票列表为空，扫描终止", flush=True)
            return []

        print(f"[三日回调Adapter] 获取到{len(stocks)}只主板股票", flush=True)

        # 2. 获取K线提供函数
        kline_provider = self._get_kline_provider()

        # 3. 执行扫描
        signals = self.strategy.scan_stock_list(
            stocks=stocks,
            kline_provider=kline_provider,
            days=days,
            verbose=verbose,
        )

        # 4. 按放量倍数排序（降序）
        signals.sort(key=lambda x: x.get('vol_multiple', 0), reverse=True)

        self._last_signals = signals
        self._last_scan_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self._scan_logs = self.strategy.get_scan_logs()

        print(f"[三日回调Adapter] 扫描完成：{len(stocks)}只股票，生成信号{len(signals)}只", flush=True)
        return signals

    def scan_single(self, code: str, name: str = "", days: int = 30, verbose: bool = False) -> Optional[Dict]:
        """单只股票扫描"""
        kline_provider = self._get_kline_provider()
        kline = kline_provider(code, days)
        if not kline:
            return None
        return self.strategy.run_single_stock(kline, code, name, verbose=verbose)

    def backtest_single(self, code: str, name: str = "", days: int = 250, hold_days: int = 5) -> Optional[Dict]:
        """单只股票回测"""
        kline_provider = self._get_kline_provider()
        kline = kline_provider(code, days)
        if not kline or len(kline) < 30:
            return None
        return self.backtest_engine.run_backtest(kline, code, name, hold_days=hold_days)

    def get_last_signals(self) -> List[Dict]:
        """获取最近一次扫描结果"""
        return self._last_signals

    def get_scan_logs(self) -> List[str]:
        """获取扫描日志"""
        return self._scan_logs

    def get_scan_info(self) -> Dict:
        """获取扫描信息"""
        return {
            'signal_source': self.SIGNAL_SOURCE_NAME,
            'signal_source_id': self.SIGNAL_SOURCE_ID,
            'last_scan_time': self._last_scan_time,
            'last_signal_count': len(self._last_signals),
            'strategy_name': self.strategy.STRATEGY_NAME,
        }

    # ============================================================
    # 监控大厅展示字段映射
    # ============================================================
    @staticmethod
    def get_display_columns() -> List[Dict]:
        """
        获取监控大厅展示列定义。
        用于在监控大厅中动态创建表格列。
        """
        return [
            {'key': 'stock_name', 'label': '股票名称', 'width': 100},
            {'key': 'stock_code', 'label': '股票代码', 'width': 80},
            {'key': 'today_pct', 'label': '今日涨跌幅(%)', 'width': 90},
            {'key': 'today_close', 'label': '今日收盘价', 'width': 80},
            {'key': 't1_high', 'label': 'T-1最高价', 'width': 80},
            {'key': 'today_volume', 'label': '今日成交量(手)', 'width': 100},
            {'key': 'vol_5ma', 'label': '5日均量(手)', 'width': 90},
            {'key': 'vol_multiple', 'label': '放量倍数', 'width': 80},
            {'key': 't4_high', 'label': 'T-4最高价', 'width': 80},
            {'key': 't3_high', 'label': 'T-3最高价', 'width': 80},
            {'key': 't3_pct', 'label': 'T-3涨跌(%)', 'width': 80},
            {'key': 't2_pct', 'label': 'T-2涨跌(%)', 'width': 80},
            {'key': 't1_pct', 'label': 'T-1涨跌(%)', 'width': 80},
            {'key': 'signal_level', 'label': '信号等级', 'width': 70},
            {'key': 'breakout_pct', 'label': '突破幅度(%)', 'width': 90},
        ]

    @staticmethod
    def get_signal_tags(signal: Dict) -> Dict:
        """
        获取信号标签（主标签+附属标签）。
        用于在监控大厅中显示标签。
        """
        return {
            'main_tag': signal.get('main_tag', '三日回调放量突破'),
            'sub_tags': signal.get('sub_tags', ['回调完成', '阳线启动', '放量', '突破前高']),
            'signal_level': signal.get('signal_level', 'B'),
            'signal_source': signal.get('signal_source', '三日回调突破'),
        }


# ============================================================
# 便捷函数
# ============================================================
def get_strategy_3day_adapter() -> Strategy3DayAdapter:
    """获取Adapter单例"""
    return Strategy3DayAdapter()


def scan_3day_callback(max_stocks: int = 100, days: int = 30, verbose: bool = False):
    """
    便捷扫描函数。

    Returns:
        (信号列表, 扫描信息字典)
    """
    adapter = Strategy3DayAdapter()
    signals = adapter.scan(max_stocks=max_stocks, days=days, verbose=verbose)
    info = adapter.get_scan_info()
    return signals, info


if __name__ == '__main__':
    print("=" * 60)
    print("三日回调模型 Adapter 自测")
    print("=" * 60)

    adapter = Strategy3DayAdapter(use_real_scan_service=False)

    # 测试获取股票列表
    print("\n1. 测试获取主板股票列表（前10只）...")
    stocks = adapter.get_main_board_stocks(max_count=10)
    print(f"   获取到{len(stocks)}只股票:")
    for s in stocks[:5]:
        print(f"     {s.get('code')} {s.get('name')}")

    # 测试单股扫描（如果有股票）
    if stocks:
        print(f"\n2. 测试单股扫描 {stocks[0].get('code')} {stocks[0].get('name')}...")
        result = adapter.scan_single(stocks[0]['code'], stocks[0].get('name', ''), days=30, verbose=True)
        if result:
            print(f"   ✅ 信号生成：等级{result['signal_level']} 放量{result['vol_multiple']}倍 突破{result['breakout_pct']}%")
        else:
            print("   无信号（该股票不满足条件，正常）")

    # 测试展示字段
    print("\n3. 测试展示字段定义...")
    columns = adapter.get_display_columns()
    print(f"   共{len(columns)}列:")
    for col in columns[:5]:
        print(f"     {col['key']}: {col['label']}")

    print("\nAdapter自测完成。")
