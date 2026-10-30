# -*- coding: utf-8 -*-
"""
模块3：今日涨停
- 数据来源：东方财富全市场行情 + 涨停池接口（获取真实首次封板时间）
- 字段：股票名称 | 股票代码 | 现价 | 涨幅 | 市值 | 题材 | 发现时间
  （「振幅」列已按用户要求删除：push2ex 接口无最高/最低价，该列恒为 0.00%）
- 题材：选股雷达同源数据 services/concept_matcher（非 stock_keywords.json）
- 市值：东财 f20 总市值(亿)
- 仅点击"股票名称"单元格跳转个股分析
- 有多少显示多少，不限制TOP
- 发现时间：使用东财涨停池接口 fbt（首次封板时间），而非程序打开时间
"""
import os
import json
import requests
from datetime import datetime, date

from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from .base import (
    fetch_ctrl_cached,
    BattleModuleBase, make_table, set_table_item,
    pct_color, format_pct, BC, HeaderSorter,
    fetch_ctrl_for, attach_ctrl, CTRL_COL_TITLE,
)
from .widget_common import make_add_button, get_radar_theme

# 列定义
COL_NAME, COL_CODE, COL_PRICE, COL_PCT = 0, 1, 2, 3
COL_MV, COL_THEME = 4, 5
COL_CTRL = 6
HEADER_LABELS = ['股票名称', '股票代码', '现价', '涨幅', '市值', '题材', CTRL_COL_TITLE]


def _format_zt_time(fbt_raw):
    """将东财涨停池 fbt 字段转换为 'HH:MM' 格式。
    fbt 是整数，格式类似 HHMMSS（可能省略前导0），如 92500 表示 09:25:00
    """
    if not fbt_raw:
        return None
    try:
        s = str(int(fbt_raw)).zfill(6)
        if len(s) != 6:
            return None
        hh = s[:2]
        mm = s[2:4]
        return f"{hh}:{mm}"
    except (ValueError, TypeError):
        return None


