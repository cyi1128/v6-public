# -*- coding: utf-8 -*-
"""
实时新闻中心 - 投资日历功能模块
覆盖维度：新股（申购/上市/缴款）、解禁（限售股解禁/数量/占比）、
         财报（定期报告预约披露日）、宏观（CPI/PMI/社融/MLF/LPR等）、
         事件（行业大会/政策发布会/重要国际事件）
数据来源：交易所官方投资日历、AkShare财经日历接口
每日开盘前自动更新一次，支持按日期切换（未来7天）、按类型筛选、关联个股跳转。
"""

import sys
import os
import json
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from news_center.news_config import (
    CALENDAR_CONFIG, CALENDAR_TYPE_COLORS, CALENDAR_TYPE_ICONS,
)


# ============================================================
# 标准日历事件结构
# ============================================================
# {
#     'event_id':    str   事件唯一ID
#     'date':        str   日期 'YYYY-MM-DD'
#     'time':        str   时间 'HH:MM'（可为空表示全天）
#     'type':        str   类型：新股/解禁/财报/宏观/事件
#     'title':       str   事件标题
#     'detail':      str   详细说明
#     'stock_code':  str   关联股票代码（可为空）
#     'stock_name':  str   关联股票名称
#     'extra':       dict  类型特有数据（如解禁数量、财报季度等）
#     'importance':  int   重要度 1-5
# }


