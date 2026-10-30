# -*- coding: utf-8 -*-
"""查看持仓的机构级做T信号（真实 DB + 真实行情 + 真控件）。

用法（在项目根目录，**先关掉主程序**）：
    python tools\\show_t_plan.py                 # 用当前真实时间
    python tools\\show_t_plan.py --at 14:20      # 模拟盘中时刻（复盘用，不改任何数据）
    python tools\\show_t_plan.py --at 10:30

只读：不写库、不发推送、不调界面；数据源 data\\cache\\atr_t_tracking.duckdb。
"""
import argparse
import os
import sys
from datetime import datetime

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--at', default=None, help='模拟盘中时刻，如 14:20')
    a = ap.parse_args()

    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    import ui.battle_widgets.atr_t_widget as mod
    from ui.battle_widgets.atr_t_widget import AtrTWidget

    if a.at:
        try:
            hh, mm = [int(x) for x in a.at.split(':')]
        except Exception:
            print('--at 格式应为 HH:MM，例如 14:20')
            return 2

        class _FakeDT(object):
            @staticmethod
            def now():
                d = datetime.now()
                return d.replace(hour=hh, minute=mm, second=0, microsecond=0)

        mod.datetime = _FakeDT
        print('（模拟盘中时刻 %s，仅替换取时间的 now，不改数据）' % a.at)

    w = AtrTWidget()
    rows, is_trading, in_open = w._fetch_and_calc()
    print('时间基准：%s ｜ is_trading=%s ｜ 开盘波动期=%s ｜ 持仓 %d 只'
          % (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), is_trading, in_open, len(rows)))
    if not rows:
        print('（无持仓行：holding 表为空且自选也为空，或 K 线不足 30 根被跳过）')
        return 0
    print('=' * 108)
    for r in rows:
        p = r.get('t_plan') or {}
        print('%-7s %-6s 现价 %8.3f  成本 %8.3f  偏离成本 %+6.2f%%' % (
            r['code'], (r.get('name') or '')[:6], r['price'], float(r.get('cost') or 0),
            p.get('dev_pct') or 0))
        print('        真VWAP %8.3f (%s)  ATR %s  量价：%s  时段：%s(权重%.1f)'
              % (p.get('vwap') or 0, p.get('vwap_src'), p.get('atr'),
                 p.get('vol_state_cn'), p.get('window_cn'), p.get('time_weight') or 0))
        print('        判定：%s %s ｜ 强度 %.0f 分（反T轨 %.0f / 正T轨 %.0f）｜ 风控：%s'
              % (p.get('text'), p.get('side_cn'), p.get('score') or 0,
                 p.get('score_rev') or 0, p.get('score_fwd') or 0, p.get('risk_status')))
        print('        操作：%s' % (p.get('action') or '-'))
        if p.get('side') in ('reverse', 'forward'):
            print('        建议 %s 股（仓位 %s%%）｜ 卖 %s → 买回 %s ｜ 盈亏平衡价差 %s'
                  % (p.get('suggest_qty'), round((p.get('suggest_ratio') or 0) * 100, 1),
                     p.get('sell_target'), p.get('buy_target'), p.get('breakeven_spread')))
            print('        预估：成本 %s → %s（%s）｜ 额外占用资金 %s ｜ 费用+滑点 %s'
                  % (r.get('cost'), p.get('est_cost_after'),
                     ('%+.3f%%' % p['est_cost_delta_pct']) if p.get('est_cost_delta_pct') is not None else '-',
                     p.get('est_extra_cash'), p.get('est_fees')))
        if p.get('reasons'):
            print('        理由：%s' % ' ｜ '.join(p['reasons']))
        if p.get('warnings'):
            print('        提醒：%s' % ' ｜ '.join(p['warnings']))
        print('-' * 108)
    return 0


if __name__ == '__main__':
    sys.exit(main())
