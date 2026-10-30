def _warn_news_ds(items):
    """08:20 消息面点火预判 LLM：新闻→可能被点燃的板块→个股→点火逻辑→开盘验证→风险。失败返回 ''。"""
    if not items or not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return ''
    hold = '；'.join(f"{h['name']}(成本{h['cost']})" for h in HOLDINGS)
    news_txt = '\n'.join(f"- {x['title']}（摘要：{x['summary'][:60]}）" for x in items[:12])
    fmt = ('你是10年A股超短线交易员，现在是开盘前08:20，手里只有隔夜和当天的新闻，没有盘中数据。'
           '任务：判断哪些板块今天可能被消息面点火启动。严格按大白话五步铁律，不许空话：\n'
           + FIVE_BRIEF + '\n'
           + '新闻列表：\n' + news_txt + '\n'
           + '只输出 JSON：{"fire":[{"sector":"可能被点燃的板块(≥8字)","stocks":"相关个股(没有写无，别硬编)","logic":"为什么会被点燃：消息→板块→资金传导逻辑(≥30字，用大白话+打比方)","verify":"开盘怎么验证：竞价量比/高开幅度/板块联动至少几只(≥20字)","risk":"风险：利好兑现/一日游/高开低走等(≥15字)"}],"avoid":[{"sector":"要避开的板块","logic":"为什么避开(≥20字)"}],"hold":"和持仓(' + hold + ')的关系：相关必须点名联动/不相关一句话说明"}，'
           + 'fire 最多3个，必须真能从新闻推出，推不出就写"今日消息面无明确点火板块"，不许硬凑。')
    t = ask_deepseek({'task': 'warn_news_ds', 'news': items[:12], 'format': fmt}, purpose='warn_news_ds')
    return t if t else ''


def _warn_render_fire(_j):
    """渲染点火预判 JSON。"""
    out = []
    fire = _j.get('fire') or []
    if fire:
        out.append('<div style="font-size:15px;font-weight:800;color:#ff922b;">🔥 今日可能被消息点燃的板块（开盘前预判，等竞价验证）</div>')
        for i, f_ in enumerate(fire[:3], 1):
            out.append(f"""<div style="background:#1c2830;border-left:3px solid {RED};border-radius:8px;padding:9px 11px;margin:6px 0;">
<div style="font-size:13px;font-weight:700;color:#fff;">{i}. {f_.get('sector','')} <span style="color:{GREY};font-weight:400;">｜相关个股：{f_.get('stocks','无')}</span></div>
<div style="color:#a78bfa;font-size:12px;margin-top:2px;">🧠 点火逻辑：{f_.get('logic','')}</div>
<div style="color:{TEAL};font-size:12px;margin-top:2px;">🔍 开盘验证：{f_.get('verify','')}</div>
<div style="color:{GREEN};font-size:12px;margin-top:2px;">⚠️ 风险：{f_.get('risk','')}</div></div>""")
    avoid = _j.get('avoid') or []
    if avoid:
        out.append('<div style="font-size:14px;font-weight:800;color:' + GREEN + ';margin-top:6px;">🚫 消息面要避开的</div>')
        for a_ in avoid[:3]:
            out.append(f"""<div style="font-size:12px;color:#c8d0e0;margin:3px 0;">• {a_.get('sector','')}：{a_.get('logic','')}</div>""")
    if _j.get('hold'):
        out.append('<div style="font-size:13px;color:' + GOLD + ';margin-top:8px;">📌 持仓联动：' + str(_j['hold']) + '</div>')
    return ''.join(out)


def _warn_rule_fallback(items):
    """LLM 失败回退：规则 news_tags 汇总利好板块（不空推）。"""
    hot = {}
    for nw in items:
        sector, stocks, plain = news_tags(nw.get('title', ''), nw.get('summary', ''))
        if sector and sector != '宏观/全市场':
            hot[sector] = hot.get(sector, 0) + 1
    if not hot:
        print('[warn] 规则兜底也无明确板块，不推送')
        return None
    hot_sorted = sorted(hot.items(), key=lambda kv: -kv[1])[:3]
    rows = ''.join(f'<div style="font-size:13px;color:#e9ecef;margin:4px 0;">🔥 {k}（{v}条相关新闻）</div>' for k, v in hot_sorted)
    inner = ('<div style="color:' + RED + ';font-size:14px;font-weight:700;">🚨 今日消息面板块预警（规则版，AI未返回）</div>'
             + '<div style="color:' + GREY + ';font-size:12px;">开盘前按当日新闻归集的热点板块，仅供开盘参考：</div>' + rows)
    return _wrap(inner, '🚨', '启动预警'), '【消息面预警】' + _bj_now().strftime('%H:%M')


def build_warn():
    """板块启动预警（消息面版）08:20：开盘前没有盘中数据，原来用昨日涨停池/资金流评分预测「今日启动」逻辑不成立。
    改为：抓当日/隔夜新闻 → LLM 判断哪些板块可能被消息点燃（新闻→板块→个股传导）+ 开盘验证条件 + 风险。
    LLM 失败回退规则 news_tags 利好板块清单；新闻源异常/无有效新闻 → 不推送（不空推）。"""
    bj = _bj_now()
    try:
        news = get_news(20)
    except Exception as e:
        print('[warn] 新闻源异常:', e)
        news = []
    if not news:
        print('[warn] 无新闻源，不推送')
        return None
    items = []
    for nw in news:
        t = (nw.get('title') or '').strip()
        s = (nw.get('summary') or '').strip()
        if t or s:
            items.append({'title': t[:80], 'summary': s[:90]})
        if len(items) >= 15:
            break
    if not items:
        print('[warn] 新闻全部为空，不推送')
        return None
    t = _warn_news_ds(items)
    if not t:
        return _warn_rule_fallback(items)
    try:
        _j = json.loads(t)
    except Exception as e:
        print('[warn] LLM JSON 解析失败，走规则兜底:', e)
        return _warn_rule_fallback(items)
    if not (_j.get('fire') or _j.get('avoid')):
        print('[warn] LLM 判定今日消息面无明确点火板块，不推送（不硬凑）')
        return None
    inner = (f'<div style="color:{RED};font-size:14px;font-weight:700;">🚨 今日消息面点火预判 · 开盘前（{bj.strftime("%H:%M")}）</div>'
             f'<div style="color:{GREY};font-size:12px;margin-top:3px;">基于当日/隔夜 {len(items)} 条新闻推演，最终以竞价/开盘验证为准</div>'
             + _warn_render_fire(_j)
             + '<div style="color:' + GREY + ';font-size:11px;margin-top:8px;">① 验证：板块竞价量比明显放大+多股联动才算真启动；② 纪律：高位连板不追，低吸为主。</div>')
    return _wrap(inner, '🚨', '启动预警'), '【消息面点火预判】' + bj.strftime('%H:%M')
