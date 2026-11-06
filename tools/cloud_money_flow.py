# -*- coding: utf-8 -*-
"""资金流评分 cloud_money_flow（工单6）

双口径（用户 2026-11-07 定案）：
  非涨停票（caliber=内外盘口径）
    money_score = 内外盘差40[>0.15满] + 量比30[≥3满,>8降半] + 3日放量上涨30[>0.6满]
    出货嫌疑：量比>8 且 内外盘差<0 → 总分 ×0.7（砍30%）
  涨停票（caliber=封单口径；涨停时成交全记内盘、外盘=0，内外盘失真）
    封单强度40[封单额/流通市值 ≥5%满, 2%给20, <1%给5]
  + 量比质量30[<1.5缩量板30, 1.5-3给25, 3-8给15, >8烂板5]
  + 3日放量上涨30[沿用]
    反复开板（炸板次数>2，可得时）总分 ×0.8
缺项按可得项权重占比折算并写明缺哪些；全缺 → None；单只失败只影响自己。

数据源（纯 stdlib）：腾讯快照 qt.gtimg.cn（gbk）
  f3现价 f4昨收 f6成交量 f7外盘 f8内盘 f9买一价 f10买一量(手)
  f32涨跌幅 f38换手 f44流通市值(亿) f47涨停价 f49量比
3日放量上涨占比：腾讯日K（并发≤8、全局 0.1s 间隔）

用法：python -u tools/cloud_money_flow.py --selftest | --codes 600000,000001
"""
import json
import ssl
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = {'User-Agent': 'Mozilla/5.0'}
MAX_WORKERS = 8
GAP = 0.1
W_ORDER, W_VR, W_VOL = 40.0, 30.0, 30.0
ORDER_FULL = 0.15
VR_FULL = 3.0
VR_DUMP = 8.0
VOL_FULL = 0.6
DUMP_CUT = 0.7
SEAL_FULL, SEAL_MID, SEAL_MIN = 0.05, 0.02, 0.01
ZB_CUT = 0.8          # 炸板次数>2 总分 ×0.8
LIMIT_PCT = 9.5       # 涨停判定（10cm/20cm/ST 均覆盖）

_lock = threading.Lock()
_last = [0.0]


def _gate():
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


def _f(f, i):
    try:
        v = f[i]
        return float(v) if v not in ('', None) else None
    except Exception:
        return None


def fetch_quote(code):
    try:
        raw = _get('https://qt.gtimg.cn/q=%s%s' % (_mkt(code), code)).decode('gbk', 'replace')
        f = raw.split('="', 1)[1].rstrip('";\n').split('~')
        if len(f) < 50:
            return None
        return {
            'code': str(code), 'name': f[1], 'price': _f(f, 3), 'prev': _f(f, 4),
            'vol': _f(f, 6), 'outer': _f(f, 7), 'inner': _f(f, 8),
            'bid1': _f(f, 9), 'bid1_vol': _f(f, 10),
            'pct': _f(f, 32), 'turnover': _f(f, 38),
            'float_cap': _f(f, 44), 'limit_price': _f(f, 47), 'vol_ratio': _f(f, 49),
        }
    except Exception as e:
        print('[money_flow] 快照失败 %s: %s' % (code, e))
        return None


def fetch_recent_bars(code, n=6):
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
    if not bars or len(bars) < days + 1:
        return None
    rows = bars[-(days + 1):]
    hit = 0
    for i in range(1, len(rows)):
        if rows[i]['close'] > rows[i - 1]['close'] and rows[i]['vol'] > rows[i - 1]['vol']:
            hit += 1
    return hit / float(days)


def is_limit_up(q):
    """以「现价==涨停价」或涨幅阈值判定；停牌/无价返回 False。"""
    if not q:
        return False
    p, lp = q.get('price'), q.get('limit_price')
    if p and lp and abs(p - lp) < 0.011:
        return True
    return (q.get('pct') or 0) >= LIMIT_PCT


# ---------- 非涨停口径 ----------
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
        return W_VR / 2.0
    if v >= VR_FULL:
        return W_VR
    return W_VR * max(v, 0) / VR_FULL


def _s_vol(r):
    if r is None:
        return None
    return W_VOL * min(r / VOL_FULL, 1.0)


# ---------- 封单口径 ----------
def seal_ratio(q):
    """封单额/流通市值。封单额=买一价×买一量(手)×100；流通市值单位亿。"""
    p, v, cap = q.get('bid1'), q.get('bid1_vol'), q.get('float_cap')
    if not p or not v or not cap:
        return None
    return (p * v * 100.0) / (cap * 1e8)


def _s_seal(r):
    if r is None:
        return None
    if r >= SEAL_FULL:
        return 40.0
    if r >= SEAL_MID:
        return 20.0 + 20.0 * (r - SEAL_MID) / (SEAL_FULL - SEAL_MID)
    if r >= SEAL_MIN:
        return 5.0 + 15.0 * (r - SEAL_MIN) / (SEAL_MID - SEAL_MIN)
    return 5.0


