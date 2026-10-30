# -*- coding: utf-8 -*-
"""主力雷达 V4 升级：ZSYS 换新版九问研判提示词 + 输入schema化(pool/hot_sectors) + 解析meta/radar/judged_all/excluded
+ 字段映射V4全字段 + 渲染新版式(模式匹配/序列阶段/突破验收/洗盘判定/二次突破/回踩买点/质量分/观察优先级/离场规则) + 降级适配"""
import io, sys
sys.stdout.reconfigure(encoding='utf-8')
P = r'D:\QuantMonitorV6\tools\cloud_daily_review.py'
src = io.open(P, encoding='utf-8').read()
orig = src

def rep(old, new, tag):
    global src
    assert old in src, 'NOT FOUND: ' + tag
    assert src.count(old) == 1, 'AMBIG: ' + tag + ' count=%d' % src.count(old)
    src = src.replace(old, new, 1)
    print('[OK]', tag)

def rep_span(start, end, new, tag):
    """按起止锚点替换整段（含起止）。"""
    global src
    i = src.find(start); j = src.find(end)
    assert i >= 0, 'SPAN START NOT FOUND: ' + tag
    assert j > i, 'SPAN END NOT FOUND: ' + tag
    j = j + len(end)
    src = src[:i] + new + src[j:]
    print('[OK]', tag)

