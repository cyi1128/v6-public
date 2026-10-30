# -*- coding: utf-8 -*-
"""一次性补丁：services/control_screen_service.py（纯 LF）

用户选 A：控盘选股页把 A/B 批次因子（破位收复 / 量能分位）与建仓因子一起纳入
「观察」列，并加「阶段（建仓/试盘/洗盘/拉升/出货）」筛选。

只动本文件（UI 侧在另一个补丁里），不碰引擎、不改任何阈值与选股结果。
"""
import io

P = r'D:\QuantMonitorV6\services\control_screen_service.py'
s = io.open(P, encoding='utf-8', newline='').read()
assert s.count('\r\n') == 0, '源文件不是纯 LF，停手'
assert 'obs_pairs' not in s, '看起来已经打过这个补丁了，不要重复打'


def rep(old, new, cnt=1, tag=''):
    global s
    n = s.count(old)
    assert n == cnt, '锚点[%s]命中 %d 次（期望 %d）' % (tag or old[:36], n, cnt)
    s = s.replace(old, new, cnt)


# ---- 1) 模块 docstring：补上新增因子与阶段筛选 ----
rep("""    观察因子 bottom_volume_stack / red_fat_green_thin / is_c4_candidate /
            is_c6_candidate / detect_probe / detect_distribution_pattern / detect_markup
""",
    """    观察因子 bottom_volume_stack / red_fat_green_thin / is_c4_candidate /
            is_c6_candidate / detect_probe / detect_distribution_pattern / detect_markup /
            detect_breakdown_recover（破位—收复双向判据）/
            detect_volume_regime（量能分位：地量/天量/缩量上涨）
    短标签  五阶段词表在 services.control_profile（obs_tag_pairs / obs_stages），
            日K建仓表与本页共用一份，本页按「建仓→试盘→洗盘→拉升→出货」出标签，
            并支持按阶段筛选（apply_filters(stage=...)）
""", tag='docstring')

# ---- 2) 顶层 import：共享词表 ----
rep("""import services.band_pattern_engine as engine""",
    """import services.band_pattern_engine as engine""", 1, 'probe-import') \
    if 'import services.band_pattern_engine as engine' in s else None
rep("""KLINE_DB = os.path.join(PROJECT_ROOT, 'data', 'cache', 'kline_cache.duckdb')""",
    """from services.control_profile import (obs_tag_pairs as _obs_tag_pairs,
                                      obs_stages as _obs_stages)

KLINE_DB = os.path.join(PROJECT_ROOT, 'data', 'cache', 'kline_cache.duckdb')""",
    tag='import')

# ---- 3) 阶段筛选选项（紧跟在观察选项之后） ----
rep("""OBS_OPTIONS = (OBS_ALL, OBS_ANY, OBS_NO_MARKUP, OBS_PROBE, OBS_C46)
""",
    """OBS_OPTIONS = (OBS_ALL, OBS_ANY, OBS_NO_MARKUP, OBS_PROBE, OBS_C46)

# 「阶段」筛选：按操盘手法五阶段归属筛（一只股票可同时属于多阶段）。
# 选项与阶段归属映射都在 services.control_profile 里定义一处，UI 直接引用。
STAGE_OPTIONS = STAGE_PICK
""", tag='stage-opts')

# ---- 4) compute_stock：算 A/B 两个因子，并接进 _ctrl_note ----
rep("""        markup = ti.detect_markup(df) or {}

        note = engine._ctrl_note(
            score, stage, pos,
            stack.get('score'), redfat.get('score'),
            c4.get('n_ok'), c6.get('n_ok'),
            probe.get('ok'), distp.get('type'), markup.get('type'))
""",
    """        markup = ti.detect_markup(df) or {}
        # A/B 批次的两个因子（破位—收复双向判据 / 量能分位）。此前只写库、界面看不到，
        # 2026-10-11 起接入本页：既进 note（悬停可见），也进「观察」列与「阶段」筛选。
        brk = ti.detect_breakdown_recover(df) or {}
        vreg = ti.detect_volume_regime(df) or {}

        note = engine._ctrl_note(
            score, stage, pos,
            stack.get('score'), redfat.get('score'),
            c4.get('n_ok'), c6.get('n_ok'),
            probe.get('ok'), distp.get('type'), markup.get('type'),
            brk.get('type'), vreg.get('tags'))
""", tag='compute-note')

# ---- 5) rec 增加字段 ----
rep("""            'stack_score': round(float(stack.get('score') or 0.0), 1),
            'redfat_ratio': round(float(redfat.get('ratio') or 0.0), 2),
""",
    """            'stack_score': round(float(stack.get('score') or 0.0), 1),
            'redfat_ratio': round(float(redfat.get('ratio') or 0.0), 2),
            'stack_ok': bool(stack.get('ok')),
            'redfat_ok': bool(redfat.get('ok')),
            'brk_type': str(brk.get('type') or ''),
            'vreg_tags': str(vreg.get('tags') or ''),
            'vreg_pct': (round(float(vreg.get('pct')), 1)
                         if vreg.get('pct') is not None else None),
""", tag='rec-fields')

