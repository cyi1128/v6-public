# -*- coding: utf-8 -*-
"""A 项（服务层）改动后的即时自检：编译 + 真股票跑 compute_stock + 阶段筛选 + 词表一致性。"""
import os
import sys
import py_compile
import tempfile

sys.path.insert(0, r'D:\QuantMonitorV6')
os.chdir(r'D:\QuantMonitorV6')

_tmp = tempfile.mkdtemp()
for f in ('services/control_profile.py', 'services/control_screen_service.py'):
    py_compile.compile(f, cfile=os.path.join(_tmp, os.path.basename(f) + 'c'), doraise=True)
print('[1] 编译通过：control_profile.py / control_screen_service.py')

from services.control_profile import obs_tag_pairs, obs_stages, STAGE_PICK, TAG_STAGE
import services.control_screen_service as SS
from services.kline_cache_service import get_latest_kline

print('[2] STAGE_PICK =', STAGE_PICK)
print('    TAG_STAGE 条数 =', len(TAG_STAGE))

# 真股票：拿库里已有的、命中过 A/B 或建仓因子的票各来一只
codes = ['600826', '603229', '601378', '300669', '301558', '600085', '600845', '605196']
rows = []
for c in codes:
    bars = get_latest_kline(c, 120)
    if not bars:
        continue
    r = SS.compute_stock(c, bars, name=c)
    if r:
        rows.append(r)

print('[3] 真股票 compute_stock 结果：')
print('    %-8s %-7s %-6s %-9s %-16s %s' % ('代码', '控盘分', '位置', '阶段', '观察标签', 'stages'))
for r in rows:
    print('    %-8s %-7.1f %-6.3f %-9s %-16s %s' % (
        r['code'], r['score'], r['pos'], r['stage'] or '-',
        '·'.join(r['observe']) or '-', ','.join(r['stages']) or '-'))

# note 里应能看到 A/B 与建仓类文案（引擎侧开关为 watch 的才出）
print('[4] note 抽查：')
for r in rows[:3]:
    print('    %s: %s' % (r['code'], (r['note'] or '(空)').replace('\n', ' ')[:150]))

# 阶段筛选
print('[5] 阶段筛选计数（在这一小撮上）：')
for st in STAGE_PICK:
    n = len(SS.apply_filters(rows, min_score=0.0, min_price=0.0, drop_st=False,
                             exclude_dist=False, stage=st))
    print('    %-6s -> %d 只' % (st, n))

# 词表与 UI 侧一致性的最小断言
assert obs_tag_pairs(brk_type='破位未收') == [('破位警示', 'risk')]
assert obs_tag_pairs(vreg_tags='地量') == [('地量', 'info')]
assert obs_tag_pairs(brk_type='洗盘收复', vreg_tags='地量') == [('洗盘收复', 'info'), ('地量', 'info')]
assert obs_tag_pairs(markup_type='阶梯式上行') == [('拉升:阶梯式上行', 'warn')]
assert obs_tag_pairs(probe_ok=True)[0] == ('试盘', 'gold')
assert obs_stages(obs_tag_pairs(stack_ok=True, brk_type='破位未收')) == ['建仓', '出货']
print('[6] 词表断言全部通过')