# ============ 1. ZSYS 替换为 V4（三引号，防内部单引号断裂） ============
V4_ZSYS = '''ZSYS = """你是主力建仓痕迹研判模型。输入是扫描器命中池和今日热点板块榜。你的任务：逐只识别建仓手法、匹配建仓模式、判断序列阶段、评估锚与洗盘质量、判断板块共振与主线归属、讲清底层逻辑、剔除确认假信号、排出最值得跟踪的观察名单。输出仅作概率研判和观察参考，不构成投资建议。
【一、输入数据与边界】
1. 只依据输入数据和产业链知识，不得虚构订单、客户、公告、业绩数字。
2. 字段缺失标"未取得/未知"，不得猜测填补。
3. 无公告/新闻/历史热点榜/板块涨停家数字段时，不得硬判"利空复牌""消息一日游""近期主线""强共振"，只能标"数据不足无法判定"并写证据缺口。
4. 允许用产业链知识补足 theme/resonance/theme_status/bottom_logic，须加"据模型知识："前缀；禁止编造具体订单、客户、供货关系、业绩数字。
5. 输出必须是完整 JSON 对象，形如 {"meta":{},"radar":[],"judged_all":[],"excluded":[]}；裸数组视为降级。
【二、红线】
1. 建仓痕迹是概率证据，不是买入信号。禁止"建仓完毕必涨""必拉""稳赚"类表述。
2. 当日涨幅>=7%或涨停的票一律不得进入 radar；若存在必须放入 excluded 并注明"涨幅红线"。
3. 禁止编造或引用绝对量能数字（手数/成交额/万元阈值）。量能只写相对倍数、近N日最低/最高、全池流动性分位。价格锚和止损价可写具体价格。
4. 观察条件只能用"价格锚+相对量能"，如"缩量回踩5日线不破"。禁止"成交额不低于XX万元""放量至XX万手"。
5. bottom_logic 每票必填；知识不足写"未取得+缺口"，禁止整字段缺失。
6. 无题材票不剔除，归"冷门池"：theme_status=冷门，ignite_theme 必写"当前无，若出现XX类消息即为催化剂"；主营不明时写"当前无；催化方向未取得（缺口：主营细分未明），若出现与主营相关的政策/价格/订单类消息再评估"。冷门池优先级降档。
7. 假信号不得硬判：确认假信号才出Top；疑似风险降credibility；数据不足无法判定则保留研判并写缺口。
8. next_watch 是"观察剧本/风险控制参考"，不是买入指令，禁止写"怎么买"；统一写"观察触发+失效条件"。
9. 质量评分→仓位换算仅作为"观察优先级参考"，不构成投资建议；输出 position_ref 时必须同时输出 observation_priority 和"非投资建议"标注。
【三、硬门槛与过滤】
A. 当日涨幅>=7%或涨停：excluded，原因"涨幅红线"。
B. 确认假信号：excluded，原因"确认假信号"。
C. 流动性枯竭：liquidity_flag=枯竭或 liquidity_percentile 全池后20%，excluded，原因"流动性枯竭"；无数据标"数据不足"，不硬剔。
D. 数据不足、冷门池、疑似风险：保留 judged_all，降credibility，不优先入radar。
【四、逐只研判·九问】
① 手法归类 + 四模式匹配
手法：横盘吸筹/打压吸筹/拉高吸筹/混合/证据不足。引用具体日期+价格锚+相对量能变化作证；复核 method_type/state，注明"扫描器给：××；复核：一致/不一致/部分一致"。禁止绝对量能。
四模式匹配（可多选或"不匹配"）：
- 模式一：跳空高开、3日不补缺口、缩量回踩5日线企稳 → 跳空高开确认型。
- 模式二：放量大阳后高位缩量小阳/十字星、5日线支撑 → 高位缩量整理型。
- 模式三：底部阳线放量、阴线缩量、横盘2-4周、5周内放量阳线 → 底部箱体蓄势型。
- 模式四：底部横盘震荡向上、阳线放量阴线缩量、周K放量 → 底部抬升型。
输出 pattern_match + pattern_basis。
② 突破日验收（三项全过）
- ①收盘站上锚1%以上（盘中刺穿不算）；
- ②量能>=前5日均量1.5倍（写相对倍数）；
- ③板块背景检查：点火日同板块涨2%家数>=3为合格，2只为一般，独苗为不合格。
输出 breakout_check：close_above_anchor_pct、volume_ratio（相对倍数）、sector_background、verdict（通过/部分通过/未通过/数据不足）。无数据项标"数据不足无法判定"。
③ 回抽洗盘判定 / 真伪鉴别
- 阴线缩量（量能低于点火量0.7倍）+红肥绿瘦=洗盘合格；
- 阴线量>=点火量或放量破点火开盘价=出货，拉黑3-5天；
- 红肥绿瘦但箱体持续下移=阴跌不是吸筹；
- 突破日为消息刺激一日游需news_today，无数据标"数据不足无法判定"；
- 死寂期利空停牌复牌需announcements_10d，无数据标"数据不足无法判定"；
- 缩量是否流动性枯竭需liquidity字段。
输出 washout_check：volume_shrink_ratio、red_fat_green_thin、verdict（洗盘合格/疑似出货/阴跌/数据不足无法判定），以及 false_alarm_status（未见异常/疑似风险/确认假信号/数据不足无法判定）。
④ 建仓成本区 + 锚质量
- 第0步找锚：涨幅>=4%+收阳+量能>=前5日均量1.5倍；锚必须是关键位——前高/箱体顶/曾套人的套牢区上沿；无名价位的大阳=低质量锚。
- 成本区：箱体中枢/坑底均价/近期密集成交区/锚±2%回踩区。
输出 anchor_price、anchor_type（关键位/无名位/未取得）、anchor_quality_score（关键位25/无名位10/未取得0）、cost_zone、cost_basis（写明计算口径）。
⑤ 板块题材共振
- 对照今日热点板块榜。
- 强共振：所属板块是今日主线且 sector_limit_up_count>=5；
- 中共振：所属板块有涨停但非主线；
- 弱共振：题材边缘或独立行情；
- 数据不足：无板块涨停家数或热点榜数据。
输出 resonance、resonance_basis、sector_rise2pct_count_on_ignition_day。
⑥ 主线归属
- 当前主线：所属板块在今日热点榜Top3且板块涨停>=3家；
- 近期主线：所属板块7个交易日内曾进热点榜前5；
- 冷门：都不属于。
无历史榜数据时依据今日榜和模型知识判断并标"据模型知识："；禁止整卡 theme_status 全部"未取得"。输出 theme_status + theme_status_basis。
⑦ 二次突破与序列阶段
- 二次突破：收盘重新站上锚=序列完成；温和放量（1-1.5倍）最佳；巨量（>2倍）分歧大降级；缩量二次突破=10分档。
- 序列阶段六选一：找锚中/突破已确认/回抽洗盘中/二次突破完成/回踩买点区/已破位出货。
输出 second_breakout（done、volume_type：温和/缩量/巨量/数据不足）、sequence_stage。
⑧ 回踩买点五条（仅当 sequence_stage=回踩买点区或二次突破完成时评估）
- ①回踩到锚±2%；
- ②只给两次机会（第1次标准档、第2次半档、第3次放弃）；
- ③形态=长下影/十字星/小阳（插而不破），大阴砸进锚下=放弃；
- ④当日缩量；
- ⑤站上5日线；
- 时间窗3-7天最有效，超10天只观察。
输出 pullback_check：five_conditions_met（逐条）、time_window、verdict（可观察/降档观察/放弃/未到）。
⑨ 底层逻辑 + 题材催化 + 离场规则
- bottom_logic 必填：主营业务、产业链身位、为什么主力可能选它、吸筹后催化。
- ignite_theme：吸筹结束后最可能被什么题材点燃；冷门池按红线6模板。
- 离场规则：止损=收盘破点火开盘价无条件走；止盈参考=锚+8%减半、+16%清仓（仅作观察剧本，非投资建议）。
输出 bottom_logic、ignite_theme、exit_rule。
【五、质量评分表 + 排序评分卡】
先算 quality_score（满分100）：
| 因子 | 分值 |
|---|---|
| 锚质量 | 关键位=25，无名位=10，未取得=0 |
| 板块共振（点火日同板块涨2%家数） | >=3只=25，2只=15，独苗=5，数据不足=0 |
| 利好新鲜度 | 点火前3天内有新公告/政策=20，旧消息=10，纯资金无消息=5，数据不足=0 |
| 洗盘质量 | 缩量+红肥绿瘦标准=15，基本合格=8，未到=0，出货=0 |
| 二次突破量型 | 温和放量=15，缩量=10，巨量=5，未到=0 |
输出 quality_score_detail + quality_total。
质量分→观察优先级参考（非投资建议）：
- >=80：observation_priority=高，position_ref=标准档参考（可加档）；
- 60-79：中，1成档参考（不加）；
- 40-59：低，三分之一档参考、严止损；
- <40：放弃，position_ref=不参与。
同时输出 observation_priority_note="仅作观察优先级参考，非投资建议"。
radar 排序步骤：
1. 硬门槛过滤：涨幅红线、确认假信号、流动性枯竭、quality_total<40 出Top。
2. 主线优先级：当前主线 > 近期主线 > 冷门。
3. 共振优先级：强 > 中 > 弱 > 数据不足。
4. quality_total 高者优先。
5. credibility：高 > 中 > 低。
6. 同档按 scan_score 全池分位排序。
输出 rank_score、rank_reason。radar最多5只，允许少于5只或空数组，不许硬凑。
credibility判定：
- 高：手法三要件齐全+锚质量关键位+洗盘合格+成本区可算+板块数据完整+未见假信号冲突；
- 中：手法可归类但缺1项证据，或板块/公告新闻数据不全，或疑似风险，或锚为无名位；
- 低：仅条件命中，成本区/题材/数据缺口明显，或数据不足无法判定。
输出 credibility_reason、evidence_gaps。
【六、输出JSON】
{
  "meta": {"scan_date":"","data_gaps":[],"disclaimer":"建仓痕迹为概率研判，不构成投资建议；position_ref仅为观察优先级参考"},
  "radar": [{
    "code":"","name":"",
    "pattern_match":"模式一/模式二/模式三/模式四/多模式/不匹配","pattern_basis":"",
    "method":"","method_review":"扫描器给：××；复核：一致/不一致/部分一致",
    "sequence_stage":"找锚中/突破已确认/回抽洗盘中/二次突破完成/回踩买点区/已破位出货",
    "anchor_price":"","anchor_type":"关键位/无名位/未取得","anchor_quality_score":0,
    "cost_zone":"","cost_basis":"",
    "breakout_check":{"close_above_anchor_pct":"","volume_ratio":"","sector_background":"","verdict":"通过/部分通过/未通过/数据不足"},
    "washout_check":{"volume_shrink_ratio":"","red_fat_green_thin":"","verdict":"洗盘合格/疑似出货/阴跌/数据不足无法判定"},
    "second_breakout":{"done":false,"volume_type":"温和/缩量/巨量/数据不足"},
    "pullback_check":{"five_conditions_met":[],"time_window":"","verdict":"可观察/降档观察/放弃/未到"},
    "quality_score_detail":{"anchor":0,"sector_resonance":0,"news_freshness":0,"washout":0,"second_breakout":0},
    "quality_total":0,
    "observation_priority":"高/中/低/放弃",
    "position_ref":"标准档参考/1成档参考/三分之一档参考/不参与",
    "observation_priority_note":"仅作观察优先级参考，非投资建议",
    "credibility":"高/中/低","credibility_reason":"","evidence_gaps":[],
    "theme":"","resonance":"强/中/弱/数据不足","resonance_basis":"",
    "sector_rise2pct_count_on_ignition_day":0,
    "theme_status":"当前主线/近期主线/冷门","theme_status_basis":"",
    "bottom_logic":"","ignite_theme":"",
    "exit_rule":"止损=收盘破点火开盘价；止盈参考=锚+8%减半/+16%清仓（观察剧本，非投资建议）",
    "next_watch":"①一句话底层逻辑/题材身位；②观察触发：价格锚+相对量能条件+回踩买点五条匹配情况；③失效条件：跌破X元或放量破箱体则移出观察池",
    "false_alarm_status":"未见异常/疑似风险/确认假信号/数据不足无法判定",
    "false_alarm_risk":"",
    "rank_score":0,"rank_reason":"","scan_score":0
  }],
  "judged_all": [{
    "code":"","name":"","pattern_match":"","method":"","sequence_stage":"",
    "anchor_type":"","cost_zone":"","quality_total":0,"observation_priority":"",
    "credibility":"高/中/低","theme":"","resonance":"强/中/弱/数据不足","theme_status":"当前主线/近期主线/冷门",
    "false_alarm_status":"","evidence_gaps":[],"bottom_logic":"","ignite_theme":"","brief":"一句话研判"
  }],
  "excluded": [{"code":"","name":"","exclude_reason":"涨幅红线/确认假信号/流动性枯竭/质量分<40"}]
}
注意：
- radar最多5只，按硬门槛→主线→共振→quality_total→credibility→scan_score排序。
- judged_all 覆盖全池，冷门池和数据不足票必须保留。
- excluded 只放硬剔除票。
- 全池证据不足时 radar 输出空数组，但 meta 和 judged_all 要说明缺口，不许硬凑。"""'''

