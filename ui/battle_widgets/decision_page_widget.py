# -*- coding: utf-8 -*-
"""今日市场决策页（高密度白版）。

数据全部来自 services.decision_page_service.compute_decision()，
后者真实调用：
  · market_rhythm_engine.get_rhythm()     题材/状态/龙头/梯队/轮动
  · market_dashboard_service.compute_dashboard()  广度/情绪分/涨停/炸板/概念
  · decision_page_service._index_snapshot()     四大指数实时点位(腾讯)
  · atr_t_tracking.duckdb holding 表      真实持仓
  · control_screen_service.compute_stock() 持仓弱化信号
按钮：
  · 全部刷新 = run_async(compute_decision)，真重算
  · 一键跳转 = jump_to_control 信号（主窗口切控盘页并勾「仅看今日主线」）
"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                             QTableWidget, QVBoxLayout)

from .base import BC, L, BattleModuleBase

_BOX = ('QFrame{background:%s;border:1px solid %s;border-radius:6px;}'
        % (BC.BG_CARD, BC.BORDER))
_GRADE_COLOR = {'强': BC.RED, '中': BC.GOLD, '弱': BC.GREEN}


def _box(parent=None):
    f = QFrame(parent)
    f.setStyleSheet(_BOX)
    return f


class DecisionPageWidget(BattleModuleBase):

    stock_clicked = pyqtSignal(str, str)
    jump_to_control = pyqtSignal()
    _done = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__('今日市场决策', parent)
        self._build_static()
        self._done.connect(self._render)
        self.set_status('正在汇总今日决策数据…')
        # 真实数据计算在后台线程跑（读全市场K线约 30 秒），不卡界面
        self.run_async(self._job, self._done.emit,
                       lambda e: self.set_status('决策汇总失败: %s' % e))

    def _job(self):
        from services.decision_page_service import compute_decision
        return compute_decision()

    @staticmethod
    def _kv(box, label, value, vcolor=BC.TEXT, vbold=True, lab_color=None, size=12):
        """横排「标签 数值」，返回数值 label。"""
        box.addWidget(L(label, lab_color or BC.TEXT2, 10))
        lab = L(str(value), vcolor, size, vbold)
        box.addWidget(lab)
        return lab

    # ============================================================
    # 静态布局（7 行高密度）
    # ============================================================
    def _build_static(self):
        root = QVBoxLayout()
        root.setSpacing(5)
        self.content_layout.addLayout(root, 1)

        # ---- 第1行：顶部状态条 ----
        f = _box()
        h = QHBoxLayout(f); h.setContentsMargins(10, 4, 10, 4); h.setSpacing(22)
        self._st_lab = self._kv(h, '市场状态', '--', BC.TEXT, size=16)
        self._sent_lab = self._kv(h, '情绪分', '--', BC.TEXT, size=16)
        self._pos_lab = self._kv(h, '建议最大仓位', '--', BC.TEXT, size=16)
        self._lu_lab = self._kv(h, '涨停/炸板', '--')
        self._lbc_lab = self._kv(h, '最高连板', '--')
        self._amt_lab = self._kv(h, '成交额', '--')
        h.addStretch()
        self._btn_ref = QPushButton('🔄 全部刷新')
        self._btn_ref.clicked.connect(self._refresh)   # 真重算
        h.addWidget(self._btn_ref)
        root.addWidget(f)

        # ---- 第2行：四大指数 ----
        f = _box()
        self._idx_lay = QHBoxLayout(f); self._idx_lay.setContentsMargins(10, 3, 10, 3)
        root.addWidget(f)

        # ---- 第3行：市场核心数据横条 ----
        f = _box()
        h = QHBoxLayout(f); h.setContentsMargins(10, 3, 10, 3); h.setSpacing(22)
        self._up_lab = self._kv(h, '涨/平/跌', '--')
        self._hw_lab = self._kv(h, '强势≥3%/弱势≤-3%', '--')
        self._ma_lab = self._kv(h, 'MA20站上率', '--')
        self._hn_lab = self._kv(h, '新高/新低(60日)', '--')
        h.addStretch()
        root.addWidget(f)

        # ---- 第4行：四重共振 ----
        self._cards = {}
        crow = QHBoxLayout(); crow.setSpacing(5)
        for key, title in [('sector', '①板块'), ('dragon', '②龙头'),
                           ('capital', '③资金'), ('sentiment', '④情绪')]:
            cf = _box()
            cl = QVBoxLayout(cf); cl.setContentsMargins(8, 4, 8, 4); cl.setSpacing(2)
            cl.addWidget(L(title, BC.TEXT2, 10, True))
            g = QHBoxLayout(); g.setSpacing(6)
            lab = L('--', BC.TEXT, 15, True); lab.setMinimumWidth(52)
            concl = L('--', BC.TEXT2, 9); concl.setWordWrap(True)
            g.addWidget(lab); g.addWidget(concl, 1)
            cl.addLayout(g)
            crow.addWidget(cf, 1)
            self._cards[key] = (lab, concl)
        # 总分条
        tf = _box()
        tl = QVBoxLayout(tf); tl.setContentsMargins(8, 4, 8, 4); tl.setSpacing(0)
        row = QHBoxLayout(); row.setSpacing(8)
        row.addWidget(L('总分', BC.TEXT2, 10))
        self._total_lab = L('--', BC.TEXT, 17, True); row.addWidget(self._total_lab)
        self._res_lab = L('--', BC.TEXT, 12, True); row.addWidget(self._res_lab)
        tl.addLayout(row)
        self._veto_lab = L('', BC.GREEN, 10, True); tl.addWidget(self._veto_lab)
        crow.addWidget(tf, 0)
        root.addLayout(crow)

        # ---- 第5行：市场结构（左右分栏） ----
        srow = QHBoxLayout(); srow.setSpacing(5)
        lf = _box()
        ll = QVBoxLayout(lf); ll.setContentsMargins(8, 4, 8, 4); ll.setSpacing(2)
        ll.addWidget(L('涨跌分布(区间:家数)', BC.TEXT2, 10, True))
        self._buckets_lab = L('--', BC.TEXT, 11); ll.addWidget(self._buckets_lab)
        ll.addWidget(L('连板梯队(板数:家数)', BC.TEXT2, 10, True))
        self._ladder_lab = L('--', BC.TEXT, 11); ll.addWidget(self._ladder_lab)
        srow.addWidget(lf, 1)
        rf = _box()
        rl = QVBoxLayout(rf); rl.setContentsMargins(8, 4, 8, 4); rl.setSpacing(2)
        rl.addWidget(L('今日最强主线', BC.TEXT2, 10, True))
        self._main_lab = L('--', BC.TEXT, 11, True); rl.addWidget(self._main_lab)
        rl.addWidget(L('资金轮动', BC.TEXT2, 10, True))
        self._rot_lab = L('--', BC.TEXT2, 10); rl.addWidget(self._rot_lab)
        rl.addWidget(L('概念热度 TOP5', BC.TEXT2, 10, True))
        self._hot_lab = L('--', BC.TEXT2, 10); rl.addWidget(self._hot_lab)
        srow.addWidget(rf, 1)
        root.addLayout(srow)

        # ---- 第6行：决策结论 + 跳转 ----
        f = _box()
        h = QHBoxLayout(f); h.setContentsMargins(10, 5, 10, 5); h.setSpacing(10)
        self._concl_lab = L('--', BC.RED, 13, True)
        self._concl_lab.setWordWrap(True)
        h.addWidget(self._concl_lab, 1)
        self._btn_jump = QPushButton('🎛 一键跳转控盘选股（按今日主线过滤）')
        self._btn_jump.clicked.connect(self.jump_to_control.emit)  # 真跳转
        h.addWidget(self._btn_jump)
        root.addWidget(f)

        # ---- 第7行：持仓快速预警 ----
        f = _box()
        fl = QVBoxLayout(f); fl.setContentsMargins(8, 4, 8, 4)
        fl.addWidget(L('持仓快速预警', BC.TEXT2, 10, True))
        self._tbl = QTableWidget(0, 7)
        self._tbl.setHorizontalHeaderLabels(['股票', '现价', '成本', '偏离',
                                             '阶段', '弱化信号', '建议动作'])
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tbl.setStyleSheet(
            'QTableWidget{background:%s;border:none;font-size:12px;}'
            'QHeaderView::section{background:%s;padding:3px;font-weight:bold;}'
            % (BC.BG_CARD, BC.BG_HEADER))
        for i, w in enumerate([170, 80, 80, 80, 90, 150, 110]):
            self._tbl.setColumnWidth(i, w)
        fl.addWidget(self._tbl)
        root.addWidget(f, 1)

    # ============================================================
    # 渲染
    # ============================================================
    def _refresh(self):
        self.set_status('刷新中（真实重算）…')
        self.run_async(self._job, self._done.emit,
                       lambda e: self.set_status('失败: %s' % e))

    def _render(self, r):
        # 第1行
        st_col = {'主升浪': BC.RED, '震荡上行': BC.RED,
                  '震荡分化': BC.GOLD, '退潮期': BC.GREEN}.get(r['state'], BC.TEXT)
        self._st_lab.setText(r['state'])
        self._st_lab.setStyleSheet('color:%s;font-size:16px;font-weight:600;' % st_col)
        self._sent_lab.setText(str(r['sentiment']))
        self._sent_lab.setStyleSheet('color:%s;font-size:16px;font-weight:600;'
                                     % (BC.RED if r['sentiment'] >= 50 else BC.GREEN))
        self._pos_lab.setText(r['max_pos'])
        self._pos_lab.setStyleSheet('color:%s;font-size:16px;font-weight:600;'
                                    % (BC.RED if r['max_pos'] in ('重仓', '中等') else BC.GREEN))
        lu = r.get('lu_stat', {}) or {}
        self._lu_lab.setText('%d/%d' % (r['lu_today'], lu.get('broken', 0)))
        self._lbc_lab.setText('%d板' % r['lbc_today'])
        self._amt_lab.setText('%d亿' % r['breadth'].get('total_amount_yi', 0))

        # 第2行：四大指数（真实腾讯行情）
        while self._idx_lay.count():
            it = self._idx_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for ix in r.get('indices', []):
            col = BC.RED if ix['pct'] >= 0 else BC.GREEN
            self._idx_lay.addWidget(L(ix['name'], BC.TEXT2, 10))
            self._idx_lay.addWidget(L("%.2f" % ix['price'], BC.TEXT, 13, True))
            self._idx_lay.addWidget(L("%+.2f%%" % ix['pct'], col, 12, True))
            self._idx_lay.addSpacing(24)
        self._idx_lay.addStretch()

        # 第3行：核心横条
        b = r['breadth']
        self._up_lab.setText('%d/%d/%d' % (b['n_up'], b['n_flat'], b['n_dn']))
        self._hw_lab.setText('%d/%d' % (b['n_hi3'], b['n_lo3']))
        self._ma_lab.setText('MA20 %.1f%%' % b['ma20_pct'])
        self._hn_lab.setText('%d/%d' % (b['new_high'], b['new_low']))

        # 第4行：四卡
        if r['cards']:
            for k, c in r['cards'].items():
                lab, concl = self._cards[k]
                lab.setText('%d %s' % (c['score'], c['grade']))
                lab.setStyleSheet('color:%s;font-size:15px;font-weight:600;'
                                  % _GRADE_COLOR.get(c['grade'], BC.TEXT))
                concl.setText(c['concl'])
            self._total_lab.setText(str(r['total']))
            col = _GRADE_COLOR.get(r['resonance'], BC.TEXT)
            self._total_lab.setStyleSheet('color:%s;font-size:17px;font-weight:600;' % col)
            self._res_lab.setText('共振:%s' % r['resonance'])
            self._res_lab.setStyleSheet('color:%s;font-size:12px;font-weight:600;' % col)
            if r.get('veto'):
                self._veto_lab.setText('⚠ 情绪拖累，不可进攻')
                self._veto_lab.setStyleSheet(
                    'color:%s;font-size:10px;font-weight:600;' % BC.GREEN)
            else:
                self._veto_lab.setText('可进攻' if r['resonance'] == '强' else '')

        # 第5行
        buckets = b.get('buckets', [0] * 8)
        labels = ['<-5', '-5~-3', '-3~-1', '-1~0', '0~1', '1~3', '3~5', '>5']
        self._buckets_lab.setText(
            '  '.join('%s:%d' % (l, v) for l, v in zip(labels, buckets)))
        ladder = lu.get('ladder', {})
        self._ladder_lab.setText('  '.join(
            '%d板:%d' % (k, v) for k, v in sorted(ladder.items())))
        self._main_lab.setText('、'.join(t['theme'] for t in r['themes']) or '--')
        self._rot_lab.setText(r['rotation'] or '--')
        hot = r.get('hot_themes', [])[:5]
        self._hot_lab.setText('｜'.join(
            '%s %d' % (x.get('name', ''), x.get('count', 0)) for x in hot) or '--')

        # 第6行结论
        self._concl_lab.setText(r['concl'])
        self._concl_lab.setStyleSheet(
            'color:%s;font-size:13px;font-weight:600;'
            % (BC.RED if r.get('allow_open') else BC.GREEN))

        # 第7行持仓表（stage unknown 显示 '-'）
        hs = r['holdings']
        self._tbl.setRowCount(len(hs))
        for i, h in enumerate(hs):
            cost = h.get('cost') or 0
            dev = (h['price'] / cost - 1) * 100 if cost and h['price'] else 0
            stage = h.get('stage') or '-'
            vals = ['%s %s' % (h['code'], h.get('name', '')),
                    '%.2f' % h['price'], '%.3f' % cost,
                    '%+.1f%%' % dev, stage, h.get('risk', ''), h['action']]
            cols = [BC.TEXT, BC.TEXT, BC.TEXT2,
                    BC.RED if dev >= 0 else BC.GREEN,
                    BC.TEXT3,
                    BC.GREEN if h['risk'] else BC.TEXT3,
                    BC.GREEN if h['action'] != '继续持有' else BC.TEXT]
            for j, (v, col) in enumerate(zip(vals, cols)):
                item = QLabel(v)
                item.setStyleSheet('color:%s;font-size:12px;%s' % (
                    col, 'font-weight:600;' if j == 6 else ''))
                self._tbl.setCellWidget(i, j, item)

        self.set_status('数据日 %s ｜ 涨停今/昨 %d/%d ｜ 连板今/昨 %d/%d'
                        % (r['data_date'], r['lu_today'], r['lu_prev'],
                           r['lbc_today'], r['lbc_prev']))
