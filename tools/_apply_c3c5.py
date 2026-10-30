# -*- coding: utf-8 -*-
"""C3 + C5 精确落盘（2026-10-10）

C3  services/band_pattern_engine.py  _ctrl_note 规则③
    「分数主导 score>=_CTRL_CAND(90) & pos<_CTRL_POS_LOW(0.4)」
 -> 「位置主导 pos<_CTRL_CAND_POS(0.25) & ctrl>=_CTRL_HIGH(85)」

C5  strategy/base.py                  estimate_control_score 的振幅分量
    「100 - amp*300」（振幅越低分越高）
 -> 「峰值 4.0% 的帐篷」（过低与过高同样降分）

同时同步 3 个工具里的复刻公式，避免重演 C2 那次「复刻没同步 -> 对拍偏差 / 分量归因失真」：
    tools/_audit_ctrl_reverse.py   对拍用的 amp 分量复刻 + 规则③口径
    tools/_c1c2_compare.py         规则③口径
    tools/_c1c2_unit.py            对拍用的 amp 分量复刻 + 规则③期望值

约定：先 shutil.copy2 备份 -> 行尾标准化 -> assert count==1 -> 替换 -> 按原行尾写回 -> py_compile
"""
import io
import os
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
SUF = '.bak_before_c3c5_20261010_2100'

report = []


