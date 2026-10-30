# -*- coding: utf-8 -*-
"""
验证 MA20 过滤真的生效（断言修正版）。

设计口径（复述一遍，避免再次误解）：
    现价 >= MA20 -> 不变
    现价 <  MA20 且 原判为「建仓触发」 -> 降级为「观察」+ trigger_type='MA20下方·筑底观察'
    现价 <  MA20 但原判为「等待确认」   -> 保持不变（等待确认本来就不能买）
因此正确断言是：
    A. 凡 trigger_type == 'MA20下方·筑底观察' -> 级别必须是「观察」且 现价 < MA20
    B. 凡级别是「观察」 -> trigger_type 必须是 'MA20下方·筑底观察'
    C. 凡级别是「建仓触发」 -> 现价必须 >= MA20   （这是本次补丁的核心效果）
写暂存表，不污染主表。
"""
import sqlite3
import sys
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')

import services.band_pattern_engine as E          # noqa: E402

MARK = 'MA20下方·筑底观察'
SAMPLE = 500

print('=' * 78)
print('① 主表现状（不动它）')
print('=' * 78)
con = sqlite3.connect(E.DB_PATH)
try:
    n = con.execute('SELECT COUNT(*) FROM pattern_record').fetchone()[0]
    print('  pattern_record 共 %d 条' % n)
    for lv, c in con.execute('SELECT signal_level, COUNT(*) FROM pattern_record'
                             ' GROUP BY signal_level').fetchall():
        print('    %-8s %d 条' % (lv, c))
finally:
    con.close()

print()
print('=' * 78)
print('② 样本扫描 %d 只（写暂存表）' % SAMPLE)
print('=' * 78)
E._init_db(E._STAGE_TABLE)
E._WRITE_TABLE = E._STAGE_TABLE

from utils.stock_name_manager import get_all_stock_names   # noqa: E402
raw = get_all_stock_names()
c2n = {}
for _nm, _cd in raw.items():
    c2n.setdefault(_cd, _nm)
items = list(c2n.items())[:SAMPLE]
print('  样本 %d 只 / 全市场 %d 只' % (len(items), len(c2n)))

for k in E._M1_FUNNEL:
    E._M1_FUNNEL[k] = 0
for k in E._M4_FUNNEL:
    E._M4_FUNNEL[k] = 0

eng = E.BandPatternEngine()
try:
    E._build_theme_context()
except Exception as e:
    print('  题材截面异常(忽略): %s' % e)

recs = []
import contextlib                                        # noqa: E402
import io as _io                                         # noqa: E402
_buf = _io.StringIO()
with contextlib.redirect_stdout(_buf):
    for code, name in items:
        try:
            recs += eng.scan_stock(code, name)
        except Exception:
            pass
print('  产出记录 %d 条（扫描噪声已静音）' % len(recs))
print('  级别分布: %s' % dict(Counter(r['signal_level'] for r in recs)))
print('  模式分布: %s' % dict(Counter(r['pattern_name'] for r in recs)))

print()
print('=' * 78)
print('③ 独立交叉核对（自己重算现价 与 MA20，不信引擎自报）')
print('=' * 78)
errs = []
n_below = n_trig = n_watch = 0
for r in recs:
    ma20 = r.get('ma20') or 0
    px = r.get('push_price') or 0
    lv = r['signal_level']
    tt = r.get('trigger_type') or ''
    if ma20 <= 0 or px <= 0:
        continue
    below = px < ma20
    if below:
        n_below += 1
    if tt == MARK:
        n_watch += 1
        if lv != E.LVL_WATCH or not below:
            errs.append('A 失败: %s %s tt=%s lv=%s px=%.2f ma20=%.2f'
                        % (r['code'], r['name'], tt, lv, px, ma20))
    if lv == E.LVL_WATCH and tt != MARK:
        errs.append('B 失败: %s %s 级别=观察 但 tt=%s' % (r['code'], r['name'], tt))
    if lv == E.LVL_TRIGGER:
        n_trig += 1
        if below:
            errs.append('C 失败: %s %s 建仓触发 但现价%.2f < MA20 %.2f'
                        % (r['code'], r['name'], px, ma20))

print('  现价 < MA20 的记录 : %d 条（其中被降级为观察: %d 条）' % (n_below, n_watch))
print('  建仓触发            : %d 条' % n_trig)
print()
print('  断言 A  降级标记 <=> 观察级 + 现价<MA20 ... %s'
      % ('通过 ✓' if not [x for x in errs if x.startswith('A')] else '失败 ✗'))
print('  断言 B  观察级 <=> 必有降级标记 ........... %s'
      % ('通过 ✓' if not [x for x in errs if x.startswith('B')] else '失败 ✗'))
print('  断言 C  建仓触发 => 现价 >= MA20 .......... %s'
      % ('通过 ✓' if not [x for x in errs if x.startswith('C')] else '失败 ✗'))
for e in errs:
    print('    %s' % e)

print()
print('=' * 78)
print('④ 引擎漏斗自报')
print('=' * 78)
f1, f4 = E._M1_FUNNEL, E._M4_FUNNEL
print('  模式一（激进）  s_ok=%d d_ok=%d struct=%d trigger=%d theme=%d '
      'entry_far=%d ma20_below=%d'
      % (f1['s_ok'], f1['d_ok'], f1['struct'], f1['trigger'],
         f1['theme'], f1['entry_far'], f1['ma20_below']))
print('  模式三（横盘周K）wk=%d struct=%d trigger=%d theme=%d entry_far=%d '
      'ma20_below=%d invalid=%d'
      % (f4['wk'], f4['struct'], f4['trigger'], f4['theme'],
         f4['entry_far'], f4['ma20_below'], f4['invalid']))
print('  漏斗 trigger 合计 = %d，应等于「建仓触发」记录数 %d  -> %s'
      % (f1['trigger'] + f4['trigger'], n_trig,
         '一致 ✓' if f1['trigger'] + f4['trigger'] == n_trig else '不一致 ✗'))
print('  漏斗 ma20_below 合计 = %d，应等于被降级条数 %d  -> %s'
      % (f1['ma20_below'] + f4['ma20_below'], n_watch,
         '一致 ✓' if f1['ma20_below'] + f4['ma20_below'] == n_watch else '不一致 ✗'))

print()
print('=' * 78)
print('⑤ 真实例子')
print('=' * 78)
for r in recs:
    if r.get('trigger_type') == MARK:
        print('  [降级] %s %s  现价 %.2f  MA20 %.2f  差 %.2f%%  %s'
              % (r['code'], r['name'], r['push_price'], r['ma20'],
                 (r['push_price'] - r['ma20']) / r['ma20'] * 100, r['pattern_name']))
for r in recs:
    if r['signal_level'] == E.LVL_TRIGGER:
        print('  [触发] %s %s  现价 %.2f  MA20 %.2f  差 %+.2f%%  %s'
              % (r['code'], r['name'], r['push_price'], r['ma20'],
                 (r['push_price'] - r['ma20']) / r['ma20'] * 100,
                 r['trigger_type']))

con = sqlite3.connect(E.DB_PATH)
try:
    con.execute('DELETE FROM %s' % E._STAGE_TABLE)
    con.commit()
finally:
    con.close()
print()
print('暂存表已清空，主表未改动 ✓')
print('结论: %s' % ('MA20 过滤已真实生效 ✓' if not errs else '仍有 %d 处 ✗' % len(errs)))
sys.exit(1 if errs else 0)
