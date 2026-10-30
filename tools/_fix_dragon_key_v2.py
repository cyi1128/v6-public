# -*- coding: utf-8 -*-
"""
board_anomaly_engine.py 龙头判定改造（①②③⑤）

① 拆两个榜：情绪龙头（板高优先） + 次日接力参考（低位早封强封单）
② 封单额 → 封单强度 = 封单额 / 流通市值
③ 首封时间分档（秒级永不并列，导致后面的键全被架空）
⑤ 封板时段识别尾盘偷袭板（14:30 后）
"""
import os
import shutil
import sys
import py_compile

sys.stdout.reconfigure(encoding='utf-8')
P = r'D:\QuantMonitorV6\services\board_anomaly_engine.py'
raw = open(P, 'rb').read()
assert raw.count(b'\r\n') == 0, '本文件应为纯 LF'
s = raw.decode('utf-8')
print('原行数 %d / %d bytes' % (len(s.splitlines()), len(raw)))


def rep(old, new, desc):
    global s
    n = s.count(old)
    assert n == 1, '[%s] 锚点命中 %d 次，期望 1 次' % (desc, n)
    s = s.replace(old, new)
    print('  ✓ %s' % desc)


# ---------- ② ltsz 进 SELECT，否则强度算不出来 ----------
rep(
"""        # 龙头排序需要的字段（time/lbc/fund/amount/hs/zbc）。
        # 老库若没有这些列，降级为只读基础字段，不让整块挂掉。
        try:
            rows = c.execute(
                'SELECT code,name,industry,reason,time,lbc,fund,amount,hs,zbc,pct_chg '
                'FROM limit_up_reasons WHERE date=?', (d,)).fetchall()
        except Exception:
            rows = [(r[0], r[1], r[2], r[3], '', 0, 0.0, 0.0, 0.0, 0, None)
                    for r in c.execute('SELECT code,name,industry,reason '
                                       'FROM limit_up_reasons WHERE date=?', (d,))]
        recs = [{'code': str(r[0]), 'name': r[1] or '', 'industry': r[2] or '',
                 'reason': r[3] or '', 'time': (r[4] or '').strip(),
                 'lbc': int(r[5] or 0), 'fund': float(r[6] or 0.0),
                 'amount': float(r[7] or 0.0), 'hs': float(r[8] or 0.0),
                 'zbc': int(r[9] or 0), 'pct': r[10]}
                for r in rows]""",
"""        # 龙头排序需要的字段（time/lbc/fund/amount/hs/zbc/ltsz）。
        # ltsz 用于算封单强度 = 封单额 / 流通市值，绝对封单额不可比。
        # 老库若没有这些列，降级为只读基础字段，不让整块挂掉。
        try:
            rows = c.execute(
                'SELECT code,name,industry,reason,time,lbc,fund,amount,hs,zbc,'
                'ltsz,pct_chg '
                'FROM limit_up_reasons WHERE date=?', (d,)).fetchall()
        except Exception:
            rows = [(r[0], r[1], r[2], r[3], '', 0, 0.0, 0.0, 0.0, 0, 0.0, None)
                    for r in c.execute('SELECT code,name,industry,reason '
                                       'FROM limit_up_reasons WHERE date=?', (d,))]
        recs = [{'code': str(r[0]), 'name': r[1] or '', 'industry': r[2] or '',
                 'reason': r[3] or '', 'time': (r[4] or '').strip(),
                 'lbc': int(r[5] or 0), 'fund': float(r[6] or 0.0),
                 'amount': float(r[7] or 0.0), 'hs': float(r[8] or 0.0),
                 'zbc': int(r[9] or 0), 'ltsz': float(r[10] or 0.0),
                 'pct': r[11]}
                for r in rows]""",
    '② ltsz 进 SELECT + 降级分支 + 记录字典')

