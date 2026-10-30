# -*- coding: utf-8 -*-
"""_watch_card 整卡统一跟随 LLM op。勿重跑。"""
import io
P = r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py'
s = io.open(P, encoding='utf-8').read()
cnt = {'ok': 0, 'fail': []}

def rep(old, new, must=1):
    global s
    n = s.count(old)
    if n != must:
        cnt['fail'].append((old[:50].replace('\n', '\\n'), n, must))
        return
    s = s.replace(old, new)
    cnt['ok'] += 1

# 1) _dsp 块 → LLM 优先统一结论
rep("""    _dsp = (ds_plain or {}).get(sg['n'])
    if isinstance(_dsp, dict):
        _logic = _dsp.get('logic', '')
        _why = _dsp.get('why', '')
        _op_ai = _dsp.get('op', '')
        _logic_html = ('<div style="color:' + TEAL + ';font-size:12px;margin-top:4px;">🧠 个股逻辑：' + _logic + '</div>') if _logic else ''
        _why_html = ('<div style="color:#e9ecef;font-size:12px;margin-top:2px;">👉 大白话：' + _why + ('（' + _op_ai + '）' if _op_ai else '') + '</div>') if _why else ''
        _ai_block = _logic_html + _why_html
    else:
        _why = _dsp if _dsp else sg.get('why', '')
        _ai_block = ('<div style="color:#e9ecef;font-size:12px;margin-top:2px;">👉 大白话：' + _why + '</div>') if _why else ''""",
    """    _dsp = (ds_plain or {}).get(sg['n'])
    _llm_ok = isinstance(_dsp, dict) and bool(_dsp.get('op'))
    if _llm_ok:
        _logic = _dsp.get('logic', '')
        _why = _dsp.get('why', '')
        _op_ai = _dsp.get('op', '')
        _buy_ai = _dsp.get('buy', '')
        _stop_ai = _dsp.get('stop', '')
        _om = {'别追': ('别追（今日无强推）', GREY, '空仓 0', '今日无买点（不参与）', '无（不参与）', ''),
               '看': ('观望为主', GOLD, '0-1成', '今日无买点，等放量企稳信号', '无（不参与）', ''),
               '观望': ('观望为主', GOLD, '0-1成', '今日无买点，等板块放量信号', '无（不参与）', ''),
               '轻仓试': ('可轻仓试', TEAL, '1-2成', _buy_ai or '回踩分时均线企稳再试', _stop_ai or '破-3%无条件止损', t_tgt)}
        if _op_ai in _om:
            _head_txt, _head_col, _pos_txt, _buy_txt, _stop_txt, _t_tgt2 = _om[_op_ai]
            st_color = _head_col
            _act_txt = _head_txt.split('（')[0]
        else:
            _head_txt, _pos_txt, _buy_txt, _stop_txt, _act_txt, _t_tgt2 = (
                st_txt, sg.get('pos', '1-2成'),
                f"{sg.get('buy_low', '—')} ~ {sg.get('buy_high', '—')}",
                sg.get('stop', '破位-3%走'), sg.get('act', '观察'), t_tgt)
        _logic_html = ('<div style="color:' + TEAL + ';font-size:12px;margin-top:4px;">🧠 个股逻辑：' + _logic + '</div>') if _logic else ''
        _why_html = ('<div style="color:#e9ecef;font-size:12px;margin-top:2px;">👉 大白话：' + _why + '</div>') if _why else ''
        _ai_block = _logic_html + _why_html
    else:
        _head_txt, _pos_txt, _buy_txt, _stop_txt, _act_txt, _t_tgt2 = (
            st_txt, sg.get('pos', '1-2成'),
            f"{sg.get('buy_low', '—')} ~ {sg.get('buy_high', '—')}",
            sg.get('stop', '破位-3%走'), sg.get('act', '观察'), t_tgt)
        _why = _dsp if _dsp else sg.get('why', '')
        _ai_block = ('<div style="color:#e9ecef;font-size:12px;margin-top:2px;">👉 大白话：' + _why + '</div>') if _why else ''
    _t_line = (f'🎯 做T思路：{_t_tgt2} 附近可先出一半，留一半看能否冲击涨停。<br>🚫 若直接冲涨停：不追，等回封或明天。<br>'
               if _t_tgt2 else '')""")

# 2) 头部行
rep("""<div style="font-size:17px;font-weight:900;color:{RED};">⚡ {sg['n']}（{sg['code']}）· {sg['type']} <span style="background:{st_color};color:#161b26;border-radius:6px;padding:1px 8px;font-size:12px;font-weight:700;">{st_lv}级·{st_txt}</span></div>""",
    """<div style="font-size:17px;font-weight:900;color:{RED};">⚡ {sg['n']}（{sg['code']}）· {sg['type']} <span style="background:{st_color};color:#161b26;border-radius:6px;padding:1px 8px;font-size:12px;font-weight:700;">{_head_txt}</span></div>""")

# 3) 价/止损/操作/做T/风险行
rep("""<div style="color:{TEAL};font-size:13px;margin-top:6px;">💰 当前价 <b>{sg.get('cur', '—')}</b> ｜ 建议买入区间 <b style="color:{GOLD}">{sg.get('buy_low', '—')} ~ {sg.get('buy_high', '—')}</b>（回踩分时均线附近）</div>
<div style="color:{GREEN};font-size:13px;margin-top:3px;">🛑 止损 <b>{sg.get('stop', '破位-3%走')}</b></div>
<div style="color:{TEAL};font-size:13px;margin-top:4px;"><b>操作：{sg['act']}</b>｜仓位建议 <b>{sg['pos']}</b></div>
<div style="color:#ced4da;font-size:12px;margin-top:6px;border-top:1px dashed #444;padding-top:6px;">
🎯 做T思路：{t_tgt} 附近可先出一半，留一半看能否冲击涨停。<br>
🚫 若直接冲涨停：不追，等回封或明天。<br>
⚠️ 风险：{risk} 市场适配度：{fit}</div></div>\"\"\"""",
    """<div style="color:{TEAL};font-size:13px;margin-top:6px;">💰 当前价 <b>{sg.get('cur', '—')}</b> ｜ 建议买入区间 <b style="color:{GOLD}">{_buy_txt}</b></div>
<div style="color:{GREEN};font-size:13px;margin-top:3px;">🛑 止损 <b>{_stop_txt}</b></div>
<div style="color:{TEAL};font-size:13px;margin-top:4px;"><b>操作：{_act_txt}</b>｜仓位建议 <b>{_pos_txt}</b></div>
<div style="color:#ced4da;font-size:12px;margin-top:6px;border-top:1px dashed #444;padding-top:6px;">
{_t_line}⚠️ 风险：{risk} 市场适配度：{fit}</div></div>\"\"\"""")

io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('OK', cnt['ok'], '替换；失败：')
for f_ in cnt['fail']:
    print('  [%s] 次数=%s 期望=%s' % f_)
