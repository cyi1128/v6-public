# -*- coding: utf-8 -*-
"""控盘提示拆分 + 标签修复的验证套件。

[A] _ctrl_note_tags / _ctrl_note 规则矩阵
[B] 新旧 _ctrl_note 全矩阵逐字等价（用改动前的备份模块做对照）
[C] control_profile 标签判定（含被 C4/C6 污染的 tip）
[D] atr_t_widget 静态确认不再做整串关键词反推
输出 tools\\ctrltag_unit.txt
"""
import importlib.util
import importlib.machinery
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')
OUT = r'D:\QuantMonitorV6\tools\ctrltag_unit.txt'
BAK = r'D:\QuantMonitorV6\services\band_pattern_engine.py.bak_before_ctrltag'
_lines = []


def P(*a):
    s = ' '.join(str(x) for x in a)
    _lines.append(s)
    print(s, flush=True)


PASS = [0, 0]


def check(name, cond, extra=''):
    if cond:
        PASS[0] += 1
        P('  PASS  %s %s' % (name, extra))
    else:
        PASS[1] += 1
        P('  FAIL  %s %s' % (name, extra))


import services.band_pattern_engine as E  # noqa: E402
import services.control_profile as CP  # noqa: E402

P('=' * 100)
P('控盘标签修复验证   %s' % time.strftime('%Y-%m-%d %H:%M:%S'))
P('=' * 100)

# ========================================================== A
P('')
P('[A] _ctrl_note_tags / _ctrl_note 规则矩阵')
check('规则① 高度控盘+洗盘（ctrl>=85 且 stage=wash）',
      E._ctrl_note_tags(85.0, 'wash', 0.5) == [],   # 2026-10-11 wash 文案关闭（_WASH_NOTE_MODE='off'）
      str(E._ctrl_note_tags(85.0, 'wash', 0.5)))
check('规则① 边界：ctrl=84.9 不触发',
      E._ctrl_note_tags(84.9, 'wash', 0.5) == [])
check('规则② 出货（stage=distribute 且 pos>=0.65）',
      E._ctrl_note_tags(50.0, 'distribute', 0.65) == ['出货风险警示'],
      str(E._ctrl_note_tags(50.0, 'distribute', 0.65)))
check('规则② 边界：pos=0.6499 不触发',
      E._ctrl_note_tags(50.0, 'distribute', 0.6499) == [])
check('规则③ 候选（pos<0.25 且 ctrl>=85）',
      E._ctrl_note_tags(99.0, 'unknown', 0.1) == ['高度控盘候选'],
      str(E._ctrl_note_tags(99.0, 'unknown', 0.1)))
check('规则③ 边界：pos=0.25 不触发', E._ctrl_note_tags(99.0, 'unknown', 0.25) == [])
check('规则③ 边界：ctrl=84.9 不触发', E._ctrl_note_tags(84.9, 'unknown', 0.1) == [])
check('pos=None 时规则②③都不触发', E._ctrl_note_tags(99.0, 'distribute', None) == [])
check('无任何控盘提示 -> 空列表', E._ctrl_note_tags(60.0, 'unknown', 0.5) == [],
      str(E._ctrl_note_tags(60.0, 'unknown', 0.5)))

P('')
P('C4/C6 只进观察文案，不进控盘标签：')
t1 = E._ctrl_note(72.0, 'unknown', 0.10, None, None, 5, 2)
check('控盘 72（非候选）+ C4/C6 命中 -> 标签为空、note 只有观察文案',
      E._ctrl_note_tags(72.0, 'unknown', 0.10) == [] and t1 == 'C4观察：低位量价结构 ｜ C6观察：低位适中振幅',
      repr(t1))
check('观察文案顺序：C4 在 C6 之前', t1.index('C4') < t1.index('C6'))
t2 = E._ctrl_note(90.0, 'unknown', 0.10, None, None, 5, 2)
check('控盘 90 + 候选 + C4/C6 -> 三条齐全且控盘标签在最前',
      t2 == '高度控盘候选 ｜ C4观察：低位量价结构 ｜ C6观察：低位适中振幅', repr(t2))