# ---------- ③⑤ 封板时段分档 ----------
rep(
"""def _dragon_key(rec, pct):
    \"\"\"龙头排序键（升序）：连板身位 > 首封时间 > 封单额 > 今日涨幅。

    口径对齐业内主流：身位（连板高度）权重最高，
    同身位再看谁先封板，再比封单额大小。
    没有首封时间的历史数据统一排到最后，再按涨幅兜底，
    避免老数据字段为空时挤掉当天真实龙头。
    \"\"\"
    t = (rec.get('time') or '').strip()
    return (0 if t else 1,
            -(rec.get('lbc') or 0),
            t or '99:99',
            -(rec.get('fund') or 0.0),
            -(pct.get(rec['code'], -999)))""",
"""# 封板时段分档（③ 首封时间不再精确到秒比较 / ⑤ 识别尾盘偷袭板）。
# 秒级首封时间几乎永不并列，会把后面的封单强度、炸板等键全部架空 ——
# 实测 2026-10-09 共 69 只涨停股，没有任何一对首封时间相同，
# 所以旧版第 4 键（封单额）和第 5 键（涨幅）一次都没被触发过。
# 改成先归「时段档」，同档内再用封单强度区分，后面的键才能真正起作用。
_SEAL_SLOTS = (
    ('09:25:00', 0, '竞价秒板'),    # 集合竞价直接成交，一字板/秒板，最强
    ('09:35:00', 1, '开盘封板'),
    ('10:00:00', 2, '早盘封板'),
    ('11:30:00', 3, '午前封板'),
    ('14:00:00', 4, '午后封板'),
    ('14:30:00', 5, '尾盘前封板'),
    ('15:00:00', 6, '尾盘偷袭'),    # 14:30 后拉板，次日溢价通常最差
)
_SEAL_SLOT_NONE = 7                 # 无首封时间（老数据）沉底


def _seal_slot(t):
    \"\"\"首封时间 -> 封板时段档位（0 最强）。返回 (档位, 档名)\"\"\"
    t = (t or '').strip()
    if not t:
        return _SEAL_SLOT_NONE, '--'
    for hi, idx, label in _SEAL_SLOTS:
        if t <= hi:
            return idx, label
    return len(_SEAL_SLOTS), '收盘封板'


def _seal_strength(rec):
    \"\"\"封单强度 = 封单额 / 流通市值（②）。

    绝对封单额不可比：同一天里 3.36 亿封在 14.6 亿流通盘上是 23.02%，
    1.12 亿封在 319.7 亿流通盘上只有 0.35%，相差 65 倍。
    拿绝对额排龙头，等于在比谁的盘子大。
    \"\"\"
    ltsz = rec.get('ltsz') or 0.0
    if ltsz <= 0:
        return 0.0
    return (rec.get('fund') or 0.0) / ltsz


def _dragon_key(rec, pct):
    \"\"\"① 情绪龙头排序键（升序）：连板身位 > 封板时段 > 封单强度 > 秒级时间。

    身位（连板高度）代表题材情绪高度，权重最高，用来判断题材能走多高；
    同身位比封板时段（越早越强，尾盘偷袭最弱）；
    同档再比封单强度；最后才用秒级首封时间兜底并列。
    它回答的是「这个题材谁最强」，不是「明天买谁」。
    \"\"\"
    t = (rec.get('time') or '').strip()
    return (0 if t else 1,
            -(rec.get('lbc') or 0),
            _seal_slot(t)[0],
            -_seal_strength(rec),
            t or '99:99')


# ① 次日接力参考：身位越低、封板越早、封单强度越大越好。
# 4 板以上不再作为接力标的（高位接力赔率差，那是情绪榜要看的）；
# 14:30 后的尾盘偷袭板也排除。
_ENTRY_MAX_LBC = 3
_ENTRY_MAX_SLOT = 5


def _entry_key(rec):
    \"\"\"次日接力排序键（升序）：身位低 > 封板早 > 封单强度大\"\"\"
    lbc = rec.get('lbc') or 1
    if lbc <= 1:
        pos = 0
    elif lbc == 2:
        pos = 1
    else:
        pos = 2
    return (pos, _seal_slot(rec.get('time'))[0], -_seal_strength(rec))


def _entry_of(mem, pct):
    \"\"\"从涨停股里挑 1 只次日接力参考，没有合格的返回 None\"\"\"
    cand = [m for m in mem
            if (m.get('lbc') or 1) <= _ENTRY_MAX_LBC
            and _seal_slot(m.get('time'))[0] <= _ENTRY_MAX_SLOT]
    if not cand:
        return None
    m = sorted(cand, key=_entry_key)[0]
    slot = _seal_slot(m.get('time'))
    return {'code': m['code'], 'name': m['name'],
            'pct': pct.get(m['code'], 0.0),
            'time': (m.get('time') or ''), 'slot_name': slot[1],
            'lbc': m.get('lbc') or 0, 'fund': m.get('fund') or 0.0,
            'strength': _seal_strength(m), 'zbc': m.get('zbc') or 0}""",
    '③⑤ 封板时段分档 + ①② 两个排序键')

