# -*- coding: utf-8 -*-
"""控盘度统一查询入口 —— 所有模块共用一份计算和一份阈值。

背景
----
控盘度（control_score）+ 洗盘/出货（stage_guess）原本只在「日K建仓」链路里算过，
其他模块（自选评分 / 竞价筛选 / 今日涨停 / 分时做T / 追踪）想看只能自己重算。
这个模块把它抽出来，全项目只走这一条路，避免两套口径。

数据来源与「日K建仓」完全一致（不是另写一套）：
    K线   services.kline_cache_service.get_latest_kline(code, 120)  -> **只读本地**
    DataFrame       band_pattern_engine._bars_to_df(bars)
    评分   strategy.base.TechnicalIndicators.estimate_control_score
    阶段   strategy.base.TechnicalIndicators.judge_wash_or_distribute
    位置   近120日位置 (close - min120) / (max120 - min120)
    文案   band_pattern_engine._ctrl_note(...)
阈值（_CTRL_HIGH / _CTRL_CAND / _CTRL_DIST / _CTRL_POS_LOW）只在
services.band_pattern_engine.py 里定义一处，本模块不重复定义。

用法
----
    from services.control_profile import get_ctrl_map, ctrl_cell
    m = get_ctrl_map([r['code'] for r in rows])     # {code: {...}} 或 {code: None}
    txt, color = ctrl_cell(m.get(code))             # '98·候选' + '#2e7d32'

性能与线程安全
-----
- 按 (code, 最后一根K线日期) 做内存缓存：同一交易日同一只股票只算一次。
- 单只首次约 28 ms（本地 duckdb + 120 根K线），同一交易日内缓存命中几乎 0。
- **必须放在 run_async 后台线程里调用**，不要在 UI 线程直接调，
  否则列表刷新时会卡一下（这也是本项目历史上"早盘卡顿"的来源之一）。
- _CACHE 加了锁；多线程同时刷新不同模块安全。
"""
import threading

_CACHE = {}          # code -> (data_date, score, stage, pos, tip)
_LOCK = threading.Lock()

# 无数据 / 无提示时统一用这两个值，方便各模块显示一致
NO_DATA_TEXT = '--'
NO_DATA_COLOR = '#9e9e9e'
NO_TIP_COLOR = '#9e9e9e'


def _engine():
    """懒加载引擎模块（避免启动期循环 import）。"""
    import services.band_pattern_engine as E
    return E


def _load_bars_local(code):
    """只读本地 kline_cache，**不做网络兜底**。

    引擎的 _load_bars 在缓存缺失时会走 pytdx/腾讯在线抓 120 天K线，
    单只可能几百 ms 甚至卡住 —— 列表刷新（自选/涨停/竞价）绝不能这样。
    本地没有就返回 []，界面上显示 '--'，宁可空也不能卡 UI。
    """
    try:
        from services.kline_cache_service import get_latest_kline
        bars = get_latest_kline(code, count=120)
        if bars and len(bars) >= 60:
            return bars
    except Exception:
        pass
    return []


def compute_one(code):
    """算单只：返回 dict(score, stage, pos, tip, data_date, ok)。

    任何异常都吞掉并返回 ok=False，不让一个坏数据把整个列表刷新打断。
    """
    try:
        E = _engine()
        bars = _load_bars_local(code)
        df = E._bars_to_df(bars)
        if df is None:
            return {'ok': False, 'score': None, 'stage': '', 'pos': None,
                    'tip': '', 'data_date': ''}
        from strategy.base import TechnicalIndicators as _TI
        _ti = _TI()
        score = float(_ti.estimate_control_score(df))
        stage = _ti.judge_wash_or_distribute(df)
        _t = df['close'].tail(120)
        _lo, _hi = float(_t.min()), float(_t.max())
        pos = (float(df['close'].iloc[-1]) - _lo) / (_hi - _lo + 1e-8)
        tip = E._ctrl_note(score, stage, pos)
        return {'ok': True, 'score': score, 'stage': stage, 'pos': pos,
                'tip': tip, 'data_date': str(bars[-1].get('date') or '')[:10]}
    except Exception:
        return {'ok': False, 'score': None, 'stage': '', 'pos': None,
                'tip': '', 'data_date': ''}