rep_span("ZSYS = '你是主力建仓痕迹研判模型。", "全池证据不足时输出空数组，不许硬凑。'", V4_ZSYS, 'zsys_v4')

# ============ 2. _by_sec 初始化外提（涨停池未取到时兜底） ============
rep("""    hot_board, res_bonus = [], {}
    _c2sec = {}""",
    """    hot_board, res_bonus, _by_sec = [], {}, defaultdict(list)
    _c2sec = {}""",
    'by_sec_init')

# ============ 3. 输入 payload 适配 V4 schema ============
rep("""    # —— LLM 研判（每天 1 次批量）——
    brief = '\\n'.join(
        '- %s(%s) 现价%s 评分%s(+板块共振%s) 所属板块:%s 命中条件%s 手法:%s 扫描器分类:%s(%s) 箱体%s-%s 锚%s 证伪%s 换手%s%% 下一信号:%s 近12日K线:%s' % (
            h['name'], h['code'], h['price'], h['score_w'], h['res_bonus'],
            _c2sec.get(str(h['code'])) or h.get('industry') or '未取得',
            h['hit_conditions'], h['method'],
            h.get('method_type') or '未分类', h.get('state') or '',
            h['box_low'], h['box_high'], h['anchor'], h['falsify_line'],
            h.get('avg_turn') or '未取得',
            h.get('next_watch') or '未取得',
            ' '.join('%s:%s%%/%s万股' % (k['d'], k['pct'], k['vol_wan']) for k in h['kline_brief'])) for h in hits[:30])
    hot_txt = '；'.join('%s(%s家涨停)' % (b['sec'], b['cnt']) for b in hot_board) or '未取得'
    payload = {'task': 'zforce_radar', 'scan_date': trade_date,
               'hits_count': len(hits), 'hits_brief': brief,
               'hot_themes': hot_txt,
               'format': '按系统提示词六问逐只研判命中池，判断板块题材共振与底层逻辑，剔除假信号，输出 radar JSON（最多5只）。'}""",
    """    # —— LLM 研判（V4 输入 schema：pool 数组 + hot_sectors + 历史榜空数组）——
    brief = '\\n'.join(
        '- %s(%s) 现价%s 评分%s(+板块共振%s) 所属板块:%s 命中条件%s 手法:%s 扫描器分类:%s(%s) 箱体%s-%s 锚%s 证伪%s 换手%s%% 下一信号:%s 近12日K线:%s' % (
            h['name'], h['code'], h['price'], h['score_w'], h['res_bonus'],
            _c2sec.get(str(h['code'])) or h.get('industry') or '未取得',
            h['hit_conditions'], h['method'],
            h.get('method_type') or '未分类', h.get('state') or '',
            h['box_low'], h['box_high'], h['anchor'], h['falsify_line'],
            h.get('avg_turn') or '未取得',
            h.get('next_watch') or '未取得',
            ' '.join('%s:%s%%/%s万股' % (k['d'], k['pct'], k['vol_wan']) for k in h['kline_brief'])) for h in hits[:30])
    hot_txt = '；'.join('%s(%s家涨停)' % (b['sec'], b['cnt']) for b in hot_board) or '未取得'
    _pool_in = []
    for h in hits[:30]:
        _kb = h.get('kline_brief') or []
        _last = _kb[-1] if _kb else {}
        _sc = _c2sec.get(str(h['code'])) or h.get('industry') or '未取得'
        _pool_in.append({
            'code': h['code'], 'name': h['name'], 'close': float(h.get('price') or 0),
            'pct_chg': float(_last.get('pct') or 0), 'limit_up': False,
            'kline_summary': '近12日K线: %s' % (' '.join('%s:%s%%/%s万股' % (k['d'], k['pct'], k['vol_wan']) for k in _kb) or '未取得'),
            'condition_hits': h['hit_conditions'], 'scan_score': int(h.get('score_w') or h.get('score') or 0),
            'method_type': h.get('method_type') or '未分类', 'state': h.get('state') or '',
            'sector': _sc,
            'sector_limit_up_count': int(_by_sec.get(_sc, 0)) if _c2sec else 0,
            'sector_rise2pct_count_on_ignition_day': None,   # 数据源未接入：LLM 按红线3标数据不足
            'announcements_10d': [], 'news_today': [],
            'liquidity_flag': '未知', 'liquidity_percentile': None,
        })
    _hot_sectors_in = [{'sector': b['sec'], 'rank': i + 1, 'limit_up_count': b['cnt']} for i, b in enumerate(hot_board)]
    payload = {'task': 'zforce_radar', 'scan_date': trade_date,
               'hits_count': len(hits), 'hits_brief': brief,
               'hot_themes': hot_txt,
               'hot_sectors': _hot_sectors_in,
               'hot_sector_history_7d': [],   # 历史热点榜数据源未接入：LLM 按红线3标数据不足，不硬判
               'pool': _pool_in,
               'format': '按系统提示词逐只九问研判命中池，输出 meta/radar/judged_all/excluded 完整 JSON 对象（radar 最多5只）。'}""",
    'payload_v4')

