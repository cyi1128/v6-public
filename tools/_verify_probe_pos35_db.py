# -*- coding: utf-8 -*-
"""用真实数据独立复核「试盘 pos 门槛 0.35」是否在库内生效（只读）

做法：不调用 detect_probe，直接从 kline_cache.duckdb 取每个记录对应股票的最近 120 根收盘，
按 pos = (close[-1] - min120) / (max120 - min120) 独立算一遍，然后断言：
  A. 每条 probe_ok=1 的记录，其 pos120 必 < 0.35    （门槛在真实数据上生效）
  B. 每条 pos120 ∈ [0.35, 0.75) 的记录，probe_ok 必 = 0（旧的 0.35~0.75 段确实被拦掉）
  C. 出货形态记录数、分型与上一版扫描日志逐项一致（未被本次改动牵连）
"""
import io
import sqlite3
import sys

import duckdb

sys.path.insert(0, r'D:\QuantMonitorV6')

DB_PAT = r'D:\QuantMonitorV6\data\cache\band_pattern.db'
DB_K = r'D:\QuantMonitorV6\data\cache\kline_cache.duckdb'
LOG_NEW = r'D:\QuantMonitorV6\tools\_scan_after_probe_pos35.log'
LOG_OLD = r'D:\QuantMonitorV6\tools\_scan_after_probedist.log'

OUT = []
PASS = [0]
FAIL = [0]


def p(line=''):
    OUT.append(line)
    print(line, flush=True)


def ck(cond, msg, extra=''):
    if cond:
        PASS[0] += 1
        p('  PASS  %s %s' % (msg, extra))
    else:
        FAIL[0] += 1
        p('  FAIL  %s %s' % (msg, extra))


p('=' * 96)
p('试盘 pos 门槛 0.35 —— 库内真实数据独立复核')
p('=' * 96)

con = sqlite3.connect(DB_PAT)
rows = con.execute(
    'SELECT code, name, pattern_id, probe_ok, probe_score, dist_pattern_ok, '
    'dist_pattern_type, signal_level, note FROM pattern_record'
).fetchall()
p('库内记录 %d 条' % len(rows))

kc = duckdb.connect(DB_K, read_only=True)
pos_map = {}
for code, name, pid, pok, ps, dok, dtype, sl, note in rows:
    d = kc.execute(
        'SELECT close FROM kline_cache WHERE code = ? ORDER BY date DESC LIMIT 120',
        [code]).fetchall()
    if len(d) < 2:
        pos_map[code] = None
        continue
    cl = [float(x[0]) for x in d][::-1]      # 升序：最后一根 = 最新交易日
    lo, hi = min(cl), max(cl)
    pos_map[code] = (cl[-1] - lo) / (hi - lo + 1e-12)

p('可独立算 pos120 的记录 %d 条（K线不足的 %d 条）'
  % (sum(1 for v in pos_map.values() if v is not None),
     sum(1 for v in pos_map.values() if v is None)))

probe_rows = [r for r in rows if r[3] == 1]
notprobe_in_band = [r for r in rows
                    if r[3] != 1 and pos_map.get(r[0]) is not None
                    and 0.35 <= pos_map[r[0]] < 0.75]

p('')
p('[A] probe_ok=1 的记录（应全部 pos120 < 0.35）')
for r in sorted(probe_rows, key=lambda x: pos_map.get(x[0]) or 9):
    v = pos_map.get(r[0])
    p('    %s %-6s 模式%s pos120=%s probe_score=%.1f level=%s'
      % (r[0], r[1], r[2], ('%.4f' % v) if v is not None else '无K线',
         float(r[4] or 0), r[7]))
bad = [r[0] for r in probe_rows if (pos_map.get(r[0]) or 0) >= 0.35]
ck(not bad, 'probe_ok=1 的记录 pos120 全部 < 0.35（门槛在真实数据上生效）',
   '越界 %s' % bad[:5])

p('')
p('[B] pos120 落在 0.35~0.75（旧门槛会放行、新门槛要拦掉）的记录')
p('    共 %d 条，它们的 probe_ok 必须全部 = 0' % len(notprobe_in_band))
for r in notprobe_in_band[:8]:
    p('    %s %-6s pos120=%.4f probe_ok=%s' % (r[0], r[1], pos_map[r[0]], r[3]))
bad2 = [r[0] for r in notprobe_in_band if r[3] == 1]
ck(not bad2, '0.35~0.75 区间的记录没有任何一条带试盘命中', '异常 %s' % bad2[:5])

p('')
p('[C] 与改动前那一版扫描日志逐项比对（证明只影响试盘这一条）')
old = io.open(LOG_OLD, 'r', encoding='utf-8', errors='ignore').read()
new = io.open(LOG_NEW, 'r', encoding='utf-8', errors='ignore').read()
for tag, txt in (('旧', old), ('新', new)):
    line = [x for x in txt.splitlines() if x.startswith('[出货形态] 可算')]
    p('    %s：%s' % (tag, line[0] if line else '(缺)'))
    line2 = [x for x in txt.splitlines() if x.startswith('[试盘观察] 通过K线门槛')]
    p('    %s：%s' % (tag, line2[0] if line2 else '(缺)'))

for key in ('放量滞涨', '双顶雏形', '命中合计'):
    o = [x for x in old.splitlines() if x.startswith('[出货形态] 可算')][0]
    n = [x for x in new.splitlines() if x.startswith('[出货形态] 可算')][0]
    o_val = o.split(key)[1].split('｜')[0].strip() if key in o else '?'
    n_val = n.split(key)[1].split('｜')[0].strip() if key in n else '?'
    ck(o_val == n_val, '出货形态「%s」新旧一致' % key, '%s -> %s' % (o_val, n_val))

cnt_dist = sum(1 for r in rows if r[5] == 1)
ck(cnt_dist == 15, '出货形态记录数仍是 15 条', '实际 %d' % cnt_dist)
ck(all(r[6] == '双顶雏形' for r in rows if r[5] == 1),
   '出货形态分型仍是清一色双顶雏形（未受牵连）')
ck(len(rows) == 230, '总记录数仍是 230 条（模式一/二/三完全没动）', '实际 %d' % len(rows))
ck(sum(1 for r in rows if r[3] == 1) == 5, '试盘命中由 7 条降到 5 条',
   '实际 %d' % sum(1 for r in rows if r[3] == 1))
ck(all(('试盘观察' in (r[8] or '')) == (r[3] == 1) for r in rows),
   'probe_ok 与 note 里的试盘文案仍逐条一致')

kc.close()
p('')
p('=' * 96)
p('总计：PASS %d ｜ FAIL %d' % (PASS[0], FAIL[0]))
p('=' * 96)

io.open(r'D:\QuantMonitorV6\tools\probe_pos35_db.txt', 'w', encoding='utf-8').write('\n'.join(OUT))
sys.exit(1 if FAIL[0] else 0)
