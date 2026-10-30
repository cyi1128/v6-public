# -*- coding: utf-8 -*-
"""
模块4：板块异动
- 不是简单板块涨幅榜，检测"突然+同板块+多只股票同步上涨"
- 数据来源：东方财富行业板块（m:90+t:2）+ 板块成分股（仅全A）
- 异动判定：上涨家数增加 / 板块涨幅加速 / 板块共振 / 多只涨停
- 新增列：异动次数（近10分钟内触发异动次数）
- 异动板块当日保留不清空，便于复盘；程序重启时重新覆盖（内存态）
- 支持列头三态排序；30秒刷新
"""
import time
from collections import deque
from datetime import date

from PyQt6.QtCore import Qt, QTimer

from .base import (
    BattleModuleBase, make_table, set_table_item,
    pct_color, format_pct, BC, HeaderSorter, layout_found_time_last,
)

# 历史快照最大保留数量（约30s*5=2.5分钟）
MAX_HISTORY = 5
# 异动阈值
MIN_CHANGE_PCT = 1.2        # 最低板块涨幅
MIN_ACCELERATION = 0.15     # 最低加速幅度（%）
MIN_UP_RATIO = 0.55         # 最低上涨家数占比
MIN_LIMIT_UP_FOR_SPIKE = 1  # 涨停数触发异动的最低值（配合其他条件）
# 异动次数统计窗口（秒）
SPIKE_COUNT_WINDOW = 600


def _is_a_share(code):
    """仅保留全A股（剔除北向/港股/美股等）"""
    if not code:
        return False
    return code[:2] in ('60', '00', '30', '68') or code[:1] in ('8', '4')


