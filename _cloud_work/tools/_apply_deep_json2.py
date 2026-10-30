# -*- coding: utf-8 -*-
"""一次性补丁part2：涨停新进卡 _intra_ds / _intra_parse_ds 改 JSON + 深挖渲染。勿重跑。"""
import io

P = r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py'
s = io.open(P, encoding='utf-8').read()
cnt = {'ok': 0, 'fail': []}

def rep(old, new, must=1):
    global s
    n = s.count(old)
    if n != must:
        cnt['fail'].append((old[:70].replace('\n', '\\n'), n, must))
        return
    s = s.replace(old, new)
    cnt['ok'] += 1

# ========== 4. _INTRA_DS_SYS_text 输出改 JSON ==========
rep("""            '4. 禁止万能句（「回踩分时均线可轻仓试」「观察为主不急着追」「量能不配合不动手」）及任何变体；'
               '数据不足以支撑推荐就直说「今日无强推，别碰」，禁止凑数硬夸。'
            '4. 严格按下面格式输出，不要多余解释：\\n'
            '【情绪】一句话说情绪+能不能追\\n'
            '【个股】\\n名称（代码）| 为什么涨（一句大白话，戳穿真假） | 操作 | 买点 | 止损\\n'
            '（每只新进票一行，没把握的也如实说）\\n'
            '【主线】一句话：今天最强方向+还能不能跟\\n'
            '【风险】一句话：最大风险+什么情况立刻撤')""",
    """            '4. 禁止万能句（「回踩分时均线可轻仓试」「观察为主不急着追」「量能不配合不动手」）及任何变体；'
               '数据不足以支撑推荐就直说「今日无强推，别碰」，禁止凑数硬夸。'
            '4. 只输出 JSON，不要任何其他文字：\\n'
            '{"overall":"情绪一句话+能不能追","mainline":"今日最强方向+还能不能跟","risk":"最大风险+什么情况立刻撤","per":[{"name":"股票名称","logic":"个股逻辑深挖：为什么涨（真消息还是纯情绪/板块合力还是个股逻辑/有没有暗雷），至少25字，不许泛泛而谈","why":"大白话：一句话戳穿真假，至少18字","op":"别追/看/轻仓试/观望","buy":"买点具体条件","stop":"止损具体"}]}，'
            'per 必须覆盖每只新进票，没把握的也如实说。')""")

# ========== 5. _intra_ds format 改 JSON ==========
rep("""        'format': ('以下是涨停池实时快照。请严格按你的输出格式逐只点评 new_stocks 里的每只票'
                   '（为什么涨、操作、买点、止损），并给情绪/主线/风险。数据看不出的直接说看不出来。'),""",
    """        'format': ('以下是涨停池实时快照。严格输出 JSON（不要任何其他文字）：\\n'
                   '{"overall":"情绪一句话+能不能追","mainline":"今日最强方向+还能不能跟","risk":"最大风险+什么情况立刻撤","per":[{"name":"股票名称","logic":"个股逻辑深挖：为什么涨（真消息还是纯情绪/板块合力还是个股逻辑/有没有暗雷），至少25字","why":"大白话：一句话戳穿真假，至少18字","op":"别追/看/轻仓试/观望","buy":"买点具体条件","stop":"止损具体"}]}，'
                   'per 必须覆盖每只新进票，没把握的也如实说。数据看不出的直接说看不出来。'),""")

# ========== 6. _intra_parse_ds 优先 JSON（回退竖线） ==========
rep("""def _intra_parse_ds(txt, names):
    \"\"\"解析 DS 输出：【情绪】/【个股】行(名称|大白话|操作|买点|止损)/【主线】/【风险】。\"\"\"
    out = {'overall': None, 'per': {}, 'mainline': None, 'risk': None}
    names_set = set(names)
    for ln in txt.splitlines():""",
    """def _intra_parse_ds(txt, names):
    \"\"\"解析 DS 输出：优先 JSON（overall/mainline/risk/per[logic,why,op,buy,stop]），回退【情绪】/竖线行。\"\"\"
    out = {'overall': None, 'per': {}, 'mainline': None, 'risk': None}
    names_set = set(names)
    try:
        import json as _json
        _j = _json.loads(txt)
        out['overall'] = str(_j.get('overall') or '') or None
        out['mainline'] = str(_j.get('mainline') or '') or None
        out['risk'] = str(_j.get('risk') or '') or None
        for it in _j.get('per') or []:
            nm = str(it.get('name') or '').strip()
            nm = nm.split('（')[0].strip()
            if nm in names_set:
                out['per'][nm] = {'logic': str(it.get('logic') or ''), 'why': str(it.get('why') or ''),
                                  'op': str(it.get('op') or ''), 'buy': str(it.get('buy') or ''),
                                  'stop': str(it.get('stop') or '')}
        return out
    except Exception:
        pass
    for ln in txt.splitlines():""")

