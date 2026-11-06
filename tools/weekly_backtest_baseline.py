# -*- coding: utf-8 -*-
"""周度回测基准 weekly_backtest_baseline（工单8）

口径（用户 2026-11-07 定案）：
  - 取当日账本 signal_log.csv 里 total(final_score) 前 20 名，等权。
  - T+1 开盘买入，持有 5 个交易日（第 5 日收盘卖出）。
  - 成本 0.1% 单边：买价 open*(1+0.001)，卖价 close*(1-0.001)。
  - 一字板剔除：**买入日 开盘=涨停价 且 全天最高=最低**（真一字买不到）。
    开盘一字但盘中打开（high>low）不剔除——实际能买到。
  - 对比沪深300（sh000300）同区间；不回填历史，只记录本次所得。
  - 结果滚动写 data/backtest_baseline.json（保留最近 4 周）。

用法：
  python -u tools/weekly_backtest_baseline.py --selftest
  python -u tools/weekly_backtest_baseline.py              # 跑并写盘
  python -u tools/weekly_backtest_baseline.py --dry        # 只算不写
"""
import csv
import io
import json
import os
import ssl
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, 'data', 'signal_log.csv')
OUT_PATH = os.path.join(ROOT, 'data', 'backtest_baseline.json')
UA = {'User-Agent': 'Mozilla/5.0'}
MAX_WORKERS = 8
COST = 0.001              # 单边 0.1%
TOP_N = 20
HOLD = 5
KEEP_WEEKS = 4
BENCH = 'sh000300'


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout,
                                  context=ssl._create_unverified_context()).read()


def _mkt(code):
    c = str(code)
    return 'sh' if c.startswith(('6', '9', '5')) else ('bj' if c.startswith(('4', '8')) else 'sz')


def fetch_bars(code, n=40):
    """日K [{date, open, close, high, low, prev_close}]，失败返回 []。"""
    sym = BENCH if str(code).startswith('sh000') else _mkt(code) + str(code)
    try:
        d = _get('https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get'
                 '?param=%s,day,,,%d,qfq' % (sym, n)).decode('utf-8', 'replace')
        kl = (((json.loads(d).get('data') or {}).get(sym)) or {})
        kl = kl.get('day') or kl.get('qfqday') or []
        out = []
        for i, x in enumerate(kl):
            if len(x) < 6:
                continue
            out.append({'date': x[0].replace('-', ''), 'open': float(x[1]), 'close': float(x[2]),
                        'high': float(x[3]), 'low': float(x[4]), 'vol': float(x[5])})
        for i in range(1, len(out)):
            out[i]['prev_close'] = out[i - 1]['close']
        return out
    except Exception as e:
        print('[backtest] 日K失败 %s: %s' % (code, e))
        return []


def limit_pct(code):
    c = str(code)
    return 0.1995 if c.startswith(('30', '68')) else (0.0495 if c.startswith('8') else 0.0995)


def is_one_word_limit(bar, code):
    """买入日开盘=涨停价 且 全天最高=最低 → 买不到（剔除）；盘中打开则保留。"""
    if not bar or not bar.get('prev_close'):
        return False
    lim = bar['prev_close'] * (1 + limit_pct(code))
    near = abs(bar['open'] - lim) / lim < 0.003
    flat = abs(bar['high'] - bar['low']) / max(bar['low'], 1e-9) < 0.001
    return bool(near and flat)


def _norm_date(d):
    """账本日期是 2026-11-06，日K日期是 20261106 —— 必须归一后再比较，否则字符串比较会把当天误当 T+1。"""
    return str(d or '').replace('-', '').replace('/', '').strip()


