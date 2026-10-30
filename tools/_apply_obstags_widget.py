# -*- coding: utf-8 -*-
"""一次性补丁：ui/battle_widgets/control_screen_widget.py（纯 LF）

A 项的 UI 侧：把「观察」列扩成五阶段标签（建仓/试盘/洗盘/拉升/出货），
并加一个「阶段」下拉筛选（与观察下拉并列）。只动本文件。
"""
import io

P = r'D:\QuantMonitorV6\ui\battle_widgets\control_screen_widget.py'
s = io.open(P, encoding='utf-8', newline='').read()
assert s.count('\r\n') == 0, '源文件不是纯 LF，停手'
assert '_cb_stage' not in s, '看起来已经打过这个补丁了，不要重复打'


def rep(old, new, cnt=1, tag=''):
    global s
    n = s.count(old)
    assert n == cnt, '锚点[%s]命中 %d 次（期望 %d）' % (tag or old[:40], n, cnt)
    s = s.replace(old, new, cnt)


# ---- 1) 「观察」列加宽（现在最多 4~5 个标签：堆量·试盘·拉升:阶梯式上行·C6） ----
rep("PAGE_WIDTHS = [96, 66, 70, 74, 230, 170, 70, 58, 58, 96, 190, 260, 90]",
    "PAGE_WIDTHS = [96, 66, 70, 74, 230, 170, 70, 58, 58, 96, 250, 260, 90]",
    tag='widths')
rep("PAGE_WIDTHS_MAX = {C_BIZ: 330, C_OBS: 330, C_ANN: 460}",
    "PAGE_WIDTHS_MAX = {C_BIZ: 330, C_OBS: 430, C_ANN: 460}",
    tag='widths-max')

# ---- 2) 观察下拉的 tooltip 与后面新增的「阶段」下拉 ----
rep("""        self._cb_obs.setToolTip('观察类因子（C4/C6/试盘/出货形态/拉升），只做筛选不改分数')
        bar1.addWidget(self._cb_obs)
""",
    """        self._cb_obs.setToolTip(
            '观察类因子（五阶段：建仓堆量/红肥绿瘦、试盘、洗盘收复/地量、拉升/缩量上涨、'
            '破位警示/天量/出货形态 + C4/C6），只做筛选不改分数')
        bar1.addWidget(self._cb_obs)

        # 「阶段」筛选（A 项）：按操盘手法五阶段归属筛；选项与归属映射都在
        # services.control_profile（TAG_STAGE / STAGE_PICK）里定义一处。
        bar1.addWidget(L('阶段', BC.TEXT2, 11))
        self._cb_stage = QComboBox()
        self._cb_stage.addItems(list(SS.STAGE_OPTIONS))
        self._cb_stage.setFixedWidth(88)
        self._cb_stage.setStyleSheet(_COMBO_STYLE)
        self._cb_stage.setToolTip(
            '按「手法阶段」筛：建仓/试盘/洗盘/拉升/出货（一只股票可同时属于多个阶段，'
            '例如同时命中拉升与出货形态）')
        bar1.addWidget(self._cb_stage)
""", tag='stage-combo')

# ---- 3) 信号连接（观察下拉下面就是它，加一行） ----
rep("""        self._cb_obs.currentIndexChanged.connect(self._apply_and_render)""",
    """        self._cb_obs.currentIndexChanged.connect(self._apply_and_render)
        self._cb_stage.currentIndexChanged.connect(self._apply_and_render)""",
    tag='stage-connect')

# ---- 4) 筛选透传 ----
rep("""            obs=self._cb_obs.currentText())""",
    """            obs=self._cb_obs.currentText(),
            stage=self._cb_stage.currentText())""", tag='filtered')

