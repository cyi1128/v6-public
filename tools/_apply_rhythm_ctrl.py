# -*- coding: utf-8 -*-
"""一次性补丁：给「市场节奏」模块接入控盘度（同一套 control_profile 口径）。

改动范围（只动 ui\\battle_widgets\\market_rhythm_widget.py）：
  Tab2 可介入：新增「控盘」列（该题材可介入候选里控盘分最高者）+ 每只候选名字后带控盘分
  Tab1 市场节奏：题材内强势股（连板梯队）每只名字后带控盘分
  后台补算 + 完成后重绘（control_profile 同一交易日只算一次）
文件是纯 LF，写回保持纯 LF。
"""
import io
import shutil

P = r'D:\QuantMonitorV6\ui\battle_widgets\market_rhythm_widget.py'
shutil.copy2(P, P + '.bak_before_rhythm_ctrl')

s = io.open(P, 'rb').read().decode('utf-8')
assert '\r\n' not in s, '该文件应为纯 LF，实际不是'
n0 = len(s)
lines0 = s.count('\n')
edits = []

# ---------------------------------------------------------------- 1) import
old = """from .base import (
    BattleModuleBase, make_table, set_table_item,
    BC, HeaderSorter,
)"""
new = """from .base import (
    BattleModuleBase, make_table, set_table_item,
    BC, HeaderSorter, CTRL_COL_TITLE,
)"""
edits.append((old, new, 'import CTRL_COL_TITLE'))

# ---------------------------------------------------------------- 2) Tab2 列常量
old = """(P_BOARD, P_COUNT, P_AVG, P_LEAD, P_PICKS, P_MEMBERS) = range(6)
P_HEADERS = ['板块/题材', '家数', '均涨幅', '龙头', '可介入', '成分股']
#   板块/题材 最长 7 字=104 | 家数 10=46 | 均涨幅 +10.92%=100
#   龙头 海峡创新 +20.0%=150 | 可介入 3只（全量在悬停） | 成分股 拉伸
P_GRID = [104, 46, 100, 150, 340, 240]"""
new = """(P_BOARD, P_COUNT, P_AVG, P_LEAD, P_PICKS, P_CTRL, P_MEMBERS) = range(7)
P_HEADERS = ['板块/题材', '家数', '均涨幅', '龙头', '可介入',
             CTRL_COL_TITLE, '成分股']
#   板块/题材 最长 7 字=104 | 家数 10=46 | 均涨幅 +10.92%=100
#   龙头 海峡创新 +20.0%=150 | 可介入 3只（含控盘分，全量在悬停）
#   控盘 该题材候选里最高分=100 | 成分股 拉伸
P_GRID = [104, 46, 100, 150, 400, 100, 240]


# ----------------------------------------------------------------------
# 控盘度（与 日K建仓 / 自选 / 竞价 / 今日涨停 / 分时做T / 追踪 同一套）
# 这两个 Tab 是「按题材成行」，行里只有成分股名单，所以控盘落两个地方：
#   ① 单元格内联：个股名字后面直接跟控盘分（Tab1 连板梯队 / Tab2 可介入候选）
#   ② Tab2 新增「控盘」列：该题材可介入候选里控盘分最高者
# 全部只读 control_profile 的内存缓存（cached_only），UI 线程绝不计算；
# 缺的由 MarketRhythmWidget._ctrl_async_fill() 在后台补算后重绘一次。
# ----------------------------------------------------------------------
def _ctrl_lookup(codes):
    \"\"\"{code: info}，**只读已有缓存、绝不计算**（UI 线程安全）。\"\"\"
    try:
        from services.control_profile import get_ctrl_map
        _cs = [str(c) for c in (codes or []) if c]
        if not _cs:
            return {}
        return get_ctrl_map(_cs, cached_only=True) or {}
    except Exception:
        return {}


def _ctrl_inline(info):
    \"\"\"单元格内联文本：'88候选' / '88'；没算出或没数据返回 ''（不占位）。\"\"\"
    if not info or not info.get('ok') or info.get('score') is None:
        return ''
    try:
        from services.control_profile import ctrl_cell
        _t, _c = ctrl_cell(info)
        _t = str(_t or '').replace('·', '')
        return '' if _t in ('', '--') else _t
    except Exception:
        return ''


def _ctrl_one_line(info):
    \"\"\"tooltip 一行：'88.3（wash）'；没有则 '--'。\"\"\"
    if not info or not info.get('ok') or info.get('score') is None:
        return '--'
    try:
        return '%.1f（%s）' % (float(info['score']), info.get('stage') or '--')
    except Exception:
        return '--'


def _ctrl_pos_txt(info):
    \"\"\"tooltip 尾巴：' ｜ 位置 32% ｜ 候选'；没有就不加。\"\"\"
    if not info or not info.get('ok') or info.get('score') is None:
        return ''
    out = ''
    try:
        if info.get('pos') is not None:
            out += ' ｜ 位置 %.0f%%' % (float(info['pos']) * 100)
        from services.control_profile import ctrl_cell
        _t, _c = ctrl_cell(info)
        if '·' in str(_t):
            out += ' ｜ ' + str(_t).split('·', 1)[1]
    except Exception:
        pass
    return out


def _ladder_ctrl(rows):
    \"\"\"Tab1：连板梯队里出现的个股 -> (内联映射, info 映射)。\"\"\"
    codes = []
    for b in (rows or []):
        for x in (b.get('ladder') or []):
            _c = str(x.get('code') or '')
            if _c:
                codes.append(_c)
    m = _ctrl_lookup(codes)
    return ({c: _ctrl_inline(i) for c, i in m.items()}, m)


def _picks_ctrl(r):
    \"\"\"Tab2 一行（一个板块）可介入候选的 [(code, info)]，只读缓存。\"\"\"
    picks = r.get('picks') or []
    codes = [str(p[0]) for p in picks if p and p[0]]
    m = _ctrl_lookup(codes)
    return [(str(p[0]), m.get(str(p[0]))) for p in picks if p and p[0]]


def _top_ctrl(pairs):
    \"\"\"[(code, info)] 里挑控盘分最高的一条 -> (code, info) 或 None。\"\"\"
    best = None
    for c, i in (pairs or []):
        try:
            if i and i.get('ok') and i.get('score') is not None:
                if best is None or float(i['score']) > float(best[1]['score']):
                    best = (c, i)
        except Exception:
            continue
    return best


def _top_ctrl_score(r):
    \"\"\"「控盘」列排序用：候选里最高控盘分；没有则 -1。\"\"\"
    b = _top_ctrl(_picks_ctrl(r))
    try:
        return float(b[1]['score']) if b else -1.0
    except Exception:
        return -1.0"""
