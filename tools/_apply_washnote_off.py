# -*- coding: utf-8 -*-
"""处理规则①「疑似洗盘 → 关注启动」：降级为只记字段、不出文案（一次性补丁，勿重跑）

依据：滚动观测里 wash 组（控盘分>=85 且 stage_guess='wash'）胜率约 37.9%，
低于全样本基准 45.2%，多档位置/分数门槛都跑不赢基准。

采用用户给的 B 方案（开关）：`_WASH_NOTE_MODE = 'off'`
  - 效果与 A（删除代码）完全相同：默认不再输出任何洗盘文案；
  - 比 A 多一个好处：要恢复旧文案只改一个字符串，不用改代码；
  - 与项目已有的 5 个文案开关（_BUILD_/_C4_/_C6_/_PROBE_/_DISTP_NOTE_MODE）同一套写法。
判定逻辑（judge_wash_or_distribute）与 stage_guess 落库完全不动。

同时同步更新 5 个历史单测脚本里编码了旧行为的期望值，以及 2 个与备份模块做
「全矩阵等价比对」的脚本（把旧版输出里的洗盘那段剥掉再比，其余必须逐字一致）。
"""
import io
import os
import shutil
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = r'D:\QuantMonitorV6'
SUF = '.bak_before_washnote'
WASH = '高度控盘 + 疑似洗盘，关注启动'


def patch(rel, pairs, must_all=True):
    """pairs: list[(old, new, expect_count_or_None)]；返回 [(old_head, n)]"""
    path = os.path.join(ROOT, rel)
    raw = io.open(path, 'rb').read()
    crlf = b'\r\n' in raw
    s = raw.decode('utf-8')
    norm = s.replace('\r\n', '\n')
    shutil.copy2(path, path + SUF)
    res = []
    for old, new, exp in pairs:
        o = old.replace('\r\n', '\n')
        n = new.replace('\r\n', '\n')
        cnt = norm.count(o)
        if cnt == 0:
            print('  !! 命中 0 次，跳过：%s' % o.strip()[:70])
            res.append((o.strip()[:50], 0))
            continue
        if exp is not None and cnt != exp:
            print('  !! 命中 %d 次（期望 %d）：%s' % (cnt, exp, o.strip()[:70]))
        norm = norm.replace(o, n)
        res.append((o.strip()[:50], cnt))
    out = norm.replace('\n', '\r\n') if crlf else norm
    io.open(path, 'wb').write(out.encode('utf-8'))
    # 行尾自检
    chk = io.open(path, 'rb').read()
    print('  %-40s CRLF=%d 裸LF=%d' % (rel, chk.count(b'\r\n'),
                                      chk.count(b'\n') - chk.count(b'\r\n')))
    return res, crlf


print('=' * 100)
print('规则① 洗盘文案降级  —— 补丁开始')
print('=' * 100)

# ---------------------------------------------------------------- 1) 引擎
ENG = r'services\band_pattern_engine.py'
const_old = """_DISTP_NOTE_MODE = 'watch'   # 'watch' 追加观察文案（默认）；'off' 只写字段不提示
_DISTP_FUNNEL = {'ok': 0, 'insuf': 0, 'stall': 0, 'break': 0, 'dtop': 0,
                 'hit': 0, 'note': 0}
"""
const_new = const_old + """
# ---- 洗盘文案降级（2026-10-11）----
# 依据：滚动观测里「控盘分>=85 且 stage_guess='wash'」这一组的胜率约 37.9%，
# 低于全样本基准 45.2%；换过多档位置/分数门槛都跑不赢基准。
# 结论：字段有价值（stage_guess 仍记录 wash，可用于事后复盘），提示没有价值。
# 处理：文案默认关闭 —— 界面上不再出现「高度控盘 + 疑似洗盘，关注启动」；
#      判定逻辑一个字没改（still 以 judge_wash_or_distribute 的 stage_guess 为准）。
_WASH_NOTE_MODE = 'off'   # 'off' 不出洗盘文案（默认，依据见上）；'watch' 恢复旧文案
"""

branch_old = """        if ctrl >= _CTRL_HIGH and stage == 'wash':
            out.append('高度控盘 + 疑似洗盘，关注启动')
"""
branch_new = """        # 2026-10-11 降级：wash 组实测胜率 37.9% < 全样本基准 45.2%，暂不作为提示。
        # stage_guess 仍照常写 'wash'（字段保留）；要恢复旧文案把 _WASH_NOTE_MODE
        # 改回 'watch' 即可，无需改代码。
        if _WASH_NOTE_MODE != 'off' and ctrl >= _CTRL_HIGH and stage == 'wash':
            out.append('高度控盘 + 疑似洗盘，关注启动')
"""

doc_old = """    返回 list[str]，无提示返回 []。异常时返回 []（宁可没标签，不给错标签）。
    \"\"\"
    out = []
    try:
        # 2026-10-11 降级"""
doc_new = """    洗盘文案自 2026-10-11 起默认关闭（_WASH_NOTE_MODE='off'，依据见该常量注释）；
    stage_guess 仍照常记录 wash / distribute / unknown。

    返回 list[str]，无提示返回 []。异常时返回 []（宁可没标签，不给错标签）。
    \"\"\"
    out = []
    try:
        # 2026-10-11 降级"""

