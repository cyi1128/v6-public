# -*- coding: utf-8 -*-
"""
模块5：板块异动监控
触发规则：5分钟涨幅≥1.5%或跌幅≥1.5%触发
区分拉升异动和跳水异动，独立推送不占用个股信号通道
同一板块30分钟内不重复推送，可配置异动阈值与推送开关
输出格式：🚨板块异动：半导体板块5分钟拉升1.8% 主力净流入3.2亿 领涨：XX半导体 📌异动归因：大基金三期投资落地消息催化
"""
import os
import sys
import time
import logging
from typing import Dict, List, Optional, Set

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.market_analysis_config import SECTOR_ANOMALY_CONFIG, GENERAL_CONFIG

logger = logging.getLogger(__name__)


def _log(msg: str, level: str = 'INFO'):
    if GENERAL_CONFIG.get('log_enabled', True):
        print(f"[板块异动] {msg}", flush=True)


class SectorAnomalyMonitor:
    """板块异动监控器"""

    def __init__(self):
        self.config = SECTOR_ANOMALY_CONFIG
        self._pushed_recently: Dict[str, float] = {}  # {sector_name: push_timestamp}
        self._sector_prices: Dict[str, List[float]] = {}  # {sector_name: [prices]}
        self._running = False

    def check_anomaly(self) -> List[Dict]:
        """
        检查板块异动
        Returns: 异动列表 [{sector_name, type, pct_change, main_net_inflow,
                            leading_stock, attribution, formatted_text}]
        """
        if not self.config.get('enabled', False):
            return []

        start_time = time.time()
        anomalies = []

        try:
            # 1. 获取板块实时数据
            sectors = self._fetch_sector_data()
            if not sectors:
                return []

            surge_threshold = self.config.get('surge_threshold', 1.5)
            drop_threshold = self.config.get('drop_threshold', 1.5)
            dedup_minutes = self.config.get('dedup_minutes', 30)

            for sector in sectors:
                name = sector.get('name', '')
                pct = sector.get('pct_change', 0)
                anomaly_type = None

                # 2. 判断异动类型
                if pct >= surge_threshold:
                    anomaly_type = 'surge'  # 拉升异动
                elif pct <= -drop_threshold:
                    anomaly_type = 'drop'  # 跳水异动

                if not anomaly_type:
                    continue

                # 3. 去重检查（30分钟内不重复推送）
                if self._is_duplicate(name, dedup_minutes):
                    continue

                # 4. 构建异动信息
                anomaly = {
                    'sector_name': name,
                    'type': anomaly_type,
                    'pct_change': pct,
                    'main_net_inflow': sector.get('main_net_inflow', 0),
                    'leading_stock': sector.get('leading_stock', ''),
                    'attribution': sector.get('attribution', ''),
                    'formatted_text': self._format_output(name, anomaly_type, pct, sector),
                    'timestamp': time.time(),
                }
                anomalies.append(anomaly)
                self._pushed_recently[name] = time.time()

            elapsed = time.time() - start_time
            if anomalies and GENERAL_CONFIG.get('log_performance', True):
                _log(f"发现{len(anomalies)}个板块异动 耗时{elapsed:.2f}s")

            return anomalies

        except Exception as e:
            _log(f"板块异动检查异常: {e}", 'ERROR')
            return []

    def _fetch_sector_data(self) -> List[Dict]:
        """获取板块实时数据（东方财富，超时≤3秒）"""
        timeout = self.config.get('timeout', 3)
        try:
            import requests
            url = 'https://push2delay.eastmoney.com/api/qt/clist/get'
            params = {
                'pn': 1, 'pz': 100, 'po': 1, 'np': 1, 'fltt': 2, 'invt': 2,
                'fid': 'f3', 'fs': 'm:90+t:2',
                'fields': 'f2,f3,f12,f14,f62,f128,f140',
            }
            resp = requests.get(url, params=params, timeout=timeout)
            data = resp.json()
            if data.get('data') and data['data'].get('diff'):
                result = []
                for item in data['data']['diff']:
                    result.append({
                        'name': item.get('f14', ''),
                        'pct_change': float(item.get('f3', 0)),
                        'main_net_inflow': float(item.get('f62', 0)) / 100000000,
                        'leading_stock': item.get('f140', ''),
                        'attribution': '',
                    })
                return result
            return []
        except Exception as e:
            _log(f"获取板块数据失败: {e}", 'WARN')
            return []

    def _is_duplicate(self, sector_name: str, dedup_minutes: int) -> bool:
        """检查是否重复推送（dedup_minutes分钟内不重复）"""
        now = time.time()
        if sector_name in self._pushed_recently:
            last_push = self._pushed_recently[sector_name]
            if (now - last_push) < dedup_minutes * 60:
                return True
        return False

    def _format_output(self, sector_name: str, anomaly_type: str,
                       pct: float, sector: Dict) -> str:
        """格式化输出"""
        if anomaly_type == 'surge':
            emoji = '🚨'
            action = '拉升'
        else:
            emoji = '📉'
            action = '跳水'

        parts = [f"{emoji}板块异动：{sector_name}板块5分钟{action}{abs(pct):.1f}%"]

        net_inflow = sector.get('main_net_inflow', 0)
        if abs(net_inflow) > 0.01:
            direction = '净流入' if net_inflow > 0 else '净流出'
            parts.append(f"主力{direction}{abs(net_inflow):.1f}亿")

        leading = sector.get('leading_stock', '')
        if leading:
            parts.append(f"领涨：{leading}")

        attribution = sector.get('attribution', '')
        if attribution:
            parts.append(f"📌异动归因：{attribution}")

        return ' '.join(parts)

    def clear_dedup_cache(self):
        """清离去重缓存（每日开盘前调用）"""
        self._pushed_recently.clear()
        _log("去重缓存已清空")


_monitor: Optional[SectorAnomalyMonitor] = None


def get_anomaly_monitor() -> SectorAnomalyMonitor:
    global _monitor
    if _monitor is None:
        _monitor = SectorAnomalyMonitor()
    return _monitor


def check_sector_anomaly() -> List[Dict]:
    return get_anomaly_monitor().check_anomaly()
