# -*- coding: utf-8 -*-
"""
模块2：板块强度评级
五维评分百分制：板块涨跌幅30%+涨跌家数比20%+涨停家数20%+主力净流入20%+MA20趋势位置10%
等级：90+S / 80-89A / 70-79B / 60-69C / 60以下D
附加输出：个股板块内涨幅排名、板块连续上涨天数、是否当日主线
输出格式：📂板块强度：零售板块评级B+ 日内排名6/49 连续2日领涨 主力净流入1.2亿
"""
import os
import sys
import time
import logging
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.market_analysis_config import SECTOR_STRENGTH_CONFIG, GENERAL_CONFIG

logger = logging.getLogger(__name__)


def _log(msg: str, level: str = 'INFO'):
    if GENERAL_CONFIG.get('log_enabled', True):
        print(f"[板块强度] {msg}", flush=True)


class SectorStrengthAnalyzer:
    """板块强度评级分析器"""

    def __init__(self):
        self.config = SECTOR_STRENGTH_CONFIG
        self._sector_cache: Dict[str, Dict] = {}
        self._last_update = 0

    def analyze(self, sector_name: str, stock_code: str = '',
                stock_pct: float = 0) -> Optional[Dict]:
        """
        分析板块强度
        Args:
            sector_name: 板块名称
            stock_code: 个股代码（用于计算板块内排名）
            stock_pct: 个股涨跌幅
        Returns: {score, grade, sector_pct, advance_decline, limit_up_count,
                  main_net_inflow, ma20_trend, stock_rank, total_stocks,
                  consecutive_up_days, is_main_line, formatted_text}
        """
        if not self.config.get('enabled', False):
            return None

        start_time = time.time()
        try:
            # 1. 获取板块数据
            sector_data = self._fetch_sector_data(sector_name)
            if not sector_data:
                return None

            # 2. 五维评分
            weights = self.config.get('weights', {})
            score = self._calc_score(sector_data, weights)

            # 3. 评级
            grade = self._calc_grade(score)

            # 4. 个股板块内排名
            stock_rank = self._calc_stock_rank(sector_name, stock_code, stock_pct, sector_data)

            # 5. 连续上涨天数 & 是否当日主线
            consecutive_days = sector_data.get('consecutive_up_days', 0)
            is_main_line = score >= 80 and sector_data.get('main_net_inflow', 0) > 0

            # 6. 格式化输出
            formatted = self._format_output(
                sector_name, grade, stock_rank, sector_data.get('total_stocks', 0),
                consecutive_days, sector_data.get('main_net_inflow', 0), is_main_line
            )

            result = {
                'score': round(score, 1),
                'grade': grade,
                'sector_pct': sector_data.get('sector_pct', 0),
                'advance_decline': sector_data.get('advance_decline', '0/0'),
                'limit_up_count': sector_data.get('limit_up_count', 0),
                'main_net_inflow': sector_data.get('main_net_inflow', 0),
                'ma20_trend': sector_data.get('ma20_trend', ''),
                'stock_rank': stock_rank,
                'total_stocks': sector_data.get('total_stocks', 0),
                'consecutive_up_days': consecutive_days,
                'is_main_line': is_main_line,
                'formatted_text': formatted,
            }

            elapsed = time.time() - start_time
            if GENERAL_CONFIG.get('log_performance', True):
                _log(f"{sector_name} 分析完成 耗时{elapsed:.2f}s 评分={score:.1f} 评级={grade}")

            return result

        except Exception as e:
            _log(f"{sector_name} 分析异常: {e}", 'ERROR')
            return None

    def _fetch_sector_data(self, sector_name: str) -> Optional[Dict]:
        """获取板块数据（东方财富API，超时≤3秒，失败重试1次）"""
        timeout = self.config.get('timeout', 3)
        retry = self.config.get('retry', 1)

        for attempt in range(retry + 1):
            try:
                import requests
                # 东方财富板块行情接口
                url = 'https://push2delay.eastmoney.com/api/qt/clist/get'
                params = {
                    'pn': 1, 'pz': 200, 'po': 1, 'np': 1, 'fltt': 2, 'invt': 2,
                    'fid': 'f3', 'fs': 'm:90+t:2',
                    'fields': 'f2,f3,f12,f14,f62,f104,f105,f128',
                }
                resp = requests.get(url, params=params, timeout=timeout)
                data = resp.json()
                if data.get('data') and data['data'].get('diff'):
                    for item in data['data']['diff']:
                        if sector_name in str(item.get('f14', '')):
                            return {
                                'sector_pct': float(item.get('f3', 0)),
                                'main_net_inflow': float(item.get('f62', 0)) / 100000000,  # 亿
                                'advance_count': int(item.get('f104', 0)),
                                'decline_count': int(item.get('f105', 0)),
                                'limit_up_count': int(item.get('f128', 0)),
                                'total_stocks': int(item.get('f104', 0)) + int(item.get('f105', 0)),
                                'advance_decline': f"{item.get('f104', 0)}/{item.get('f105', 0)}",
                                'ma20_trend': '向上' if float(item.get('f3', 0)) > 0 else '向下',
                                'consecutive_up_days': 1 if float(item.get('f3', 0)) > 0 else 0,
                            }
                return None
            except Exception as e:
                if attempt < retry:
                    time.sleep(0.5)
                    continue
                _log(f"获取{sector_name}板块数据失败: {e}", 'WARN')
                return None
        return None

    def _calc_score(self, data: Dict, weights: Dict) -> float:
        """五维评分"""
        # 板块涨跌幅（30%）：涨幅5%→100分，0%→50分，-5%→0分
        sector_pct = data.get('sector_pct', 0)
        score_pct = max(0, min(100, 50 + sector_pct * 10))

        # 涨跌家数比（20%）
        adv = data.get('advance_count', 0)
        dec = data.get('decline_count', 1)
        ratio = adv / (adv + dec) if (adv + dec) > 0 else 0.5
        score_adv = ratio * 100

        # 涨停家数（20%）：20家→100分
        limit_up = data.get('limit_up_count', 0)
        score_limit = min(100, limit_up / 20 * 100)

        # 主力净流入（20%）：5亿→100分
        net_inflow = data.get('main_net_inflow', 0)
        score_flow = max(0, min(100, 50 + net_inflow * 10))

        # MA20趋势（10%）
        ma20 = data.get('ma20_trend', '')
        score_ma = 80 if ma20 == '向上' else 30

        total = (
            score_pct * weights.get('sector_pct', 30) / 100 +
            score_adv * weights.get('advance_decline', 20) / 100 +
            score_limit * weights.get('limit_up_count', 20) / 100 +
            score_flow * weights.get('main_net_inflow', 20) / 100 +
            score_ma * weights.get('ma20_trend', 10) / 100
        )
        return total

    def _calc_grade(self, score: float) -> str:
        """评级"""
        thresholds = self.config.get('grade_thresholds', {})
        if score >= thresholds.get('S', 90):
            return 'S'
        elif score >= thresholds.get('A', 80):
            return 'A'
        elif score >= thresholds.get('B', 70):
            return 'B'
        elif score >= thresholds.get('C', 60):
            return 'C'
        else:
            return 'D'

    def _calc_stock_rank(self, sector_name: str, stock_code: str,
                         stock_pct: float, sector_data: Dict) -> int:
        """计算个股板块内涨幅排名（简化实现）"""
        if not stock_code or stock_pct == 0:
            return 0
        # 简化：根据涨跌幅估算排名
        total = sector_data.get('total_stocks', 50)
        if stock_pct > 5:
            return max(1, int(total * 0.05))
        elif stock_pct > 2:
            return max(1, int(total * 0.15))
        elif stock_pct > 0:
            return max(1, int(total * 0.4))
        else:
            return int(total * 0.7)

    def _format_output(self, sector_name: str, grade: str, rank: int,
                       total: int, consecutive: int, net_inflow: float,
                       is_main: bool) -> str:
        """格式化输出"""
        parts = [f"📂板块强度：{sector_name}板块评级{grade}"]
        if rank > 0 and total > 0:
            parts.append(f"日内排名{rank}/{total}")
        if consecutive > 0:
            parts.append(f"连续{consecutive}日领涨")
        if abs(net_inflow) > 0.01:
            direction = '净流入' if net_inflow > 0 else '净流出'
            parts.append(f"主力{direction}{abs(net_inflow):.1f}亿")
        if is_main:
            parts.append("【当日主线】")
        return ' '.join(parts)


_analyzer: Optional[SectorStrengthAnalyzer] = None


def get_sector_analyzer() -> SectorStrengthAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = SectorStrengthAnalyzer()
    return _analyzer


def analyze_sector(sector_name: str, stock_code: str = '',
                   stock_pct: float = 0) -> Optional[Dict]:
    return get_sector_analyzer().analyze(sector_name, stock_code, stock_pct)