def _s_vr_quality(v):
    if v is None:
        return None
    if v < 1.5:
        return 30.0
    if v < 3.0:
        return 25.0
    if v <= VR_DUMP:
        return 15.0
    return 5.0


def _fold(parts, weights, missing):
    if not parts:
        return None
    wsum = sum(weights[k] for k in parts)
    if wsum <= 0:
        return None
    return 100.0 * sum(parts.values()) / wsum


def score_one(q, bars):
    """返回 {money_score, detail, missing, note}。q=None → 数据不足。"""
    if not q:
        return {'money_score': None, 'detail': {'caliber': None}, 'missing': ['快照'],
                'note': '数据不足：快照拉取失败'}
    v3 = vol_up_ratio(bars)
    vr = q.get('vol_ratio')
    limit_up = is_limit_up(q)
    missing = []
    if limit_up:
        sr = seal_ratio(q)
        parts = {}
        s1 = _s_seal(sr)
        if s1 is None:
            missing.append('封单额/流通市值')
        else:
            parts['seal'] = s1
        s2 = _s_vr_quality(vr)
        if s2 is None:
            missing.append('量比')
        else:
            parts['vr'] = s2
        s3 = _s_vol(v3)
        if s3 is None:
            missing.append('3日放量上涨')
        else:
            parts['vol'] = s3
        w = {'seal': W_ORDER, 'vr': W_VR, 'vol': W_VOL}
        s = _fold(parts, w, missing)
        caliber = '封单口径'
        note = ''
        if missing:
            note = '缺：%s（按可得项折算）' % '/'.join(missing)
        if s is not None and (q.get('zb_times') or 0) > 2:
            s = s * ZB_CUT
            note = (note + '；' if note else '') + '反复开板>2次，总分×0.8'
        return {
            'money_score': None if s is None else round(s, 1),
            'detail': {'caliber': caliber, 'limit_up': True,
                       'seal_ratio': None if sr is None else round(sr, 4),
                       'vol_ratio': vr, 'vol_up_ratio': None if v3 is None else round(v3, 2),
                       'turnover': q.get('turnover'), 'pct': q.get('pct'),
                       'zb_times': q.get('zb_times'), 'dump_suspect': False},
            'missing': missing, 'note': note or '涨停票：成交多记内盘，改用封单口径',
        }
    # ---- 非涨停：内外盘口径 ----
    outer, inner = q.get('outer') or 0, q.get('inner') or 0
    order_ratio = (outer - inner) / float(outer + inner) if (outer + inner) > 0 else None
    parts = {}
    s1 = _s_order(order_ratio)
    if s1 is None:
        missing.append('内外盘差')
    else:
        parts['order'] = s1
    s2 = _s_vr(vr)
    if s2 is None:
        missing.append('量比')
    else:
        parts['vr'] = s2
    s3 = _s_vol(v3)
    if s3 is None:
        missing.append('3日放量上涨')
    else:
        parts['vol'] = s3
    w = {'order': W_ORDER, 'vr': W_VR, 'vol': W_VOL}
    s = _fold(parts, w, missing)
    if s is None:
        return {'money_score': None, 'detail': {'caliber': '内外盘口径', 'limit_up': False},
                'missing': missing, 'note': '数据不足：三项全缺'}
    dump = bool(vr is not None and vr > VR_DUMP and order_ratio is not None and order_ratio < 0)
    if dump:
        s = s * DUMP_CUT
    note = '缺：%s（按可得项折算）' % '/'.join(missing) if missing else ''
    if dump:
        note = (note + '；' if note else '') + '高位放量+外盘弱→出货嫌疑，总分砍30%'
    return {
        'money_score': round(s, 1),
        'detail': {'caliber': '内外盘口径', 'limit_up': False,
                   'outer_ratio': None if order_ratio is None else round(order_ratio, 3),
                   'vol_ratio': vr, 'vol_up_ratio': None if v3 is None else round(v3, 2),
                   'turnover': q.get('turnover'), 'pct': q.get('pct'),
                   'dump_suspect': dump},
        'missing': missing, 'note': note,
    }