class SectorSpikeWidget(BattleModuleBase):
    """板块异动模块"""

    def __init__(self, parent=None):
        super().__init__('⚡ 板块异动', parent)
        self._sectors = []
        self._history = {}                 # {sector_name: deque 快照}
        self._retained = {}                # {sector_name: 最近一次异动记录} 当日保留
        self._spike_clicks = {}            # {sector_name: [ts,...]} 异动触发时间戳
        # 当日发现持久化：板块首次触发异动的时间（盘中不变）
        self._spike_first_time = {}        # {sector_name: 'HH:MM'}
        self._persist_date = None          # 'YYYY-MM-DD' 跨日清空
        # 发现时间持久化到 DuckDB：程序重启后恢复今天板块首次异动时间
        from services.discovery_time_db import MOD_SECTOR_SPIKE, load_today as _db_load_today
        self._db_module = MOD_SECTOR_SPIKE
        self._spike_first_time = _db_load_today(MOD_SECTOR_SPIKE)
        self._persist_date = date.today().isoformat()
        self._build_content()
        QTimer.singleShot(250, self.refresh)
        self.start_refresh(30000)  # 30秒刷新

    def _build_content(self):
        self.table = make_table(8, ['板块', '涨幅', '上涨家数', '涨停', '异动次数', '快速上涨', '领涨股', '发现时间'])
        self.table.setColumnWidth(0, 90)
        self.table.setColumnWidth(1, 60)
        self.table.setColumnWidth(2, 65)
        self.table.setColumnWidth(3, 45)
        self.table.setColumnWidth(4, 70)
        self.table.setColumnWidth(5, 60)
        self.table.setColumnWidth(6, 85)
        # 发现时间列(第7列)固定80px，板块列(第0列)Stretch吸收剩余空间
        layout_found_time_last(self.table, 7, 0, 80)
        self.content_layout.addWidget(self.table, 1)
        self.sorter = HeaderSorter(
            self.table,
            keys={
                0: lambda r: r['name'],
                1: lambda r: r['change_pct'],
                2: lambda r: r['up_count'],
                3: lambda r: r['limit_up'],
                4: lambda r: r.get('spike_count', 0),
                5: lambda r: r.get('fast_rising', 0),
                6: lambda r: r.get('leader') or '',
                7: lambda r: self._spike_first_time.get(r.get('name', ''), '--'),
            },
            getter=lambda: self._sectors,
            render=self._render_rows,
        )

    def refresh(self):
        self.set_status('监测中...')
        self.run_async(
            self._fetch_and_analyze,
            self._on_loaded,
            self._on_failed,
        )

    def _fetch_and_analyze(self):
        """获取板块数据并计算异动，合并当日保留板块"""
        from utils.http_market_data import eastmoney_request
        from datetime import date as _date, datetime as _dt

        # 跨交易日自动清空当日保留数据
        today = _date.today().isoformat()
        if self._persist_date != today:
            self._retained = {}
            self._spike_clicks = {}
            self._history = {}
            self._persist_date = today
            # 从库里恢复今天已有的板块首次异动时间（重启不丢）
            from services.discovery_time_db import MOD_SECTOR_SPIKE, load_today as _db_load_today
            self._spike_first_time = _db_load_today(MOD_SECTOR_SPIKE)

        # 1. 获取全部行业板块（按涨幅降序，取前50）
        params = {
            'pn': '1', 'pz': '50', 'po': '1', 'np': '1',
            'fltt': '2', 'invt': '2', 'fid': 'f3',
            'fs': 'm:90+t:2',
            'fields': 'f12,f14,f2,f3,f62,f104,f105,f128,f207',
        }
        data = eastmoney_request('/api/qt/clist/get', params, timeout=12)
        if not data or not isinstance(data, dict):
            raise Exception('东方财富板块数据格式错误')
        items = data.get('data', {}).get('diff', [])
        if not items:
            raise Exception('无板块数据')

        now = time.time()
        sectors = []
        for it in items:
            if not it or not isinstance(it, dict):
                continue
            name = it.get('f14', '')
            if not name:
                continue
            try:
                change_pct = float(it.get('f3', 0) or 0)
            except (ValueError, TypeError):
                change_pct = 0.0
            try:
                up_count = int(it.get('f104', 0) or 0)
            except (ValueError, TypeError):
                up_count = 0
            try:
                down_count = int(it.get('f105', 0) or 0)
            except (ValueError, TypeError):
                down_count = 0
            try:
                limit_up = int(it.get('f128', 0) or 0)
            except (ValueError, TypeError):
                limit_up = 0
            leader = it.get('f207', '') or ''
            sector_code = it.get('f12', '')

            total = up_count + down_count
            up_ratio = (up_count / total) if total > 0 else 0

            sectors.append({
                'name': name,
                'code': sector_code,
                'change_pct': round(change_pct, 2),
                'up_count': up_count,
                'down_count': down_count,
                'total': total,
                'up_ratio': round(up_ratio, 3),
                'limit_up': limit_up,
                'leader': leader,
                'fast_rising': 0,
                'anomaly_score': 0,
                'acceleration': 0,
                'ts': now,
            })

        # 2. 更新历史并计算加速
        for s in sectors:
            name = s['name']
            if name not in self._history:
                self._history[name] = deque(maxlen=MAX_HISTORY)
            hist = self._history[name]
            if len(hist) >= 1:
                prev = hist[-1]
                s['acceleration'] = round(s['change_pct'] - prev['change_pct'], 3)
                s['up_delta'] = s['up_count'] - prev['up_count']
            else:
                s['acceleration'] = 0
                s['up_delta'] = 0
            hist.append({'change_pct': s['change_pct'], 'up_count': s['up_count'], 'ts': now})

        # 3. 异动筛选
        spike_now = set()
        for s in sectors:
            if s['change_pct'] < MIN_CHANGE_PCT:
                continue
            cond_a = s['up_delta'] >= 2
            cond_b = s['acceleration'] >= MIN_ACCELERATION
            cond_c = (s['up_ratio'] >= MIN_UP_RATIO and s['limit_up'] >= MIN_LIMIT_UP_FOR_SPIKE)
            cond_d = s['limit_up'] >= 3
            if not (cond_a or cond_b or cond_c or cond_d):
                continue
            score = 0
            score += min(30, s['change_pct'] * 6)
            score += min(25, max(0, s['acceleration']) * 30)
            score += min(20, s['up_ratio'] * 20)
            score += min(25, s['limit_up'] * 8)
            s['anomaly_score'] = round(min(100, score), 1)
            spike_now.add(s['name'])

        # 4. 更新异动次数与当日保留
        sector_map = {s['name']: s for s in sectors}
        for name in spike_now:
            clicks = self._spike_clicks.setdefault(name, [])
            clicks.append(now)
        # 清理窗口外时间戳
        for name in list(self._spike_clicks.keys()):
            self._spike_clicks[name] = [t for t in self._spike_clicks[name] if now - t <= SPIKE_COUNT_WINDOW]

        # 本次新触发：刷新保留记录；新板块记录首次异动时间
        now_hm = _dt.now().strftime('%H:%M')
        from services.discovery_time_db import MOD_SECTOR_SPIKE, save_today as _db_save_today
        for name in spike_now:
            rec = dict(sector_map[name])
            rec['spike_count'] = len(self._spike_clicks.get(name, []))
            self._retained[name] = rec
            if name not in self._spike_first_time:
                self._spike_first_time[name] = now_hm
                # 写库（INSERT OR IGNORE）：重启后还原板块首次异动时间
                _db_save_today(MOD_SECTOR_SPIKE, name, now_hm)
        # 保留但本轮未触发：更新异动次数（仍在窗口内），数据沿用上次
        for name, rec in self._retained.items():
            if name not in spike_now:
                rec['spike_count'] = len(self._spike_clicks.get(name, []))

        spike_sectors = list(self._retained.values())

        # 5. 对前15个异动板块获取全A成分股快速上涨数量
        spike_sectors.sort(key=lambda x: (-x['anomaly_score'], -x['spike_count'], -x['change_pct']))
        for s in spike_sectors[:15]:
            try:
                s['fast_rising'] = self._fetch_fast_rising(s['code'])
            except Exception:
                s['fast_rising'] = 0

        # 6. 最终排序：异动强度 > 异动次数 > 板块涨幅
        spike_sectors.sort(key=lambda x: (-x['anomaly_score'], -x['spike_count'], -x['change_pct']))
        return spike_sectors

    @staticmethod
    def _fetch_fast_rising(sector_code):
        """获取板块成分股中涨幅>=3%的全A股票数量"""
        from utils.http_market_data import eastmoney_request
        if not sector_code:
            return 0
        params = {
            'pn': '1', 'pz': '200', 'po': '1', 'np': '1',
            'fltt': '2', 'invt': '2', 'fid': 'f3',
            'fs': f'b:{sector_code}',
            'fields': 'f12,f14,f3',
        }
        data = eastmoney_request('/api/qt/clist/get', params, timeout=8)
        if not data or not isinstance(data, dict):
            return 0
        items = data.get('data', {}).get('diff', [])
        if not items:
            return 0
        count = 0
        for it in items:
            code = it.get('f12', '')
            if not _is_a_share(code):
                continue  # 只筛选全A股
            try:
                pct = float(it.get('f3', 0) or 0)
                if pct >= 3.0:
                    count += 1
            except (ValueError, TypeError):
                continue
        return count

    def _on_loaded(self, sectors):
        self._sectors = sectors
        self._render_rows()
        self.title_label.setText(f'⚡ 板块异动（{len(sectors)}个·当日保留）')
        self.set_update_time()

    def _render_rows(self):
        sectors = self._sectors
        self.table.clearSpans()
        self.table.setRowCount(len(sectors))
        for row, s in enumerate(sectors):
            score = s['anomaly_score']
            if score >= 70:
                name_color = BC.ORANGE
            elif score >= 50:
                name_color = BC.YELLOW
            else:
                name_color = BC.TEXT
            set_table_item(self.table, row, 0, s['name'], name_color, bold=True)
            set_table_item(self.table, row, 1, format_pct(s['change_pct']),
                           pct_color(s['change_pct']), bold=True,
                           align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
            up_text = f"{s['up_count']}/{s['total']}" if s['total'] > 0 else str(s['up_count'])
            set_table_item(self.table, row, 2, up_text, BC.TEXT,
                           align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
            lu_color = BC.RED if s['limit_up'] > 0 else BC.TEXT3
            set_table_item(self.table, row, 3, str(s['limit_up']), lu_color, bold=(s['limit_up'] > 0),
                           align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
            cnt = s.get('spike_count', 0)
            cnt_color = BC.RED if cnt >= 3 else (BC.YELLOW if cnt >= 1 else BC.TEXT3)
            set_table_item(self.table, row, 4, f'{cnt}次', cnt_color, bold=(cnt >= 3),
                           align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
            fast_color = BC.YELLOW if s.get('fast_rising', 0) > 0 else BC.TEXT3
            set_table_item(self.table, row, 5, str(s.get('fast_rising', 0)), fast_color,
                           align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
            set_table_item(self.table, row, 6, s.get('leader') or '--', BC.CYAN)
            # 发现时间（板块首次异动时间，盘中不变）
            found_t = self._spike_first_time.get(s.get('name', ''), '--')
            set_table_item(self.table, row, 7, found_t, BC.CYAN, bold=True,
                           align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)

    def _on_failed(self, err):
        self.set_status('数据超时')
        if not self._sectors:
            self.table.setRowCount(1)
            set_table_item(self.table, 0, 0, '暂无异动', BC.TEXT3,
                           align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
            self.table.setSpan(0, 0, 1, 8)
