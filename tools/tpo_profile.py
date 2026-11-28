# -*- coding: utf-8 -*-
"""四度空间 TPO / 市场轮廓（Market Profile）计算与卡片渲染。

口径（写死在代码里，卡面只出算出数的量，缺数据不编）：
  时间维度：1 分钟一格 TPO（A 股连续竞价 240 分钟）。
  价格维度：把当日最高-最低按自适应桶宽切分（约 25 个桶，最小 0.01）。
  成交量分布：每分钟收盘价落桶，累加该分钟成交量 -> 价格-成交量轮廓。
  POC：成交量最大的桶中心价（同时给 TPO 计数口径的 POC 做交叉核对）。
  价值区 VA：从 POC 向两侧扩桶，累计成交量 >=70% 时止，上沿 VAH、下沿 VAL。
  初始平衡 IB：09:30-10:00 的最高/最低（IBH/IBL）。
  真空带（单印近似）：连续 >=2 个桶全天分钟数 <=2（价格被快速穿越，多为加速或缺口区）。
  结构分类：趋势日 / 平衡日 / 双分布（两个峰之间有明显低谷）。
  价值迁移：与前一交易日 VA 的重叠比例 -> 上移 / 下移 / 重叠。

数据源（都取真实，不伪造）：
  1) 腾讯 minute/query：当日 1 分钟（vm 与云端均通，生产已在用 qt.gtimg.cn）
  2) 东财 trends2：近 N 日 1 分钟（云端可用，vm 不通则自动落回腾讯）
"""
import json
import math
import sys
import time
import urllib.request

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
GOLD, RED, GREEN, GREY, PUR = '#ffd43b', '#ff6b6b', '#51cf66', '#8b93a7', '#b197fc'
CARD_BG, SEC_BG = '#161b26', '#232a3a'


def _http(url, timeout=15, tries=2):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=timeout).read().decode('utf-8', 'replace')
        except Exception as e:
            last = e
            time.sleep(0.8 + i)
    raise last


def _sym(code):
    c = str(code).strip().lower()
    if c.startswith(('sh', 'sz', 'bj')):
        return c
    return ('sh' if c.startswith('6') else 'sz') + c


def fetch_tencent(code):
    """当日 1 分钟：{'date': '2026-11-27', 'preclose': float, 'bars': [(hhmm, px, vol)]}"""
    sym = _sym(code)
    d = json.loads(_http('https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=%s' % sym))
    node = (d.get('data') or {}).get(sym) or {}
    inner = node.get('data') or {}
    raw = inner.get('data') or []
    ds = str(inner.get('date') or '')
    date = '%s-%s-%s' % (ds[:4], ds[4:6], ds[6:8]) if len(ds) == 8 else ''
    bars = []
    for row in raw:
        p = str(row).split()
        if len(p) < 3:
            continue
        t, px, vol = p[0], float(p[1]), float(p[2])
        if not ('0930' <= t <= '1500'):
            continue
        if px <= 0:
            continue
        bars.append((t, px, vol))
    # 15:30 收盘快照可能与 15:00 重复，去重
    seen, out = set(), []
    for b in bars:
        if b[0] in seen:
            continue
        seen.add(b[0])
        out.append(b)
    pc = None
    try:
        q = _http('http://qt.gtimg.cn/q=%s' % sym).split('~')
        pc = float(q[4]) if len(q) > 50 and float(q[4] or 0) > 0 else None
    except Exception:
        pc = None
    return {'date': date, 'preclose': pc, 'bars': out}


