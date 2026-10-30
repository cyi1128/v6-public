# -*- coding: utf-8 -*-
"""验证「规则① 洗盘文案降级」：默认不出文案、别的规则不受影响、判定逻辑没动、开关可逆。

只读验证，不修改任何代码。
"""
import difflib
import io
import re
import sys

sys.path.insert(0, r'D:\QuantMonitorV6')
import services.band_pattern_engine as E  # noqa: E402

ROOT = r'D:\QuantMonitorV6'
OUT = []
PASS = [0]
FAIL = [0]
WASH = '高度控盘 + 疑似洗盘，关注启动'


def p(line=''):
    OUT.append(line)
    print(line, flush=True)


def ck(cond, msg, extra=''):
    if cond:
        PASS[0] += 1
        p('  PASS  %s %s' % (msg, extra))
    else:
        FAIL[0] += 1
        p('  FAIL  %s %s' % (msg, extra))


def expect_tags(ctrl, stage, pos):
    """按「洗盘文案已关闭」后的规则独立算期望标签（不调引擎）。"""
    out = []
    if stage == 'distribute' and pos is not None and pos >= E._CTRL_DIST_POS:
        out.append('出货风险警示')
    if pos is not None and pos < E._CTRL_CAND_POS and ctrl >= E._CTRL_HIGH:
        out.append('高度控盘候选')
    return out


p('=' * 96)
p('规则① 洗盘文案降级 —— 验证（_WASH_NOTE_MODE 现值 = %s）' % E._WASH_NOTE_MODE)
p('=' * 96)

ck(E._WASH_NOTE_MODE == 'off', "引擎 _WASH_NOTE_MODE == 'off'", '实际 %s' % E._WASH_NOTE_MODE)

# ---------------------------------------------------------------- A 全矩阵
p('')
p('[A] 全矩阵：wash 一律无文案，其他两条规则与独立算法逐格一致')
ncase = 0
bad_wash = []
bad_other = []
for ctrl in (0.0, 50.0, 60.0, 84.9, 85.0, 86.0, 90.0, 95.0, 99.0):
    for stage in (None, 'wash', 'distribute', 'unknown'):
        for pos in (None, 0.10, 0.24, 0.25, 0.64, 0.65, 0.90):
            ncase += 1
            tags = E._ctrl_note_tags(ctrl, stage, pos)
            full = E._ctrl_note(ctrl, stage, pos)
            if WASH in tags or WASH in full:
                bad_wash.append((ctrl, stage, pos, tags))
            if tags != expect_tags(ctrl, stage, pos):
                bad_other.append((ctrl, stage, pos, tags, expect_tags(ctrl, stage, pos)))
p('  组合数 %d' % ncase)
ck(not bad_wash, 'wash / 任何组合都不再出现「疑似洗盘」文案', '异常 %s' % bad_wash[:3])
ck(not bad_other, '出货风险警示 / 高度控盘候选 与独立算法逐格一致', '异常 %s' % bad_other[:3])

p('')
for c in ((90.0, 'wash', 0.20), (90.0, 'wash', 0.30), (90.0, 'wash', 0.90),
          (95.0, 'unknown', 0.10), (85.0, 'distribute', 0.70)):
    p('    抽样 ctrl=%-5s stage=%-10s pos=%-5s -> %r' % (c[0], c[1], c[2],
                                                        E._ctrl_note(*c)))

# ---------------------------------------------------------------- B 开关可逆
p('')
p('[B] 开关可逆：临时改回 watch 应当恢复旧文案')
try:
    E._WASH_NOTE_MODE = 'watch'
    back = E._ctrl_note(90.0, 'wash', 0.20)
    back2 = E._ctrl_note(90.0, 'wash', 0.90)
finally:
    E._WASH_NOTE_MODE = 'off'
