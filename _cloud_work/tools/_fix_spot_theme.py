# -*- coding: utf-8 -*-
"""异动提醒题材修复：①单股行业兜底(东财stock/get) ②今日主线名单注入LLM ③'其他'题材热度虚高清零 ④score不虚标。勿重跑。"""
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

# ========== 1. 单股行业兜底函数（插在 _sec_clean 之后） ==========
rep("def _SPOT_DS_SYS_text():",
    """def _stock_industry(code):
    \"\"\"单股行业兜底：东财 stock/get 接口取行业(f127)。sec='其他'/空 时用，失败返回 ''。\"\"\"
    try:
        mk = '1' if str(code).startswith('6') else '0'
        url = ('https://push2.eastmoney.com/api/qt/stock/get?secid=' + mk + '.' + str(code)
               + '&fields=f57,f58,f127')
        txt, ok = _getm(url, 'stock_ind')
        if ok and txt:
            dd = json.loads(txt).get('data') or {}
            ind = str(dd.get('f127') or '').strip()
            if ind:
                return _sec_clean(ind) or ''
    except Exception:
        pass
    return ''


def _today_top(d):
    \"\"\"今日主线名单：涨停板块 TOP6 + 题材热度 TOP，去重拼接。供单股卡判断主线归属。\"\"\"
    names = []
    for sec in (d.get('sectors') or {}).keys():
        if sec not in names:
            names.append(sec)
    for nm in (d.get('themes') or {}).keys():
        if nm not in names:
            names.append(nm)
    return '、'.join(names[:6]) or '（今日暂无明确主线）'


def _SPOT_DS_SYS_text():""")

# ========== 2. _theme_heat '其他' 桶清零 ==========
rep("""    for sec, lst in grp.items():
        cnt[sec] = len(lst)
        avg_gap = sum(x['pct'] for x in lst) / max(len(lst), 1)
        strong = sum(1 for x in lst if x['pct'] >= (4 if (x.get('board') or ('gem' if x['code'].startswith('300') else 'main')) == 'gem' else 2)) / max(len(lst), 1)
        heat[sec] = min(100.0, avg_gap / 8.0 * 50 + strong * 50)
    return heat, cnt""",
    """    for sec, lst in grp.items():
        cnt[sec] = len(lst)
        if sec in ('其他', '热点方向'):
            heat[sec] = 0.0    # 无题材信息的杂毛桶不虚标热度
            continue
        avg_gap = sum(x['pct'] for x in lst) / max(len(lst), 1)
        strong = sum(1 for x in lst if x['pct'] >= (4 if (x.get('board') or ('gem' if x['code'].startswith('300') else 'main')) == 'gem' else 2)) / max(len(lst), 1)
        heat[sec] = min(100.0, avg_gap / 8.0 * 50 + strong * 50)
    return heat, cnt""")

# ========== 3. _SPOT_DS_SYS_text 加主线归属要求 ==========
rep("""            '核心任务：回答「为什么是它被选中」——多因素交叉（主线归属/板块共振/资金逻辑/位置预期差），禁止单条件结论。'
            '数据不足以判断就直说「数据看不出明显逻辑」，不许编新闻猜消息。禁止满仓/必涨/稳了。'""",
    """            '核心任务：回答「为什么是它被选中」——多因素交叉（主线归属/板块共振/资金逻辑/位置预期差），禁止单条件结论。'
            '【主线归属硬要求】我会给你 today_top（今日真实主线名单），先判断这只票属不属于今日主线/与主线沾不沾边，'
            '再判断是主线内的补涨/龙头扩散，还是完全在主线外的孤军：不许只会说「题材不明」——'
            '就算行业标签缺失，也要结合涨幅榜给的方向（如医药/机器人/算力哪个在领涨）判断它更接近哪一簇，'
            '确实一点线索都没有才如实写「数据看不出它属于哪个方向」。'
            '数据不足以判断就直说「数据看不出明显逻辑」，不许编新闻猜消息。禁止满仓/必涨/稳了。'""")

# ========== 4. _spot_ds payload 注入 today_top ==========
rep("""def _spot_ds(sgs, mem=None, days=None):
    \"\"\"单股异动卡 DeepSeek 大白话（深度挖掘版）：一次调用喂本次所有信号卡，每只附K线近况+板块历史。
    返回 {name: 大白话}；失败/用尽返回 {}（模板降级）。\"\"\"
    if not sgs:
        return {}""",
    """def _spot_ds(sgs, mem=None, days=None, today_top=''):
    \"\"\"单股异动卡 DeepSeek 大白话（深度挖掘版）：一次调用喂本次所有信号卡，每只附K线近况+板块历史+今日主线。
    返回 {name: 大白话}；失败/用尽返回 {}（模板降级）。\"\"\"
    if not sgs:
        return {}""")

