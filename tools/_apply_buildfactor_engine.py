# -*- coding: utf-8 -*-
"""V20「建仓阶段专门因子」接入 services/band_pattern_engine.py（2026-10-10）

四处同步（少一处字段就全 0，shake / C2 都踩过）：
  1  _ALL_COLS           自动 ALTER 补列
  2  _save_or_update     列清单 + 占位符 + 取值
  3  scan_stock          计算 + 传参 + rec
  4  _ctrl_note          文案机制
另加：阈值常量与开关 / 漏斗计数 / 扫描汇总打印 / 扫描前清零

engine 是纯 LF，按项目约定：备份 -> assert count==1 -> 替换 -> py_compile
"""
import io
import os
import re
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
SUF = '.bak_before_buildfactor_20261010_2120'
REL = 'services/band_pattern_engine.py'
NL = chr(10)
U = '\\u'          # 目标文件里用 \uXXXX 转义写中文（与文件既有风格一致）


def _u(s):
    """把中文转成 \\uXXXX 转义序列（用于写进目标文件的字符串字面量）。"""
    return ''.join(c if ord(c) < 128 else U + ('%04x' % ord(c)) for c in s)


CONSTS = NL + '''
# ---- V20 建仓阶段专门因子（2026-10-10）bottom_volume_stack / red_fat_green_thin ----
# 因子本体在 strategy/base.py 的 TechnicalIndicators 里。
# 实测结论（tools\\build_factor_calibration*.txt：17570 条观测 / 4401 只 / 4 锚点 k=20/40/60/80，
# 每个锚点只喂截断到 T 的 120 根，无未来数据）：
#   1. 【孤立使用】堆量倍数与红肥绿瘦比值都跟未来20日收益【单调负相关】
#      （rho -0.043 / -0.054）；ratio<1.0 -> -0.21%，ratio 1.6~2.2 -> -3.09%，
#      ratio>3.5 -> -6.27%；反向「红瘦绿肥」反而是 +0.31%。
#   2. 【条件使用】把它们挂进「控盘高分区」(score>=85 & pos<0.25) 也救不回来：
#      逐锚点算同锚点增量，三种样本充足的口径（s_score>=45/50 & r_ratio>=1.10、
#      s_score>=40 & r_score>=40）都是【4 个锚点全部为负】，平均 -1.6 ~ -2.4pt。
#      汇总值看起来是 +2.23%（vs 基准 +0.33%），那是锚点构成偏差 —— 该组合 59.7%
#      的样本落在 k60，而 k60 的基准本身就是 +6.89%；逐锚点看每个锚点都不如基准。
#   3. 结论：这两个因子在本样本上【没有任何可用方向】。字段照写（供观察与复盘，
#      也给后续更大的样本继续验证），但建仓类提示默认【不上线】，
#      避免往程序里塞一个已被证伪的信号。
_BUILD_NOTE_MODE = 'off'   # 'off' 只写字段不提示（默认，依据见上）
                           # 'buy' 按原始草案：堆量/红肥绿瘦 满足 -> 建仓特征文案
                           # 'warn' 按实测方向：高控盘区内堆量+红肥绿瘦 -> 过热谨慎文案
_BUILD_HIT_STACK = 70.0    # 堆量分 >= 该值算「满足」（与 strategy/base.py BUILD_HIT_STACK 对齐）
_BUILD_HIT_REDFAT = 65.0   # 红肥绿瘦分 >= 该值算「满足」（对齐 BUILD_HIT_REDFAT）
_BUILD_FUNNEL = {'ok': 0, 'stack_ok': 0, 'redfat_ok': 0, 'both_ok': 0, 'tip': 0}
'''

CTRL_NOTE_NEW = '''def _ctrl_note(ctrl, stage, pos, stack=None, redfat=None):
    """按控盘分 / 阶段 / 位置生成提醒文案，多条用 ' ｜ ' 连接；无提示返回 ''。

    stack / redfat
    --------------
    V20 建仓因子的两个分数（0~100），默认 None。
    只有显式传入时才会追加建仓类文案；7 张个股列表走 control_profile，
    那里只传前 3 个参数，因此它们的行为完全不受影响。
    是否真的追加由模块级 _BUILD_NOTE_MODE 控制，默认 'off'（依据见该常量注释）。
    """
    out = []
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
    except Exception:
        return ''
    return ' ｜ '.join(out)'''