check('note == join(tags + observe)（拆分后组装一致）',
      t2 == ' ｜ '.join(E._ctrl_note_tags(90.0, 'unknown', 0.10)
                       + E._observe_tags(None, None, 5, 2, True)))
check('C6=1（只满足一条）不追加文案',
      'C6' not in E._ctrl_note(72.0, 'unknown', 0.10, None, None, None, 1))
check('C4=4（差一条）不追加文案',
      'C4' not in E._ctrl_note(72.0, 'unknown', 0.10, None, None, 4, None))
check('_BUILD_NOTE_MODE=off 时建仓因子文案不出现（保持默认不变）',
      E._BUILD_NOTE_MODE == 'off'
      and '堆量' not in E._ctrl_note(90.0, 'unknown', 0.10, 99.0, 99.0),
      'mode=%s' % E._BUILD_NOTE_MODE)

# ========================================================== B
P('')
P('[B] 新旧 _ctrl_note 全矩阵逐字等价（对照改动前的备份模块）')
_loader = importlib.machinery.SourceFileLoader('bpe_old', BAK)
_spec = importlib.util.spec_from_loader('bpe_old', _loader)
Old = importlib.util.module_from_spec(_spec)
_loader.exec_module(Old)
P('  备份模块载入成功：%s' % BAK.split('\\')[-1])
n_case = 0
diff = []
for ctrl in (0.0, 50.0, 84.9, 85.0, 86.0, 99.0):
    for stage in (None, 'wash', 'distribute', 'unknown'):
        for pos in (None, 0.10, 0.24, 0.25, 0.64, 0.65, 0.90):
            for c4 in (None, 0, 4, 5):
                for c6 in (None, 0, 1, 2):
                    n_case += 1
                    a = E._ctrl_note(ctrl, stage, pos, None, None, c4, c6)
                    b = Old._ctrl_note(ctrl, stage, pos, None, None, c4, c6)
                    # 2026-10-11 起 wash 文案默认关闭：把旧版输出里的那一段剥掉后，
                    # 其余文案必须逐字一致（这才是本次要守的不变量）。
                    b = ' ｜ '.join(x for x in b.split(' ｜ ')
                                    if x != '高度控盘 + 疑似洗盘，关注启动')
                    if a != b:
                        diff.append((ctrl, stage, pos, c4, c6, b, a))
P('  组合数 %d' % n_case)
check('全矩阵输出与改动前逐字一致（含 C4/C6 文案；已剔除 2026-10-11 关闭的洗盘文案）', not diff,
      '不一致 %d 例 %s' % (len(diff), diff[:3]))
# 建仓因子分支（三种模式）也要等价
diff2 = []
for mode in ('off', 'buy', 'warn'):
    E._BUILD_NOTE_MODE = mode
    Old._BUILD_NOTE_MODE = mode
    for ctrl in (50.0, 90.0):
        for pos in (0.10, 0.50):
            for stk, rf in ((0.0, 0.0), (70.0, 65.0), (99.0, 99.0)):
                a = E._ctrl_note(ctrl, 'unknown', pos, stk, rf, None, None)
                b = Old._ctrl_note(ctrl, 'unknown', pos, stk, rf, None, None)
                if a != b:
                    diff2.append((mode, ctrl, pos, stk, rf, b, a))
E._BUILD_NOTE_MODE = 'off'
Old._BUILD_NOTE_MODE = 'off'
P('  建仓因子分支组合数 36（3 模式 × 2 控盘 × 2 位置 × 3 分数）')
check('建仓因子文案（含 建仓加强 / 堆量过热）与改动前逐字一致', not diff2,
      '不一致 %d 例 %s' % (len(diff2), diff2[:3]))

# ========================================================== C
P('')
P('[C] control_profile 标签判定')
check('引擎文案与白名单逐字对齐（防止某天改了文案导致标签静默失效）',
      set(CP._CTRL_TAGS) >= set(
          x for x in ('高度控盘候选', '出货风险警示', '高度控盘 + 疑似洗盘，关注启动')),
      str(CP._CTRL_TAGS))
