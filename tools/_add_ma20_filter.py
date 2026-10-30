# -*- coding: utf-8 -*-
"""
补上 services/band_pattern_engine.py 里那条空注释的 MA20 硬过滤。

原状：L1194 写着 `# MA20硬过滤：MA20下方只能观察不能建仓`，但下面没有任何代码。
      ma20 只在 L1188 被算出来、L1189 判非空、L1225 写进记录，从未参与过滤。

本次按注释原意 + 用户 2026-09-26 确认过的口径实现（不是"跌破就删"）：
      现价 >= MA20  -> 不变
      现价 <  MA20  -> 信号降级为「观察」，不给建仓触发，记录保留做筑底观察
为什么不 return []：模式三「横盘周K」本身就是底部构筑形态，启动前现价贴近
      MA20 甚至短暂在其下方是常态，硬删会误杀正样本。
"""
import io
import os
import shutil
import sys
import py_compile

sys.stdout.reconfigure(encoding='utf-8')
P = r'D:\QuantMonitorV6\services\band_pattern_engine.py'
raw = open(P, 'rb').read()
assert raw.count(b'\r\n') == 0, '本文件应为纯 LF'
s = raw.decode('utf-8')
print('原行数 %d' % len(s.splitlines()))


def rep(old, new, desc, cnt=1):
    global s
    n = s.count(old)
    assert n == cnt, '[%s] 锚点命中 %d 次，期望 %d 次' % (desc, n, cnt)
    s = s.replace(old, new)
    print('  ✓ %s' % desc)


# ---------- 1. 补实现 ----------
rep(
"""        # MA20硬过滤：MA20下方只能观察不能建仓
        today_str = today['date'][:10]
""",
"""        # MA20 硬过滤（V15，2026-10-09 补实现）。
        # 原为一条空注释 —— ma20 只被算出来、判非空、写进记录，从未参与过滤。
        # 口径（用户 2026-09-26 确认的版本，不是"跌破就删"）：
        #   现价 >= MA20  -> 不变
        #   现价 <  MA20  -> 信号降级为「观察」，不产生建仓触发（记录保留做筑底观察）
        # 为什么不直接 return []：模式三「横盘周K」本就是底部构筑形态，
        # 启动前现价贴近 MA20 甚至短暂在其下方是常态，硬删会误杀正样本。
        _below_ma20 = today['close'] < ma20
        today_str = today['date'][:10]
""",
    '补 MA20 判定 + 说明')

# ---------- 2. 落库前降级 ----------
rep(
"""            _save_or_update(rec)
            found.append(rec)""",
"""            # MA20 降级：现价在 20 日均线下方 -> 只观察，不给建仓触发
            # （等待确认档本来就不能买，不受影响；只针对已经给出的建仓触发）
            if _below_ma20 and rec['signal_level'] == LVL_TRIGGER:
                rec['signal_level'] = LVL_WATCH
                rec['trigger_type'] = 'MA20下方·筑底观察'
                _fn = (_M1_FUNNEL if fn is detect_pattern_aggressive
                       else _M4_FUNNEL)
                _fn['trigger'] = max(0, _fn['trigger'] - 1)
                _fn['ma20_below'] += 1
            _save_or_update(rec)
            found.append(rec)""",
    'scan_stock 内降级逻辑')

# ---------- 3. 两个漏斗字典加计数键 ----------
rep(
"""_M4_FUNNEL = {'wk': 0, 'struct': 0, 'trigger': 0, 'invalid': 0, 'theme': 0,
               'entry_far': 0}""",
"""_M4_FUNNEL = {'wk': 0, 'struct': 0, 'trigger': 0, 'invalid': 0, 'theme': 0,
               'entry_far': 0, 'ma20_below': 0}""",
    '模式三漏斗字典加 ma20_below')

rep(
"""_M1_FUNNEL = {'s_ok': 0, 'd_ok': 0, 'struct': 0, 'trigger': 0, 'theme': 0,
               'entry_far': 0}""",
"""_M1_FUNNEL = {'s_ok': 0, 'd_ok': 0, 'struct': 0, 'trigger': 0, 'theme': 0,
               'entry_far': 0, 'ma20_below': 0}""",
    '模式一漏斗字典加 ma20_below')

# ---------- 4. 漏斗打印加一行 ----------
rep(
"""            print(f'  建仓价距现价>{_ENTRY_GAP_CAP}%剔除              : {_f1["entry_far"]}', flush=True)""",
"""            print(f'  建仓价距现价>{_ENTRY_GAP_CAP}%剔除              : {_f1["entry_far"]}', flush=True)
            print(f'  现价<MA20降级为观察                    : {_f1["ma20_below"]}', flush=True)""",
    '模式一漏斗加 MA20 行')

rep(
"""            print(f'  建仓价距现价>{_ENTRY_GAP_CAP}%剔除    : {f["entry_far"]}', flush=True)""",
"""            print(f'  建仓价距现价>{_ENTRY_GAP_CAP}%剔除    : {f["entry_far"]}', flush=True)
            print(f'  现价<MA20降级为观察      : {f["ma20_below"]}', flush=True)""",
    '模式三漏斗加 MA20 行')

shutil.copy2(P, P + '.bak_before_ma20')
open(P, 'wb').write(s.encode('utf-8'))
print('\n已写入 %s (%d bytes, %d 行)' % (P, os.path.getsize(P), len(s.splitlines())))
py_compile.compile(P, doraise=True)
print('py_compile OK')
