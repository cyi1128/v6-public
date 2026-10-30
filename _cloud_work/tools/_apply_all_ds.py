# -*- coding: utf-8 -*-
"""纯规则通道 LLM 化：build_hourly / build_confirm / build_holiday_news 全部接入大白话五步模型。勿重跑。"""
import io
P = r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py'
s = io.open(P, encoding='utf-8').read()
cnt = {'ok': 0, 'fail': []}

def rep(old, new, must=1):
    global s
    n = s.count(old)
    if n != must:
        cnt['fail'].append((old[:60].replace('\n', '\\n'), n, must))
        return
    s = s.replace(old, new)
    cnt['ok'] += 1

FIVE_BRIEF = ('【大白话五步铁律】第一步·先干活后说话：先把数据事实说清，不许上来就喊涨跌；'
              '第二步·问三个问题：①为什么涨/跌——驱动是政策/业绩/资金/纯情绪，给依据；②跟我什么关系——能买吗、踩雷吗、和持仓有没有联动；③风险藏在哪——位置/业绩/暗雷（解禁/担保/减持）；'
              '第三步·翻译成人话：术语必须配翻译，打比方优先（击鼓传花/接飞刀/烧到头的鞭炮/装死/开奖日），结论先行+动作可执行；'
              '第四步·套纪律：高位连板一律别追，四重共振不够就「看戏不追」，加仓只加确定性（缩量企稳才算信号），放量破位止损位给死；'
              '第五步·自查：结论和逻辑不许矛盾，说机会必须带风险位，能扛住用户反推。')

# ================= 1. build_hourly =================
rep('def build_hourly():',
    '''def _hourly_ds(idx, d, b, zbr):
    """每小时行情 LLM 深度解读（五步大白话）。失败返回 ''（原规则操作建议保留）。"""
    if not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return ''
    try:
        idx_txt = '、'.join(f"{x['name']}{x['pct']:+.2f}%" for x in idx) or '未取得'
        tops = '、'.join(f"{sec}({len(sts)}只)" for sec, sts in sorted(d['sectors'].items(), key=lambda kv: -len(kv[1]))[:5]) or '无'
        hold_txt = '；'.join(f"{h['name']}成本{h['cost']}" for h in HOLDINGS)
        fmt = (FIVE_BRIEF
               + '你是10年A股短线交易员，基于以下盘中数据做整点解读，输出 JSON（不要任何其他文字）：\\n'
               + '{"overall":"现在盘面真正什么情况(用数据说，别空喊)，一句大白话+能不能做","hold":"持仓(' + hold_txt + ')每只看一眼：该拿/该减/破位信号，一句大白话","op":"该干什么：具体动作+仓位档(按情绪绑定)","risk":"最大风险+什么情况必须撤，一句话"}\\n'
               + '数据：指数 ' + idx_txt + '；涨停{d["lu"]}家 炸板{d["zb"]}家(炸板率{zbr*100:.0f}%) 跌停{d["dt"]}家 最高{d["max_lbc"]}板；情绪=' + b + '；最强板块 ' + tops)
        t = ask_deepseek({'task': 'hourly_ds', 'idx': idx_txt, 'tops': tops, 'b': b,
                          'lu': d['lu'], 'zb': d['zb'], 'dt': d['dt'], 'max_lbc': d['max_lbc'],
                          'format': fmt}, purpose='hourly_ds')
        if not t:
            return ''
        _j = json.loads(t)
        out = []
        if _j.get('overall'):
            out.append('<div style="color:#e9ecef;font-size:13px;">🧭 盘面：' + str(_j['overall']) + '</div>')
        if _j.get('hold'):
            out.append('<div style="color:' + TEAL + ';font-size:13px;margin-top:3px;">📌 持仓：' + str(_j['hold']) + '</div>')
        if _j.get('op'):
            out.append('<div style="color:' + GOLD + ';font-size:13px;margin-top:3px;">💡 操作：' + str(_j['op']) + '</div>')
        if _j.get('risk'):
            out.append('<div style="color:' + RED + ';font-size:13px;margin-top:3px;">⚠️ 风险：' + str(_j['risk']) + '</div>')
        if not out:
            return ''
        return '<div style="margin-top:8px;padding:10px;background:#1c2230;border-left:4px solid ' + TEAL + ';border-radius:8px;">' + ''.join(out) + '</div>'
    except Exception:
        return ''


def build_hourly():''')

