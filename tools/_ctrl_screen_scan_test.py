# -*- coding: utf-8 -*-
"""控盘选股服务 真实数据自测（可重跑）。

用法：
    python tools\\_ctrl_screen_scan_test.py            # 全市场扫描 + 分布 + 交叉验证
    python tools\\_ctrl_screen_scan_test.py quick      # 只扫前 300 只（冒烟）
"""
import os
import random
import sys
import time

sys.path.insert(0, r'D:\QuantMonitorV6')
os.chdir(r'D:\QuantMonitorV6')

import services.control_screen_service as S   # noqa: E402

QUICK = len(sys.argv) > 1 and sys.argv[1] == 'quick'


def main():
    t0 = time.perf_counter()
    bars = S.load_all_bars()
    print('批量读K线: %d 只 ｜ %.1fs' % (len(bars), time.perf_counter() - t0), flush=True)

    codes = None
    if QUICK:
        codes = sorted(bars.keys())[:300]
        print('冒烟模式：只扫 %d 只' % len(codes), flush=True)

    def _p(done, total, msg):
        if done % 1000 == 0 or done == total:
            print('  %s ｜ %.0fs' % (msg, time.perf_counter() - t0), flush=True)

    rows, stats = S.scan_market(codes=codes, bars=bars, progress_cb=_p)
    print('\n扫描统计: %s' % stats, flush=True)

    n = len(rows)
    if n == 0:
        print('!! 没有任何结果，先别继续', flush=True)
        return
    out = []
    out.append('扫描统计: %s' % stats)
    out.append('结果 %d 只' % n)

    # 分布
    buckets = [(90, 101), (85, 90), (80, 85), (70, 80), (60, 70), (0, 60)]
    out.append('--- 控盘分分布 ---')
    for lo, hi in buckets:
        c = sum(1 for r in rows if lo <= float(r['score']) < hi)
        out.append('  [%d,%d) : %d 只' % (lo, hi, c))
    st = {}
    for r in rows:
        st[r['stage']] = st.get(r['stage'], 0) + 1
    out.append('--- 阶段分布 --- %s' % st)
    lb = {}
    for r in rows:
        lb[r['label'] or '(无)'] = lb.get(r['label'] or '(无)', 0) + 1
    out.append('--- 控盘提示标签 --- %s' % lb)
    ob = {}
    for r in rows:
        for t in (r.get('observe') or []):
            ob[t] = ob.get(t, 0) + 1
    out.append('--- 观察标签 --- %s' % ob)
    md = {}
    for r in rows:
        md[r.get('data_date')] = md.get(r.get('data_date'), 0) + 1
    out.append('--- 数据日分布 --- %s' % md)

    # 各档筛选数量（页面默认 85 / 排出货 / 价格≥6 / 剔ST）
    out.append('--- 筛选数量（排出货 + 价格≥6 + 剔ST）---')
    for ms in (60, 70, 80, 85, 90):
        for pm in (None, 0.65, 0.45, 0.25):
            rr = S.apply_filters(rows, min_score=ms, pos_max=pm)
            out.append('  控盘≥%d 位置上限=%s -> %d 只' % (ms, pm, len(rr)))
    rr = S.apply_filters(rows, min_score=85.0)
    out.append('默认（控盘≥85、位置不限）: %d 只' % len(rr))
    for r in rr[:20]:
        out.append('   %s %s 控盘%.1f %-10s pos=%.2f %s %s'
                   % (r['code'], r['name'], r['score'], r['stage'], r['pos'],
                      r['label'], ' '.join(r.get('observe') or [])))

    txt = '\n'.join(out)
    print('\n' + txt, flush=True)
    with open(r'D:\QuantMonitorV6\tools\ctrl_screen_scan_test.txt', 'w', encoding='utf-8') as f:
        f.write(txt + '\n')

    # 交叉验证：随机 200 只，与 control_profile.compute_one 逐只比对
    from services.control_profile import compute_one
    sample = random.Random(20261011).sample(range(n), min(200, n))
    bad, checked = [], 0
    for i in sample:
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
                        r['pos'], a['pos'], r['data_date'], a['data_date']))
    print('\n--- 与 control_profile.compute_one 交叉验证 ---', flush=True)
    print('抽样 %d 只 ｜ 实际比对 %d 只 ｜ 不一致 %d 只' % (len(sample), checked, len(bad)), flush=True)
    for b in bad[:10]:
        print('  不一致: %s' % (b,), flush=True)

    # 过滤边界自测（构造数据，不依赖行情）
    edge = S.apply_filters(
        [{'code': '600000', 'name': '甲', 'score': 85.0, 'pos': 0.4499, 'stage': 'unknown',
          'price': 6.0, 'observe': []},
         {'code': '600001', 'name': 'ST乙', 'score': 86.0, 'pos': 0.1, 'stage': 'unknown',
          'price': 10.0, 'observe': []},
         {'code': '600002', 'name': '丙', 'score': 84.99, 'pos': 0.1, 'stage': 'unknown',
          'price': 10.0, 'observe': []},
         {'code': '600003', 'name': '丁', 'score': 90.0, 'pos': 0.1, 'stage': 'distribute',
          'price': 10.0, 'observe': []},
         {'code': '600004', 'name': '戊', 'score': 90.0, 'pos': 0.1, 'stage': 'unknown',
          'price': 5.99, 'observe': []},
         {'code': '600005', 'name': '己', 'score': 99.0, 'pos': 0.4501, 'stage': 'unknown',
          'price': 10.0, 'observe': ['拉升：阶梯式上行'], 'markup_type': '阶梯式上行'}],
        min_score=85.0, pos_max=0.45)
    print('边界自测: 通过 %s（期望只有 600000 一只，85.0/6.0/0.4499 都算通过）'
          % [r['code'] for r in edge], flush=True)
    print('边界自测(排除拉升): %s'
          % [r['code'] for r in S.apply_filters(
              [{'code': '600005', 'name': '己', 'score': 99.0, 'pos': 0.1,
                'stage': 'unknown', 'price': 10.0,
                'observe': ['拉升'], 'markup_type': '阶梯式上行'}], obs=S.OBS_NO_MARKUP)],
          flush=True)

    if not QUICK:
        sp = S.save_snapshot(rows, stats)
        print('快照已写: %s' % sp, flush=True)

    print('\n总用时 %.1fs' % (time.perf_counter() - t0), flush=True)


if __name__ == '__main__':
    main()
