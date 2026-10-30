# -*- coding: utf-8 -*-
"""验证「扫描前补当日K线」这条链路（可重跑）。离屏跑，不弹窗。

覆盖：
  A. 服务层 services.kline_cache_service.seed_today_bar
     A1 正常执行：写库成功、rows 真的进了 kline_cache（date=今天）、meta 同步
     A2 非交易时段：被打回、且不写任何行
     A3 停牌/无成交代码：跳过不写假 bar
  B. 页面层 ControlScreenWidget
     B1 「补当日K线」开关存在、默认勾选、有 tooltip、挂在 bar1
     B2 扫描流程里确实先调 seed_today_bar 再 load_all_bars（源码顺序 + 真实跑一次）
     B3 取消勾选后扫描照常工作、不出现补数文案（真跑一次）
"""
import os
import sys
import time

sys.path.insert(0, r'D:\QuantMonitorV6')
os.chdir(r'D:\QuantMonitorV6')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import duckdb  # noqa: E402

DB = 'data/cache/kline_cache.duckdb'
TODAY = time.strftime('%Y-%m-%d')
P, F = [], []


def ck(name, cond, extra=''):
    (P if cond else F).append(name)
    print('%s %s %s' % ('PASS' if cond else 'FAIL', name, extra), flush=True)


def q(sql, args=None):
    c = duckdb.connect(DB, read_only=True)
    try:
        return c.execute(sql, args or []).fetchall()
    finally:
        c.close()


# ============================ A. 服务层 ============================
print('=' * 70)
print('A. seed_today_bar 服务层')
from services.kline_cache_service import seed_today_bar  # noqa: E402

codes = ['600519', '000811', '002838', '300750', '603011']
before = q('SELECT COUNT(DISTINCT code) FROM kline_cache WHERE date = ?', [TODAY])[0][0]
r = seed_today_bar(codes=codes)
after = q('SELECT COUNT(DISTINCT code) FROM kline_cache WHERE date = ?', [TODAY])[0][0]
ck('A1 ok=True', r.get('ok') is True, str(r.get('reason') or ''))
ck('A1 请求/行情/写入 对得上', r.get('requested') == len(codes) and r.get('written') >= 3,
   'requested=%s quotes=%s written=%s' % (r.get('requested'), r.get('quotes'), r.get('written')))
rows = q('SELECT code, date, open, high, low, close, volume FROM kline_cache '
         "WHERE date = ? AND code IN ('600519','000811') ORDER BY code", [TODAY])
ck('A1 库里真有今天的行', len(rows) == 2, str(rows))
if rows:
    _c, _d, _o, _h, _l, _cl, _v = rows[0]
    ck('A1 日期=今天 + OHLC 合理', _d == TODAY and _l <= _cl <= _h and _o > 0,
       'date=%s o=%s h=%s l=%s c=%s v=%s' % (_d, _o, _h, _l, _cl, _v))
    ck('A1 volume 是股不是手', _v > 1e6, 'volume=%s' % _v)
meta = q("SELECT last_date, source FROM kline_cache_meta WHERE code='600519'")
ck('A1 meta 已同步', bool(meta) and meta[0][0] == TODAY, str(meta))
ck('A1 before/after 计数正确', r.get('before') == before and r.get('after') >= after,
   'before=%s/%s after=%s/%s' % (r.get('before'), before, r.get('after'), after))

# A2 非交易时段：把 trade_calendar.is_market_open 临时打成 False
import utils.trade_calendar as TC  # noqa: E402
_orig = TC.is_market_open
TC.is_market_open = lambda *a, **k: False
try:
    n0 = q('SELECT COUNT(*) FROM kline_cache WHERE date = ?', [TODAY])[0][0]
    r2 = seed_today_bar(codes=codes)
    n1 = q('SELECT COUNT(*) FROM kline_cache WHERE date = ?', [TODAY])[0][0]
finally:
    TC.is_market_open = _orig