rep('''    inner = f"""\{_overall}
<div style="font-size:14px;">{bits}</div>
<div style="margin-top:6px;font-size:14px;">🔴涨停<b style="color:{RED}">{d['lu']}</b> 🟢炸板<b style="color:{GREEN}">{d['zb']}</b> 🟢跌停<b style="color:{GREEN}">{d['dt']}</b> 最高<b style="color:{GOLD}">{d['max_lbc']}板</b> ｜ 情绪 <b style="color:{_c(avg)}">{b}</b>（炸板率 {zbr*100:.0f}%）</div>
<div style="margin-top:4px;font-size:13px;">{breadth_sample()}</div>
<div style="margin-top:4px;font-size:13px;">{money_flow_note()}</div>
<div style="margin-top:8px;padding:10px;background:#1c2230;border-left:4px solid {ac};border-radius:8px;font-size:13px;font-weight:700;color:{ac};">📌 操作建议：{advice}</div>
<div style="margin-top:8px;padding:9px 11px;background:#2a1f22;border-left:4px solid {rc};border-radius:8px;font-size:13px;color:{rc};">⚠️ {risk_line}</div>{leader_divergence(d)}''',
    '''    inner = f"""\{_overall}
<div style="font-size:14px;">{bits}</div>
<div style="margin-top:6px;font-size:14px;">🔴涨停<b style="color:{RED}">{d['lu']}</b> 🟢炸板<b style="color:{GREEN}">{d['zb']}</b> 🟢跌停<b style="color:{GREEN}">{d['dt']}</b> 最高<b style="color:{GOLD}">{d['max_lbc']}板</b> ｜ 情绪 <b style="color:{_c(avg)}">{b}</b>（炸板率 {zbr*100:.0f}%）</div>
<div style="margin-top:4px;font-size:13px;">{breadth_sample()}</div>
<div style="margin-top:4px;font-size:13px;">{money_flow_note()}</div>
{_ds_block or '<div style="margin-top:8px;padding:10px;background:#1c2230;border-left:4px solid ' + ac + ';border-radius:8px;font-size:13px;font-weight:700;color:' + ac + ';">📌 操作建议：' + advice + '</div>'}
<div style="margin-top:8px;padding:9px 11px;background:#2a1f22;border-left:4px solid {rc};border-radius:8px;font-size:13px;color:{rc};">⚠️ {risk_line}</div>{leader_divergence(d)}''')

rep('''    return _wrap(inner, '⏱️', '盘中解读')


def _fx(code):''',
    '''    _ds_block = _hourly_ds(idx, d, b, zbr)
    return _wrap(inner, '⏱️', '盘中解读')


def _fx(code):''')

# ================= 2. build_confirm =================
rep('def build_confirm():',
    '''def _confirm_ds(infos):
    """竞价确认 LLM 深挖：对 TOP5 每只输出 为什么能跟/为什么放弃（大白话五步）。失败返回 {}（保留原规则文案）。"""
    if not infos or not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return {}
    hold = '；'.join(f"{h['name']}(成本{h['cost']})" for h in HOLDINGS)
    lines = '\\n'.join(f"- {x['name']}({x['code']}) 高开{x['op']:+.1f}% 量比{x['lb']:.1f} 题材{x['sec']} 判定={'可跟' if x['ok'] else '放弃'}（规则原因：{x['why']}）" for x in infos)
    fmt = ('你是10年A股超短线交易员，竞价确认阶段，对下面每只票逐一解释判定，不许只说"不在区间"：\\n'
           + FIVE_BRIEF + '\\n'
           + '竞价名单：\\n' + lines + '\\n'
           + '持仓：' + hold + '（若与持仓同题材/同板块必须点名联动）\\n'
           + '只输出 JSON：{"per":[{"name":"股票名称","reason":"为什么能跟/为什么放弃(大白话深挖: 高开是否透支/量比真假/题材是不是当日主线/有没有暗雷/和持仓关系)，至少25字"}]}，'
           + '必须覆盖每只，不许偷懒。')
    t = ask_deepseek({'task': 'confirm_ds', 'stocks': [{'name': x['name'], 'code': x['code'], 'op': x['op'],
                                                        'lb': x['lb'], 'sec': x['sec'], 'ok': x['ok']} for x in infos],
                      'format': fmt}, purpose='confirm_ds')
    out = {}
    if not t:
        return out
    try:
        _j = json.loads(t)
        for it in _j.get('per') or []:
            nm = str(it.get('name') or '').strip()
            if nm and it.get('reason'):
                out[nm] = str(it['reason'])
    except Exception:
        pass
    return out


def build_confirm():''')

