# -*- coding: utf-8 -*-
"""
V6 量化投研简报生成器（新规范6模块输出）
================================================================
⚡ 一句话核心提炼 / 🧠 深度逻辑拆解 / 📈 机会挖掘红榜 / 📉 风险预警黑榜 /
🌡️ 交易环境共振 / 🏷️ 量化标签JSON

底层复用 ui.battle_console_v2 的 _deep_* 分类传导链引擎（6类新闻分类+产业链传导），
在其之上重组为"可交易投研简报"：明确区分机会与风险、标注证据等级、
给出传导链条、催化节点、板块阶段与操作原则。

核心原则：
- 拒绝废话：观点鲜明，逻辑带传导链条，不用"可能/或许/值得关注"搪塞
- 事实分级：A公告/合同，B董秘回复/互动易，C媒体/产业链，D市场传闻
- 交易视角：落脚到对股价/板块的潜在影响与交易应对思路（不直接给买卖点位）
- 诚实边界：信息不足时明确标注[待验证]/[市场传闻]，绝不编造合作关系
"""
import re
import json

# 分类名（与 battle_console_v2._deep_classify_news 的分类保持一致）
_V6_CATEGORY_NAMES = {
    '期货指数异动': '指数/期指异动',
    '大宗商品': '大宗商品价格',
    '宏观数据': '宏观数据',
    '国际政治': '国际政治/外围事件',
    '个股公告': '公司公告',
    '行业政策': '行业政策/产业动态',
}

# 事件定性（规范允许值：情绪博弈/基本面反转/政策落地/技术突破/突发黑天鹅/旧闻翻炒/宏观映射）
_V6_EVENT_TYPE = {
    '期货指数异动': '情绪博弈',
    '大宗商品': '基本面反转',
    '宏观数据': '宏观映射',
    '国际政治': '突发黑天鹅',
    '个股公告': '基本面反转',
    '行业政策': '政策落地',
}

# category -> (时效标签, impact_duration)
_V6_DURATION = {
    '期货指数异动': ('短线脉冲', 'short_term'),
    '大宗商品': ('中线趋势', 'mid_term'),
    '宏观数据': ('短线脉冲', 'short_term'),
    '国际政治': ('短线脉冲', 'short_term'),
    '个股公告': ('中线趋势', 'mid_term'),
    '行业政策': ('中线趋势', 'mid_term'),
}

# 下一关键催化节点（必须具体，不含"等"）
_V6_CATALYST = {
    '期货指数异动': '现货指数是否同步跟跌/跟涨（期现联动确认）、两市涨跌停家数与成交额变化',
    '大宗商品': '商品主力合约价格走势、交易所/社会库存数据、OPEC等供给侧事件（如有）',
    '宏观数据': '央行/部委政策表态（降准降息窗口）、下月同类数据公布',
    '国际政治': '政策落地原文、事件进展（谈判/会议）、北向资金实际流向',
    '个股公告': '事项进展公告、监管问询/审批结果、下一期业绩验证',
    '行业政策': '地方配套细则与资金到位、龙头公司订单/业绩验证、行业高频数据',
}

# 板块阶段：token -> 展示名
_V6_STAGE_DISPLAY = {'高潮': '高潮期', '预热': '预热期', '低位': '低位蓄势', '退潮': '退潮期'}

# 板块关键词映射（与行业政策传导引擎同源）
_V6_SECTOR_KEYWORDS = {
    '半导体': '电子', '芯片': '电子', '集成电路': '电子', '消费电子': '电子', '苹果': '电子',
    '人工智能': '计算机', 'AI': '计算机', '大模型': '计算机', '算力': '计算机', '数据中心': '计算机',
    '新能源': '电力设备', '光伏': '电力设备', '风电': '电力设备', '储能': '电力设备', '锂电池': '电力设备',
    '新能源车': '汽车', '电动车': '汽车', '比亚迪': '汽车',
    '医药': '医药生物', '创新药': '医药生物', '医疗器械': '医药生物', '医疗': '医药生物',
    '白酒': '食品饮料', '消费': '食品饮料',
    '房地产': '房地产', '楼市': '房地产',
    '军工': '国防军工', '国防': '国防军工',
    '银行': '银行', '券商': '非银金融', '保险': '非银金融',
    '机器人': '机械设备', '工业母机': '机械设备',
    '煤炭': '煤炭', '石油': '石油石化', '原油': '石油石化',
    '黄金': '有色金属', '铜': '有色金属', '稀土': '有色金属',
    '5G': '通信', '光模块': '通信', '华为': '通信',
    '游戏': '传媒', '影视': '传媒',
    '农业': '农林牧渔', '猪肉': '农林牧渔',
    '家电': '家用电器',
    '纺织': '纺织服饰', '服装': '纺织服饰',
    '航运': '交通运输', '物流': '交通运输',
    '环保': '公用事业', '核电': '公用事业',
}

