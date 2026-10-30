# -*- coding: utf-8 -*-
"""验收机构/量化执行标准：引擎侧 + 界面侧。"""
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')
import py_compile                                                    # noqa: E402

py_compile.compile(r'D:\QuantMonitorV6\services\board_anomaly_engine.py', doraise=True)
py_compile.compile(r'D:\QuantMonitorV6\ui\battle_widgets\market_rhythm_widget.py', doraise=True)
print('py_compile OK')

from services.board_anomaly_engine import (                          # noqa: E402
    get_board_anomaly, get_flat_rows, _load_limit_up, _seal_ratio,
    _is_rotten, _load_realtime, _load_ma20, _load_pools,
    _PICK_MIN_AMOUNT, _PICK_MIN_CMV, _VWAP_DEV_MAX, _VWAP_VR_MIN,
    _PICK_MIN_PCT, _PICK_MAX_PCT, _PICK_MIN_VR, _PICK_MIN_PRICE)

print()
print('=' * 104)
print('一、烂板识别（封成比 < 0.10 且 ≥2 板）')
print('=' * 104)
ludate, recs = _load_limit_up()
rotten = [r for r in recs if _is_rotten(r)]
print('涨停 %d 只，其中烂板 %d 只：' % (len(recs), len(rotten)))
for r in sorted(rotten, key=lambda x: -(_seal_ratio(x))):
    print('  %-9s %-7s %d板 封成比 %.3f 封单%.4f亿 成交%.2f亿 换手%.2f%% 炸板%d次'
          % (r['name'], r['code'], r.get('lbc') or 0, _seal_ratio(r),
             (r.get('fund') or 0) / 1e8, (r.get('amount') or 0) / 1e8,
             r.get('hs') or 0, r.get('zbc') or 0))

print()
print('=' * 104)
print('二、可介入池：机构门槛前后对比（全市场口径）')
print('=' * 104)
q, ma20, pools = _load_realtime(), _load_ma20(), _load_pools()
lu = pools.get('lu') or set()


def build(use_inst):
    n = 0
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
        if use_inst:
            amt = float(v.get('amount') or 0.0)
            cmv = float(v.get('circ_mv') or 0.0)
            if amt and amt < _PICK_MIN_AMOUNT:
                continue
            if cmv and cmv < _PICK_MIN_CMV:
                continue
        m20 = ma20.get(code)
        if not m20 or px < m20:
            continue
        n += 1
    return n


print('  旧口径（非涨停/1~9%%/量比≥1.2/≥6元/非ST/站上MA20）：%d 只' % build(False))
print('  加机构门槛（成交额≥2亿 + 流通市值≥20亿）：        %d 只  留存 %.0f%%'
      % (build(True), build(True) * 100.0 / max(build(False), 1)))
print()
print('  量化痕迹阈值：|最新价 − VWAP| ≤ %.1f%%  且  量比 ≥ %.1f'
      % (_VWAP_DEV_MAX, _VWAP_VR_MIN))

print()
print('=' * 104)
print('三、端到端：板块的情绪龙头 / 接力参考 / 可介入（带量化痕迹）')
print('=' * 104)
bd = get_board_anomaly(force=True)
rows = get_flat_rows(bd)
print('引擎 ok=%s  拍平 %d 行  可介入行数 %d'
      % (bd.get('ok'), len(rows), bd.get('pick_rows')))
print()
for r in rows[:8]:
    dg = (r.get('dragons') or [{}])[0]
    e = r.get('entry') or {}
    print('【%s】' % r.get('name'))
    print('  情绪龙头：%s %d板 %s 封成比%.2f 强度%.2f%%%s'
          % (dg.get('name'), dg.get('lbc', 0), dg.get('slot_name', ''),
             dg.get('ratio') or 0.0, (dg.get('strength') or 0) * 100,
             '  ⚠烂板' if dg.get('rotten') else ''))
    if e:
        print('  接力参考：%s %d板 %s 封成比%.2f 强度%.2f%%'
              % (e['name'], e['lbc'], e.get('slot_name', ''),
                 e.get('ratio') or 0.0, (e.get('strength') or 0) * 100))
    for p in (r.get('picks') or [])[:3]:
        print('  可介入　：%s %s %+.2f%% 量比%.2f 额%.2f亿 市值%.0f亿 换手%.2f%% '
              'VWAP偏%s %s'
              % (p[1], p[0], p[2], p[3], p[6], p[7], p[8],
                 ('%+.2f%%' % p[9]) if p[9] is not None else '--',
                 '✅量化' if p[10] else ''))
    print('-' * 104)