def score_codes(codes, workers=MAX_WORKERS):
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

    bars = [{'close': 10, 'vol': 100}, {'close': 11, 'vol': 120},
            {'close': 12, 'vol': 150}, {'close': 12.5, 'vol': 160}]   # 放量上涨 2/3
    bars_flat = [{'close': 10, 'vol': 100}, {'close': 10.2, 'vol': 90},
                 {'close': 9.8, 'vol': 110}, {'close': 9.5, 'vol': 120}]  # 0/3
    # 1 全满（非涨停）：外盘差0.30 / 量比3.5 / 放量2/3 → 100
    q = {'outer': 1300, 'inner': 700, 'vol_ratio': 3.5, 'turnover': 5.0, 'pct': 6.0,
         'price': 10, 'limit_price': 11}
    r = score_one(q, bars)
    ck('非涨停全满→100', r['money_score'] == 100.0 and r['detail']['caliber'] == '内外盘口径', (r['money_score'], r['detail']['caliber']))
    # 2 中档 65
    q2 = {'outer': 1075, 'inner': 925, 'vol_ratio': 1.5, 'pct': 1.0, 'price': 10, 'limit_price': 11}
    r2 = score_one(q2, bars)
    ck('非涨停中档→65', r2['money_score'] == 65.0, r2['money_score'])
    # 3 量比>8 降半 → 85
    q3 = {'outer': 1300, 'inner': 700, 'vol_ratio': 9.0, 'pct': 8.0, 'price': 10, 'limit_price': 11}
    ck('量比>8降半→85', score_one(q3, bars)['money_score'] == 85.0, score_one(q3, bars)['money_score'])
    # 4 出货嫌疑 45→31.5
    q4 = {'outer': 600, 'inner': 1400, 'vol_ratio': 10.0, 'pct': 7.0, 'price': 10, 'limit_price': 11}
    r4 = score_one(q4, bars)
    ck('出货嫌疑砍30%→31.5', r4['money_score'] == 31.5 and r4['detail']['dump_suspect'], r4['money_score'])
    # 5 断网摊权（日K缺）→ 按 40+30 折算 = 100
    r5 = score_one({'outer': 1300, 'inner': 700, 'vol_ratio': 3.5, 'price': 10, 'limit_price': 11}, [])
    ck('断网按可得项折算', r5['money_score'] == 100.0 and '3日放量上涨' in r5['missing'], (r5['money_score'], r5['missing']))
    # 6 全缺 → None
    r6 = score_one({'outer': 0, 'inner': 0, 'vol_ratio': None, 'price': 10, 'limit_price': 11}, [])
    ck('全缺→None', r6['money_score'] is None, r6['money_score'])
    # 7 快照失败
    ck('快照失败→数据不足', score_one(None, [])['money_score'] is None, '')
    # 8 批量隔离
    res = score_codes(['600000', 'ZZZZZZ', '000001'])
    ck('批量隔离失败', len(res) == 3 and any(x['money_score'] is not None for x in res), '')
    # 9 涨停封单口径：封单/流通=6%、量比1.2缩量、放量2/3 → 100 ≥85
    q9 = {'price': 10.0, 'limit_price': 10.0, 'bid1': 10.0, 'bid1_vol': 600000.0,
          'float_cap': 10.0, 'vol_ratio': 1.2, 'pct': 10.0}
    r9 = score_one(q9, bars)
    print('  封单6%缩量板=', r9['money_score'], r9['detail']['caliber'], 'seal=', r9['detail']['seal_ratio'])
    ck('①封单6%缩量板≥85', r9['money_score'] is not None and r9['money_score'] >= 85
       and r9['detail']['caliber'] == '封单口径', r9['money_score'])
    # 10 涨停烂板：封单0.8%(5) + 量比12(5) + 放量0(0) → 10，炸板3次 → 8 ≤50
    q10 = {'price': 10.0, 'limit_price': 10.0, 'bid1': 10.0, 'bid1_vol': 800.0,
           'float_cap': 10.0, 'vol_ratio': 12.0, 'pct': 10.0, 'zb_times': 3}
    r10 = score_one(q10, bars_flat)
    print('  巨量复开烂板=', r10['money_score'], r10['note'])
    ck('②巨量反复开板烂板≤50', r10['money_score'] is not None and r10['money_score'] <= 50, r10['money_score'])
    # 11 涨停票不再被内外盘拖累：外盘=0、封单足量 → 强
    q11 = {'outer': 0, 'inner': 5000, 'price': 10.0, 'limit_price': 10.0, 'bid1': 10.0,
           'bid1_vol': 600000.0, 'float_cap': 10.0, 'vol_ratio': 1.0, 'pct': 10.0}
    ck('③外盘为0不再压分', score_one(q11, bars)['money_score'] >= 85, score_one(q11, bars)['money_score'])
    # 12 封单缺失仍可折算（不编封单分）
    q12 = {'price': 10.0, 'limit_price': 10.0, 'bid1': None, 'bid1_vol': None,
           'float_cap': None, 'vol_ratio': 1.0, 'pct': 10.0}
    r12 = score_one(q12, bars)
    ck('封单缺→按量比+放量折算', r12['money_score'] == 100.0 and '封单额/流通市值' in r12['missing'],
       (r12['money_score'], r12['missing']))
    print('[selftest] money_flow RESULT %s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 5


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(_selftest())
    if '--codes' in sys.argv:
        i = sys.argv.index('--codes')
        codes = sys.argv[i + 1].split(',') if i + 1 < len(sys.argv) else []
        for r in score_codes(codes):
            d = r.get('detail') or {}
            print('%-8s money=%-6s %-6s 封单=%-7s 外盘差=%-7s 量比=%-5s 放量=%-4s %s'
                  % (r.get('code'), r.get('money_score'), d.get('caliber') or '-',
                     d.get('seal_ratio'), d.get('outer_ratio'), d.get('vol_ratio'),
                     d.get('vol_up_ratio'), r.get('note') or ''))
        sys.exit(0)
    print('用法: cloud_money_flow.py --selftest | --codes 600000,000001')
