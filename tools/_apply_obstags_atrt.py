# -*- coding: utf-8 -*-
"""一次性补丁：ui/battle_widgets/atr_t_widget.py（纯 CRLF）

用户选的 B：日K建仓表把已经写进 note 的文案（破位警示 / 天量 / 缩量上涨 / 洗盘收复 /
地量 / 试盘 / 拉升形态 / 出货形态）拆成**可见的独立列**，不再只藏在「触发条件」的悬停里。
新增第 11 列「观察」（插在「控盘」与「环境分」之间）。

⚠ 本文件是纯 CRLF，写回必须显式 \r\n。
⚠ 新增列必须同步 5 处：列常量 range(N) / HEADER_DAILY / DAILY_WIDTHS /
  make_table(N, ...) / 渲染映射 —— 少一处这一列就是空的（AGENTS.md 记的老坑）。
"""
import io

P = r'D:\QuantMonitorV6\ui\battle_widgets\atr_t_widget.py'
s = io.open(P, encoding='utf-8', newline='').read()
assert s.count('\r\n') == s.count('\n'), '源文件不是纯 CRLF，停手'
assert 'COL_D_OBS' not in s, '看起来已经打过这个补丁了，不要重复打'
CRLF = '\r\n'


def rep(old, new, cnt=1, tag=''):
    global s
    old = old.replace('\n', CRLF)
    new = new.replace('\n', CRLF)
    n = s.count(old)
    assert n == cnt, '锚点[%s]命中 %d 次（期望 %d）' % (tag or old[:40], n, cnt)
    s = s.replace(old, new, cnt)


# ---- 1) 列常量 + 表头 + 宽度 ----
rep("""# 日K建仓表列（12列）
# 顺序：股票名称 代码 现价 涨跌幅 建仓价 止盈价 题材 模式 触发条件 控盘 环境分 基准日
COL_D_NAME, COL_D_CODE, COL_D_PRICE, COL_D_PCT, COL_D_TRIG_PRICE, \\
    COL_D_TAKE_PROFIT, COL_D_THEME, COL_D_PATTERN, COL_D_TRIGGER, \\
    COL_D_CTRL, COL_D_ENV, COL_D_BASE_DATE = range(12)
HEADER_DAILY = ['股票名称', '代码', '现价', '涨跌幅', '建仓价', '止盈价',
                '题材', '模式', '触发条件', '控盘', '环境分', '基准日']
# 0 = 该列不固定，改为 Stretch（吃掉剩余宽度）。题材列放 0。
DAILY_WIDTHS = [80, 70, 58, 72, 58, 58, 0, 92, 86, 74, 52, 92]
""",
    """# 日K建仓表列（13列）
# 顺序：股票名称 代码 现价 涨跌幅 建仓价 止盈价 题材 模式 触发条件 控盘 观察 环境分 基准日
# 「观察」（2026-10-11 新增，用户选的 B）：把原本只写进 note 的因子文案拆成可见标签，
# 词表来自 services.control_profile（与「控盘选股」页共用一份），
# 覆盖五阶段：建仓(堆量/红肥绿瘦)·试盘·洗盘(洗盘收复/地量)·拉升(形态/缩量上涨)·
# 出货(破位警示/天量/出货形态) + 观察规则 C4/C6。风险类单独上色，悬停看完整 note。
COL_D_NAME, COL_D_CODE, COL_D_PRICE, COL_D_PCT, COL_D_TRIG_PRICE, \\
    COL_D_TAKE_PROFIT, COL_D_THEME, COL_D_PATTERN, COL_D_TRIGGER, \\
    COL_D_CTRL, COL_D_OBS, COL_D_ENV, COL_D_BASE_DATE = range(13)
HEADER_DAILY = ['股票名称', '代码', '现价', '涨跌幅', '建仓价', '止盈价',
                '题材', '模式', '触发条件', '控盘', '观察', '环境分', '基准日']
# 0 = 该列不固定，改为 Stretch（吃掉剩余宽度）。题材列放 0。
# 「观察」给 200：最多四个标签（如「堆量·试盘·拉升:阶梯式上行·C6」）也放得下。
DAILY_WIDTHS = [80, 70, 58, 72, 58, 58, 0, 92, 86, 74, 200, 52, 92]
""", tag='cols')

