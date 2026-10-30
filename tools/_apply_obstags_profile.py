# -*- coding: utf-8 -*-
"""一次性补丁：在 services/control_profile.py 末尾追加「五阶段观察/风险短标签」共享词表。

背景：2026-10-11 对照操盘手法拆解逐条核对后，用户选 A+B —— 把建仓/试盘/洗盘/拉升/出货
五个阶段的因子都标注到界面上（此前 A/B 批次只写库、建仓因子只出数值）。
词表集中在这里定义一次，日K建仓表与控盘选股页共用，避免两处词不一致。

本文件是 CRLF 文件，写回必须用显式 \r\n。
"""
import io

P = r'D:\QuantMonitorV6\services\control_profile.py'
s = io.open(P, encoding='utf-8', newline='').read()
assert s.count('\r\n') == s.count('\n'), '源文件不是纯 CRLF，停手'
anchor = "def ctrl_tooltip(info):"
assert s.count(anchor) == 1, '锚点不唯一：%d' % s.count(anchor)
assert '_OBS_TAG_ORDER' not in s, '看起来已经打过这个补丁了，不要重复打'

BLOCK = '''# ============================================================
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
    return str(text or '').split(':')[0].split('\uff1a')[0].strip()


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


def obs_tag_text(pairs, sep='\u00b7'):
    """把 tag 对拼成表格文本（配色由各自 UI 按 level 决定）。"""
    return sep.join(t for t, _lv in (pairs or []))


def obs_tag_color(level, fallback='#9e9e9e'):
    """level -> 颜色（与项目 battle_widgets.BC 的语义色一致）。"""
    return {'risk': '#c62828', 'warn': '#ef6c00', 'gold': '#b8860b',
            'info': '#1565c0'}.get(str(level or ''), fallback)


'''
s = s.replace(anchor, BLOCK.replace('\n', '\r\n') + anchor, 1)
io.open(P, 'w', encoding='utf-8', newline='').write(s)

_t = io.open(P, encoding='utf-8', newline='').read()
assert _t.count('\r\n') == _t.count('\n'), '写回后不是纯 CRLF'
print('control_profile.py 已追加共享词表：%d 行 / CRLF=%d 裸LF=%d'
      % (_t.count('\n'), _t.count('\r\n'), _t.count('\n') - _t.count('\r\n')))