# ============ 4. 解析段：meta/judged_all/excluded ============
rep("""    t = ask_deepseek(payload, purpose='zforce_radar', system_text='ZSYS')
    radar = []
    _hmap = {h['code']: h for h in hits}""",
    """    t = ask_deepseek(payload, purpose='zforce_radar', system_text=ZSYS)
    radar, _judged_all, _excluded, _meta = [], [], [], {}
    _hmap = {h['code']: h for h in hits}""",
    'out_init')

rep("""                radar = [x for x in raw if isinstance(x, dict) and (x.get('code') or x.get('stock_code') or x.get('symbol'))]
                # 通用兜底：递归两层找含 code/stock_code 的数组（LLM 结构多变，兜底不降级）""",
    """                radar = [x for x in raw if isinstance(x, dict) and (x.get('code') or x.get('stock_code') or x.get('symbol'))]
                _judged_all = [x for x in (_j.get('judged_all') or []) if isinstance(x, dict)] if isinstance(_j.get('judged_all'), list) else []
                _excluded = [x for x in (_j.get('excluded') or []) if isinstance(x, dict)] if isinstance(_j.get('excluded'), list) else []
                _meta = _j.get('meta') if isinstance(_j.get('meta'), dict) else {}
                # 通用兜底：递归两层找含 code/stock_code 的数组（LLM 结构多变，兜底不降级）""",
    'out_extract')

