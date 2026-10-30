# -*- coding: utf-8 -*-
"""C. 把「即时缓存填充」接到 6 个模块的渲染入口 + 竞价快照路径补后台补算。

设计：放在渲染函数最顶部，是唯一覆盖所有装配路径的位置
（快照恢复 / 持久化合并 / 初始恢复 / 定时重绘，未来新增路径也自动覆盖），
且 cached_only 保证在 UI 线程里零计算、零阻塞。
"""
import io
import shutil
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = r'D:\QuantMonitorV6'


def patch(rel, edits, imp_after_def=None):
    """edits: [(old, new, tag)]；imp_after_def: (anchor, insert) 用于补 import。"""
    P = ROOT + '\\' + rel
    raw = open(P, 'rb').read()
    crlf, lf = raw.count(b'\r\n'), raw.count(b'\n') - raw.count(b'\r\n')
    pure_crlf = bool(crlf) and not lf
    shutil.copy2(P, P + '.bak_before_cached')
    s = raw.decode('utf-8')
    if pure_crlf:
        s = s.replace('\r\n', '\n')
    for old, new, tag in edits:
        n = s.count(old)
        assert n == 1, '%s %s 锚点 %d' % (rel, tag, n)
        s = s.replace(old, new, 1)
    # 补 import fetch_ctrl_cached
    if imp_after_def:
        anchor, line = imp_after_def
        if anchor in s and 'fetch_ctrl_cached' not in s.split('\n\n')[0]:
            assert s.count(anchor) == 1, '%s import 锚点 %d' % (rel, s.count(anchor))
            s = s.replace(anchor, anchor + line, 1)
    out = s.replace('\n', '\r\n') if pure_crlf else s
    open(P, 'wb').write(out.encode('utf-8'))
    print('OK %-46s %s' % (rel, 'CRLF' if pure_crlf else 'LF'))


IMP = '    fetch_ctrl_cached,\n'

# 1) 今日涨停：渲染入口即时填 + 合并后补算（持久化表里 DB 恢复的老股没有 ctrl）
patch(r'ui\battle_widgets\limit_up_widget.py',
      [("    def _render_rows(self):\n        stocks = self._stocks\n",
        "    def _render_rows(self):\n        fetch_ctrl_cached(self._stocks)\n        stocks = self._stocks\n",
        'render'),
       ("        self._stocks.sort(key=lambda x: (-(x.get('pct') or 0), x.get('code', '')))\n"
        "        self._render_rows()\n",
        "        self._stocks.sort(key=lambda x: (-(x.get('pct') or 0), x.get('code', '')))\n"
        "        self._render_rows()\n"
        "        # 控盘度：持久化合并出来的老股没有 ctrl，后台补算（缓存命中几乎 0 成本）\n"
        "        self.ctrl_fill_and_async(self._stocks, self._render_rows)\n",
        'onloaded')],
      imp_after_def=('from .base import (\n', IMP))

