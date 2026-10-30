# -*- coding: utf-8 -*-
"""机构/量化执行标准：在真实数据上测通过率，先测再加，避免加完变成空表。"""
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')

from services.board_anomaly_engine import (                        # noqa: E402
    _load_realtime, _load_ma20, _load_pools, _load_limit_up,
    _PICK_MIN_PCT, _PICK_MAX_PCT, _PICK_MIN_VR, _PICK_MIN_PRICE)

ludate, recs = _load_limit_up()
q = _load_realtime()
ma20 = _load_ma20()
pools = _load_pools()
lu = pools.get('lu') or set()
print('涨停库=%s(%d只)  实时行情=%d只  MA20=%d只  涨停名单=%d只'
      % (ludate, len(recs), len(q), len(ma20), len(lu)))

# ---------- 复现当前「可介入」池 ----------
pool = []
for code, v in q.items():
    if code in lu:
        continue
    try:
        pct = float(v.get('pct_chg') or 0)
        px = float(v.get('price') or 0)
        vr = float(v.get('vol_ratio') or 0)
    except (TypeError, ValueError):
        continue
    if px <= 0 or pct < _PICK_MIN_PCT or pct >= _PICK_MAX_PCT:
        continue
    if px < _PICK_MIN_PRICE:
        continue
    if 'ST' in (v.get('name') or '').upper().replace(' ', ''):
        continue
    if vr and vr < _PICK_MIN_VR:
        continue
    m20 = ma20.get(code)
    if not m20 or px < m20:
        continue
    pool.append((code, v))
print('当前「可介入」候选池（全市场，未按板块归集）= %d 只' % len(pool))

print()
print('=' * 118)
print('一、机构/量化执行口径在候选池上的分布')
print('=' * 118)


def vwap_of(v):
    amt = float(v.get('amount') or 0)
    vol = float(v.get('volume') or 0)
    if amt <= 0 or vol <= 0:
        return 0.0
    return amt / (vol * 100.0)          # 元 / 股


rows = []
for code, v in pool:
    amt = float(v.get('amount') or 0) / 1e8          # 亿元
    cmv = float(v.get('circ_mv') or 0)               # 亿元
    hs = float(v.get('turnover') or 0)               # %
    amp = float(v.get('amplitude') or 0)             # %
    px = float(v.get('price') or 0)
    w = vwap_of(v)
    dev = ((px - w) / w * 100.0) if w > 0 else 999.0
    rows.append({'code': code, 'name': v.get('name'), 'pct': float(v.get('pct_chg') or 0),
                 'vr': float(v.get('vol_ratio') or 0), 'px': px, 'amt': amt,
                 'cmv': cmv, 'hs': hs, 'amp': amp, 'dev': dev})


def stat(key, cond, label):
    n = sum(1 for r in rows if cond(r))
    print('  %-34s 通过 %2d / %d  (%.0f%%)' % (label, n, len(rows), n * 100.0 / max(len(rows), 1)))
    return n


print('  —— 流动性门槛（机构算法单冲击成本约束）——')
stat('amt', lambda r: r['amt'] >= 1.0, '成交额 ≥ 1 亿')
stat('amt', lambda r: r['amt'] >= 2.0, '成交额 ≥ 2 亿')
stat('amt', lambda r: r['amt'] >= 3.0, '成交额 ≥ 3 亿')
print()
print('  —— 流通市值门槛（<20亿游资盘，>500亿拉不动）——')
stat('cmv', lambda r: 20 <= r['cmv'] <= 500, '流通市值 20~500 亿')
stat('cmv', lambda r: 20 <= r['cmv'] <= 300, '流通市值 20~300 亿')
stat('cmv', lambda r: r['cmv'] < 20, '流通市值 < 20 亿（游资盘）')
stat('cmv', lambda r: r['cmv'] > 500, '流通市值 > 500 亿')
print()
print('  —— 换手率区间（机构建仓常见 3~15%）——')
stat('hs', lambda r: 3 <= r['hs'] <= 15, '换手率 3~15%')
stat('hs', lambda r: 1 <= r['hs'] <= 20, '换手率 1~20%')
stat('hs', lambda r: r['hs'] > 20, '换手率 > 20%（浮筹重）')
stat('hs', lambda r: r['hs'] < 1, '换手率 < 1%（无量）')
print()
print('  —— 量化算法单痕迹：VWAP 偏离（算法单执行完收在均价附近）——')
stat('dev', lambda r: abs(r['dev']) <= 0.3, '|收盘−VWAP| ≤ 0.3%')
stat('dev', lambda r: abs(r['dev']) <= 0.5, '|收盘−VWAP| ≤ 0.5%')
stat('dev', lambda r: abs(r['dev']) <= 1.0, '|收盘−VWAP| ≤ 1.0%')
stat('dev', lambda r: abs(r['dev']) <= 0.5 and r['vr'] >= 1.5, '≤0.5% 且 量比≥1.5')
stat('dev', lambda r: abs(r['dev']) <= 0.5 and r['hs'] >= 3, '≤0.5% 且 换手≥3%')
print()
print('  —— 组合硬度 ——')
c1 = stat('x', lambda r: r['amt'] >= 2.0 and 20 <= r['cmv'] <= 500, '成交额≥2亿 且 市值20~500亿')
c2 = stat('x', lambda r: r['amt'] >= 2.0 and 20 <= r['cmv'] <= 500 and 3 <= r['hs'] <= 15,
          '  再加 换手3~15%')
