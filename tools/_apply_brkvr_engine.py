# -*- coding: utf-8 -*-
"""一次性补丁：把 A（破位—收复）/ B（量能分位）/ C（markup② 位置下限）接进引擎。

依据（都是真实标定，不是手感）：
  tools\\brk_volgem_calib.txt  —— A/B 标定（17516 条滚动观测 / 锚点 20/40/60/80 / 无未来数据）
  tools\\markup2_pos_calib.txt —— C 的补充标定（放开 ② 自身位置下限）
结论：
  A「破位未收」 -3.63% / 胜率 33.9% / t=-3.76  -> 出风险文案
  A「洗盘收复」 -1.08% / t=-1.75（低位档 -0.41% / t=-0.65 不显著） -> 只写字段
  B「天量」     -2.44% / t=-8.36（各位置档全负） -> 出警示
  B「缩量上涨」 全位置 +2.64% / t=+4.84；pos<0.45 档 +4.34% / 胜率 66.4% / t=+8.21 -> 限低位出
  B「地量」     +0.02% / t=+0.14（噪音，低位才 +0.34% / t=+2.21） -> 只写字段
  C ② 位置下限 0.55 把它锁在唯一为负区间（[0.55,0.75) -2.83% / t=-2.89）；
    放开下限后 pos<0.35 = +2.36% / 胜率 58.1% / t=+11.66 -> 下限改 0.00（全局门槛 0.45 仍生效）

改两个文件：
  strategy\\base.py（纯 CRLF）：只改 MARKUP_LOCK_POS_MIN 的值与注释 + detect_markup docstring 一句
  services\\band_pattern_engine.py（纯 LF）：加 5 个 DB 字段 + 2 组漏斗 + 文案分支
执行一次即失效，勿重跑。
"""
import io
import os
import re
import shutil

os.chdir(r'D:\QuantMonitorV6')

# ==================================================================
# 一、strategy\base.py —— C 项（② 位置下限 0.55 -> 0.00）
# ==================================================================
PB = os.path.join('strategy', 'base.py')
sb = io.open(PB, encoding='utf-8', newline='').read()
NL = '\r\n'
assert sb.count('\n') == sb.count(NL), 'base.py 应为纯 CRLF'

old = 'MARKUP_LOCK_POS_MIN = 0.55  # ② 位置下限（锁仓拉升必然已离开底部）' + NL
assert sb.count(old) == 1, '② 位置下限锚点不唯一'
new = ('MARKUP_LOCK_POS_MIN = 0.00  # ② 位置下限：2026-10-11 由 0.55 改为 0.00'
       '（依据 tools\\markup2_pos_calib.txt）' + NL +
       '                                #   原值 0.55 把 ② 锁在唯一为负的区间：'
       'pos∈[0.55,0.75) -2.83%/t=-2.89；' + NL +
       '                                #   放开下限后 pos<0.35 = +2.36%/胜率58.1%/t=+11.66、'
       '[0.35,0.45) +1.48%/t=+2.18。' + NL +
       '                                #   全局门槛 MARKUP_POS_MAX=0.45 仍在，'
       '故 ② 只在 pos<0.45（正期望区）生效。' + NL)
sb = sb.replace(old, new)

old_doc = '        ⚠ 连带后果：形态②缩量强势要求 pos>=0.55，被本门槛完全覆盖后【不可达】。' + NL
assert sb.count(old_doc) == 1, 'docstring ② 不可达 锚点不唯一'
new_doc = ('        ⚠ 形态②缩量强势自 2026-10-11 起位置下限改为 MARKUP_LOCK_POS_MIN=0.00'
           '（依据 tools\\markup2_pos_calib.txt），' + NL +
           '        在本门槛（pos<0.45）内可正常命中，且标定显示它在该区间是正期望。' + NL)
