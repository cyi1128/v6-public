# -*- coding: utf-8 -*-
"""给 band_pattern_engine.py 加「启动前震仓/试盘」因子。

锚点全部基于实际行号定位后的精确文本替换，逐条 assert 命中 1 次。
"""
import py_compile
import shutil
import sys

P = r'D:\QuantMonitorV6\services\band_pattern_engine.py'
BAK = P + '.bak_before_shake'

sys.stdout.reconfigure(encoding='utf-8')
shutil.copy2(P, BAK)
raw = open(P, 'rb').read()
assert raw.count(b'\r\n') == 0, '该文件应为纯 LF'
s = raw.decode('utf-8')

# ---------- 1) 新增 _shake_factors() 函数 ----------
A1 = """def _entry_shift(f, atr):
    \"\"\"共振修正量：强势上移（不必等太深），弱势下移（要更厚的安全垫）\"\"\"
    return (0.5 * f * atr) if f >= 0 else (0.8 * f * atr)
"""
N1 = A1 + '''

# ==================================================================
# 启动前「震仓 / 试盘」因子（V16，2026-10-09 加）
#   专业的启动链条是：吸筹 -> 震仓 -> 试盘 -> 主升。
#   横盘段已经由 struct_pos / up_rate / down_rate 覆盖了「吸筹」；
#   这里补的是紧贴启动周之前那 5 个交易日（震仓/试盘）的形态证据。
#
#   实测标定（2026-10-09，8 只可在本地K线回放的用户正样本：
#     国脉文化600640 振石股份601112 中视传媒600088 龙版传媒605577
#     德豪润达002005 内蒙新华603230 大亚圣象000910 华丽家族600503）：
#       shake_dip    回撤到箱体什么位置   中位 61.0%  范围  30.8% ~ 67.0%
#       shake_shadow 启动前最大下影线占比  中位 46.9%  范围  26.7% ~ 66.7%
#       shake_probe  最低价相对MA20       中位 -2.9%  范围  -6.2% ~ -0.04%
#                    -> 8/8 全部探到 MA20 下方（挖坑动作，无一例外）
#       shake_amp    振幅收敛比           中位 0.82   范围  0.58 ~ 1.19（6/8 <1）
#
#   被同批数据否掉、不要当因子的两条（写在这里防止以后再被加回来）：
#       A1 阳线均量 / 阴线均量：中位 1.04，范围 0.83~1.08
#          —— 启动前的吸筹期阳量与阴量基本持平，"阳线必须大于阴线"不成立
#       B1 启动前必须缩到地量（近5日均量 / 横盘均量）：中位 0.83，范围 0.51~1.37
#          —— 只是温和缩量（约 -17%），要求 <0.5 会大面积误杀
#
#   阈值按上述样本标定，所以这 8 只必然全过；它的作用不是"挑出正样本"，
#   而是把「形态上根本不是震仓/试盘」的股票从横盘周K候选里区分出来。
#   四项：回撤<=72% / 下影>=25% / 探针<=0 / 0<振幅收敛<=1.2
# ==================================================================
def _shake_factors(bars, si, hi, lo, st):
    """启动周前 5 个交易日的震仓/试盘因子。si=启动周首根下标，[st,si)=横盘窗口"""
    res = {'shake_dip': 0.0, 'shake_shadow': 0.0, 'shake_probe': 0.0,
           'shake_amp': 0.0, 'shake_ok': 0}
    if si < 8 or hi <= lo:
        return res
    seg = bars[max(st, si - 5):si]
    win = bars[st:si]
    if len(seg) < 3 or len(win) < 3:
        return res
    low5 = min(b['low'] for b in seg)
    res['shake_dip'] = round((hi - low5) / (hi - lo) * 100, 1)
    hl = [b for b in seg if b['high'] > b['low']]
    if hl:
        res['shake_shadow'] = round(max(
            (min(b['open'], b['close']) - b['low']) / (b['high'] - b['low']) * 100
            for b in hl), 1)
    ma20 = _ma([b['close'] for b in bars[:si]], 20)
    if ma20:
        res['shake_probe'] = round((low5 - ma20) / ma20 * 100, 2)
    a5 = sum((b['high'] - b['low']) / b['close'] for b in seg) / len(seg)
    aw = sum((b['high'] - b['low']) / b['close'] for b in win) / len(win)
    if aw > 0:
        res['shake_amp'] = round(a5 / aw, 2)
    ok = 0
    ok += 1 if res['shake_dip'] <= 72.0 else 0
    ok += 1 if res['shake_shadow'] >= 25.0 else 0
    ok += 1 if res['shake_probe'] <= 0.0 else 0
    ok += 1 if 0 < res['shake_amp'] <= 1.2 else 0
    res['shake_ok'] = ok
    return res
'''
assert s.count(A1) == 1, 'A1 锚点命中 %d 次' % s.count(A1)
s = s.replace(A1, N1, 1)

# ---------- 2) _ALL_COLS 补 5 个字段 ----------
A2 = "    ('struct_pos', 'REAL'), ('recent_vol3', 'INTEGER'),\n"
N2 = ("    ('struct_pos', 'REAL'), ('recent_vol3', 'INTEGER'),\n"
      "    ('shake_dip', 'REAL'), ('shake_shadow', 'REAL'), ('shake_probe', 'REAL'),\n"
      "    ('shake_amp', 'REAL'), ('shake_ok', 'INTEGER'),\n")
assert s.count(A2) == 1, 'A2 锚点命中 %d 次' % s.count(A2)
s = s.replace(A2, N2, 1)

# ---------- 3) _save_or_update 的 INSERT 同步扩展 ----------
A3 = ("             struct_pos, recent_vol3, take_profit, env_score, env_note,\n"
      "             created_at, updated_at)\n"
      "            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)\"\"\", (")
