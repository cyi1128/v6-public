# -*- coding: utf-8 -*-
"""量化「全市场一次性补满」的代价（只读，不改任何数据）。"""
import os
import sys
from collections import Counter

ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import services.control_screen_service as SS  # noqa: E402

snap = SS.load_snapshot()
rows = snap['rows']
items = SS.load_extras()
print('快照：universe=%s ok=%s theme_ok=%s saved_at=%s data_date=%s'
      % (snap.get('universe'), snap.get('ok'), snap.get('theme_ok'),
         snap.get('saved_at'), snap.get('data_date')))
print('快照总行数=%d ｜ 两列缓存=%d 条' % (len(rows), len(items)))

print('\n-- 各控盘分阈值下的筛选池（其余条件同页面默认：排出货/价格≥6/剔ST）--')
for th in (0.0, 60.0, 70.0, 75.0, 80.0, 85.0, 90.0):
    r = SS.apply_filters(rows, min_score=th, pos_max=None, exclude_dist=True,
                         min_price=6.0, drop_st=True, obs=SS.OBS_ALL)
    cov = sum(1 for x in r if str(x['code']) in items)
    print('  控盘分>=%-5s 池=%-5d 已有两列=%-5d 待补=%-5d'
          % (th, len(r), cov, len(r) - cov))

_csv = [str(c) for c in snap.get('codes') or []]
if not _csv:
    _csv = [str(r['code']) for r in rows]
print('\n-- 全市场（快照 codes）--')
print('  全市场代码数=%d ｜ 已在缓存=%d ｜ 待补=%d'
      % (len(_csv), sum(1 for c in _csv if c in items),
         SS.extras_missing(_csv, items).__len__()))

print('\n-- 已补 978 只的来源与覆盖率 --')
print('  公告来源分布：', dict(Counter(str(v.get('ann_src') or '?')
                                      for v in items.values() if v.get('ann'))))
print('  有主营=%d ｜ 有公告=%d' % (sum(1 for v in items.values() if v.get('biz')),
                                   sum(1 for v in items.values() if v.get('ann'))))
_dates = Counter(str(v.get('biz_date') or '?') for v in items.values() if v.get('biz'))
print('  主营报告期分布：', dict(_dates.most_common(4)))
print('  缓存文件=%.2f MB' % (os.path.getsize(SS.EXTRAS_PATH) / 1048576.0))

# 请求量与耗时推算（口径写在注释里，全部来自服务层常量）
_ann_iv = SS.ANN_MIN_INTERVAL
_biz_iv = SS.BIZ_MIN_INTERVAL
_todo = SS.extras_missing(_csv, items).__len__()
print('\n-- 一次性补满的推算（以 %d 只为上限）--' % _todo)
print('  限速常量：公告 %.2fs/次（三源共用桶）｜主营 %.2fs/次' % (_ann_iv, _biz_iv))
print('  最坏请求数 ≈ 主营 %d + 公告 %d（东财被限后走新浪 1 次/只）= 约 %d 次'
      % (_todo, _todo, _todo * 2))
print('  纯限速耗时下限 ≈ 公告 %.0f 秒 + 主营 %.0f 秒'
      % (_todo * _ann_iv, _todo * _biz_iv))
print('  熔断：连续 %d 只「主营+公告都失败」即停手' % 12)
print('  失败退避：%d 分钟' % (SS.ANN_FAIL_COOLDOWN / 60))
