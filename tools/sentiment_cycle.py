# -*- coding: utf-8 -*-
"""情绪周期定位器 sentiment_cycle（工单7）

口径（用户 2026-11-07 指令）：
  S = 涨停家数30[≥80家满] + 炸板率25[≤20%满] + 昨涨停溢价25[≥3%满] + 高度20[≥5板满]
  四态：S≥75 高潮 / 55-74 回暖 / 35-54 退潮 / <35 冰点
  档位：高潮→可重仓 / 回暖→底仓轻仓 / 退潮→轻仓只看 / 冰点→空仓1成
  转折信号缺数据不写；子项缺数据按可得项占比折算，绝不编分。

纯标准库。数据源：
  涨停池 / 炸板池：东财 push2ex（支持 date 参数，可回算历史）
  昨涨停溢价：腾讯日K（proxy.finance.qq.com，取昨收→今收涨幅），拉不到就标"数据未接入"
"""
import json
import os
import ssl
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = {'User-Agent': 'Mozilla/5.0'}
EM_UT = '7eea3edcaed734bea9cbfc24409ed989'

LEVELS = [(75, '高潮期', '可重仓'), (55, '回暖期', '底仓轻仓'), (35, '退潮期', '轻仓只看')]
BOTTOM = ('冰点期', '空仓1成')

W_ZT, W_ZB, W_PM, W_H = 30.0, 25.0, 25.0, 20.0


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    ctx = ssl._create_unverified_context()
    return urllib.request.urlopen(req, timeout=timeout, context=ctx).read().decode('utf-8', 'replace')


def fetch_pool(day):
    """当日涨停池（东财原始行）。失败返回 []。"""
    try:
        t = _get('https://push2ex.eastmoney.com/getTopicZTPool?ut=%s&dpt=wz.ztzt'
                 '&Pageindex=0&pagesize=300&sort=fbt:asc&date=%s' % (EM_UT, day))
        return (json.loads(t).get('data') or {}).get('pool') or []
    except Exception:
        return []


def fetch_zb(day):
    """当日炸板池。失败返回 []，由调用方标'数据未接入'。"""
    try:
        t = _get('https://push2ex.eastmoney.com/getTopicZBPool?ut=%s&dpt=wz.ztzt'
                 '&Pageindex=0&pagesize=300&sort=fbt:asc&date=%s' % (EM_UT, day))
        return (json.loads(t).get('data') or {}).get('pool') or []
    except Exception:
        return []


def _kline_ret(code, day):
    """腾讯日K：返回 (prev_close, close) for day。失败 None。"""
    try:
        mkt = 'sh' if str(code).startswith(('6', '9')) else 'sz'
        t = _get('https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get'
                 '?param=%s%s,day,,,10,qfq' % (mkt, code), timeout=12)
        j = json.loads(t)
        d = (j.get('data') or {}).get(mkt + str(code)) or {}
        kl = d.get('day') or d.get('qfqday') or []
        rows = [(x[0].replace('-', ''), float(x[1]), float(x[2])) for x in kl if len(x) >= 3]
        for i, (dt, op, cl) in enumerate(rows):
            if dt == day and i > 0:
                return rows[i - 1][2], cl
        return None
    except Exception:
        return None


def _prev_biz(day):
    """上一个工作日（只跳周末，节假日不猜）。"""
    from datetime import datetime, timedelta
    d0 = datetime.strptime(day, '%Y%m%d')
    for i in range(1, 8):
        d1 = d0 - timedelta(days=i)
        if d1.weekday() < 5:
            return d1.strftime('%Y%m%d')
    return day


def prev_premium(prev_pool, day, workers=8):
    """昨涨停票今日涨幅均值（%）。返回 (均值 or None, 统计只数)。"""
    codes = [str(x.get('c') or x.get('code') or '') for x in prev_pool or []]
    codes = [c for c in codes if c]
    if not codes:
        return None, 0
    rets = []

    def one(c):
        r = _kline_ret(c, day)
        if not r or not r[0]:
            return None
        return (r[1] - r[0]) / r[0] * 100.0

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for v in ex.map(one, codes):
            if v is not None and -60 < v < 60:
                rets.append(v)
    if len(rets) < max(5, len(codes) * 0.3):
        return None, len(rets)
    return round(sum(rets) / len(rets), 2), len(rets)