_RUMOR_WORDS = ['传闻', '网传', '据称', '知情人士', '市场传言']
_BLACK_SWAN_WORDS = ['战争', '冲突', '袭击', '制裁', '军事', '熔断', '暴涨暴跌']


def _bc():
    """懒加载 battle_console_v2（避免循环导入）"""
    from ui import battle_console_v2 as _m
    return _m


def _v6_strip_html(s):
    """去掉HTML标签得到纯文本"""
    if not s:
        return ''
    return re.sub(r'<[^>]+>', '', str(s)).strip()


def _v6_clean_chain(core_logic, wencai_voice=''):
    """把4段式核心逻辑清洗成纯传导链：去掉'事件：xxx。'前缀与'问财解读：'尾巴"""
    s = str(core_logic or '')
    m = re.match(r'^事件：[^。]*。', s)
    if m:
        s = s[m.end():]
    idx = s.find('问财解读：')
    if idx != -1:
        s = s[:idx]
    s = _v6_strip_html(s).strip()
    if wencai_voice:
        voice = _v6_strip_html(wencai_voice)
        if voice:
            s = (s.rstrip('。；') + '。问财交叉验证：' + voice[:100]) if s else ('问财交叉验证：' + voice[:100])
    return s


def _v6_core_pick(category, sentiment, text, d):
    """⚡ 一句话核心提炼（≤30字）"""
    if any(k in text for k in _RUMOR_WORDS):
        return '市场传闻发酵，情绪脉冲为主，谨防证伪回落。'
    if category == '期货指数异动':
        if d == 'down':
            return '期指急跌，风险偏好骤降，中小盘风格承压。'
        if d == 'up':
            return '期指急涨，风险偏好回升，风格beta行情启动。'
        return '期指异动，期现联动待确认，风格切换信号。'
    if category == '大宗商品':
        if d == 'up':
            return '商品大涨，上游盈利弹性释放，成本传导下游。'
        if d == 'down':
            return '商品大跌，上游承压减值，中下游成本红利。'
        return '商品价格异动，产业链利润再分配窗口打开。'
    if category == '宏观数据':
        return '宏观数据公布，政策预期与风格轮动迎来新锚。'
    if category == '国际政治':
        return '外围事件冲击，情绪面主导，A股映射待验证。'
    if category == '个股公告':
        if sentiment == '利好':
            return '公告利好落地，确定性增强，关注兑现节奏。'
        if sentiment == '利空':
            return '公告利空落地，筹码与预期承压，规避弱逻辑。'
        return '公告事项落地，中性偏观察，等待后续进展。'
    # 行业政策（默认）
    if sentiment == '利好':
        return '政策定调明确，产业趋势提速，板块预期上修。'
    if sentiment == '利空':
        return '政策/行业利空落地，板块承压，规避弱逻辑标的。'
    return '行业动态落地，产业趋势明确，催化节点需跟踪。'


def _v6_event_type(category, text):
    """事件定性"""
    if any(k in text for k in _RUMOR_WORDS):
        return '市场传闻/存疑待证'
    return _V6_EVENT_TYPE.get(category, '基本面反转')


