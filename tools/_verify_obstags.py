# -*- coding: utf-8 -*-
"""A+B 落地验证（可重跑，离屏 Qt）：五阶段「观察」标签到底有没有真的出现在界面上。

1) 源码级：4 个文件的列/宽度/表头/事件/筛选参数是否全部同步（少一处列就是空的）
2) 词表级：obs_tag_pairs / obs_stages 的判定与顺序
3) 真实数据：从 kline_cache 抽 120 只真股票跑 compute_stock，量出各标签命中数
4) DB 级：pattern_record 230 条按字段推标签，与 note 文案逐条互证
5) 离屏真实渲染：控盘选股页（阶段下拉 + 观察列）+ 日K建仓表（新增 观察 列）逐格读回

输出：tools\\obstags_verify.txt
"""
import io
import os
import sqlite3
import sys
import random

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, r'D:\QuantMonitorV6')
os.chdir(r'D:\QuantMonitorV6')

OUT = []
PASS = [0]
FAIL = [0]


def P(s=''):
    OUT.append(str(s))
    print(s, flush=True)


def ck(name, cond, extra=''):
    (PASS if cond else FAIL)[0] += 1
    P('  %s  %s %s' % ('PASS' if cond else 'FAIL', name, extra))


ROOT = r'D:\QuantMonitorV6'
def rd(p):
    return io.open(os.path.join(ROOT, p), encoding='utf-8', newline='').read()


P('=' * 96)
P('[1] 源码级：4 个文件的改动是否都在（少同步一处，那一列就是空的）')
P('=' * 96)

prof = rd(r'services\control_profile.py')
svc = rd(r'services\control_screen_service.py')
wid = rd(r'ui\battle_widgets\control_screen_widget.py')
atr = rd(r'ui\battle_widgets\atr_t_widget.py')

ck('词表在 control_profile 里定义（obs_tag_pairs/obs_stages/STAGE_PICK）',
   all(k in prof for k in ('def obs_tag_pairs(', 'def obs_stages(', 'STAGE_PICK = (',
                            'TAG_STAGE = {', 'OBS_TAG_LEVEL = {')))
ck('control_profile 仍是纯 CRLF',
   open(os.path.join(ROOT, r'services\control_profile.py'), 'rb').read().count(b'\r\n')
   == open(os.path.join(ROOT, r'services\control_profile.py'), 'rb').read().count(b'\n'))
ck('control_screen_service 仍是纯 LF 且接入了 A/B 两因子',
   ('detect_breakdown_recover' in svc and 'detect_volume_regime' in svc
    and open(os.path.join(ROOT, r'services\control_screen_service.py'), 'rb').read().count(b'\r\n') == 0))
ck('apply_filters 新增 stage 参数并真的生效',
   'obs=OBS_ALL, stage=None' in svc and "stage not in stages_of(r)" in svc)
ck('compute_stock 把 brk/vreg 传给了 _ctrl_note',
   "brk.get('type'), vreg.get('tags'))" in svc)
_obs_miss = [k for k in ('stack_ok', 'redfat_ok', 'brk_type', 'vreg_tags', 'vreg_pct', 'obs_pairs', 'stages')
             if "'%s'" % k not in svc]
ck('rec 里 7 个新字段都在（缺哪个，哪类标签就永远不出现）', not _obs_miss, str(_obs_miss))

ck('控盘选股页有「阶段」下拉且透传给 apply_filters',
   '_cb_stage' in wid and 'stage=self._cb_stage.currentText()' in wid
   and 'SS.STAGE_OPTIONS' in wid)
ck('控盘选股页观察列配色改为 level 判（风险/拉升/试盘/中性）',
   'OBS_TAG_LEVEL' in wid and "if 'risk' in _lv" in wid)
ck('控盘选股页 tooltip 补了 A/B 因子与阶段',
   '破位/收复' in wid and '量能分位' in wid and '手法阶段' in wid)

ck('日K建仓表列数 12 -> 13（常量/表头/宽度/make_table 四处齐全）',
   'COL_D_CTRL, COL_D_OBS, COL_D_ENV, COL_D_BASE_DATE = range(13)' in atr
   and "'控盘', '观察', '环境分', '基准日']" in atr
   and 'DAILY_WIDTHS = [80, 70, 58, 72, 58, 58, 0, 92, 86, 74, 200, 52, 92]' in atr
   and 'make_table(13, HEADER_DAILY)' in atr)
