# -*- coding: utf-8 -*-
"""隔夜外盘→A股题材参考分 overnight_map（工单10）

边界（用户 2026-11-07 定案）：
  - 只出「开盘情绪偏移参考分」，**不进 aggregator、不单独成 engine**；
  - 注入竞价卡「隔夜外盘一句话」段，现有 LLM 文字保留，两者并存；
  - 幅度→参考分换算写在 config/overnight_map.json，首版线性（如 SOXX -3% → 半导体链 -15）；
  - 数据源全挂 → 优雅降级「外盘未接入」，不编数。
数据源：统一腾讯 —— 美股/ETF 用 us 前缀（qt.gtimg.cn），商品用 hf_ 前缀（同一接口）。
  个股/指数字段：f1名 f3现价 f4昨收 f32涨跌 f33涨跌幅%
  商品 hf_ 字段：f0现价 f1涨跌幅% f7昨收 f8今开
日K：proxy.finance.qq.com（含 2011 年杂行，**必须按日期过滤**，见 _clean_k）

用法：
  python -u tools/overnight_map.py --selftest
  python -u tools/overnight_map.py                      # 出今日参考分 + 卡面一句话
  python -u tools/overnight_map.py --replay 20261105,20261103,20261104
"""
import json
import os
import ssl
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG_PATH = os.path.join(ROOT, 'config', 'overnight_map.json')
UA = {'User-Agent': 'Mozilla/5.0'}
MIN_K_DATE = '2015-01-01'      # 早于此视为脏数据（实测返回过 2011 年首行）


def _get(url, timeout=12):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout,
                                  context=ssl._create_unverified_context()).read()


def load_cfg(path=CFG_PATH):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def fetch_quote(sym):
    """腾讯快照。返回 {'sym','name','pct','price','prev'}，失败 None。

    字段口径（实测核对，2026-11-07）：
      美股/ETF：f1名 f3现价 f4昨收 f31涨跌额 **f32涨跌幅%** f33最高 f34最低
                （注意 f33 是最高价，不是涨跌幅——取错会得到"涨"的假象）
      商品 hf_：**逗号分隔**，f0现价 f1涨跌幅% f4最高 f5最低 f7昨收 f8今开 f13名称
    """
    try:
        raw = _get('https://qt.gtimg.cn/q=%s' % sym).decode('gbk', 'replace')
        if 'pv_none_match' in raw:
            print('[overnight] %s 无此标的' % sym)
            return None
        body = raw.split('="', 1)[1].rstrip('";\n')
        if str(sym).startswith('hf_'):
            f = body.split(',')
            if len(f) < 9:
                return None
            return {'sym': sym, 'name': f[13] if len(f) > 13 else sym,
                    'pct': float(f[1]), 'price': float(f[0]),
                    'prev': float(f[7]) if f[7] else None}
        f = body.split('~')
        if len(f) < 36:
            return None
        return {'sym': sym, 'name': f[1], 'pct': float(f[32]), 'price': float(f[3]),
                'prev': float(f[4]) if f[4] else None}
    except Exception as e:
        print('[overnight] 快照失败 %s: %s' % (sym, e))
        return None


def _clean_k(rows, min_date=MIN_K_DATE):
    """按日期过滤脏行：实测腾讯日K会夹 2011 年旧行，不能直接取末尾。"""
    out = [r for r in rows if r.get('date') and r['date'] >= min_date]
    return sorted(out, key=lambda r: r['date'])


def fetch_kline(sym, n=30):
    try:
        d = _get('https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get'
                 '?param=%s,day,,,%d,qfq' % (sym, n)).decode('utf-8', 'replace')
        node = ((json.loads(d).get('data') or {}).get(sym)) or {}
        kl = node.get('day') or node.get('qfqday') or []
        rows = []
        for x in kl:
            if len(x) < 6:
                continue
            rows.append({'date': x[0], 'open': float(x[1]), 'close': float(x[2]),
                         'high': float(x[3]), 'low': float(x[4]), 'vol': float(x[5])})
        return _clean_k(rows)
    except Exception as e:
        print('[overnight] 日K失败 %s: %s' % (sym, e))
        return []


def _pct_on(rows, day):
    """取 day 当日（或之前最近一日）涨跌幅%。"""
    day = str(day).replace('-', '')
    dayk = day[:4] + '-' + day[4:6] + '-' + day[6:8]
    use = [r for r in rows if r['date'] <= dayk]
    if len(use) < 2:
        return None
    cur, prev = use[-1], use[-2]
    if prev['close'] <= 0:
        return None
    return (cur['close'] / prev['close'] - 1) * 100.0


def _score(pct, factor, rng):
    s = pct * factor
    return max(rng[0], min(rng[1], s))


