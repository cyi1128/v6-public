# -*- coding: utf-8 -*-
"""资金流评分 cloud_money_flow（工单6）

口径（用户 2026-11-07 指令）：
  money_score = 内外盘差40[>0.15 满] + 量比30[≥3 满，>8 降半] + 3日放量上涨占比30[>0.6 满]
  对倒/出货识别（更严）：量比>8 且 内外盘差<0（高位放量+外盘弱＝出货嫌疑）→ 总分再砍 30%（乘 0.7）
  子项缺失按可得项权重占比折算，promote_note 写明缺哪些；全部缺失 → money_score=None。
  单只失败只影响自己，绝不拖垮整批。

数据源（纯 stdlib）：腾讯快照 qt.gtimg.cn/q=code（gbk）
  外盘=f[7] 内盘=f[8] 换手=f[38] 量比=f[49] 涨跌幅=f[32] 现价=f[3] 昨收=f[4]
3日放量上涨占比：腾讯日K proxy.finance.qq.com（并发≤8、间隔 0.1s）

用法：
  python -u tools/cloud_money_flow.py --selftest
  python -u tools/cloud_money_flow.py --codes 600000,000001,...
"""
import json
import os
import ssl
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = {'User-Agent': 'Mozilla/5.0'}
MAX_WORKERS = 8
GAP = 0.1          # 每次请求之间的最小间隔
W_ORDER, W_VR, W_VOL = 40.0, 30.0, 30.0
ORDER_FULL = 0.15
VR_FULL = 3.0
VR_DUMP = 8.0      # 量比>8 降半
VOL_FULL = 0.6
DUMP_CUT = 0.7     # 出货嫌疑：总分乘 0.7（砍 30%）

_lock = threading.Lock()
_last = [0.0]


def _gate():
    """全局 0.1s 间隔（多线程共享）。"""
    with _lock:
        now = time.time()
        wait = GAP - (now - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()


def _get(url, timeout=12):
    _gate()
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout,
                                  context=ssl._create_unverified_context()).read()


def _mkt(code):
    c = str(code)
    return 'sh' if c.startswith(('6', '9', '5')) else ('bj' if c.startswith(('4', '8')) else 'sz')


def fetch_quote(code):
    """腾讯快照。失败 None（调用方按缺失处理）。"""
    try:
        raw = _get('https://qt.gtimg.cn/q=%s%s' % (_mkt(code), code)).decode('gbk', 'replace')
        body = raw.split('="', 1)[1].rstrip('";\n')
        f = body.split('~')
        if len(f) < 50:
            return None
        return {
            'code': str(code), 'name': f[1], 'price': float(f[3] or 0),
            'prev': float(f[4] or 0), 'outer': float(f[7] or 0), 'inner': float(f[8] or 0),
            'pct': float(f[32] or 0) if f[32] else None,
            'turnover': float(f[38] or 0) if f[38] else None,
            'vol_ratio': float(f[49] or 0) if f[49] else None,
        }
    except Exception as e:
        print('[money_flow] 快照失败 %s: %s' % (code, e))
        return None


def fetch_recent_bars(code, n=6):
    """日K（最近 n 根），失败 []。"""
    try:
        d = _get('https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get'
                 '?param=%s%s,day,,,%d,qfq' % (_mkt(code), code, n)).decode('utf-8', 'replace')
        j = json.loads(d)
        node = (j.get('data') or {}).get(_mkt(code) + str(code)) or {}
        kl = node.get('day') or node.get('qfqday') or []
        return [{'date': x[0], 'open': float(x[1]), 'close': float(x[2]),
                 'vol': float(x[5]) if len(x) > 5 else 0.0} for x in kl if len(x) >= 6]
    except Exception as e:
        print('[money_flow] 日K失败 %s: %s' % (code, e))
        return []


def vol_up_ratio(bars, days=3):
    """近 days 日「放量上涨」占比；数据不足 days+1 根返回 None。"""
    if not bars or len(bars) < days + 1:
        return None
    rows = bars[-(days + 1):]
    hit = 0
    for i in range(1, len(rows)):
        up = rows[i]['close'] > rows[i - 1]['close']
        vol_up = rows[i]['vol'] > rows[i - 1]['vol']
        if up and vol_up:
            hit += 1
    return hit / float(days)


