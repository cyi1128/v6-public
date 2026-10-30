# -*- coding: utf-8 -*-
"""独立复算模式四（不复用引擎函数），验证 DB 中 605123 派克新材 / 000062 深圳华强"""
import sys
sys.path.insert(0, r'D:\QuantMonitorV6')

from services.kline_cache_service import get_latest_kline

def ma(vals, n):
    if len(vals) < n:
        return None
    return sum(vals[-n:]) / n

for code, name in [('605123', '派克新材'), ('000062', '深圳华强')]:
    bars = get_latest_kline(code, 120)
    if not bars:
        print(code, name, '无K线数据'); continue
    print('=' * 70)
    print(code, name, '  K线根数:', len(bars), ' 最新:', bars[-1]['date'])
    closes = [b['close'] for b in bars]
    vols = [b['volume'] for b in bars]

    recent = bars[-21:-1]
    print('结构区间: %s ~ %s  共%d根（最新K线不参与上下沿）'
          % (recent[0]['date'], recent[-1]['date'], len(recent)))
    r_high = max(b['high'] for b in recent)
    r_low = min(b['low'] for b in recent)
    amp = (r_high - r_low) / r_low * 100
    print('结构高=%.2f 结构低=%.2f 振幅=%.2f%%  条件(<=15%%) -> %s'
          % (r_high, r_low, amp, '通过' if amp <= 15 else '不通过'))

    half = len(recent) // 2
    lf = min(b['low'] for b in recent[:half])
    ls = min(b['low'] for b in recent[half:])
    print('低点抬高: 前半低=%.2f 后半低=%.2f -> %s' % (lf, ls, '通过' if ls > lf else '不通过'))

    ma5 = ma(closes, 5)
    ma5_prev = sum(closes[-10:-5]) / 5
    print('MA5=%.2f  5日前MA5=%.2f -> %s' % (ma5, ma5_prev, '通过' if ma5 >= ma5_prev else '不通过'))

    start_i = len(bars) - len(recent)
    end_i = start_i + len(recent) - 1
    up_days = up_ok = down_days = down_ok = 0
    recent_vol3 = 0
    print('--- 逐根量能明细 ---')
    for k, b in enumerate(recent):
        gi = start_i + k
        if gi < 5:
            continue
        p5 = sum(vols[gi - 5:gi]) / 5.0
        if p5 <= 0:
            continue
        vr = b['volume'] / p5
        if b['close'] > b['open']:
            up_days += 1
            ok = vr >= 1.3
            if ok:
                up_ok += 1
                if gi >= end_i - 2:
                    recent_vol3 = 1
            print('  %s 阳 量比前5均=%.2f  %s%s' % (b['date'], vr,
                  '1.3倍达成' if ok else '', ' [最近3日]' if gi >= end_i - 2 else ''))
        else:
            down_days += 1
            ok = b['volume'] <= p5 * 1.0
            if ok:
                down_ok += 1
            print('  %s 阴 量比前5均=%.2f  %s' % (b['date'], vr, '缩量达成' if ok else ''))
    up_rate = up_ok / up_days * 100 if up_days else 0
    down_rate = down_ok / down_days * 100 if down_days else 0
    print('上涨日 %d 中 1.3倍达成 %d -> 满足率 %.1f%%  (要求>=50%%) -> %s'
          % (up_days, up_ok, up_rate, '通过' if up_rate >= 50 else '不通过'))
    print('下跌日 %d 中 缩量达成 %d -> 满足率 %.1f%%  (要求>=60%%) -> %s'
          % (down_days, down_ok, down_rate, '通过' if down_rate >= 60 else '不通过'))
    print('最近3日出现1.3倍放量上涨 -> %s' % ('是' if recent_vol3 else '否'))

    pos = (closes[-1] - r_low) / (r_high - r_low) * 100
    print('结构位置 = (%.2f-%.2f)/(%.2f-%.2f) = %.1f%%  (要求>=70%% 且 <=100%%) -> %s'
          % (closes[-1], r_low, r_high, r_low, pos,
             '通过' if 70 <= pos <= 100 else '不通过'))
    allok = (amp <= 15 and ls > lf and ma5 >= ma5_prev and up_rate >= 50
             and down_rate >= 60 and recent_vol3 and 70 <= pos <= 100)
    print('>>> 九项全满足 -> %s' % ('建仓触发' if allok else '未触发'))