def _v6_gap(category, sentiment, text, stage, avg_cp):
    """预期差分析：市场是否已定价 + 超预期/符合/低于 + 板块位置"""
    stage_txt = {
        '高潮': '相关板块已连续大涨，消息大概率已提前定价，警惕利好出尽',
        '预热': '相关板块已预热，消息部分反映，预期差取决于细则与兑现力度',
        '低位': '相关板块处于低位蓄势阶段，消息未充分反映，预期差空间较大',
        '退潮': '相关板块已退潮/承压，情绪面偏弱，消息难以独立驱动反转',
    }.get(stage, '相关板块位置中性，消息定价程度取决于后续验证')
    if category == '期货指数异动':
        return f'期指端往往领先现货，市场对风格的定价正在边际切换；当前{stage_txt}。需以现货量能与期现联动确认方向，避免把期货脉冲当趋势。'
    if category == '大宗商品':
        return f'商品价格由供需、库存、美元与地缘多因素叠加，市场习惯先炒预期后验业绩；当前{stage_txt}。涨价持续性需库存去化与开工率验证，情绪定价占比高。'
    if category == '宏观数据':
        return f'宏观数据对A股多为预期交易，公布前资金往往已提前布局；当前{stage_txt}。若数据超预期但指数不涨，说明已price in，警惕利好出尽反向波动。'
    if category == '国际政治':
        return f'外围事件对A股多为情绪面映射，市场先按最差/最好情景抢跑；当前{stage_txt}。真实影响需北向资金与汇率验证，表态与落地文本之间的预期差是核心交易点。'
    if category == '个股公告':
        if sentiment == '利空':
            return f'利空公告市场反应通常一次到位，但若为减持/质押类分批执行则压制持续；当前{stage_txt}。需区分被动与主动减持，警惕连锁抛压。'
        return f'公告利好若公布前股价已上涨，则大概率已部分定价；当前{stage_txt}。重点看金额占比、收入确认节奏与后续进展，防高开低走。'
    # 行业政策（默认）
    if sentiment == '利好':
        return f'政策类消息市场惯于"先炒预期、再验业绩"；当前{stage_txt}。顶层文件到细则、资金到位存在时滞，若力度低于预期则题材回落。'
    if sentiment == '利空':
        return f'监管/行业利空短期冲击情绪，但市场对龙头集中度提升的长期逻辑仍有分歧；当前{stage_txt}。口头表态与实际处罚力度差异大，超预期从严则杀估值。'
    return f'行业动态对板块的影响需要订单/价格/开工率等高频数据验证；当前{stage_txt}。'


def _v6_catalyst(category):
    """时效与催化：返回 (时效定位+催化节点 文本, impact_duration)"""
    dur_label, duration = _V6_DURATION.get(category, ('短线脉冲', 'short_term'))
    node = _V6_CATALYST.get(category, '后续官方/公司公告与行业高频数据')
    return f'时效定位：{dur_label}；下一关键催化节点：{node}。', duration


def _v6_sector_stage(matched_sectors, sector_map):
    """板块阶段：高潮/预热/低位/退潮（按关联板块实际均涨幅粗判）"""
    if not matched_sectors:
        return '低位', 0.0
    cps = []
    for sname in matched_sectors:
        sec = sector_map.get(sname, {})
        try:
            cp = float(sec.get('change_pct', 0) or 0)
        except Exception:
            cp = 0.0
        cps.append(cp)
    avg = sum(cps) / len(cps) if cps else 0.0
    if avg >= 2.0:
        return '高潮', avg
    if avg >= 0.5:
        return '预热', avg
    if avg > -0.5:
        return '低位', avg
    return '退潮', avg


def _v6_match_sectors(text, sector_map):
    """板块关键词匹配（与行业政策传导引擎同源）"""
    matched = []
    for kw, sec in _V6_SECTOR_KEYWORDS.items():
        if kw in text and sec not in matched:
            matched.append(sec)
    return matched


def _v6_market_regime(sector_map):
    """市场环境：risk_on / risk_off / neutral（按板块普涨普跌粗判）"""
    if not sector_map:
        return 'neutral'
    up = sum(1 for s in sector_map.values() if float(s.get('change_pct', 0) or 0) > 0.3)
    down = sum(1 for s in sector_map.values() if float(s.get('change_pct', 0) or 0) < -0.3)
    if up >= down + 3:
        return 'risk_on'
    if down >= up + 3:
        return 'risk_off'
    return 'neutral'