SCAN_COMPUTE_OLD = """        _ctrl, _stage, _pos = 0.0, 'unknown', None
        try:
            from strategy.base import TechnicalIndicators as _TI
            _df = _bars_to_df(bars)
            if _df is not None:
                _ti = _TI()
                _ctrl = float(_ti.estimate_control_score(_df))
                _stage = _ti.judge_wash_or_distribute(_df)
                _t120 = _df['close'].tail(120)
                _lo, _hi = float(_t120.min()), float(_t120.max())
                _pos = (float(_df['close'].iloc[-1]) - _lo) / (_hi - _lo + 1e-8)
                _CTRL_FUNNEL['ok'] += 1
                if _ctrl >= _CTRL_HIGH:
                    _CTRL_FUNNEL['ctrl'] += 1
                if _stage == 'wash':
                    _CTRL_FUNNEL['wash'] += 1
                elif _stage == 'distribute':
                    _CTRL_FUNNEL['dist'] += 1
        except Exception as _e:
            print(f'[日K建仓] {code} 控盘度计算异常: {type(_e).__name__}: {_e}', flush=True)
        _ctrl_tip = _ctrl_note(_ctrl, _stage, _pos)"""

SCAN_COMPUTE_NEW = """        # V20 建仓阶段专门因子（与控盘度共用同一个 df，不额外取数）
        _ctrl, _stage, _pos = 0.0, 'unknown', None
        _stack_sc, _redfat_sc = 0.0, 0.0
        _stack_ok, _redfat_ok = False, False
        try:
            from strategy.base import TechnicalIndicators as _TI
            _df = _bars_to_df(bars)
            if _df is not None:
                _ti = _TI()
                _ctrl = float(_ti.estimate_control_score(_df))
                _stage = _ti.judge_wash_or_distribute(_df)
                _t120 = _df['close'].tail(120)
                _lo, _hi = float(_t120.min()), float(_t120.max())
                _pos = (float(_df['close'].iloc[-1]) - _lo) / (_hi - _lo + 1e-8)
                _CTRL_FUNNEL['ok'] += 1
                if _ctrl >= _CTRL_HIGH:
                    _CTRL_FUNNEL['ctrl'] += 1
                if _stage == 'wash':
                    _CTRL_FUNNEL['wash'] += 1
                elif _stage == 'distribute':
                    _CTRL_FUNNEL['dist'] += 1
                _stk = _ti.bottom_volume_stack(_df)
                _rf = _ti.red_fat_green_thin(_df)
                _stack_sc = float(_stk.get('score') or 0.0)
                _redfat_sc = float(_rf.get('score') or 0.0)
                _stack_ok = bool(_stk.get('ok'))
                _redfat_ok = bool(_rf.get('ok'))
                _BUILD_FUNNEL['ok'] += 1
                if _stack_ok:
                    _BUILD_FUNNEL['stack_ok'] += 1
                if _redfat_ok:
                    _BUILD_FUNNEL['redfat_ok'] += 1
                if _stack_ok and _redfat_ok:
                    _BUILD_FUNNEL['both_ok'] += 1
        except Exception as _e:
            print(f'[日K建仓] {code} 控盘度计算异常: {type(_e).__name__}: {_e}', flush=True)
        _ctrl_tip = _ctrl_note(_ctrl, _stage, _pos, _stack_sc, _redfat_sc)
        if _ctrl_tip and _BUILD_NOTE_MODE != 'off':
            _BUILD_FUNNEL['tip'] += 1"""

ANCHOR_CF = ("                  % (_cf['ok'], _CTRL_HIGH, _cf['ctrl'], _cf['wash']," + NL
             + "                     _cf['dist'], _cf['tip']), flush=True)" + NL)
_P_MSG = _u('[建仓因子] 已计算 %d 只 ｜ 堆量满足 %d 只 ｜ 红肥绿瘦满足 %d 只'
            ' ｜ 两者同时 %d 只 ｜ 方向开关 _BUILD_NOTE_MODE=%s')
PRINT_NEW = ANCHOR_CF + NL.join([
    "            _bf = _BUILD_FUNNEL",
    "            print('" + _P_MSG + "'",
    "                  % (_bf['ok'], _bf['stack_ok'], _bf['redfat_ok'],",
    "                     _bf['both_ok'], _BUILD_NOTE_MODE), flush=True)",
    "",
])