c3 = stat('x', lambda r: r['amt'] >= 2.0 and 20 <= r['cmv'] <= 500 and 3 <= r['hs'] <= 15
          and abs(r['dev']) <= 1.0, '  再加 |VWAP偏离|≤1.0%')

print()
print('=' * 118)
print('二、候选池明细（按成交额排序，前 30）')
print('=' * 118)
rows.sort(key=lambda r: -r['amt'])
print('%-9s %-7s %6s %5s %7s %8s %8s %7s %7s  %s'
      % ('名称', '代码', '涨幅%', '量比', '成交额亿', '流通亿', '换手%', '振幅%', 'VWAP偏%', '机构痕迹'))
print('-' * 118)
for r in rows[:30]:
    tag = '✅量化' if (abs(r['dev']) <= 0.5 and r['vr'] >= 1.5) else ''
    print('%-9s %-7s %6.2f %5.2f %7.2f %8.1f %8.2f %7.2f %7.2f  %s'
          % (r['name'], r['code'], r['pct'], r['vr'], r['amt'], r['cmv'],
             r['hs'], r['amp'], r['dev'], tag))

# ---------- 涨停股：封成比 ----------
print()
print('=' * 118)
print('三、涨停股：封成比 = 封单额 ÷ 当日成交额（业内判板强度）')
print('=' * 118)
lu_rows = []
for r in recs:
    fund, amt = r.get('fund') or 0.0, r.get('amount') or 0.0
    ratio = (fund / amt) if amt > 0 else 0.0
    lu_rows.append((r['name'], r['code'], r.get('lbc') or 0, fund / 1e8,
                    amt / 1e8, ratio, (r.get('hs') or 0.0),
                    (r.get('ltsz') or 0.0) / 1e8))
lu_rows.sort(key=lambda x: -(x[5]))
print('%-9s %-7s %3s %9s %9s %8s %8s %8s' %
      ('名称', '代码', '板', '封单亿', '成交额亿', '封成比', '换手%', '流通亿'))
print('-' * 118)
for x in lu_rows[:20]:
    print('%-9s %-7s %3d %9.4f %9.2f %8.2f %8.2f %8.1f' % x)
print('...')
for x in lu_rows[-6:]:
    print('%-9s %-7s %3d %9.4f %9.2f %8.2f %8.2f %8.1f' % x)

print()
tot = len(lu_rows)
for th in (0.3, 0.5, 1.0, 1.5, 2.0):
    n = sum(1 for x in lu_rows if x[5] >= th)
    print('  封成比 ≥ %.1f 的涨停股：%2d / %d' % (th, n, tot))
print()
print('  换手率分布（涨停股）：')
for lo, hi, lab in ((0, 2, '<2% 一字锁筹'), (2, 8, '2~8% 健康'),
                    (8, 15, '8~15%'), (15, 25, '15~25%'), (25, 999, '>25% 高换手')):
    n = sum(1 for x in lu_rows if lo <= x[6] < hi)
    print('    %-14s %2d 只' % (lab, n))