sb = sb.replace(old_doc, new_doc)
shutil.copy2(PB, PB + '.bak_before_brkvr_engine')
io.open(PB, 'w', encoding='utf-8', newline='').write(sb)
_chk = io.open(PB, encoding='utf-8', newline='').read()
print('base.py：行 %d ｜ CRLF %d ｜ 裸LF %d ｜ ②下限=%.2f'
      % (_chk.count('\n'), _chk.count(NL), _chk.count('\n') - _chk.count(NL),
         0.0 if 'MARKUP_LOCK_POS_MIN = 0.00' in _chk else 0.55))

# ==================================================================
# 二、services\band_pattern_engine.py
# ==================================================================
PE = os.path.join('services', 'band_pattern_engine.py')
se = io.open(PE, encoding='utf-8', newline='').read()
assert '\r\n' not in se, 'band_pattern_engine.py 应为纯 LF'
n0 = se.count('\n')

# --- 1. 模块常量 + 漏斗 -------------------------------------------------
anchor_const = ("_MARKUP_FUNNEL = {'ok': 0, 'insuf': 0, 'pos': 0, 'trend': 0, 'lock': 0,\n"
                "                  'acc': 0, 'hit': 0, 'note': 0}\n")
assert se.count(anchor_const) == 1, 'MARKUP_FUNNEL 锚点不唯一'
new_const = anchor_const + """
# 破位—收复 双向判据（A 项，2026-10-11）。文案默认 'watch'：只出【风险侧】——
# 「破位未收」标定为 -3.63% / 胜率 33.9% / t=-3.76（显著负），值得提示；
# 「洗盘收复」在低位只是不显著（-0.41% / t=-0.65），按项目「无信息不出文案」只写字段。
# 依据 tools\\brk_volgem_calib.txt（17516 条滚动观测 / 锚点 20/40/60/80 / 无未来数据）。
_BRK_NOTE_MODE = 'watch'   # 'watch' 追加观察文案（默认）；'off' 只写字段不提示
_BRK_FUNNEL = {'ok': 0, 'insuf': 0, 'pos': 0, 'nobreak': 0, 'wash': 0, 'dist': 0, 'note': 0}

# 量能分位 / 缩量上涨（B 项，2026-10-11）。文案默认 'watch'：
#   天量     全位置档都显著为负（-2.44% / t=-8.36）-> 出警示
#   缩量上涨 只有 pos<0.45 显著为正（+4.34% / 胜率 66.4% / t=+8.21）-> 限低位出
#   地量     整体噪音（+0.02% / t=+0.14）-> 只写字段（vreg_tags），不出文案
# 依据同上（tools\\brk_volgem_calib.txt）。
_VREG_NOTE_MODE = 'watch'   # 'watch' 追加观察文案（默认）；'off' 只写字段不提示
_VREG_FUNNEL = {'ok': 0, 'insuf': 0, 'low': 0, 'high': 0, 'shrinkup': 0, 'note': 0}
"""
se = se.replace(anchor_const, new_const)

# --- 2. 拉升注释里「② 不可达」的说明更新 -------------------------------
old_cmt = ('#   因此 markup_ok=1 只会落在 pos120<0.45 的票上；连带形态②缩量强势（自带 pos>=0.55）不可达。\n')
assert se.count(old_cmt) == 1, '拉升②不可达注释 锚点不唯一'
se = se.replace(old_cmt,
                '#   因此 markup_ok=1 只会落在 pos120<0.45 的票上。\n'
                '# 2026-10-11 修正：形态②缩量强势原来的位置下限 0.55 把它锁在唯一为负的区间\n'
                '#   （[0.55,0.75) -2.83%/t=-2.89），已按 tools\\markup2_pos_calib.txt 改成 0.00，\n'
                '#   于是 ② 在 pos<0.45（+2.36%/胜率58.1%/t=+11.66）区间恢复可命中。\n')

# --- 3. _ctrl_note / _observe_tags 新增参数与文案 ----------------------
old_sig = ('def _observe_tags(stack=None, redfat=None, c4=None, c6=None, low_ctrl=False,\n'
           '                  probe=None, distpat=None, markup=None):\n')