ck('日K建仓表渲染真的写了新列（setItem(i, COL_D_OBS, ...)）',
   'self.daily_table.setItem(i, COL_D_OBS, _ob_item)' in atr)
ck('日K建仓表行数据带上了因子字段（含控盘 ctrl_tag）',
   all(k in atr for k in ("'probe_ok': bool(s.get('probe_ok'))", "'ctrl_tag': s.get('ctrl_tag') or ''",
                          "'vreg_tags': s.get('vreg_tags') or ''", "'brk_type': s.get('brk_type') or ''")))
ck('atr_t_widget 仍是纯 CRLF',
   open(os.path.join(ROOT, r'ui\battle_widgets\atr_t_widget.py'), 'rb').read().count(b'\r\n')
   == open(os.path.join(ROOT, r'ui\battle_widgets\atr_t_widget.py'), 'rb').read().count(b'\n'))

P('')
P('=' * 96)
P('[2] 词表级：标签判定与顺序')
P('=' * 96)
from services.control_profile import (obs_tag_pairs, obs_stages, obs_tag_text,
                                      obs_tag_color, STAGE_PICK, TAG_STAGE)
ck('建仓类（堆量/红肥绿瘦）', obs_tag_pairs(stack_ok=True, redfat_ok=True)
   == [('堆量', 'info'), ('红肥绿瘦', 'info')])
ck('试盘金色', obs_tag_pairs(probe_ok=True) == [('试盘', 'gold')])
ck('破位未收 -> 破位警示(risk)；洗盘收复 -> info',
   obs_tag_pairs(brk_type='破位未收') == [('破位警示', 'risk')]
   and obs_tag_pairs(brk_type='洗盘收复') == [('洗盘收复', 'info')])
ck('量能分位：地量/天量/缩量上涨 三标签拆分正确',
   obs_tag_pairs(vreg_tags='地量|天量|缩量上涨') == [('地量', 'info'), ('缩量上涨', 'warn'), ('天量', 'risk')])
ck('拉升带形态后缀且为 warn', obs_tag_pairs(markup_type='阶梯式上行') == [('拉升:阶梯式上行', 'warn')])
ck('顺序固定：建仓→试盘→洗盘→拉升→出货→C4/C6',
   [t for t, _lv in obs_tag_pairs(stack_ok=True, probe_ok=True, c4_ok=True, c6_ok=True,
                                  brk_type='破位未收', vreg_tags='地量|天量',
                                  dist_type='双顶雏形', markup_type='加速迹象')]
   == ['堆量', '试盘', 'C4', 'C6', '地量', '拉升:加速迹象', '破位警示', '天量', '出货形态'])
ck('阶段归属（多阶段可并存）',
   obs_stages(obs_tag_pairs(stack_ok=True, brk_type='破位未收', markup_type='加速迹象'))
   == ['建仓', '拉升', '出货'])
ck('STAGE_PICK 六项 / TAG_STAGE 覆盖 10 个标签',
   STAGE_PICK == ('全部', '建仓', '试盘', '洗盘', '拉升', '出货') and len(TAG_STAGE) == 10)
ck('颜色映射（risk 红 / warn 橙 / gold 金 / info 蓝）',
   (obs_tag_color('risk'), obs_tag_color('warn'), obs_tag_color('gold'), obs_tag_color('info'))
   == ('#c62828', '#ef6c00', '#b8860b', '#1565c0'))

P('')
P('=' * 96)
P('[3] 真实数据：从 kline_cache 抽 120 只真股票，跑 compute_stock，量各标签命中')
P('=' * 96)
import services.control_screen_service as SS
from services.kline_cache_service import get_latest_kline
import duckdb

_con = duckdb.connect(os.path.join(ROOT, r'data\cache\kline_cache.duckdb'), read_only=True)
_codes = [r[0] for r in _con.execute(
    "SELECT code FROM (SELECT code, COUNT(*) n FROM kline_cache "
    "WHERE code LIKE '60%' OR code LIKE '00%' OR code LIKE '30%' GROUP BY code) t "
    "WHERE n >= 120").fetchall()]