def compute(cfg=None, quote_fn=fetch_quote):
    """返回 {'offsets':{sector:分}, 'details':[{...}], 'ok':bool}"""
    cfg = cfg or load_cfg()
    rng = cfg.get('score_range') or [-40, 40]
    offsets, details, any_ok = {}, [], False
    drops = []
    for rule in cfg.get('rules') or []:
        syms = rule.get('symbols') or []
        quotes = []
        for s in syms:
            q = quote_fn(s)
            if q:
                quotes.append(q)
        if not quotes:
            drops.append('%s(%s)' % (rule.get('label'), '全部取数失败'))
            continue
        any_ok = True
        pct = sum(q['pct'] for q in quotes) / float(len(quotes))
        score = _score(pct, float(rule.get('factor') or 0), rng)
        offsets[rule['sector']] = round(score, 1)
        details.append({'sector': rule['sector'], 'label': rule.get('label'),
                        'pct': round(pct, 2), 'factor': rule.get('factor'),
                        'score': round(score, 1),
                        'proxy': bool(rule.get('note') and '代理' in rule.get('note', ''))})
    return {'offsets': offsets, 'details': details, 'ok': any_ok, 'drops': drops}


def card_line(res):
    """竞价卡「隔夜一句话」：定量参考分。数据全挂 → 外盘未接入。"""
    if not res or not res.get('ok'):
        return '🌙 隔夜外盘：外盘未接入（数据源全部不可用），今日不做外盘参考。'
    parts = []
    for d in res['details']:
        sign = '+' if d['pct'] >= 0 else ''
        parts.append('%s %s%.2f%% → %s %s' % (d['label'], sign, d['pct'], d['sector'],
                                              ('+' if d['score'] >= 0 else '') + ('%.0f' % d['score'])))
    return '🌙 隔夜外盘：' + '｜'.join(parts) + '（参考分，仅作开盘情绪偏移，不构成投资建议）'


def _prev_day(day):
    """A股日 → 前一日（YYYY-MM-DD）。美股夜盘对应 A股当日之前那个自然日的收盘。"""
    import datetime
    d = str(day).replace('-', '')
    dt = datetime.date(int(d[:4]), int(d[4:6]), int(d[6:8])) - datetime.timedelta(days=1)
    return dt.strftime('%Y-%m-%d')


def _snapshot_night():
    """快照即"最新一个美股收盘"（前夜）。返回 (交易日期, 涨跌幅%)，失败 (None,None)。

    腾讯美股日K对个股/ETF 只返回 2011 脏行 + 最新一行（无历史序列），
    因此历史回放里"前夜费半"只能用快照取最近一夜，并在结果里标注来源。
    """
    try:
        raw = _get('https://qt.gtimg.cn/q=usSOXX').decode('gbk', 'replace')
        f = raw.split('="', 1)[1].rstrip('";\n').split('~')
        return f[30][:10], float(f[32])
    except Exception:
        return None, None


def replay(dates):
    """历史日回放：外盘**前夜**涨跌 vs 同日 A股半导体ETF 方向，人工核对用。

    每行标注 soxx_from：'kline'（日K序列）/ 'snapshot'（仅能取最新一夜）/ None（不可得）。
    """
    us = {'usSOXX': fetch_kline('usSOXX', 320), 'usNDX': fetch_kline('usNDX', 120)}
    a_etf = fetch_kline('sh512480', 120)
    a_bench = fetch_kline('sh000300', 120)
    snap_date, snap_pct = _snapshot_night()
    rows = []
    for d in dates:
        day = str(d).replace('-', '')
        cutoff = _prev_day(day)
        src = None
        soxx = None
        if len([r for r in us['usSOXX'] if r['date'] <= cutoff]) >= 2:
            soxx = _pct_on([r for r in us['usSOXX'] if r['date'] <= cutoff], day)
            src = 'kline' if soxx is not None else None
        elif snap_date is not None and snap_date <= cutoff:
            soxx, src = snap_pct, 'snapshot'
        ndx = _pct_on([r for r in us['usNDX'] if r['date'] <= cutoff], day)
        etf = _pct_on(a_etf, day)
        bench = _pct_on(a_bench, day)
        same = None
        if soxx is not None and etf is not None:
            same = (soxx > 0) == (etf > 0)
        ndx_same = None
        if ndx is not None and etf is not None:
            ndx_same = (ndx > 0) == (etf > 0)
        rows.append({'date': day, 'us_night_cutoff': cutoff,
                     'soxx_pct': None if soxx is None else round(soxx, 2), 'soxx_from': src,
                     'ndx_pct': None if ndx is None else round(ndx, 2),
                     'a_semi_etf_pct': None if etf is None else round(etf, 2),
                     'a_hs300_pct': None if bench is None else round(bench, 2),
                     'same_direction': same, 'ndx_same_direction': ndx_same})
    return rows