ck('A2 非交易时段被打回', r2.get('ok') is False and '非交易时段' in (r2.get('reason') or ''),
   str(r2.get('reason')))
ck('A2 且没写任何行', n0 == n1, '%s -> %s' % (n0, n1))
ck('A2 开关恢复后能再跑', TC.is_market_open is _orig)

# A3 不存在的代码 → 跳过不写
r3 = seed_today_bar(codes=['999999'])
ck('A3 无行情代码不写假 bar', r3.get('written', 0) == 0 and r3.get('skipped_quote', 0) == 1,
   str(r3))

# ============================ B. 页面层 ============================
print('=' * 70)
print('B. ControlScreenWidget 接入')
_src = open('ui/battle_widgets/control_screen_widget.py', encoding='utf-8').read()
ck('B1 开关存在且默认勾选', "_ck_seed = QCheckBox('补当日K线')" in _src
   and '_ck_seed.setChecked(True)' in _src)
ck('B1 有说明 tooltip', '_ck_seed.setToolTip(' in _src and 'WAF' in _src and '09:15~15:05' in _src)
_i_seed, _i_scan, _i_bars = (_src.index('bar1.addWidget(self._ck_seed)'),
                             _src.index('def _start_scan'),
                             _src.index('bars = SS.load_all_bars()', _src.index('def _start_scan')))
ck('B1 开关挂进 bar1 且在扫描按钮之前', _i_seed < _i_scan < _i_bars)
ck('B2 扫描任务里先补数、再读K线',
   'seed_today_bar(progress_cb=_p)' in _src and _src.index('seed_today_bar(progress_cb=_p)') < _i_bars)
ck('B2 补数失败/关闭都不影响扫描', '_r.get(\'ok\')' in _src and 'except Exception as _e' in _src
   and 'if _seed_on:' in _src)

from PyQt6.QtWidgets import QApplication  # noqa: E402
app = QApplication.instance() or QApplication([])
from ui.battle_widgets.control_screen_widget import ControlScreenWidget  # noqa: E402

w = ControlScreenWidget()
try:
    w._ck_auto.setChecked(False)
    w._ck_extra.setChecked(False)
except Exception:
    pass
w.resize(1600, 800)
w.show()
for _ in range(10):
    app.processEvents()
ck('B1 实例上开关存在且默认勾选', w._ck_seed.isChecked() and '09:15' in w._ck_seed.toolTip())


def _wait_scan(limit=240):
    t0 = time.time()
    while w._scanning and time.time() - t0 < limit:
        app.processEvents()
        time.sleep(0.2)
    for _ in range(8):
        app.processEvents()
    return time.time() - t0


# B2 真跑一次（勾选补数）
w._ck_seed.setChecked(True)
w._start_scan()
_dt = _wait_scan()
_st = w._count_label.text()
ck('B2 扫描跑完', (not w._scanning) and w.table.rowCount() > 0,
   '耗时 %.0fs 行数=%d' % (_dt, w.table.rowCount()))
ck('B2 统计条带今天的数据日', TODAY in _st, _st)
snap_date = w._stats.get('data_date')
ck('B2 扫描结果数据日=今天', snap_date == TODAY, 'data_date=%s' % snap_date)

# B3 关掉开关再扫一次：不应出现补数动作
w._ck_seed.setChecked(False)
_t_off = time.time()
w._start_scan()
_wait_scan()
_dt_off = time.time() - _t_off
ck('B3 关闭开关后扫描照常', (not w._scanning) and w.table.rowCount() > 0,
   '耗时 %.0fs（关掉补数应明显更快）' % _dt_off)
ck('B3 关闭开关时不跑补数', _dt_off < max(_dt - 10, 20),
   '补数 %.0fs vs 不补 %.0fs' % (_dt, _dt_off))
w.close()

print('=' * 70)
print('结果：%d PASS / %d FAIL' % (len(P), len(F)))
if F:
    print('失败项:', F)
print('=' * 70)
sys.exit(1 if F else 0)
