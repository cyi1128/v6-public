# -*- coding: utf-8 -*-
"""修复：控盘列「候选/出货/洗盘」标签被观察类文案（C4/C6）污染。执行一次即失效。

背景（2026-10-10 离屏 UI 实测抓到的真 bug）：
  日K建仓表控盘列的短标签原来是用整串 note 做关键词反推 ——
  「有 [控盘] 文案且不含 洗盘/出货 就是 候选」。
  C4/C6 的观察文案与控盘提示共用同一串 note，于是只命中 C4/C6、
  控盘分只有 72 的股票也被染成绿色「候选」（实测 15 -> 43 条）。

修法：
  1) band_pattern_engine：把「控盘提示」与「观察类文案」拆成两个函数，
     新增 pattern_record.ctrl_tag（只存控盘提示），note 内容与顺序完全不变。
  2) control_profile：标签判定改为只看「控盘提示」（白名单），不再整串反推。
  3) atr_t_widget：优先读 ctrl_tag；旧库/快照没有该列时退回白名单比对。
     tooltip 仍显示完整 note（C4/C6 文案照旧可见）。

改 3 个文件：services\\band_pattern_engine.py(纯LF) / services\\control_profile.py(纯CRLF)
            / ui\\battle_widgets\\atr_t_widget.py(纯CRLF)
"""
import py_compile
import shutil
import sys

sys.stdout.reconfigure(encoding='utf-8')
ENG = r'D:\QuantMonitorV6\services\band_pattern_engine.py'
CP = r'D:\QuantMonitorV6\services\control_profile.py'
ATR = r'D:\QuantMonitorV6\ui\battle_widgets\atr_t_widget.py'
SUF = '.bak_before_ctrltag'


def load(p):
    with open(p, 'rb') as f:
        raw = f.read()
    crlf = raw.count(b'\r\n')
    return raw.decode('utf-8'), crlf, raw.count(b'\n') - crlf


def save(p, s, crlf):
    with open(p, 'wb') as f:
        f.write((s.replace('\n', '\r\n') if crlf else s).encode('utf-8'))


def rep(s, old, new, tag, n=1):
    c = s.count(old)
    assert c == n, '锚点命中 %d 次（期望 %d）: %s' % (c, n, tag)
    return s.replace(old, new)


# ============================================================ engine
s, crlf, lf = load(ENG)
assert crlf == 0, 'engine 应为纯 LF，实际 CRLF=%d' % crlf
shutil.copy2(ENG, ENG + SUF)
t = s.replace('\r\n', '\n')

OLD_BODY = """    out = []
    try:
        if ctrl >= _CTRL_HIGH and stage == 'wash':
            out.append('高度控盘 + 疑似洗盘，关注启动')
        if stage == 'distribute' and pos is not None and pos >= _CTRL_DIST_POS:
            out.append('出货风险警示')
        # C3（2026-10-10）：改为位置主导 —— 先看是否在低位区，再用控盘分过滤
        if pos is not None and pos < _CTRL_CAND_POS and ctrl >= _CTRL_HIGH:
            out.append('高度控盘候选')
        # V20 建仓因子文案（默认不触发；依据见 _BUILD_NOTE_MODE 注释）
        if _BUILD_NOTE_MODE != 'off' and stack is not None and redfat is not None:
            _s_hit = float(stack) >= _BUILD_HIT_STACK
            _r_hit = float(redfat) >= _BUILD_HIT_REDFAT
            _low = (ctrl >= _CTRL_HIGH and pos is not None and pos < _CTRL_CAND_POS)
            if _BUILD_NOTE_MODE == 'buy':
                if _s_hit:
                    out.append('疑似底部堆量')
                if _r_hit:
                    out.append('红肥绿瘦建仓特征')
                if _s_hit and _r_hit and _low:
                    out.append('建仓加强')
            elif _BUILD_NOTE_MODE == 'warn':
                # 按实测方向：这几个条件下同锚点增量 4/4 为负 -> 提示谨慎，而非提示买入
                if _s_hit and _r_hit and _low:
                    out.append('堆量过热 + 红肥绿瘦，历史同形态偏弱')
        # C4 观察文案（默认 'watch' 会追加；未通过逐锚点检验，只能观察，依据见常量注释）
        if _C4_NOTE_MODE != 'off' and c4 is not None and int(c4) >= 5:
            out.append('C4观察：低位量价结构')
        # C6 观察文案（默认 'watch'；C4 去掉量价结构后的更稳子集，依据见常量注释）
        if _C6_NOTE_MODE != 'off' and c6 is not None and int(c6) >= 2:
            out.append('C6观察：低位适中振幅')
    except Exception:
        return ''
    return ' ｜ '.join(out)
"""