N3 = ("             struct_pos, recent_vol3, shake_dip, shake_shadow, shake_probe,\n"
      "             shake_amp, shake_ok, take_profit, env_score, env_note,\n"
      "             created_at, updated_at)\n"
      "            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)\"\"\", (")
assert s.count(A3) == 1, 'A3 锚点命中 %d 次' % s.count(A3)
s = s.replace(A3, N3, 1)

A4 = ("            rec.get('struct_pos',0), rec.get('recent_vol3',0),\n"
      "            rec.get('take_profit',0), rec.get('env_score',0), rec.get('env_note',''),")
N4 = ("            rec.get('struct_pos',0), rec.get('recent_vol3',0),\n"
      "            rec.get('shake_dip',0), rec.get('shake_shadow',0),\n"
      "            rec.get('shake_probe',0), rec.get('shake_amp',0), rec.get('shake_ok',0),\n"
      "            rec.get('take_profit',0), rec.get('env_score',0), rec.get('env_note',''),")
assert s.count(A4) == 1, 'A4 锚点命中 %d 次' % s.count(A4)
s = s.replace(A4, N4, 1)

# ---------- 4) detect_pattern_bottom：计算并写出 ----------
A5 = """    struct_pos = (round((closes[-1] - lo) / (hi - lo) * 100, 1) if hi > lo else 0)
    return {
        'pattern_id': PATTERN_BOTTOM,"""
N5 = """    struct_pos = (round((closes[-1] - lo) / (hi - lo) * 100, 1) if hi > lo else 0)
    # V16：启动前震仓/试盘因子（紧贴启动周之前的 5 个交易日）
    _sk = _shake_factors(bars, si, hi, lo, si - seg_n)
    return {
        'pattern_id': PATTERN_BOTTOM,"""
assert s.count(A5) == 1, 'A5 锚点命中 %d 次' % s.count(A5)
s = s.replace(A5, N5, 1)

A6 = """        'note': '横盘%d日(振幅%.0f%%) 上涨放量%d/%d(%.0f%%) 下跌缩量%d/%d(%.0f%%) '
                '本周%.2f倍放量阳·结构位%.0f%%近上沿%.2f' % (
                    seg_n, amp * 100, up_ok, up_days, up_rate,
                    dn_ok, dn_days, dn_rate, w_mult, _pos, hi),
    }"""
N6 = """        'shake_dip': _sk['shake_dip'], 'shake_shadow': _sk['shake_shadow'],
        'shake_probe': _sk['shake_probe'], 'shake_amp': _sk['shake_amp'],
        'shake_ok': _sk['shake_ok'],
        'note': '横盘%d日(振幅%.0f%%) 上涨放量%d/%d(%.0f%%) 下跌缩量%d/%d(%.0f%%) '
                '本周%.2f倍放量阳·结构位%.0f%%近上沿%.2f'
                '\\n震仓确认%d/4｜启动前回撤到箱体%.0f%%·最大下影%.0f%%·'
                '探针MA20%+.1f%%·振幅收敛%.2f' % (
                    seg_n, amp * 100, up_ok, up_days, up_rate,
                    dn_ok, dn_days, dn_rate, w_mult, _pos, hi,
                    _sk['shake_ok'], _sk['shake_dip'], _sk['shake_shadow'],
                    _sk['shake_probe'], _sk['shake_amp']),
    }"""
assert s.count(A6) == 1, 'A6 锚点命中 %d 次' % s.count(A6)
s = s.replace(A6, N6, 1)

# ---------- 5) docstring 补记新因子与两条反证 ----------
A7 = """    【被数据淘汰、不再参与筛选的指标】
        - MA5 走平向上：13 案例仅 6/13 通过。启动前必有一跌，MA5 天然被压，
          要求它向上等于「等涨起来才买」，会漏掉 7 只正样本。
        - 阳线均量 > 阴线均量：13 案例仅 10/13，最小 0.79。与横盘后期放量洗盘冲突。
      这两项仅作为参考值写入 up_rate/down_rate/struct_pos，不做门槛。
    \"\"\""""
N7 = """    【被数据淘汰、不再参与筛选的指标】
        - MA5 走平向上：13 案例仅 6/13 通过。启动前必有一跌，MA5 天然被压，
          要求它向上等于「等涨起来就买」，会漏掉 7 只正样本。
        - 阳线均量 > 阴线均量：13 案例仅 10/13，最小 0.79。与横盘后期放量洗盘冲突。
      这两项仅作为参考值写入 up_rate/down_rate/struct_pos，不做门槛。

    【V16 启动前震仓/试盘因子（2026-10-09 加）】
      见 _shake_factors()。紧贴启动周之前的 5 个交易日，写库并在 UI tooltip 显示：
        shake_dip / shake_shadow / shake_probe / shake_amp / shake_ok(0~4)
      阈值按 8 只正样本标定，只做展示与后续排序参考，不做硬门槛。
      同批数据再次否掉两条：阳线均量/阴线均量（中位 1.04）、
      启动前必须地量（中位 0.83）—— 都不要加回来。
    \"\"\""""
assert s.count(A7) == 1, 'A7 锚点命中 %d 次' % s.count(A7)
s = s.replace(A7, N7, 1)

open(P, 'wb').write(s.encode('utf-8'))
py_compile.compile(P, doraise=True)
print('OK  band_pattern_engine.py 打补丁完成')
print('  1. 新增 _shake_factors()')
print('  2. _ALL_COLS +5 字段（shake_dip/shadow/probe/amp/ok）')
print('  3. _save_or_update INSERT 37 -> 42 占位符')
print('  4. detect_pattern_bottom 计算并写出 + note 追加')
print('  5. docstring 补记')
print('  备份:', BAK)