def _s_order(r):
    if r is None:
        return None
    if r >= ORDER_FULL:
        return W_ORDER
    if r <= 0:
        return 0.0
    return W_ORDER * r / ORDER_FULL


def _s_vr(v):
    if v is None:
        return None
    if v > VR_DUMP:
        return W_VR / 2.0            # >8 降半
    if v >= VR_FULL:
        return W_VR
    return W_VR * max(v, 0) / VR_FULL


def _s_vol(r):
    if r is None:
        return None
    return W_VOL * min(r / VOL_FULL, 1.0)


def score_one(q, bars):
    """返回 {money_score, detail, missing, tag}。q 为 None → 数据不足。"""
    if not q:
        return {'money_score': None, 'detail': {}, 'missing': ['快照'],
                'note': '数据不足：快照拉取失败'}
    outer, inner = q.get('outer') or 0, q.get('inner') or 0
    order_ratio = None
    if outer + inner > 0:
        order_ratio = (outer - inner) / float(outer + inner)
    vr = q.get('vol_ratio')
    v3 = vol_up_ratio(bars)
    parts, missing, wsum = {}, [], 0.0
    s1 = _s_order(order_ratio)
    if s1 is None:
        missing.append('内外盘差')
    else:
        parts['order'] = s1
        wsum += W_ORDER
    s2 = _s_vr(vr)
    if s2 is None:
        missing.append('量比')
    else:
        parts['vr'] = s2
        wsum += W_VR
    s3 = _s_vol(v3)
    if s3 is None:
        missing.append('3日放量上涨')
    else:
        parts['vol'] = s3
        wsum += W_VOL
    if wsum <= 0:
        return {'money_score': None, 'detail': {'outer_ratio': None, 'vol_ratio': vr},
                'missing': missing, 'note': '数据不足：三项全缺'}
    raw = sum(parts.values())
    s = 100.0 * raw / wsum          # 缺项按可得项占比折算，不补假分
    dump = False
    if vr is not None and vr > VR_DUMP and order_ratio is not None and order_ratio < 0:
        dump = True
        s = s * DUMP_CUT
    note = ''
    if missing:
        note = '缺：%s（按可得项折算）' % '/'.join(missing)
    limit_up = (q.get('pct') or 0) >= 9.5
    if limit_up and order_ratio is not None and order_ratio <= -0.8:
        note = (note + '；' if note else '') + '涨停票外盘常为0（成交记内盘），内外盘差失真'
    if dump:
        note = (note + '；' if note else '') + '高位放量+外盘弱→出货嫌疑，总分砍30%'
    return {
        'money_score': round(s, 1),
        'detail': {'outer_ratio': None if order_ratio is None else round(order_ratio, 3),
                   'vol_ratio': vr, 'vol_up_ratio': None if v3 is None else round(v3, 2),
                   'turnover': q.get('turnover'), 'pct': q.get('pct'),
                   'dump_suspect': dump,
                   'limit_up': (q.get('pct') or 0) >= 9.5},
        'missing': missing, 'note': note,
    }


def score_codes(codes, workers=MAX_WORKERS):
    """批量评分。单只异常只标数据不足。"""
    codes = [str(c).strip() for c in codes if str(c).strip()]

    def one(c):
        try:
            q = fetch_quote(c)
            bars = fetch_recent_bars(c, 5) if q else []
            r = score_one(q, bars)
            r['code'] = c
            return r
        except Exception as e:
            return {'code': c, 'money_score': None, 'detail': {}, 'missing': ['异常'],
                    'note': '单只异常：%s' % e}

    with ThreadPoolExecutor(max_workers=max(1, min(workers, MAX_WORKERS))) as ex:
        return list(ex.map(one, codes))


