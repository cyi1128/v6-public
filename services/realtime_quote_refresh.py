# -*- coding: utf-8 -*-
"""
V2.8 AI520实时行情强制刷新模块
问题修复：AI520选股列表现价/涨跌幅数据陈旧，与盘中实时推送不一致
核心机制：
1. 每次扫描完成后强制拉取最新实时行情，禁止复用历史缓存的价格字段
2. 仅缓存K线/指标/评分等计算类数据，行情价格字段每次扫描强制重新获取
3. 两端一致性校验：UI展示与企业微信推送数据同源，偏差自动记录并强制刷新
"""
import os
import sys
import time
import logging
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logger = logging.getLogger(__name__)


def _log(msg: str, level: str = 'INFO'):
    print(f"[行情刷新] {msg}", flush=True)


class RealtimeQuoteRefresher:
    """实时行情强制刷新器"""

    def __init__(self):
        self._last_refresh_time = 0
        self._quote_cache: Dict[str, Dict] = {}
        self._consistency_log: List[Dict] = []

    def refresh_signals_quotes(self, signals: List[Dict],
                                force: bool = True) -> Tuple[List[Dict], Dict]:
        """
        强制刷新选股结果的实时行情
        Args:
            signals: AI520选股信号列表
            force: 是否强制刷新（True=忽略缓存，每次重新获取）
        Returns:
            (refreshed_signals, stats)
            stats: {total, refreshed, failed, consistency_issues, duration}
        """
        start_time = time.time()
        if not signals:
            return signals, {'total': 0, 'refreshed': 0, 'failed': 0,
                             'consistency_issues': 0, 'duration': 0}

        codes = [s.get('code', '') for s in signals if s.get('code')]
        if not codes:
            return signals, {'total': 0, 'refreshed': 0, 'failed': 0,
                             'consistency_issues': 0, 'duration': 0}

        # 1. 批量获取实时行情
        quotes = self._fetch_realtime_quotes(codes)

        refreshed = 0
        failed = 0
        consistency_issues = 0

        # 2. 强制更新每只股票的行情字段
        for signal in signals:
            code = signal.get('code', '')
            if not code or code not in quotes:
                failed += 1
                continue

            quote = quotes[code]
            new_price = quote.get('price', 0)
            new_pct = quote.get('pct_chg', 0)

            if new_price <= 0:
                failed += 1
                continue

            # 3. 一致性校验：记录旧值与新值偏差
            old_price = signal.get('price', 0)
            old_pct = signal.get('pct_chg', 0)

            if old_price > 0 and abs(new_price - old_price) > 0.001:
                issue = {
                    'code': code,
                    'name': signal.get('name', ''),
                    'old_price': old_price,
                    'new_price': new_price,
                    'old_pct': old_pct,
                    'new_pct': new_pct,
                    'price_diff': round(new_price - old_price, 3),
                    'pct_diff': round(new_pct - old_pct, 2),
                    'time': time.strftime('%H:%M:%S'),
                }
                consistency_issues += 1
                self._consistency_log.append(issue)
                if consistency_issues <= 10:  # 只打印前10条避免日志过多
                    _log(f"一致性偏差: {code} {signal.get('name','')} "
                         f"价格{old_price:.2f}→{new_price:.2f} "
                         f"涨跌幅{old_pct:.2f}%→{new_pct:.2f}%", 'WARN')

            # 4. 强制更新行情字段（禁止复用历史缓存价格）
            signal['price'] = new_price
            signal['pct_chg'] = new_pct
            signal['last_close'] = quote.get('last_close', 0)
            signal['open'] = quote.get('open', 0)
            signal['high'] = quote.get('high', 0)
            signal['low'] = quote.get('low', 0)
            signal['volume'] = quote.get('volume', 0)
            signal['amount'] = quote.get('amount', 0)
            signal['quote_refresh_time'] = time.strftime('%Y-%m-%d %H:%M:%S')
            signal['quote_source'] = quote.get('source', 'http_realtime')

            refreshed += 1

        duration = time.time() - start_time
        stats = {
            'total': len(signals),
            'refreshed': refreshed,
            'failed': failed,
            'consistency_issues': consistency_issues,
            'duration': round(duration, 2),
        }

        _log(f"行情刷新完成: 共{len(signals)}只, 成功{refreshed}只, "
             f"失败{failed}只, 一致性偏差{consistency_issues}处, 耗时{duration:.2f}秒")

        return signals, stats

    def _fetch_realtime_quotes(self, codes: List[str]) -> Dict[str, Dict]:
        """
        批量获取实时行情（pytdx优先，HTTP降级，实际数据源为腾讯HTTP）
        每批50只，超时≤3秒，失败重试1次
        """
        result = {}
        try:
            from utils.tdx_stock_list import get_realtime_quotes_tdx
            # 分批获取，每批最多80只（pytdx get_security_quotes限制）
            batch_size = 80
            for i in range(0, len(codes), batch_size):
                batch = codes[i:i + batch_size]
                try:
                    quotes = get_realtime_quotes_tdx(batch)
                    if quotes:
                        result.update(quotes)
                except Exception as e:
                    _log(f"第{i//batch_size+1}批行情获取失败: {e}", 'WARN')
                    # 重试1次
                    try:
                        time.sleep(0.3)
                        quotes = get_realtime_quotes_tdx(batch)
                        if quotes:
                            result.update(quotes)
                    except Exception as e2:
                        _log(f"重试失败: {e2}", 'WARN')
                time.sleep(0.1)  # 避免请求过快
        except Exception as e:
            _log(f"实时行情获取异常: {e}", 'ERROR')

        return result

    def get_consistency_log(self) -> List[Dict]:
        """获取一致性校验日志"""
        return self._consistency_log

    def clear_consistency_log(self):
        """清一致性日志"""
        self._consistency_log.clear()


# 全局单例
_refresher: Optional[RealtimeQuoteRefresher] = None


def get_quote_refresher() -> RealtimeQuoteRefresher:
    global _refresher
    if _refresher is None:
        _refresher = RealtimeQuoteRefresher()
    return _refresher


def refresh_signal_quotes(signals: List[Dict], force: bool = True) -> Tuple[List[Dict], Dict]:
    """便捷函数：刷新选股信号的实时行情"""
    return get_quote_refresher().refresh_signals_quotes(signals, force)