# ============ 5. 字段映射：V4 全字段兜底 ============
rep("""                _fr = r.get('false_alarm_risk') or r.get('risk') or r.get('risk_point')
                if not _fr and (r.get('stop_loss') or r.get('stop_loss_level') or r.get('falsification_point') or dt.get('falsify_price')):
                    _fr = ('止损' + str(r.get('stop_loss') or r.get('stop_loss_level') or dt.get('falsify_price'))) + \\
                          ('；证伪' + str(r.get('falsification_point') or dt.get('falsify_price')))
                r.setdefault('false_alarm_risk', _fr)""",
    """                _fr = r.get('false_alarm_risk') or r.get('risk') or r.get('risk_point')
                if not _fr and (r.get('stop_loss') or r.get('stop_loss_level') or r.get('falsification_point') or dt.get('falsify_price')):
                    _fr = ('止损' + str(r.get('stop_loss') or r.get('stop_loss_level') or dt.get('falsify_price'))) + \\
                          ('；证伪' + str(r.get('falsification_point') or dt.get('falsify_price')))
                r.setdefault('false_alarm_risk', _fr)
                # V4 字段兜底映射（LLM 输出 V4 规范字段，缺失时从旧字段/命中池兜底）
                for _k, _alts in (('pattern_match', ('pattern_match', 'pattern', 'mode_match')),
                                  ('pattern_basis', ('pattern_basis',)),
                                  ('sequence_stage', ('sequence_stage', 'stage_phase', 'stage')),
                                  ('anchor_price', ('anchor_price',)),
                                  ('anchor_type', ('anchor_type',)),
                                  ('anchor_quality_score', ('anchor_quality_score',)),
                                  ('cost_basis', ('cost_basis',)),
                                  ('quality_total', ('quality_total', 'total_score', 'quality_score')),
                                  ('observation_priority', ('observation_priority',)),
                                  ('position_ref', ('position_ref',)),
                                  ('exit_rule', ('exit_rule', 'exit_rule_plan')),
                                  ('method_review', ('method_review',)),
                                  ('false_alarm_status', ('false_alarm_status',)),
                                  ('rank_score', ('rank_score',)),
                                  ('rank_reason', ('rank_reason',)),
                                  ('scan_score', ('scan_score',)),
                                  ('resonance_basis', ('resonance_basis',)),
                                  ('theme_status_basis', ('theme_status_basis',))):
                    if r.get(_k) is None:
                        for _a in _alts:
                            if r.get(_a) is not None:
                                r[_k] = r[_a]
                                break
                for _k in ('breakout_check', 'washout_check', 'second_breakout', 'pullback_check', 'quality_score_detail'):
                    if r.get(_k) is None:
                        r[_k] = {}
                if not r.get('sequence_stage'):
                    r['sequence_stage'] = '找锚中'
                if r.get('quality_total') is None:
                    r['quality_total'] = int(hh.get('score_w') or hh.get('score') or 0)
                _eg = r.get('evidence_gaps')
                if isinstance(_eg, list):
                    r['evidence_gaps'] = '；'.join(str(x) for x in _eg) if _eg else '无'""",
    'v4_field_map')

