# -*- coding: utf-8 -*-
"""分时做T 持仓表（cost/qty）录入工具 —— 机构级做T标准①「持仓成本偏离」的前置数据源。

背景：项目里 holding 表此前**没有任何写入方**（无 UI、无 INSERT），所以模块的
成本偏离永远算不出来（cost=None → 按中性处理）。本工具补上这个入口。

用法（在项目根目录，**先关掉主程序**，DuckDB 被占用时会直接报错）：
    python tools\\add_holding.py list
    python tools\\add_holding.py add 600519 1200.5 500
    python tools\\add_holding.py add 300750 250.0 300 --buy-time "2026-10-09 10:30:00"
    python tools\\add_holding.py add 000001 11.00 2000 --qty-avail 1000
    python tools\\add_holding.py remove 600519
    python tools\\add_holding.py clear            # 清空（会二次确认）

注意：
  · 不传 --buy-time → 引擎按「全部可用」处理（宽松）；若是**今天买的**，
    务必传成交时间，否则反T 可能卖出当日买入股（T+1 违规）。
  · 同一代码重复 add 为覆盖更新（PRIMARY KEY = code）。
"""
import argparse
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(ROOT, 'data', 'cache', 'atr_t_tracking.duckdb')


def _resolve_name(code):
    try:
        sys.path.insert(0, ROOT)
        from utils.http_market_data import get_realtime_quotes_http
        d = (get_realtime_quotes_http([code]) or {}).get(code) or {}
        return d.get('name') or code
    except Exception:
        return code


def _conn(db):
    import duckdb
    con = duckdb.connect(db)
    con.execute("""
        CREATE TABLE IF NOT EXISTS holding(
            code TEXT PRIMARY KEY, name TEXT, cost DOUBLE, qty INTEGER,
            buy_time TIMESTAMP, exec_buy DOUBLE, exec_sell DOUBLE,
            anchor_vwap DOUBLE, updated_at TIMESTAMP)
    """)
    return con


def _fields():
    return ['code', 'name', 'cost', 'qty', 'buy_time', 'exec_buy',
            'exec_sell', 'anchor_vwap', 'updated_at', 'qty_avail']


def _ensure_qty_avail(con):
    """兼容性补齐：qty_avail 列（可选，用于手工指定可用量）。"""
    try:
        cols = [r[1] for r in con.execute('PRAGMA table_info(holding)').fetchall()]
        if 'qty_avail' not in cols:
            con.execute('ALTER TABLE holding ADD COLUMN qty_avail INTEGER')
            return True
    except Exception:
        pass
    return False


def cmd_list(con):
    _ensure_qty_avail(con)
    rows = con.execute(
        'SELECT code, name, cost, qty, qty_avail, buy_time, updated_at '
        'FROM holding ORDER BY code').fetchall()
    if not rows:
        print('holding 表为空 —— 引擎目前按「无成本」处理（成本偏离维度不生效）')
        return 0
    print('%-8s %-10s %10s %8s %8s  %-20s %s' % ('代码', '名称', '成本', '数量', '可用', '买入时间', '更新时间'))
    for c, n, cost, qty, qa, bt, up in rows:
        print('%-8s %-10s %10.3f %8s %8s  %-20s %s' % (
            c, (n or '')[:10], float(cost or 0), qty if qty is not None else '-',
            qa if qa is not None else '-', str(bt or '-'), str(up or '-')))
    print('合计 %d 只' % len(rows))
    return 0


def cmd_add(con, a):
    _ensure_qty_avail(con)
    code = a.code.strip()
    if len(code) != 6 or not code.isdigit():
        print('代码格式应为 6 位数字：%s' % code)
        return 2
    name = a.name or _resolve_name(code)
    bt = a.buy_time
    if bt:
        try:
            bt = datetime.strptime(bt.replace('/', '-'), '%Y-%m-%d %H:%M:%S')
        except ValueError:
            try:
                bt = datetime.strptime(bt.replace('/', '-'), '%Y-%m-%d')
            except ValueError:
                print('buy-time 格式应为 "YYYY-MM-DD HH:MM:SS" 或 "YYYY-MM-DD"')
                return 2
    con.execute('DELETE FROM holding WHERE code = ?', [code])
    con.execute(
        'INSERT INTO holding(code,name,cost,qty,qty_avail,buy_time,updated_at) '
        'VALUES (?,?,?,?,?,?,?)',
        [code, name, float(a.cost), int(a.qty), (int(a.qty_avail) if a.qty_avail is not None else None),
         bt, datetime.now()])
    today = datetime.now().strftime('%Y-%m-%d')
    warn = ''
    if bt is None:
        warn = '  ⚠ 未填 --buy-time → 引擎按「全部可用」处理；若是今日买入请补上成交时间'
    elif str(bt.strftime('%Y-%m-%d')) == today:
        warn = '  ⚠ 成交日为今天 → 反T 会按 T+1 被拦下（当日买入不可卖）'
    print('已写入：%s %s 成本 %.3f 数量 %d%s' % (code, name, float(a.cost), int(a.qty), warn))
    return 0


def cmd_remove(con, code):
    n = con.execute('SELECT count(*) FROM holding WHERE code = ?', [code]).fetchone()[0]
    con.execute('DELETE FROM holding WHERE code = ?', [code])
    print('已删除 %s（命中 %d 行）' % (code, n))
    return 0


def cmd_clear(con):
    n = con.execute('SELECT count(*) FROM holding').fetchone()[0]
    ans = input('确认清空 holding 表 %d 行？输入 YES 继续：' % n)
    if ans.strip() != 'YES':
        print('已取消')
        return 0
    con.execute('DELETE FROM holding')
    print('已清空 %d 行' % n)
    return 0


def main():
    ap = argparse.ArgumentParser(description='分时做T 持仓表录入')
    ap.add_argument('--db', default=DEFAULT_DB)
    sub = ap.add_subparsers(dest='cmd')

    sub.add_parser('list')
    p = sub.add_parser('add')
    p.add_argument('code')
    p.add_argument('cost', type=float)
    p.add_argument('qty', type=int)
    p.add_argument('--name', default='')
    p.add_argument('--buy-time', dest='buy_time', default=None)
    p.add_argument('--qty-avail', dest='qty_avail', type=int, default=None)
    r = sub.add_parser('remove')
    r.add_argument('code')
    sub.add_parser('clear')

    a = ap.parse_args()
    if not a.cmd:
        ap.print_help()
        return 0
    print('DB: %s' % a.db)
    try:
        con = _conn(a.db)
    except Exception as e:
        print('打开数据库失败（主程序可能在运行，DuckDB 独占）：%s: %s' % (type(e).__name__, e))
        return 1
    try:
        if a.cmd == 'list':
            return cmd_list(con)
        if a.cmd == 'add':
            return cmd_add(con, a)
        if a.cmd == 'remove':
            return cmd_remove(con, a.code)
        if a.cmd == 'clear':
            return cmd_clear(con)
    finally:
        try:
            con.close()
        except Exception:
            pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