assert se.count(old_sig) == 1, '_observe_tags 签名 锚点不唯一'
se = se.replace(old_sig,
                'def _observe_tags(stack=None, redfat=None, c4=None, c6=None, low_ctrl=False,\n'
                '                  probe=None, distpat=None, markup=None, brk=None, vreg=None,\n'
                '                  pos=None):\n')

old_tail = ("        # 拉升阶段识别文案（默认 'watch'；与试盘/出货形态同为观察类，方向见常量注释）\n"
            "        if _MARKUP_NOTE_MODE != 'off' and markup:\n"
            "            out.append('拉升观察：%s' % markup)\n")
assert se.count(old_tail) == 1, '_observe_tags 文案尾部 锚点不唯一'
new_tail = old_tail + """        # A 破位—收复（默认 'watch'）：只出风险侧文案，洗盘侧只写字段（依据见 _BRK_NOTE_MODE）
        if _BRK_NOTE_MODE != 'off' and brk == '破位未收':
            out.append('破位警示：放量破位未收回')
        # B 量能分位（默认 'watch'）：天量出警示；缩量上涨只在 pos<0.45 出（依据见 _VREG_NOTE_MODE）
        if _VREG_NOTE_MODE != 'off' and vreg:
            _vt = [x for x in str(vreg).split('|') if x]
            if '天量' in _vt:
                out.append('天量警示')
            if '缩量上涨' in _vt and pos is not None and pos < 0.45:
                out.append('缩量上涨·疑似控盘')
"""
se = se.replace(old_tail, new_tail)

old_call = ("    return ' ｜ '.join(_ctrl_note_tags(ctrl, stage, pos)\n"
            "                      + _observe_tags(stack, redfat, c4, c6, _low_ctrl,\n"
            "                                      probe, distpat, markup))\n")
assert se.count(old_call) == 1, '_ctrl_note 内 _observe_tags 调用 锚点不唯一'
se = se.replace(old_call,
                "    return ' ｜ '.join(_ctrl_note_tags(ctrl, stage, pos)\n"
                "                      + _observe_tags(stack, redfat, c4, c6, _low_ctrl,\n"
                "                                      probe, distpat, markup, brk, vreg, pos))\n")

old_cs = ('def _ctrl_note(ctrl, stage, pos, stack=None, redfat=None, c4=None, c6=None,\n'
          '               probe=None, distpat=None, markup=None):\n')
assert se.count(old_cs) == 1, '_ctrl_note 签名 锚点不唯一'
se = se.replace(old_cs,
                'def _ctrl_note(ctrl, stage, pos, stack=None, redfat=None, c4=None, c6=None,\n'
                '               probe=None, distpat=None, markup=None, brk=None, vreg=None):\n')

# --- 4. _ALL_COLS 加 5 列 ----------------------------------------------
old_cols = "    ('markup_ok', 'INTEGER'), ('markup_type', 'TEXT'),\n    ('markup_score', 'REAL'),\n"
assert se.count(old_cols) == 1, '_ALL_COLS 锚点不唯一'
se = se.replace(old_cols, old_cols +
                "    ('brk_ok', 'INTEGER'), ('brk_type', 'TEXT'), ('brk_score', 'REAL'),\n"
                "    ('vreg_tags', 'TEXT'), ('vreg_pct', 'REAL'),\n")

# --- 5. _save_or_update：列清单 / 占位符 / 取值 -------------------------
old_ins = ("             markup_ok, markup_type, markup_score,\n"
           "             created_at, updated_at)\n")
assert se.count(old_ins) == 1, 'INSERT 列清单 锚点不唯一'
se = se.replace(old_ins,
                "             markup_ok, markup_type, markup_score,\n"
                "             brk_ok, brk_type, brk_score, vreg_tags, vreg_pct,\n"
                "             created_at, updated_at)\n")

m = re.search(r'\n(\s*)VALUES \((?:\?,)*\?\)"""', se)
assert m, 'VALUES 占位符行未找到'
_ph_old = m.group(0)
_nph = _ph_old.count('?')
assert _nph == 59, '占位符应为 59，实际 %d' % _nph
_ph_new = '\n%sVALUES (%s)"""' % (m.group(1), ','.join(['?'] * (_nph + 5)))
se = se.replace(_ph_old, _ph_new)

