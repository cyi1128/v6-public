# -*- coding: utf-8 -*-
"""v3.0 专项验证（批 A：题材名进化；批 B 段后续追加）。"""
import sys, os, re, io, json
sys.path.insert(0, r'D:\QuantMonitorV6\_cloud_work\tools')
import cloud_daily_review as cdr
cdr._git_commit_push = lambda *a, **k: True   # 验证时打桩，禁止真实 git push

PASS = FAIL = 0
def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f'  FAIL  {name}')

def mk(code, name, pct, lb, price, prev, board='main', industry='半导体'):
    return {'code': code, 'name': name, 'pct': pct, 'lb': lb, 'price': price,
            'prev': prev, 'industry': industry, 'board': board, 'amount': 1e8, 'turn': 3.0}

# ================= 批 A 段 =================
print('== A1 _concept_score 边界 ==')
check('纯数字 13.96 → 10(<50)', cdr._concept_score('13.96') == 10)
check('存储芯片 → 100', cdr._concept_score('存储芯片') == 100)
check('半导体设备 → 100', cdr._concept_score('半导体设备') == 100)
check('AIGC(无中文) <50', cdr._concept_score('AIGC') < 50)
check('空串 → 0', cdr._concept_score('') == 0)
check('黑名单"板块" 评分≥50 但被过滤', cdr._concept_score('板块') >= 50 and '板块' in cdr._BLACKLIST)

print('== A2 _board_sec_info 兜底链 ==')
# 混合组：2 只有效 + 1 只脏
grp_mixed = [mk('000201', '甲', 3.2, 1.9, 10.3, 10.0, 'main', '存储芯片'),
             mk('000202', '乙', 2.8, 1.8, 10.3, 10.0, 'main', '存储芯片'),
             mk('000203', '丙', 2.6, 1.8, 10.3, 10.0, 'main', '13.96')]
name, dirty = cdr._board_sec_info(grp_mixed)
check('混合组 → 存储芯片', name == '存储芯片')
check('混合组 → dirty 含 13.96 一条', len(dirty) == 1 and dirty[0]['concept'] == '13.96')
check('dirty reason 含 score', dirty and 'score' in dirty[0]['reason'])
# 全脏组
grp_all = [mk('000211', '龙一', 3.5, 2.0, 10.4, 10.0, 'main', '13.96'),
           mk('000212', '跟二', 3.0, 1.8, 10.3, 10.0, 'main', ''),
           mk('000213', '跟三', 2.8, 1.8, 10.3, 10.0, 'main', '123')]
name2, dirty2 = cdr._board_sec_info(grp_all)
check('全脏组 → 龙头名相关板块', name2 == '龙一相关板块')
check('全脏组 → dirty 2 条（空概念跳过）', len(dirty2) == 2)
# 龙头锚定：龙头概念唯一高分，其余全脏
grp_anchor = [mk('000221', '锚一', 5.0, 2.2, 10.6, 10.0, 'main', 'AI算力'),
              mk('000222', '锚二', 3.0, 1.8, 10.3, 10.0, 'main', ''),
              mk('000223', '锚三', 2.6, 1.8, 10.3, 10.0, 'main', '')]
name3, _ = cdr._board_sec_info(grp_anchor)
check('龙头锚定 → AI算力（其余脏）', name3 == 'AI算力')
# 空组
name4, dirty4 = cdr._board_sec_info([])
check('空组 → 热门板块', name4 == '热门板块' and dirty4 == [])

print('== A3 兼容层 ==')
check('_board_sec_name 返回 str', isinstance(cdr._board_sec_name(grp_mixed), str))
check('_board_sec_name 兼容 = _board_sec_info[0]', cdr._board_sec_name(grp_mixed) == name)

print('== A4 _board_start 带 dirty + 非数字 sec ==')
rows = [mk('000231', '甲', 3.2, 1.9, 10.3, 10.0, 'main', '存储芯片'),
        mk('000232', '乙', 2.8, 1.8, 10.3, 10.0, 'main', '存储芯片'),
        mk('000233', '丙', 2.6, 1.8, 10.3, 10.0, 'main', '存储芯片')]
