# -*- coding: utf-8 -*-
"""一次性补丁：每条新闻解读加「代表个股深挖」要素（五元组 t,i,s,w,a）。
渲染新增 🏆 代表个股 行（在 🎯影响 之后）。勿重跑。"""
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

# 1. _parse_ds_json → 五元组 (t, i, s, w, a)
rep("""                out.append((str(it.get('t') or it.get('title')),
                            str(it.get('i') or it.get('impact') or ''),
                            str(it.get('w') or it.get('p') or it.get('note') or ''),
                            str(it.get('a') or it.get('op') or '')))""",
    """                out.append((str(it.get('t') or it.get('title')),
                            str(it.get('i') or it.get('impact') or ''),
                            str(it.get('s') or it.get('stock') or ''),
                            str(it.get('w') or it.get('p') or it.get('note') or ''),
                            str(it.get('a') or it.get('op') or '')))""")

# 2. _news_ds_lines prompt 加 s 字段（代表个股深挖）
rep("""           '{"items":[{"t":"消息标题","i":"影响：写清板块/题材/代表性个股，至少20字（猜不到写「暂看不出直接关联」，不许编）","w":"大白话：一句话戳穿真假+为什么+怎么传导，至少25字","a":"操作：买/躲/看，写具体怎么应对（价位/条件/仓位），至少20字"}]}\\n'""",
    """           '{"items":[{"t":"消息标题","i":"影响：写清板块/题材，至少15字（猜不到写「暂看不出直接关联」，不许编）","s":"代表个股深挖：点名1-2只能代表这条消息的股票代码+名称，深挖它自己的逻辑（业绩/催化/位置/为什么它能代表），至少30字，不许泛泛而谈","w":"大白话：一句话戳穿真假+为什么+怎么传导，至少25字","a":"操作：买/躲/看，写具体怎么应对（价位/条件/仓位），至少20字"}]}\\n'""")

# 3. 校验扩展 s 字段
rep("""        for _try in range(2):
            bad_row = [it for it in pairs
                       if len(it[1]) < 12 or len(it[2]) < 12 or len(it[3]) < 10]""",
    """        for _try in range(2):
            bad_row = [it for it in pairs
                       if len(it[1]) < 12 or (len(it) >= 5 and len(it[2]) < 20) or len(it[3]) < 12 or len(it[4]) < 10]""")

# 4. 标题覆盖五元组
rep("                pairs[k] = (brief[k]['t'], it[1], it[2], it[3])",
    "                pairs[k] = (brief[k]['t'], it[1], it[2], it[3], it[4])")

# 5. _news_html_lines 渲染加 🏆 行 + 五元组展开
rep("""            t0 = it[0]
            i, w, a = (it[1], it[2], it[3]) if len(it) >= 4 else ('', it[1] if len(it) > 1 else '', '')
            i = _strip_pre(i, ('影响：', '影响:'))
            w = _strip_pre(w, ('大白话：', '大白话:', '人话：', '解读：'))
            a = _strip_pre(a, ('操作：', '操作:'))
            _sum = _brief_sum.get(t0, '')
            rows.append(f'<div style=\"color:#ced4da;font-size:12px;margin:8px 0 0 0;\">· {t0}</div>'
                        + (f'<div style=\"margin:2px 0 0 16px;color:{GREY};font-size:11px;\">📰 {_sum}</div>' if _sum else '')
                        + (f'<div style=\"margin:2px 0 0 16px;color:{GOLD};font-size:12px;\">🎯 影响：{i}</div>' if i else '')
                        + (f'<div style=\"margin:2px 0 0 16px;color:{TEAL};font-size:12px;\">🧠 大白话：{w}</div>' if w else '')
                        + (f'<div style=\"margin:2px 0 8px 16px;color:{RED};font-size:12px;\">💡 操作：{a}</div>' if a else ''))""",
    """            t0 = it[0]
            i, s2, w, a = (it[1], it[2], it[3], it[4]) if len(it) >= 5 else (it[1], '', it[2] if len(it) > 2 else '', it[3] if len(it) > 3 else '')
            i = _strip_pre(i, ('影响：', '影响:'))
            s2 = _strip_pre(s2, ('代表个股：', '代表个股:', '个股：', '个股:'))
            w = _strip_pre(w, ('大白话：', '大白话:', '人话：', '解读：'))
            a = _strip_pre(a, ('操作：', '操作:'))
            _sum = _brief_sum.get(t0, '')
            rows.append(f'<div style=\"color:#ced4da;font-size:12px;margin:8px 0 0 0;\">· {t0}</div>'
                        + (f'<div style=\"margin:2px 0 0 16px;color:{GREY};font-size:11px;\">📰 {_sum}</div>' if _sum else '')
                        + (f'<div style=\"margin:2px 0 0 16px;color:{GOLD};font-size:12px;\">🎯 影响：{i}</div>' if i else '')
                        + (f'<div style=\"margin:2px 0 0 16px;color:#b197fc;font-size:12px;\">🏆 代表个股：{s2}</div>' if s2 else '')
                        + (f'<div style=\"margin:2px 0 0 16px;color:{TEAL};font-size:12px;\">🧠 大白话：{w}</div>' if w else '')
                        + (f'<div style=\"margin:2px 0 8px 16px;color:{RED};font-size:12px;\">💡 操作：{a}</div>' if a else ''))""")