def _selftest():
    ok = True

    def ck(name, cond, got=''):
        nonlocal ok
        print(('PASS ' if cond else 'FAIL ') + name + ('  ' + str(got) if got else ''))
        if not cond:
            ok = False

    # 1. 全满：外盘差 0.30 / 量比 3.5 / 放量上涨 0.67 → 100
    q = {'outer': 1300, 'inner': 700, 'vol_ratio': 3.5, 'turnover': 5.0, 'pct': 6.0}
    bars = [{'close': 10, 'vol': 100}, {'close': 11, 'vol': 120},
            {'close': 12, 'vol': 150}, {'close': 12.5, 'vol': 160}]
    r = score_one(q, bars)
    ck('全满→100', r['money_score'] == 100.0, r['money_score'])
    # 2. 内外盘差 0.075（半数）→ 40*0.5=20；量比 1.5→15；放量上涨 2/3=0.667→30 满 → 65
    q2 = {'outer': 1075, 'inner': 925, 'vol_ratio': 1.5, 'turnover': 3.0, 'pct': 1.0}
    bars2 = [{'close': 10, 'vol': 100}, {'close': 11, 'vol': 120},
             {'close': 10.8, 'vol': 150}, {'close': 11.2, 'vol': 160}]
    r2 = score_one(q2, bars2)
    ck('中档 65.0', r2['money_score'] == 65.0, r2['money_score'])
    # 3. 量比>8 降半：量比 9 → 15（其余满）→ 85
    q3 = {'outer': 1300, 'inner': 700, 'vol_ratio': 9.0, 'turnover': 9.0, 'pct': 8.0}
    r3 = score_one(q3, bars)
    ck('量比>8降半→85', r3['money_score'] == 85.0, r3['money_score'])
    # 4. 出货嫌疑：量比 10 且内外盘差<0 → (0+15+30)=45 → 砍30% = 31.5
    q4 = {'outer': 600, 'inner': 1400, 'vol_ratio': 10.0, 'turnover': 12.0, 'pct': 7.0}
    r4 = score_one(q4, bars)
    print('dump=', r4['money_score'], r4['note'])
    ck('出货嫌疑砍30%→31.5', r4['money_score'] == 31.5, r4['money_score'])
    ck('出货嫌疑有标注', r4['detail']['dump_suspect'] is True and '砍30%' in r4['note'], r4['note'])
    # 5. 断网摊权：快照在、日K缺 → 按 40+30 折算（不补 15 分假分）
    r5 = score_one({'outer': 1300, 'inner': 700, 'vol_ratio': 3.5}, [])
    print('offline fold=', r5['money_score'], r5['missing'])
    ck('断网按可得项折算=100', r5['money_score'] == 100.0 and '3日放量上涨' in r5['missing'],
       (r5['money_score'], r5['missing']))
    # 6. 三项全缺 → None，不编分
    r6 = score_one({'outer': 0, 'inner': 0, 'vol_ratio': None}, [])
    ck('全缺→None', r6['money_score'] is None, r6['money_score'])
    # 7. 快照失败 → 数据不足，不抛异常
    r7 = score_one(None, [])
    ck('快照失败→数据不足', r7['money_score'] is None and '数据不足' in r7['note'], r7['note'])
    # 9. 涨停票标注：外盘为0导致内外盘差 -1，如实提示失真（不静默当正常）
    r9 = score_one({'outer': 0, 'inner': 3000, 'vol_ratio': 1.0, 'turnover': 5.0, 'pct': 10.0}, bars)
    print('limitup=', r9['money_score'], r9['note'])
    ck('涨停票标注内外盘失真', '内盘' in r9['note'] and r9['detail']['limit_up'] is True, r9['note'])
    # 8. 批量里单只失败不拖垮其他
    res = score_codes(['600000', 'ZZZZZZ', '000001'])
    print('batch=', [(x['code'], x['money_score']) for x in res])
    ck('批量隔离失败', len(res) == 3 and any(x['money_score'] is not None for x in res), '')
    print('[selftest] money_flow RESULT %s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 5


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(_selftest())
    if '--codes' in sys.argv:
        i = sys.argv.index('--codes')
        codes = sys.argv[i + 1].split(',') if i + 1 < len(sys.argv) else []
        for r in score_codes(codes):
            print('%-8s money=%-6s 外盘差=%-7s 量比=%-6s 放量上涨=%-5s %s'
                  % (r.get('code'), r.get('money_score'),
                     (r.get('detail') or {}).get('outer_ratio'),
                     (r.get('detail') or {}).get('vol_ratio'),
                     (r.get('detail') or {}).get('vol_up_ratio'),
                     r.get('note') or ''))
        sys.exit(0)
    print('用法: cloud_money_flow.py --selftest | --codes 600000,000001')