# ---- 5) 配色：按 level 判（风险红 > 拉升/缩量上涨橙 > 试盘金 > 中性蓝） ----
rep('''def _obs_color(tags):
    """观察标签配色：出货形态红、拉升橙、试盘金、C4/C6 蓝。"""
    tags = tags or []
    if '出货形态' in tags:
        return BC.RED
    for t in tags:
        if str(t).startswith('拉升'):
            return BC.ORANGE
    if '试盘' in tags:
        return BC.GOLD
    if tags:
        return BC.BLUE
    return BC.TEXT3
''',
    '''def _obs_color(tags):
    """观察标签配色（按 level）：风险红 > 拉升/缩量上涨橙 > 试盘金 > 中性蓝。

    level 由 services.control_profile.OBS_TAG_LEVEL 给（词表唯一来源），
    这里只做「一张格子一个颜色」的降级 —— 取整格里级别最高的那个颜色。
    """
    from services.control_profile import OBS_TAG_LEVEL
    tags = tags or []
    _lv = []
    for t in tags:
        _k = str(t).split(':')[0].split('\\uff1a')[0].strip()
        _lv.append(OBS_TAG_LEVEL.get(_k, 'info'))
    if 'risk' in _lv:
        return BC.RED
    if 'warn' in _lv:
        return BC.ORANGE
    if 'gold' in _lv:
        return BC.GOLD
    if _lv:
        return BC.BLUE
    return BC.TEXT3
''', tag='obs-color')

# ---- 6) tooltip 补上 A/B 两个因子与阶段归属 ----
rep("""                '出货形态=%s ｜ 拉升=%s\\n'
                '底部堆量分=%.1f ｜ 红肥绿瘦比=%.2f\\n'
                '提示：%s'
                % (rec.get('stage') or '', float(rec.get('pos') or 0),
                   float(rec.get('score') or 0),
                   int(rec.get('c4_n') or 0), int(rec.get('c6_n') or 0),
                   '是' if rec.get('probe_ok') else '否', rec.get('probe_stage') or '-',
                   rec.get('dist_type') or '-', rec.get('markup_type') or '-',
                   float(rec.get('stack_score') or 0),
                   float(rec.get('redfat_ratio') or 0),
                   rec.get('note') or '（无）'))""",
    """                '出货形态=%s ｜ 拉升=%s\\n'
                '底部堆量分=%.1f%s ｜ 红肥绿瘦比=%.2f%s\\n'
                '破位/收复=%s ｜ 量能分位=%s%s\\n'
                '手法阶段=%s\\n'
                '提示：%s'
                % (rec.get('stage') or '', float(rec.get('pos') or 0),
                   float(rec.get('score') or 0),
                   int(rec.get('c4_n') or 0), int(rec.get('c6_n') or 0),
                   '是' if rec.get('probe_ok') else '否', rec.get('probe_stage') or '-',
                   rec.get('dist_type') or '-', rec.get('markup_type') or '-',
                   float(rec.get('stack_score') or 0),
                   '（达标）' if rec.get('stack_ok') else '',
                   float(rec.get('redfat_ratio') or 0),
                   '（达标）' if rec.get('redfat_ok') else '',
                   rec.get('brk_type') or '-', rec.get('vreg_tags') or '-',
                   ('（分位 %.0f%%）' % float(rec.get('vreg_pct'))
                    if rec.get('vreg_pct') is not None else ''),
                   '·'.join(SS.stages_of(rec)) or '-',
                   rec.get('note') or '（无）'))""", tag='obs-tip')

# ---- 7) 模块 docstring 同步 ----
rep("""「最新公告」放 MM-DD + 标题（标题很长会被省略号截断，悬停看全文，260 够）。""",
    """「最新公告」放 MM-DD + 标题（标题很长会被省略号截断，悬停看全文，260 够）。""",
    tag='noop') if False else None

io.open(P, 'w', encoding='utf-8', newline='').write(s)
t = io.open(P, encoding='utf-8', newline='').read()
assert t.count('\r\n') == 0, '写回后不是纯 LF'
print('control_screen_widget.py 完成：%d 行（原 668 行）' % t.count('\n'))
