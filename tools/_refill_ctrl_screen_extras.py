# -*- coding: utf-8 -*-
"""重跑补数（v3 链路）：先把上一轮「限流被记成空」的记录标成失败态，再补。可重跑。

上一轮（v1/v2 代码）：东财 567 + 巨潮 403 → `ann=[]`、`ann_src=''`，
但 `ann_ts` 是「尝试时间」，按空结果 TTL 2 小时算「新鲜」→ 不会重试。
这里把这类记录标成 `ann_fail=1` + `ann_ts=0`（立刻可重试），走新的「东财→新浪→巨潮」链路。
"""
import io
import os
import sys
import time
from collections import Counter

ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import services.control_screen_service as SS   # noqa: E402

snap = SS.load_snapshot()
rows = SS.apply_filters(snap['rows'], min_score=85.0, pos_max=None, exclude_dist=True,
                        min_price=6.0, drop_st=True, obs=SS.OBS_ALL)
codes = [str(r['code']) for r in rows]
items = SS.load_extras()
print('筛选池 %d 只 ｜ 缓存 %d 条' % (len(codes), len(items)), flush=True)

# ---- 迁移：把「上游失败被记成空」的记录改成可重试 ----
_mig_ann = _mig_biz = 0
for c, rec in items.items():
    if not isinstance(rec, dict):
        continue
    if not (rec.get('ann') or []) and not str(rec.get('ann_src') or ''):
        rec['ann_fail'] = 1
        rec['ann_ts'] = 0
        _mig_ann += 1
    if not (rec.get('biz') or []) and not (rec.get('biz_items') or []):
        rec['biz_fail'] = 1
        rec['biz_ts'] = 0
        _mig_biz += 1
print('迁移：公告待重试 %d 只 ｜ 主营待重试 %d 只' % (_mig_ann, _mig_biz), flush=True)
SS.save_extras(items)

miss = SS.extras_missing(codes, items)
print('本轮需要补/过期 %d 只（公告桶限速 0.3s/次，预计 %d 分钟）'
      % (len(miss), max(1, int(len(miss) * 0.30 / 60))), flush=True)

t0 = time.perf_counter()
_buf = {'n': 0}


def _p(done, total, msg):
    if done - _buf['n'] >= 50 or done == total:
        _buf['n'] = done
        print('   %s ｜ 已用 %.0fs' % (msg, time.perf_counter() - t0), flush=True)


items, stats = SS.fetch_extras(miss, items, workers=3, path=SS.EXTRAS_PATH,
                              progress_cb=_p, save_every=50)
print('完成: %s ｜ 墙钟 %.1fs' % (stats, time.perf_counter() - t0), flush=True)

print(flush=True)
print('=== 覆盖率（筛选池 %d 只）===' % len(codes), flush=True)
_biz = [c for c in codes if (items.get(c) or {}).get('biz')]
_ann = [c for c in codes if (items.get(c) or {}).get('ann')]
_fail = [c for c in codes if (items.get(c) or {}).get('ann_fail')]
print('主营有数据 %d/%d = %.1f%%' % (len(_biz), len(codes), 100.0 * len(_biz) / max(1, len(codes))))
print('公告有数据 %d/%d = %.1f%%' % (len(_ann), len(codes), 100.0 * len(_ann) / max(1, len(codes))))
print('公告待重试(失败标记) %d 只' % len(_fail))
print('公告来源分布: %s' % Counter((items.get(c) or {}).get('ann_src') or '空' for c in codes))
print('主营报告期分布: %s' % Counter((items.get(c) or {}).get('biz_date') or '空' for c in codes))
for b, pre in (('主板', ('60', '00')), ('创业板', ('30',))):
    _sub = [c for c in codes if c.startswith(pre)]
    _a = sum(1 for c in _sub if (items.get(c) or {}).get('ann'))
    _bb = sum(1 for c in _sub if (items.get(c) or {}).get('biz'))
    print('   %s %d 只：主营 %d（%.0f%%）｜公告 %d（%.0f%%）'
          % (b, len(_sub), _bb, 100.0 * _bb / max(1, len(_sub)), _a, 100.0 * _a / max(1, len(_sub))))

print(flush=True)
print('=== 抽样 12 只 ===', flush=True)
for c in codes[:12]:
    _nm = next((r['name'] for r in rows if str(r['code']) == c), '')
    _bt, _ = SS.fmt_biz(items.get(c))
    _at, _ = SS.fmt_ann(items.get(c))
    _rec = items.get(c) or {}
    print('   %s %-6s 主营=%-24s 公告=[%s]%s'
          % (c, _nm, _bt or '--', _rec.get('ann_src') or '重试中', (_at or '--')[:38]), flush=True)

print(flush=True)
print('缓存 %s ｜ %d 字节' % (SS.EXTRAS_PATH,
                            os.path.getsize(SS.EXTRAS_PATH) if os.path.isfile(SS.EXTRAS_PATH) else -1))
print('补完后 extras_missing = %d 只' % len(SS.extras_missing(codes, items)), flush=True)
