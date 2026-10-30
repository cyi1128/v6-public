# -*- coding: utf-8 -*-
"""分时做T引擎「接入 widget」验证：静态核对 + 真机功能 + 推送 bug 动态前后对比。

跑法（会真的实例化控件、真的拉行情，离屏模式）：
    set QT_QPA_PLATFORM=offscreen && python tools\_verify_tengine_widget.py
可重跑。
"""
import ast
import os
import sys
import textwrap
from datetime import datetime, timedelta

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, r'D:\QuantMonitorV6')

W = r'D:\QuantMonitorV6\ui\battle_widgets\atr_t_widget.py'
BAK = W + '.bak_before_tengine'
RESULTS = []


def check(name, cond, detail=''):
    RESULTS.append((name, bool(cond), detail))
    print('  [%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def skip(name, why):
    RESULTS.append((name, None, why))
    print('  [SKIP] %s（%s）' % (name, why))


print('=' * 96)
print('[[[ 分时做T引擎 接入 widget 验证 ]]]')
print('=' * 96)

# ============================================================
# A. 静态核对
# ============================================================
print('\n[A] 补丁静态核对')
src = open(W, newline='', encoding='utf-8').read()
old = open(BAK, newline='', encoding='utf-8').read()

naked = src.count('\n') - src.count('\r\n')
check('A1 行尾仍为纯 CRLF（裸LF=0）', naked == 0, '裸LF=%d，总行数=%d' % (naked, src.count('\r\n') + 1))
try:
    compile(src, W, 'exec')
    check('A2 语法可编译', True)
except SyntaxError as e:
    check('A2 语法可编译', False, str(e))

lines = src.split('\r\n')


def find_line(sub):
    return [i + 1 for i, l in enumerate(lines) if sub in l]


l_engine = find_line('机构级分时做T引擎接入')
l_apply_call = find_line('r = self._apply_risk_and_signal(r, in_open_window)')
check('A3 引擎块位于旧判定之后（顺序正确）',
      len(l_engine) == 1 and len(l_apply_call) == 1 and l_engine[0] > l_apply_call[0],
      '引擎块 L%s / 旧判定调用 L%s' % (l_engine, l_apply_call))
check('A4 模块级开关存在且为 True', '_T_ENGINE_AUTHORITATIVE = True' in src)
check('A5 静默 bug 已修（atr=atr 归零 / 新写法 2 处）',
      src.count('atr=atr,') == 0 and src.count("atr=r.get('atr', 0),") == 2,
      '旧=%d 新=%d' % (src.count('atr=atr,'), src.count("atr=r.get('atr', 0),")))
check('A6 备份存在（可一行回退）', os.path.exists(BAK))
# 变量名是否与函数内真实局部名一致（防止 NameError 被 try 吞掉）
blk = '\r\n'.join(lines[l_engine[0] - 1: l_engine[0] + 40])
bad_names = [n for n in ('_q.', '_prev_close', 'bar_high') if n in blk]
check('A7 补丁内变量名与真实局部名一致（q/prev_close/day_high/day_low）',
      not bad_names and 'q.get(' in blk and 'prev_close=prev_close' in blk,
      '误用名 %s' % bad_names if bad_names else 'q / prev_close / day_high / day_low 全部命中')

# ============================================================
# B. 真机功能（离屏 Qt + 真行情 + 真 _fetch_and_calc）
# ============================================================
print('\n[B] 真机功能：离屏实例化控件 → 跑真实 _fetch_and_calc()')
try:
    from PyQt6.QtWidgets import QApplication
    from utils.http_market_data import get_realtime_quotes_http
    app = QApplication.instance() or QApplication(sys.argv)
    from ui.battle_widgets.atr_t_widget import AtrTWidget

    CODES = ['600519', '300750', '000001']
    live = get_realtime_quotes_http(CODES) or {}
    today = datetime.now().strftime('%Y-%m-%d')
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    fake_holdings = []
    for i, c in enumerate(CODES):
        d = live.get(c)
        if not d:
            continue
        cost = round(float(d['price']) * 0.97, 2)          # 造一个 +3% 浮盈的底仓
        fake_holdings.append(dict(
            code=c, name=d.get('name', c), cost=cost, qty=2000,
            buy_time=(today + ' 09:35:00') if i == 2 else (yesterday + ' 10:00:00'),
            from_db=True))
    if not fake_holdings:
        skip('B 真机功能', '行情接口无返回')
    else:
        w = AtrTWidget()
        w._get_holdings_source = lambda: fake_holdings     # 不往你的库里写任何东西
        rows, is_trading, in_open = w._fetch_and_calc()
        print('      持仓行数=%d  is_trading=%s  开窗=%s' % (len(rows), is_trading, in_open))
        ok_plan = ok_vwap = ok_score = ok_dev = 0
        for r in rows:
            pl = r.get('t_plan') or {}
            tag = 'T+1(今日买入)' if r['code'] == CODES[2] else '隔日底仓'
            print('      %s %-6s %s 现价%.2f VWAP%.3f(%s) 偏离成本%+.2f%% | %s %.0f分 | %s' % (
                r['code'], r.get('name', '')[:6], tag, r['price'], pl.get('vwap', 0),
                pl.get('vwap_src', '-'), pl.get('dev_pct') or 0, pl.get('side_cn', '-'),
                pl.get('score', 0), pl.get('action', '')[:40]))
            print('          信号灯=%s  风控=%s' % (pl.get('text', ''), pl.get('risk_status', '')))
            ok_plan += 1 if pl else 0
            ok_vwap += 1 if pl.get('vwap_src') in ('amount/volume', 'fallback(HLC/3)') else 0
            ok_score += 1 if 0 <= pl.get('score', -1) <= 100 else 0
            ok_dev += 1 if abs((pl.get('dev_pct') or 0) - 3.0) < 1.0 else 0
            if r['code'] == CODES[2]:
                check('B5 今日买入(T+1) → 不给反T', pl.get('side') != 'reverse',
                      '%s | %s' % (pl.get('side_cn'), '；'.join(pl.get('warnings', [])[:1])))
        check('B1 每行都挂上了 t_plan', bool(rows) and ok_plan == len(rows), '%d/%d' % (ok_plan, len(rows)))
        check('B2 VWAP 来源合法（真值或显式 fallback）', ok_vwap == len(rows), '%d/%d' % (ok_vwap, len(rows)))
        check('B3 强度分落在 0~100', ok_score == len(rows), '%d/%d' % (ok_score, len(rows)))
        check('B4 成本偏离被真正算出来（≈+3%）', ok_dev == len(rows), '%d/%d' % (ok_dev, len(rows)))
        check('B6 信号灯/操作建议已被引擎文案接管',
              all((r.get('t_plan') or {}).get('text') for r in rows) and
              all(r.get('signal_text') for r in rows),
              '例：%s' % (rows[0].get('signal_text') if rows else '-'))

        # ---- B7 模拟盘中时刻（14:20）再跑一遍：验证非交易时段闸门之外的正常出信号 ----
        import ui.battle_widgets.atr_t_widget as _mod

        class _FakeDT(object):
            @staticmethod
            def now():
                return datetime(2026, 10, 12, 14, 20, 0)

        _real_dt = _mod.datetime
        _mod.datetime = _FakeDT
        try:
            rows2, _, _ = w._fetch_and_calc()
        finally:
            _mod.datetime = _real_dt
        print('      ── 模拟盘中 14:20（真实行情，仅替换取时间的 now）──')
        got_signal = 0
        for r in rows2:
            pl = r.get('t_plan') or {}
            print('      %s %-6s 现价%.2f VWAP%.3f 偏离成本%+.2f%% | %s %.0f分 | %s' % (
                r['code'], r.get('name', '')[:6], r['price'], pl.get('vwap', 0),
                pl.get('dev_pct') or 0, pl.get('side_cn', '-'), pl.get('score', 0),
                (pl.get('text', '') + ' ' + (pl.get('action') or ''))[:52]))
            print('          时段=%s(权重%.1f) 量价=%s 建议=%s股 预估新成本%s(%s)' % (
                pl.get('window_cn'), pl.get('time_weight', 0), pl.get('vol_state_cn'),
                pl.get('suggest_qty'), pl.get('est_cost_after'),
                ('%+.3f%%' % pl['est_cost_delta_pct']) if pl.get('est_cost_delta_pct') is not None else '-'))
            if pl.get('side') in ('reverse', 'forward'):
                got_signal += 1
        check('B7 盘中时刻有票给出可执行做T信号（含成本预估）',
              got_signal >= 1, '可执行 %d/%d 只' % (got_signal, len(rows2)))
except Exception as e:
    import traceback
    traceback.print_exc()
    check('B 真机功能', False, '%s: %s' % (type(e).__name__, e))

# ============================================================
# C. 推送静默 bug：动态前后对比（探针版只存在测试内存里，不改磁盘）
# ============================================================
print('\n[C] 微信「买入观察」推送：修复前 / 修复后 动态对比')
try:
    import services.wechat_bus as wb

    CALLS = []

    class _RecBus(object):
        def send_t_timing(self, **kw):
            CALLS.append(kw)
            return True

    wb.get_wechat_bus = lambda *a, **k: _RecBus()      # 打桩：只记录，不真发

    # 构造一个必然走 red_buy 分支的行（条件见 L737：在买点雷达 + 零轴下金叉 + 结构分≥2）
    r_case = dict(code='600000', name='测试股', price=10.00, pct=0.50,
                  buy_point=9.90, sell_point=10.10, momentum='MACD零轴下金叉',
                  vwap=10.00, atr=0.15, f=0.0, theme_tag='测试', theme_dir='strong',
                  k_buy=0.3, k_sell=0.3, anchor_vwap=10.0,
                  in_buy_radar=True, in_sell_radar=False,
                  cross='golden_below_zero', div=None,
                  td={'is_low9': False, 'is_high9': False, 'is_low78': False,
                      'is_high78': False, 'level': 0},
                  struct_score=2, near_support=True, near_resist=False)

    # ---- 旧版（取自备份文件，探针版：把吞异常的 pass 换成记录）----
    old_lines = old.split('\r\n')
    s = next(i for i, l in enumerate(old_lines) if l.startswith('    def _apply_risk_and_signal'))
    e = next(i for i in range(s + 1, len(old_lines)) if old_lines[i].startswith('    def '))
    old_src = textwrap.dedent('\n'.join(old_lines[s:e]))
    ERRS = []
    import re as _re
    old_src_probe, probe_cnt = _re.subn(
        r'except Exception:(\s*)pass',
        lambda m: 'except Exception as _ee:%sERRS.append(repr(_ee))' % m.group(1),
        old_src)
    import ui.battle_widgets.atr_t_widget as mod
    g = dict(vars(mod))
    g['ERRS'] = ERRS
    exec(compile(old_src_probe, '<old_probe>', 'exec'), g)      # noqa: S102
    old_fn = g['_apply_risk_and_signal']

    class _Stub(object):
        _lock_state = {}

        def __getattr__(self, n):
            return lambda *a, **k: None

    CALLS.clear()
    old_fn(_Stub(), dict(r_case), False)
    old_push = len(CALLS)
    print('      修复前：推送调用 %d 次，被吞掉的异常 %d 条 → %s' % (
        old_push, len(ERRS), ERRS[:2]))
    check('C1 修复前确实静默失效（推送 0 次 + 捕获到 NameError）',
          probe_cnt == 2 and old_push == 0 and any('atr' in x for x in ERRS),
          '探针替换 %d 处；异常样本 %s' % (probe_cnt, ERRS[:1]))

    # ---- 新版（真实控件实例的方法）----
    w2 = AtrTWidget()
    CALLS.clear()
    w2._lock_state = {}
    out = w2._apply_risk_and_signal(dict(r_case), False)
    print('      修复后：推送调用 %d 次 | 信号=%s | 操作=%s' % (
        len(CALLS), out.get('signal_text'), out.get('action')))
    if CALLS:
        print('      推送内容: event=%s code=%s price=%s atr=%s' % (
            CALLS[0].get('event'), CALLS[0].get('code'), CALLS[0].get('price'), CALLS[0].get('atr')))
    check('C2 修复后推送真的发出（且 atr 有值）',
          len(CALLS) >= 1 and 'atr' in CALLS[0] and CALLS[0]['atr'] not in (None, ''),
          'atr=%s' % (CALLS[0].get('atr') if CALLS else 'N/A'))
    check('C3 信号本身未被破坏（仍是红买入）',
          out.get('signal_level') == 'red' and out.get('signal_dir') == 'buy',
          '%s / %s' % (out.get('signal_level'), out.get('signal_dir')))
except Exception as e:
    import traceback
    traceback.print_exc()
    check('C 推送对比', False, '%s: %s' % (type(e).__name__, e))

# ============================================================
print('\n' + '=' * 96)
bad = [n for n, ok, _ in RESULTS if ok is False]
sk = [n for n, ok, _ in RESULTS if ok is None]
print('PASS %d / FAIL %d / SKIP %d' % (len(RESULTS) - len(bad) - len(sk), len(bad), len(sk)))
if bad:
    print('失败：' + '；'.join(bad))
print('=' * 96)
sys.exit(1 if bad else 0)
