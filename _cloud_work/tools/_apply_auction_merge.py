# -*- coding: utf-8 -*-
"""build_auction 加「竞价实盘确认」段（合并原 09:28 竞价确认），并拼进 inner。勿重跑。"""
import io
P = r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py'
s = io.open(P, encoding='utf-8').read()

A1 = '''    inner = (overall + f'<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">🔔 持仓竞价诊断（先看自己的）</div>'
             + (''.join(own) or '<div style="color:' + GREY + ';font-size:13px;">无持仓</div>')
             + pick + wind + pos_cap_line(emotion, None))
    return _wrap(inner, '🔔', '竞价观察')'''

NEW_A1 = '''    # —— 竞价实盘确认（合并原 09:28：同一推送里直接复核高开/量能，数据同时点更可靠）——
    _confirm_block = ''
    try:
        _cinfos, _crows = [], []
        for s in tops[:5]:
            sym2 = ('sh' if s['code'].startswith('6') else 'sz') + s['code']
            q2 = _qt(sym2)
            if not q2 or not q2['prev']:
                continue
            op2 = (q2['open'] / q2['prev'] - 1) * 100
            lb2 = float(q2.get('lb', 0))
            gem2 = s.get('board') == 'gem'
            lo2, hi2 = (2, 7) if not gem2 else (4, 14)
            lb_min2 = 2.0 if not gem2 else 1.5
            ok2 = lo2 <= op2 <= hi2 and lb2 >= lb_min2
            why2 = ''
            if not ok2:
                why2 = (f'量比{lb2:.1f}<{lb_min2}，资金竞价没进场，撑不起高开' if lb2 < lb_min2
                        else f'高开{op2:+.1f}%超过{hi2}%，竞价透支、开盘容易被砸' if op2 > hi2
                        else f'高开{op2:+.1f}%不足{lo2}%，没溢价不值得做')
            _cinfos.append({'name': s['name'], 'code': s['code'], 'op': op2, 'lb': lb2, 'sec': s['industry'], 'ok': ok2, 'why': why2})
            if ok2:
                _crows.append(f'<div style="margin:4px 0;font-size:13px;background:#1c2830;border-left:3px solid {RED};border-radius:8px;padding:6px 10px;">✅ <b style="color:#fff;">{s["name"]}({s["code"]})</b> 高开{op2:+.1f}% 量比{lb2:.1f} → <span style="color:{RED};font-weight:800;">可跟 1成试探，止损-3%</span></div>')
            else:
                _crows.append(f'<div style="margin:4px 0;font-size:13px;background:#1f2635;border-left:3px solid {GREY};border-radius:8px;padding:6px 10px;">❌ {s["name"]}({s["code"]}) 高开{op2:+.1f}% 量比{lb2:.1f} → <span style="color:{GREY};">放弃（{why2}）</span></div>')
        _dmap2 = _confirm_ds(_cinfos)
        if _dmap2:
            _crows.append('<div style="margin-top:6px;padding:8px 10px;background:#1c2230;border-left:4px solid ' + TEAL + ';border-radius:8px;">'
                          + ''.join('<div style="color:#e9ecef;font-size:12px;margin:3px 0;">🧠 ' + nm + '：' + rz + '</div>' for nm, rz in _dmap2.items()) + '</div>')
        if _crows:
            _confirm_block = ('<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">🔔 竞价实盘确认（高开+量能复核，AI逐票深挖）</div>'
                              + ''.join(_crows))
    except Exception as e:
        print('[auction] 确认段失败:', e)
        _confirm_block = ''
    inner = (overall + f'<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">🔔 持仓竞价诊断（先看自己的）</div>'
             + (''.join(own) or '<div style="color:' + GREY + ';font-size:13px;">无持仓</div>')
             + pick + wind + pos_cap_line(emotion, None) + _confirm_block)
    return _wrap(inner, '🔔', '竞价观察')'''

assert s.count(A1) == 1, 'A1 锚点不唯一: %d' % s.count(A1)
s = s.replace(A1, NEW_A1)
io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('OK auction 确认段合并完成')