rep("""    payload = {
        'task': 'intraday_spot',
        'stocks': stk,
        'format': ('请对下列盘中异动个股逐只深挖，严格输出 JSON（不要任何其他文字）：\\n'
                   '{"per":[{"name":"股票名称","logic":"个股逻辑深挖：结合kline与board_hist给出最可能原因和依据，点出有没有暗雷，至少25字","why":"大白话：一句话戳穿真假+该不该追，至少18字","op":"别追/看/轻仓试/观望——必须与logic结论完全一致，看空就给别追，禁止矛盾","buy":"买点具体条件，op=别追时写今日无买点","stop":"止损具体条件，op=别追时写无"}]}，'
                   'per 必须覆盖每只股票，不许偷懒。数据里看不出的直说「数据看不出明显逻辑」，不许编新闻。'),
    }""",
    """    payload = {
        'task': 'intraday_spot',
        'stocks': stk,
        'today_top': today_top or '（今日暂无明确主线）',
        'format': ('请对下列盘中异动个股逐只深挖，严格输出 JSON（不要任何其他文字）：\\n'
                   '今日主线名单：' + (today_top or '（今日暂无明确主线）') + '。\\n'
                   '每只先判断属不属于这条主线（是主线内补涨/龙头扩散，还是主线外孤军），再深挖逻辑；'
                   '行业标签缺失时也按涨幅榜方向猜最近的一簇，确实无线索才写「数据看不出方向」。\\n'
                   '{"per":[{"name":"股票名称","logic":"个股逻辑深挖：先答主线归属（属不属于today_top主线/最接近哪簇），再结合kline与board_hist给出最可能原因和依据，点出有没有暗雷，至少25字","why":"大白话：一句话戳穿真假+该不该追，至少18字","op":"别追/看/轻仓试/观望——必须与logic结论完全一致，看空就给别追，禁止矛盾","buy":"买点具体条件，op=别追时写今日无买点","stop":"止损具体条件，op=别追时写无"}]}，'
                   'per 必须覆盖每只股票，不许偷懒。数据里看不出的直说「数据看不出明显逻辑」，不许编新闻。'),
    }""")

# ========== 5. sg 构造处 sec 兜底 + score 不虚标 ==========
rep("""    for s in ambush[:4]:
        key = f"{s['name']}|埋伏"
        if key in fired:
            continue
        heat = _theme_heat([s])[0].get(s['sec_clean'], 0)
        sg = {'n': s['name'], 'code': s['code'], 'type': '启动埋伏', 'price': s.get('price'),
              'sec': s['sec_clean'], 'pct': s['pct'], 'lb': s['lb'], 'turn': s['turn'], 'score': round(min(10.0, heat / 10.0), 1),""",
    """    for s in ambush[:4]:
        key = f"{s['name']}|埋伏"
        if key in fired:
            continue
        if not s['sec_clean'] or s['sec_clean'] == '其他':
            _fix = _stock_industry(s.get('code') or '')
            if _fix:
                s['sec_clean'] = _fix
        heat = _theme_heat([s])[0].get(s['sec_clean'], 0)
        sg = {'n': s['name'], 'code': s['code'], 'type': '启动埋伏', 'price': s.get('price'),
              'sec': s['sec_clean'], 'pct': s['pct'], 'lb': s['lb'], 'turn': s['turn'],
              'score': round(min(10.0, (heat / 10.0 if heat else 0.0)), 1),""")

rep("""    for s in near[:4]:
        key = f"{s['name']}|逼近"
        if key in fired:
            continue
        heat = _theme_heat([s])[0].get(s['sec_clean'], 0)
        strong = s['lb'] >= 1.8
        sg = {'n': s['name'], 'code': s['code'], 'type': '逼近涨停', 'price': s.get('price'),
              'sec': s['sec_clean'], 'pct': s['pct'], 'lb': s['lb'], 'turn': s['turn'], 'score': round(min(10.0, heat / 10.0), 1),""",
    """    for s in near[:4]:
        key = f"{s['name']}|逼近"
        if key in fired:
            continue
        if not s['sec_clean'] or s['sec_clean'] == '其他':
            _fix = _stock_industry(s.get('code') or '')
            if _fix:
                s['sec_clean'] = _fix
        heat = _theme_heat([s])[0].get(s['sec_clean'], 0)
        strong = s['lb'] >= 1.8
        sg = {'n': s['name'], 'code': s['code'], 'type': '逼近涨停', 'price': s.get('price'),
              'sec': s['sec_clean'], 'pct': s['pct'], 'lb': s['lb'], 'turn': s['turn'],
              'score': round(min(10.0, (heat / 10.0 if heat else 0.0)), 1),""")

# ========== 6. 调用处传 today_top ==========
rep("""    ds_plain = _spot_ds([sg for _, sg in sel], mem, days) if sel else {}""",
    """    ds_plain = _spot_ds([sg for _, sg in sel], mem, days, today_top=_today_top(d)) if sel else {}""")

io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('OK', cnt['ok'], '替换；失败：')
for f_ in cnt['fail']:
    print('  [%s] 次数=%s 期望=%s' % f_)