def _v6_evidence_level(news, text):
    """证据分级：A公告/合同/中标，B董秘回复/互动易，C媒体/产业链，D市场传闻"""
    source = str(news.get('source', '')) + str(news.get('source_tag', ''))
    category = str(news.get('category', ''))
    if any(k in text for k in _RUMOR_WORDS):
        return 'D'
    if '巨潮' in source or '公告' in category or any(k in text for k in ['中标', '合同', '签署', '发布公告', '披露']):
        return 'A'
    if any(k in text for k in ['董秘', '互动易', '投资者关系']):
        return 'B'
    return 'C'


def _v6_stars(pct, sentiment):
    """受益确定性星级：★★★直接关联 / ★★板块映射 / ★情绪外溢"""
    if sentiment == '利空':
        return '★'
    if pct >= 0:
        return '★★★' if sentiment == '利好' else '★★'
    return '★'


def _v6_opportunity(news, wencai_stocks, matched_sectors, sector_map, stage, avg_cp, sentiment):
    """📈 机会挖掘（红榜）HTML：核心直接受益 / 间接映射 / 板块效应 / 星级排序"""
    bc = _bc()
    parts = []
    has_direct = False
    if wencai_stocks:
        parts.append('<b>核心/直接关联标的（问财真实返回）：</b><br>')
        for s in wencai_stocks[:6]:
            name = s.get('name', '')
            code = s.get('code', '')
            try:
                pct = float(s.get('pct', 0) or 0)
            except Exception:
                pct = 0.0
            price = s.get('price', 0)
            color = '#FF3B30' if pct >= 0 else '#34C759'
            price_str = f'{price:.2f}' if price else '--'
            stars = _v6_stars(pct, sentiment)
            parts.append(
                f'{name}({code}) 现价<span style="color:#1E293B">{price_str}</span> '
                f'<span style="color:{color}">{pct:+.2f}%</span>　'
                f'<span style="color:#D97706">{stars}</span><br>'
            )
        has_direct = True
    stock_list = news.get('stock_codes', news.get('stocks', []))
    if isinstance(stock_list, list) and stock_list:
        named = [st for st in stock_list if isinstance(st, dict) and st.get('name')]
        if named and not has_direct:
            parts.append('<b>新闻明确提及（直接关联）：</b><br>')
            for st in named[:5]:
                parts.append(
                    f"{st.get('name', '')}({str(st.get('code', '')).zfill(6)})　"
                    f'<span style="color:#D97706">★★★</span><br>'
                )
            has_direct = True
    if matched_sectors:
        parts.append('<b>间接/映射（板块联动，附本地实时涨跌幅）：</b><br>')
        for sname in matched_sectors[:6]:
            parts.append(bc._deep_fmt_sector(sector_map, sname) + '　')
        parts.append('<br>')
    elif not has_direct:
        parts.append('<b>间接/映射：</b>按产业链上下游关注——上游资源/材料端、中游制造端、下游应用端，可在板块雷达中按行业景气度筛选龙头。<br>')
    effect = '足以驱动整个板块' if (len(matched_sectors) >= 2 or (wencai_stocks and sentiment == '利好')) else '对单一板块驱动有限，更多是局部机会'
    stage_disp = _V6_STAGE_DISPLAY.get(stage, stage)
    parts.append(f'<b>板块效应：</b>{effect}；当前阶段：<b>{stage_disp}</b>（关联板块均涨{avg_cp:+.2f}%）。')
    parts.append('<br><span style="color:#64748B">受益确定性排序：★★★ 直接关联（问财/公告/新闻明确提及）＞ ★★ 板块映射 ＞ ★ 情绪外溢。</span>')
    return ''.join(parts)


def _v6_seesaw(category, sentiment):
    """连带风险/跷跷板效应"""
    if category == '大宗商品' and sentiment == '利好':
        return '商品涨价→上游资源品吸金，中下游（航空/化工/火电等成本敏感方向）短期资金分流承压。'
    if category == '期货指数异动':
        return '小盘风格异动→红利/大盘权重可能承接避险资金；反之权重行情抽离小盘题材资金。'
    if category == '行业政策' and sentiment == '利好':
        return '新主线走强→传统同源板块（如传统制造/旧能源）短期资金分流，注意主线切换。'
    if category == '国际政治' and sentiment == '利空':
        return '避险情绪升温→黄金/军工/红利相对受益，成长与外资重仓方向资金流出。'
    if category == '个股公告':
        return '个股异动带动同板块情绪，但跟风标的无基本面支撑回落更快；同板块龙头可能虹吸资金。'
    return '主线轮动下注意相关板块间的资金跷跷板，勿在单一方向重仓。'