edits.append((old, new, 'Tab2 列常量 + 控盘工具函数'))

# ---------------------------------------------------------------- 3) make_table 列数
old = "        self.pick_table = make_table(6, P_HEADERS)"
new = "        self.pick_table = make_table(len(P_HEADERS), P_HEADERS)"
edits.append((old, new, 'make_table 列数'))

# ---------------------------------------------------------------- 4) 排序键
old = """            keys={P_BOARD: lambda r: r['name'],
                  P_COUNT: lambda r: r['count'],
                  P_AVG: lambda r: r['avg_pct']},"""
new = """            keys={P_BOARD: lambda r: r['name'],
                  P_COUNT: lambda r: r['count'],
                  P_AVG: lambda r: r['avg_pct'],
                  P_CTRL: _top_ctrl_score},"""
edits.append((old, new, 'pick_sorter 加控盘排序键'))

# ---------------------------------------------------------------- 5) _apply 收尾
old = """        else:
            self.set_status('可介入数据不可用: %s' % (d.get('board_err') or '空'))"""
new = """        else:
            self.set_status('可介入数据不可用: %s' % (d.get('board_err') or '空'))

        # 控盘度：上面两个 render 已经把「缓存里已有的」画出来了，
        # 这里再后台把没算过的补齐，完成后回 UI 线程重绘一次（不阻塞界面）。
        self._ctrl_async_fill()"""
edits.append((old, new, '_apply 触发控盘后台补算'))

# ---------------------------------------------------------------- 6) Tab1 连板梯队带控盘
old = """    def _render_rhythm_rows(self, rows):
        self.table.setRowCount(0)
        self.table.setRowCount(len(rows))"""
new = """    def _render_rhythm_rows(self, rows):
        # 控盘度：只读缓存（没算过的先空着，后台补完会重绘）
        _ck, _cki = _ladder_ctrl(rows)
        self.table.setRowCount(0)
        self.table.setRowCount(len(rows))"""
