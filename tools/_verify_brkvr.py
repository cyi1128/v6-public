# -*- coding: utf-8 -*-
"""A/B/C 落地后的独立验证（可重跑）。

原则：验证脚本**不调用被验证的函数**，而是按规则文档重新实现一遍，再与
DB 里实际写入的值逐只比对 —— 这样字段错位、判据写错、写库漏列都能被抓到。

[A] 源码结构：常量值 / @staticmethod / _ALL_COLS 与 INSERT 列清单与占位符三者一致
[B] DB 逐只独立重算：brk_type / brk_score / vreg_tags / vreg_pct 四项比对
[C] 文案与字段一致性：note 里的新文案只能由对应字段触发（洗盘收复不得出破位警示）
[D] C 项：markup_type='缩量强势' 的记录必须 pos120<0.45（证明 ② 只在正期望区命中）

输出：tools\\brkvr_verify.txt
"""
import io
import os
import re
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import duckdb  # noqa: E402

OUT = r'D:\QuantMonitorV6\tools\brkvr_verify.txt'
_lines = []
PASS = FAIL = 0


def P(*a):
    s = ' '.join(str(x) for x in a)
    _lines.append(s)
    print(s, flush=True)


def ck(name, cond, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        P('  PASS  %s %s' % (name, extra))
    else:
        FAIL += 1
        P('  FAIL  %s %s' % (name, extra))


# ==================== [A] 源码结构 ====================
P('=' * 96)
P('[A] 源码结构')
P('=' * 96)
sb = io.open(os.path.join('strategy', 'base.py'), encoding='utf-8', newline='').read()
se = io.open(os.path.join('services', 'band_pattern_engine.py'), encoding='utf-8', newline='').read()
ck('base.py 纯 CRLF', sb.count('\n') == sb.count('\r\n'),
   'CRLF=%d 裸LF=%d' % (sb.count('\r\n'), sb.count('\n') - sb.count('\r\n')))
ck('engine.py 纯 LF', '\r\n' not in se)
ck('BRK_POS_LOW = 0.55', re.search(r'^BRK_POS_LOW = 0\.55', sb, re.M) is not None)
ck('MARKUP_POS_MAX = 0.45', re.search(r'^MARKUP_POS_MAX = 0\.45', sb, re.M) is not None)
ck('MARKUP_LOCK_POS_MIN = 0.00（C 项）',
   re.search(r'^MARKUP_LOCK_POS_MIN = 0\.00', sb, re.M) is not None)
for fn in ('detect_breakdown_recover', 'volume_percentile', 'detect_volume_regime'):
    ck('@staticmethod 在 %s 之前' % fn,
       ('@staticmethod' + '\r\n' + '    def %s(' % fn) in sb)
# docstring 里的单反斜杠会触发 SyntaxWarning；注释里的反斜杠无害，所以只查三引号区间
_doc_bad = []
for _m in re.finditer(r'"""[\s\S]*?"""', sb):
    for _ln in _m.group(0).split('\r\n'):
        if re.search(r'[^\\]\\[a-zA-Z]', _ln) and '\\\\' not in _ln:
            _doc_bad.append(_ln.strip()[:70])
ck('docstring 内无单反斜杠转义（\\m 告警源）', not _doc_bad, '可疑 %d 行' % len(_doc_bad))
for _x in _doc_bad[:4]:
    P('        %s' % _x)

# _ALL_COLS / INSERT 列清单 / 占位符 三者一致
cols = re.findall(r"\('([a-z_0-9]+)', '[A-Z ]+'\)", se.split('_ALL_COLS = [')[1].split(']')[0])
ins = se.split('INSERT OR REPLACE INTO {tbl}')[1].split('VALUES')[0]
ins_cols = [c.strip() for c in ins.split('(', 1)[1].split(')')[0].replace('\n', ' ').split(',')]
ins_cols = [c for c in ins_cols if c]
nph = re.search(r'VALUES \(((?:\?,)*\?)\)"""', se)
ck('_ALL_COLS 列数 == INSERT 列数 == 占位符数',
   len(cols) == len(ins_cols) == (nph.group(1).count('?') if nph else -1),
   '_ALL_COLS=%d INSERT=%d 占位符=%s' % (len(cols), len(ins_cols),
                                        nph.group(1).count('?') if nph else '?'))
# 列名在 INSERT 里是显式给出的，所以顺序不必等于 _ALL_COLS；真正必须对齐的是
# 「INSERT 列清单」与「取值元组」——错位就会像历史上那样整列写成别的字段的值。
_vals_seg = se.split('VALUES (', 1)[1].split('""", (', 1)[1].split('\n        ))')[0]
val_names = re.findall(r"rec\s*(?:\.get\s*\(\s*|\[\s*)'([a-z_0-9]+)'", _vals_seg)
ck('取值元组与 INSERT 列清单逐项同序同名（末列 updated_at 为字面量表达式）',
   val_names == ins_cols[:len(val_names)] and ins_cols[len(val_names):] == ['updated_at'],
   '元组 %d 项 / 列 %d 项' % (len(val_names), len(ins_cols)))
if val_names != ins_cols[:len(val_names)]:
    for _i, (_a, _b) in enumerate(zip(val_names, ins_cols)):
        if _a != _b:
            P('        首个错位 @%d：列=%s 取值=%s' % (_i, _b, _a))
            break
ck('新字段在取值元组里也按同序出现',
   val_names[val_names.index('markup_score') + 1:val_names.index('markup_score') + 6]
   == ['brk_ok', 'brk_type', 'brk_score', 'vreg_tags', 'vreg_pct'])
for c in ('brk_ok', 'brk_type', 'brk_score', 'vreg_tags', 'vreg_pct'):
    ck('新字段 %s 在 _ALL_COLS 与 INSERT 里都存在' % c, c in cols and c in ins_cols)

# ==================== 载入 DB 与K线 ====================
con = sqlite3.connect(os.path.join('data', 'cache', 'band_pattern.db'))
con.row_factory = sqlite3.Row
rows = [dict(r) for r in con.execute('SELECT * FROM pattern_record')]
cols_db = [r[1] for r in con.execute('PRAGMA table_info(pattern_record)')]
con.close()
P('')
P('DB：%d 条记录 ｜ %d 列 ｜ push_date 分布 %s'
  % (len(rows), len(cols_db), sorted({r['push_date'] for r in rows})[:4]))
ck('DB 列数 == _ALL_COLS 列数', len(cols_db) == len(cols), '%d vs %d' % (len(cols_db), len(cols)))
ck('5 个新字段全部落到库里',
   all(c in cols_db for c in ('brk_ok', 'brk_type', 'brk_score', 'vreg_tags', 'vreg_pct')))

dcon = duckdb.connect(os.path.join('data', 'cache', 'kline_cache.duckdb'), read_only=True)
codes = [r['code'] for r in rows]
if codes:
    q = ("SELECT code,date,open,high,low,close,volume FROM kline_cache WHERE code IN (%s) "
         "ORDER BY code,date" % ','.join("'%s'" % c for c in codes))
    kl = dcon.execute(q).fetchdf()
else:
    kl = pd.DataFrame()
dcon.close()
by_code = {c: g.to_dict('records') for c, g in kl.groupby('code')} if len(kl) else {}


# ---------- 独立实现（按规则重写，不用引擎函数） ----------
def brk_indep(bars):
    if len(bars) < 60:
        return None
    o = np.array([b['open'] for b in bars], float)
    h = np.array([b['high'] for b in bars], float)
    lw = np.array([b['low'] for b in bars], float)
    c = np.array([b['close'] for b in bars], float)
    v = np.array([b['volume'] for b in bars], float)
    n = len(c)
    c120 = c[-120:]
    pos = (c[-1] - c120.min()) / (c120.max() - c120.min() + 1e-8)
    if pos >= 0.55:
        return dict(type='', score=None, pos=pos, vr=None, reason='pos')
    i_brk, sup = -1, 0.0
    for i in range(n - 1, max(20, n - 12) - 1, -1):
        _s = float(lw[i - 20:i].min())
        if lw[i] < _s:
            i_brk, sup = i, _s
            break
    if i_brk < 5:
        return dict(type='', score=None, pos=pos, vr=None, reason='nobreak')
    vr = float(v[i_brk] / (v[i_brk - 5:i_brk].mean() + 1e-9))
    rec_j, rec_vr = -1, 0.0
    for j in range(i_brk + 1, min(i_brk + 5, n - 1) + 1):
        if c[j] >= sup:
            rec_j = j
            rec_vr = float(v[j] / (v[j - 5:j].mean() + 1e-9)) if j >= 5 else 0.0
            break
    if vr <= 1.00 and rec_j >= 0 and rec_vr >= 1.20:
        sc = 70.0 + min(20.0, (1.00 - vr) * 40.0) + min(10.0, (rec_vr - 1.20) * 25.0)
        return dict(type='洗盘收复', score=round(min(sc, 100.0), 6), pos=pos, vr=vr, reason='')
    if vr >= 1.50 and rec_j < 0:
        sc = 70.0 + min(30.0, (vr - 1.50) * 20.0)
        return dict(type='破位未收', score=round(min(sc, 100.0), 6), pos=pos, vr=vr, reason='')
    half = 30.0 + (15.0 if vr <= 1.00 else 0.0) + (15.0 if rec_j >= 0 else 0.0)
    return dict(type='', score=round(min(60.0, half), 6), pos=pos, vr=vr, reason='')


def vreg_indep(bars):
    if len(bars) < 60:
        return None
    o = np.array([b['open'] for b in bars], float)
    c = np.array([b['close'] for b in bars], float)
    v = np.array([b['volume'] for b in bars], float)
    n = len(c)
    w = v[-60:]
    pct = float((w <= v[-1]).sum()) / 60.0 * 100.0 if w.max() > 0 else None
    tags = []
    if pct is not None:
        if pct <= 20.0:
            tags.append('地量')
        if pct >= 80.0:
            tags.append('天量')
    ws = n - 5
    if ws >= 5:
        base = float(v[ws - 5:ws].mean())
        yang = [i for i in range(ws, n) if c[i] > o[i]]
        yratio = len(yang) / 5.0
        gain = (c[-1] - c[ws - 1]) / (c[ws - 1] + 1e-9)
        yvr = float(np.mean([v[i] for i in yang]) / (base + 1e-9)) if yang else 0.0
        if yratio >= 0.60 and yvr <= 0.90 and gain >= 0.03:
            tags.append('缩量上涨')
    return dict(tags=tags, pct=pct)


P('')
P('=' * 96)
P('[B] DB 逐只独立重算比对（%d 条记录）' % len(rows))
P('=' * 96)
n_checked = n_date_mismatch = 0
bad = []
brk_cnt = {'洗盘收复': 0, '破位未收': 0, '': 0}
tg_cnt = {'地量': 0, '天量': 0, '缩量上涨': 0}
score_mismatch = 0
for r in rows:
    bars = by_code.get(r['code'])
    if not bars:
        continue
    if str(bars[-1]['date'])[:10] != str(r['push_date'])[:10]:
        n_date_mismatch += 1
        continue
    b = brk_indep(bars)
    g = vreg_indep(bars)
    if b is None or g is None:
        continue
    n_checked += 1
    brk_cnt[b['type']] += 1
    for t in g['tags']:
        tg_cnt[t] += 1
    if (r['brk_type'] or '') != b['type']:
        bad.append('%s brk_type DB=%r 独立=%r' % (r['code'], r['brk_type'], b['type']))
    if int(r['brk_ok'] or 0) != (1 if b['type'] else 0):
        bad.append('%s brk_ok DB=%s 独立=%s' % (r['code'], r['brk_ok'], b['type']))
    if b['score'] is not None:
        db_sc = float(r['brk_score'] or 0)
        if abs(db_sc - b['score']) > 0.02:
            score_mismatch += 1
            bad.append('%s brk_score DB=%.4f 独立=%.4f' % (r['code'], db_sc, b['score']))
    if (r['vreg_tags'] or '') != '|'.join(g['tags']):
        bad.append('%s vreg_tags DB=%r 独立=%r' % (r['code'], r['vreg_tags'], g['tags']))
    d_pct, i_pct = r['vreg_pct'], g['pct']
    if (d_pct is None) != (i_pct is None) or (d_pct is not None
                                             and abs(float(d_pct) - float(i_pct)) > 0.01):
        bad.append('%s vreg_pct DB=%s 独立=%s' % (r['code'], d_pct, i_pct))
    elif i_pct is not None:
        db_t = [x for x in str(r['vreg_tags'] or '').split('|') if x]
        if ('地量' in db_t) != (i_pct <= 20.0) or ('天量' in db_t) != (i_pct >= 80.0):
            bad.append('%s 分位与标签不符 pct=%.2f tags=%s' % (r['code'], i_pct, db_t))
ck('可比对记录数 > 0', n_checked > 0, 'n=%d（%d 条因缓存末日与 push_date 不一致跳过）'
   % (n_checked, n_date_mismatch))
ck('brk_type / brk_ok / vreg_tags / vreg_pct 与独立重算逐只一致',
   not bad, '不一致 %d 处' % len(bad))
ck('brk_score 与独立重算一致(±0.02)', score_mismatch == 0, '不一致 %d 处' % score_mismatch)
for x in bad[:8]:
    P('        差异：%s' % x)
P('  独立重算分布：brk %s ｜ 标签 %s' % (brk_cnt, tg_cnt))

P('')
P('=' * 96)
P('[C] 文案与字段一致性（note 里的新文案只能由对应字段触发）')
P('=' * 96)
n_brk_missing = n_high_missing = n_su_note = n_wash_warn = 0
n_brk_hit = n_high_hit = 0
errs = []
for r in rows:
    note = r['note'] or ''
    if '破位警示' in note and (r['brk_type'] or '') != '破位未收':
        errs.append('%s note 有破位警示但 brk_type=%r' % (r['code'], r['brk_type']))
    if (r['brk_type'] or '') == '破位未收':
        n_brk_hit += 1
        if '破位警示' not in note:
            n_brk_missing += 1
    if (r['brk_type'] or '') == '洗盘收复' and '破位警示' in note:
        n_wash_warn += 1
    if '天量警示' in note and '天量' not in str(r['vreg_tags'] or ''):
        errs.append('%s note 有天量警示但 vreg_tags=%r' % (r['code'], r['vreg_tags']))
    if '天量' in str(r['vreg_tags'] or ''):
        n_high_hit += 1
        if '天量警示' not in note:
            n_high_missing += 1
    if '缩量上涨·疑似控盘' in note and '缩量上涨' not in str(r['vreg_tags'] or ''):
        errs.append('%s note 有缩量上涨文案但 vreg_tags=%r' % (r['code'], r['vreg_tags']))
    if '缩量上涨' in str(r['vreg_tags'] or '') and '缩量上涨·疑似控盘' in note:
        n_su_note += 1
ck('文案与字段无矛盾', not errs, '矛盾 %d 处' % len(errs))
for x in errs[:6]:
    P('        问题：%s' % x)
ck('「洗盘收复」不出破位警示', n_wash_warn == 0, '%d 条' % n_wash_warn)
ck('「破位未收」都出了破位警示', n_brk_missing == 0, '命中 %d 条' % n_brk_hit)
ck('「天量」都出了天量警示', n_high_missing == 0, '命中 %d 条' % n_high_hit)
P('  实际出文案：破位警示 %d ｜ 天量警示 %d ｜ 缩量上涨 %d（缩量上涨只在 pos<0.45 出）'
  % (n_brk_hit, n_high_hit, n_su_note))

P('')
P('=' * 96)
P('[D] C 项：markup 形态② 只在 pos<0.45 命中')
P('=' * 96)
m2n = m2bad = 0
for r in rows:
    if (r['markup_type'] or '') == '缩量强势':
        m2n += 1
        bars = by_code.get(r['code'])
        if bars:
            c = np.array([b['close'] for b in bars], float)[-120:]
            pos = (c[-1] - c.min()) / (c.max() - c.min() + 1e-8)
            if pos >= 0.45:
                m2bad += 1
                P('        %s ② 命中但 pos=%.3f >= 0.45' % (r['code'], pos))
ck('② 命中记录全部 pos<0.45（证明 C 修法正确）', m2bad == 0, '② 命中 %d 条' % m2n)
ck('② 命中数 > 0（修复前恒为 0）', m2n > 0, '② 命中 %d 条' % m2n)

P('')
P('=' * 96)
P('汇总：PASS %d / FAIL %d' % (PASS, FAIL))
P('=' * 96)
with open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(_lines) + '\n')
print('\n已写出 %s' % OUT)
sys.exit(1 if FAIL else 0)