EDITS = [
    # 1) 常量与漏斗
    ("_CTRL_FUNNEL = {'ok': 0, 'ctrl': 0, 'wash': 0, 'dist': 0, 'tip': 0}" + NL,
     "_CTRL_FUNNEL = {'ok': 0, 'ctrl': 0, 'wash': 0, 'dist': 0, 'tip': 0}" + NL + CONSTS),

    # 2) _ctrl_note 全文替换
    ('''def _ctrl_note(ctrl, stage, pos):
    """按控盘分 / 阶段 / 位置生成提醒文案，多条用 ' ｜ ' 连接；无提示返回 ''。"""
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
        return ''
    return ' ｜ '.join(out)''', CTRL_NOTE_NEW),

    # 3) _ALL_COLS 加两列
    ("    ('control_score', 'REAL'), ('stage_guess', 'TEXT')," + NL + "    ('note', 'TEXT')",
     "    ('control_score', 'REAL'), ('stage_guess', 'TEXT')," + NL
     + "    ('stack_vol_score', 'REAL'), ('red_fat_score', 'REAL')," + NL
     + "    ('note', 'TEXT')"),

    # 4) _save_or_update 列清单
    ("             control_score, stage_guess," + NL + "             created_at, updated_at)",
     "             control_score, stage_guess," + NL
     + "             stack_vol_score, red_fat_score," + NL
     + "             created_at, updated_at)"),

    # 5) _save_or_update 取值
    ("            rec.get('control_score',0), rec.get('stage_guess','unknown')," + NL,
     "            rec.get('control_score',0), rec.get('stage_guess','unknown')," + NL
     + "            rec.get('stack_vol_score',0), rec.get('red_fat_score',0)," + NL),

    # 6) scan_stock 计算段
    (SCAN_COMPUTE_OLD, SCAN_COMPUTE_NEW),

    # 7) scan_stock rec
    ("                'control_score': _ctrl, 'stage_guess': _stage," + NL,
     "                'control_score': _ctrl, 'stage_guess': _stage," + NL
     + "                'stack_vol_score': _stack_sc, 'red_fat_score': _redfat_sc," + NL),

    # 8) 扫描前清零
    ("        for _k in _CTRL_FUNNEL:" + NL + "            _CTRL_FUNNEL[_k] = 0" + NL,
     "        for _k in _CTRL_FUNNEL:" + NL + "            _CTRL_FUNNEL[_k] = 0" + NL
     + "        for _k in _BUILD_FUNNEL:" + NL + "            _BUILD_FUNNEL[_k] = 0" + NL),

    # 9) 扫描汇总打印
    (ANCHOR_CF, PRINT_NEW),
]

p = os.path.join(ROOT, REL)
raw = io.open(p, encoding='utf-8', newline='').read()
n_crlf = raw.count('\r\n')
assert n_crlf == 0, '%s 不是纯 LF（crlf=%d）' % (REL, n_crlf)
shutil.copy2(p, p + SUF)
s = raw
for i, (old, new) in enumerate(EDITS, 1):
    c = s.count(old)
    assert c == 1, '[第 %d 处锚点命中 %d 次] %r' % (i, c, old[:70])
    s = s.replace(old, new)

# 10) VALUES 占位符 44 -> 46
_lines = s.split(NL)
_hit = [i for i, l in enumerate(_lines) if 'VALUES (' in l and '"""' in l]
assert len(_hit) == 1, 'VALUES 占位符行命中 %d 次' % len(_hit)
_i = _hit[0]
_m = re.match(r'^(\s*VALUES \()([?,]+)(\)""".*)$', _lines[_i])
assert _m, '占位符行格式不符: %r' % _lines[_i]
_n = _m.group(2).count('?')
assert _n == 44, '占位符数不是 44 而是 %d' % _n
_lines[_i] = _m.group(1) + '?,' * 45 + '?' + _m.group(3)
assert _lines[_i].count('?') == 46, '占位符替换后不是 46'
s = NL.join(_lines)

io.open(p, 'w', encoding='utf-8', newline='').write(s)
back = io.open(p, encoding='utf-8', newline='').read()
assert back == s, '回读不一致'
assert back.count('\r\n') == 0, '行尾被破坏'
r = subprocess.run([PY, '-X', 'utf8', '-m', 'py_compile', p],
                   capture_output=True, text=True, encoding='utf-8', errors='replace')
print('py_compile rc=%d' % r.returncode)
if r.returncode != 0:
    print(r.stderr[:4000])
    print('!! 已保留改动以便排查；回退: copy /Y "%s%s" "%s"' % (REL, SUF, REL))
    sys.exit(1)

print('=' * 96)
print('V20 建仓因子接入 engine 完成')
print('=' * 96)
print('  %s   %d 处编辑 + 占位符 44->46   行数 %d -> %d   纯 LF   py_compile OK'
      % (REL, len(EDITS), raw.count(NL), back.count(NL)))
print('  备份: %s%s' % (REL, SUF))