class LimitUpWidget(BattleModuleBase):
    """今日涨停模块"""

    # 点击股票名称 -> 跳转个股分析(code, name)
    stock_clicked = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__('🔥 今日涨停', parent)
        self._stocks = []
        # 当日发现持久化：发现时间列 + 盘中涨停股当日保留（炸板也不删）
        self._found_time = {}       # {code: 'HH:MM'}
        self._persist_rows = {}     # {code: row_dict}
        self._persist_date = None
        # 发现时间持久化到 DuckDB：程序重启后恢复今天的真实封板时间
        from services.discovery_time_db import MOD_LIMIT_UP
        self._db_module = MOD_LIMIT_UP
        self._load_found_time_from_db()
        self._build_content()
        QTimer.singleShot(200, self.refresh)
        self.start_refresh(45000)  # 45秒刷新

    def _build_content(self):
        self.table = make_table(7, HEADER_LABELS)
        # 列宽按「有多少字显示多少字」给足（「振幅」列已删）
        # 原「涨幅」列只有 65px，扣除 item 左右各 8px 内边距后只剩 49px，
        # 装不下 +29.68%（约 84px），所以截图里被截成 +29...
        self.table.setColumnWidth(COL_NAME, 92)
        self.table.setColumnWidth(COL_CODE, 86)
        self.table.setColumnWidth(COL_PRICE, 84)
        self.table.setColumnWidth(COL_PCT, 104)
        self.table.setColumnWidth(COL_MV, 84)
        # 「控盘」列插到末尾后，stretchLastSection 会把控盘列撑开，
        # 所以改成显式指定「题材」列吃剩余宽度（与日K建仓表同一做法）
        self.table.setColumnWidth(COL_CTRL, 80)
        from PyQt6.QtWidgets import QHeaderView
        _h = self.table.horizontalHeader()
        _h.setStretchLastSection(False)
        _h.setSectionResizeMode(COL_THEME, QHeaderView.ResizeMode.Stretch)
        self.content_layout.addWidget(self.table, 1)
        # 仅点击股票名称跳转，其他列不跳转
        self.table.cellClicked.connect(self._on_cell_clicked)
        # 右键菜单：添加到自选
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.sorter = HeaderSorter(
            self.table,
            keys={
                0: lambda r: r['name'],
                1: lambda r: r['code'],
                2: lambda r: r['price'],
                3: lambda r: r['pct'],
                4: lambda r: r.get('mv', 0),
                5: lambda r: r.get('_theme', ''),
                6: lambda r: ((r.get('ctrl') or {}).get('score') or 0),
            },
            getter=lambda: self._stocks,
            render=self._render_rows,
        )

    def refresh(self):
        self.set_status('加载中...')
        self.run_async(
            self._fetch_limit_up,
            self._on_loaded,
            self._on_failed,
        )

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
            print(f'[今日涨停] 涨停池接口获取失败: {e}', flush=True)
            return {}

    @staticmethod
    def _fetch_via_push2ex():
        """[B-FALLBACK] push2ex 涨停池专用接口降级源：
        主源 push2delay 被封时，直接用 getTopicZTPool 当日涨停池填表。
        返回 rows list（与主源结构一致），失败返回空 list。
        字段映射：c->code, n->name, p/1000->price, zdp->pct, ltsz/1e8->mv,
                  hybk->industry, fbt->real_found_time（首次封板时间）。
        振幅无数据填 0.0。"""
        import requests as _req
        from datetime import datetime as _dt
        today = _dt.now().strftime('%Y%m%d')
        url = "http://push2ex.eastmoney.com/getTopicZTPool"
        params = {
            'ut': '7eea3edcaed734bea9cbfc24409ed989',
            'dpt': 'wz.ztzt', 'Pageindex': '0', 'pagesize': '500',
            'sort': 'fbt:asc', 'date': today,
            '_': str(int(_dt.now().timestamp() * 1000)),
        }
        try:
            r = _req.get(url, params=params, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://quote.eastmoney.com/ztb/detail',
            }, timeout=10)
            j = r.json()
            pool = (j.get('data') or {}).get('pool') or []
        except Exception as e:
            print(f'[今日涨停] push2ex 降级接口失败: {e}', flush=True)
            return []
        rows = []
        for it in pool:
            try:
                code = it.get('c', '')
                name = it.get('n', '')
                if not code or not name:
                    continue
                price = (float(it.get('p', 0) or 0)) / 1000.0
                pct = float(it.get('zdp', 0) or 0)
                mv = float(it.get('ltsz', 0) or 0) / 1e8
                industry = it.get('hybk', '') or ''
                fbt = int(it.get('fbt', 0) or 0)
                hh, mm = fbt // 10000, (fbt // 100) % 100
                real_t = f'{hh:02d}:{mm:02d}' if hh < 24 else None
                rows.append({
                    'code': code, 'name': name,
                    'price': round(price, 2), 'pct': round(pct, 2),
                    'amp': 0.0,                       # push2ex 无最高最低价，振幅留0
                    'mv': round(mv, 1), 'industry': industry,
                    'real_found_time': real_t,
                })
            except Exception:
                continue
        rows.sort(key=lambda x: (-x['pct'], x['code']))
        return rows

    @staticmethod
    def _fetch_limit_up():
        """从东方财富获取全市场行情，筛选涨停。
        [B-FALLBACK] 主源 push2delay 失败/为空时自动降级 push2ex 涨停池。
        返回 (rows, source)：source='em' 主源 / 'push2ex' 降级 / 抛异常=全失败"""
        from utils.http_market_data import eastmoney_request

        # 先获取涨停池的真实时间（push2ex 未被封，主源成功时也用它补时间）
        zt_times = LimitUpWidget._fetch_zt_pool_times()

        # 取300只（按涨幅降序），足够覆盖所有涨停
        # f15最高 f16最低 f18昨收 f20总市值 f100行业
        params = {
            'pn': '1', 'pz': '300', 'po': '1', 'np': '1',
            'fltt': '2', 'invt': '2', 'fid': 'f3',
            'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23',
            'fields': 'f12,f14,f2,f3,f15,f16,f18,f20,f100',
        }
        data = eastmoney_request('/api/qt/clist/get', params, timeout=15)
        items = None
        if data and isinstance(data, dict):
            items = data.get('data', {}).get('diff') or []
        if not items:
            # [B-FALLBACK] 主源失败 → 自动降级 push2ex
            print('[今日涨停] 主源 push2delay 无数据，降级 push2ex 涨停池', flush=True)
            fb = LimitUpWidget._fetch_via_push2ex()
            if fb:
                return fb, 'push2ex'
            raise Exception('主源与降级源均无数据')

        result = []
        for it in items:
            if not it or not isinstance(it, dict):
                continue
            try:
                pct = float(it.get('f3', 0) or 0)
            except (ValueError, TypeError):
                continue
            code = it.get('f12', '')
            name = it.get('f14', '')
            if not code or not name:
                continue
            # 涨停判定按板块真实涨停规则（不再统一9.8）：
            #   主板(60/00) 10%  → 9.8
            #   创业板(300/301)/科创板(688/689) 20% → 19.5
            #   北交所(8/4/920) 30% → 29.5
            # 避免创业板/科创板涨9.8%~19.4%的非涨停股被误选
            if code.startswith(('300', '301', '688', '689')):
                limit_threshold = 19.5
            elif code.startswith(('8', '4', '920')):
                limit_threshold = 29.5
            else:
                limit_threshold = 9.8
            if pct < limit_threshold:
                continue
            def _f(k):
                try:
                    return float(it.get(k, 0) or 0)
                except (ValueError, TypeError):
                    return 0.0
            price = _f('f2')
            high = _f('f15')
            low = _f('f16')
            prev = _f('f18')
            mv = _f('f20') / 1e8  # 总市值(元)->亿
            # 振幅 = (最高-最低)/昨收*100%
            amp = round((high - low) / prev * 100, 2) if prev > 0 else 0.0
            industry = it.get('f100', '') or ''
            # 真实涨停时间（从涨停池接口获取）
            real_time = zt_times.get(code, None)
            result.append({
                'code': code,
                'name': name,
                'price': round(price, 2),
                'pct': round(pct, 2),
                'amp': amp,
                'mv': round(mv, 1),
                'industry': industry,
                'real_found_time': real_time,  # 真实首次封板时间
            })

        # 按涨幅降序，同涨幅按代码
        result.sort(key=lambda x: (-x['pct'], x['code']))
        # 控盘度：只读本地 kline_cache，无网络兜底（在 run_async 线程里跑）
        fetch_ctrl_for(result)
        return result, 'em'

    def _merge_persist_with_real_time(self, fresh_rows, key='code'):
        """自定义合并：优先使用真实涨停时间，而非当前时间。
        新股票：如果有real_found_time用它，否则用当前时间。
        老股票：保留已有的发现时间。
        """
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
                # 优先使用真实涨停时间，没有则用当前时间
                real_t = r.get('real_found_time')
                found_t = real_t if real_t else now_hm
                self._found_time[k] = found_t
                # 写库（INSERT OR IGNORE）：重启后还原真实封板时间
                self._persist_new_found_time(k, found_t)
        return list(self._persist_rows.values())

    def _on_loaded(self, result):
        # [B-FALLBACK] result 是 (rows, source)：source='em'/'push2ex'
        if isinstance(result, tuple) and len(result) == 2:
            stocks, source = result
        else:
            stocks, source = result, 'em'
        # 题材：和选股雷达一致，从涨停原因数据库取
        from data.limit_up_reason_db import get_last_limit_up_reason
        for s in stocks:
            reason, _, _, _ = get_last_limit_up_reason(s['code'])
            if reason:
                # 过滤无效板型词
                tags = []
                for t in reason.split('+'):
                    t = t.strip()
                    if t and not t.endswith('板') and len(t) > 2:
                        tags.append(t)
                s['_theme'] = '+'.join(tags) if tags else reason
            else:
                s['_theme'] = s.get('industry', '--')
        # 合并到当日持久化表：使用真实涨停时间（优先）或当前时间
        self._stocks = self._merge_persist_with_real_time(stocks, key='code')
        # 按涨幅降序（持久化表中历史股也一起排）
        self._stocks.sort(key=lambda x: (-(x.get('pct') or 0), x.get('code', '')))
        self._render_rows()
        # 控盘度：持久化合并出来的老股没有 ctrl，后台补算（缓存命中几乎 0 成本）
        self.ctrl_fill_and_async(self._stocks, self._render_rows)
        self.title_label.setText(f'🔥 今日涨停（{len(self._stocks)}只·当日保留）')
        # [B-FALLBACK] 右上角：更新时间 + 数据源标识（降级时醒目标注）
        from datetime import datetime as _dt
        now = _dt.now().strftime('%H:%M:%S')
        src_label = '东财' if source == 'em' else 'push2ex降级'
        self.set_update_time(f'{now} · {src_label}')

    def _render_rows(self):
        fetch_ctrl_cached(self._stocks)
        stocks = self._stocks
        self.table.clearSpans()
        self.table.setRowCount(len(stocks))
        right = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        for row, s in enumerate(stocks):
            set_table_item(self.table, row, COL_NAME, s['name'], BC.RED, bold=True)
            set_table_item(self.table, row, COL_CODE, s['code'], '#000000')
            set_table_item(self.table, row, COL_PRICE, f"{s['price']:.2f}", '#000000', align=right)
            set_table_item(self.table, row, COL_PCT, format_pct(s['pct']), BC.RED, bold=True, align=right)
            # 市值（亿）
            mv = s.get('mv', 0) or 0
            set_table_item(self.table, row, COL_MV, f'{mv:.0f}亿' if mv > 0 else '--', '#000000', align=right)
            # 题材
            set_table_item(self.table, row, COL_THEME, s.get('_theme', '--'), BC.RED, bold=True)
            # 控盘（新增列，填在最后一列）
            attach_ctrl(self.table, stocks, col=COL_CTRL)


    def _show_context_menu(self, pos):
        """右键菜单：添加到自选"""
        from PyQt6.QtWidgets import QMenu
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        it = self.table.item(row, COL_CODE)
        code = it.text() if it else ''
        nit = self.table.item(row, COL_NAME)
        name = nit.text() if nit else code
        menu = QMenu(self.table)
        add_action = menu.addAction('➕ 添加到自选')
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == add_action and code:
            try:
                from core.watchlist import get_watchlist_manager
                mgr = get_watchlist_manager()
                if not any(str(x.get('code','')) == code for x in mgr.stocks):
                    mgr.stocks.append({'code': code, 'name': name})
                    mgr.save()
                    print(f'[今日涨停] 已添加自选: {code} {name}', flush=True)
            except Exception as e:
                print(f'[今日涨停] 添加自选失败: {e}', flush=True)

    def _on_cell_clicked(self, row, col):
        """仅点击股票名称跳转个股分析"""
        if col != COL_NAME:
            return
        it = self.table.item(row, COL_CODE)
        code = it.text() if it else ''
        nit = self.table.item(row, COL_NAME)
        name = nit.text() if nit else code
        if code:
            self.stock_clicked.emit(code, name)

    def _on_failed(self, err):
        # [C-KEEP] 失败时不清表：保留上次成功渲染的数据，仅右上角标注延迟
        from datetime import datetime as _dt
        now = _dt.now().strftime('%H:%M:%S')
        self.set_update_time(f'{now} · 数据延迟')
        # 标题加"（数据可能延迟）"标注，不覆盖已有表格内容
        try:
            cur = self.title_label.text()
            if '（数据可能延迟）' not in cur:
                self.title_label.setText(cur + '（数据可能延迟）')
        except Exception:
            pass