def _v6_evade(sentiment, stage):
    """避险提示"""
    if sentiment == '利空':
        if stage == '退潮':
            return '短期回避为主，已持仓者注意止损纪律，不急于抄底。'
        return '短期回避或逢高减磅，等待情绪出清与止跌信号。'
    if sentiment == '利好':
        if stage == '高潮':
            return '注意止盈，谨防利好兑现出货，不追涨停。'
        if stage == '预热':
            return '回调低吸为主，勿追高，仓位分批。'
        return '可左侧潜伏或右侧突破跟随，仓位控制在可承受范围。'
    return '消息中性，观望为主，等待催化验证再定仓位。'


def _v6_risk_block(news, analysis4_risk, category, sentiment, wencai_stocks, stage):
    """📉 风险预警（黑榜）HTML：风险预期差 / 直接受损或纯概念 / 跷跷板 / 避险提示"""
    parts = ['<b>风险与预期差：</b><br>']
    risk_text = _v6_strip_html(analysis4_risk or '')
    if risk_text.startswith('风险与预期差：'):
        risk_text = risk_text[len('风险与预期差：'):]
    parts.append(risk_text + '<br><br>')
    if sentiment == '利空' and wencai_stocks:
        parts.append('<b>直接受损标的（问财返回且今日下跌）：</b><br>')
        fell = []
        for s in wencai_stocks:
            try:
                p = float(s.get('pct', 0) or 0)
            except Exception:
                p = 0.0
            if p < -0.5:
                fell.append((s, p))
        fell = fell[:5]
        if fell:
            for s, p in fell:
                parts.append(
                    f"{s.get('name', '')}({s.get('code', '')}) "
                    f"<span style='color:#34C759'>{p:+.2f}%</span>　谨慎观望<br>"
                )
        else:
            parts.append('暂无明确下挫标的，仍应规避无业绩支撑的跟风股。<br>')
    else:
        parts.append('<b>纯概念股警示：</b>谨防无实质业务关联、靠蹭热点拉升的标的，退潮期此类个股回撤最剧烈，注意识别澄清公告。<br>')
    parts.append('<b>连带风险/跷跷板效应：</b>' + _v6_seesaw(category, sentiment) + '<br>')
    parts.append('<b>避险提示：</b>' + _v6_evade(sentiment, stage) + '<br>')
    return ''.join(parts)