print('[1] 引擎 services\\band_pattern_engine.py')
patch(ENG, [(const_old, const_new, 1),
            (branch_old, branch_new, 1),
            (doc_old, doc_new, 1)])

# ---------------------------------------------------------------- 2) 历史单测
print('[2] 历史单测里的 wash 期望值同步')
patch(r'tools\_c1c2_unit.py', [
    ("E._ctrl_note(90.0, 'wash', 0.30), '高度控盘 + 疑似洗盘，关注启动')",
     "E._ctrl_note(90.0, 'wash', 0.30), '')                 # 2026-10-11 wash 文案关闭", None),
    ("E._ctrl_note(90.0, 'wash', 0.20), '高度控盘 + 疑似洗盘，关注启动 ｜ 高度控盘候选')",
     "E._ctrl_note(90.0, 'wash', 0.20), '高度控盘候选')      # 2026-10-11 wash 文案关闭", None),
    ("E._ctrl_note(90.0, 'wash', 0.60), '高度控盘 + 疑似洗盘，关注启动')",
     "E._ctrl_note(90.0, 'wash', 0.60), '')                 # 2026-10-11 wash 文案关闭", None),
    ("E._ctrl_note(90.0, 'wash', None), '高度控盘 + 疑似洗盘，关注启动')",
     "E._ctrl_note(90.0, 'wash', None), '')                 # 2026-10-11 wash 文案关闭", None),
])

patch(r'tools\_c3c5_unit.py', [
    ("E._ctrl_note(90.0, 'wash', 0.20), '高度控盘 + 疑似洗盘，关注启动 ｜ 高度控盘候选')",
     "E._ctrl_note(90.0, 'wash', 0.20), '高度控盘候选')      # 2026-10-11 wash 文案关闭", None),
    ("E._ctrl_note(90.0, 'wash', 0.30), '高度控盘 + 疑似洗盘，关注启动')",
     "E._ctrl_note(90.0, 'wash', 0.30), '')                 # 2026-10-11 wash 文案关闭", None),
])

patch(r'tools\_buildfactor_unit.py', [
    ("(95.0, 'wash', 0.10, '高度控盘 + 疑似洗盘，关注启动 ｜ 高度控盘候选'),",
     "(95.0, 'wash', 0.10, '高度控盘候选'),   # 2026-10-11 wash 文案关闭", None),
    ("(95.0, 'wash', 0.90, '高度控盘 + 疑似洗盘，关注启动'),",
     "(95.0, 'wash', 0.90, ''),   # 2026-10-11 wash 文案关闭", None),
])

patch(r'tools\_test_ctrl_dist.py', [
    ("(86.0,'wash',0.90, '高度控盘 + 疑似洗盘，关注启动'),",
     "(86.0,'wash',0.90, ''),   # 2026-10-11 wash 文案关闭", None),
    ("(90.0,'wash',0.30, '高度控盘 + 疑似洗盘，关注启动 ｜ 高度控盘候选'),",
     "(90.0,'wash',0.30, '高度控盘候选'),   # 2026-10-11 wash 文案关闭", None),
])

patch(r'tools\_ctrltag_unit.py', [
    ("E._ctrl_note_tags(85.0, 'wash', 0.5) == ['高度控盘 + 疑似洗盘，关注启动'],",
     "E._ctrl_note_tags(85.0, 'wash', 0.5) == [],   # 2026-10-11 wash 文案关闭（_WASH_NOTE_MODE='off'）", None),
])

# ---------------------------------------------------------------- 3) 两个等价比对脚本
print('[3] 与备份模块做全矩阵比对的 2 个脚本（剥离洗盘段后再比）')
STRIP_OLD = """                    a = E._ctrl_note(ctrl, stage, pos, None, None, c4, c6)
                    b = Old._ctrl_note(ctrl, stage, pos, None, None, c4, c6)
                    if a != b:"""
STRIP_NEW = """                    a = E._ctrl_note(ctrl, stage, pos, None, None, c4, c6)
                    b = Old._ctrl_note(ctrl, stage, pos, None, None, c4, c6)
                    # 2026-10-11 起 wash 文案默认关闭：把旧版输出里的那一段剥掉后，
                    # 其余文案必须逐字一致（这才是本次要守的不变量）。
                    b = ' ｜ '.join(x for x in b.split(' ｜ ')
                                    if x != '高度控盘 + 疑似洗盘，关注启动')
                    if a != b:"""

patch(r'tools\_probedist_unit.py', [
    (STRIP_OLD, STRIP_NEW, 1),
    ("check('旧参数组合下 _ctrl_note 输出与改动前逐字一致', not diff,",
     "check('旧参数组合下 _ctrl_note 输出与改动前逐字一致（已剔除 2026-10-11 关闭的洗盘文案）', not diff,", 1),
])

patch(r'tools\_ctrltag_unit.py', [
    (STRIP_OLD, STRIP_NEW, 1),
    ("check('全矩阵输出与改动前逐字一致（含 C4/C6 文案）', not diff,",
     "check('全矩阵输出与改动前逐字一致（含 C4/C6 文案；已剔除 2026-10-11 关闭的洗盘文案）', not diff,", 1),
])

print('')
print('补丁结束。备份后缀：%s' % SUF)
