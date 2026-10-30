# -*- coding: utf-8 -*-
"""控盘选股服务 独立验证（可重跑）。

覆盖：
  [A] 源码级：股票池边界、无未来函数、常量口径
  [B] 真实数据：全市场扫描 + 与 control_profile.compute_one 逐只交叉验证
  [C] 筛选边界：控盘分 / 位置 / 价格 / ST / 观察标签
  [D] 导出：格式、去重、6 位码
  [E] 快照：写→读 一致
  [F] 不改动任何库（扫描前后 band_pattern.db / kline_cache.duckdb 字节不变）
结果写 tools\\ctrl_screen_unit.txt（同时打印）。
"""
import io
import os
import random
import sys
import tempfile
import time

sys.path.insert(0, r'D:\QuantMonitorV6')
os.chdir(r'D:\QuantMonitorV6')

import services.control_screen_service as SS   # noqa: E402

PASS, FAIL, LINES = [], [], []


def ck(name, cond, extra=''):
    (PASS if cond else FAIL).append(name)
    LINES.append('%s %s%s' % ('PASS' if cond else 'FAIL', name,
                              (' ｜ %s' % extra) if extra else ''))


def main():
    t0 = time.perf_counter()

    # ---------- [A] 源码级 ----------
    src = io.open(os.path.join(r'D:\QuantMonitorV6', 'services', 'control_screen_service.py'),
                  'r', encoding='utf-8').read()
    ck('A1 常量：MIN_BARS=60 / BARS_LIMIT=120',
       'MIN_BARS = 60' in src and 'BARS_LIMIT = 120' in src)
    ck('A2 股票池：主板+创业板，剔科创板/北交所',
       "UNIVERSE_PREFIXES = ('60', '00', '30')" in src
       and "EXCLUDE_PREFIXES = ('688', '689', '8', '4', '920')" in src)
    _cases = [('600000', True), ('000001', True), ('300750', True), ('301029', True),
              ('688111', False), ('689009', False), ('830799', False), ('430047', False),
              ('920819', False), ('12345', False), ('60000X', False), ('', False)]
    _bad = [(c, e, SS.is_universe_code(c)) for c, e in _cases
            if SS.is_universe_code(c) != e]
    ck('A3 is_universe_code 12 组边界', not _bad, str(_bad))
    # 无未来数据：源码里所有切片/下标都只用 i-5:i 这种「往前看」的写法
    _bad_slice = [s for s in ['volumes[i:', 'bars[i+', 'iloc[i+', '.shift(-'] if s in src]
    ck('A4 无未来函数写法（无正向切片/负向shift）', not _bad_slice, str(_bad_slice))
    ck('A5 只读库：duckdb.connect 带 read_only=True',
       'duckdb.connect(KLINE_DB, read_only=True)' in src)
    ck('A6 涨停题材走同源 get_last_limit_up_reason（不另写一套 SQL）',
       'from data.limit_up_reason_db import get_last_limit_up_reason' in src
       and 'def limit_up_theme(' in src)

    # ---------- [F] 前置：记录库文件指纹 ----------
    def _fp(p):
        try:
            st = os.stat(p)
            return (st.st_size, int(st.st_mtime))
        except Exception:
            return None
    _dbs = {'band_pattern.db': r'D:\QuantMonitorV6\data\cache\band_pattern.db',
            'kline_cache.duckdb': r'D:\QuantMonitorV6\data\cache\kline_cache.duckdb'}
    _before = {k: _fp(v) for k, v in _dbs.items()}

    # ---------- [B] 全市场扫描 ----------
    bars = SS.load_all_bars()
    ck('B1 批量读库拿到代码', len(bars) > 4000, '只数=%d' % len(bars))
    _k = sorted(bars.keys())[0]
    ck('B2 bar 结构与传统接口一致（date/open/high/low/close/volume）',
       set(bars[_k][-1].keys()) == {'date', 'open', 'high', 'low', 'close', 'volume'},
       str(sorted(bars[_k][-1].keys())))
    _asc = all(bars[_k][i]['date'] <= bars[_k][i + 1]['date'] for i in range(len(bars[_k]) - 1))
    ck('B3 K线按日期升序（最后一根=最新）', _asc)

    rows, stats = SS.scan_market(bars=bars)
    ck('B4 全市场扫描有结果且无失败', len(rows) > 4000 and stats['fail'] == 0,
       'universe=%d ok=%d skip=%d fail=%d %.1fs'
       % (stats['universe'], stats['ok'], stats['skip_bars'], stats['fail'],
          stats['elapsed']))
    ck('B5 结果按控盘分降序', all(float(rows[i]['score']) >= float(rows[i + 1]['score'])
                                for i in range(min(200, len(rows) - 1))))
    ck('B6 控盘分区间合法 0~100',
       all(0.0 <= float(r['score']) <= 100.0 for r in rows))
    ck('B7 位置区间合法 0~1', all(0.0 <= float(r['pos']) <= 1.0 for r in rows))
    ck('B8 数据日=本地缓存最新日', stats['data_date'] == max(r['data_date'] for r in rows),
       stats['data_date'])
    ck('B9 观察标签与字段自洽',
       all((('试盘' in (r['observe'] or [])) == bool(r['probe_ok']))
           and (('C4' in (r['observe'] or [])) == bool(r['c4_ok']))
           and (('C6' in (r['observe'] or [])) == bool(r['c6_ok']))
           and (('出货形态' in (r['observe'] or [])) == bool(r['dist_type']))
           and any(str(t).startswith('拉升') for t in (r['observe'] or [])) == bool(r['markup_type'])
           for r in rows))

    # 交叉验证：随机 250 只 与 control_profile.compute_one 逐只比对
    from services.control_profile import compute_one
    rnd = random.Random(20261011)
    idx = rnd.sample(range(len(rows)), min(250, len(rows)))
    bad, checked = [], 0
    for i in idx:
        r = rows[i]
        a = compute_one(r['code'])
        if not a.get('ok'):
            continue
        checked += 1
        if (abs(float(a['score']) - float(r['score'])) > 0.01
                or str(a['stage']) != str(r['stage'])
                or abs(float(a['pos']) - float(r['pos'])) > 5e-4
                or str(a['data_date']) != str(r['data_date'])):
            bad.append((r['code'], r['score'], a['score'], r['stage'], a['stage'],
                        r['pos'], a['pos']))
    ck('B10 与 control_profile.compute_one 逐只一致', not bad,
       '抽样 %d 比对 %d 不一致 %d ｜ %s' % (len(idx), checked, len(bad), bad[:3]))
    # 名称：非空比例
    _named = sum(1 for r in rows if r.get('name'))
    ck('B11 名称填充率 > 95%%', _named > len(rows) * 0.95,
       '%d/%d' % (_named, len(rows)))

    # ---------- [B-题材] 涨停题材 ----------
    from data.limit_up_reason_db import get_last_limit_up_reason   # noqa: E402
    ck('B12 每行都有 theme/theme_date/theme_lbc/theme_ind 字段（类型正确）',
       all(isinstance(r.get('theme'), str) and isinstance(r.get('theme_date'), str)
           and isinstance(r.get('theme_lbc'), int) and isinstance(r.get('theme_ind'), str)
           for r in rows))
    _th_rows = [r for r in rows if r['theme']]
    ck('B13 有题材的行数 > 0 且题材串含「+」（与库口径一致）',
       len(_th_rows) > 0 and all('+' in r['theme'] for r in _th_rows),
       '有题材 %d / %d' % (len(_th_rows), len(rows)))
    ck('B14 stats.theme_ok 与有题材行数一致',
       int(stats.get('theme_ok') or 0) == len(_th_rows),
       'theme_ok=%s 实际=%d' % (stats.get('theme_ok'), len(_th_rows)))
    _rnd2 = random.Random(20261012)
    _idx2 = _rnd2.sample(range(len(rows)), 30)
    _bad_th = []
    for i in _idx2:
        r = rows[i]
        _a = get_last_limit_up_reason(r['code'])
        _want = (str(_a[0] or ''), str(_a[1] or ''), int(_a[2] or 0), str(_a[3] or ''))
        _got = (r['theme'], r['theme_date'], int(r['theme_lbc']), r['theme_ind'])
        if _want != _got:
            _bad_th.append((r['code'], _want, _got))
    ck('B15 抽样 30 只题材与 get_last_limit_up_reason 直连结果逐字段一致',
       not _bad_th, str(_bad_th[:2]))
    _bad_th2 = [(r['code'], r['theme']) for r in rows
                if r['theme'] and '+' not in r['theme']]
    ck('B16 无「不含 + 的题材」漏网', not _bad_th2, str(_bad_th2[:3]))

    # ---------- [F] 扫描不改动库 ----------
    _after = {k: _fp(v) for k, v in _dbs.items()}
    ck('F1 扫描前后 band_pattern.db 未变', _before['band_pattern.db'] == _after['band_pattern.db'],
       '%s -> %s' % (_before['band_pattern.db'], _after['band_pattern.db']))
    ck('F2 扫描前后 kline_cache.duckdb 未变',
       _before['kline_cache.duckdb'] == _after['kline_cache.duckdb'],
       '%s -> %s' % (_before['kline_cache.duckdb'], _after['kline_cache.duckdb']))

    # ---------- [C] 筛选边界 ----------
    M = [{'code': '600000', 'name': '甲', 'score': 85.0, 'pos': 0.4499,
          'stage': 'unknown', 'price': 6.0, 'observe': []},          # 全踩线 -> 通过
         {'code': '600001', 'name': 'ST乙', 'score': 90.0, 'pos': 0.1,
          'stage': 'unknown', 'price': 10.0, 'observe': []},          # ST -> 剔除
         {'code': '600002', 'name': '丙', 'score': 84.99, 'pos': 0.1,
          'stage': 'unknown', 'price': 10.0, 'observe': []},          # 差 0.01 分 -> 剔除
         {'code': '600003', 'name': '丁', 'score': 90.0, 'pos': 0.1,
          'stage': 'distribute', 'price': 10.0, 'observe': ['出货形态']},  # 出货 -> 剔除
         {'code': '600004', 'name': '戊', 'score': 90.0, 'pos': 0.1,
          'stage': 'unknown', 'price': 5.99, 'observe': []},           # 价格差 0.01 -> 剔除
         {'code': '600005', 'name': '己', 'score': 99.0, 'pos': 0.4501,
          'stage': 'unknown', 'price': 10.0, 'observe': [], 'markup_type': ''},
         {'code': '600006', 'name': '庚', 'score': 99.0, 'pos': 0.1, 'stage': 'unknown',
          'price': 10.0, 'observe': ['拉升：阶梯式上行'], 'markup_type': '阶梯式上行'},
         {'code': '600007', 'name': '辛', 'score': 99.0, 'pos': 0.1, 'stage': 'unknown',
          'price': 10.0, 'observe': ['试盘'], 'probe_ok': True},
         {'code': '600008', 'name': '壬', 'score': 99.0, 'pos': 0.1, 'stage': 'unknown',
          'price': 10.0, 'observe': ['C6'], 'c6_ok': True}]
    got = [r['code'] for r in SS.apply_filters(M, min_score=85.0, pos_max=0.45)]
    # 逐行判定（严格按默认条件 min_score=85/pos≤0.45/排出货/价≥6/剔ST/观察=全部）：
    #   600000 85.0/0.4499/6.0 踩线   -> 通过
    #   600001 ST                    -> 剔
    #   600002 84.99（差 0.01 分）    -> 剔
    #   600003 distribute            -> 剔
    #   600004 5.99（差 0.01 元）     -> 剔
    #   600005 pos 0.4501            -> 剔（位置超限）
    #   600006/600007/600008 99 分、低位、有观察标签 -> 通过
    ck('C1 边界：85.0/0.4499/6.0 通过；84.99/0.4501/5.99/ST/出货 剔除',
       got == ['600006', '600007', '600008', '600000'], str(got))
    ck('C1b 位置超限样本单独验证（放宽位置后 600005 才进来）',
       '600005' not in got
       and '600005' in [r['code'] for r in SS.apply_filters(M, min_score=85.0, pos_max=None)])
    ck('C2 排出货可关：关掉后 distribute 进得来',
       '600003' in [r['code'] for r in SS.apply_filters(M, min_score=85.0, exclude_dist=False)])
    ck('C3 价格门槛可关',
       '600004' in [r['code'] for r in SS.apply_filters(M, min_score=85.0, min_price=0.0)])
    ck('C4 位置不限（pos_max=None）时 0.4501 也通过',
       '600005' in [r['code'] for r in SS.apply_filters(M, min_score=85.0, pos_max=None)])
    # 观察=排除拉升（排出货关掉，否则 600003 被另一个条件剔掉）：
    #   通过顺序按分数降序 = 600005(99) 600007(99) 600008(99) 600003(90) 600000(85)；600006 被拉升条件剔
    ck('C5 观察=排除拉升 只剔拉升',
       [r['code'] for r in SS.apply_filters(M, obs=SS.OBS_NO_MARKUP, exclude_dist=False)]
       == ['600005', '600007', '600008', '600003', '600000'])
    ck('C6 观察=仅试盘',
       [r['code'] for r in SS.apply_filters(M, obs=SS.OBS_PROBE, exclude_dist=False)]
       == ['600007'])
    ck('C7 观察=仅C4/C6',
       [r['code'] for r in SS.apply_filters(M, obs=SS.OBS_C46, exclude_dist=False)]
       == ['600008'])
    # 观察=有任一观察：无标签的 600000 被剔；600003(出货形态标签) 在排出货关掉后保留
    ck('C8 观察=有任一观察（无标签的 600000 被剔）',
       [r['code'] for r in SS.apply_filters(M, obs=SS.OBS_ANY, pos_max=0.45,
                                            exclude_dist=False)]
       == ['600006', '600007', '600008', '600003'])
    ck('C9 真实数据：控盘≥85 排出货 结果 ⊆ 全量且降序',
       all(float(a['score']) >= 85.0 and a['stage'] != 'distribute'
           for a in SS.apply_filters(rows, min_score=85.0, pos_max=None)
           if len(SS.apply_filters(rows, min_score=85.0, pos_max=None)) > 0),
       '控盘≥85 -> %d 只' % len(SS.apply_filters(rows, min_score=85.0, pos_max=None)))

    # ---------- [D] 导出 ----------
    _tmp = os.path.join(tempfile.gettempdir(), 'ctrl_screen_export_test.txt')
    _top = SS.apply_filters(rows, min_score=90.0, pos_max=0.25)
    n = SS.export_codes(_top, _tmp)
    _lines = [ln.strip() for ln in io.open(_tmp, 'r', encoding='utf-8').read().split('\n') if ln.strip()]
    ck('D1 导出条数=入参条数（无重复）', n == len(_top) == len(_lines),
       'n=%d 行=%d 入参=%d' % (n, len(_lines), len(_top)))
    ck('D2 导出内容全是 6 位数字且无表头、无逗号',
       all(len(x) == 6 and x.isdigit() for x in _lines)
       and all(',' not in x for x in _lines))
    ck('D3 导出代码与筛选结果逐行同序',
       _lines == [str(r['code']) for r in _top])
    ck('D4 去重：同一代码重复传入只出一行',
       SS.export_codes([{'code': '600000'}, {'code': '600000'}], _tmp) == 1)
    ck('D5 空结果返回 0 且不报错', SS.export_codes([], _tmp) == 0)

    # ---------- [E] 快照 ----------
    _snap = os.path.join(tempfile.gettempdir(), 'ctrl_screen_snap_test.json')
    p = SS.save_snapshot(rows[:50], stats, path=_snap)
    d = SS.load_snapshot(path=_snap)
    ck('E1 快照写→读 行数一致', bool(p) and d is not None and len(d['rows']) == 50)
    ck('E2 快照保留 data_date / universe / saved_at',
       d and d['data_date'] == stats['data_date'] and d['universe'] == stats['universe']
       and bool(d['saved_at']), str(d.get('saved_at') if d else None))
    ck('E3 快照行字段无损（浮点+列表+题材）',
       d and abs(float(d['rows'][0]['score']) - float(rows[0]['score'])) < 1e-9
       and (d['rows'][0]['observe'] or []) == (rows[0]['observe'] or [])
       and str(d['rows'][0].get('theme') or '') == str(rows[0].get('theme') or '')
       and str(d['rows'][0].get('theme_date') or '') == str(rows[0].get('theme_date') or ''))
    ck('E4 快照路径缺省指向 data/cache/control_screen.json',
       SS.SNAPSHOT_PATH.endswith(os.path.join('data', 'cache', 'control_screen.json')))

    # ---------- 汇总 ----------
    LINES.append('')
    LINES.append('=== %d PASS / %d FAIL ｜ 用时 %.1fs ==='
                 % (len(PASS), len(FAIL), time.perf_counter() - t0))
    if FAIL:
        LINES.append('失败项：%s' % FAIL)
    txt = '\n'.join(LINES)
    print(txt, flush=True)
    with io.open(r'D:\QuantMonitorV6\tools\ctrl_screen_unit.txt', 'w', encoding='utf-8') as f:
        f.write(txt + '\n')
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