# ============================================================
# 数据获取器
# ============================================================
class CalendarDataProvider:
    """投资日历数据提供者"""

    def __init__(self):
        self._cache = {}
        self._cache_time = 0
        self._cache_file = CALENDAR_CONFIG.get('cache_file', '')

    def get_events(self, date_str: str = None) -> List[Dict]:
        """
        获取指定日期的财经事件
        date_str: 'YYYY-MM-DD'，默认为今天
        """
        if date_str is None:
            date_str = datetime.now().strftime('%Y-%m-%d')

        # 缓存检查
        cache_key = date_str
        if cache_key in self._cache and time.time() - self._cache_time < CALENDAR_CONFIG.get('cache_ttl_hours', 12) * 3600:
            return self._cache[cache_key]

        events = []
        # 并行获取各维度数据
        events.extend(self._get_ipo_events(date_str))
        events.extend(self._get_unlock_events(date_str))
        events.extend(self._get_report_events(date_str))
        events.extend(self._get_macro_events(date_str))
        events.extend(self._get_special_events(date_str))

        # 按时间排序
        events.sort(key=lambda x: (x.get('date', ''), x.get('time', '99:99')))

        self._cache[cache_key] = events
        self._cache_time = time.time()
        return events

    def get_date_range_events(self, start_date: str, end_date: str) -> Dict[str, List[Dict]]:
        """获取日期范围内的事件，返回 {date: [events]}"""
        result = {}
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
            current = start
            while current <= end:
                ds = current.strftime('%Y-%m-%d')
                result[ds] = self.get_events(ds)
                current += timedelta(days=1)
        except Exception as e:
            print(f"[投资日历] 日期范围查询失败: {e}", flush=True)
        return result

    def _get_ipo_events(self, date_str: str) -> List[Dict]:
        """新股事件：申购、上市、缴款日（优先AkShare）"""
        events = []
        try:
            import akshare as ak
            # 新股申购
            try:
                df = ak.stock_new_ipo_cninfo()
                if df is not None and not df.empty:
                    for _, row in df.iterrows():
                        ipo_date = str(row.get('申购日期', row.get('purchase_date', ''))).strip()[:10]
                        list_date = str(row.get('上市日期', row.get('list_date', ''))).strip()[:10]
                        pay_date = str(row.get('缴款日期', row.get('pay_date', ''))).strip()[:10]
                        code = str(row.get('股票代码', row.get('stock_code', ''))).strip()
                        name = str(row.get('股票名称', row.get('stock_name', ''))).strip()
                        price = row.get('发行价格', row.get('issue_price', ''))

                        if ipo_date == date_str:
                            events.append(self._make_event(
                                date_str, '09:30', '新股', f'{name}({code}) 新股申购',
                                f'发行价格：{price}元/股' if price else '新股申购日',
                                code, name, {'ipo_type': '申购', 'price': str(price)}, 5
                            ))
                        if list_date == date_str:
                            events.append(self._make_event(
                                date_str, '09:30', '新股', f'{name}({code}) 新股上市',
                                '新股上市交易日', code, name, {'ipo_type': '上市'}, 5
                            ))
                        if pay_date == date_str:
                            events.append(self._make_event(
                                date_str, '15:00', '新股', f'{name}({code}) 新股缴款',
                                '中签投资者需在今日完成缴款', code, name, {'ipo_type': '缴款'}, 4
                            ))
            except Exception as e:
                print(f"[投资日历] AkShare新股数据失败: {e}", flush=True)
        except ImportError:
            pass
        return events

    def _get_unlock_events(self, date_str: str) -> List[Dict]:
        """限售股解禁事件"""
        events = []
        try:
            import akshare as ak
            try:
                df = ak.stock_restricted_release_queue_sina()
                if df is not None and not df.empty:
                    for _, row in df.iterrows():
                        unlock_date = str(row.get('解禁时间', row.get('release_date', ''))).strip()[:10]
                        if unlock_date != date_str:
                            continue
                        code = str(row.get('股票代码', row.get('stock_code', ''))).strip()
                        name = str(row.get('股票名称', row.get('stock_name', ''))).strip()
                        count = row.get('解禁数量', row.get('release_count', ''))
                        ratio = row.get('占总股本比例', row.get('ratio', ''))
                        detail = f'解禁数量：{count}股' if count else '限售股解禁'
                        if ratio:
                            detail += f'，占总股本：{ratio}'
                        events.append(self._make_event(
                            date_str, '09:30', '解禁', f'{name}({code}) 限售股解禁',
                            detail, code, name,
                            {'unlock_count': str(count), 'ratio': str(ratio)}, 4
                        ))
            except Exception as e:
                print(f"[投资日历] 解禁数据失败: {e}", flush=True)
        except ImportError:
            pass
        return events

    def _get_report_events(self, date_str: str) -> List[Dict]:
        """财报预约披露日"""
        events = []
        try:
            import akshare as ak
            try:
                # 业绩预告/预约披露
                df = ak.stock_yjbb_em(date=date_str.replace('-', ''))
                if df is None:
                    return events
                if hasattr(df, 'empty') and not df.empty:
                    for _, row in df.head(30).iterrows():
                        code = str(row.get('股票代码', '')).strip()
                        name = str(row.get('股票简称', '')).strip()
                        report_type = str(row.get('报告期', '')).strip()
                        events.append(self._make_event(
                            date_str, '', '财报', f'{name}({code}) 披露{report_type}',
                            f'定期报告预约披露日', code, name,
                            {'report_type': report_type}, 3
                        ))
            except Exception:
                pass  # akshare财报接口不稳定，静默处理，返回空列表
        except ImportError:
            pass
        return events

    def _get_macro_events(self, date_str: str) -> List[Dict]:
        """宏观经济数据公布（CPI/PMI/社融/MLF/LPR等）"""
        events = []
        try:
            import akshare as ak
            try:
                # 财经日历（宏观事件）
                df = ak.news_economic_baidu()
                if df is not None and not df.empty:
                    for _, row in df.iterrows():
                        event_date = str(row.get('日期', row.get('date', ''))).strip()[:10]
                        if event_date != date_str:
                            continue
                        title = str(row.get('事件', row.get('event', ''))).strip()
                        time_str = str(row.get('时间', row.get('time', ''))).strip()[:5]
                        importance = row.get('重要性', row.get('importance', 3))
                        if title:
                            events.append(self._make_event(
                                date_str, time_str or '', '宏观', title,
                                str(row.get('前值', '')) + ' ' + str(row.get('预测值', '')),
                                '', '', {'importance': int(importance) if importance else 3},
                                int(importance) if importance else 3
                            ))
            except Exception as e:
                print(f"[投资日历] 宏观数据失败: {e}", flush=True)
        except ImportError:
            pass

        # LPR每月20日（遇节假日顺延）
        try:
            d = datetime.strptime(date_str, '%Y-%m-%d')
            if d.day == 20:
                events.append(self._make_event(
                    date_str, '09:15', '宏观', 'LPR利率公布',
                    '全国银行间同业拆借中心公布贷款市场报价利率(LPR)',
                    '', '', {'data_type': 'LPR'}, 5
                ))
        except Exception:
            pass
        return events

    def _get_special_events(self, date_str: str) -> List[Dict]:
        """重要事件：行业大会、政策发布会、国际事件"""
        events = []
        # 事件类型映射（本地数据类型 → UI显示类型）
        TYPE_MAP = {
            'ipo_apply': '新股', 'ipo_list': '新股',
            'report': '财报', 'unlock': '解禁',
            'macro': '宏观', 'industry_event': '行业活动',
            'company_event': '公司活动', 'policy': '政策发布',
            'meeting': '公司活动', 'dividend': '事件',
            'convert_bond': '事件', 'other': '事件',
        }
        # 从本地数据文件补充（如果有）
        try:
            local_file = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'data', 'investment_calendar.py'
            )
            if os.path.exists(local_file):
                try:
                    from data.investment_calendar import get_calendar_by_date
                    local_day = get_calendar_by_date(date_str)
                    local_events = local_day.get('events', []) if isinstance(local_day, dict) else []
                    if local_events:
                        for ev in local_events:
                            if isinstance(ev, dict):
                                raw_type = ev.get('type', '事件')
                                mapped_type = TYPE_MAP.get(raw_type, raw_type if raw_type in ['新股','解禁','财报','宏观','事件','行业活动','公司活动','政策发布'] else '事件')
                                events.append(self._make_event(
                                    date_str,
                                    str(ev.get('time', '')),
                                    mapped_type,
                                    ev.get('title', ev.get('event', '')),
                                    ev.get('detail', ev.get('description', '')),
                                    ev.get('stock_code', ''),
                                    ev.get('stock_name', ''),
                                    ev.get('extra', {}),
                                    ev.get('importance', 3)
                                ))
                except Exception as e:
                    print(f"[投资日历] 本地日历数据读取失败: {e}", flush=True)
        except Exception:
            pass
        return events

    def _make_event(self, date: str, time_str: str, event_type: str,
                    title: str, detail: str, stock_code: str = '',
                    stock_name: str = '', extra: Dict = None, importance: int = 3) -> Dict:
        """构建标准日历事件"""
        event_id = f"{date}_{event_type}_{hash(title + stock_code) % 100000}"
        return {
            'event_id': event_id,
            'date': date,
            'time': time_str,
            'type': event_type,
            'title': title,
            'detail': detail,
            'stock_code': stock_code,
            'stock_name': stock_name,
            'extra': extra or {},
            'importance': importance,
        }

    def refresh_all(self):
        """强制刷新所有缓存（每日开盘前调用）"""
        self._cache.clear()
        self._cache_time = 0
        print("[投资日历] 缓存已刷新", flush=True)

    def auto_update_if_needed(self):
        """每日开盘前自动更新检查"""
        now = datetime.now()
        today_str = now.strftime('%Y-%m-%d')
        cache_date = datetime.fromtimestamp(self._cache_time).strftime('%Y-%m-%d') if self._cache_time else ''
        if cache_date != today_str and now.hour >= CALENDAR_CONFIG.get('auto_update_hour', 8):
            self.refresh_all()
            return True
        return False


# ============================================================
# 单例
# ============================================================
_provider_instance = None

def get_calendar_provider() -> CalendarDataProvider:
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = CalendarDataProvider()
    return _provider_instance