def fetch_em(code, ndays=4):
    """东财近 N 日 1 分钟：{'2026-11-27': [(hhmm, px, vol)], ...}"""
    sym = _sym(code)
    secid = ('1.' if sym.startswith('sh') else '0.') + sym[2:]
    u = ('https://push2his.eastmoney.com/api/qt/stock/trends2/get?secid=%s'
         '&fields1=f1,f2,f3,f4,f5,f6,f7,f8&fields2=f51,f52,f53,f54,f55,f56,f57,f58'
         '&iscr=0&ndays=%d' % (secid, ndays))
    d = json.loads(_http(u))
    data = (d.get('data') or {})
    prev = float(data.get('preClose') or 0)
    rows = data.get('trends') or []
    days = {}
    for r in rows:
        p = str(r).split(',')
        if len(p) < 6:
            continue
        dt, px, vol = p[0], float(p[2] or 0), float(p[5] or 0)
        date, tm = dt.split(' ')[0], dt.split(' ')[1].replace(':', '')
        if px <= 0 or not ('0930' <= tm <= '1500'):
            continue
        days.setdefault(date, []).append((tm, px, vol))
    return {'days': days, 'preclose': prev or None}


def quote(code):
    """qt.gtimg.cn 快照：{'price','preclose','high','low'}，用来交叉校验分时源对不对。"""
    sym = _sym(code)
    q = _http('http://qt.gtimg.cn/q=%s' % sym).split('~')
    if len(q) < 35:
        return {}
    try:
        d = {'price': float(q[3]), 'preclose': float(q[4]), 'high': float(q[33]), 'low': float(q[34])}
    except Exception:
        return {}
    if d['price'] <= 0:
        return {}
    return d


def _bucket(lo, hi):
    rng = max(hi - lo, 0.01)
    b = rng / 25.0
    if b >= 1:
        b = round(b)
    elif b >= 0.1:
        b = round(b, 1)
    else:
        b = max(0.01, round(b, 2))
    return max(b, 0.01)