NEW_BODY = """    return ' ｜ '.join(_ctrl_note_tags(ctrl, stage, pos)
                      + _observe_tags(stack, redfat, c4, c6))


def _ctrl_note_tags(ctrl, stage, pos):
    \"\"\"只返回「控盘提示」标签列表（就是表格里 候选 / 出货 / 洗盘 那一部分）。

    必须与 _ctrl_note 共用这同一份判定：引擎把它写进 pattern_record.ctrl_tag，
    UI 显示短标签时读那一列。**不要**拿 _ctrl_note 的整串文案去做关键词反推 ——
    C4/C6/建仓因子这些「观察类文案」混在同一串里，反推会把只命中观察规则的股票
    误标成绿色「候选」（2026-10-10 实测：控盘 72 分、无任何控盘提示的股票被标 候选，
    15 条虚增到 43 条）。

    返回 list[str]，无提示返回 []。异常时返回 []（宁可没标签，不给错标签）。
    \"\"\"
    out = []
    try:
        if ctrl >= _CTRL_HIGH and stage == 'wash':
            out.append('高度控盘 + 疑似洗盘，关注启动')
        if stage == 'distribute' and pos is not None and pos >= _CTRL_DIST_POS:
            out.append('出货风险警示')
        # C3（2026-10-10）：改为位置主导 —— 先看是否在低位区，再用控盘分过滤
        if pos is not None and pos < _CTRL_CAND_POS and ctrl >= _CTRL_HIGH:
            out.append('高度控盘候选')
    except Exception:
        return []
    return out


def _observe_tags(stack=None, redfat=None, c4=None, c6=None):
    \"\"\"只返回「观察类」文案（建仓因子 + C4 + C6），与控盘提示分开。

    分开的唯一目的：让 UI 取标签时不必解析整串 note（见 _ctrl_note_tags 说明）。
    文案内容与拼接顺序与历史版本逐字一致，note 字段因此没有任何变化。
    \"\"\"
    out = []
    try:
        # V20 建仓因子文案（默认不触发；依据见 _BUILD_NOTE_MODE 注释）
        if _BUILD_NOTE_MODE != 'off' and stack is not None and redfat is not None:
            _s_hit = float(stack) >= _BUILD_HIT_STACK
            _r_hit = float(redfat) >= _BUILD_HIT_REDFAT
            _low_ok = float(ctrl_low_probe(stack, redfat, c4, c6)) if False else None  # noqa: F841
            if _BUILD_NOTE_MODE == 'buy':
                if _s_hit:
                    out.append('疑似底部堆量')
                if _r_hit:
                    out.append('红肥绿瘦建仓特征')
            elif _BUILD_NOTE_MODE == 'warn':
                if _s_hit and _r_hit:
                    out.append('堆量过热 + 红肥绿瘦，历史同形态偏弱')
        # C4 观察文案（默认 'watch' 会追加；未通过逐锚点检验，只能观察，依据见常量注释）
        if _C4_NOTE_MODE != 'off' and c4 is not None and int(c4) >= 5:
            out.append('C4观察：低位量价结构')
        # C6 观察文案（默认 'watch'；C4 去掉量价结构后的更稳子集，依据见常量注释）
        if _C6_NOTE_MODE != 'off' and c6 is not None and int(c6) >= 2:
            out.append('C6观察：低位适中振幅')
    except Exception:
        return out
    return out
"""
t = rep(t, OLD_BODY, NEW_BODY, 'engine _ctrl_note 拆分')

# 建仓因子分支里原来用到了 ctrl/pos 的 _low 组合（'建仓加强' / '堆量过热' 文案），
# 拆开后 _observe_tags 拿不到 ctrl/pos —— 把 _low 作为显式参数传进来，保持文案逐字不变。
t = rep(t, "def _observe_tags(stack=None, redfat=None, c4=None, c6=None):",
        "def _observe_tags(stack=None, redfat=None, c4=None, c6=None, low_ctrl=False):",
        'engine _observe_tags 签名')
t = rep(t, """            _low_ok = float(ctrl_low_probe(stack, redfat, c4, c6)) if False else None  # noqa: F841
            if _BUILD_NOTE_MODE == 'buy':
                if _s_hit:
                    out.append('疑似底部堆量')
                if _r_hit:
                    out.append('红肥绿瘦建仓特征')
            elif _BUILD_NOTE_MODE == 'warn':
                if _s_hit and _r_hit:
                    out.append('堆量过热 + 红肥绿瘦，历史同形态偏弱')""",
        """            if _BUILD_NOTE_MODE == 'buy':
                if _s_hit:
                    out.append('疑似底部堆量')
                if _r_hit:
                    out.append('红肥绿瘦建仓特征')
                if _s_hit and _r_hit and low_ctrl:
                    out.append('建仓加强')
            elif _BUILD_NOTE_MODE == 'warn':
                # 按实测方向：这几个条件下同锚点增量 4/4 为负 -> 提示谨慎，而非提示买入
                if _s_hit and _r_hit and low_ctrl:
                    out.append('堆量过热 + 红肥绿瘦，历史同形态偏弱')""",
        'engine 建仓因子文案恢复')