check('ctrl_tag 命中候选 -> 候选',
      CP.ctrl_label('高度控盘候选', '') == ('候选', '#2e7d32'))
check('ctrl_tag 命中出货 -> 出货', CP.ctrl_label('出货风险警示', '') == ('出货', '#c62828'))
check('ctrl_tag 命中洗盘 -> 洗盘',
      CP.ctrl_label('高度控盘 + 疑似洗盘，关注启动', '') == ('洗盘', '#ef6c00'))
check('只有 C4/C6 观察文案（无 ctrl_tag）-> 不给标签',
      CP.ctrl_label('', 'C4观察：低位量价结构 ｜ C6观察：低位适中振幅')
      == ('', CP.NO_TIP_COLOR),
      str(CP.ctrl_label('', 'C4观察：低位量价结构 ｜ C6观察：低位适中振幅')))
check('被污染的 note（72 分那种）-> 不再误判候选',
      CP.ctrl_label('', 'C6观察：低位适中振幅') == ('', CP.NO_TIP_COLOR))
check('旧库（没有 ctrl_tag 列）：从 tip 白名单仍能取到候选',
      CP.ctrl_label('', '高度控盘候选 ｜ C6观察：低位适中振幅') == ('候选', '#2e7d32'))
check('旧库：出货 + 观察文案 -> 出货',
      CP.ctrl_label('', '出货风险警示 ｜ C4观察：低位量价结构') == ('出货', '#c62828'))
check('ctrl_tags 去重（tag 与 tip 同时给）',
      CP.ctrl_tags('高度控盘候选', '高度控盘候选') == ['高度控盘候选'])
# ctrl_cell：有标签 -> 分数·标签；无标签 -> 纯分数灰色
check("ctrl_cell: 72 分 + 只有 C6 -> '72' 灰色",
      CP.ctrl_cell({'ok': True, 'score': 72.0, 'tip': 'C6观察：低位适中振幅'})
      == ('72', CP.NO_TIP_COLOR),
      str(CP.ctrl_cell({'ok': True, 'score': 72.0, 'tip': 'C6观察：低位适中振幅'})))
check("ctrl_cell: 92 分 + ctrl_tag 候选 -> '92·候选' 绿",
      CP.ctrl_cell({'ok': True, 'score': 92.0, 'ctrl_tag': '高度控盘候选'})
      == ('92·候选', '#2e7d32'),
      str(CP.ctrl_cell({'ok': True, 'score': 92.0, 'ctrl_tag': '高度控盘候选'})))
check('ctrl_cell: 无数据 -> --',
      CP.ctrl_cell(None) == (CP.NO_DATA_TEXT, CP.NO_DATA_COLOR))
check('7 张个股列表路径不受影响（3 参调用 note 里没有观察文案）',
      '观察' not in E._ctrl_note(92.0, 'unknown', 0.10))

# ========================================================== D
P('')
P('[D] atr_t_widget 静态检查')
src = open(r'D:\QuantMonitorV6\ui\battle_widgets\atr_t_widget.py', encoding='utf-8').read()
check('不再用 _has_tip + 关键词反推整串 note', '_has_tip' not in src)
check('已改为调用 control_profile.ctrl_label', 'ctrl_label as _ctrl_label' in src)
check('tooltip 仍显示完整 note（C4/C6 文案可见）',
      "_full_tt = (_nt.split('[控盘]')[-1]" in src and "_full_tt) if _full_tt else ''" in src)
check('行尾仍为纯 CRLF',
      open(r'D:\QuantMonitorV6\ui\battle_widgets\atr_t_widget.py', 'rb').read().count(b'\r\n') > 2000)

P('')
P('=' * 100)
P('总计：PASS %d ｜ FAIL %d' % (PASS[0], PASS[1]))
P('=' * 100)
with open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(_lines) + '\n')
print('\n已写出 %s' % OUT)
sys.exit(1 if PASS[1] else 0)
