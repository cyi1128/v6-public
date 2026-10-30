# -*- coding: utf-8 -*-
"""导出 69 只涨停股的 板数 / 封成比 / 封板时段 / 烂板标记，供画图。"""
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')
from services.board_anomaly_engine import (_load_limit_up, _seal_ratio,  # noqa
                                          _is_rotten, _seal_slot)

ludate, recs = _load_limit_up()
recs.sort(key=lambda r: (r.get('lbc') or 0, -_seal_ratio(r)))
print('日期 %s  共 %d 只' % (ludate, len(recs)))
print('%-9s %3s %9s %8s %-8s %s' % ('名称', '板', '封成比', '成交亿', '时段', '烂板'))
for r in recs:
    print('%-9s %3d %9.3f %8.2f %-8s %s'
          % (r['name'], r.get('lbc') or 0, _seal_ratio(r),
             (r.get('amount') or 0) / 1e8, _seal_slot(r.get('time'))[1],
             '×' if _is_rotten(r) else ''))