p('    watch 下 ctrl=90 wash pos=0.20 -> %r' % back)
p('    watch 下 ctrl=90 wash pos=0.90 -> %r' % back2)
ck(back == WASH + ' ｜ 高度控盘候选' and back2 == WASH,
   "改回 'watch' 能完整恢复旧文案（无需改代码）", '')

# ---------------------------------------------------------------- C 判定逻辑没动
p('')
p('[C] judge_wash_or_distribute 判定逻辑一字未动（与上一批备份比源码）')


def grab(path, fname):
    s = io.open(path, 'r', encoding='utf-8').read()
    m = re.search(r'\n    def %s\(.*?(?=\n    def |\n\nclass |\Z)' % fname, s, re.S)
    return m.group(0) if m else ''


cur = grab(ROOT + r'\strategy\base.py', 'judge_wash_or_distribute')
old = grab(ROOT + r'\strategy\base.py.bak_before_probe_pos35', 'judge_wash_or_distribute')
p('    当前版本 %d 字符 ｜ 备份版本 %d 字符' % (len(cur), len(old)))
ck(cur and cur == old, '判定函数源码与上一批备份逐字一致（没有改判断逻辑）')

# ---------------------------------------------------------------- D 引擎只改了 3 处
p('')
p('[D] 引擎与 .bak_before_washnote 逐行 diff：改动必须只落在洗盘文案这一处')
a = io.open(ROOT + r'\services\band_pattern_engine.py', 'r', encoding='utf-8').read().splitlines()
b = io.open(ROOT + r'\services\band_pattern_engine.py.bak_before_washnote',
            'r', encoding='utf-8').read().splitlines()
chg = [l for l in difflib.unified_diff(b, a, lineterm='', n=0)
       if (l.startswith('+') or l.startswith('-')) and not l.startswith(('+++', '---'))]
allow = ('_WASH_NOTE_MODE', 'wash', '洗盘', '疑似洗盘', '关注启动', 'stage_guess',
         '2026-10-11', '37.9', '45.2', '依据', '结论', '处理', '字段', '判定逻辑', 'watch')
outside = [l for l in chg
           if l.strip() not in ('+', '-') and not any(k in l for k in allow)]
p('    diff 变更行 %d 条（+/- 合计，其中纯空行 %d 条）'
  % (len(chg), sum(1 for l in chg if l.strip() in ('+', '-'))))
for l in chg:
    p('      %s' % l[:110])
ck(not outside, '所有变更行都与洗盘文案相关，没有顺手改别的东西', '越界 %s' % outside[:3])

# 把注释与空行剔掉后，剩下的「真正代码变更」必须是且仅是这 5 行
code_lines = sorted(l.strip() for l in chg
                    if l.strip() not in ('+', '-') and not l[1:].strip().startswith('#'))
expect_lines = sorted([
    "+_WASH_NOTE_MODE = 'off'   # 'off' 不出洗盘文案（默认，依据见上）；'watch' 恢复旧文案",
    "-        if ctrl >= _CTRL_HIGH and stage == 'wash':",
    "+        if _WASH_NOTE_MODE != 'off' and ctrl >= _CTRL_HIGH and stage == 'wash':",
    "+    洗盘文案自 2026-10-11 起默认关闭（_WASH_NOTE_MODE='off'，依据见该常量注释）；",
    "+    stage_guess 仍照常记录 wash / distribute / unknown。",
])
ck(code_lines == expect_lines, '剔掉注释后的代码变更恰好是「开关常量 + 一行门槛 + 两行 docstring」',
   '实际 %d 行' % len(code_lines))
for l in code_lines:
    p('      代码变更 %s' % l[:110])

p('')
p('=' * 96)
p('总计：PASS %d ｜ FAIL %d' % (PASS[0], FAIL[0]))
p('=' * 96)

io.open(ROOT + r'\tools\washnote_off_verify.txt', 'w', encoding='utf-8').write('\n'.join(OUT))
sys.exit(1 if FAIL[0] else 0)