def get_ctrl_map(codes, force=False, cached_only=False):
    """批量取控盘信息，返回 {code: info_dict 或 None}。

    codes 可以是 list / set，内部去重；顺序无关。
    已缓存且 K线日期没变时直接复用，force=True 强制重算。
    cached_only=True 时**绝不计算**，只返回已有缓存的条目（可在 UI 线程直接调）。
    """
    out = {}
    todo = []
    codes = list(dict.fromkeys([str(c) for c in (codes or []) if c]))
    with _LOCK:
        for c in codes:
            if not force and c in _CACHE:
                out[c] = _CACHE[c]
            else:
                todo.append(c)
    if cached_only:
        return out
    for c in todo:
        info = compute_one(c)
        with _LOCK:
            _CACHE[c] = info
        out[c] = info
    return out


def clear_cache():
    """清空内存缓存（换交易日 / 手动刷新时用）。"""
    with _LOCK:
        _CACHE.clear()


# 真正决定表格短标签的「控盘提示」白名单（与 band_pattern_engine._ctrl_note_tags
# 的三个文案逐字一致）。**必须白名单比对，不能拿整串 note 做关键词反推** ——
# C4/C6/建仓因子等观察类文案与控盘提示共用同一串 note，反推会把只命中观察规则的
# 股票误标成绿色「候选」（2026-10-10 实测：控盘 72 分却显示 候选，虚增 15 -> 43 条）。
_CTRL_TAGS = ('高度控盘 + 疑似洗盘，关注启动', '出货风险警示', '高度控盘候选')
_LABEL_COLORS = {'洗盘': '#ef6c00', '出货': '#c62828', '候选': '#2e7d32'}


def ctrl_tags(tag_str='', full_tip=''):
    """取出真正的「控盘提示」标签（list）。

    优先用引擎写进 DB 的 ctrl_tag（权威、无需解析）；它为空时退回在白名单里
    比对 note 片段（兼容旧库 / 快照恢复的行）。
    """
    out = []
    try:
        for _src in (tag_str, full_tip):
            for _s in str(_src or '').replace('\n', ' ').split(' ｜ '):
                _s = _s.strip()
                if _s in _CTRL_TAGS and _s not in out:
                    out.append(_s)
    except Exception:
        return []
    return out


def ctrl_label(tag_str='', full_tip=''):
    """返回 (短标签, 颜色)；没有任何控盘提示时返回 ('', 灰色)。"""
    _tags = ctrl_tags(tag_str, full_tip)
    if not _tags:
        return '', NO_TIP_COLOR
    _j = ' ｜ '.join(_tags)
    if '疑似洗盘' in _j:
        return '洗盘', _LABEL_COLORS['洗盘']
    if '出货' in _j:
        return '出货', _LABEL_COLORS['出货']
    return '候选', _LABEL_COLORS['候选']


def ctrl_cell(info):
    """把 info 转成表格里一格文字 + 颜色。

    有提示: '98·候选'(绿) / '80·出货'(红) / '97·洗盘'(橙)
    无提示: '71'(灰)        没数据: '--'(灰)
    """
    if not info or not info.get('ok') or info.get('score') is None:
        return NO_DATA_TEXT, NO_DATA_COLOR
    score = float(info['score'])
    # 标签只看「控盘提示」（tag 或白名单片段），观察类文案不参与 —— 见 ctrl_tags 说明
    _label, _color = ctrl_label(info.get('ctrl_tag') or '', info.get('tip') or '')
    if _label:
        return '%d·%s' % (int(round(score)), _label), _color
    return (str(int(round(score))) if score else NO_DATA_TEXT), NO_TIP_COLOR


# ============================================================
# 五阶段「观察 / 风险」短标签（全项目唯一词表，2026-10-11 新增）
# ============================================================
# 来历：对照「机构/庄家/主力操盘控盘手法拆解」逐条核查后，把建仓/试盘/洗盘/拉升/出货
# 五个阶段的因子统一标注出来：
#   建仓  堆量（底部堆量）/ 红肥绿瘦          -> bottom_volume_stack / red_fat_green_thin
#   试盘  试盘（长上影测试抛压）              -> detect_probe
#   洗盘  洗盘收复（破位缩量后快速收复）/ 地量 -> detect_breakdown_recover / detect_volume_regime
#   拉升  拉升:<形态> / 缩量上涨              -> detect_markup / detect_volume_regime
#   出货  破位警示（放量破位未收回）/ 天量 / 出货形态 -> detect_breakdown_recover /
#          detect_volume_regime / detect_distribution_pattern
# level 决定界面配色：risk=风险(红) / warn=提示(橙) / gold=试盘(金) / info=中性(蓝)。
# ⚠ 洗盘收复与地量在标定里没有正向价值（只作「状态存在」的事实标注，不是买入提示）；
#   要整类收起来，把对应 UI 的开关或过滤条件改掉即可，不必改这里。
_OBS_TAG_ORDER = ('堆量', '红肥绿瘦', '试盘', 'C4', 'C6', '洗盘收复', '地量',
                  '拉升', '缩量上涨', '破位警示', '天量', '出货形态')
