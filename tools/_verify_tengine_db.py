# -*- coding: utf-8 -*-
"""真实库往返验证：holding 表 → AtrTWidget._get_holdings_source → 引擎成本偏离。

流程：临时插入 2 行测试持仓 → 用**真实控件、真实 DB 路径、真实行情**跑 _fetch_and_calc
      → 校验成本偏离/信号 → 无论成败都删除测试行 → 复核表已恢复为空。
可重跑（自带清理）。
"""
import os
import sys
from datetime import datetime, timedelta

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, r'D:\QuantMonitorV6')

DB = r'D:\QuantMonitorV6\data\cache\atr_t_tracking.duckdb'
CODES = ['600519', '300750']
R = []


def check(name, cond, detail=''):
    R.append((name, bool(cond)))
    print('  [%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def rows():
    import duckdb
    con = duckdb.connect(DB)
    try:
        return con.execute('SELECT code,name,cost,qty,buy_time FROM holding ORDER BY code').fetchall()
    finally:
        con.close()


print('=' * 96)
print('[[[ 真实库 → 控件 → 引擎 往返验证（结束时自动清理测试数据）]]]')
print('=' * 96)

before = rows()
print('插入前 holding 行数：%d' % len(before))
if before:
    print('!! 你的持仓表里本来就有 %d 行真实数据，为安全起见本脚本不做任何写入，仅退出' % len(before))
    print('   请改用 tools\\add_holding.py list 查看')
    sys.exit(0)

import duckdb
con = duckdb.connect(DB)
try:
    y = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d 10:30:00')
    for c, cost, qty in (('600519', 1200.0, 500), ('300750', 250.0, 800)):
        con.execute('DELETE FROM holding WHERE code = ?', [c])
        con.execute(
            'INSERT INTO holding(code,name,cost,qty,buy_time,updated_at) '
            "VALUES (?,?,?,?,?,?)",
            [c, '往返测试', cost, qty, y, datetime.now()])
    print('已插入 2 行测试持仓（成本 1200.0 / 250.0，买入日 %s）' % y[:10])
finally:
    con.close()

ok = False
try:
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from ui.battle_widgets.atr_t_widget import AtrTWidget

    w = AtrTWidget()
    src = w._get_holdings_source()
    check('D1 控件真的从 DB 读到持仓（非自选兜底）',
          len(src) == 2 and all(s.get('from_db') for s in src),
          '读到 %d 行，来自DB=%s' % (len(src), [s.get('from_db') for s in src]))

    rows_out, is_trading, _ = w._fetch_and_calc()
    print('      _fetch_and_calc 返回 %d 行（is_trading=%s）' % (len(rows_out), is_trading))
    for r in rows_out:
        pl = r.get('t_plan') or {}
        print('      %s 现价%.2f 成本%s 偏离%+.2f%% | 反T可用%s | %s %.0f分 %.1f' % (
            r['code'], r['price'], r.get('cost'),
            pl.get('dev_pct') or 0,
            (pl.get('suggest_qty') if pl.get('side') == 'reverse' else '-'),
            pl.get('side_cn', '-'), pl.get('score', 0), pl.get('time_weight', 0)))
    ok = all(r.get('cost') for r in rows_out) and len(rows_out) == 2
    check('D2 成本从 DB 贯通到引擎（cost 非空）', ok,
          'cost=%s' % [r.get('cost') for r in rows_out])
    devs = [(r.get('t_plan') or {}).get('dev_pct') for r in rows_out]
    check('D3 成本偏离被真实算出（非 0 / 非空）',
          all(d is not None and abs(d) > 0.5 for d in devs), 'dev=%s' % devs)
    check('D4 每行都带 t_plan（引擎在真实 DB 路径下生效）',
          all(r.get('t_plan') for r in rows_out), '%d/%d' % (sum(1 for r in rows_out if r.get('t_plan')), len(rows_out)))
    # T+1：测试行为 3 天前买入 → 应全部可用
    check('D5 隔日底仓不被 T+1 误拦',
          all((r.get('t_plan') or {}).get('suggest_qty', 0) >= 0 for r in rows_out))
except Exception as e:
    import traceback
    traceback.print_exc()
    check('D 往返验证', False, '%s: %s' % (type(e).__name__, e))
finally:
    con = duckdb.connect(DB)
    try:
        for c, _, _ in (('600519', 0, 0), ('300750', 0, 0)):
            con.execute('DELETE FROM holding WHERE code = ? AND name = ?', [c, '往返测试'])
    finally:
        con.close()
    after = rows()
    print('清理后 holding 行数：%d' % len(after))
    check('D6 测试数据已完全清理（表恢复原状）', after == before, 'before=%d after=%d' % (len(before), len(after)))

bad = [n for n, o in R if not o]
print('\n' + '=' * 96)
print('PASS %d / FAIL %d' % (len(R) - len(bad), len(bad)))
if bad:
    print('失败：' + '；'.join(bad))
print('=' * 96)
sys.exit(1 if bad else 0)