def _score_zt(n):
    return W_ZT * min(n / 80.0, 1.0)


def _score_zb(rate):
    if rate <= 0.2:
        return W_ZB
    if rate >= 0.6:
        return 0.0
    return W_ZB * (0.6 - rate) / 0.4


def _score_pm(pct):
    if pct is None:
        return None
    if pct >= 3.0:
        return W_PM
    if pct <= -3.0:
        return 0.0
    return W_PM * (pct + 3.0) / 6.0


def _score_h(max_lb):
    return W_H * min(max_lb / 5.0, 1.0)


def level_of(s):
    for hi, name, pos in LEVELS:
        if s >= hi:
            return name, pos
    return BOTTOM


def compute(pool, zb_pool, premium=None, prev_pool=None):
    """纯计算。缺项按可得项占比折算（并记录 missing）。"""
    zt = len(pool or [])
    zb = len(zb_pool or []) if zb_pool is not None else None
    max_lb = max([int(x.get('lbc') or 0) for x in (pool or [])], default=0)
    parts, missing = {}, []
    wsum = 0.0
    if zt > 0:
        parts['zt'] = _score_zt(zt)
        wsum += W_ZT
    else:
        missing.append('涨停家数')
    if zb is not None and zt + zb > 0:
        rate = zb / float(zt + zb)
        parts['zb'] = _score_zb(rate)
        wsum += W_ZB
        parts['zb_rate'] = round(rate * 100, 1)
    else:
        missing.append('炸板率')
    p = _score_pm(premium)
    if p is None:
        missing.append('昨涨停溢价')
    else:
        parts['pm'] = p
        wsum += W_PM
    if max_lb > 0:
        parts['h'] = _score_h(max_lb)
        wsum += W_H
    else:
        missing.append('高度')

    raw = sum(parts[k] for k in ('zt', 'zb', 'pm', 'h') if k in parts)
    s = 100.0 * raw / wsum if wsum > 0 else None
    name, pos = level_of(s) if s is not None else ('数据不足', '—')
    detail = {'zt': zt, 'zb': zb, 'max_lb': max_lb, 'premium': premium,
              'parts': {k: round(v, 1) for k, v in parts.items()},
              'weight_used': wsum, 'missing': missing}
    return {'S': None if s is None else round(s, 1), 'level': name, 'position': pos,
            'detail': detail, 'missing': missing}


def turning_signals(today, prev_day_result=None):
    """转折信号：只在数据齐时给，缺就不写。"""
    out = []
    d = today.get('detail') or {}
    p = (prev_day_result or {}).get('detail') or {}
    if d.get('zt') is not None and p.get('zt') is not None:
        if d['zt'] <= p['zt'] * 0.5:
            out.append('涨停腰斩（%d→%d家）' % (p['zt'], d['zt']))
    if d.get('max_lb') is not None and p.get('max_lb') is not None:
        if d['max_lb'] <= max(2, p['max_lb'] - 2):
            out.append('高度板断档（%d板→%d板）' % (p['max_lb'], d['max_lb']))
    return out


def card_line(res):
    """竞价卡顶部一行。"""
    if not res or res.get('S') is None:
        return ''
    return '🌡️ 情绪周期：%s(S=%.0f) → 建议档位：%s' % (res['level'], res['S'], res['position'])


def run_day(day, prev_day, workers=8):
    pool = fetch_pool(day)
    zb = fetch_zb(day)
    prev_pool = fetch_pool(prev_day)
    pm, n = prev_premium(prev_pool, day, workers=workers)
    res = compute(pool, zb if zb else None, pm, prev_pool)
    res['date'] = day
    res['premium_n'] = n
    if zb == []:
        res['missing'] = list(res.get('missing') or []) + ['炸板池(接口无数据)']
    return res


