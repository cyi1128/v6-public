# -*- coding: utf-8 -*-
"""真实路径验证：行数据故意不带 ctrl，看渲染入口能否自己填出来。

用法: python _verify_ctrl_cached.py <模块名>
每个模块单独进程（隔离 QtWebEngine 离屏崩溃）。
"""
import os
import sys
import time

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, r'D:\QuantMonitorV6')
sys.stdout.reconfigure(encoding='utf-8')

EXP_TRACK = []
CODES = [('600845', '宝信软件', '98·候选'),
         ('002847', '盐津铺子', '97·候选'),
         ('605196', '华通线缆', '91·出货'),
         ('600587', '新华医疗', '44')]


class Row(dict):
    """宽容字典：缺键返回空，避免测试数据反复补键。"""
    def __missing__(self, k):
        return ''


def base_row(c, n):
    return Row(code=c, name=n, price=10.0, pct=1.0, pct_chg=1.0, cur_pct=1.0,
                gap=1.0, amp=2.0, mv=100.0, amount=1e8, jj_amount=0.0,
                cur_amount=0.0, turnover=3.0, score=50.0, theme=u'测试',
                _theme=u'测试', industry=u'测试', sector=u'测试', trend='--',
                limit_up_count=0, signals=[], found_time='09:30',
                real_found_time='09:30', date='2026-10-10', cur_time='',
                jj_amount_time='', cost=9.0, profit=1.0, shares=100,
                key_price=10.0, cum_pct=1.0, path=u'测试', status=u'预备',
                is_tail=False, buy_point=9.5, sell_point=10.5,
                trade_date='2026-10-10', pnl=1.0, pnl_pct=1.0, cum=1.0,
                rt_price=10.0, rt_pct=1.0, reason=u'测试', board=u'测试',
                rank=1, momentum=[], base_price=9.5, atr=0.3, support=9.5,
                resistance=10.5, vol_ratio=1.2, ma5=9.8, ma20=9.5,
                cur_price=10.0, last_price=10.0, close=10.0, volume=1e6,
                signal_text='', kind='', sub_kind='', tag='', note='',
                trigger='', level='', state='', action='', type='')


def build(mod):
    """返回 (widget, setrows(w, rows), render(w, rows), 控盘列index)"""
    if mod == 'limitup':
        from ui.battle_widgets.limit_up_widget import LimitUpWidget
        return (LimitUpWidget(),
                lambda w, rows: setattr(w, '_stocks', rows),
                lambda w, rows: w._render_rows(), 6)
    if mod == 'auction':
        from ui.battle_widgets.auction_filter_widget import AuctionFilterWidget
        return (AuctionFilterWidget(),
                lambda w, rows: setattr(w, '_rows', rows),
                lambda w, rows: w._render_rows(), 8)
    if mod == 'hold':
        from ui.battle_widgets.atr_t_widget import AtrTWidget
        return (AtrTWidget(),
                lambda w, rows: setattr(w, '_hold_rows', rows),
                lambda w, rows: w._render_hold_table(), 10)
    if mod == 'track':
        from ui.battle_widgets.picks_track_widget import PicksTrackWidget
        return (PicksTrackWidget(),
                lambda w, rows: setattr(w, '_shown', rows),
                lambda w, rows: w._render(), 9)
    if mod == 'wsp':
        from ui.watchlist_panel import WatchlistWidget
        return (WatchlistWidget(),
                lambda w, rows: None,
                lambda w, rows: w._update_table(rows), 9)
    raise SystemExit('未知模块 ' + mod)


def main():
    mod = sys.argv[1]
    from PyQt6.QtCore import Qt as _Qt
    from PyQt6.QtWidgets import QApplication
    if mod == 'wsp':
        QApplication.setAttribute(
            _Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
        import PyQt6.QtWebEngineWidgets  # noqa: F401  必须在 QApplication 之前
    app = QApplication([])

    # 1. 预热缓存（模拟正常使用中"别的模块先算过一次"的状态）
    from services.control_profile import get_ctrl_map
    get_ctrl_map([c for c, _, _ in CODES])

    w, setrows, render, colidx = build(mod)
    if mod == 'track':
        # 追踪表用真实行数据（字段多且会被格式化，宽字典不适用）
        from services.picks_tracking_service import fetch_tracking
        from services.control_profile import ctrl_cell
        real = fetch_tracking()
        allc = [c for c, _, _ in CODES]
        rows = []
        for r in real:
            if r.get('code') in allc and r['code'] not in [x.get('code') for x in rows]:
                rows.append(r)
            if len(rows) == 4:
                break
        assert len(rows) == 4, '追踪库没取满 4 只'
        rows.sort(key=lambda r: allc.index(r['code']))
        cm = get_ctrl_map([r['code'] for r in rows])
        global EXP_TRACK
        EXP_TRACK = [ctrl_cell(cm.get(r['code']))[0] for r in rows]
        for r in rows:
            r['ctrl'] = None
    else:
        rows = [base_row(c, n) for c, n, _ in CODES]
    assert all(not r.get('ctrl') for r in rows), '构造的行不应带 ctrl'
    setrows(w, rows)
    render(w, rows)

    print('[%s] 列数=%d 控盘列index=%d' % (mod, w.table.columnCount(), colidx))
    bad = []
    for i, r in enumerate(rows):
        c = r['code']; n = r.get('name')
        exp = EXP_TRACK[i] if mod == 'track' else CODES[i][2]
        it = w.table.item(i, colidx)
        txt = it.text() if it else None
        if txt != exp:
            bad.append((c, txt, exp))
        print('   row%d %-6s %-8s 控盘=%r (期望 %s)' % (i, c, n, txt, exp))
    print('[%s] %s' % (mod, '通过' if not bad else '失败 %s' % bad))
    sys.stdout.flush()
    time.sleep(0.3)
    os._exit(0)


main()
