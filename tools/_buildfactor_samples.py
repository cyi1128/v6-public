# -*- coding: utf-8 -*-
"""V20 建仓因子：抽样人工核对（步骤四）

从库内 230 条里抽高分股，把因子的原始分量摊开，供人工判断合理性：
  底部堆量：近10日均量 / 前20日均量(不重叠) = ratio；cont = 近10日量 > 基准均量的天数占比；
            pos120 = 近120日位置；score
  红肥绿瘦：上涨日均量 / 下跌日均量 = ratio；up/dn 天数；score
"""
import io
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
DB = os.path.join(ROOT, 'data', 'cache', 'band_pattern.db')
OUT = os.path.join(ROOT, 'tools', 'buildfactor_samples.txt')
_fh = io.open(OUT, 'w', encoding='utf-8')


def P(*a):
    s = ' '.join(str(x) for x in a)
    print(s)
    _fh.write(s + '\n')


import services.band_pattern_engine as E
from services.kline_cache_service import get_latest_kline
from strategy.base import TechnicalIndicators as TI

_ti = TI()
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
rows = con.execute(
    'SELECT code, name, pattern_id, base_date, stack_vol_score, red_fat_score,'
    ' control_score, stage_guess, note FROM pattern_record ORDER BY rowid').fetchall()
con.close()

cache = {}


def df_of(code):
    if code not in cache:
        try:
            cache[code] = E._bars_to_df(get_latest_kline(code, count=120))
        except Exception:
            cache[code] = None
    return cache[code]


recs = []
for r in rows:
    d = df_of(r['code'])
    if d is None:
        continue
    rs = _ti.bottom_volume_stack(d)
    rr = _ti.red_fat_green_thin(d)
    recs.append({
        'code': r['code'], 'name': (r['name'] or '').strip(), 'pid': r['pattern_id'],
        'base': r['base_date'], 'nv': int(len(d)),
        'ss': rs['score'], 'sr': rs['ratio'], 'sc': rs['cont'], 'sp': rs['pos120'], 'sok': rs['ok'],
        'fs': rr['score'], 'fr': rr['ratio'], 'fu': rr['up_days'], 'fd': rr['down_days'], 'fok': rr['ok'],
        'ctrl': r['control_score'], 'stage': r['stage_guess'], 'note': (r['note'] or ''),
    })

P('=' * 118)
P('V20 建仓因子 · 抽样人工核对   （库内 %d 条，能取到K线 %d 条）' % (len(rows), len(recs)))
P('=' * 118)

P('\n■ 底部堆量 TOP 12（score 高 → 近10日量相对前20日放大、且位置低、放量持续）')
P('  %-8s %-10s %5s %6s %7s %6s %6s %6s %6s  %s'
  % ('代码', '名称', 'K线', 'stack分', '量比', '连续', 'pos120', '控盘', '阶段', '是否满足'))
for x in sorted(recs, key=lambda z: -z['ss'])[:12]:
    P('  %-8s %-10s %5d %6.1f %7.2f %6.2f %6.3f %6.1f %6s  %s'
      % (x['code'], x['name'], x['nv'], x['ss'], x['sr'], x['sc'], x['sp'],
         x['ctrl'], x['stage'], '★满足' if x['sok'] else '—'))

P('\n■ 红肥绿瘦 TOP 12（score 高 → 上涨日均量 / 下跌日均量 明显 >1）')
P('  %-8s %-10s %5s %6s %7s %5s %5s %6s %6s  %s'
  % ('代码', '名称', 'K线', 'red分', '量比', '涨日', '跌日', '控盘', '阶段', '是否满足'))
for x in sorted(recs, key=lambda z: -z['fs'])[:12]:
    P('  %-8s %-10s %5d %6.1f %7.2f %5d %5d %6.1f %6s  %s'
      % (x['code'], x['name'], x['nv'], x['fs'], x['fr'], x['fu'], x['fd'],
         x['ctrl'], x['stage'], '★满足' if x['fok'] else '—'))

P('\n■ 两个因子同时满足（最接近「底部堆量 + 红肥绿瘦」形态，共 %d 条，列前 12）'
  % len([x for x in recs if x['sok'] and x['fok']]))
P('  %-8s %-10s %7s %6s %7s %7s %6s %6s'
  % ('代码', '名称', '堆量比', '连续', 'pos120', '红肥比', '控盘', '阶段'))
both = [x for x in recs if x['sok'] and x['fok']]
for x in sorted(both, key=lambda z: -(z['ss'] + z['fs']))[:12]:
    P('  %-8s %-10s %7.2f %6.2f %7.3f %7.2f %6.1f %6s'
      % (x['code'], x['name'], x['sr'], x['sc'], x['sp'], x['fr'], x['ctrl'], x['stage']))

P('\n■ 低分对照（两个因子都靠后 10 条，供反向核对）')
P('  %-8s %-10s %7s %6s %7s %7s %6s'
  % ('代码', '名称', '堆量比', '堆量分', '红肥比', '红肥分', '控盘'))
for x in sorted(recs, key=lambda z: z['ss'] + z['fs'])[:10]:
    P('  %-8s %-10s %7.2f %6.1f %7.2f %6.1f %6.1f'
      % (x['code'], x['name'], x['sr'], x['ss'], x['fr'], x['fs'], x['ctrl']))

P('\n■ 库内 note 实际带提示的条目（C1/C3 回归人工核对）')
hit = [x for x in recs if x['note'].strip()]
P('  带 note 的条目: %d 条' % len(hit))
for x in hit[:15]:
    P('  %-8s %-10s ctrl=%.1f %-11s %s' % (x['code'], x['name'], x['ctrl'], x['stage'], x['note'][:70]))

_fh.close()
print('\n已写:', OUT)