# 6. build_news2h._rows 同样加 🏆 行
rep("""        for it in pairs:
            t0 = it[0]
            i, w, a = (it[1], it[2], it[3]) if len(it) >= 4 else ('', it[1] if len(it) > 1 else '', '')
            i = _strip_pre(i, ('影响：', '影响:'))
            w = _strip_pre(w, ('大白话：', '大白话:', '人话：', '解读：'))
            a = _strip_pre(a, ('操作：', '操作:'))
            _sum = _brief_sum.get(t0, '')
            out.append(f'<div style=\"color:#fff;font-size:13px;margin:8px 0 0 0;\">· {t0}</div>'
                       + (f'<div style=\"margin:2px 0 0 16px;color:{GREY};font-size:11px;\">📰 {_sum}</div>' if _sum else '')
                       + (f'<div style=\"margin:2px 0 0 16px;color:{GOLD};font-size:12px;\">🎯 影响：{i}</div>' if i else '')
                       + (f'<div style=\"margin:2px 0 0 16px;color:{TEAL};font-size:12px;\">🧠 大白话：{w}</div>' if w else '')
                       + (f'<div style=\"margin:2px 0 8px 16px;color:{RED};font-size:12px;\">💡 操作：{a}</div>' if a else ''))""",
    """        for it in pairs:
            t0 = it[0]
            i, s2, w, a = (it[1], it[2], it[3], it[4]) if len(it) >= 5 else (it[1], '', it[2] if len(it) > 2 else '', it[3] if len(it) > 3 else '')
            i = _strip_pre(i, ('影响：', '影响:'))
            s2 = _strip_pre(s2, ('代表个股：', '代表个股:', '个股：', '个股:'))
            w = _strip_pre(w, ('大白话：', '大白话:', '人话：', '解读：'))
            a = _strip_pre(a, ('操作：', '操作:'))
            _sum = _brief_sum.get(t0, '')
            out.append(f'<div style=\"color:#fff;font-size:13px;margin:8px 0 0 0;\">· {t0}</div>'
                       + (f'<div style=\"margin:2px 0 0 16px;color:{GREY};font-size:11px;\">📰 {_sum}</div>' if _sum else '')
                       + (f'<div style=\"margin:2px 0 0 16px;color:{GOLD};font-size:12px;\">🎯 影响：{i}</div>' if i else '')
                       + (f'<div style=\"margin:2px 0 0 16px;color:#b197fc;font-size:12px;\">🏆 代表个股：{s2}</div>' if s2 else '')
                       + (f'<div style=\"margin:2px 0 0 16px;color:{TEAL};font-size:12px;\">🧠 大白话：{w}</div>' if w else '')
                       + (f'<div style=\"margin:2px 0 8px 16px;color:{RED};font-size:12px;\">💡 操作：{a}</div>' if a else ''))""")

io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('OK', cnt['ok'], '替换；失败：')
for f_ in cnt['fail']:
    print('  [%s] 次数=%s 期望=%s' % f_)