OBS_TAG_LEVEL = {'破位警示': 'risk', '天量': 'risk', '出货形态': 'risk',
                 '拉升': 'warn', '缩量上涨': 'warn', '试盘': 'gold'}
# 阶段归属（供「阶段」下拉筛选）：一只股票可同时属于多个阶段
TAG_STAGE = {'堆量': '建仓', '红肥绿瘦': '建仓', '试盘': '试盘',
             '洗盘收复': '洗盘', '地量': '洗盘', '拉升': '拉升', '缩量上涨': '拉升',
             '破位警示': '出货', '天量': '出货', '出货形态': '出货'}
STAGE_PICK = ('全部', '建仓', '试盘', '洗盘', '拉升', '出货')


def _tag_key(text):
    """'拉升:阶梯式上行' -> '拉升'（去掉形态后缀，供查表用）。"""
    return str(text or '').split(':')[0].split('：')[0].strip()


def obs_tag_pairs(stack_ok=False, redfat_ok=False, probe_ok=False, c4_ok=False, c6_ok=False,
                  brk_type='', vreg_tags='', dist_type='', markup_type=''):
    """按五阶段口径生成 [(短标签, level)]，顺序固定（建仓→试盘→洗盘→拉升→出货→观察规则）。"""
    cand = []
    if stack_ok:
        cand.append(('堆量', '堆量', 'info'))
    if redfat_ok:
        cand.append(('红肥绿瘦', '红肥绿瘦', 'info'))
    if probe_ok:
        cand.append(('试盘', '试盘', 'gold'))
    if c4_ok:
        cand.append(('C4', 'C4', 'info'))
    if c6_ok:
        cand.append(('C6', 'C6', 'info'))
    _bt = str(brk_type or '')
    _vt = str(vreg_tags or '')
    if _bt == '洗盘收复':
        cand.append(('洗盘收复', '洗盘收复', 'info'))
    if '地量' in _vt:
        cand.append(('地量', '地量', 'info'))
    if markup_type:
        cand.append(('拉升', '拉升:%s' % str(markup_type), 'warn'))
    if '缩量上涨' in _vt:
        cand.append(('缩量上涨', '缩量上涨', 'warn'))
    if _bt == '破位未收':
        cand.append(('破位警示', '破位警示', 'risk'))
    if '天量' in _vt:
        cand.append(('天量', '天量', 'risk'))
    if dist_type:
        cand.append(('出货形态', '出货形态', 'risk'))
    _idx = {k: i for i, k in enumerate(_OBS_TAG_ORDER)}
    cand.sort(key=lambda x: _idx.get(x[0], 99))
    return [(t, lv) for _k, t, lv in cand]


def obs_stages(pairs):
    """由 tag 对推出所属阶段（list，可能多阶段）。"""
    out = []
    for t, _lv in (pairs or []):
        s = TAG_STAGE.get(_tag_key(t))
        if s and s not in out:
            out.append(s)
    return out


def obs_tag_text(pairs, sep='·'):
    """把 tag 对拼成表格文本（配色由各自 UI 按 level 决定）。"""
    return sep.join(t for t, _lv in (pairs or []))


def obs_tag_color(level, fallback='#9e9e9e'):
    """level -> 颜色（与项目 battle_widgets.BC 的语义色一致）。"""
    return {'risk': '#c62828', 'warn': '#ef6c00', 'gold': '#b8860b',
            'info': '#1565c0'}.get(str(level or ''), fallback)


def ctrl_tooltip(info):
    """表格 tooltip：控盘分 + 阶段 + 完整文案。"""
    if not info or not info.get('ok') or info.get('score') is None:
        return '控盘度：暂无K线数据'
    s = '控盘分 %.1f（%s）' % (float(info['score']), info.get('stage') or '--')
    if info.get('pos') is not None:
        s += '\n近120日位置 %.0f%%' % (float(info['pos']) * 100)
    if info.get('tip'):
        s += '\n[控盘] ' + str(info['tip'])
    if info.get('data_date'):
        s += '\n数据日 ' + str(info['data_date'])
    return s
