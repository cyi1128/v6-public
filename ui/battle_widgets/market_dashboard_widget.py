# -*- coding: utf-8 -*-
"""市场看板仪表盘（对标 TickFlow Stock Panel 首页布局）。

布局（按用户给的截图顺序）：
  行1  指数条（上证/深成/创业板/科创，实时行情未接，占位）
  行2  6 个统计卡：个股涨/平/跌 | 强势/弱势 | 涨停/跌停·封板率 | 最高连板 | 成交额 | 平均/中位涨跌
  行3  4 列：涨跌分布 | 情绪分 | 趋势强度 | 涨停梯队+实用监控
  行4  2 列：概念热度 | 行业热度
  行5  4 列：涨幅榜 | 跌幅榜 | 成交额榜 | 活跃振幅榜
"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QProgressBar, QVBoxLayout, QWidget)

from .base import BC, L, BattleModuleBase

_BOX = ('QFrame{background:%s;border:1px solid %s;border-radius:8px;}'
        % (BC.BG_CARD, BC.BORDER))


def _card(title, parent=None):
    f = QFrame(parent)
    f.setStyleSheet(_BOX)
    lay = QVBoxLayout(f)
    lay.setContentsMargins(10, 6, 10, 8)
    lay.setSpacing(4)
    t = L(title, BC.TEXT2, 11, True)
    lay.addWidget(t)
    return f, lay


def _kv_row(parent_lay, label, value, vcolor=None, small=False):
    row = QHBoxLayout()
    row.addWidget(L(label, BC.TEXT2, 10))
    row.addStretch()
    row.addWidget(L(str(value), vcolor or BC.TEXT, 15 if not small else 12, True))
    parent_lay.addLayout(row)


class MarketDashboardWidget(BattleModuleBase):
    """市场看板（外层第一个 Tab）。"""

    stock_clicked = pyqtSignal(str, str)
    _done = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__('市场看板', parent)
        self._build_static()
        self._done.connect(self._render)
        self.set_status('正在统计全市场…')
        self.run_async(self._job, self._done.emit,
                       lambda e: self.set_status('统计失败: %s' % e))

    # ---------------------------------------------------------------
    def _job(self):
        from services.market_dashboard_service import compute_dashboard
        return compute_dashboard()

    def _build_static(self):
        root = QVBoxLayout()
        root.setSpacing(6)
        self.content_layout.addLayout(root, 1)

        # 行1：指数条（占位，未接实时行情）
        idx_row = QHBoxLayout()
        for nm in ['上证指数', '深证成指', '创业板指', '科创综指']:
            c, lay = _card(nm)
            lay.addWidget(L('--', BC.TEXT3, 14, True))
            idx_row.addWidget(c)
        root.addLayout(idx_row)

        # 行2：6 个统计卡（占位，render 填）
        self._stat_cards = []
        stat_row = QHBoxLayout()
        for title in ['个股涨/平/跌', '强势/弱势(≥3%)', '涨停/跌停·封板率',
                      '最高连板', '全市场成交额', '平均/中位涨跌']:
            c, lay = _card(title)
            lay.addWidget(L('--', BC.TEXT3, 16, True))
            self._stat_cards.append(lay)
            stat_row.addWidget(c)
        root.addLayout(stat_row)

        # 行3：4 列
        r3 = QHBoxLayout()
        self._buckets_lay = QVBoxLayout()
        c, lay = _card('涨跌分布 / 广度')
        lay.addLayout(self._buckets_lay)
        r3.addWidget(c, 3)

        c, lay = _card('情绪分')
        self._sent_lbl = L('--', BC.TEXT, 34, True)
        lay.addWidget(self._sent_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(L('0=极度恐慌 100=极度贪婪', BC.TEXT3, 9),
                      alignment=Qt.AlignmentFlag.AlignCenter)
        r3.addWidget(c, 1)

        c, lay = _card('趋势强度')
        self._trend_lay = QVBoxLayout()
        lay.addLayout(self._trend_lay)
        r3.addWidget(c, 2)

        c, lay = _card('涨停梯队 / 实用监控')
        self._ladder_lay = QVBoxLayout()
        lay.addLayout(self._ladder_lay)
        r3.addWidget(c, 2)
        root.addLayout(r3)

        # 行4：概念/行业热度
        r4 = QHBoxLayout()
        c, lay = _card('概念热度 TOP5')
        self._themes_lay = lay
        r4.addWidget(c)
        c, lay = _card('行业热度 TOP5')
        self._inds_lay = lay
        r4.addWidget(c)
        root.addLayout(r4)

        # 行5：四张榜
        r5 = QHBoxLayout()
        self._gainers_lay = QVBoxLayout()
        c, lay = _card('涨幅榜 TOP8'); lay.addLayout(self._gainers_lay); r5.addWidget(c)
        self._losers_lay = QVBoxLayout()
        c, lay = _card('跌幅榜 TOP8'); lay.addLayout(self._losers_lay); r5.addWidget(c)
        self._amt_lay = QVBoxLayout()
        c, lay = _card('成交额榜 TOP8（亿）'); lay.addLayout(self._amt_lay); r5.addWidget(c)
        self._act_lay = QVBoxLayout()
        c, lay = _card('活跃振幅榜 TOP8(%)'); lay.addLayout(self._act_lay); r5.addWidget(c)
        root.addLayout(r5)

    # ---------------------------------------------------------------
    def _clear(self, lay):
        while lay.count():
            it = lay.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

    def _row_line(self, parent_lay, left, mid, right, color):
        row = QHBoxLayout()
        row.addWidget(L(left, BC.TEXT, 10))
        row.addStretch()
        row.addWidget(L(mid, BC.TEXT2, 10))
        row.addWidget(L('  ' + right, color, 10, True))
        parent_lay.addLayout(row)

    def _render(self, d):
        b = d['breadth']
        lu = d['limit_up'] or {}
        # 行2
        texts = [
            '%d / %d / %d' % (b['n_up'], b['n_flat'], b['n_dn']),
            '%d / %d' % (b['n_hi3'], b['n_lo3']),
            '%d / %d · %s%%' % (lu.get('lu_count', 0), lu.get('broken', 0),
                                lu.get('fengban_rate', '--')),
            '%d 板' % lu.get('max_lbc', 0),
            '%.2f 万亿' % (b['total_amount_yi'] / 10000.0),
            '%+.2f%% / %+.2f%%' % (b['avg_pct'], b['median_pct']),
        ]
        cols = [BC.RED if b['n_up'] >= b['n_dn'] else BC.GREEN,
                BC.RED if b['n_hi3'] >= b['n_lo3'] else BC.GREEN,
                BC.RED, BC.GOLD, BC.TEXT,
                BC.RED if b['avg_pct'] >= 0 else BC.GREEN]
        for lay, t, col in zip(self._stat_cards, texts, cols):
            self._clear(lay)
            lay.addWidget(L(t, col, 16, True))

        # 情绪分
        s = d['sentiment']
        self._sent_lbl.setText(str(s))
        self._sent_lbl.setStyleSheet('color:%s;font-size:34px;font-weight:600;'
                                     % (BC.RED if s >= 50 else BC.GREEN))

        # 涨跌分布：8 个小条
        self._clear(self._buckets_lay)
        labels = ['<-5', '-5~-3', '-3~-1', '-1~0', '0~1', '1~3', '3~5', '>5']
        mx = max(b['buckets']) or 1
        row = QHBoxLayout()
        for lab, v in zip(labels, b['buckets']):
            col = BC.GREEN if v >= 0 and labels.index(lab) < 4 else BC.RED
            box = QVBoxLayout()
            bar = QProgressBar()
            bar.setRange(0, mx)
            bar.setValue(v)
            bar.setTextVisible(False)
            bar.setFixedHeight(26)
            bar.setStyleSheet('QProgressBar{background:%s;border:none;border-radius:3px;}'
                              'QProgressBar::chunk{background:%s;border-radius:3px;}'
                              % (BC.BG_HEADER, col))
            box.addWidget(bar)
            box.addWidget(L(str(v), BC.TEXT2, 9, True), alignment=Qt.AlignmentFlag.AlignCenter)
            box.addWidget(L(lab, BC.TEXT3, 8), alignment=Qt.AlignmentFlag.AlignCenter)
            row.addLayout(box)
        self._buckets_lay.addLayout(row)
        self._buckets_lay.addWidget(L('涨 %d ｜ 平 %d ｜ 跌 %d'
                                      % (b['n_up'], b['n_flat'], b['n_dn']),
                                      BC.TEXT, 11, True))

        # 趋势强度
        self._clear(self._trend_lay)
        for k, v in [('站上 MA5', b['ma5_pct']), ('站上 MA20', b['ma20_pct']),
                     ('站上 MA60', b['ma60_pct'])]:
            bar = QProgressBar(); bar.setRange(0, 100); bar.setValue(int(v))
            bar.setTextVisible(True); bar.setFormat('%s  %s%%' % (k, v))
            bar.setFixedHeight(18)
            self._trend_lay.addWidget(bar)
        self._row_line(self._trend_lay, '60日新高', str(b['new_high']), '', BC.RED)
        self._row_line(self._trend_lay, '60日新低', str(b['new_low']), '', BC.GREEN)
        self._row_line(self._trend_lay, '新高/新低', str(b['hl_ratio']), '', BC.TEXT2)

        # 涨停梯队
        self._clear(self._ladder_lay)
        ladder = lu.get('ladder', {})
        top_lbc = max(ladder) if ladder else 0
        self._row_line(self._ladder_lay, '封板率', str(lu.get('fengban_rate', '--')) + '%', '', BC.RED)
        for k in sorted(ladder.keys(), reverse=True):
            tag = '%d 板' % k if k > 1 else '首板'
            self._row_line(self._ladder_lay, tag, str(ladder[k]), '',
                           BC.GOLD if k >= 3 else BC.TEXT)
        self._row_line(self._ladder_lay, '炸板', str(lu.get('broken', 0)), '', BC.GREEN)
        self._row_line(self._ladder_lay, '跌超3%', str(b['n_lo3']), '', BC.GREEN)

        # 概念 / 行业热度
        for lay, items in [(self._themes_lay, d['themes']), (self._inds_lay, d['industries'])]:
            self._clear(lay)
            for i, t in enumerate(items, 1):
                lead = (t.get('lead_name') or '') + ' '
                self._row_line(lay, '%d %s' % (i, t.get('name', '')),
                               str(t.get('count', 0)) + '只',
                               lead, BC.RED if t.get('avg_pct', 0) >= 0 else BC.GREEN)

        # 四张榜
        for lay, data, fmt in [
                (self._gainers_lay, b['gainers'], '+%'),
                (self._losers_lay, b['losers'], '%'),
                (self._amt_lay, b['by_amt'], '亿'),
                (self._act_lay, b['active'], '%%')]:
            self._clear(lay)
            for i, (code, nm, v) in enumerate(data, 1):
                row = QHBoxLayout()
                row.addWidget(L('%d %s %s' % (i, code, nm), BC.TEXT, 9))
                row.addStretch()
                col = BC.RED if i < 5 and lay is self._gainers_lay else (
                    BC.GREEN if lay is self._losers_lay else BC.TEXT2)
                row.addWidget(L(('%.2f' % v), col, 9, True))
                lay.addLayout(row)

        self.set_status('数据日 %s ｜ 涨停 %d 只 ｜ 情绪分 %d'
                        % (d.get('data_date', ''), lu.get('lu_count', 0), s))