def profile(bars, preclose=None):
    """返回轮廓字典；bars=[(hhmm, px, vol)]，至少 10 格才计算。"""
    if not bars or len(bars) < 10:
        return {}
    px = [b[1] for b in bars]
    lo, hi = min(px), max(px)
    bk = _bucket(lo, hi)
    n = int(math.ceil((hi - lo) / bk)) + 1
    base = math.floor(lo / bk) * bk
    vol = [0.0] * n
    cnt = [0] * n
    for _, p, v in bars:
        i = min(max(int((p - base) // bk), 0), n - 1)
        vol[i] += max(v, 0.0)
        cnt[i] += 1
    tot_v = sum(vol) or 1.0
    tot_c = sum(cnt) or 1
    poc_i = max(range(n), key=lambda i: (vol[i], cnt[i]))
    tpo_poc_i = max(range(n), key=lambda i: cnt[i])

    def center(i):
        return base + (i + 0.5) * bk

    # VA70：从 POC 向两侧扩，比较下一桶两侧成交量谁大先扩谁
    acc = vol[poc_i]
    lo_i = hi_i = poc_i
    while acc < tot_v * 0.7 and (lo_i > 0 or hi_i < n - 1):
        dl = vol[lo_i - 1] if lo_i > 0 else -1
        dh = vol[hi_i + 1] if hi_i < n - 1 else -1
        if dh >= dl:
            hi_i += 1
            acc += max(dh, 0)
        else:
            lo_i -= 1
            acc += max(dl, 0)
    val, vah = base + lo_i * bk, base + (hi_i + 1) * bk

    # IB：前 30 分钟
    ib = [b for b in bars if b[0] <= '1000']
    ibh = max(b[1] for b in ib) if ib else None
    ibl = min(b[1] for b in ib) if ib else None

    # 真空带：连续 >=2 桶、分钟数 <=2
    gaps, run = [], []
    for i in range(n):
        if cnt[i] <= 2 and i > 0 and i < n - 1:
            run.append(i)
        else:
            if len(run) >= 2:
                gaps.append((run[0], run[-1]))
            run = []
    if len(run) >= 2:
        gaps.append((run[0], run[-1]))

    close = bars[-1][1]
    rng = hi - lo
    # 结构：双分布检测（POC 两侧各有一个 >=60% POC 量的峰，且中间低谷 <30%）
    sec_peaks = []
    for i in range(n):
        if vol[i] >= vol[poc_i] * 0.60 and 0 < i < n - 1 and vol[i] >= vol[i - 1] and vol[i] >= vol[i + 1]:
            sec_peaks.append(i)
    dbl = False
    for i in sec_peaks:
        if abs(i - poc_i) >= 3:
            a, b_ = min(i, poc_i), max(i, poc_i)
            if min(vol[a + 1:b_]) < vol[poc_i] * 0.30:
                dbl = True
                break
    op = bars[0][1]
    near_hi = (hi - close) <= bk * 0.8
    near_lo = (close - lo) <= bk * 0.8
    if dbl and not (near_hi or near_lo):
        struct = '双分布'
    elif near_hi and close >= op and (hi - lo) >= bk * 6:
        struct = '上涨趋势日'
    elif near_lo and close <= op and (hi - lo) >= bk * 6:
        struct = '下跌趋势日'
    elif close >= val and close <= vah and (vah - val) >= max((ibh - ibl) * 1.2 if ibh and ibl else 0, bk * 4):
        struct = '平衡日'
    else:
        struct = '偏斜日'
    return {
        'bars_n': len(bars), 'poc': round(center(poc_i), 2), 'poc_tpo': round(center(tpo_poc_i), 2),
        'vah': round(vah, 2), 'val': round(val, 2), 'hi': round(hi, 2), 'lo': round(lo, 2),
        'ibh': round(ibh, 2) if ibh else None, 'ibl': round(ibl, 2) if ibl else None,
        'close': round(close, 2), 'bucket': bk, 'struct': struct, 'dbl': dbl,
        'gaps': [(round(center(a), 2), round(center(b_), 2)) for a, b_ in gaps[:3]],
        'va_pct': round((vah - val) / close * 100, 2) if close else None,
        'poc_share': round(vol[poc_i] / tot_v * 100, 1),
        'va_share': round(acc / tot_v * 100, 1),
    }


def migrate(now_p, prev_p):
    """价值迁移：与上一交易日 VA 的重叠比例。"""
    if not now_p or not prev_p:
        return {}
    a1, b1 = now_p['val'], now_p['vah']
    a2, b2 = prev_p['val'], prev_p['vah']
    ov = max(0.0, min(b1, b2) - max(a1, a2))
    span = max(b1 - a1, b2 - a2) or 1.0
    ratio = ov / span
    mid1, mid2 = (a1 + b1) / 2, (a2 + b2) / 2
    if ratio >= 0.7:
        tag = '价值区基本重叠'
    elif mid1 > mid2:
        tag = '价值上移'
    else:
        tag = '价值下移'
    return {'ratio': round(ratio * 100), 'tag': tag, 'dmid': round(mid1 - mid2, 2)}


def verdict(kind, price, prof, mig=None):
    """把结构翻成位置口径：只给点位与条件。kind: idx=指数 / hold=持仓 / stock=候选"""
    if not prof:
        return None
    poc, vah, val = prof['poc'], prof['vah'], prof['val']
    st = prof.get('struct') or ''
    head = []
    if price > vah:
        head.append('站在 VAH %.2f 上方' % vah)
    elif price < val:
        head.append('掉到 VAL %.2f 下方' % val)
    else:
        head.append('还在 %.2f-%.2f 的价值区里' % (val, vah))
    # 结构一句话（按真实分类出，不套统一句）
    if st == '上涨趋势日':
        head.append('单边拉升，成交重心被抬到 %.2f' % poc)
    elif st == '下跌趋势日':
        head.append('单边下压，成交重心压在 %.2f' % poc)
    elif st == '双分布':
        head.append('两段成交分开，中间那段没人接')
    elif st == '平衡日':
        head.append('区间来回，谁也没把谁打穿')
    else:
        head.append('方向偏斜但没走成单边')
    if mig and mig.get('tag'):
        _unit = '点' if kind == 'idx' else '元'
        _dm = mig.get('dmid', 0.0)
        if mig.get('ratio', 0) <= 5:
            head.append('%s %.2f%s，和昨天基本不重叠' % (mig['tag'], _dm, _unit))
        else:
            head.append('%s %.2f%s，重叠 %d%%' % (mig['tag'], _dm, _unit, mig['ratio']))
    above, inside, below = price > vah, (val <= price <= vah), price < val
    if kind == 'idx':
        if above:
            act = '明天守住 %.2f 就还是价值上移，跌回 %.2f（POC）就是震荡' % (vah, poc)
        elif below:
            act = '明天收不回 %.2f 就还是弱，别把反抽当反转' % val
        else:
            act = '明天站上 %.2f 才算上移，掉回 %.2f（POC）下方就是震荡' % (vah, poc)
    elif kind == 'hold':
        if above:
            act = '回踩 %.2f 是低吸带；做T 摸 %.2f 减、回 %.2f 补' % (vah, vah, poc)
        elif below:
            act = '反抽 %.2f 不过就是弱势，别补仓，按纪律价处理' % val
        else:
            act = '区间做T：摸 %.2f 减、回 %.2f 补；两边都不破就别动' % (vah, val)
    else:
        if above:
            act = '回踩 %.2f 不破才接，追高不给' % vah
        elif below:
            act = '反抽 %.2f 不过就还是弱，别在这里接' % val
        else:
            act = '只在 %.2f 附近接，冲 %.2f 不追' % (val, vah)
    return {'head': '｜'.join(head), 'act': act}


def html_block(items, title='📐 四度空间·TPO', sub='时间×价格×成交量，一天只看三个数'):
    """items=[{'name','price','prof','mig','note'}...] -> 深色卡片段落 HTML"""
    rows = []
    for it in items:
        p, prof, mig = it.get('price'), it.get('prof'), it.get('mig') or {}
        if not prof:
            continue
        c = RED if (p or 0) >= (prof['close'] or 0) else GREEN
        v = verdict(it.get('kind') or 'stock', p or prof['close'], prof, mig)
        gapline = ''
        if prof.get('gaps'):
            g0 = prof['gaps'][0]
            gapline = ("<div style=\"font-size:10.5px;color:%s;margin-top:2px;\">"
                       "真空带 %.2f-%.2f（快速穿越，回踩容易加速）</div>" % (GREY, g0[0], g0[1]))
        extra = ''
        if it.get('note'):
            extra = ("<div style=\"font-size:10.5px;color:%s;margin-top:2px;\">%s</div>"
                     % (GREY, it['note']))
        rows.append(
            "<div style=\"margin-top:7px;padding:7px 9px;background:#1c2230;border-radius:8px;\">"
            "<div style=\"font-size:12.5px;font-weight:800;color:#e9ecef;\">%s "
            "<span style=\"color:%s;\">%.2f</span>"
            "<span style=\"color:%s;font-size:10.5px;font-weight:400;\">　%s</span></div>"
            "<div style=\"font-size:14px;margin-top:3px;color:#e9ecef;\">"
            "POC <b style=\"color:%s;\">%.2f</b>　VAH <b style=\"color:%s;\">%.2f</b>　VAL <b style=\"color:%s;\">%.2f</b></div>"
            "<div style=\"font-size:11px;color:#ced4da;margin-top:3px;\">%s</div>"
            "<div style=\"font-size:11px;color:%s;margin-top:2px;\">怎么做：%s</div>"
            "%s%s</div>"
            % (it['name'], c, p or prof['close'], GREY, prof['struct'],
               GOLD, prof['poc'], RED, prof['vah'], GREEN, prof['val'],
               v['head'], GOLD, v['act'], gapline, extra))
    if not rows:
        return ''
    return ("<div style=\"margin-top:10px;padding:10px 11px;background:%s;border-radius:10px;"
            "border-left:4px solid %s;\">"
            "<div style=\"font-size:15px;font-weight:800;color:%s;\">%s</div>"
            "<div style=\"font-size:10.5px;color:%s;margin-top:2px;\">%s"
            "<span style=\"color:#6b7280;\">｜POC 成交最密价 · VAH/VAL 价值区上下沿 · 跌破下沿=结构变了</span></div>"
            "%s</div>" % (SEC_BG, GOLD, GOLD, title, GREY, sub, ''.join(rows)))


def analyze(code, name, price=None, ndays=4):
    """单品：腾讯/东财两源都取，用实时快照校验收盘与高低点，选对得上的那个；对不上就不出。"""
    q = quote(code)
    cands = []
    try:
        tc = fetch_tencent(code)
        if tc.get('bars'):
            cands.append(('tx', tc['bars'], tc.get('date') or ''))
    except Exception as e:
        print('[tpo] tx fail %s: %r' % (code, e), file=sys.stderr)
    em_prev = None
    try:
        em = fetch_em(code, ndays)
        days = sorted(em.get('days') or {})
        if days:
            cands.append(('em', em['days'][days[-1]], days[-1]))
            if len(days) >= 2:
                em_prev = (em['days'][days[-2]], days[-2])
    except Exception as e:
        print('[tpo] em fail %s: %r' % (code, e), file=sys.stderr)
    prof, date, src = {}, '', ''
    for tag, bars, d in cands:
        pf = profile(bars, q.get('preclose'))
        if not pf:
            continue
        if q and abs(pf['close'] - q['price']) > max(0.02, q['price'] * 0.003):
            continue
        # 分时的极值由分钟收盘价构成，与真实最高/最低天然有小差，只拦「半天数据」
        if q and (pf['hi'] > q['high'] + max(0.03, q['high'] * 0.01)
                  or pf['lo'] < q['low'] - max(0.03, q['low'] * 0.01)
                  or pf['hi'] < q['high'] - max(0.05, q['high'] * 0.015)
                  or pf['lo'] > q['low'] + max(0.05, q['low'] * 0.015)):
            print('[tpo] %s %s 高低点对不上快照 %.2f/%.2f vs %.2f/%.2f，弃用'
                  % (code, tag, pf['hi'], pf['lo'], q['high'], q['low']), file=sys.stderr)
            continue
        prof, date, src = pf, d, tag
        break
    if not prof:
        return {}
    mig = {}
    if em_prev:
        pp = profile(em_prev[0], None)
        if pp and q and abs(pp['close'] - q.get('preclose', 0)) <= max(0.02, q.get('preclose', 1) * 0.003):
            mig = migrate(prof, pp)
    return {'name': name, 'price': price if price is not None else prof['close'],
            'prof': prof, 'mig': mig, 'date': date, 'src': src}


def section_html(codes=None, title='📐 四度空间·TPO'):
    """云端接入点：codes=[(code,name,price)]；默认上证 + 两只持仓。失败返回空串。"""
    if codes is None:
        codes = [('sh000001', '上证', None, 'idx'),
                 ('sz002838', '道恩股份', None, 'hold'),
                 ('sz000811', '冰轮环境', None, 'hold')]
    items = []
    for row in codes:
        c, n, p = row[0], row[1], row[2]
        kind = row[3] if len(row) > 3 else 'stock'
        a = analyze(c, n, p)
        if a:
            a['kind'] = kind
            items.append(a)
    if not items:
        return ''
    return html_block(items, title=title)


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        for c, n in (('sz002838', '道恩股份'), ('sz000811', '冰轮环境'), ('sh000001', '上证')):
            a = analyze(c, n)
            if not a:
                print(c, 'NO DATA')
                continue
            p = a['prof']
            print('%-6s %s 收%.2f POC%.2f(TPO%.2f) VAH%.2f VAL%.2f 桶%.2f %s VA覆盖%.0f%% POC占%.1f%% IB %s-%s gaps=%s mig=%s'
                  % (n, a['date'], p['close'], p['poc'], p['poc_tpo'], p['vah'], p['val'], p['bucket'],
                     p['struct'], p['va_share'], p['poc_share'], p['ibl'], p['ibh'], p['gaps'], a['mig']))
        print('--- html len', len(section_html()))
    else:
        print(section_html())