def _selftest():
    ok = True

    def ck(name, cond, got=''):
        nonlocal ok
        print(('PASS ' if cond else 'FAIL ') + name + ('  ' + str(got) if got else ''))
        if not cond:
            ok = False

    # 边界：一档一测（构造刚好落在 75 / 55 / 35）
    # 75：涨停80家(30)+炸板率20%(25)+溢价3%(25)+高度5板(20)=100 → 改高度0? 用调档构造
    def mk(zt, zb, pm, lb):
        pool = [{'c': str(600000 + i), 'lbc': lb if i == 0 else 1} for i in range(zt)]
        return compute(pool, [{'c': str(1)}] * zb, pm)

    r = mk(80, 20, 3.0, 5)
    ck('全满→100 高潮', r['S'] == 100.0 and r['level'] == '高潮期', (r['S'], r['level'], r['position']))
    r = mk(80, 20, 3.0, 4)   # 高度16 → 96
    ck('96 仍高潮', r['level'] == '高潮期', r['S'])
    r = mk(40, 60, 3.0, 5)   # 15+0(炸板60%)+25+20=60
    ck('60 回暖', r['S'] == 60.0 and r['level'] == '回暖期', (r['S'], r['level'], r['position']))
    r = mk(40, 60, 3.0, 3)   # 15+0+25+12=52
    ck('52 退潮', r['level'] == '退潮期' and r['position'] == '轻仓只看', (r['S'], r['level'], r['position']))
    r = mk(8, 30, -3.0, 1)   # 3+0+0+4=7
    ck('7 冰点', r['level'] == '冰点期' and r['position'] == '空仓1成', (r['S'], r['level'], r['position']))

    # 阈值边界：75 / 55 / 35 正好落档
    for target, want in ((75.0, '高潮期'), (55.0, '回暖期'), (35.0, '退潮期')):
        ck('边界%.0f→%s' % (target, want), level_of(target)[0] == want, level_of(target))
    ck('34.9→冰点', level_of(34.9)[0] == '冰点期', level_of(34.9))

    # 缺溢价：按可得项(75)折算，不补假分
    r = compute([{'c': '600001', 'lbc': 5}] * 80, [{'c': 'x'}] * 20, None)
    print('缺溢价 folded=', r['S'], r['parts'] if 'parts' in r else r['detail']['parts'])
    ck('缺溢价按占比折算', r['S'] == 100.0 and '昨涨停溢价' in r['missing'], (r['S'], r['missing']))

    # 全缺 → 数据不足，不出档位
    r = compute([], None, None)
    ck('全缺→数据不足', r['S'] is None and r['level'] == '数据不足', (r['S'], r['level']))

    # 卡面一行格式
    line = card_line({'S': 42.0, 'level': '退潮期', 'position': '轻仓只看'})
    print('card=', line)
    ck('卡面格式', line == '🌡️ 情绪周期：退潮期(S=42) → 建议档位：轻仓只看', line)

    # 转折信号
    a = {'detail': {'zt': 32, 'max_lb': 3}}
    b = {'detail': {'zt': 80, 'max_lb': 5}}
    sig = turning_signals(a, b)
    print('signals=', sig)
    ck('涨停腰斩+高度断档识别', len(sig) == 2, sig)
    ck('无数据不写信号', turning_signals({'detail': {}}, None) == [], '')

    print('[selftest] sentiment_cycle RESULT %s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 4


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(_selftest())
    days = sys.argv[1:]
    if not days:
        print('用法: sentiment_cycle.py YYYYMMDD [...]')
        sys.exit(0)
    for d in days:
        r = run_day(d, _prev_biz(d))
        print('%s S=%s %s/%s 涨停%d 炸板%s 最高%d板 溢价%s(%d只) 缺:%s'
              % (d, r['S'], r['level'], r['position'], r['detail']['zt'],
                 r['detail']['zb'], r['detail']['max_lb'], r['detail']['premium'],
                 r.get('premium_n'), r['missing']))
        print('   ' + (card_line(r) or '（数据不足，不出卡面行）'))
