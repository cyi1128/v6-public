# -*- coding: utf-8 -*-
"""修复 _spot_ds 的 format+解析段（旧竖线版残留）。勿重跑。"""
import io
P = r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py'
s = io.open(P, encoding='utf-8').read()
old = """    payload = {
        'task': 'intraday_spot',
        'stocks': stk,
        'format': ('请对下列盘中异动个股逐只点评，每只一行：\\n'
                   '名称（代码）| 最近为什么动（结合kline与board_hist给出最可能原因和依据，一句大白话，直接戳穿真假） | 该不该追（一句）\\n'
                   '数据里看不出的直说「数据看不出明显逻辑」，不许编新闻。'),
    }
    txt = ask_deepseek(payload, purpose='intra_spot', system_text=_SPOT_DS_SYS_text())
    if not txt:
        return {}
    out = {}
    for ln in txt.splitlines():
        ln = ln.strip()
        if '|' in ln:
            nm = ln.split('|')[0].split('（')[0].strip()
            parts = [p.strip() for p in ln.split('|')]
            if nm and len(parts) >= 2:
                out[nm] = parts[1]
    return out"""
new = """    payload = {
        'task': 'intraday_spot',
        'stocks': stk,
        'format': ('请对下列盘中异动个股逐只深挖，严格输出 JSON（不要任何其他文字）：\\n'
                   '{"per":[{"name":"股票名称","logic":"个股逻辑深挖：结合kline与board_hist给出最可能原因和依据，点出有没有暗雷，至少25字","why":"大白话：一句话戳穿真假+该不该追，至少18字","op":"别追/可轻仓/等回踩/持仓不动/先观察"}]}，'
                   'per 必须覆盖每只股票，不许偷懒。数据里看不出的直说「数据看不出明显逻辑」，不许编新闻。'),
    }
    txt = ask_deepseek(payload, purpose='intra_spot', system_text=_SPOT_DS_SYS_text())
    if not txt:
        return {}
    out = {}
    try:
        import json as _json
        _j = _json.loads(txt)
        for it in _j.get('per') or []:
            nm = str(it.get('name') or '').strip().split('（')[0].strip()
            if nm and (it.get('logic') or it.get('why')):
                out[nm] = {'logic': str(it.get('logic') or ''), 'why': str(it.get('why') or ''),
                           'op': str(it.get('op') or '')}
        if out:
            return out
    except Exception:
        pass
    for ln in txt.splitlines():
        ln = ln.strip()
        if '|' in ln:
            nm = ln.split('|')[0].split('（')[0].strip()
            parts = [p.strip() for p in ln.split('|')]
            if nm and len(parts) >= 2:
                out[nm] = {'logic': '', 'why': parts[1], 'op': parts[2] if len(parts) > 2 else ''}
    return out"""
if old not in s:
    print('OLD ANCHOR NOT FOUND')
    raise SystemExit(1)
s = s.replace(old, new)
io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('spot_ds payload+parse fixed')
