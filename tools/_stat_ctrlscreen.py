# -*- coding: utf-8 -*-
"""从真实快照统计控盘选股页的筛选漏斗与控盘分分布（只读，一次性）。"""
import io
import os
import sys

sys.path.insert(0, r'D:\QuantMonitorV6')
os.chdir(r'D:\QuantMonitorV6')

import services.control_screen_service as SS   # noqa: E402

snap = SS.load_snapshot()
rows = snap['rows']
print('快照: saved_at=%s data_date=%s universe=%s ok=%s elapsed=%s 行数=%d'
      % (snap['saved_at'], snap['data_date'], snap['universe'], snap['ok'],
         snap['elapsed'], len(rows)))


def n(**kw):
    return len(SS.apply_filters(rows, **kw))


D = dict(min_score=85.0, pos_max=None, exclude_dist=True, min_price=6.0, drop_st=True,
         obs=SS.OBS_ALL)
print('抽出池（K线≥60）: %d' % len(rows))
print('控盘≥85 + 排出货 + 价≥6 + 剔ST: %d' % n(**D))
print('  再叠加 位置≤0.65: %d' % n(**dict(D, pos_max=0.65)))
print('  再叠加 位置≤0.45: %d' % n(**dict(D, pos_max=0.45)))
print('  再叠加 位置≤0.25: %d' % n(**dict(D, pos_max=0.25)))
for s in (90.0, 95.0):
    print('控盘≥%.0f（位置不限）: %d ；位置≤0.25: %d'
          % (s, n(**dict(D, min_score=s)), n(**dict(D, min_score=s, pos_max=0.25))))
print('不排出货（控盘≥85）: %d' % n(**dict(D, exclude_dist=False)))
print('观察=排除拉升（控盘≥85）: %d' % n(**dict(D, obs=SS.OBS_NO_MARKUP)))

bins = [(90, 101), (85, 90), (80, 85), (70, 80), (60, 70), (0, 60)]
print('控盘分分布: ' + ' ｜ '.join('[%d,%d) %d' % (a, b, sum(1 for r in rows if a <= float(r['score']) < b))
                                  for a, b in bins))
st = {}
for r in rows:
    st[r['stage']] = st.get(r['stage'], 0) + 1
print('阶段分布: %s' % st)
lab = {}
for r in rows:
    k = r['label'] or '(无)'
    lab[k] = lab.get(k, 0) + 1
print('控盘提示: %s' % lab)
obs = {}
for r in rows:
    for t in (r['observe'] or []):
        obs[t] = obs.get(t, 0) + 1
print('观察标签: %s' % obs)
print('数据日分布: %s' % {d: sum(1 for r in rows if r['data_date'] == d)
                        for d in sorted({r['data_date'] for r in rows})})

# ---- 涨停题材覆盖（2026-10-11 新增列）----
_th = sum(1 for r in rows if r.get('theme'))
print('题材覆盖: 全量 %d/%d (%.1f%%) ｜ 控盘≥85 排出货 %d/%d (%.1f%%)'
      % (_th, len(rows), _th * 100.0 / max(1, len(rows)),
         sum(1 for r in SS.apply_filters(rows, **D) if r.get('theme')),
         n(**D),
         sum(1 for r in SS.apply_filters(rows, **D) if r.get('theme'))
         * 100.0 / max(1, n(**D))))
_has = [r for r in SS.apply_filters(rows, **D) if r.get('theme')]
print('题材 Top8（控盘≥85 池内，按题材串出现次数）:')
_c = {}
for r in _has:
    _c[r['theme']] = _c.get(r['theme'], 0) + 1
for t, k in sorted(_c.items(), key=lambda x: -x[1])[:8]:
    print('   %2d 次  %s' % (k, t))
print('题材样例 8 只:')
for r in _has[:8]:
    print('   %s %s 控盘%.1f 题材=%s (%s/%s连板)'
          % (r['code'], r['name'], float(r['score']), r['theme'],
             r.get('theme_date') or '-', r.get('theme_lbc') or 0))