# ---- 2) make_table ----
rep("        self.daily_table = make_table(12, HEADER_DAILY)",
    "        self.daily_table = make_table(13, HEADER_DAILY)", tag='make_table')

# ---- 3) 行数据：带上各因子字段（原来只带 note/control_score/stage_guess） ----
rep("""                'control_score': s.get('control_score') or 0,
                'stage_guess': s.get('stage_guess') or '',
            })""",
    """                'control_score': s.get('control_score') or 0,
                'stage_guess': s.get('stage_guess') or '',
                # 引擎写库的控盘短标签（原来漏带 → 控盘列只能退回 note 白名单比对）
                'ctrl_tag': s.get('ctrl_tag') or '',
                # 「观察」列要用的五阶段因子字段（query_signals 是 SELECT *，都在 s 里）
                'probe_ok': bool(s.get('probe_ok')),
                'c4_ok': bool(s.get('c4_ok')),
                'c6_ok': bool(s.get('c6_ok')),
                'brk_type': s.get('brk_type') or '',
                'vreg_tags': s.get('vreg_tags') or '',
                'dist_type': s.get('dist_pattern_type') or '',
                'markup_type': s.get('markup_ok') and (s.get('markup_type') or '') or '',
            })""", tag='rows')

# ---- 4) 渲染：新增「观察」列（插在控盘与环境分之间） ----
rep("""            self.daily_table.setItem(i, COL_D_CTRL, _c_item)
            set_table_item(self.daily_table, i, COL_D_BASE_DATE, r.get('base_date', ''),
                           '#607d8b', align=center)""",
    """            self.daily_table.setItem(i, COL_D_CTRL, _c_item)
            # 观察（五阶段短标签）：只是「结构状态」的事实标注，不是买入建议。
            # 一格一个颜色 -> 取该格里级别最高的（风险红 > 拉升橙 > 试盘金 > 中性蓝）。
            from services.control_profile import (obs_tag_pairs as _obs_pairs,
                                                  obs_stages as _obs_stages,
                                                  obs_tag_color as _obs_color_of)
            _pairs = _obs_pairs(
                probe_ok=bool(r.get('probe_ok')), c4_ok=bool(r.get('c4_ok')),
                c6_ok=bool(r.get('c6_ok')), brk_type=r.get('brk_type') or '',
                vreg_tags=r.get('vreg_tags') or '', dist_type=r.get('dist_type') or '',
                markup_type=r.get('markup_type') or '')
            if _pairs:
                _lv = [lv for _t, lv in _pairs]
                _ob_col = _obs_color_of(
                    'risk' if 'risk' in _lv else (
                        'warn' if 'warn' in _lv else (
                            'gold' if 'gold' in _lv else 'info')))
                _ob_txt = '·'.join(t for t, _lv2 in _pairs)
                _ob_tip = ('手法阶段：%s\\n%s' % ('/'.join(_obs_stages(_pairs)) or '-',
                                               '\\n'.join('· ' + t for t, _l in _pairs)))
                if r.get('note'):
                    _ob_tip += '\\n\\n' + str(r.get('note'))
            else:
                _ob_col, _ob_txt = '#9e9e9e', '—'
                _ob_tip = '本行没有任何阶段标注（建仓/试盘/洗盘/拉升/出货 均未命中）'
            _ob_item = QTableWidgetItem(_ob_txt)
            _ob_item.setForeground(QColor(_ob_col))
            _ob_item.setTextAlignment(left)
            _ob_item.setToolTip(_ob_tip)
            self.daily_table.setItem(i, COL_D_OBS, _ob_item)
            set_table_item(self.daily_table, i, COL_D_BASE_DATE, r.get('base_date', ''),
                           '#607d8b', align=center)""", tag='render')

# ---- 5) 函数 docstring 同步 ----
rep('        """[V5.0] 渲染日K建仓表（12列，含环境分阀门过滤）"""',
    '        """[V5.0] 渲染日K建仓表（13列，含环境分阀门过滤 + 五阶段观察列）"""',
    tag='docstring')

io.open(P, 'w', encoding='utf-8', newline='').write(s)
t = io.open(P, encoding='utf-8', newline='').read()
assert t.count('\r\n') == t.count('\n'), '写回后不是纯 CRLF'
print('atr_t_widget.py 完成：%d 行 / CRLF=%d 裸LF=%d（原 2216 行）'
      % (t.count('\n'), t.count('\r\n'), t.count('\n') - t.count('\r\n')))
