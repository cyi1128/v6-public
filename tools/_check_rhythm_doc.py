# -*- coding: utf-8 -*-
"""核对 docs/市场节奏_三Tab思路逻辑.md 里写到的每一个常量。"""
import io
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')

import services.market_rhythm_engine as M        # noqa: E402
import services.board_anomaly_engine as B        # noqa: E402
import services.picks_tracking_service as T      # noqa: E402

bad = 0


def chk(desc, got, want):
    global bad
    ok = got == want
    if not ok:
        bad += 1
    print('  %s %-42s 实际=%r 文档=%r' % ('OK ' if ok else 'NOT', desc, got, want))


print('--- market_rhythm_engine ---')
chk('MIN_STOCK 成板块家数', M.MIN_STOCK, 2)
chk('MEMORY_DAYS 题材记忆回看', M.MEMORY_DAYS, 10)
chk('CACHE_TTL 结果缓存秒', M.CACHE_TTL, 60.0)
chk('KW_MIN', M.KW_MIN, 2)
chk('KW_MAX', M.KW_MAX, 12)
chk('ATTRIBUTE_WORDS 数量', len(M.ATTRIBUTE_WORDS), 40)
chk('STOPWORDS 数量', len(M.STOPWORDS), 35)
chk('MAINLINE 主线条数', len(M.MAINLINE), 15)
chk('_STATE_RANK[发酵中]', M._STATE_RANK[M.ST_FERMENT], 0)
chk('_STATE_RANK[持续]', M._STATE_RANK[M.ST_KEEP], 0)
chk('_STATE_RANK[首日启动]', M._STATE_RANK[M.ST_NEW], 1)
chk('_STATE_RANK[复活]', M._STATE_RANK[M.ST_REVIVE], 1)
chk('_STATE_RANK[高潮]', M._STATE_RANK[M.ST_CLIMAX], 1)
chk('_STATE_RANK[退潮]', M._STATE_RANK[M.ST_FADE], 3)
chk('_STATE_RANK[零星]', M._STATE_RANK[M.ST_SCATTER], 4)
chk('_STATE_RANK[熄火]', M._STATE_RANK[M.ST_DIE], 5)
for c, want in (('600000', True), ('601111', True), ('603000', True),
                ('605000', True), ('000001', True), ('001000', True),
                ('002000', True), ('003000', True), ('300001', False),
                ('688001', False), ('830000', False), ('430000', False)):
    chk('is_main_board(%s)' % c, M.is_main_board(c), want)

print()
print('--- board_anomaly_engine ---')
chk('_TTL 结果缓存秒', B._TTL, 90.0)
chk('_RT_TTL 实时行情缓存', B._RT_TTL, 60.0)
chk('_POOL_TTL 成分池缓存', B._POOL_TTL, 600.0)
chk('_MIN_STOCK', B._MIN_STOCK, 2)
chk('_PICK_MIN_PCT 候选涨幅下限', B._PICK_MIN_PCT, 1.0)
chk('_PICK_MAX_PCT 候选涨幅上限', B._PICK_MAX_PCT, 9.0)
chk('_PICK_MIN_VR 候选量比下限', B._PICK_MIN_VR, 1.2)
chk('_PICK_MIN_PRICE 候选股价下限', B._PICK_MIN_PRICE, 6.0)
chk('_PICK_TOP 每题最多展示', B._PICK_TOP, 5)

print()
print('--- picks_tracking_service ---')
chk('PICK_MIN_PCT', T.PICK_MIN_PCT, 1.0)
chk('PICK_MAX_PCT', T.PICK_MAX_PCT, 9.0)
chk('PICK_MIN_VR', T.PICK_MIN_VR, 1.2)
chk('PICK_MIN_PRICE', T.PICK_MIN_PRICE, 6.0)
chk('LIMIT_UP_PCT 涨停判定', T.LIMIT_UP_PCT, 9.5)
chk('BACKFILL_DAYS 回填交易日', T.BACKFILL_DAYS, 70)
chk('TRACK_KEEP_DAYS 保留自然日', T.TRACK_KEEP_DAYS, 100)
chk('BOARD_MIN_STOCK 回填板块门槛', T.BOARD_MIN_STOCK, 2)
chk('_PICK_TOP', T._PICK_TOP, 5)

print()
print('--- widget 关键代码片段 ---')
s = io.open(r'D:\QuantMonitorV6\ui\battle_widgets\market_rhythm_widget.py',
            encoding='utf-8').read()
for frag in ('GRID = [112, 84, 98, 62, 48, 52, 122, 330, 205, 180]',
             'P_GRID = [104, 46, 100, 150, 340, 240]',
             '_PUSH_MIN_STOCK = 3',
             '_PUSH_COOLDOWN = 1800',
             'start_refresh(60000)',
             'TREND_DAYS = 10',
             "'市场节奏', '可介入', '追踪'",
             'self._track_widget.stop_timer()',
             "仅按涨停原因聚合，未确认资金性质"):
    ok = frag in s
    if not ok:
        bad += 1
    print('  %s %s' % ('OK ' if ok else 'NOT', frag[:62]))

print()
print('--- Tab1 表头 ---')
hdr = "题材 主线 状态 今/昨 连续 最高板 龙头 题材内强势股 近10日家数 同簇题材".split()
ok = len(hdr) == 10 and all(h in s for h in hdr)
if not ok:
    bad += 1
print('  %s 10 列表头 %s' % ('OK ' if ok else 'NOT', hdr))

print()
print('结论: %s' % ('全部命中 ✓' if bad == 0 else '%d 项不符 ✗' % bad))
sys.exit(0 if bad == 0 else 1)