# 2) 竞价：渲染入口即时填；快照路径（白天看的正是这条）补后台补算
patch(r'ui\battle_widgets\auction_filter_widget.py',
      [("    def _render_rows(self):\n        rows = self._rows\n",
        "    def _render_rows(self):\n        fetch_ctrl_cached(self._rows)\n        rows = self._rows\n",
        'render'),
       ("                self._rows = rows\n"
        "                self._render_rows()\n"
        "                self.set_status(\n"
        "                    f'\u4f11\u5e02 \u00b7 \u6570\u636e\u65e5\u671f {trading_date}",
        "                self._rows = rows\n"
        "                self._render_rows()\n"
        "                self.ctrl_fill_and_async(self._rows, self._render_rows)\n"
        "                self.set_status(\n"
        "                    f'\u4f11\u5e02 \u00b7 \u6570\u636e\u65e5\u671f {trading_date}",
        'snap_v1'),
       ("            self._rows = rows\n"
        "            self._render_rows()\n"
        "            self.set_status(\n"
        "                f'\u4f11\u5e02 \u00b7 \u6570\u636e\u65e5\u671f {trading_date} \u00b7 \u6a21\u5f0f\uff1a\u590d\u76d8 \u00b7 {len(rows)}\u6761')",
        "            self._rows = rows\n"
        "            self._render_rows()\n"
        "            self.ctrl_fill_and_async(self._rows, self._render_rows)\n"
        "            self.set_status(\n"
        "                f'\u4f11\u5e02 \u00b7 \u6570\u636e\u65e5\u671f {trading_date} \u00b7 \u6a21\u5f0f\uff1a\u590d\u76d8 \u00b7 {len(rows)}\u6761')",
        'snap'),
       ("        self._render_rows()\n"
        "        # \u63a7\u76d8\u5ea6\uff1a\u540e\u53f0\u7b97\u5b8c\u518d\u5237\u4e00\u6b21\uff08\u4e0d\u963b\u585e UI\uff09\n"
        "        self.ctrl_async_fill(self._rows, self._render_rows)\n",
        "        self._render_rows()\n"
        "        # \u63a7\u76d8\u5ea6\uff1a\u5148\u7528\u7f13\u5b58\u7acb\u523b\u586b\uff0c\u518d\u540e\u53f0\u8865\u7b97\u7f3a\u7684\uff08\u4e0d\u963b\u585e UI\uff09\n"
        "        self.ctrl_fill_and_async(self._rows, self._render_rows)\n",
        'onloaded'),
       ("        self._render_rows()\n"
        "        self.ctrl_async_fill(self._rows, self._render_rows)\n",
        "        self._render_rows()\n"
        "        self.ctrl_fill_and_async(self._rows, self._render_rows)\n",
        'tail')],
      imp_after_def=('from .base import (\n', IMP))

# 3) 分时做T（持仓表）
patch(r'ui\battle_widgets\atr_t_widget.py',
      [("    def _render_hold_table(self):\n        rows = self._hold_rows\n",
        "    def _render_hold_table(self):\n        fetch_ctrl_cached(self._hold_rows)\n        rows = self._hold_rows\n",
        'render')],
      imp_after_def=('from .base import (\n', IMP))

# 4) 市场节奏·追踪
patch(r'ui\battle_widgets\picks_track_widget.py',
      [("    def _render(self):\n        rows = self._shown\n",
        "    def _render(self):\n        fetch_ctrl_cached(self._shown)\n        rows = self._shown\n",
        'render')],
      imp_after_def=('from .base import (\n', IMP))

# 5) ⭐ 自选评分（主界面）：渲染前即时填，缓存命中就是 0 成本
patch(r'ui\watchlist_panel.py',
      [('    def _update_table(self, stocks=None):\n'
        '        """\u66f4\u65b0\u8868\u683c"""\n'
        '        # \u5982\u679c\u6ca1\u6709\u4f20\u5165stocks\uff0c\u7528self.stocks\n'
        '        if stocks is None:\n'
        '            stocks = self.stocks\n',
        '    def _update_table(self, stocks=None):\n'
        '        """\u66f4\u65b0\u8868\u683c"""\n'
        '        # \u5982\u679c\u6ca1\u6709\u4f20\u5165stocks\uff0c\u7528self.stocks\n'
        '        if stocks is None:\n'
        '            stocks = self.stocks\n'
        '        # \u63a7\u76d8\u5ea6\uff1a\u5148\u7528\u5df2\u6709\u7f13\u5b58\u7acb\u523b\u586b\uff08\u96f6\u8ba1\u7b97\uff09\uff0c\u540e\u9762 _ctrl_async \u518d\u8865\u7b97\u7f3a\u7684\n'
        '        try:\n'
        '            from ui.battle_widgets.base import fetch_ctrl_cached\n'
        '            fetch_ctrl_cached(stocks)\n'
        '        except Exception:\n'
        '            pass\n',
        'render')])

print('\nC \u90e8\u5206\u5b8c\u6210')