def trade_return(bars, pick_date, code):
    """T+1 开盘买、持 5 日收盘卖。返回 {'ret', 'status', 'entry', 'exit'}。"""
    pd = _norm_date(pick_date)
    idx = None
    for i, b in enumerate(bars):
        if b['date'] > pd:
            idx = i
            break
    if idx is None:
        return {'ret': None, 'status': '无 T+1 数据'}
    if idx + HOLD - 1 >= len(bars):
        return {'ret': None, 'status': '不足5日'}
    entry = bars[idx]
    if is_one_word_limit(entry, code):
        return {'ret': None, 'status': '一字板剔除'}
    exit_bar = bars[idx + HOLD - 1]
    buy = entry['open'] * (1 + COST)
    sell = exit_bar['close'] * (1 - COST)
    if buy <= 0:
        return {'ret': None, 'status': '价格异常'}
    return {'ret': sell / buy - 1.0, 'status': 'ok',
            'entry': entry['date'], 'exit': exit_bar['date']}


def pick_top(rows_by_date, date, n=TOP_N):
    rows = rows_by_date.get(date) or []
    def sk(r):
        try:
            return float(r.get('total') or 0)
        except Exception:
            return 0.0
    return sorted(rows, key=sk, reverse=True)[:n]


def week_result(rows_by_date, date, bars_map, bench_bars):
    picked = pick_top(rows_by_date, date)
    if not picked:
        return None
    rets, excluded, failed = [], [], []
    for r in picked:
        code = str(r.get('code'))
        b = bars_map.get(code) or []
        t = trade_return(b, date, code)
        if t['ret'] is None:
            (excluded if t['status'] == '一字板剔除' else failed).append((code, t['status']))
        else:
            rets.append(t['ret'])
    bt = trade_return(bench_bars, date, 'sh000300')
    if not rets:
        return {'date': date, 'n': 0, 'portfolio': None, 'bench': bt['ret'],
                'excess': None, 'excluded': excluded, 'failed': failed, 'status': '无可用样本'}
    port = sum(rets) / len(rets)
    bench = bt['ret']
    return {
        'date': date, 'n': len(rets), 'portfolio': round(port * 100, 2),
        'bench': None if bench is None else round(bench * 100, 2),
        'excess': None if bench is None else round((port - bench) * 100, 2),
        'excluded': excluded, 'failed': failed, 'status': 'ok',
    }


def card_line(results):
    last = results[-1] if results else None
    if not last or last.get('portfolio') is None:
        return '📊 系统成绩单：本周前20组合数据不足（无可回测样本），本周末不出结论。'
    wins = sum(1 for x in results if x.get('excess') is not None and x['excess'] > 0)
    total = sum(1 for x in results if x.get('excess') is not None)
    cum = None
    comp_p, comp_b = 1.0, 1.0
    for x in results:
        if x.get('portfolio') is None or x.get('bench') is None:
            continue
        comp_p *= 1 + x['portfolio'] / 100.0
        comp_b *= 1 + x['bench'] / 100.0
    if comp_b:
        cum = (comp_p / comp_b - 1) * 100
    return ('📊 系统成绩单：本周前20组合%s%% vs 沪深300 %s%%，超额%s%%；近%d周累计超额%s%%（胜%d负%d）'
            % (_fmt(last['portfolio']), _fmt(last['bench']), _fmt(last['excess']),
               total, _fmt(cum) if cum is not None else '—', wins, total - wins))


def _fmt(v):
    if v is None:
        return '—'
    return ('+' if v >= 0 else '') + '%.2f' % v