t = rep(t, """    return ' ｜ '.join(_ctrl_note_tags(ctrl, stage, pos)
                      + _observe_tags(stack, redfat, c4, c6))""",
        """    _low_ctrl = bool(ctrl >= _CTRL_HIGH and pos is not None and pos < _CTRL_CAND_POS)
    return ' ｜ '.join(_ctrl_note_tags(ctrl, stage, pos)
                      + _observe_tags(stack, redfat, c4, c6, _low_ctrl))""",
        'engine _ctrl_note 组装')

# 新字段 ctrl_tag
t = rep(t, "    ('c6_ok', 'INTEGER'), ('c6_score', 'REAL'),\n",
        "    ('c6_ok', 'INTEGER'), ('c6_score', 'REAL'),\n"
        "    ('ctrl_tag', 'TEXT'),   # 只存「控盘提示」（候选/出货/洗盘），UI 取短标签用这列\n",
        'engine _ALL_COLS ctrl_tag')
t = rep(t, "             c6_ok, c6_score,\n",
        "             c6_ok, c6_score, ctrl_tag,\n", 'engine INSERT 列清单')
t = rep(t, "            rec.get('c6_ok',0), rec.get('c6_score',0),\n",
        "            rec.get('c6_ok',0), rec.get('c6_score',0),\n"
        "            rec.get('ctrl_tag',''),\n", 'engine INSERT 取值')
t = rep(t, 'VALUES (' + ','.join(['?'] * 50) + ')',
        'VALUES (' + ','.join(['?'] * 51) + ')', 'engine 占位符 50->51')
print('INSERT 占位符：50 -> 51')

t = rep(t, '        _ctrl_tip = _ctrl_note(_ctrl, _stage, _pos, _stack_sc, _redfat_sc, _c4_n, _c6_n)\n',
        "        # 控盘提示（决定 UI 短标签的只有这一部分；观察类文案另算）\n"
        "        _ctrl_tag = ' ｜ '.join(_ctrl_note_tags(_ctrl, _stage, _pos))\n"
        "        _ctrl_tip = _ctrl_note(_ctrl, _stage, _pos, _stack_sc, _redfat_sc, _c4_n, _c6_n)\n",
        'engine scan_stock ctrl_tag')
t = rep(t, "                'c6_ok': 1 if _c6_ok else 0, 'c6_score': _c6_sc,\n",
        "                'c6_ok': 1 if _c6_ok else 0, 'c6_score': _c6_sc,\n"
        "                'ctrl_tag': _ctrl_tag,\n", 'engine rec ctrl_tag')
save(ENG, t, False)
py_compile.compile(ENG, doraise=True)
print('engine OK (%d 行, 纯LF)' % (t.count('\n') + 1))

# ============================================================ control_profile
s, crlf, lf = load(CP)
assert crlf > 0 and lf == 0, 'control_profile 应为纯 CRLF（CRLF=%d 裸LF=%d）' % (crlf, lf)
shutil.copy2(CP, CP + SUF)
t = s.replace('\r\n', '\n')

t = rep(t, '''def ctrl_cell(info):''',
        '''# 真正决定表格短标签的「控盘提示」白名单（与 band_pattern_engine._ctrl_note_tags
# 的三个文案逐字一致）。**必须白名单比对，不能拿整串 note 做关键词反推** ——
# C4/C6/建仓因子等观察类文案与控盘提示共用同一串 note，反推会把只命中观察规则的
# 股票误标成绿色「候选」（2026-10-10 实测：控盘 72 分却显示 候选，虚增 15 -> 43 条）。
_CTRL_TAGS = ('高度控盘 + 疑似洗盘，关注启动', '出货风险警示', '高度控盘候选')
_LABEL_COLORS = {'洗盘': '#ef6c00', '出货': '#c62828', '候选': '#2e7d32'}


def ctrl_tags(tag_str='', full_tip=''):
    """取出真正的「控盘提示」标签（list）。

    优先用引擎写进 DB 的 ctrl_tag（权威、无需解析）；它为空时退回在白名单里
    比对 note 片段（兼容旧库 / 快照恢复的行）。
    """
    out = []
    try:
        for _src in (tag_str, full_tip):
            for _s in str(_src or '').replace('\\n', ' ').split(' ｜ '):
                _s = _s.strip()
                if _s in _CTRL_TAGS and _s not in out:
                    out.append(_s)
    except Exception:
        return []
    return out


def ctrl_label(tag_str='', full_tip=''):
    """返回 (短标签, 颜色)；没有任何控盘提示时返回 ('', 灰色)。"""
    _tags = ctrl_tags(tag_str, full_tip)
    if not _tags:
        return '', NO_TIP_COLOR
    _j = ' ｜ '.join(_tags)
    if '疑似洗盘' in _j:
        return '洗盘', _LABEL_COLORS['洗盘']
    if '出货' in _j:
        return '出货', _LABEL_COLORS['出货']
    return '候选', _LABEL_COLORS['候选']


def ctrl_cell(info):''', 'cp ctrl_tags/ctrl_label')