rep('''    rows, ok_n = [], 0
    for s in cands[:5]:
        sym = ('sh' if s['code'].startswith('6') else 'sz') + s['code']
        try:
            q = _qt(sym)
            if not q or not q['prev']:
                continue
            op = (q['open'] / q['prev'] - 1) * 100  # 真实高开幅度（open/昨收）
            vq = None
            try:
                arr = get_klines(sym, 2)
                if len(arr) >= 2 and float(arr[-2][5]) > 0 and q.get('vol'):
                    vq = (q['vol'] * 100) / float(arr[-2][5]) * 100
            except Exception:
                pass
            gem = s.get('board') == 'gem'
            lo, hi = (2, 7) if not gem else (4, 14)
            lb_min = 2.0 if not gem else 1.5
            sec_heat = heat.get(re.sub(r'[行业板块概念\\s]+', '', s['industry']) or '其他', 0)
            if lo <= op <= hi and q.get('lb', 0) >= lb_min and (vq is None or vq >= 8):
                rows.append(f'<div style="margin:6px 0;font-size:13px;background:#1c2830;border-left:3px solid {RED};border-radius:8px;padding:7px 10px;">'
                            f'✅ <b style="color:#fff;">{s["name"]}({s["code"]})</b> 高开{op:+.1f}% 量比{q.get("lb", 0):.1f} '
                            f'→ <span style="color:{RED};font-weight:800;">可跟 1成试探，止损-3%</span>'
                            f'<div style="color:{TEAL};font-size:12px;">今日总仓建议：{_pos_advice(_emotion_from_pools(d))}</div>'
                            f'<div style="color:{TEAL};font-size:12px;">题材 {s["industry"]}（热度{sec_heat:.0f}）｜综合分 {s["score"]}</div></div>')
                ok_n += 1
            else:
                if q.get('lb', 0) < lb_min:
                    why = f'量比{q.get("lb", 0):.1f}<{lb_min}，资金竞价没进场，撑不起高开，放弃'
                elif op > hi:
                    why = f'高开{op:+.1f}%超过{hi}%，竞价透支、开盘容易被砸，放弃'
                elif op < lo:
                    why = f'高开{op:+.1f}%不足{lo}%，没溢价不值得做，放弃'
                else:
                    why = '竞价量/昨量不足8%，虚量撑不住，放弃'
                rows.append(f'<div style="margin:6px 0;font-size:13px;background:#1f2635;border-left:3px solid {GREY};border-radius:8px;padding:7px 10px;">'
                            f'❌ {s["name"]}({s["code"]}) 高开{op:+.1f}% 量比{q.get("lb", 0):.1f} → <span style="color:{GREY};">放弃（{why}）</span></div>')
        except Exception:
            continue''',
    '''    rows, ok_n, infos = [], 0, []
    for s in cands[:5]:
        sym = ('sh' if s['code'].startswith('6') else 'sz') + s['code']
        try:
            q = _qt(sym)
            if not q or not q['prev']:
                continue
            op = (q['open'] / q['prev'] - 1) * 100  # 真实高开幅度（open/昨收）
            vq = None
            try:
                arr = get_klines(sym, 2)
                if len(arr) >= 2 and float(arr[-2][5]) > 0 and q.get('vol'):
                    vq = (q['vol'] * 100) / float(arr[-2][5]) * 100
            except Exception:
                pass
            gem = s.get('board') == 'gem'
            lo, hi = (2, 7) if not gem else (4, 14)
            lb_min = 2.0 if not gem else 1.5
            sec_heat = heat.get(re.sub(r'[行业板块概念\\s]+', '', s['industry']) or '其他', 0)
            sec_clean2 = re.sub(r'[行业板块概念\\s]+', '', s['industry']) or '其他'
            ok_flag = lo <= op <= hi and q.get('lb', 0) >= lb_min and (vq is None or vq >= 8)
            if ok_flag:
                why_r = ''
                rows.append(f'<div style="margin:6px 0;font-size:13px;background:#1c2830;border-left:3px solid {RED};border-radius:8px;padding:7px 10px;">'
                            f'✅ <b style="color:#fff;">{s["name"]}({s["code"]})</b> 高开{op:+.1f}% 量比{q.get("lb", 0):.1f} '
                            f'→ <span style="color:{RED};font-weight:800;">可跟 1成试探，止损-3%</span>'
                            f'<div style="color:{TEAL};font-size:12px;">今日总仓建议：{_pos_advice(_emotion_from_pools(d))}</div>'
                            f'<div style="color:{TEAL};font-size:12px;">题材 {s["industry"]}（热度{sec_heat:.0f}）｜综合分 {s["score"]}</div></div>')
                ok_n += 1
            else:
                if q.get('lb', 0) < lb_min:
                    why_r = f'量比{q.get("lb", 0):.1f}<{lb_min}，资金竞价没进场，撑不起高开，放弃'
                elif op > hi:
                    why_r = f'高开{op:+.1f}%超过{hi}%，竞价透支、开盘容易被砸，放弃'
                elif op < lo:
                    why_r = f'高开{op:+.1f}%不足{lo}%，没溢价不值得做，放弃'
                else:
                    why_r = '竞价量/昨量不足8%，虚量撑不住，放弃'
                rows.append(f'<div style="margin:6px 0;font-size:13px;background:#1f2635;border-left:3px solid {GREY};border-radius:8px;padding:7px 10px;">'
                            f'❌ {s["name"]}({s["code"]}) 高开{op:+.1f}% 量比{q.get("lb", 0):.1f} → <span style="color:{GREY};">放弃（{why_r}）</span></div>')
            infos.append({'name': s['name'], 'code': s['code'], 'op': op, 'lb': float(q.get('lb', 0)),
                          'sec': sec_clean2, 'ok': ok_flag, 'why': why_r})
        except Exception:
            continue''')

