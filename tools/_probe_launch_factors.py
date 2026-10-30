# -*- coding: utf-8 -*-
"""启动前吸筹/震仓/试盘因子 + 启动后主升量能：13 个正样本实测。

不依赖 detect_pattern_bottom（它现已是「未突破才收」的 V9 口径），
直接定位启动周：周K放量收阳 且 周收盘站上前 40 日横盘上沿。
"""
import statistics
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')

from services.band_pattern_engine import _load_bars, _to_weekly, _ma  # noqa: E402

CASES = [
    ('600640', '国脉文化'), ('601112', '振石股份'), ('600088', '中视传媒'),
    ('002584', '西陇科学'), ('600793', '宜宾纸业'), ('605577', '龙版传媒'),
    ('002005', '德豪润达'), ('603230', '内蒙新华'), ('600127', '金健米业'),
    ('000910', '大亚圣象'), ('002246', '北化股份'), ('605058', '澳弘电子'),
    ('600503', '华丽家族'),
]


def find_launch(bars):
    """找到第一个「周K放量收阳 + 站上前40日上沿」的周，返回 (si, st, hi, lo, weeks_i)"""
    weeks = _to_weekly(bars)
    for wi in range(12, len(weeks)):
        wstart = weeks[wi]['date'][:10]
        si = None
        for i in range(len(bars)):
            if bars[i]['date'][:10] >= wstart:
                si = i
                break
        if si is None or si < 45:
            continue
        wn, wp = weeks[wi], weeks[wi - 1]
        if not wp['volume']:
            continue
        if wn['volume'] / wp['volume'] < 1.3 or wn['close'] <= wn['open']:
            continue
        st = si - 40
        cand = bars[st:si]
        hi = max(b['high'] for b in cand)
        lo = min(b['low'] for b in cand)
        if lo <= 0 or (hi - lo) / lo > 0.25:
            continue
        half = len(cand) // 2
        if min(b['low'] for b in cand[half:]) <= min(b['low'] for b in cand[:half]):
            continue
        if (statistics.mean([b['close'] for b in cand[half:]])
                <= statistics.mean([b['close'] for b in cand[:half]])):
            continue
        if wn['close'] <= hi:            # 必须站上上沿 = 真启动
            continue
        return si, st, hi, lo, wi
    return None, None, None, None, None


def factors(bars, si, hi, lo, st):
    vols = [b['volume'] for b in bars]
    win = bars[st:si]
    n = len(win)
    if n < 8 or si < 10:
        return None
    f = {}
    uv = [b['volume'] for b in win if b['close'] > b['open']]
    dv = [b['volume'] for b in win if b['close'] <= b['open']]
    f['A1阳阴量比'] = (statistics.mean(uv) / statistics.mean(dv)) if uv and dv else 0
    dn = [b for b in win if b['close'] <= b['open'] and b['high'] > b['low']]
    f['A2承接度'] = (statistics.mean(
        [(b['close'] - b['low']) / (b['high'] - b['low']) for b in dn]) if dn else 0)
    sh = [b for b in win if b['high'] > b['low']
          and (min(b['open'], b['close']) - b['low']) / (b['high'] - b['low']) >= 0.35]
    f['A3下影日占比'] = len(sh) * 100.0 / n
    m = statistics.mean([b['volume'] for b in win])
    f['A4量能平稳度'] = (1 - statistics.pstdev([b['volume'] for b in win]) / m) if m else 0
    h = n // 2
    f['A5重心斜率%'] = ((statistics.mean([b['close'] for b in win[h:]])
                     / statistics.mean([b['close'] for b in win[:h]]) - 1) * 100)
    f['A6末期量能比'] = ((statistics.mean([b['volume'] for b in win[-10:]])
                     / statistics.mean([b['volume'] for b in win[:10]]))
                    if n >= 20 else 0)
    p5v = statistics.mean(vols[si - 5:si]) if si >= 5 else 0
    f['B1地量比'] = (p5v / m) if m else 0
    seg5 = bars[max(st, si - 5):si]
    low5 = min(b['low'] for b in seg5)
    f['B2回撤占比%'] = ((hi - low5) / (hi - lo) * 100) if hi > lo else 0
    f['B3振幅收敛'] = (statistics.mean([(b['high'] - b['low']) / b['close'] for b in seg5])
                  / statistics.mean([(b['high'] - b['low']) / b['close'] for b in win]))
    f['C1最大下影%'] = max((min(b['open'], b['close']) - b['low'])
                       / (b['high'] - b['low']) * 100
                       for b in seg5 if b['high'] > b['low'])
    ma20 = _ma([b['close'] for b in bars[:si]], 20)
    f['C2探针MA20%'] = ((low5 - ma20) / ma20 * 100) if ma20 else 0
    weeks = _to_weekly(bars[:si + 1])
    w_now, w_prev = weeks[-1], weeks[-2]
    f['D1周量倍'] = w_now['volume'] / w_prev['volume'] if w_prev['volume'] else 0
    f['D2触发日量倍'] = (bars[si]['volume'] / p5v) if p5v else 0
    f['D3启动周最大日量倍'] = max(
        (bars[i]['volume'] / statistics.mean(vols[i - 5:i]))
        for i in range(si, min(si + 5, len(bars)))
        if i >= 5 and statistics.mean(vols[i - 5:i]) > 0)
    a = si + 1
    f['E1启动后5日量比'] = ((statistics.mean(vols[a:a + 5]) / p5v)
                       if p5v and len(bars) >= a + 5 else 0)
    f['E2启动后10日量比'] = ((statistics.mean(vols[a:a + 10]) / p5v)
                        if p5v and len(bars) >= a + 10 else 0)
    if len(bars) >= a + 20:
        hi20 = max(b['high'] for b in bars[a:a + 20])
        f['E3后20日最大涨幅%'] = (hi20 / bars[si]['close'] - 1) * 100
        f['E4后20日最大回撤%'] = (min(b['low'] for b in bars[a:a + 20])
                            / bars[si]['close'] - 1) * 100
        dn_after = [b for b in bars[a:a + 10] if b['close'] < b['open']]
        f['E5回调日量/启动日量'] = ((statistics.mean([b['volume'] for b in dn_after])
                              / bars[si]['volume']) if dn_after else 0)
        f['E7启动后最大天量倍'] = max(b['volume'] for b in bars[a:a + 10]) / p5v if p5v else 0
        f['E6出现缩量新高'] = 0
        ph = None
        for i in range(a, min(a + 20, len(bars))):
            if bars[i]['high'] >= hi20 * 0.995:
                ph = i
                break
        if ph and ph >= 6:
            pv = max(bars[j]['volume'] for j in range(max(0, ph - 20), ph - 1))
            if pv and bars[ph]['volume'] < pv * 0.9:
                f['E6出现缩量新高'] = 1
    return f