t = rep(t, '''    score = float(info['score'])
    tip = info.get('tip') or ''
    if tip:
        if '疑似洗盘' in tip:
            return '%d·洗盘' % int(round(score)), '#ef6c00'
        if '出货' in tip:
            return '%d·出货' % int(round(score)), '#c62828'
        return '%d·候选' % int(round(score)), '#2e7d32'
    return (str(int(round(score))) if score else NO_DATA_TEXT), NO_TIP_COLOR''',
        '''    score = float(info['score'])
    # 标签只看「控盘提示」（tag 或白名单片段），观察类文案不参与 —— 见 ctrl_tags 说明
    _label, _color = ctrl_label(info.get('ctrl_tag') or '', info.get('tip') or '')
    if _label:
        return '%%d·%%s' %% (int(round(score)), _label), _color
    return (str(int(round(score))) if score else NO_DATA_TEXT), NO_TIP_COLOR''',
        'cp ctrl_cell')
save(CP, t, True)
py_compile.compile(CP, doraise=True)
print('control_profile OK (%d 行, 纯CRLF)' % (t.count('\n') + 1))

# ============================================================ atr_t_widget
s, crlf, lf = load(ATR)
assert crlf > 0 and lf == 0, 'atr_t_widget 应为纯 CRLF（CRLF=%d 裸LF=%d）' % (crlf, lf)
shutil.copy2(ATR, ATR + SUF)
t = s.replace('\r\n', '\n')

OLD = """            _cs = float(r.get('control_score') or 0)
            _nt = r.get('note') or ''
            _has_tip = '[控盘]' in _nt
            if _has_tip:
                _tt = _nt.split('[控盘]')[-1].strip().replace('\\n', ' ')
                if '疑似洗盘' in _tt:
                    _clabel, _ccol = '洗盘', '#ef6c00'
                elif '出货' in _tt:
                    _clabel, _ccol = '出货', '#c62828'
                else:
                    _clabel, _ccol = '候选', '#2e7d32'
                _ctxt = '%d·%s' % (int(round(_cs)), _clabel)
            else:
                _ccol = '#9e9e9e'
                _ctxt = str(int(round(_cs))) if _cs else '--'
            _c_item = QTableWidgetItem(_ctxt)
            _c_item.setForeground(QColor(_ccol))
            _c_item.setTextAlignment(center)
            _c_item.setToolTip(('控盘分 %.1f（%s）' % (
                _cs, r.get('stage_guess') or '--'))
                + (('\\n[控盘] ' + _tt) if _has_tip else ''))"""
NEW = """            _cs = float(r.get('control_score') or 0)
            _nt = r.get('note') or ''
            _full_tt = (_nt.split('[控盘]')[-1].strip().replace('\\n', ' ')
                        if '[控盘]' in _nt else '')
            # 短标签只能用「控盘提示」判定：优先读引擎写库的 ctrl_tag，旧库/快照
            # 没有该列时退回白名单比对（见 services.control_profile.ctrl_label）。
            # 不能拿整串 note 关键词反推 —— C4/C6 观察文案混在同一串里，
            # 会把只命中观察规则的股票染成绿色「候选」（72 分也显示候选）。
            from services.control_profile import ctrl_label as _ctrl_label
            _clabel, _ccol = _ctrl_label(r.get('ctrl_tag') or '', _full_tt)
            if _clabel:
                _ctxt = '%d·%s' % (int(round(_cs)), _clabel)
            else:
                _ccol = '#9e9e9e'
                _ctxt = str(int(round(_cs))) if _cs else '--'
            _c_item = QTableWidgetItem(_ctxt)
            _c_item.setForeground(QColor(_ccol))
            _c_item.setTextAlignment(center)
            _c_item.setToolTip(('控盘分 %.1f（%s）' % (
                _cs, r.get('stage_guess') or '--'))
                + (('\\n[控盘] ' + _full_tt) if _full_tt else ''))"""
t = rep(t, OLD, NEW, 'atr 控盘列标签')
save(ATR, t, True)
py_compile.compile(ATR, doraise=True)
print('atr_t_widget OK (%d 行, 纯CRLF)' % (t.count('\n') + 1))
print('备份后缀：%s' % SUF)
print('修复完成')