def _v6_resonance(news, sentiment, impact, category, matched_sectors, sector_map, stage, avg_cp):
    """🌡️ 交易环境共振 HTML：情绪匹配 / 历史股性 / 操作节奏 / 仓位风控"""
    parts = []
    if matched_sectors and abs(avg_cp) > 0.3:
        if (sentiment == '利好' and avg_cp > 0) or (sentiment == '利空' and avg_cp < 0):
            amp = '放大'
            detail = f'相关板块实际均涨跌{avg_cp:+.2f}%，方向与消息一致，市场已共振'
        else:
            amp = '衰减'
            detail = f'相关板块实际均涨跌{avg_cp:+.2f}%，方向与消息背离，资金未跟进'
    else:
        amp = '中性'
        detail = '板块数据暂不足以确认共振，需结合大盘量能与主线节奏判断'
    parts.append(f'<b>市场情绪匹配：</b>消息影响力{amp}——{detail}。<br>')

    pattern = {
        '期货指数异动': '期指异动历史上多为"当日风格切换→次日确认"的节奏，单日脉冲不等于趋势，一日游与主升浪的分水岭在期现联动与量能',
        '大宗商品': '涨价题材历史走势为"期货领涨→资源股脉冲→业绩验证分化"，前期涨幅大者反转时回撤也大，易高开低走',
        '宏观数据': '宏观数据公布日多为"预期交易兑现日"，公布即兑现、反向波动是常态，持续性取决于政策跟进',
        '国际政治': '外部事件驱动多为脉冲式行情，1-2个交易日内情绪溢价即消化，低开反包与高开低走均常见，看落地文本',
        '个股公告': '利好公告常见"高开低走"（公布前已涨）或"低开反包"（超预期），利空公告易一次性宣泄后超跌反弹',
        '行业政策': '政策行情惯走"顶层定调→细则催化→业绩验证"三阶段，预热期低吸优于高潮期追高',
    }.get(category, '事件驱动行情以脉冲为主，持续性看后续催化与量能')
    parts.append(f'<b>历史股性参考：</b>{pattern}。<br>')

    if sentiment == '利好':
        if stage == '高潮':
            rhythm = '板块已处于高潮，注意止盈、谨防利好兑现出货，勿追今日涨停板'
        elif stage == '预热':
            rhythm = '板块已预热，建议关注回调低吸机会，勿追高，等分歧转一致'
        else:
            rhythm = '板块处于低位/蓄势，可左侧潜伏或右侧突破跟随，突破需放量确认'
    elif sentiment == '利空':
        if stage == '退潮':
            rhythm = '板块退潮+利空共振，建议短期回避，等待情绪出清'
        else:
            rhythm = '利空落地后或有超跌反弹，但不宜抢反弹，等待止跌信号'
    else:
        rhythm = '消息中性，建议观望，等待催化验证后再定操作'
    parts.append(f'<b>操作节奏建议：</b>{rhythm}。<br>')

    if sentiment == '利好' and stage == '高潮':
        position = '情绪高潮期不宜追高，建议降低单票仓位，获利部分分批了结'
    elif sentiment == '利空':
        position = '利空期控制总仓位，严格执行止损纪律，破位离场观察，不逆势加仓'
    elif sentiment == '利好':
        position = '趋势未确认前控制仓位在可承受范围，题材仓与基本面仓分开管理'
    else:
        position = '中性观望期轻仓应对，等待信号明确后再上仓位'
    parts.append(f'<b>仓位与风控：</b>{position}。')
    parts.append('<br><span style="color:#64748B">本模块为交易观察与原则性风控建议，不构成具体买卖点位指导。</span>')
    return ''.join(parts)


def _v6_quant_tags(news, category, sentiment, impact, matched_sectors, sector_map,
                    stage, avg_cp, wencai_stocks, duration, catalyst_node, evidence,
                    regime, rumor, text):
    """🏷️ 量化标签（纯JSON，供程序解析/打标/触发量化信号）"""
    base = {'利好': 0.7, '利空': -0.7, '中性': 0.0}.get(sentiment, 0.0)
    if impact == '强':
        base += 0.15 if base >= 0 else -0.15
    elif impact == '弱':
        base += -0.1 if base >= 0 else 0.1
    base = max(-1.0, min(1.0, base))

    relevance = min(100, 80 + len(matched_sectors) * 4 + len(wencai_stocks) * 3)
    is_priced_in = (stage == '高潮') or (avg_cp >= 2.0)
    risk_level = 'high' if (sentiment == '利空' or stage == '高潮') else ('medium' if sentiment == '中性' else 'low')
    if sentiment == '利空' and stage == '退潮':
        risk_level = 'high'
    event_type_map = {
        '期货指数异动': 'index', '大宗商品': 'commodity', '宏观数据': 'macro',
        '国际政治': 'geo', '个股公告': 'announcement', '行业政策': 'policy',
    }
    confidence = 'high' if (len(wencai_stocks) >= 3 or len(matched_sectors) >= 3) else (
        'medium' if wencai_stocks or matched_sectors else 'low')
    trade_style = {
        '期货指数异动': 'momentum', '国际政治': 'momentum', '个股公告': 'event_driven',
    }.get(category, 'swing')
    if sentiment == '利好':
        advice = {'高潮': '止盈', '预热': '回调低吸', '低位': '低吸', '退潮': '观望'}.get(stage, '观望')
    elif sentiment == '利空':
        advice = {'退潮': '止损'}.get(stage, '观望')
    else:
        advice = '观望'
    black_swan = bool(category == '国际政治' and any(k in text for k in _BLACK_SWAN_WORDS))
    return {
        'sentiment_score': round(base, 2),
        'relevance_score': relevance,
        'impact_duration': duration,
        'sector_tags': matched_sectors,
        'risk_level': risk_level,
        'is_priced_in': is_priced_in,
        'event_type': event_type_map.get(category, 'policy'),
        'evidence_level': evidence,
        'beneficiary_confidence': confidence,
        'market_regime': regime,
        'trade_style': trade_style,
        'sector_stage': stage,
        'key_catalyst_node': catalyst_node,
        'operation_advice': advice,
        'black_swan_flag': black_swan,
        'rumor_flag': rumor,
    }


