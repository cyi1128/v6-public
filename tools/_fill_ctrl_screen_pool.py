# -*- coding: utf-8 -*-
"""把「控盘选股」页可达上限（控盘分≥0 + 页面默认三勾 = 3294 只）的两列补满。

只会补真正缺/过期的（2301 只左右），workers=3 + 服务层限速 + 失败退避 + 熔断。
写 data/cache/ctrl_screen_extras.json；只读快照，不改任何选股逻辑。
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

LOG = os.path.join(ROOT, 'tools', '_fill_pool2301.log')
_buf = []


def say(s):
    _buf.append(str(s))
    print(s, flush=True)
    try:
        io.open(LOG, 'w', encoding='utf-8').write('\n'.join(_buf) + '\n')
    except Exception:
        pass


snap = SS.load_snapshot()
if not snap:
    say('没有快照，先跑 tools\\_rescan_ctrl_screen.py')
    sys.exit(1)

rows = SS.apply_filters(snap['rows'], min_score=0.0, pos_max=None, exclude_dist=True,
                        min_price=6.0, drop_st=True, obs=SS.OBS_ALL)
codes = [str(r['code']) for r in rows]
say('目标池 %d 只（控盘≥0 / 排除出货 / 价≥6 / 剔ST）｜快照全量 %d 只'
    % (len(codes), len(snap['rows'])))
say('板块：%s' % dict(Counter('创业板' if c.startswith(('300', '301')) else '主板'
                              for c in codes)))

items = SS.load_extras()
say('缓存已有 %d 条 ｜ 需补/过期 %d 只' % (len(items), len(SS.extras_missing(codes, items))))

t0 = time.perf_counter()
_tick = {'n': 0}


def _p(done, total, msg):
    if done - _tick['n'] >= 150 or done == total:
        _tick['n'] = done
        say('   %s ｜ 已用 %.0fs' % (msg, time.perf_counter() - t0))


items, stats = SS.fetch_extras(codes, items, workers=3, path=SS.EXTRAS_PATH,
                               progress_cb=_p, save_every=100, fail_circuit=12)
el = time.perf_counter() - t0
say('完成: %s ｜ 墙钟 %.1fs' % (stats, el))

say('')
say('=== 覆盖率（目标池 %d 只）===' % len(codes))
for b, pre in (('主板', ('60', '00')), ('创业板', ('300', '301'))):
    _sub = [c for c in codes if c.startswith(pre)]
    _b = sum(1 for c in _sub if (items.get(c) or {}).get('biz'))
    _a = sum(1 for c in _sub if (items.get(c) or {}).get('ann'))
    say('   %-4s %5d 只：主营 %5d（%.1f%%）｜公告 %5d（%.1f%%）'
        % (b, len(_sub), _b, 100.0 * _b / max(1, len(_sub)), _a, 100.0 * _a / max(1, len(_sub))))
_b = sum(1 for c in codes if (items.get(c) or {}).get('biz'))
_a = sum(1 for c in codes if (items.get(c) or {}).get('ann'))
say('   合计 %d 只：主营 %d（%.1f%%）｜公告 %d（%.1f%%）'
    % (len(codes), _b, 100.0 * _b / max(1, len(codes)), _a, 100.0 * _a / max(1, len(codes))))
say('公告来源分布: %s'
    % Counter((items.get(c) or {}).get('ann_src') or '空' for c in codes))
say('主营报告期分布: %s'
    % Counter((items.get(c) or {}).get('biz_date') or '空' for c in codes))
say('主营失败标记 %d 只 ｜ 公告失败标记 %d 只'
    % (sum(1 for c in codes if (items.get(c) or {}).get('biz_fail')),
       sum(1 for c in codes if (items.get(c) or {}).get('ann_fail'))))

say('')
say('=== 抽样 12 只 ===')
for c in codes[:12]:
    _nm = next((r['name'] for r in rows if str(r['code']) == c), '')
    say('   %s %-6s 主营=%-24s 公告=%s'
        % (c, _nm, SS.fmt_biz(items.get(c))[0] or '--',
           (SS.fmt_ann(items.get(c))[0] or '--')[:38]))

say('')
say('缓存 %s ｜ %d 字节'
    % (SS.EXTRAS_PATH, os.path.getsize(SS.EXTRAS_PATH)
       if os.path.isfile(SS.EXTRAS_PATH) else -1))
say('补完后 extras_missing = %d 只' % len(SS.extras_missing(codes, items)))