def _selftest():
    ok = True

    def ck(name, cond, got=''):
        nonlocal ok
        print(('PASS ' if cond else 'FAIL ') + name + ('  ' + str(got) if got else ''))
        if not cond:
            ok = False

    # 1. 线性映射：SOXX -3% → 半导体链 -15
    cfg = load_cfg()
    ck('配置5条映射', len(cfg['rules']) == 5, len(cfg['rules']))
    ck('SOXX -3%→-15', _score(-3.0, 5.0, [-40, 40]) == -15.0, _score(-3.0, 5.0, [-40, 40]))
    ck('纳指 -5.5%→-19.3', abs(_score(-5.52, 3.5, [-40, 40]) + 19.3) < 0.1, _score(-5.52, 3.5, [-40, 40]))
    ck('极端值被夹到±40', _score(-30.0, 5.0, [-40, 40]) == -40.0, _score(-30.0, 5.0, [-40, 40]))
    # 2. 日K 脏行过滤（回归断言）：构造含 2011 行的数据，过滤后不含 2011
    dirty = [{'date': '2011-06-02', 'close': 346, 'open': 1, 'high': 1, 'low': 1, 'vol': 1},
             {'date': '2026-11-04', 'close': 350, 'open': 1, 'high': 1, 'low': 1, 'vol': 1},
             {'date': '2026-11-05', 'close': 344, 'open': 1, 'high': 1, 'low': 1, 'vol': 1}]
    cleaned = _clean_k(dirty)
    print('  cleaned dates=', [x['date'] for x in cleaned])
    ck('过滤2011脏行', all(x['date'] >= MIN_K_DATE for x in cleaned) and len(cleaned) == 2, cleaned)
    ck('过滤后仍按日期升序', [x['date'] for x in cleaned] == ['2026-11-04', '2026-11-05'], cleaned)
    # 3. 全挂 → 外盘未接入
    res = compute(quote_fn=lambda s: None)
    print('  ', card_line(res))
    ck('全挂优雅降级', res['ok'] is False and '外盘未接入' in card_line(res), card_line(res))
    ck('全挂不编参考分', res['offsets'] == {}, res['offsets'])
    # 4. 部分挂：只有 SOXX 取到 → 只出半导体一条，其余记入 drops
    fake = {'usSOXX': {'sym': 'usSOXX', 'name': 'SOXX', 'pct': -3.0, 'price': 131.9, 'prev': 136.0}}
    r2 = compute(quote_fn=lambda s: fake.get(s))
    print('  ', card_line(r2))
    ck('部分可用仍出分', abs(r2['offsets'].get('半导体/存储', 0) + 15.0) < 0.1, r2['offsets'])
    ck('缺失项记入drops', len(r2['drops']) == 4, r2['drops'])
    ck('代理标注', r2['details'][0]['proxy'] is True, r2['details'][0])
    # 5. 三只均值聚合（AI应用/传媒）
    fake2 = {'usAAPL': {'pct': -2.0}, 'usNVDA': {'pct': -4.0}, 'usTSLA': {'pct': -6.0}}
    r3 = compute(quote_fn=lambda s: fake2.get(s))
    print('  AI均值 ->', r3['offsets'].get('AI应用/传媒'))
    ck('三只均值-4%→-8', abs(r3['offsets'].get('AI应用/传媒', 0) + 8.0) < 0.1,
       r3['offsets'].get('AI应用/传媒'))
    # 6. 卡面文案：无问号、含参考分口径声明
    line = card_line(r2)
    ck('卡面无问号且带免责', '？' not in line and '?' not in line and '不构成投资建议' in line, line)
    # 7. 真实数据：直接用实测行情核对解析口径（美股 f32 / 商品逗号分隔）
    soxx = fetch_quote('usSOXX')
    cl = fetch_quote('hf_CL')
    if soxx is not None:
        print('  live usSOXX =', soxx)
        ck('美股 pct 取自 f32（非最高价）', abs(soxx['pct']) < 30 and soxx['pct'] != soxx['price'], soxx['pct'])
    if cl is not None:
        print('  live hf_CL =', cl)
        ck('商品逗号分隔解析成功', cl['pct'] is not None and cl['name'].startswith('纽约'), cl)
    live = compute()
    print('  live offsets=', live['offsets'], 'drops=', live['drops'])
    ck('实时映射可出分或可降级', live['ok'] or '外盘未接入' in card_line(live), live['ok'])
    # 8. 方向一致性：外盘跌 → 参考分必须为负（防"取错列变成涨"的回归）
    for sec, sc in (live['offsets'] or {}).items():
        d = next(x for x in live['details'] if x['sector'] == sec)
        ck('%s 参考分方向与涨跌一致' % sec, (d['pct'] > 0) == (sc > 0) or d['pct'] == 0, (d['pct'], sc))
    print('[selftest] overnight_map RESULT %s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 7


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(_selftest())
    if '--replay' in sys.argv:
        i = sys.argv.index('--replay')
        dates = sys.argv[i + 1].split(',') if i + 1 < len(sys.argv) else []
        for r in replay(dates):
            print(r)
        sys.exit(0)
    res = compute()
    print(card_line(res))
    if res['drops']:
        print('  降级项:', res['drops'])