edits.append((old, new, 'Tab1 渲染顶部取控盘缓存'))

old = """            lad = b.get('ladder') or []
            txt = ' '.join('%s%d板' % (x['name'], x['lbc']) for x in lad[:5])
            if len(lad) > 5:
                txt += ' …共%d只' % len(lad)
            set_table_item(self.table, r, C_LADDER, txt)
            self.table.item(r, C_LADDER).setToolTip(
                '\\n'.join('%s %s %d板 %s  %s' % (
                    x['name'], x['code'], x['lbc'], x['time'] or '',
                    x['reason'] or '') for x in lad[:15]) or '—')"""
new = """            lad = b.get('ladder') or []
            _lparts = []
            for x in lad[:5]:
                _lt = _ck.get(str(x.get('code') or '')) or ''
                _lparts.append('%s%d板%s' % (x['name'], x['lbc'],
                                             (' ' + _lt) if _lt else ''))
            txt = ' '.join(_lparts)
            if len(lad) > 5:
                txt += ' …共%d只' % len(lad)
            set_table_item(self.table, r, C_LADDER, txt)
            self.table.item(r, C_LADDER).setToolTip(
                '\\n'.join('%s %s %d板 %s  %s%s' % (
                    x['name'], x['code'], x['lbc'], x['time'] or '',
                    x['reason'] or '',
                    ('  ｜ 控盘 ' + _ctrl_one_line(
                        _cki.get(str(x.get('code') or ''))))
                    if _cki.get(str(x.get('code') or '')) else '')
                    for x in lad[:15]) or '—')"""
edits.append((old, new, 'Tab1 连板梯队内联控盘 + tooltip'))

# ---------------------------------------------------------------- 7) Tab2 可介入单元格内联
old = """            picks = r.get('picks') or []
            if picks:
                set_table_item(self.pick_table, row, P_PICKS,
                               '  '.join('%s %+.1f%%%s'
                                         % (p[1], p[2],
                                            '✅' if (len(p) > 10 and p[10]) else '')
                                         for p in picks[:3]),
                               BC.CYAN, align=left)"""
new = """            picks = r.get('picks') or []
            _pc = _picks_ctrl(r)
            _pcm = {c: i for c, i in _pc}
            if picks:
                _pbody = []
                for p in picks[:3]:
                    _pt = _ctrl_inline(_pcm.get(str(p[0])))
                    _pbody.append('%s %+.1f%%%s%s'
                                  % (p[1], p[2],
                                     (' ' + _pt) if _pt else '',
                                     '✅' if (len(p) > 10 and p[10]) else ''))
                set_table_item(self.pick_table, row, P_PICKS,
                               '  '.join(_pbody), BC.CYAN, align=left)"""
edits.append((old, new, 'Tab2 可介入单元格内联控盘'))

# ---------------------------------------------------------------- 8) Tab2 tooltip 每只候选加控盘
old = """                        _lines.append(_t)
                    _pi.setToolTip("""
new = """                        _ci = _pcm.get(str(p[0]))
                        _t += ('\\n      控盘 %s%s'
                               % (_ctrl_one_line(_ci), _ctrl_pos_txt(_ci)))
                        _lines.append(_t)
                    _pi.setToolTip("""
edits.append((old, new, 'Tab2 tooltip 每只候选加控盘行'))