# ---- 6) 观察标签改为五阶段词表，并顺带算 stages ----
rep("""        rec['observe'] = observe_tags(rec)
        return rec
""",
    """        # 五阶段短标签（词表在 services.control_profile，日K建仓表与本页共用一份）
        _pairs = _obs_tag_pairs(
            stack_ok=rec['stack_ok'], redfat_ok=rec['redfat_ok'],
            probe_ok=rec['probe_ok'], c4_ok=rec['c4_ok'], c6_ok=rec['c6_ok'],
            brk_type=rec['brk_type'], vreg_tags=rec['vreg_tags'],
            dist_type=rec['dist_type'], markup_type=rec['markup_type'])
        rec['obs_pairs'] = [[t, lv] for t, lv in _pairs]   # 快照要落 JSON，用 list
        rec['observe'] = [t for t, lv in _pairs]
        rec['stages'] = _obs_stages(_pairs)
        return rec
""", tag='rec-observe')

# ---- 7) observe_tags：改成薄封装（保留函数名，外部/验证脚本仍在引用） ----
rep("""def observe_tags(rec):
    \"\"\"观察类短标签（来自各因子的 ok/type），供表格「观察」列显示。\"\"\"
    out = []
    try:
        if rec.get('probe_ok'):
            out.append('试盘')
        if rec.get('c4_ok'):
            out.append('C4')
        if rec.get('c6_ok'):
            out.append('C6')
        if rec.get('dist_type'):
            out.append('出货形态')
        if rec.get('markup_type'):
            out.append('拉升：%s' % rec['markup_type'])
    except Exception:
        return []
    return out
""",
    """def observe_tags(rec):
    \"\"\"五阶段观察/风险短标签，供表格「观察」列显示。

    2026-10-11 起词表移到 services.control_profile.obs_tag_pairs（日K建仓表与本页
    共用一份，避免两处词不一致）；本函数保留为薄封装，旧调用方无需改。
    输出顺序固定：建仓 → 试盘 → 洗盘 → 拉升 → 出货 → 观察规则(C4/C6)。
    \"\"\"
    try:
        return [t for t, _lv in obs_tag_pairs(rec)]
    except Exception:
        return []


def obs_tag_pairs(rec):
    \"\"\"按 rec 的因子字段生成 [(短标签, level)]（兼容老快照：字段缺就当没命中）。\"\"\"
    try:
        return _obs_tag_pairs(
            stack_ok=bool(rec.get('stack_ok')),
            redfat_ok=bool(rec.get('redfat_ok')),
            probe_ok=bool(rec.get('probe_ok')),
            c4_ok=bool(rec.get('c4_ok')),
            c6_ok=bool(rec.get('c6_ok')),
            brk_type=rec.get('brk_type') or '',
            vreg_tags=rec.get('vreg_tags') or '',
            dist_type=rec.get('dist_type') or '',
            markup_type=rec.get('markup_type') or '')
    except Exception:
        return []


def stages_of(rec):
    \"\"\"阶段归属（list）：优先用扫描时算好的 stages；老快照缺列时从观察文本回推。\"\"\"
    try:
        st = rec.get('stages')
        if st:
            return list(st)
        return _obs_stages(obs_tag_pairs(rec))
    except Exception:
        return []
""", tag='observe_tags')

# ---- 8) 范围白名单（单选）也要能按阶段筛 ----
rep("""def apply_filters(rows, min_score=85.0, pos_max=None, exclude_dist=True,
                  min_price=6.0, drop_st=True, obs=OBS_ALL):
    \"\"\"按页面上的条件筛一遍。全部条件都是「筛掉」，不改任何分数。\"\"\"""",
    """def apply_filters(rows, min_score=85.0, pos_max=None, exclude_dist=True,
                  min_price=6.0, drop_st=True, obs=OBS_ALL, stage=None):
    \"\"\"按页面上的条件筛一遍。全部条件都是「筛掉」，不改任何分数。

    stage：'建仓'/'试盘'/'洗盘'/'拉升'/'出货' 之一（'全部'/None = 不筛）。
           归属来自五阶段观察标签（services.control_profile.TAG_STAGE），
           一只股票可同时属于多个阶段（例如 拉升+出货形态 都命中）。
    \"\"\"""", tag='apply_filters-doc')

rep("""            if obs != OBS_ALL:
                _tags = r.get('observe') or []
                if obs == OBS_ANY and not _tags:
                    continue
                if obs == OBS_NO_MARKUP and r.get('markup_type'):
                    continue
                if obs == OBS_PROBE and not r.get('probe_ok'):
                    continue
                if obs == OBS_C46 and not (r.get('c4_ok') or r.get('c6_ok')):
                    continue
""",
    """            if obs != OBS_ALL:
                _tags = r.get('observe') or []
                if obs == OBS_ANY and not _tags:
                    continue
                if obs == OBS_NO_MARKUP and r.get('markup_type'):
                    continue
                if obs == OBS_PROBE and not r.get('probe_ok'):
                    continue
                if obs == OBS_C46 and not (r.get('c4_ok') or r.get('c6_ok')):
                    continue
            if stage and stage != '全部' and stage not in stages_of(r):
                continue
""", tag='apply_filters-stage')

io.open(P, 'w', encoding='utf-8', newline='').write(s)
t = io.open(P, encoding='utf-8', newline='').read()
assert t.count('\r\n') == 0, '写回后不是纯 LF'
print('control_screen_service.py 完成：%d 行（原 886 行）' % t.count('\n'))