old_val = ("            rec.get('markup_ok',0), rec.get('markup_type',''),\n"
           "            rec.get('markup_score',0),\n")
assert se.count(old_val) == 1, 'INSERT 取值 锚点不唯一'
se = se.replace(old_val, old_val +
                "            rec.get('brk_ok',0), rec.get('brk_type',''), rec.get('brk_score',0),\n"
                "            rec.get('vreg_tags',''), rec.get('vreg_pct'),\n")

# --- 6. scan_stock 局部量 ----------------------------------------------
old_loc = "        _markup_ok, _markup_sc, _markup_type = False, 0.0, ''\n"
assert se.count(old_loc) == 1, 'markup 局部量 锚点不唯一'
se = se.replace(old_loc, old_loc +
                "        _brk_ok, _brk_type, _brk_sc = False, '', 0.0\n"
                "        _vreg_tags, _vreg_pct = '', None\n")

# --- 7. scan_stock 计算块（接在 markup 漏斗之后） ----------------------
old_calc = ("                        elif _markup_type == '加速迹象':\n"
            "                            _MARKUP_FUNNEL['acc'] += 1\n")
assert se.count(old_calc) == 1, 'markup 计算块尾部 锚点不唯一'
new_calc = old_calc + """                # A 破位—收复 双向判据（复用同一个 df；只做观察）
                _br = _ti.detect_breakdown_recover(_df)
                _brk_ok = bool(_br.get('ok'))
                _brk_type = _br.get('type') or ''
                _brk_sc = float(_br.get('score') or 0.0)
                _brr = _br.get('reason') or ''
                if _brr.startswith('pos>'):
                    _BRK_FUNNEL['pos'] += 1
                elif _brr == 'no_break':
                    _BRK_FUNNEL['nobreak'] += 1
                elif _brr:
                    _BRK_FUNNEL['insuf'] += 1
                else:
                    _BRK_FUNNEL['ok'] += 1
                    if _brk_type == '洗盘收复':
                        _BRK_FUNNEL['wash'] += 1
                    elif _brk_type == '破位未收':
                        _BRK_FUNNEL['dist'] += 1
                # B 量能分位 / 缩量上涨（复用同一个 df；只做观察）
                _vg = _ti.detect_volume_regime(_df)
                _vreg_tags = '|'.join(_vg.get('tags') or [])
                _vreg_pct = _vg.get('pct')
                if _vg.get('reason'):
                    _VREG_FUNNEL['insuf'] += 1
                else:
                    _VREG_FUNNEL['ok'] += 1
                    _vgt = _vg.get('tags') or []
                    if '地量' in _vgt:
                        _VREG_FUNNEL['low'] += 1
                    if '天量' in _vgt:
                        _VREG_FUNNEL['high'] += 1
                    if '缩量上涨' in _vgt:
                        _VREG_FUNNEL['shrinkup'] += 1
"""
se = se.replace(old_calc, new_calc)

# --- 8. 调用与计数 -----------------------------------------------------
old_tip = ("        _ctrl_tip = _ctrl_note(_ctrl, _stage, _pos, _stack_sc, _redfat_sc, _c4_n,\n"
           "                               _c6_n, _probe_ok, _distp_type, _markup_type)\n")
assert se.count(old_tip) == 1, '_ctrl_note 调用 锚点不唯一'
se = se.replace(old_tip,
                "        _ctrl_tip = _ctrl_note(_ctrl, _stage, _pos, _stack_sc, _redfat_sc, _c4_n,\n"
                "                               _c6_n, _probe_ok, _distp_type, _markup_type,\n"
                "                               _brk_type, _vreg_tags)\n")

old_cnt = ("        if _markup_ok and _MARKUP_NOTE_MODE != 'off':\n"
           "            _MARKUP_FUNNEL['note'] += 1\n")