# ---------------------------------------------------------------- 9) Tab2 新增「控盘」列
old = """            # ---- 成分股：前 3 名标「龙一/龙二/龙三」----"""
new = """            # ---- 控盘：该题材可介入候选里控盘分最高的一只 ----
            _best = _top_ctrl(_pc)
            if not _pc:
                set_table_item(self.pick_table, row, P_CTRL, '—', BC.TEXT3,
                               align=center)
                self.pick_table.item(row, P_CTRL).setToolTip(
                    '该板块今日没有「可介入」候选，无可比控盘度\\n'
                    '（可介入口径：非涨停 ｜ 涨幅 1~9% ｜ 量比≥1.2 ｜ '
                    '现价≥MA20 ｜ 成交额≥2亿 ｜ 流通市值≥20亿 ｜ 股价≥6元）')
            else:
                from services.control_profile import (ctrl_cell as _ccell,
                                                      NO_DATA_TEXT as _NDT,
                                                      NO_DATA_COLOR as _NDC)
                if _best is None:
                    _ct, _cc = _NDT, _NDC
                else:
                    _ct, _cc = _ccell(_best[1])
                set_table_item(self.pick_table, row, P_CTRL, _ct, _cc,
                               bold=True, align=center)
                _bname = next((p[1] for p in picks
                               if _best and str(p[0]) == _best[0]), '')
                _ctip = ['【控盘】该题材可介入候选里控盘分最高：%s%s'
                         % (_bname, (' ' + _ctrl_one_line(_best[1]))
                            if _best else ''),
                         '口径：与 日K建仓 / 自选 / 竞价 / 今日涨停 / 分时做T / '
                         '追踪 完全同一套 —— 同一份 estimate_control_score + '
                         '同一份阈值；只读本地K线缓存，无网络兜底。',
                         '逐只候选（控盘分（阶段）｜位置｜标签）：']
                for p in picks:
                    _pi2 = _pcm.get(str(p[0]))
                    _ctip.append('  %s %s  %s%s'
                                 % (p[1], str(p[0]), _ctrl_one_line(_pi2),
                                    _ctrl_pos_txt(_pi2)))
                _ctip.append('分越高 = 筹码越集中；带「出货」标签要警惕高位。'
                             '（控盘列可点表头排序）')
                self.pick_table.item(row, P_CTRL).setToolTip('\\n'.join(_ctip))
            # ---- 成分股：前 3 名标「龙一/龙二/龙三」----"""
edits.append((old, new, 'Tab2 新增控盘列'))

# ---------------------------------------------------------------- 10) 类方法：代码收集 + 后台补算
old = """    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------
    def _on_rhythm_cell(self, row, col):"""
new = """    # ------------------------------------------------------------------
    # 控盘度：后台补算（同一套算法 / 同一份阈值，跟日K建仓完全一致）
    # ------------------------------------------------------------------
    def _all_stock_codes(self):
        \"\"\"两个 Tab 单元格里出现过的全部个股代码（Tab1 连板梯队 + Tab2 可介入候选）。\"\"\"
        codes = []
        for b in (self._rows or []):
            for x in (b.get('ladder') or []):
                _c = str(x.get('code') or '')
                if _c:
                    codes.append(_c)
        for b in (self._pick_rows or []):
            for p in (b.get('picks') or []):
                _c = str(p[0] or '') if p else ''
                if _c:
                    codes.append(_c)
        return list(dict.fromkeys(codes))

    def _ctrl_async_fill(self):
        \"\"\"后台把还没算过的控盘补齐，完成后回 UI 线程重绘一次。

        控盘单只首次约 28ms（本地 duckdb），必须在后台线程算；
        同一交易日同一只只算一次（control_profile 内部按
        (代码, 最后一根K线日期) 缓存），所以日常刷新这里几乎立即返回。
        \"\"\"
        try:
            from services.control_profile import get_ctrl_map
        except Exception:
            return
        codes = self._all_stock_codes()
        if not codes:
            return
        try:
            _m = get_ctrl_map(codes, cached_only=True)
        except Exception:
            return
        missing = [c for c in codes if _m.get(c) is None]
        if not missing:
            return

        def work():
            try:
                get_ctrl_map(missing)
            except Exception:
                pass
            return {'n': len(missing)}

        def ok(_d):
            try:
                self._render_rhythm_rows(self._rows)
                self._render_pick_rows(self._pick_rows)
            except Exception as e:
                print('[市场节奏] 控盘重绘异常: %s' % e, flush=True)

        try:
            self.run_async(work, ok, lambda _m2: None)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------
    def _on_rhythm_cell(self, row, col):"""
edits.append((old, new, '类方法：_all_stock_codes / _ctrl_async_fill'))

for i, (o, n, tag) in enumerate(edits, 1):
    c = s.count(o)
    assert c == 1, '第 %d 处（%s）命中 %d 次' % (i, tag, c)
    s = s.replace(o, n)

io.open(P, 'wb').write(s.encode('utf-8'))
raw = io.open(P, 'rb').read()
print('market_rhythm_widget.py: %d -> %d 字符 ｜ %d -> %d 行 ｜ CRLF=%d 裸LF=%d'
      % (n0, len(s), lines0, s.count('\n'), raw.count(b'\r\n'),
         raw.count(b'\n') - raw.count(b'\r\n')))