_con.close()
random.seed(20261011)
_sample = random.sample(_codes, min(120, len(_codes)))

rows = []
for c in _sample:
    try:
        b = get_latest_kline(c, 120)
    except Exception:
        b = None
    if not b:
        continue
    r = SS.compute_stock(c, b, name=c)
    if r:
        rows.append(r)
P('  样本可用 %d 只（候选池 %d 只）' % (len(rows), len(_codes)))

from collections import Counter
_c_tag = Counter()
_c_stage = Counter()
_any = 0
for r in rows:
    if r['observe']:
        _any += 1
    for t in r['observe']:
        _c_tag[t.split(':')[0]] += 1
    for s in r['stages']:
        _c_stage[s] += 1
P('  有 ≥1 个标签: %d/%d (%.0f%%)' % (_any, len(rows), 100.0 * _any / max(len(rows), 1)))
P('  标签命中数: %s' % dict(_c_tag.most_common()))
P('  阶段命中数: %s' % dict(_c_stage.most_common()))
ck('真实数据上确实出现了新标签（建仓/试盘/洗盘/拉升/出货 至少四类）',
   len([k for k in _c_tag if k in ('堆量', '红肥绿瘦', '试盘', '洗盘收复', '地量',
                                   '拉升', '缩量上涨', '破位警示', '天量', '出货形态')]) >= 4)
_mis = [r['code'] for r in rows
        if set(obs_stages(obs_tag_pairs(stack_ok=r['stack_ok'], redfat_ok=r['redfat_ok'],
                                        probe_ok=r['probe_ok'], c4_ok=r['c4_ok'], c6_ok=r['c6_ok'],
                                        brk_type=r['brk_type'], vreg_tags=r['vreg_tags'],
                                        dist_type=r['dist_type'], markup_type=r['markup_type'])))
        != set(r['stages'])]
ck('stages 与 observe 逐个自洽', not _mis, _mis[:5])
ck('阶段筛选计数与手工统计一致（「全部」不参与）',
   all(len(SS.apply_filters(rows, min_score=0.0, min_price=0.0, drop_st=False,
                            exclude_dist=False, stage=s))
       == sum(1 for r in rows if s in r['stages']) for s in STAGE_PICK if s != '全部'))
ck('obs_pairs 是 JSON 友好的 list（快照落盘不炸）',
   all(isinstance(p, list) and len(p) == 2 for r in rows for p in r['obs_pairs']))

P('')
P('=' * 96)
P('[4] DB 级：pattern_record 230 条，按字段推标签，并与 note 文案互证')
P('=' * 96)
con = sqlite3.connect(os.path.join(ROOT, r'data\cache\band_pattern.db'))
con.row_factory = sqlite3.Row
db = [dict(r) for r in con.execute(
    "SELECT code,name,signal_level,note,brk_type,vreg_tags,probe_ok,c4_ok,c6_ok,"
    "dist_pattern_type,markup_ok,markup_type,stage_guess,control_score FROM pattern_record")]
con.close()
_c2 = Counter()
_db_any = 0
_db_pairs = {}
for r in db:
    ps = obs_tag_pairs(probe_ok=bool(r['probe_ok']), c4_ok=bool(r['c4_ok']), c6_ok=bool(r['c6_ok']),
                       brk_type=r['brk_type'] or '', vreg_tags=r['vreg_tags'] or '',
                       dist_type=r['dist_pattern_type'] or '',
                       markup_type=(r['markup_type'] or '') if r['markup_ok'] else '')
    _db_pairs[r['code']] = ps
    if ps:
        _db_any += 1
    for t, _lv in ps:
        _c2[t.split(':')[0]] += 1
P('  230 条里有标签 %d 条' % _db_any)
P('  标签分布: %s' % dict(_c2.most_common()))
VIS = ('建仓触发', '等待确认')
_vis = [r for r in db if r['signal_level'] in VIS]
_vis_any = sum(1 for r in _vis if _db_pairs[r['code']])
P('  默认可见（建仓触发+等待确认）%d 条，其中带标签 %d 条' % (len(_vis), _vis_any))
ck('断位/量能字段与标签一致：brk_type=破位未收 ⟺ 有「破位警示」',
   all((('破位警示' in [t for t, _ in _db_pairs[r['code']]]) == (r['brk_type'] == '破位未收'))
       for r in db))