# ========== 7. 竖线回退解析兼容 dict 值 ==========
rep("""                parts = [p.strip() for p in ln.split('|')]
                if len(parts) >= 5:
                    out['per'][nm] = {'why': parts[1], 'op': parts[2], 'buy': parts[3], 'stop': parts[4]}""",
    """                parts = [p.strip() for p in ln.split('|')]
                if len(parts) >= 5:
                    out['per'][nm] = {'logic': '', 'why': parts[1], 'op': parts[2], 'buy': parts[3], 'stop': parts[4]}""")

# ========== 8. 涨停卡渲染：per dict 加 🧠 个股逻辑 行 ==========
rep("""            if dsp:
                why, op, buy, stop = dsp['why'], dsp['op'], dsp['buy'], dsp['stop']
                op_col = TEAL if op in ('轻仓', '轻仓试', '看') else (GOLD if op in ('观望', '持仓不动') else RED)""",
    """            if dsp:
                why, op, buy, stop = (dsp.get('why') or ''), (dsp.get('op') or ''), (dsp.get('buy') or ''), (dsp.get('stop') or '')
                op_col = TEAL if op in ('轻仓', '轻仓试', '看') else (GOLD if op in ('观望', '持仓不动') else RED)
                if not (why or op or buy or stop):
                    dsp = None""")

rep("""            dsp = ds.get('per', {}).get(name) if ds else None
        if dsp:""",
    """            dsp = ds.get('per', {}).get(name) if ds else None
            _logic = (dsp.get('logic') or '') if isinstance(dsp, dict) else ''
        if dsp:""")

rep("""        rows.append(
            '<div style=\"background:#1f2635;border-left:3px solid ' + op_col + ';border-radius:8px;padding:8px 10px;margin:6px 0;\">'
            + '<div style=\"font-size:13px;font-weight:700;color:#fff;\">' + name + '（' + code + '）｜' + sec + '｜<span style=\"color:' + RED + ';\">' + lb_txt + '</span>' + fbt_txt + '</div>'
            + '<div style=\"color:' + GREY + ';font-size:12px;\">👉 ' + ('AI 大白话' if dsp else '大白话') + '：' + why + '。</div>'
            + '<div style=\"color:#ced4da;font-size:12px;\">操作：<b style=\"color:' + op_col + ';\">' + op + '</b> ｜ 买点：' + buy + ' ｜ 止损：' + stop + '</div></div>')""",
    """        rows.append(
            '<div style=\"background:#1f2635;border-left:3px solid ' + op_col + ';border-radius:8px;padding:8px 10px;margin:6px 0;\">'
            + '<div style=\"font-size:13px;font-weight:700;color:#fff;\">' + name + '（' + code + '）｜' + sec + '｜<span style=\"color:' + RED + ';\">' + lb_txt + '</span>' + fbt_txt + '</div>'
            + (('<div style=\"color:' + TEAL + ';font-size:12px;margin-top:2px;\">🧠 个股逻辑：' + _logic + '</div>') if _logic else '')
            + '<div style=\"color:' + GREY + ';font-size:12px;\">👉 ' + ('AI 大白话' if dsp else '大白话') + '：' + why + '。</div>'
            + '<div style=\"color:#ced4da;font-size:12px;\">操作：<b style=\"color:' + op_col + ';\">' + op + '</b> ｜ 买点：' + buy + ' ｜ 止损：' + stop + '</div></div>')""")

io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('OK', cnt['ok'], '替换；失败：')
for f_ in cnt['fail']:
    print('  [%s] 次数=%s 期望=%s' % f_)
