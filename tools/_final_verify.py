# -*- coding: utf-8 -*-
"""终验：1) expire_overdue 只作用于模式四且真实生效  2) UI 取数+过滤+题材链路"""
import sys, sqlite3
sys.path.insert(0, r'D:\QuantMonitorV6')
from services.band_pattern_engine import expire_overdue, query_signals

DB = r'D:\QuantMonitorV6\data\cache\band_pattern.db'

# ---------- 1. 自动失效：造一条过期记录，验证只失效模式四 ----------
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
row = con.execute("SELECT * FROM pattern_record WHERE pattern_id=4 AND signal_level='观察' LIMIT 1").fetchone()
assert row, '没有模式四观察记录'
old_valid, old_level, old_reason = row['valid_until'], row['signal_level'], row['invalid_reason']
key = (row['code'], row['pattern_id'], row['base_date'])
con.execute("UPDATE pattern_record SET valid_until='2026-09-01' WHERE code=? AND pattern_id=? AND base_date=?", key)
# 同时造一条模式一的过期记录，验证不会被误伤
row1 = con.execute("SELECT * FROM pattern_record WHERE pattern_id=1 LIMIT 1").fetchone()
key1 = (row1['code'], row1['pattern_id'], row1['base_date'])
old_valid1 = row1['valid_until']
con.execute("UPDATE pattern_record SET valid_until='2026-09-01' WHERE code=? AND pattern_id=? AND base_date=?", key1)
con.commit()
con.close()

n = expire_overdue()
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
after = con.execute("SELECT signal_level, invalid_reason FROM pattern_record WHERE code=? AND pattern_id=? AND base_date=?", key).fetchone()
after1 = con.execute("SELECT signal_level FROM pattern_record WHERE code=? AND pattern_id=? AND base_date=?", key1).fetchone()
print('=== 自动失效验证 ===')
print('  expire_overdue 标记数量:', n, '（应为 1，只失效模式四那条）')
print('  模式四该条 -> %s / %s' % (after['signal_level'], after['invalid_reason']))
print('  模式一该条 -> %s （应保持不变，证明未误伤模式一）' % after1['signal_level'])
# 还原
con.execute("UPDATE pattern_record SET valid_until=?, signal_level=?, invalid_reason=? WHERE code=? AND pattern_id=? AND base_date=?",
            (old_valid, old_level, old_reason) + key)
con.execute("UPDATE pattern_record SET valid_until=? WHERE code=? AND pattern_id=? AND base_date=?", (old_valid1,) + key1)
con.commit()
con.close()
print('  已还原原始数据')

# ---------- 2. UI 取数链路模拟 ----------
print()
print('=== UI 取数链路模拟（与 _daily_fetch_and_calc 同逻辑） ===')
from data.limit_up_reason_db import get_last_limit_up_reason
sigs = query_signals() or []
rows = []
cache = {}
for s in sigs:
    if s.get('signal_level', '') not in ('建仓触发', '等待确认'):
        continue
    code = s['code']
    if code not in cache:
        try:
            _r = get_last_limit_up_reason(code)
            cache[code] = (_r[0] or '') if _r else ''
        except Exception:
            cache[code] = ''
    rows.append((code, s.get('name'), s.get('signal_level'), cache[code]))
print('  表格行数:', len(rows))
print('  前 8 行（代码 / 名称 / 结构状态 / 题材）：')
for r in rows[:8]:
    print('    %s %s [%s] 题材=%s' % (r[0], r[1], r[2], r[3] or '--'))
print('  题材命中数:', sum(1 for r in rows if r[3]), '/', len(rows))