ck('note 里出现「破位警示」的行 ⟺ brk_type=破位未收（文案与字段不矛盾）',
   all((('破位警示' in (r['note'] or '')) == (r['brk_type'] == '破位未收')) for r in db))
ck('天量标签 ⟺ vreg_tags 含天量',
   all((('天量' in [t for t, _ in _db_pairs[r['code']]]) == ('天量' in (r['vreg_tags'] or '')))
       for r in db))
ck('默认可见行里带标签的 > 0（界面上真能看到东西）', _vis_any > 0, '%d 条' % _vis_any)

P('')
P('=' * 96)
P('[5] 离屏真实渲染：两个界面逐格读回')
P('=' * 96)
from PyQt6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])

# ---- 5.1 控盘选股页 ----
_ok_w = True
try:
    from ui.battle_widgets.control_screen_widget import ControlScreenWidget, PAGE_COL_N
    w = ControlScreenWidget()
    w._ck_extra.setChecked(False)          # 关掉联网补数
    w._all_rows = rows
    w._apply_and_render(fill=False)
    n_row = w.table.rowCount()
    P('  控盘选股页：喂入 %d 只，渲染 %d 行，列数=%d' % (len(rows), n_row, PAGE_COL_N))
    ck('控盘选股页列数仍是 13（没被改坏）', PAGE_COL_N == 13)
    ck('阶段下拉存在且选项与词表一致',
       [w._cb_stage.itemText(i) for i in range(w._cb_stage.count())] == list(STAGE_PICK))
    ck('渲染行数与筛选结果一致', n_row == len(w._rows))
    _cell_n = 0
    _cells = []
    for i in range(min(n_row, 40)):
        it = w.table.item(i, 10)          # C_OBS
        _t = it.text() if it else ''
        _cells.append(_t)
        if _t and _t != '—':
            _cell_n += 1
    P('  观察列前 40 行示例: %s' % ' ｜ '.join(_cells[:8]))
    ck('观察列真的显示出标签（非空、非全 —）', _cell_n > 0, '%d/40 行有标签' % _cell_n)
    # 阶段筛选联动（切阶段会自动松开「排除出货」，两条筛法互斥）
    _before = w.table.rowCount()
    w._cb_stage.setCurrentText('出货')
    _after = w.table.rowCount()
    _manual = sum(1 for r in rows
                  if '出货' in r['stages']
                  and float(r['score']) >= float(w._sp_score.value())
                  and (not w._ck_price.isChecked() or float(r['price']) >= 6.0)
                  and not (w._ck_st.isChecked()
                           and SS.is_st_name(r.get('name'))))
    P('  阶段=出货：%d 行（手工口径 %d，排除出货已自动松开=%s）'
      % (_after, _manual, not w._ck_dist.isChecked()))
    ck('阶段下拉真的改了表格行数（不是摆设）', _after <= _before and _after == _manual)
    ck('切到具体阶段时「排除出货」被自动松开（否则选出货必空表）',
       not w._ck_dist.isChecked())
    w._cb_stage.setCurrentText('建仓')
    _m2 = sum(1 for r in rows if '建仓' in r['stages']
              and float(r['score']) >= float(w._sp_score.value())
              and (not w._ck_price.isChecked() or float(r['price']) >= 6.0)
              and not (w._ck_st.isChecked() and SS.is_st_name(r.get('name'))))
    P('  阶段=建仓：%d 行（手工口径 %d）' % (w.table.rowCount(), _m2))
    ck('阶段=建仓 行数一致', w.table.rowCount() == _m2)
    w._cb_stage.setCurrentText('全部')
    ck('切回全部后行数恢复', w.table.rowCount() == _before)
except Exception as e:
    _ok_w = False
    ck('控盘选股页离屏渲染', False, '异常 %s: %s' % (type(e).__name__, e))