# ============ 6. 降级分支适配 V4 ============
rep("""    if not radar:
        radar = []
        for h in hits[:5]:
            _rb = h.get('res_bonus', 0)
            radar.append({'code': h['code'], 'name': h['name'], 'method': h['method'],
                          'cost_zone': str(h['anchor']), 'credibility': '中(规则降级)',
                          'theme': h.get('industry') or '未判',
                          'resonance': ('强' if _rb >= 15 else '中' if _rb >= 5 else '弱' if _rb else '未判'),
                          'bottom_logic': ('客观数据：现价' + str(h.get('price') or '') + '元，箱体'
                                           + str(h.get('box_low') or '') + '-' + str(h.get('box_high') or '')
                                           + '，评分' + str(h.get('score_w') or h.get('score') or '')
                                           + '，换手' + str(h.get('avg_turn') or '未取得')
                                           + '%。主营与产业链信息不在输入内，待LLM研判恢复。'),
                          'ignite_theme': h['industry'],
                          'next_watch': '放量突破' + str(h['box_high']) + '=建仓完成确认',
                          'false_alarm_risk': '缺模型研判'})""",
    """    if not radar:
        radar = []
        for h in hits[:5]:
            _rb = h.get('res_bonus', 0)
            _qt = int(h.get('score_w') or h.get('score') or 0)
            radar.append({'code': h['code'], 'name': h['name'], 'method': h['method'],
                          'pattern_match': '不匹配', 'pattern_basis': 'LLM未输出，规则降级',
                          'sequence_stage': '找锚中',
                          'anchor_price': str(h.get('anchor') or ''), 'anchor_type': '未取得', 'anchor_quality_score': 0,
                          'cost_zone': str(h['anchor']), 'cost_basis': '规则降级：箱体' + str(h.get('box_low') or '') + '-' + str(h.get('box_high') or ''),
                          'breakout_check': {'verdict': '数据不足'}, 'washout_check': {'verdict': '数据不足无法判定'},
                          'second_breakout': {'done': False, 'volume_type': '数据不足'},
                          'pullback_check': {'five_conditions_met': [], 'time_window': '', 'verdict': '未到'},
                          'quality_score_detail': {'anchor': 0, 'sector_resonance': _rb, 'news_freshness': 0, 'washout': 0, 'second_breakout': 0},
                          'quality_total': _qt,
                          'observation_priority': '低', 'position_ref': '三分之一档参考（规则降级）', 'observation_priority_note': '仅作观察优先级参考，非投资建议',
                          'credibility': '中(规则降级)',
                          'theme': h.get('industry') or '未判',
                          'resonance': ('强' if _rb >= 15 else '中' if _rb >= 5 else '弱' if _rb else '未判'),
                          'bottom_logic': ('客观数据：现价' + str(h.get('price') or '') + '元，箱体'
                                           + str(h.get('box_low') or '') + '-' + str(h.get('box_high') or '')
                                           + '，评分' + str(h.get('score_w') or h.get('score') or '')
                                           + '，换手' + str(h.get('avg_turn') or '未取得')
                                           + '%。主营与产业链信息不在输入内，待LLM研判恢复。'),
                          'ignite_theme': h['industry'],
                          'exit_rule': '止损=收盘破' + str(h.get('falsify_line') or h.get('box_low') or '') + '元；止盈参考=锚+' + str(h.get('anchor') or '') + '元+8%（观察剧本，非投资建议）',
                          'next_watch': '①' + str(h.get('method') or '建仓痕迹') + '；②观察触发：放量突破' + str(h.get('box_high') or '') + '；③失效：跌破' + str(h.get('falsify_line') or '') + '元移出观察池',
                          'false_alarm_status': '数据不足无法判定', 'false_alarm_risk': '缺模型研判',
                          'rank_score': _qt, 'rank_reason': '规则降级按评分排', 'scan_score': int(h.get('score') or 0)})""",
    'fallback_v4')

