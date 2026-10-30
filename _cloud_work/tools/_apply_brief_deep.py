# -*- coding: utf-8 -*-
"""事件简报添加大白话五步模型：_brief_deep 批量LLM深挖 + 渲染加三行。勿重跑。"""
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

# ========== 1. 新增 _brief_deep（插在 build_events 前） ==========
rep('def build_events(slot):', '''def _brief_deep(items):
    """事件简报·大白话五步深挖：对已筛事件批量 LLM 生成五要素。失败返回 {}（调用方用原模板兜底）。"""
    if not items or not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return {}
    hold = '；'.join(f"{h['name']}(成本{h['cost']})" for h in HOLDINGS)
    evs = '\\n'.join(f"- {x['title']}（标签：{x['tag']}）" for x in items[:6])
    fmt = ('你是10年A股超短线交易员。以下是一批市场事件简报，对每条严格按大白话五步铁律深度挖掘，不许偷懒：\\n'
           '【第一步·先干活后说话】先把事实说清（谁发布/干了什么/涉及谁），不许上来就喊利好。\\n'
           '【第二步·问三个问题】①为什么重要——驱动是政策、业绩、资金还是纯情绪，给依据；②跟我什么关系——利好/利空哪个板块题材个股，能买吗、踩雷吗、和持仓有没有联动；③风险藏在哪——有没有暗雷（解禁/担保/减持）、高位风险。\\n'
           '【第三步·翻译成人话】术语必须配翻译；打比方优先（击鼓传花/接飞刀/烧到头的鞭炮/装死/开奖日）；结论先行+动作可执行（具体价位/仓位/止损）。\\n'
           '【第四步·套纪律】高位连板一律别追；四重共振不够就「看戏不追」；加仓只加确定性（缩量企稳才算信号）；放量破位止损位给死。\\n'
           '【第五步·自查】结论和逻辑不许矛盾；说机会必须带风险位；能扛住用户反推（说它是政策票，要能答出业绩和位置）。\\n'
           '事件列表：\\n' + evs + '\\n'
           '只输出 JSON，不要任何其他文字：\\n'
           '{"items":[{"t":"事件标题（照抄原文）","impact":"利好/利空哪个板块/题材/个股，至少15字（猜不到写「暂看不出直接关联」，不许编）","logic":"为什么重要/驱动力深挖，至少25字","why":"大白话：一句话戳穿真假+怎么应对，至少22字（必须打比方或术语翻译）","act":"操作：买/躲/看+具体条件（买点/止损/仓位），至少20字"}]}，'
           '必须覆盖每条事件，不许偷懒。当前持仓：' + hold + '，若事件与持仓相关必须点名联动提醒。')
    t = ask_deepseek({'task': 'event_brief', 'events': [x['title'] for x in items[:6]],
                      'format': fmt}, purpose='brief')
    out = {}
    if not t:
        return out
    try:
        _j = json.loads(t)
        for it in _j.get('items') or []:
            tt = str(it.get('t') or '').strip()
            if tt and (it.get('logic') or it.get('why')):
                out[tt] = {'impact': str(it.get('impact') or ''),
                           'logic': str(it.get('logic') or ''),
                           'why': str(it.get('why') or ''),
                           'act': str(it.get('act') or '')}
    except Exception:
        pass
    return out


def build_events(slot):''')

# ========== 2. build_events 调用深挖 + 渲染三行 ==========
rep('''    n = {'pre': 5, 'noon': 4, 'eod': 5}.get(slot, 4)
    out = out[:n]
    if not out:
        return ''
    cards = ''.join(f"""<div style="background:#1f2635;border-left:4px solid {x['color']};border-radius:10px;padding:9px 12px;margin:6px 0;">
<div style="font-weight:800;color:{x['color']};">【{x['tag']}】</div>
<div style="color:#fff;font-size:13px;margin-top:3px;">{x['title']}</div>
<div style="color:{GREY};font-size:12px;margin-top:3px;">影响：{x['rel']}</div></div>""" for x in out)''',
'''    n = {'pre': 5, 'noon': 4, 'eod': 5}.get(slot, 4)
    out = out[:n]
    if not out:
        return ''
    _deep = _brief_deep(out)
    cards = []
    for x in out:
        _d = _deep.get(x['title']) if _deep else None
        if _d:
            _imp = _d.get('impact') or x['rel']
            _lo = _d.get('logic') or ''
            _wh = _d.get('why') or ''
            _ac = _d.get('act') or ''
            cards.append(f"""<div style="background:#1f2635;border-left:4px solid {x['color']};border-radius:10px;padding:9px 12px;margin:6px 0;">
<div style="font-weight:800;color:{x['color']};">【{x['tag']}】</div>
<div style="color:#fff;font-size:13px;margin-top:3px;">{x['title']}</div>
<div style="color:{TEAL};font-size:12px;margin-top:3px;">影响：{_imp}</div>
<div style="color:#e9ecef;font-size:12px;margin-top:3px;">🧠 逻辑：{_lo}</div>
<div style="color:{GOLD};font-size:12px;margin-top:2px;">👉 大白话：{_wh}</div>
<div style="color:{RED};font-size:12px;margin-top:2px;">💡 操作：{_ac}</div></div>""")
        else:
            cards.append(f"""<div style="background:#1f2635;border-left:4px solid {x['color']};border-radius:10px;padding:9px 12px;margin:6px 0;">
<div style="font-weight:800;color:{x['color']};">【{x['tag']}】</div>
<div style="color:#fff;font-size:13px;margin-top:3px;">{x['title']}</div>
<div style="color:{GREY};font-size:12px;margin-top:3px;">影响：{x['rel']}</div></div>""")
    cards = ''.join(cards)''')

io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('OK', cnt['ok'], '替换；失败：')
for f_ in cnt['fail']:
    print('  [%s] 次数=%s 期望=%s' % f_)