# ---- 5.2 日K建仓表 ----
try:
    from ui.battle_widgets import atr_t_widget as AW
    import services.band_pattern_engine as engine
    s0 = engine.query_signals()
    vis = [x for x in s0 if x.get('signal_level') in ('建仓触发', '等待确认')]
    t = AW.AtrTWidget()
    _PAT = AW._PATTERN_SHORT
    _TRG = AW._TRIGGER_SHORT
    from data.limit_up_reason_db import get_last_limit_up_reason
    drows = []
    for x in vis:
        c = x['code']
        try:
            th = (get_last_limit_up_reason(c) or ('',))[0] or ''
        except Exception:
            th = ''
        drows.append({
            'name': x.get('name') or c, 'code': c, 'price': x.get('push_price') or 0,
            'pct': x.get('push_pct') or 0, 'pattern_name': _PAT.get(x.get('pattern_name', ''), ''),
            'signal_level': x.get('signal_level', ''), 'base_date': x.get('base_date', ''),
            'theme': th, 'trigger_type': _TRG.get(x.get('trigger_type', ''), x.get('trigger_type', '')),
            'trigger_price': x.get('trigger_price') or 0, 'take_profit': x.get('take_profit') or 0,
            'env_score': x.get('env_score'), 'env_note': x.get('env_note') or '',
            'note': x.get('note') or '', 'control_score': x.get('control_score') or 0,
            'stage_guess': x.get('stage_guess') or '', 'ctrl_tag': x.get('ctrl_tag') or '',
            'probe_ok': bool(x.get('probe_ok')), 'c4_ok': bool(x.get('c4_ok')),
            'c6_ok': bool(x.get('c6_ok')), 'brk_type': x.get('brk_type') or '',
            'vreg_tags': x.get('vreg_tags') or '', 'dist_type': x.get('dist_pattern_type') or '',
            'markup_type': (x.get('markup_type') or '') if x.get('markup_ok') else '',
        })
    t._daily_rows = drows
    t._daily_render_table()
    tb = t.daily_table
    P('  日K建仓表：喂入 %d 条，渲染 %d 行，列数=%d，表头=%s'
      % (len(drows), tb.rowCount(), tb.columnCount(), AW.HEADER_DAILY))
    ck('日K建仓表列数=13 且第 11 列表头为「观察」', tb.columnCount() == 13 and AW.HEADER_DAILY[10] == '观察')
    _n = 0
    _samples = []
    for i in range(tb.rowCount()):
        it = tb.item(i, AW.COL_D_OBS)
        _t = it.text() if it else '(无item)'
        _tip = it.toolTip() if it else ''
        if _t and _t != '—':
            _n += 1
            if len(_samples) < 6:
                _samples.append('%s %s -> %s' % (tb.item(i, AW.COL_D_CODE).text(), _t, _tip.split('\n')[0]))
    P('  观察列带标签 %d/%d 行' % (_n, tb.rowCount()))
    for s in _samples:
        P('    %s' % s)
    ck('观察列有内容（不是空列）', tb.rowCount() > 0 and _n > 0)
    # 其他列没被挤错位：控盘格都在、基准日仍是日期（库里是 YYYY-MM-DD）
    import re as _re
    _ct_ok = all(tb.item(i, AW.COL_D_CTRL) is not None
                 and (tb.item(i, AW.COL_D_CTRL).text() or '').strip() != ''
                 for i in range(tb.rowCount()))
    _bd_bad = [tb.item(i, AW.COL_D_BASE_DATE).text() for i in range(tb.rowCount())
               if tb.item(i, AW.COL_D_BASE_DATE) is not None
               and not _re.match(r'^\d{4}-\d{2}-\d{2}$',
                                 (tb.item(i, AW.COL_D_BASE_DATE).text() or '').strip())]
    ck('列没错位：控盘格都有内容', _ct_ok)
    ck('列没错位：基准日仍是 YYYY-MM-DD', not _bd_bad, str(_bd_bad[:3]))
    ck('观察列宽度已设（200）', tb.columnWidth(AW.COL_D_OBS) == 200)
except Exception as e:
    import traceback
    traceback.print_exc()
    ck('日K建仓表离屏渲染', False, '异常 %s: %s' % (type(e).__name__, e))

P('')
P('=' * 96)
P('汇总：PASS %d / FAIL %d' % (PASS[0], FAIL[0]))
P('=' * 96)
io.open(os.path.join(ROOT, r'tools\obstags_verify.txt'), 'w', encoding='utf-8').write('\n'.join(OUT))
