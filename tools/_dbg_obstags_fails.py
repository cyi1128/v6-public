# -*- coding: utf-8 -*-
"""诊断上一轮验证里 3 个 FAIL：是真 bug 还是验证脚本自身的口径错误。"""
import os
import sys
import io
import random

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, r'D:\QuantMonitorV6')
os.chdir(r'D:\QuantMonitorV6')
P = lambda s: print(s, flush=True)

from services.control_profile import obs_tag_pairs, obs_stages, STAGE_PICK
import services.control_screen_service as SS
from services.kline_cache_service import get_latest_kline
import duckdb

_con = duckdb.connect(r'data\cache\kline_cache.duckdb', read_only=True)
_codes = [r[0] for r in _con.execute(
    "SELECT code FROM (SELECT code, COUNT(*) n FROM kline_cache "
    "WHERE code LIKE '60%' OR code LIKE '00%' OR code LIKE '30%' GROUP BY code) t "
    "WHERE n >= 120").fetchall()]
_con.close()
random.seed(20261011)
_sample = random.sample(_codes, 120)
rows = []
for c in _sample:
    b = get_latest_kline(c, 120)
    if not b:
        continue
    r = SS.compute_stock(c, b, name=c)
    if r:
        rows.append(r)

P('[A] stages 与重算不一致的样本：')
_bad = 0
for r in rows:
    ps = obs_tag_pairs(stack_ok=r['stack_ok'], redfat_ok=r['redfat_ok'],
                       probe_ok=r['probe_ok'], c4_ok=r['c4_ok'], c6_ok=r['c6_ok'],
                       brk_type=r['brk_type'], vreg_tags=r['vreg_tags'],
                       dist_type=r['dist_type'], markup_type=r['markup_type'])
    st = obs_stages(ps)
    if set(st) != set(r['stages']):
        _bad += 1
        if _bad <= 5:
            P('  %s  记录stages=%s / 重算=%s' % (r['code'], r['stages'], st))
            P('     observe=%s obs_pairs=%s' % (r['observe'], r['obs_pairs']))
            P('     字段: stack_ok=%s redfat_ok=%s probe_ok=%s c4_ok=%s c6_ok=%s brk=%r vreg=%r dist=%r mk=%r'
              % (r['stack_ok'], r['redfat_ok'], r['probe_ok'], r['c4_ok'], r['c6_ok'],
                 r['brk_type'], r['vreg_tags'], r['dist_type'], r['markup_type']))
P('  不一致总数 = %d / %d' % (_bad, len(rows)))

P('')
P('[B] 阶段筛选口径：把「全部」也算进手工口径的差别')
for s in STAGE_PICK:
    a = len(SS.apply_filters(rows, min_score=0.0, min_price=0.0, drop_st=False,
                             exclude_dist=False, stage=s))
    b = sum(1 for r in rows if s in r['stages'])
    P('  %-4s apply_filters=%3d  手工(含全部=0)=%3d  %s' % (s, a, b, 'OK' if (a == b or s == '全部') else 'X'))

P('')
P('[C] 日K建仓表 base_date / 控盘格的真实取值')
import sqlite3
from ui.battle_widgets import atr_t_widget as AW
import services.band_pattern_engine as engine
s0 = engine.query_signals()
vis = [x for x in s0 if x.get('signal_level') in ('建仓触发', '等待确认')]
t = AW.AtrTWidget()
t._daily_rows = [{
    'name': x.get('name') or x['code'], 'code': x['code'],
    'price': x.get('push_price') or 0, 'pct': x.get('push_pct') or 0,
    'pattern_name': AW._PATTERN_SHORT.get(x.get('pattern_name', ''), ''),
    'signal_level': x.get('signal_level', ''), 'base_date': x.get('base_date', ''),
    'theme': '', 'trigger_type': AW._TRIGGER_SHORT.get(x.get('trigger_type', ''), ''),
    'trigger_price': x.get('trigger_price') or 0, 'take_profit': x.get('take_profit') or 0,
    'env_score': x.get('env_score'), 'env_note': x.get('env_note') or '',
    'note': x.get('note') or '', 'control_score': x.get('control_score') or 0,
    'stage_guess': x.get('stage_guess') or '', 'ctrl_tag': x.get('ctrl_tag') or '',
    'probe_ok': bool(x.get('probe_ok')), 'c4_ok': bool(x.get('c4_ok')), 'c6_ok': bool(x.get('c6_ok')),
    'brk_type': x.get('brk_type') or '', 'vreg_tags': x.get('vreg_tags') or '',
    'dist_type': x.get('dist_pattern_type') or '',
    'markup_type': (x.get('markup_type') or '') if x.get('markup_ok') else '',
} for x in vis]
t._daily_render_table()
tb = t.daily_table
P('  行数=%d 列数=%d' % (tb.rowCount(), tb.columnCount()))
_nd = _nb = 0
for i in range(tb.rowCount()):
    it_bd = tb.item(i, AW.COL_D_BASE_DATE)
    it_ct = tb.item(i, AW.COL_D_CTRL)
    if it_ct is None:
        _nd += 1
    if it_bd is not None and '/' not in it_bd.text():
        _nb += 1
        if _nb <= 5:
            P('  base_date 样例: %r （代码 %s）' % (it_bd.text(), tb.item(i, AW.COL_D_CODE).text()))
P('  控盘格缺失 %d 行 / base_date 非斜杠格式 %d 行' % (_nd, _nb))
