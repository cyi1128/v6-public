# -*- coding: utf-8 -*-
"""一次性补丁：盘中异动两个 LLM 通道改 JSON 输出 + 个股逻辑深挖。
①单股卡 _spot_ds ②涨停新进卡 _intra_ds。渲染加「🧠 个股逻辑」行。勿重跑。"""
import io, json

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

# ========== 1. _SPOT_DS_SYS_text 输出改 JSON（含逻辑深挖字段） ==========
rep("""            '6.敢下判断：数据不足以支撑就直说「今日无强推，别碰」，不许为了凑数硬夸。7.格式：每只一行：\\n'
            '名称（代码）| 最近为什么动（一句大白话，含最可能原因和依据） | 该不该追（一句）')""",
    """            '6.敢下判断：数据不足以支撑就直说「今日无强推，别碰」，不许为了凑数硬夸。'
            '7.只输出 JSON，不要任何其他文字：\\n'
            '{"per":[{"name":"股票名称","logic":"个股逻辑深挖：最近异动最可能的原因+依据（放量突破/板块共振/连板情绪/超跌反弹/高位出货嫌疑），并点出有没有暗雷，至少25字，不许泛泛而谈","why":"大白话：一句话戳穿真假+该不该追，至少18字，禁止万能句"}]}，'
            'per 必须覆盖我给的全部股票。')""")

# ========== 2. _spot_ds format 改 JSON + 解析改 JSON（回退竖线） ==========
rep("""    payload = {
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
    return out""",
    """    payload = {
        'task': 'intraday_spot',
        'stocks': stk,
        'format': ('请对下列盘中异动个股逐只深挖，严格输出 JSON：\\n'
                   '{"per":[{"name":"股票名称","logic":"个股逻辑深挖：结合kline与board_hist给出最可能原因和依据，点出有没有暗雷，至少25字","why":"大白话：一句话戳穿真假+该不该追，至少18字","op":"别追/可轻仓/等回踩/持仓不动/先观察"}]}，'
                   'per 必须覆盖每只股票，不许偷懒。数据里看不出的直说「数据看不出明显逻辑」，不许编新闻。'),
    }
    txt = ask_deepseek(payload, purpose='intra_spot', system_text=_SPOT_DS_SYS_text())
    if not txt:
        return {}
    out = {}
    try:
        _j = json.loads(txt)
        for it in _j.get('per') or []:
            nm = str(it.get('name') or '').strip()
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
    return out""")

# ========== 3. _watch_card 渲染：ds_plain 为 dict 时显示 🧠 逻辑 + 👉 大白话 两行 ==========
rep("""    _dsp = (ds_plain or {}).get(sg['n'])
    if _dsp:
        why_txt, ai_tag = _dsp, 'AI 大白话'
    else:
        why_txt, ai_tag = sg.get('why', ''), '大白话'
    return f\"\"\"<div style=\"background:#2a1518;border:2px solid {RED};border-radius:12px;padding:12px 14px;margin:10px 0;\">
<div style=\"font-size:17px;font-weight:900;color:{RED};\">⚡ {sg['n']}（{sg['code']}）· {sg['type']} <span style=\"background:{st_color};color:#161b26;border-radius:6px;padding:1px 8px;font-size:12px;font-weight:700;\">{st_lv}级·{st_txt}</span></div>
<div style=\"color:#fff;font-size:13px;margin-top:6px;\">所属题材：{sg['sec']}｜得分 <b style=\"color:{GOLD}\">{sg['score']}/10</b>{sg.get('life', '')}</div>
<div style=\"color:#e9ecef;font-size:13px;margin-top:6px;background:#1f2635;border-radius:8px;padding:8px 10px;\">🧠 {ai_tag}：{why_txt}</div>\"\"\"""",
    """    _dsp = (ds_plain or {}).get(sg['n'])
    if isinstance(_dsp, dict):
        _logic = _dsp.get('logic', '')
        _why = _dsp.get('why', '')
        _op_ai = _dsp.get('op', '')
        _logic_html = ('<div style=\"color:' + TEAL + ';font-size:12px;margin-top:4px;\">🧠 个股逻辑：' + _logic + '</div>') if _logic else ''
        _why_html = ('<div style=\"color:#e9ecef;font-size:12px;margin-top:2px;\">👉 大白话：' + _why + ('（' + _op_ai + '）' if _op_ai else '') + '</div>') if _why else ''
        _ai_block = _logic_html + _why_html
    else:
        _why = _dsp if _dsp else sg.get('why', '')
        _ai_block = ('<div style=\"color:#e9ecef;font-size:12px;margin-top:2px;\">👉 大白话：' + _why + '</div>') if _why else ''
    return f\"\"\"<div style=\"background:#2a1518;border:2px solid {RED};border-radius:12px;padding:12px 14px;margin:10px 0;\">
<div style=\"font-size:17px;font-weight:900;color:{RED};\">⚡ {sg['n']}（{sg['code']}）· {sg['type']} <span style=\"background:{st_color};color:#161b26;border-radius:6px;padding:1px 8px;font-size:12px;font-weight:700;\">{st_lv}级·{st_txt}</span></div>
<div style=\"color:#fff;font-size:13px;margin-top:6px;\">所属题材：{sg['sec']}｜得分 <b style=\"color:{GOLD}\">{sg['score']}/10</b>{sg.get('life', '')}</div>
{_ai_block}\"\"\"""")