# ---------- _dragons_of 带出时段/强度 ----------
rep(
"""    out = []
    for m in mem[:n]:
        out.append({'code': m['code'], 'name': m['name'],
                    'pct': pct.get(m['code'], 0.0),
                    'time': (m.get('time') or ''),
                    'lbc': m.get('lbc') or 0,
                    'fund': m.get('fund') or 0.0,
                    'zbc': m.get('zbc') or 0})
    return out""",
"""    out = []
    for m in mem[:n]:
        slot = _seal_slot(m.get('time'))
        out.append({'code': m['code'], 'name': m['name'],
                    'pct': pct.get(m['code'], 0.0),
                    'time': (m.get('time') or ''),
                    'slot': slot[0], 'slot_name': slot[1],
                    'lbc': m.get('lbc') or 0,
                    'fund': m.get('fund') or 0.0,
                    'strength': _seal_strength(m),
                    'zbc': m.get('zbc') or 0})
    return out""",
    '_dragons_of 带出 slot/slot_name/strength')

# ---------- 两处 row 加 entry ----------
rep(
"""            'dragons': _dragons_of(mem2, mpct),
            'members': [[m['code'], m['name'], mpct.get(m['code'], 0.0)]
                        for m in mem2],
            'all_avg_pct': None, 'all_count': None,
            'picks': _pick_candidates(pools['th'].get(kw) or set(),
                                      quotes, lu_codes, ma20),""",
"""            'dragons': _dragons_of(mem2, mpct),
            'entry': _entry_of(mem2, mpct),
            'members': [[m['code'], m['name'], mpct.get(m['code'], 0.0)]
                        for m in mem2],
            'all_avg_pct': None, 'all_count': None,
            'picks': _pick_candidates(pools['th'].get(kw) or set(),
                                      quotes, lu_codes, ma20),""",
    '题材行加 entry')

rep(
"""            'dragons': _dragons_of(mem2, mpct),
            'members': [[m['code'], m['name'], mpct.get(m['code'], 0.0)]
                        for m in mem2],
            'all_avg_pct': (sum(ag) / len(ag)) if ag else None,
            'all_count': len(ag) or None,""",
"""            'dragons': _dragons_of(mem2, mpct),
            'entry': _entry_of(mem2, mpct),
            'members': [[m['code'], m['name'], mpct.get(m['code'], 0.0)]
                        for m in mem2],
            'all_avg_pct': (sum(ag) / len(ag)) if ag else None,
            'all_count': len(ag) or None,""",
    '行业行加 entry')

shutil.copy2(P, P + '.bak_before_dragon_key_v2')
open(P, 'wb').write(s.encode('utf-8'))
print()
print('已写入 %s (%d bytes, %d 行)' % (P, os.path.getsize(P),
                                      len(s.splitlines())))
py_compile.compile(P, doraise=True)
print('py_compile OK')
