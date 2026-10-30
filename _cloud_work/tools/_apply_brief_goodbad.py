# -*- coding: utf-8 -*-
"""事件简报升级：每条事件单独输出 利好什么/利空什么/逻辑原因 三行。勿重跑。"""
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

# ========== 1. prompt schema 加 good/bad ==========
rep('''           '【第二步·问三个问题】①为什么重要——驱动是政策、业绩、资金还是纯情绪，给依据；②跟我什么关系——利好/利空哪个板块题材个股，能买吗、踩雷吗、和持仓有没有联动；③风险藏在哪——有没有暗雷（解禁/担保/减持）、高位风险。\\n'
           '【第三步·翻译成人话】术语必须配翻译；打比方优先（击鼓传花/接飞刀/烧到头的鞭炮/装死/开奖日）；结论先行+动作可执行（具体价位/仓位/止损）。\\n'
           '【第四步·套纪律】高位连板一律别追；四重共振不够就「看戏不追」；加仓只加确定性（缩量企稳才算信号）；放量破位止损位给死。\\n'
           '【第五步·自查】结论和逻辑不许矛盾；说机会必须带风险位；能扛住用户反推（说它是政策票，要能答出业绩和位置）。\\n'
           '事件列表：\\n' + evs + '\\n'
           '只输出 JSON，不要任何其他文字：\\n'
           '{"items":[{"t":"事件标题（照抄原文）","impact":"利好/利空哪个板块/题材/个股，至少15字（猜不到写「暂看不出直接关联」，不许编）","logic":"为什么重要/驱动力深挖，至少25字","why":"大白话：一句话戳穿真假+怎么应对，至少22字（必须打比方或术语翻译）","act":"操作：买/躲/看+具体条件（买点/止损/仓位），至少20字"}]}，''',
'''           '【第二步·问三个问题】①为什么重要——驱动是政策、业绩、资金还是纯情绪，给依据；②跟我什么关系——利好/利空哪个板块题材个股，能买吗、踩雷吗、和持仓有没有联动；③风险藏在哪——有没有暗雷（解禁/担保/减持）、高位风险。\\n'
           '【第三步·翻译成人话】术语必须配翻译；打比方优先（击鼓传花/接飞刀/烧到头的鞭炮/装死/开奖日）；结论先行+动作可执行（具体价位/仓位/止损）。\\n'
           '【第四步·套纪律】高位连板一律别追；四重共振不够就「看戏不追」；加仓只加确定性（缩量企稳才算信号）；放量破位止损位给死。\\n'
           '【第五步·自查】结论和逻辑不许矛盾；说机会必须带风险位；能扛住用户反推（说它是政策票，要能答出业绩和位置）。\\n'
           '事件列表：\\n' + evs + '\\n'
           '只输出 JSON，不要任何其他文字：\\n'
           '{"items":[{"t":"事件标题（照抄原文）","good":"✅利好哪个板块/题材/个股+为什么利好，至少12字（确实无明显利好就写「无明显直接利好」，不许编）","bad":"⚠️利空哪个板块/题材/个股+为什么利空，至少12字（确实无明显利空就写「无明显直接利空」，不许编）","logic":"逻辑原因：为什么重要/驱动力深挖，至少25字","why":"大白话：一句话戳穿真假+怎么应对，至少22字（必须打比方或术语翻译）","act":"操作：买/躲/看+具体条件（买点/止损/仓位），至少20字"}]}，''')

# ========== 2. 解析带出 good/bad ==========
rep('''        for it in _j.get('items') or []:
            tt = str(it.get('t') or '').strip()
            if tt and (it.get('logic') or it.get('why')):
                out[tt] = {'impact': str(it.get('impact') or ''),
                           'logic': str(it.get('logic') or ''),
                           'why': str(it.get('why') or ''),
                           'act': str(it.get('act') or '')}''',
'''        for it in _j.get('items') or []:
            tt = str(it.get('t') or '').strip()
            if tt and (it.get('logic') or it.get('why')):
                out[tt] = {'good': str(it.get('good') or ''),
                           'bad': str(it.get('bad') or ''),
                           'logic': str(it.get('logic') or ''),
                           'why': str(it.get('why') or ''),
                           'act': str(it.get('act') or '')}''')

# ========== 3. 渲染：影响行拆成 利好/利空/逻辑 三行 ==========
rep('''            cards.append(f"""<div style="background:#1f2635;border-left:4px solid {x['color']};border-radius:10px;padding:9px 12px;margin:6px 0;">
<div style="font-weight:800;color:{x['color']};">【{x['tag']}】</div>
<div style="color:#fff;font-size:13px;margin-top:3px;">{x['title']}</div>
<div style="color:{TEAL};font-size:12px;margin-top:3px;">影响：{_imp}</div>
<div style="color:#e9ecef;font-size:12px;margin-top:3px;">🧠 逻辑：{_lo}</div>
<div style="color:{GOLD};font-size:12px;margin-top:2px;">👉 大白话：{_wh}</div>
<div style="color:{RED};font-size:12px;margin-top:2px;">💡 操作：{_ac}</div></div>""")''',
'''            _good = _d.get('good') or ''
            _bad = _d.get('bad') or ''
            _good_row = (f'<div style="color:{RED};font-size:12px;margin-top:3px;">✅ 利好：{_good}</div>' if _good else '')
            _bad_row = (f'<div style="color:{GREEN};font-size:12px;margin-top:2px;">⚠️ 利空：{_bad}</div>' if _bad else '')
            cards.append(f"""<div style="background:#1f2635;border-left:4px solid {x['color']};border-radius:10px;padding:9px 12px;margin:6px 0;">
<div style="font-weight:800;color:{x['color']};">【{x['tag']}】</div>
<div style="color:#fff;font-size:13px;margin-top:3px;">{x['title']}</div>
{_good_row}{_bad_row}
<div style="color:#e9ecef;font-size:12px;margin-top:3px;">🧠 逻辑：{_lo}</div>
<div style="color:{GOLD};font-size:12px;margin-top:2px;">👉 大白话：{_wh}</div>
<div style="color:{RED};font-size:12px;margin-top:2px;">💡 操作：{_ac}</div></div>""")''')

io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('OK', cnt['ok'], '替换；失败：')
for f_ in cnt['fail']:
    print('  [%s] 次数=%s 期望=%s' % f_)