# ============ 7. 渲染段：V4 新版式 ============
rep_span("""    # —— 渲染：主力雷达卡 ——
    lines = ['<div style="font-size:15px;font-weight:900;color:' + GOLD + ';">🛰 主力雷达 · 建仓痕迹（' + str(len(hits)) + ' 只扫描命中，Top' + str(len(radar)) + '）</div>',""",
    """    lines.append('<div style="margin-top:8px;font-size:11px;color:' + GREY + ';">⚠️ 建仓痕迹是概率证据非买入信号；主力雷达票已入火点观察池，等放量点火信号。</div>')
    return ''.join(lines)""",
    """    # —— 渲染：主力雷达卡（V4 版式） ——
    lines = ['<div style="font-size:15px;font-weight:900;color:' + GOLD + ';">🛰 主力雷达 · 建仓痕迹（' + str(len(hits)) + ' 只扫描命中，Top' + str(len(radar)) + '）</div>',
             '<div style="margin-top:2px;font-size:12px;color:' + GREY + ';">数据日 ' + trade_date + '：六条件扫描 → 板块共振加权 → 模型九问研判（建仓手法/四模式/序列阶段/锚与洗盘质量/底层逻辑）</div>',
             '<div style="margin-top:4px;font-size:12px;color:' + RED + ';">🔥 今日热点板块（涨停家数）：' + (('；'.join('%s(%s家)' % (b['sec'], b['cnt']) for b in hot_board)) if hot_board else '未取得') + '</div>']
    def _strip_abs_vol(t):
        \"\"\"量能红线渲染终拦：剔除 LLM 输出的绝对量能数字（万手/万股/万元/亿），保留相对表述与价格锚。\"\"\"
        if not t:
            return t
        t = str(t)
        t = re.sub(r'成交金额超?\\s*\\d+(?:\\.\\d+)?\\s*万元', '大单放量确认', t)
        t = re.sub(r'成交量\\s*\\d+(?:\\.\\d+)?\\s*万股?', '成交量放量', t)
        t = re.sub(r'\\d+(?:\\.\\d+)?\\s*(?:万手|万股|万元|亿元|亿股|手)', '', t)
        t = re.sub(r'\\s{2,}', ' ', t).strip(' ，。、；')
        return t
    def _bc(r, k, d=''):
        v = r.get(k) or {}
        return str(v.get(d) or '') if isinstance(v, dict) else ''
    def _pr(r, k):
        v = r.get(k) or {}
        return v.get('verdict') if isinstance(v, dict) and v.get('verdict') else '数据不足'

    for r in radar[:5]:
        for _k in ('method', 'cost_zone', 'bottom_logic', 'ignite_theme', 'next_watch', 'false_alarm_risk',
                   'theme', 'reason', 'condition', 'risk', 'observation_logic', 'trigger_condition',
                   'data_trace', 'logic', 'why', 'pattern_basis', 'exit_rule', 'method_review',
                   'resonance_basis', 'theme_status_basis', 'cost_basis', 'rank_reason'):
            if r.get(_k):
                r[_k] = _strip_abs_vol(r[_k])
        c = r.get('code') or r.get('stock_code') or ''
        nm = r.get('name') or r.get('stock_name') or ''
        cred = str(r.get('credibility') or '中')
        hh2 = _hmap.get(c) or {}
        cred_c = '#52c41a' if cred.startswith('高') else '#ffd43b' if cred.startswith('中') else '#ff6b6b'
        _dvg = _divergence_label(hh2, str(r.get('theme') or ''), _sec_map, hot_board)
        _qt = r.get('quality_total') or 0
        _prk = str(r.get('observation_priority') or ('高' if _qt >= 80 else '中' if _qt >= 60 else '低' if _qt >= 40 else '放弃'))
        _prc = '#52c41a' if _prk.startswith('高') else '#ffd43b' if _prk.startswith('中') else '#ff922b' if _prk.startswith('低') else '#ff6b6b'
        _pri = ('观察优先级：' + _prk + '（质量分 ' + str(_qt) + '）｜参考仓位：' + str(r.get('position_ref') or '未取得')) if (_qt is not None) else ('观察优先级：' + _prk)
        _bchk = _pr(r, 'breakout_check')
        _wchk = _pr(r, 'washout_check')
        _bchk_txt = ('收盘站上锚' + _bc(r, 'breakout_check', 'close_above_anchor_pct') + '%｜量能' + _bc(r, 'breakout_check', 'volume_ratio') + '倍｜板块' + _bc(r, 'breakout_check', 'sector_background')) if _bchk != '数据不足' else '突破数据不足'
        _wchk_txt = ('缩量' + _bc(r, 'washout_check', 'volume_shrink_ratio') + '倍｜红肥绿瘦' + _bc(r, 'washout_check', 'red_fat_green_thin')) if _wchk not in ('数据不足无法判定', '') else '洗盘数据不足'
        _sb = r.get('second_breakout') or {}
        _sb_txt = ('已二次突破·' + str(_sb.get('volume_type') or '数据不足')) if (_sb.get('done') if isinstance(_sb, dict) else False) else '未二次突破'
        _pb = r.get('pullback_check') or {}
        _pb_n = len(_pb.get('five_conditions_met') or []) if isinstance(_pb, dict) else 0
        _pb_txt = ('回踩五条满足 %d/%d｜时间窗 %s' % (_pb_n, 5, str(_pb.get('time_window') or '未到'))) if (_pb.get('verdict') if isinstance(_pb, dict) else '') not in ('未到', '', None) else '回踩未到（' + str(_pb.get('verdict') or '未到') + '）'
        lines.append(
            '<div style="margin-top:10px;padding:10px;background:#1c2230;border-left:4px solid ' + GOLD + ';border-radius:8px;">'
            '<div style="font-size:14px;color:#fff;font-weight:700;">' + nm + '（' + c + '）'
            '<span style="margin-left:8px;font-size:11px;color:' + cred_c + ';">可信度' + cred + '</span>'
            '<span style="margin-left:8px;font-size:11px;color:' + _prc + ';">' + _prk + '</span></div>'
            '<div style="font-size:12px;color:' + TEAL + ';margin-top:4px;">建仓手法：' + str(r.get('method') or '') + ('（' + str(hh2.get('method_type') or '') + '·' + str(hh2.get('state') or '') + '）' if hh2.get('method_type') else '') + ('　复核：' + str(r.get('method_review') or '') if r.get('method_review') else '') + '</div>'
            '<div style="font-size:12px;color:#66d9e8;margin-top:2px;">模式匹配：' + str(r.get('pattern_match') or '不匹配') + ('｜' + str(r.get('pattern_basis') or '') if r.get('pattern_basis') else '') + '　序列阶段：' + str(r.get('sequence_stage') or '找锚中') + '</div>'
            '<div style="font-size:12px;color:' + GOLD + ';margin-top:2px;">锚：' + str(r.get('anchor_price') or '') + '（' + str(r.get('anchor_type') or '未取得') + '，质量' + str(r.get('anchor_quality_score') or 0) + '分）｜成本区：' + str(r.get('cost_zone') or '') + ('（' + str(r.get('cost_basis') or '') + '）' if r.get('cost_basis') else '') + '</div>'
            '<div style="font-size:12px;color:#e9ecef;margin-top:2px;">突破验收：' + _bchk + '（' + _bchk_txt + '）｜洗盘判定：' + _wchk + '（' + _wchk_txt + '）</div>'
            '<div style="font-size:12px;color:#e9ecef;margin-top:2px;">二次突破：' + _sb_txt + '　' + _pb_txt + '</div>'
            '<div style="font-size:12px;color:#ff6b6b;margin-top:2px;">板块共振：' + str(r.get('theme') or '未判') + '｜强度' + str(r.get('resonance') or '未判') + ('（板块共振+' + str(hh2.get('res_bonus') or 0) + '分）' if hh2.get('res_bonus') else '') + ('　主线：' + ('🔥当前主线' if str(r.get('theme_status') or '').startswith('当前') else '📅近期主线' if str(r.get('theme_status') or '').startswith('近期') else '❄️冷门·仓位减半' if str(r.get('theme_status') or '').startswith('冷门') else str(r.get('theme_status') or ''))) + '</div>'
            '<div style="font-size:12px;color:' + RED + ';margin-top:2px;">底层逻辑：' + str(r.get('bottom_logic') or '未取得') + '</div>'
            '<div style="font-size:12px;color:#e9ecef;margin-top:2px;">👉 观察剧本：' + str(r.get('next_watch') or '') + '</div>'
            '<div style="font-size:12px;color:' + TEAL + ';margin-top:2px;">离场规则：' + str(r.get('exit_rule') or '') + '</div>'
            '<div style="font-size:11px;color:' + GREY + ';margin-top:2px;">' + _pri + '｜假信号：' + str(r.get('false_alarm_status') or '数据不足无法判定') + '｜' + str(r.get('false_alarm_risk') or '') + '｜点火题材预判：' + str(r.get('ignite_theme') or '') + '</div>'
            + ('<div style="font-size:12px;color:#66d9e8;margin-top:2px;">' + _dvg + '</div>' if _dvg else '') + '</div>')
    if _excluded:
        lines.append('<div style="margin-top:8px;font-size:11px;color:#ff6b6b;">🗑 硬剔除：' + '；'.join('%s(%s) %s' % (x.get('name') or '', x.get('code') or '', x.get('exclude_reason') or '') for x in _excluded[:6]) + '</div>')
    if _judged_all:
        lines.append('<div style="margin-top:4px;font-size:11px;color:' + GREY + ';">📋 全池研判 ' + str(len(_judged_all)) + ' 只（含冷门池/数据不足保留，不优先入榜）</div>')
    lines.append('<div style="margin-top:8px;font-size:11px;color:' + GREY + ';">⚠️ 建仓痕迹是概率证据非买入信号；position_ref 仅为观察优先级参考，不构成投资建议；主力雷达票已入火点观察池，等放量点火信号。</div>')
    return ''.join(lines)""",
    'render_v4')

io.open(P, 'w', encoding='utf-8', newline='').write(src)
print('patched, delta=%d' % (len(src) - len(orig)))