ALL = []
print('=' * 152)
print('启动前：吸筹 / 震仓 / 试盘 因子（13 个正样本）')
print('=' * 152)
print('%-9s %-11s %6s %7s %7s %8s %8s %7s %7s %7s %8s %8s'
      % ('名称', '启动周', '振幅%', '阳阴量比', '承接度', '下影占比%', '量能平稳',
         '重心斜%', '地量比', '回撤占%', '振幅收敛', '试盘下影%'))
print('-' * 152)
for code, name in CASES:
    bars = _load_bars(code)
    if len(bars) < 80:
        print('%-9s 数据不足(%d)' % (name, len(bars)))
        continue
    si, st, hi, lo, wi = find_launch(bars)
    if si is None:
        print('%-9s 未找到启动周' % name)
        continue
    f = factors(bars, si, hi, lo, st)
    if not f:
        continue
    f['_name'], f['_code'], f['_si'], f['_bars'] = name, code, si, bars
    ALL.append(f)
    print('%-9s %-11s %6.1f %7.2f %7.2f %8.1f %8.2f %7.2f %7.2f %7.1f %8.2f %8.1f'
          % (name, bars[si]['date'][:10], (hi - lo) / lo * 100,
             f['A1阳阴量比'], f['A2承接度'], f['A3下影日占比'], f['A4量能平稳度'],
             f['A5重心斜率%'], f['B1地量比'], f['B2回撤占比%'], f['B3振幅收敛'],
             f['C1最大下影%']))

print()
print('=' * 152)
print('启动后：主升量能')
print('=' * 152)
print('%-9s %8s %9s %11s %10s %11s %11s %12s %11s %9s'
      % ('名称', '周量倍', '触发日倍', '周内最大倍', '后5日量比', '后10日量比',
         '后20日涨幅%', '后20日回撤%', '回调/启动', '天量倍'))
print('-' * 152)
for f in ALL:
    print('%-9s %8.2f %9.2f %11.2f %10.2f %11.2f %11.1f %12.1f %11.2f %9.2f'
          % (f['_name'], f['D1周量倍'], f['D2触发日量倍'], f['D3启动周最大日量倍'],
             f['E1启动后5日量比'], f['E2启动后10日量比'],
             f.get('E3后20日最大涨幅%', 0), f.get('E4后20日最大回撤%', 0),
             f.get('E5回调日量/启动日量', 0), f.get('E7启动后最大天量倍', 0)))

print()
print('=' * 152)
print('分布（中位 / 最小 / 最大）')
print('=' * 152)
KEYS = ['A1阳阴量比', 'A2承接度', 'A3下影日占比', 'A4量能平稳度', 'A5重心斜率%',
        'A6末期量能比', 'B1地量比', 'B2回撤占比%', 'B3振幅收敛', 'C1最大下影%',
        'C2探针MA20%', 'D1周量倍', 'D2触发日量倍', 'D3启动周最大日量倍',
        'E1启动后5日量比', 'E2启动后10日量比', 'E3后20日最大涨幅%',
        'E4后20日最大回撤%', 'E5回调日量/启动日量', 'E7启动后最大天量倍']
for k in KEYS:
    vs = sorted(f[k] for f in ALL if f.get(k) is not None)
    if not vs:
        continue
    print('  %-18s 中位 %8.2f  最小 %8.2f  最大 %8.2f  n=%d'
          % (k, statistics.median(vs), vs[0], vs[-1], len(vs)))
print()
print('  主升途中出现「缩量新高」：%d / %d'
      % (sum(1 for f in ALL if f.get('E6出现缩量新高')), len(ALL)))