rep('''    if not rows:
        return _wrap('<div style="color:#e2e8f0;font-size:13px;">今日竞价无确认标的，多看少动</div>', '🔔', '竞价确认')
    inner = (f'<div style="color:{TEAL};font-size:13px;">基于 09:20 双打分 TOP5 实盘复核（纯规则，不调 AI）'
             f'｜确认 {ok_n} 只</div>' + ''.join(rows))
    return _wrap(inner, '🔔', '竞价确认')''',
    '''    if not rows:
        return _wrap('<div style="color:#e2e8f0;font-size:13px;">今日竞价无确认标的，多看少动</div>', '🔔', '竞价确认')
    _dmap = _confirm_ds(infos)
    rows2 = list(rows)
    if _dmap:
        rows2.append('<div style="margin-top:6px;padding:8px 10px;background:#1c2230;border-left:4px solid ' + TEAL + ';border-radius:8px;">'
                     + ''.join('<div style="color:#e9ecef;font-size:12px;margin:3px 0;">🧠 ' + nm + '：' + rz + '</div>'
                               for nm, rz in _dmap.items()) + '</div>')
    inner = (f'<div style="color:{TEAL};font-size:13px;">基于 09:20 双打分 TOP5 实盘复核（规则复核 + AI 深挖）'
             f'｜确认 {ok_n} 只</div>' + ''.join(rows2))
    return _wrap(inner, '🔔', '竞价确认')''')

# ================= 3. build_holiday_news =================
rep('def build_holiday_news():',
    '''def _holiday_ds(items):
    """休市日新闻 LLM 五步深挖：批量生成 板块题材/利好利空/大白话/操作。失败返回 {}（回退规则 news_tags）。"""
    if not items or not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return {}
    hold = '；'.join(f"{h['name']}(成本{h['cost']})" for h in HOLDINGS)
    news_txt = '\\n'.join(f"- {x['title']}（摘要：{x['summary'][:50]}）" for x in items[:10])
    fmt = ('你是10年A股超短线交易员，休市日新闻汇总，对每条新闻严格按大白话五步铁律深度挖掘，不许偷懒：\\n'
           + FIVE_BRIEF + '\\n'
           + '新闻列表：\\n' + news_txt + '\\n'
           + '只输出 JSON：{"items":[{"t":"标题(照抄)","sector":"板块题材(至少8字，猜不到写「暂看不出直接关联」)","stocks":"相关个股(没有写无)","good":"✅利好什么(至少8字，无则写无明显直接利好)","bad":"⚠️利空什么(至少8字，无则写无明显直接利空)","why":"大白话(一句话戳穿+怎么应对，至少20字，必须打比方或术语翻译)","act":"操作(买/躲/看+条件，至少15字)"}]}，'
           + '必须覆盖每条新闻。持仓：' + hold + '，相关必须点名联动。')
    t = ask_deepseek({'task': 'holiday_ds', 'news': [{'title': x['title'], 'summary': x['summary'][:60]} for x in items[:10]],
                      'format': fmt}, purpose='holiday_ds')
    out = {}
    if not t:
        return out
    try:
        _j = json.loads(t)
        for it in _j.get('items') or []:
            tt = str(it.get('t') or '').strip()
            if tt and (it.get('why') or it.get('sector')):
                out[tt] = {'sector': str(it.get('sector') or ''), 'stocks': str(it.get('stocks') or ''),
                           'good': str(it.get('good') or ''), 'bad': str(it.get('bad') or ''),
                           'why': str(it.get('why') or ''), 'act': str(it.get('act') or '')}
    except Exception:
        pass
    return out


def build_holiday_news():''')

