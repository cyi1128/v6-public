# -*- coding: utf-8 -*-
"""
模块：龙头梯队 - 个股强度Top20
- 只主板
- 按资金净流入+涨幅+题材共振排序
- 每只股票只出现一次，名称旁显示聚合题材标签
- 发现时间：涨停股用真实首次封板时间，非涨停股用首次进入强势榜时间
"""
import os
import requests
from datetime import datetime, date

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel

from .base import (
    BattleModuleBase, make_table, set_table_item,
    BC,
)
from .limit_up_widget import _format_zt_time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MAIN_PREFIX = ('600', '601', '603', '605', '000', '001', '002', '003')


def is_main_board(code: str) -> bool:
    return code.startswith(MAIN_PREFIX)


HEADER_LABELS = ['个股(题材)', '现价', '涨跌幅', '主力净流入', '核心逻辑', '跟涨股', '发现时间']
COL_FOUND_TIME = 6


class LeaderLadderWidget(BattleModuleBase):
    """龙头梯队：主板强势个股Top20"""

    def __init__(self, parent=None):
        super().__init__('🔗 题材联动', parent)
        self._sort_col = 2  # 默认按涨跌幅
        self._sort_reverse = True
        # 当日发现持久化：发现时间列 + 盘中强势股当日保留（后续回落也不删）
        self._found_time = {}       # {code: 'HH:MM'}
        self._persist_rows = {}     # {code: row_dict}
        self._persist_date = None
        # 发现时间持久化到 DuckDB：程序重启后恢复今天的真实发现时间
        from services.discovery_time_db import MOD_LEADER_LADDER
        self._db_module = MOD_LEADER_LADDER
        self._load_found_time_from_db()
        self._build_content()
        QTimer.singleShot(350, self.refresh)
        self.start_refresh(60000)

    def _build_content(self):
        # 表格
        self.table = make_table(7, HEADER_LABELS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 220)
        self.table.setColumnWidth(1, 60)
        self.table.setColumnWidth(2, 70)
        self.table.setColumnWidth(3, 80)
        self.table.setColumnWidth(4, 140)
        self.table.setColumnWidth(COL_FOUND_TIME, 60)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.content_layout.addWidget(self.table, 1)

    def _on_sort_changed(self, idx):
        pass  # 表头排序在_on_loaded里绑定

    def _connect_header_sort(self):
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)

    def _on_header_clicked(self, col):
        if col == self._sort_col:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_col = col
            self._sort_reverse = True
        self.refresh()

    def refresh(self):
        self.set_status('统计中...')
        self.run_async(self._build_top, self._on_loaded, self._on_failed)

    @staticmethod
    def _fetch_zt_pool_times():
        """从东财涨停池接口获取所有涨停股的首次封板时间。
        返回 {code: 'HH:MM'} 映射，失败返回空字典。
        """
        today = date.today().strftime('%Y%m%d')
        url = "http://push2ex.eastmoney.com/getTopicZTPool"
        params = {
            'ut': '7eea3edcaed734bea9cbfc24409ed989',
            'dpt': 'wz.ztzt',
            'Pageindex': '0',
            'pagesize': '500',
            'sort': 'fbt:asc',
            'date': today,
            '_': str(int(datetime.now().timestamp() * 1000)),
        }
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://quote.eastmoney.com/ztb/detail',
        }
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            data = resp.json()
            pool = (data.get('data') or {}).get('pool', []) or []
            result = {}
            for item in pool:
                code = item.get('c', '')
                fbt = item.get('fbt', 0)
                t = _format_zt_time(fbt)
                if code and t:
                    result[code] = t
            return result
        except Exception as e:
            print(f'[题材联动] 涨停池接口获取失败: {e}', flush=True)
            return {}

    @staticmethod
    def _fetch_strong():
        from utils.http_market_data import eastmoney_request
        # f62: 主力净流入, f12代码,f14名称,f2现价,f3涨跌幅,f100行业
        params = {
            'pn': '1', 'pz': '500', 'po': '1', 'np': '1',
            'fltt': '2', 'invt': '2', 'fid': 'f62',  # 按主力净流入排序
            'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23',
            'fields': 'f12,f14,f2,f3,f62,f100',
        }
        data = eastmoney_request('/api/qt/clist/get', params, timeout=15)
        items = (data or {}).get('data', {}).get('diff', []) if isinstance(data, dict) else []
        out = []
        for it in items:
            try:
                pct = float(it.get('f3', 0) or 0)
                net = float(it.get('f62', 0) or 0)
            except:
                continue
            if pct < 3.0:
                continue
            code = it.get('f12', '')
            name = it.get('f14', '')
            price = float(it.get('f2', 0) or 0)
            if price > 10000:
                price = price / 100
            industry = it.get('f100', '') or ''
            out.append({
                'code': code, 'name': name, 'pct': round(pct, 2),
                'price': round(price, 2), 'net': net, 'industry': industry
            })
        return out

    def _filter_market(self, stocks):
        if self._market_filter == 'main':
            return [s for s in stocks if is_main_board(s['code'])]
        elif self._market_filter == 'star':
            return [s for s in stocks if s['code'].startswith(('300', '301', '688', '689'))]
        return stocks

    def _get_themes(self, code):
        """从涨停原因库取该股所有题材"""
        from data.limit_up_reason_db import get_last_limit_up_reason
        reason, _, _, industry = get_last_limit_up_reason(code)
        if reason:
            tags = []
            for t in reason.split('+'):
                t = t.strip()
                if t and not t.endswith('板') and len(t) > 1:
                    tags.append(t)
            return tags, reason
        return [industry], industry

    def _row_sort_key(self, x):
        """根据当前排序列返回排序键，支持发现时间列(字符串HH:MM比较)"""
        if self._sort_col == COL_FOUND_TIME:
            return self._found_time.get(x.get('code', ''), '--')
        sort_map = {0: 'name', 1: 'price', 2: 'pct', 3: 'net', 4: 'core_theme', 5: 'peers'}
        key = sort_map.get(self._sort_col, 'pct')
        val = x.get(key, 0)
        return val if isinstance(val, (int, float)) else str(val)

    def _build_top(self):
        # 获取涨停池的真实时间
        zt_times = self._fetch_zt_pool_times()
        
        all_strong = self._fetch_strong()
        # 只主板
        strong = [s for s in all_strong if is_main_board(s['code'])]
        # 每只股票算题材，聚合标签
        result = []
        for s in strong:
            themes, core = self._get_themes(s['code'])
            s['themes'] = themes
            s['core_theme'] = core
            # 真实涨停时间（如果是涨停股）
            s['real_found_time'] = zt_times.get(s['code'], None)
            # 综合评分：主力净流入(万元) + 涨幅*1000万 + 题材数*500万
            score = s['net'] / 10000 + s['pct'] * 1000 + len(themes) * 500
            s['score'] = score
            result.append(s)
        # 按点击的列排序
        try:
            result.sort(key=self._row_sort_key, reverse=self._sort_reverse)
        except:
            result.sort(key=lambda x: -x['score'])
        # 跟涨股：同行业其他主板股
        by_ind = {}
        for s in result:
            by_ind.setdefault(s['industry'], []).append(s['name'])
        top = result
        for s in top:
            peers = [n for n in by_ind.get(s['industry'], []) if n != s['name']]
            s['peers'] = '/'.join(peers[:3])
        self._last_top = top
        return top

    def _merge_persist_with_real_time(self, fresh_rows, key='code'):
        """自定义合并：涨停股优先使用真实首次封板时间，非涨停股用当前时间。"""
        self._check_date_reset()
        now_hm = datetime.now().strftime('%H:%M')
        for r in fresh_rows:
            k = r.get(key) if isinstance(r, dict) else None
            if k is None:
                continue
            if k in self._persist_rows:
                # 更新行情字段，但不覆盖 _found_time
                self._persist_rows[k].update(r)
            else:
                self._persist_rows[k] = r
                # 涨停股用真实封板时间，非涨停股用当前时间
                real_t = r.get('real_found_time')
                found_t = real_t if real_t else now_hm
                self._found_time[k] = found_t
                # 写库（INSERT OR IGNORE）：重启后还原真实发现时间
                self._persist_new_found_time(k, found_t)
        return list(self._persist_rows.values())

    def _on_loaded(self, top):
        center = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter
        # 合并到当日持久化表：涨停股用真实时间，非涨停股用当前时间
        merged = self._merge_persist_with_real_time(top, key='code')
        # 按当前排序键对合并后的完整列表重新排序
        try:
            merged.sort(key=self._row_sort_key, reverse=self._sort_reverse)
        except Exception:
            merged.sort(key=lambda x: -x.get('score', 0))
        self._last_top = merged
        self.table.setRowCount(len(merged))
        for row, s in enumerate(merged):
            # 个股列：名称 + [题材标签]
            theme_tag = '[' + '/'.join(s['themes'][:3]) + ']' if s['themes'] else ''
            name_text = f"{s['name']}\n{theme_tag}"
            set_table_item(self.table, row, 0, name_text, BC.TEXT_PRIMARY, bold=True, align=center)
            # 现价
            set_table_item(self.table, row, 1, f"{s['price']:.2f}", '#000000', align=center)
            # 涨跌幅
            color = '#000000'
            set_table_item(self.table, row, 2, f"{s['pct']:+.1f}%", color, align=center)
            # 主力净流入
            net_w = s['net'] / 10000
            if net_w > 0:
                net_text = f"+{net_w:.0f}万"
                net_color = '#000000'
            else:
                net_text = f"{net_w:.0f}万"
                net_color = '#000000'
            set_table_item(self.table, row, 3, net_text, net_color, align=center)
            # 核心逻辑
            set_table_item(self.table, row, 4, s['core_theme'], BC.RED, align=center)
            # 跟涨股
            set_table_item(self.table, row, 5, s['peers'] or '--', BC.TEXT, align=center)
            # 发现时间（涨停股用真实封板时间，非涨停股用首次进入强势榜时间）
            found_t = self._found_time.get(s.get('code', ''), '--')
            set_table_item(self.table, row, COL_FOUND_TIME, found_t, BC.CYAN, bold=True, align=center)
        self.title_label.setText(f'🔗 题材联动（{len(merged)}只强势股·当日保留）')
        self.set_update_time()

    def _on_failed(self, err):
        self.set_status('数据超时')
        self.table.setRowCount(1)
        set_table_item(self.table, 0, 0, '暂无数据', BC.TEXT3,
                       align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
        self.table.setSpan(0, 0, 1, 7)