def patch(rel, edits, eol):
    p = os.path.join(ROOT, rel)
    raw = io.open(p, encoding='utf-8', newline='').read()
    n_crlf = raw.count('\r\n')
    n_lf = raw.count('\n') - n_crlf
    bak = p + SUF
    shutil.copy2(p, bak)
    s = raw.replace('\r\n', '\n')
    for old, new in edits:
        c = s.count(old)
        assert c == 1, '[锚点命中 %d 次] %s :: %r' % (c, rel, old[:70])
        s = s.replace(old, new)
    out = s.replace('\n', '\r\n') if eol == '\r\n' else s
    io.open(p, 'w', encoding='utf-8', newline='').write(out)
    # 回读校验
    back = io.open(p, encoding='utf-8', newline='').read()
    n_crlf2 = back.count('\r\n')
    n_lf2 = back.count('\n') - n_crlf2
    assert back.replace('\r\n', '\n') == s, '回读内容不一致: ' + rel
    if eol == '\r\n':
        assert n_lf2 == 0 and n_crlf2 > 0, '行尾被破坏(应纯CRLF): %s crlf=%d lf=%d' % (rel, n_crlf2, n_lf2)
    else:
        assert n_crlf2 == 0, '行尾被破坏(应纯LF): %s crlf=%d' % (rel, n_crlf2)
    r = subprocess.run([PY, '-X', 'utf8', '-m', 'py_compile', p],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    ok = (r.returncode == 0)
    assert ok, 'py_compile 失败: %s\n%s' % (rel, r.stderr)
    report.append('  %-38s 行尾=%-4s 编辑%d处  crlf %d->%d / lf %d->%d  py_compile OK'
                  % (rel, 'CRLF' if eol == '\r\n' else 'LF', len(edits),
                     n_crlf, n_crlf2, n_lf, n_lf2))


# ==================================================================
# 1) services/band_pattern_engine.py  —— C3（纯 LF）
# ==================================================================
ENG = 'services/band_pattern_engine.py'
E = []

# 1.1 头部注释：登记 C3
E.append((
    "#   _CTRL_DIST_POS=0.65」—— 旧口径方向是反的，依据见 _CTRL_DIST_POS 注释。\n"
    "_CTRL_HIGH = 85.0        # 高度控盘线\n",

    "#   _CTRL_DIST_POS=0.65」—— 旧口径方向是反的，依据见 _CTRL_DIST_POS 注释。\n"
    "#   规则③「高度控盘候选」2026-10-10（C3）由「分数主导」改为「位置主导」，\n"
    "#   位置阈值改看 _CTRL_CAND_POS=0.25，依据见该常量注释。\n"
    "_CTRL_HIGH = 85.0        # 高度控盘线（规则①与规则③共用）\n"))

# 1.2 常量：停用 _CTRL_CAND，新增 _CTRL_CAND_POS；_CTRL_POS_LOW 标停用
E.append((
    "_CTRL_CAND = 90.0        # 高度控盘候选线\n"
    "_CTRL_POS_LOW = 0.4      # 「位置较低」= 近120日位置 < 0.4（与评分里的加权阈值一致）\n",

    "_CTRL_CAND = 90.0        # 【已停用 2026-10-10（C3）】原为「高度控盘候选线」（规则③的分数门槛）。\n"
    "                         #   保留常量仅为兼容 tools\\_*.py 旧脚本的 import；\n"
    "                         #   _ctrl_note 已不再引用它，不要再用它做候选判断。\n"
    "_CTRL_CAND_POS = 0.25    # 规则③「高度控盘候选」的位置上限（C3 新增）：近120日位置 < 0.25。\n"
    "                         #   2026-10-10 由「分数主导(score>=90 & pos<0.4)」改为\n"
    "                         #   「位置主导 + 分数过滤(pos<0.25 & ctrl>=85)」。依据（17570 条滚动观测）：\n"
    "                         #     旧  score>=90 & pos<0.4  -> n=3220 r20 -0.01% 胜率44.9% t=-0.03（零区分度）\n"
    "                         #     新  pos<0.25 & ctrl>=85  -> n=3474 r20 +0.22% 胜率46.5% t=+1.17\n"
    "                         #   备注：纯 pos<0.25 不筛分数 t=+3.73 更强（n=10598），说明残留的\n"
    "                         #   分数门槛仍偏严，留待后续评估是否放开，不要擅自改。\n"
    "_CTRL_POS_LOW = 0.4      # 【已停用 2026-10-10（C3）】原为规则③的位置上限。\n"
    "                         #   保留常量仅为兼容旧脚本 import；该值同时仍是评分里\n"
    "                         #   pos_weight 的 1.2 倍分界（见 strategy/base.py），不要删。\n"))

# 1.3 规则③ 本体：改为位置主导
E.append((
    "        if ctrl >= _CTRL_CAND and pos is not None and pos < _CTRL_POS_LOW:\n"
    "            out.append('高度控盘候选')\n",

    "        # C3（2026-10-10）：改为位置主导 —— 先看是否在低位区，再用控盘分过滤\n"
    "        if pos is not None and pos < _CTRL_CAND_POS and ctrl >= _CTRL_HIGH:\n"
    "            out.append('高度控盘候选')\n"))

patch(ENG, E, '\n')


# ==================================================================
# 2) strategy/base.py  —— C5（纯 CRLF）
# ==================================================================
BAS = 'strategy/base.py'
B = []

# 2.1 docstring 实现说明追加第 4 条
B.append((
    "        3. 所有中间量做 NaN / 除零 / 缺列防护。\n"
    "        \"\"\"\n",

    "        3. 所有中间量做 NaN / 除零 / 缺列防护。\n"
    "        4. C5（2026-10-10）：振幅分量原为「100 - amp*300」，即振幅越低分越高；\n"
    "           实测方向是反的（低位区 amp<2.5% 未来20日收益为负、胜率仅 29~41%，\n"
    "           峰值在 amp≈3.75~4.5%）。已改为峰值 4.0% 的帐篷函数。\n"
    "        \"\"\"\n"))

# 2.2 振幅分量本体
B.append((
    "            # ---- 3. 振幅收敛 ----\n"
    "            amp = ((recent['high'] - recent['low'])\n"
    "                   / (recent['close'] + 1e-8)).mean()\n"
    "            amp_score = _clamp100(100.0 - float(amp) * 300.0)\n",

    "            # ---- 3. 振幅适中度（C5：原「振幅越小分越高」方向是反的）----\n"
    "            #   17570 条滚动观测实测（低位区 pos<0.25，未来20日）：\n"
    "            #     amp < 1.5%    -> r20 -1.16% 胜率 28.9%（死票）\n"
    "            #     amp 2.5~3%    -> r20 +0.23% 胜率 49.2%\n"
    "            #     amp 3.75~4.5% -> r20 +1.19% 胜率 54.7%（峰值）\n"
    "            #     amp 4.5~5.5%  -> r20 +0.29% 胜率 50.0%\n"
    "            #     amp 5.5~7%    -> r20 -0.42% 胜率 44.1%\n"
    "            #   故改为「峰值 4.0% 的帐篷」：过低（死票）与过高同样降分。\n"
    "            amp = ((recent['high'] - recent['low'])\n"
    "                   / (recent['close'] + 1e-8)).mean()\n"
    "            amp20 = float(amp)\n"
    "            if amp20 <= 0.040:\n"
    "                amp_score = 100.0 - (0.040 - amp20) * 2300.0\n"
    "            else:\n"
    "                amp_score = 100.0 - (amp20 - 0.040) * 1200.0\n"
    "            amp_score = _clamp100(amp_score)\n"))

patch(BAS, B, '\r\n')


# ==================================================================
# 3) tools/_audit_ctrl_reverse.py —— 同步复刻（防 C2 那次的坑）
# ==================================================================
AUD = 'tools/_audit_ctrl_reverse.py'
A = []

# 3.1 import 增加 _CTRL_CAND_POS
A.append((
    "                                          _CTRL_DIST, _CTRL_POS_LOW,\n"
    "                                          _CTRL_DIST_POS)\n",
    "                                          _CTRL_DIST, _CTRL_POS_LOW,\n"
    "                                          _CTRL_DIST_POS, _CTRL_CAND_POS)\n"))

# 3.2 阈值打印补全
A.append((
    "P('阈值实测: _CTRL_HIGH=%s _CTRL_CAND=%s _CTRL_DIST=%s(已停用) _CTRL_DIST_POS=%s _CTRL_POS_LOW=%s'\n"
    "  % (_CTRL_HIGH, _CTRL_CAND, _CTRL_DIST, _CTRL_DIST_POS, _CTRL_POS_LOW))\n",
    "P('阈值实测: _CTRL_HIGH=%s _CTRL_CAND=%s(已停用C3) _CTRL_CAND_POS=%s '\n"
    "  '_CTRL_DIST=%s(已停用C1) _CTRL_DIST_POS=%s _CTRL_POS_LOW=%s(已停用C3)'\n"
    "  % (_CTRL_HIGH, _CTRL_CAND, _CTRL_CAND_POS, _CTRL_DIST, _CTRL_DIST_POS, _CTRL_POS_LOW))\n"))

# 3.3 对拍用的 amp 分量复刻 —— 必须与 C5 同步，否则分量归因全失真
A.append((
    "    ams = max(0.0, min(100.0, 100.0 - amp * 300.0))\n",
    "    # 2026-10-10 C5：真函数已把振幅分量从「越低越高」改为「峰值 4.0% 帐篷」，\n"
    "    # 复刻必须同步，否则对拍会出现几十点偏差、分量归因全失真。\n"
    "    if amp <= 0.040:\n"
    "        ams = 100.0 - (0.040 - amp) * 2300.0\n"
    "    else:\n"
    "        ams = 100.0 - (amp - 0.040) * 1200.0\n"
    "    ams = max(0.0, min(100.0, ams))\n"))

# 3.4 规则③ 复刻改为新口径 + 保留旧口径对照
A.append((
    "r3 = O[(O['score'] >= _CTRL_CAND) & (O['pos120'] < _CTRL_POS_LOW)]\n",
    "# 2026-10-10 C3：规则③ 已由「分数主导(score>=_CTRL_CAND & pos<_CTRL_POS_LOW)」改为\n"
    "# 「位置主导(pos<_CTRL_CAND_POS & score>=_CTRL_HIGH)」\n"
    "r3 = O[(O['pos120'] < _CTRL_CAND_POS) & (O['score'] >= _CTRL_HIGH)]\n"
    "r3_ref = O[(O['score'] >= _CTRL_CAND) & (O['pos120'] < _CTRL_POS_LOW)]\n"))

A.append((
    "                ('③高度控盘候选', r3)):\n",
    "                ('③高度控盘候选(新:位置)', r3),\n"
    "                ('③高度控盘候选(旧:分数)', r3_ref)):\n"))

# 3.5 [B7] 标题：_CTRL_CAND 已停用，改成「分数本身」的区分度
A.append((
    "P('\\n[B7] 阈值敏感性：如果把 _CTRL_CAND 从 90 调到 80 / 82 / 85')\n",
    "P('\\n[B7] 控盘分阈值敏感性（已与规则③解耦，只看「分数本身」的区分度）')\n"))

# 3.6 新增 [B9]：振幅分量分档（C5 的可复现依据）
A.append((
    "# 落 CSV\n",
    "P('\\n[B9] 振幅分量（C5 目标）分档：未来20日表现 + 新旧 amp_score 对照')\n"
    "for _lo, _hi in ((0, 0.02), (0.02, 0.025), (0.025, 0.03), (0.03, 0.0375),\n"
    "                 (0.0375, 0.045), (0.045, 0.055), (0.055, 0.07), (0.07, 9)):\n"
    "    sub = O[(O['amp'] >= _lo) & (O['amp'] < _hi)]\n"
    "    if len(sub) < 20:\n"
    "        continue\n"
    "    mid = (_lo + min(_hi, 0.12)) / 2.0\n"
    "    old_ = max(0.0, min(100.0, 100.0 - mid * 300.0))\n"
    "    new_ = (100.0 - (0.040 - mid) * 2300.0) if mid <= 0.040 else (100.0 - (mid - 0.040) * 1200.0)\n"
    "    P('   amp[%.3f,%.3f) n=%5d | r20=%6.2f%% 胜率20=%5.1f%% mdd20=%6.2f%% | amp_score 旧%5.1f -> 新%5.1f'\n"
    "      % (_lo, _hi, len(sub), sub['r20'].mean(), 100.0 * (sub['r20'] > 0).mean(),\n"
    "         sub['mdd20'].mean(), old_, max(0.0, min(100.0, new_))))\n"
    "\n"
    "# 落 CSV\n"))

patch(AUD, A, '\n')


# ==================================================================
# 4) tools/_c1c2_compare.py —— 规则③口径同步
# ==================================================================
CMP = 'tools/_c1c2_compare.py'
C = []
C.append((
    "P('[5] 规则①③ 命中条数（应只受分数偏移影响，规则本身未改）')\n",
    "P('[5] 规则①③ 命中条数（①未改；③已按 C3 改为位置主导，同时列旧口径对照）')\n"))
C.append((
    "              ('③高度控盘候选  score>=90 & pos<0.4', lambda D: (D.score >= E._CTRL_CAND) & (D.pos120 < E._CTRL_POS_LOW))):\n",
    "              ('③高度控盘候选(新:位置主导)', lambda D: (D.pos120 < E._CTRL_CAND_POS) & (D.score >= E._CTRL_HIGH)),\n"
    "              ('③高度控盘候选(旧:分数主导)', lambda D: (D.score >= E._CTRL_CAND) & (D.pos120 < E._CTRL_POS_LOW))):\n"))
patch(CMP, C, '\n')


# ==================================================================
# 5) tools/_c1c2_unit.py —— 复刻与期望值同步（保持 C1/C2 回归可跑）
# ==================================================================
UNT = 'tools/_c1c2_unit.py'
U = []
U.append((
    "P('   _CTRL_HIGH=%s  _CTRL_CAND=%s  _CTRL_POS_LOW=%s' % (E._CTRL_HIGH, E._CTRL_CAND, E._CTRL_POS_LOW))\n"
    "P('   _CTRL_DIST=%s（已停用）  _CTRL_DIST_POS=%s' % (E._CTRL_DIST, E._CTRL_DIST_POS))\n",
    "P('   _CTRL_HIGH=%s  _CTRL_CAND=%s（已停用C3）  _CTRL_CAND_POS=%s  _CTRL_POS_LOW=%s（已停用C3）'\n"
    "  % (E._CTRL_HIGH, E._CTRL_CAND, E._CTRL_CAND_POS, E._CTRL_POS_LOW))\n"
    "P('   _CTRL_DIST=%s（已停用）  _CTRL_DIST_POS=%s' % (E._CTRL_DIST, E._CTRL_DIST_POS))\n"))
# C3 之后 pos=0.30 不再命中规则③
U.append((
    "chk('wash + ctrl=90 + pos=0.30 -> ①+③ 合并（设计如此）',\n"
    "    E._ctrl_note(90.0, 'wash', 0.30), '高度控盘 + 疑似洗盘，关注启动 ｜ 高度控盘候选')\n",
    "# 2026-10-10 C3：规则③ 位置门槛改为 <0.25，pos=0.30 不再命中③\n"
    "chk('wash + ctrl=90 + pos=0.30 -> 仅①（C3 后 ③ 位置门槛=0.25）',\n"
    "    E._ctrl_note(90.0, 'wash', 0.30), '高度控盘 + 疑似洗盘，关注启动')\n"
    "chk('wash + ctrl=90 + pos=0.20 -> ①+③ 合并（设计如此）',\n"
    "    E._ctrl_note(90.0, 'wash', 0.20), '高度控盘 + 疑似洗盘，关注启动 ｜ 高度控盘候选')\n"))
# 对拍用的 amp 分量复刻
U.append((
    "amp = ((recent['high'] - recent['low']) / (recent['close'] + 1e-8)).mean()\n"
    "amps = _clamp100(100.0 - float(amp) * 300.0)\n",
    "amp = ((recent['high'] - recent['low']) / (recent['close'] + 1e-8)).mean()\n"
    "# 2026-10-10 C5：振幅分量已改为「峰值 4.0% 帐篷」，复刻同步\n"
    "amps = (100.0 - (0.040 - float(amp)) * 2300.0) if float(amp) <= 0.040 \\\n"
    "    else (100.0 - (float(amp) - 0.040) * 1200.0)\n"
    "amps = _clamp100(amps)\n"))
patch(UNT, U, '\n')


print('=' * 100)
print('C3 + C5 落盘完成')
print('=' * 100)
for line in report:
    print(line)
print('\n备份后缀: %s' % SUF)