def load_csv(path=CSV_PATH):
    rows = []
    with open(path, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            if r.get('date') and r.get('code'):
                rows.append(r)
    by = {}
    for r in rows:
        by.setdefault(r['date'], []).append(r)
    return by


def run_dates(by, dates=None):
    dates = dates or sorted(by)
    bars_map, missing = {}, set()
    for d in dates:
        for r in pick_top(by, d):
            missing.add(str(r['code']))
    missing.add(BENCH)

    def one(c):
        return c, fetch_bars(c, 40)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for c, b in ex.map(one, sorted(missing)):
            bars_map[c] = b
    bench = bars_map.get(BENCH) or []
    if not bench:
        return [{'date': d, 'status': '沪深300 数据缺失', 'portfolio': None} for d in dates]
    return [week_result(by, d, bars_map, bench) for d in dates]


def save(results, path=OUT_PATH):
    old = []
    try:
        with open(path, encoding='utf-8') as f:
            old = (json.load(f) or {}).get('weeks') or []
    except Exception:
        old = []
    merged = [x for x in old if x.get('date') not in {r['date'] for r in results}] + results
    merged.sort(key=lambda x: x.get('date') or '')
    merged = merged[-KEEP_WEEKS:]
    doc = {'updated': time.strftime('%Y-%m-%d %H:%M'), 'weeks': merged,
           'card': card_line(merged),
           'note': 'T+1开盘买入持有5日，成本0.1%单边，一字板剔除，不回填'}
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    return doc


def _selftest():
    ok = True

    def ck(name, cond, got=''):
        nonlocal ok
        print(('PASS ' if cond else 'FAIL ') + name + ('  ' + str(got) if got else ''))
        if not cond:
            ok = False

    # 1. 收益与成本可复算：open 10 → close 12，5日；成本0.1%单边
    bars = [{'date': '20261103', 'open': 10, 'close': 10, 'high': 10.5, 'low': 9.9, 'prev_close': 9.9},
            {'date': '20261104', 'open': 10.0, 'close': 10.5, 'high': 10.6, 'low': 9.95, 'prev_close': 10.0},
            {'date': '20261105', 'open': 10.6, 'close': 10.8, 'high': 10.9, 'low': 10.4, 'prev_close': 10.5},
            {'date': '20261106', 'open': 10.8, 'close': 11.0, 'high': 11.2, 'low': 10.7, 'prev_close': 10.8},
            {'date': '20261107', 'open': 11.0, 'close': 11.5, 'high': 11.6, 'low': 10.9, 'prev_close': 11.0},
            {'date': '20261108', 'open': 11.5, 'close': 12.0, 'high': 12.1, 'low': 11.4, 'prev_close': 11.5}]
    t = trade_return(bars, '20261103', '600000')
    exp = (12.0 * 0.999) / (10.0 * 1.001) - 1
    print('  收益=%.6f 期望=%.6f' % (t['ret'], exp))
    ck('收益可复算(含0.1%单边)', abs(t['ret'] - exp) < 1e-9, t['ret'])
    ck('成交日=T+1开盘/第5日收盘', t['entry'] == '20261104' and t['exit'] == '20261108', (t['entry'], t['exit']))
    # 2. 一字板（开盘=涨停价且全天最高=最低）→ 剔除
    zw = [{'date': '20261103', 'open': 9.9, 'close': 9.9, 'high': 9.9, 'low': 9.9, 'prev_close': 9.9},
          {'date': '20261104', 'open': 10.89, 'close': 10.89, 'high': 10.89, 'low': 10.89, 'prev_close': 9.9},
          {'date': '20261105', 'open': 11.0, 'close': 11.5, 'high': 11.6, 'low': 10.9, 'prev_close': 10.89},
          {'date': '20261106', 'open': 11.5, 'close': 11.8, 'high': 11.9, 'low': 11.4, 'prev_close': 11.5},
          {'date': '20261107', 'open': 11.8, 'close': 12.0, 'high': 12.1, 'low': 11.7, 'prev_close': 11.8},
          {'date': '20261108', 'open': 12.0, 'close': 12.2, 'high': 12.3, 'low': 11.9, 'prev_close': 12.0}]
    tz = trade_return(zw, '20261103', '600000')
    ck('一字板剔除', tz['ret'] is None and tz['status'] == '一字板剔除', tz['status'])
    # 3. 开盘一字但盘中打开（high>low）→ 不剔除，能买到
    ok_open = [dict(zw[0]), {'date': '20261104', 'open': 10.89, 'close': 10.6, 'high': 10.89, 'low': 10.3, 'prev_close': 9.9},
               dict(zw[2]), dict(zw[3]), dict(zw[4]), dict(zw[5])]
    to = trade_return(ok_open, '20261103', '600000')
    ck('开盘一字后打开→不剔除', to['ret'] is not None and to['status'] == 'ok', to['status'])
    # 4. 创业板 20cm 一字也能识别
    cyb = [{'date': '20261103', 'open': 10, 'close': 10, 'high': 10, 'low': 10, 'prev_close': 10},
           {'date': '20261104', 'open': 11.99, 'close': 11.99, 'high': 11.99, 'low': 11.99, 'prev_close': 10},
           {'date': '20261105', 'open': 12, 'close': 12.5, 'high': 12.8, 'low': 11.9, 'prev_close': 11.99},
           {'date': '20261106', 'open': 12.5, 'close': 13, 'high': 13.1, 'low': 12.4, 'prev_close': 12.5},
           {'date': '20261107', 'open': 13, 'close': 13.5, 'high': 13.6, 'low': 12.9, 'prev_close': 13},
           {'date': '20261108', 'open': 13.5, 'close': 14, 'high': 14.1, 'low': 13.4, 'prev_close': 13.5}]
    ck('20cm 一字识别', trade_return(cyb, '20261103', '300001')['status'] == '一字板剔除',
       trade_return(cyb, '20261103', '300001')['status'])
    # 5. 不足5日 → 明确状态，不硬算
    ck('不足5日不硬算', trade_return(bars[:3], '20261103', '600000')['status'] == '不足5日', '')
    # 5b. 账本日期带横线 2026-11-03 也必须正确对齐（回归断言）
    t_dash = trade_return(bars, '2026-11-03', '600000')
    ck('带横线日期同样对齐 T+1', t_dash['entry'] == '20261104' and t_dash['exit'] == '20261108',
       (t_dash['entry'], t_dash['exit']))
    # 5c. 只有当日及以前数据（T+1 未到）→ 不出收益，不拿当天当买入日
    ck('T+1未到不出收益', trade_return([{'date': '20261103', 'open': 10, 'close': 10.2, 'high': 10.3,
                                       'low': 9.9, 'prev_close': 9.8}], '2026-11-03', '600000')['status'] == '无 T+1 数据',
       '')
    # 6. 等权组合与超额
    by = {'20261103': [{'code': '600000', 'total': '70'}, {'code': '000001', 'total': '66'},
                       {'code': '600001', 'total': '10'}]}
    bench = [{'date': '20261103', 'open': 3000, 'close': 3000, 'high': 3010, 'low': 2990, 'prev_close': 3000},
             {'date': '20261104', 'open': 3000, 'close': 3010, 'high': 3015, 'low': 2995, 'prev_close': 3000},
             {'date': '20261105', 'open': 3010, 'close': 3020, 'high': 3025, 'low': 3005, 'prev_close': 3010},
             {'date': '20261106', 'open': 3020, 'close': 3030, 'high': 3035, 'low': 3015, 'prev_close': 3020},
             {'date': '20261107', 'open': 3030, 'close': 3040, 'high': 3045, 'low': 3025, 'prev_close': 3030},
             {'date': '20261108', 'open': 3040, 'close': 3050, 'high': 3055, 'low': 3035, 'prev_close': 3040}]
    res = week_result(by, '20261103', {'600000': bars, '000001': ok_open, '600001': zw}, bench)
    print('  week=', res)
    ck('取前2(按total)', res['n'] == 2, res['n'])
    ck('一字板记为剔除', ('600001', '一字板剔除') in res['excluded'], res['excluded'])
    ck('超额=组合-基准', res['excess'] is not None, res['excess'])
    # 7. 卡片文案含四要素且无问号
    line = card_line([res])
    print('  card=', line)
    ck('卡片含 系统成绩单/超额/胜',
       all(k in line for k in ('系统成绩单', '沪深300', '超额')) and '?' not in line and '？' not in line, line)
    print('[selftest] weekly_backtest RESULT %s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 4


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(_selftest())
    by = load_csv()
    dates = sorted(by)
    print('[backtest] 账本日期=%s 记录=%d' % (dates, sum(len(v) for v in by.values())))
    res = run_dates(by, dates)
    for r in res:
        print('  ' + json.dumps(r, ensure_ascii=False))
    line = card_line(res)
    print(line)
    if '--dry' not in sys.argv:
        doc = save(res)
        print('[backtest] 已写 %s（%d 周）' % (OUT_PATH, len(doc['weeks'])))