def _v6_build_analysis(news, sector_map=None, wencai_stocks=None, wencai_voice=''):
    """V6量化投研简报生成器：6模块 + 量化标签JSON。

    Args:
        news: 新闻dict（title/content/sentiment/intensity/source/category/stock_codes）
        sector_map: 板块实时数据 {name: {change_pct,...}}，None时自动获取
        wencai_stocks: 问财返回的真实关联股票 [{name, code, price, pct}]
        wencai_voice: 问财voice_txt（交叉验证信息）

    Returns:
        dict: {
            'core_pick': 一句话核心提炼,
            'logic_event': 事件定性,
            'logic_gap': 预期差分析,
            'logic_chain': 传导机制,
            'logic_catalyst': 时效与催化,
            'opportunity': 机会红榜HTML,
            'risk': 风险黑榜HTML,
            'resonance': 交易环境共振HTML,
            'quant': 量化标签dict,
            'quant_json': 量化标签JSON字符串,
            'sentiment': 利好/利空/中性,
            'impact': 强/中/弱,
        }
    """
    bc = _bc()
    if sector_map is None:
        sector_map = bc._deep_get_sector_map()
    wencai_stocks = wencai_stocks or []
    title = str(news.get('title', ''))
    content = str(news.get('content', ''))
    text = title + ' ' + content
    category = bc._deep_classify_news(news)
    sentiment = str(news.get('sentiment', '中性') or '中性')
    if sentiment not in ('利好', '利空', '中性'):
        sentiment = '中性'
    impact = str(news.get('intensity', news.get('impact', '中')) or '中')
    if impact not in ('强', '中', '弱'):
        impact = '中'
    d = bc._deep_dir(text)

    # 底层4段式内容（复用分类传导链引擎）
    base = bc._deep_logical_analysis(news, sector_map=sector_map, wencai_voice=wencai_voice)

    # 板块匹配与阶段判断
    matched_sectors = _v6_match_sectors(text, sector_map)
    stage, avg_cp = _v6_sector_stage(matched_sectors, sector_map)
    catalyst_text, duration = _v6_catalyst(category)
    rumor = bool(any(k in text for k in _RUMOR_WORDS))
    evidence = _v6_evidence_level(news, text)
    regime = _v6_market_regime(sector_map)

    chain = _v6_clean_chain(base.get('core_logic', ''), wencai_voice)
    if not chain:
        chain = '事件 → 产业链上下游订单/价格/政策 → 企业盈利预期 → 估值与资金面 → 股价反应，详见下方板块映射。'

    quant = _v6_quant_tags(
        news, category, sentiment, impact, matched_sectors, sector_map,
        stage, avg_cp, wencai_stocks, duration,
        _V6_CATALYST.get(category, '后续官方/公司公告与行业高频数据'),
        evidence, regime, rumor, text,
    )

    return {
        'core_pick': _v6_core_pick(category, sentiment, text, d),
        'logic_event': _v6_event_type(category, text),
        'logic_gap': _v6_gap(category, sentiment, text, stage, avg_cp),
        'logic_chain': chain,
        'logic_catalyst': catalyst_text,
        'opportunity': _v6_opportunity(news, wencai_stocks, matched_sectors, sector_map, stage, avg_cp, sentiment),
        'risk': _v6_risk_block(news, base.get('risk', ''), category, sentiment, wencai_stocks, stage),
        'resonance': _v6_resonance(news, sentiment, impact, category, matched_sectors, sector_map, stage, avg_cp),
        'quant': quant,
        'quant_json': json.dumps(quant, ensure_ascii=False, indent=2),
        'sector_tags': matched_sectors,
        'sentiment': sentiment,
        'impact': impact,
    }
