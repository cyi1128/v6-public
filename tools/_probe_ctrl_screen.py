# -*- coding: utf-8 -*-
"""控盘选股页 前置探查（一次性）：
1) 本地缓存里有多少只可算股票（按板性过滤后）
2) 单只算「控盘 + 观察因子」的真实耗时（决定整页扫描要不要进度条）
3) 我准备在页面上用的因子接口是否都能跑通
4) 与 services.control_profile.compute_one 的口径是否一致（同码同值）
"""
import io
import os
import sys
import time

sys.path.insert(0, r'D:\QuantMonitorV6')
os.chdir(r'D:\QuantMonitorV6')

from services.kline_cache_service import get_all_cached_codes, get_latest_kline   # noqa: E402
import services.band_pattern_engine as E                                           # noqa: E402
from strategy.base import TechnicalIndicators as TI                                # noqa: E402

codes = get_all_cached_codes()
print('本地缓存代码总数: %d' % len(codes), flush=True)


def _keep(c):
    c = str(c)
    if len(c) != 6 or not c.isdigit():
        return False
    if c.startswith(('688', '689', '8', '4', '920')):
        return False
    return c.startswith(('60', '00', '30'))


main = [c for c in codes if _keep(c)]
print('主板+创业板可算: %d ｜ 剔除: %d' % (len(main), len(codes) - len(main)), flush=True)

ti = TI()
sample = main[:12]
print('\n--- 单只耗时与因子契约（前 12 只）---', flush=True)
t_load = t_ctrl = t_obs = 0.0
for c in sample:
    t0 = time.perf_counter()
    bars = get_latest_kline(c, count=120)
    t1 = time.perf_counter()
    df = E._bars_to_df(bars)
    if df is None or len(df) < 60:
        print('%s  K线不足(%d) 跳过' % (c, len(bars or [])), flush=True)
        continue
    score = ti.estimate_control_score(df)
    stage = ti.judge_wash_or_distribute(df)
    _t = df['close'].tail(120)
    _lo, _hi = float(_t.min()), float(_t.max())
    pos = (float(df['close'].iloc[-1]) - _lo) / (_hi - _lo + 1e-8)
    t2 = time.perf_counter()
    stack = ti.bottom_volume_stack(df)
    redfat = ti.red_fat_green_thin(df)
    c4 = ti.is_c4_candidate(df, ctrl_score=score)
    c6 = ti.is_c6_candidate(df)
    probe = ti.detect_probe(df)
    distp = ti.detect_distribution_pattern(df)
    markup = ti.detect_markup(df)
    t3 = time.perf_counter()
    t_load += t1 - t0
    t_ctrl += t2 - t1
    t_obs += t3 - t2
    note = E._ctrl_note(score, stage, pos, stack.get('score') if stack else None,
                        redfat.get('score') if redfat else None,
                        (c4 or {}).get('n_ok'), (c6 or {}).get('n_ok'),
                        (probe or {}).get('ok'), (distp or {}).get('type'),
                        (markup or {}).get('type'))
    print('%s 控盘%.1f %-10s pos=%.3f ｜ stack=%.0f redfat=%.2f ｜ c4=%s c6=%s probe=%s/%s dist=%s markup=%s'
          % (c, score, stage, pos,
             (stack or {}).get('score', -1), (redfat or {}).get('ratio', -1),
             (c4 or {}).get('n_ok'), (c6 or {}).get('n_ok'),
             (probe or {}).get('ok'), (probe or {}).get('stage'),
             (distp or {}).get('type') or '-', (markup or {}).get('type') or '-'), flush=True)
    print('      note=%r' % note, flush=True)

n = max(1, len(sample))
print('\n平均耗时: 读K线 %.1f ms ｜ 控盘 %.1f ms ｜ 观察因子 %.1f ms ｜ 合计 %.1f ms/只'
      % (t_load / n * 1000, t_ctrl / n * 1000, t_obs / n * 1000,
         (t_load + t_ctrl + t_obs) / n * 1000), flush=True)
print('据此推算全市场 %d 只 ≈ %.1f 分钟'
      % (len(main), (t_load + t_ctrl + t_obs) / n * len(main) / 60.0), flush=True)

print('\n--- 与 control_profile.compute_one 口径比对（同一批）---', flush=True)
from services.control_profile import compute_one   # noqa: E402
for c in sample[:6]:
    bars = get_latest_kline(c, count=120)
    df = E._bars_to_df(bars)
    if df is None or len(df) < 60:
        continue
    _t = df['close'].tail(120)
    _lo, _hi = float(_t.min()), float(_t.max())
    pos_a = (float(df['close'].iloc[-1]) - _lo) / (_hi - _lo + 1e-8)
    a = compute_one(c)
    same = (abs(float(a['score']) - float(ti.estimate_control_score(df))) < 1e-9
            and a['stage'] == ti.judge_wash_or_distribute(df)
            and abs(float(a['pos']) - pos_a) < 1e-12)
    print('%s 一致=%s ｜ profile score=%.2f stage=%s pos=%.4f ｜ 本页 score=%.2f stage=%s pos=%.4f'
          % (c, same, a['score'], a['stage'], a['pos'],
             ti.estimate_control_score(df), ti.judge_wash_or_distribute(df), pos_a), flush=True)