assert se.count(old_cnt) == 1, 'markup note 计数 锚点不唯一'
se = se.replace(old_cnt, old_cnt +
                "        if _BRK_NOTE_MODE != 'off' and _brk_type:\n"
                "            _BRK_FUNNEL['note'] += 1\n"
                "        if _VREG_NOTE_MODE != 'off' and _vreg_tags:\n"
                "            _VREG_FUNNEL['note'] += 1\n")

# --- 9. rec 字段 -------------------------------------------------------
old_rec = "                'markup_score': _markup_sc,\n"
assert se.count(old_rec) == 1, 'rec markup_score 锚点不唯一'
se = se.replace(old_rec, old_rec +
                "                'brk_ok': 1 if _brk_ok else 0,\n"
                "                'brk_type': _brk_type,\n"
                "                'brk_score': _brk_sc,\n"
                "                'vreg_tags': _vreg_tags,\n"
                "                'vreg_pct': _vreg_pct,\n")

# --- 10. scan_all 清零 + 打印 -----------------------------------------
old_rst = ("        for _k in _MARKUP_FUNNEL:\n"
           "            _MARKUP_FUNNEL[_k] = 0\n")
assert se.count(old_rst) == 1, 'MARKUP_FUNNEL 清零 锚点不唯一'
se = se.replace(old_rst, old_rst +
                "        for _k in _BRK_FUNNEL:\n"
                "            _BRK_FUNNEL[_k] = 0\n"
                "        for _k in _VREG_FUNNEL:\n"
                "            _VREG_FUNNEL[_k] = 0\n")

old_pr = ("            print('[拉升观察] K线不足60根跳过 %d 只 ｜ 位置超限跳过(pos>=%.2f) %d 只 ｜ "
          "命中并追加观察文案 %d 只'\n"
          "                  % (_mkf['insuf'], _MPMAX, _mkf['pos'], _mkf['note']), flush=True)\n")
assert se.count(old_pr) == 1, '拉升打印 锚点不唯一'
new_pr = old_pr + """            _bkf = _BRK_FUNNEL
            from strategy.base import BRK_POS_MAX as _BPMAX
            print('[破位收复] 可算 %d 只 ｜ 洗盘收复 %d ｜ 破位未收 %d ｜ 文案开关 _BRK_NOTE_MODE=%s'
                  % (_bkf['ok'], _bkf['wash'], _bkf['dist'], _BRK_NOTE_MODE), flush=True)
            print('[破位收复] K线不足60根跳过 %d 只 ｜ 位置超限跳过(pos>=%.2f) %d 只 ｜ '
                  '无破位日 %d 只 ｜ 命中并追加观察文案 %d 只'
                  % (_bkf['insuf'], _BPMAX, _bkf['pos'], _bkf['nobreak'],
                     _bkf['note']), flush=True)
            _vgf = _VREG_FUNNEL
            print('[量能分位] 可算 %d 只 ｜ 地量 %d ｜ 天量 %d ｜ 缩量上涨 %d ｜ 文案开关 _VREG_NOTE_MODE=%s'
                  % (_vgf['ok'], _vgf['low'], _vgf['high'], _vgf['shrinkup'],
                     _VREG_NOTE_MODE), flush=True)
            print('[量能分位] K线不足60根跳过 %d 只 ｜ 命中并追加观察文案 %d 只'
                  % (_vgf['insuf'], _vgf['note']), flush=True)
"""
se = se.replace(old_pr, new_pr)

shutil.copy2(PE, PE + '.bak_before_brkvr_engine')
io.open(PE, 'w', encoding='utf-8', newline='').write(se)
_chk2 = io.open(PE, encoding='utf-8', newline='').read()
print('engine.py：%d -> %d 行 ｜ 裸CRLF %d ｜ 新字段 %s ｜ 占位符 %d'
      % (n0, _chk2.count('\n'), _chk2.count('\r\n'),
         all(k in _chk2 for k in ['brk_ok', 'vreg_tags', '_BRK_FUNNEL', '_VREG_FUNNEL']),
         _chk2.count(','.join(['?'] * 64))))