b = cdr._board_start(rows, '震荡')
check('3只共振命中', b is not None)
check('sec 非数字含中文', b is not None and bool(re.search(r'[\u4e00-\u9fff]', b['sec'])))
check('best 带 dirty 键', b is not None and 'dirty' in b)
check('启动卡 sec 同源', b['sec'] == '存储芯片')

print('== A5 dirty_data_log 落盘 ==')
cdr._append_dirty_log(dirty)
if os.path.exists(cdr.DIRTY_PATH):
    logs = json.load(open(cdr.DIRTY_PATH, encoding='utf-8'))
    check('dirty log 文件含记录', isinstance(logs, list) and len(logs) >= 1)
    rec = logs[-1]
    check('记录含 ts/concept/from_stock/reason',
          all(k in rec for k in ('ts', 'concept', 'from_stock', 'reason')))
    check('记录的 from_stock=000203', rec['from_stock'] == '000203')
else:
    check('dirty log 文件存在', False)

print('== A6 源码机制 ==')
src = open(r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py', encoding='utf-8').read()
for kw in ('_BLACKLIST', '_INDUSTRY_KEYWORDS', 'def _concept_score', 'def _board_sec_info',
           'def _is_digit_serial', 'def _append_dirty_log', 'DIRTY_PATH'):
    check(f'源码含「{kw}」', kw in src)
check('blacklist 含"板块"', '"板块"' in src.split('_BLACKLIST =')[1].split('}')[0])

# ================= 批 B 段 =================
print('== B1 _data_health 健康判定 ==')
import tempfile
_tmp = tempfile.mkdtemp()
cdr.HEALTH_STATE_PATH = os.path.join(_tmp, 'health.json')
cdr.THEMES_PATH = os.path.join(_tmp, 'themes.json')
cdr.LIFECYCLE_PATH = os.path.join(_tmp, 'lc.json')
h0 = cdr._data_health([])
check('空数据 → abnormal', h0['abnormal'] is True)
check('空数据无缓存 → confidence=低', h0['confidence'] == '低')
h1 = cdr._data_health([mk(f'0002{i}', f'a{i}', 3.0, 1.8, 10.3, 10.0) for i in range(25)])
check('正常数据 → confidence=高', h1['confidence'] == '高')
big = [mk(f'0003{i}', f'n{i}', 3.0, 1.8, 10.3, 10.0) for i in range(85)]
h2 = cdr._data_health(big)
check('>80 只(常态100只) → 正常', h2['abnormal'] is False)
check('>80 只有缓存 → confidence=高', h2['confidence'] == '高')
# 连续两次 abnormal → conservative
h3 = cdr._data_health([])
h3b = cdr._data_health([])
check('连续两次异常 → conservative', h3b['conservative'] is True)
check('conservative 时 confidence 仍低', h3b['confidence'] == '低')

print('== B2 缓存机制 ==')
with open(cdr.THEMES_PATH, 'w', encoding='utf-8') as f:
    json.dump({'theme_name': 'AI算力', 'ts': cdr._bj_now().strftime('%Y-%m-%d %H:%M:%S'),
               'stocks': ['300750']}, f, ensure_ascii=False)
check('缓存新鲜(<90分钟) → True', cdr._cache_themes_fresh() is True)
with open(cdr.THEMES_PATH, 'w', encoding='utf-8') as f:
    json.dump({'theme_name': 'AI算力', 'ts': '2020-01-01 00:00:00', 'stocks': []}, f, ensure_ascii=False)
check('缓存过期 → False', cdr._cache_themes_fresh() is False)

print('== B3 生命周期迁移 ==')
st2 = [mk('000311', 'a', 3.0, 1.8, 10.3, 10.0, 'main', 'AI算力'),
       mk('000312', 'b', 2.6, 1.7, 10.3, 10.0, 'main', 'AI算力')]
st3 = [mk('000321', 'a', 6.0, 2.2, 10.6, 10.0, 'main', 'AI算力'),
       mk('000322', 'b', 5.0, 2.0, 10.5, 10.0, 'main', 'AI算力'),
       mk('000323', 'c', 4.0, 1.9, 10.4, 10.0, 'main', 'AI算力')]
s_ment = cdr._theme_lifecycle('AI算力', st2)
check('首次出现 → 萌芽', s_ment == '萌芽')
s_fa = cdr._theme_lifecycle('AI算力', st3)
check('再次出现 → 发酵', s_fa == '发酵')
s_lu = [mk('000331', 'x', 9.5, 3.0, 11.0, 10.0, 'main', 'AI算力'),
        mk('000332', 'y', 9.6, 2.8, 10.9, 10.0, 'main', 'AI算力'),
        mk('000333', 'z', 6.0, 2.2, 10.6, 10.0, 'main', 'AI算力')]
s_high = cdr._theme_lifecycle('AI算力', s_lu)
check('≥2只涨停 → 高潮', s_high == '高潮')
# 高潮后红盘<2 → 退潮（构造 prev 高潮 + 当前组 reds<2：传 1 只红盘 + 1 只绿盘）
s_tui = cdr._theme_lifecycle('AI算力', [mk('000341', 'x', 1.0, 1.2, 10.1, 10.0, 'main', 'AI算力'),
                                        mk('000342', 'y', -1.0, 0.8, 9.9, 10.0, 'main', 'AI算力')])
check('高潮后红盘<2 → 退潮', s_tui == '退潮')

print('== B4 退潮反向卡 ==')
with open(cdr.LIFECYCLE_PATH, 'w', encoding='utf-8') as f:
    json.dump({'AI算力': {'status': '发酵', 'push_count': 2, 'last_push_type': '观察卡'}}, f, ensure_ascii=False)
rows_tui = [mk('000351', 'x', 1.0, 1.2, 10.1, 10.0, 'main', 'AI算力')]
ret = cdr._detect_retreat(rows_tui, set(), '2026-10-21')
check('曾推过+红盘<2 → 检出退潮', ret and ret[0][0] == 'AI算力')
ret2 = cdr._detect_retreat([], {'R|AI算力|2026-10-21'}, '2026-10-21')
check('当日已推反向卡 → 不再检', ret2 == [])
rc = cdr._board_reverse_card('AI算力', '发酵')
for kw in ('退潮', '减仓观望', '移出', '别在退潮期抄底'):
    check(f'反向卡含「{kw}」', kw in rc)

print('== B5 need_streak 共振增强 ==')
rows_weak = [mk('000361', 'a', 3.0, 1.8, 10.3, 10.0, 'main', '存储芯片'),
             mk('000362', 'b', 2.8, 1.8, 10.3, 10.0, 'main', '存储芯片'),
             mk('000363', 'c', 2.6, 1.8, 10.3, 10.0, 'main', '存储芯片')]
b_ns = cdr._board_start(rows_weak, '震荡', need_streak=True)
check('无≥5%无涨停 + need_streak → 不命中', b_ns is None)
b_ns2 = cdr._board_start(rows_weak, '震荡', need_streak=False)
check('无≥5%无涨停 + 默认 → 命中（兼容旧行为）', b_ns2 is not None)
rows_str = [mk('000371', 'a', 6.0, 2.2, 10.6, 10.0, 'main', '存储芯片'),
            mk('000372', 'b', 2.8, 1.8, 10.3, 10.0, 'main', '存储芯片'),
            mk('000373', 'c', 2.6, 1.8, 10.3, 10.0, 'main', '存储芯片')]
b_ns3 = cdr._board_start(rows_str, '震荡', need_streak=True)
check('含≥5% + need_streak → 命中', b_ns3 is not None)

print('== B6 源码机制 ==')
src2 = open(r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py', encoding='utf-8').read()
for kw in ('def _data_health', 'def _cache_themes_fresh', 'def _save_cache_themes',
           'def _theme_lifecycle', 'def _detect_retreat', 'def _board_reverse_card',
           'HEALTH_STATE_PATH', '_AMT_HIGH', 'need_streak', 'confidence=低'):
    check(f'源码含「{kw}」', kw in src2)

print('== C1 _board_payload 中间层字段 ==')
_prows = [mk('000381', 'a', 6.0, 2.2, 10.6, 10.0, 'main', 'AI算力'),
          mk('000382', 'b', 5.0, 2.0, 10.5, 10.0, 'main', 'AI算力'),
          mk('000383', 'c', 9.9, 3.1, 11.0, 10.0, 'main', 'AI算力'),
          mk('000384', 'd', 3.0, 1.8, 10.3, 10.0, 'main', 'AI算力')]
_pl = cdr._board_payload('启动卡', '高', 'AI算力', '3只同时放量共振确认', '发酵', _prows,
                         '资金集中涌入', '龙头炸板减仓', cdr._VERIFY_NODES, 'eastmoney',
                         ['13.96'], 'HTML')
for _f in ('card_type', 'confidence', 'theme_name', 'trigger_reason', 'lifecycle_status',
           'leaders', 'followers', 'volume_emotion', 'risk_warning', 'verify_nodes',
           'data_source', 'raw_dirty_concepts', 'push_content'):
    check(f'payload 含字段「{_f}」', _f in _pl)
check('payload card_type=启动卡', _pl['card_type'] == '启动卡')
check('payload leaders=涨幅前3（含已涨停作证据）', len(_pl['leaders']) == 3)
check('payload leaders[0] 是涨停票（热度证据）', _pl['leaders'][0]['code'] == '000383')
check('payload followers=第4只', len(_pl['followers']) == 1 and _pl['followers'][0]['code'] == '000384')
check('payload verify_nodes 三段', len(_pl['verify_nodes']) == 3)
check('payload raw_dirty 透传', _pl['raw_dirty_concepts'] == ['13.96'])

print('== C2 验证节点固定三段 ==')
check('_VERIFY_NODES 09:45', cdr._VERIFY_NODES[0] == '09:45 看龙头是否继续封板/回封')
check('_VERIFY_NODES 10:30', cdr._VERIFY_NODES[1] == '10:30 看跟风是否扩散')
check('_VERIFY_NODES 14:00', cdr._VERIFY_NODES[2] == '14:00 看整体是否回落')

print('== C3 观察卡新增内容 ==')
_ww = {'sec': 'AI算力', 'stocks': _prows, 'fzn': 3, 'dirty': []}
_wc = cdr._board_watch_card(_ww, 62, '偏多', confidence='高', lifecycle='萌芽', data_source='eastmoney')
check('观察卡仍返回 str（不破坏调用方）', isinstance(_wc, str))
for _kw in ('验证节点', '09:45 看龙头是否继续封板/回封', '10:30 看跟风是否扩散', '14:00 看整体是否回落',
            '若龙头炸板或板块红盘不足 2 只，则观察失败', '置信度高（数据源正常）'):
    check(f'观察卡含「{_kw}」', _kw in _wc)

print('== C4 启动卡新增内容 ==')
_bs = {'sec': 'AI算力', 'stocks': _prows, 'fzn': 3, 'dirty': []}
_bc = cdr._board_card(_bs, 62, '偏多', confidence='高', lifecycle='发酵', data_source='eastmoney')
check('启动卡仍返回 str（不破坏调用方）', isinstance(_bc, str))
for _kw in ('启动后观察窗口', '30 分钟内看龙头封单与共振数，失守即减仓', '置信度高（数据源正常）'):
    check(f'启动卡含「{_kw}」', _kw in _bc)

print('== C5 theme_pushes.json 落盘 ==')
_tmp3 = tempfile.mkdtemp()
cdr.PUSHES_PATH = os.path.join(_tmp3, 'pushes.json')
cdr._append_push(_pl)
with open(cdr.PUSHES_PATH, encoding='utf-8') as _f:
    _pushes = json.load(_f)
check('推送快照累计 1 条', len(_pushes) == 1)
check('快照含 ts/theme/card_type', 'ts' in _pushes[0] and _pushes[0]['theme_name'] == 'AI算力'
      and _pushes[0]['card_type'] == '启动卡')
check('快照 board_snapshot ≤8', len(_pushes[0]['board_snapshot']) <= 8)
cdr._append_push({'card_type': '静默'})
with open(cdr.PUSHES_PATH, encoding='utf-8') as _f:
    _pushes2 = json.load(_f)
check('静默卡不落盘', len(_pushes2) == 1)

print('== C6 源码机制 ==')
for kw in ('def _board_payload', 'def _append_push', '_VERIFY_NODES'):
    check(f'源码含「{kw}」', kw in src2)

print(f'\n=== {PASS} PASS / {FAIL} FAIL ===')
sys.exit(1 if FAIL else 0)