rep('''    items = []
    for nw in today_news:
        title = nw.get('title', '').strip()
        summary = nw.get('summary', '').strip()
        ts = str(nw.get('ts') or '')
        src = nw.get('source') or '东财7x24'
        if not title and not summary:
            continue
        sentiment, color = classify_news(title + ' ' + summary)
        sector, stocks, plain = news_tags(title, summary)
        tag_html = ''
        if sector:
            tag_html = (f'<div style="color:{TEAL};font-size:12px;margin-top:3px;">🏷️ 板块题材：{sector}'
                        f'｜相关个股：{stocks}</div>')
        if plain:
            tag_html += (f'<div style="color:#e2e8f0;font-size:12px;margin-top:3px;">'
                         f'🗣️ 大白话：{plain}</div>')
        items.append(f"""<div style="background:#1f2635;border-left:3px solid {color};border-radius:8px;padding:9px 11px;margin:7px 0;">
<b style="color:#fff;">【{sentiment}】{title or '（无标题）'}</b>
<div style="color:{GREY};font-size:12px;margin-top:2px;">🕐 {ts}｜来源：{src}</div>
<div style="color:#c8d0e0;font-size:13px;margin-top:4px;line-height:1.7;">{summary[:200]}</div>{tag_html}</div>""")''',
    '''    _deep_map = _holiday_ds([{'title': nw.get('title', ''), 'summary': nw.get('summary', '')}
                               for nw in today_news if nw.get('title', '').strip() or nw.get('summary', '').strip()])
    items = []
    for nw in today_news:
        title = nw.get('title', '').strip()
        summary = nw.get('summary', '').strip()
        ts = str(nw.get('ts') or '')
        src = nw.get('source') or '东财7x24'
        if not title and not summary:
            continue
        sentiment, color = classify_news(title + ' ' + summary)
        sector, stocks, plain = news_tags(title, summary)
        tag_html = ''
        _d = _deep_map.get(title) if _deep_map else None
        if _d:
            _sec2 = _d.get('sector') or sector
            _stk2 = _d.get('stocks') or stocks
            _gd = _d.get('good') or ''
            _bd = _d.get('bad') or ''
            _wh2 = _d.get('why') or plain
            _ac2 = _d.get('act') or ''
            tag_html = (f'<div style="color:{TEAL};font-size:12px;margin-top:3px;">🏷️ 板块题材：{_sec2}'
                        f'｜相关个股：{_stk2}</div>')
            if _gd:
                tag_html += (f'<div style="color:{RED};font-size:12px;margin-top:2px;">✅ 利好：{_gd}</div>')
            if _bd:
                tag_html += (f'<div style="color:{GREEN};font-size:12px;margin-top:2px;">⚠️ 利空：{_bd}</div>')
            if _wh2:
                tag_html += (f'<div style="color:#e2e8f0;font-size:12px;margin-top:2px;">🗣️ 大白话：{_wh2}</div>')
            if _ac2:
                tag_html += (f'<div style="color:{GOLD};font-size:12px;margin-top:2px;">💡 操作：{_ac2}</div>')
        else:
            if sector:
                tag_html = (f'<div style="color:{TEAL};font-size:12px;margin-top:3px;">🏷️ 板块题材：{sector}'
                            f'｜相关个股：{stocks}</div>')
            if plain:
                tag_html += (f'<div style="color:#e2e8f0;font-size:12px;margin-top:3px;">'
                             f'🗣️ 大白话：{plain}</div>')
        items.append(f"""<div style="background:#1f2635;border-left:3px solid {color};border-radius:8px;padding:9px 11px;margin:7px 0;">
<b style="color:#fff;">【{sentiment}】{title or '（无标题）'}</b>
<div style="color:{GREY};font-size:12px;margin-top:2px;">🕐 {ts}｜来源：{src}</div>
<div style="color:#c8d0e0;font-size:13px;margin-top:4px;line-height:1.7;">{summary[:200]}</div>{tag_html}</div>""")''')

io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('OK', cnt['ok'], '替换；失败：')
for f_ in cnt['fail']:
    print('  [%s] 次数=%s 期望=%s' % f_)
