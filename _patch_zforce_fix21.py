# -*- coding: utf-8 -*-
"""FIX21：主力雷达加"现价>=5日线"条件（用户指令）
①zhu_force_scan.py _finish_hit 计算 ma5/above_ma5 并输出
②run_scanner 末尾硬过滤 above_ma5（统计剔除数+坑底期影响）
③cloud_daily_review.py pool 输入加 ma5/above_ma5 + 渲染"站上5日线"标记"""
import io, sys
sys.stdout.reconfigure(encoding='utf-8')

def rep_file(P, old, new, tag):
    src = io.open(P, encoding='utf-8').read()
    assert old in src, 'NOT FOUND: ' + tag + ' @ ' + P
    assert src.count(old) == 1, 'AMBIG: ' + tag + ' count=%d' % src.count(old)
    io.open(P, 'w', encoding='utf-8', newline='').write(src.replace(old, new, 1))
    print('[OK]', tag)

# ============ 1. zhu_force_scan.py：_finish_hit 计算 MA5 ============
rep_file(r'D:\QuantMonitorV6\tools\zhu_force_scan.py',
    """    code, name, industry = s['code'], s['name'], s['industry']
    price = float(kl[-1]['close'])
    float_mv_yi = float_info or 0""",
    """    code, name, industry = s['code'], s['name'], s['industry']
    price = float(kl[-1]['close'])
    # FIX21: 现价 >= 5日线（用户铁律：只做站上5日线的票；等于5日线算通过）
    ma5 = sum(r['close'] for r in kl[-5:]) / 5 if len(kl) >= 5 else price
    above_ma5 = price >= ma5
    float_mv_yi = float_info or 0""",
    'ma5_calc')

# ============ 2. 输出 dict 加 ma5/above_ma5 ============
rep_file(r'D:\QuantMonitorV6\tools\zhu_force_scan.py',
    """        'kline_brief': kline_brief, 'score': score,
        'method_type': method_type, 'state': state, 'next_watch': next_watch,
        'pit_depth': (pit['depth'] if at_pit and pit else None),
    }""",
    """        'kline_brief': kline_brief, 'score': score,
        'method_type': method_type, 'state': state, 'next_watch': next_watch,
        'pit_depth': (pit['depth'] if at_pit and pit else None),
        'ma5': round(ma5, 2), 'above_ma5': bool(above_ma5),
    }""",
    'ma5_out')

# ============ 3. run_scanner 末尾硬过滤 ============
rep_file(r'D:\QuantMonitorV6\tools\zhu_force_scan.py',
    """    # FIX16: 用户铁律——当日涨跌幅>=7% 的票不进补涨池（已涨停/大涨不追；大跌结构坏）
    _before = len(hits)
    hits = [h for h in hits if abs(float((h.get('kline_brief') or [{}])[-1].get('pct') or 0)) < 7.0]
    if len(hits) != _before:
        print(f'[zforce] FIX16涨幅过滤: 剔除 {_before - len(hits)} 只 (当日|涨跌|>=7%)')""",
    """    # FIX16: 用户铁律——当日涨跌幅>=7% 的票不进补涨池（已涨停/大涨不追；大跌结构坏）
    _before = len(hits)
    hits = [h for h in hits if abs(float((h.get('kline_brief') or [{}])[-1].get('pct') or 0)) < 7.0]
    if len(hits) != _before:
        print(f'[zforce] FIX16涨幅过滤: 剔除 {_before - len(hits)} 只 (当日|涨跌|>=7%)')
    # FIX21: 用户铁律——现价 >= 5日线（价格大于五日线或等于五日线才进池）
    _before = len(hits)
    _keng = sum(1 for h in hits if not h.get('above_ma5') and h.get('state') == '坑底期')
    hits = [h for h in hits if h.get('above_ma5', False)]
    if len(hits) != _before:
        print(f'[zforce] FIX21五日线过滤: 剔除 {_before - len(hits)} 只 (现价<5日线，其中坑底期{_keng}只)')""",
    'ma5_filter')

# ============ 4. cloud_daily_review.py：pool 输入加字段 ============
rep_file(r'D:\QuantMonitorV6\tools\cloud_daily_review.py',
    """            'sector': _sc,
            'sector_limit_up_count': len(_by_sec.get(_sc, [])) if _c2sec else 0,
            'sector_rise2pct_count_on_ignition_day': None,   # 数据源未接入：LLM 按红线3标数据不足
            'announcements_10d': [], 'news_today': [],
            'liquidity_flag': '未知', 'liquidity_percentile': None,
        })""",
    """            'sector': _sc,
            'sector_limit_up_count': len(_by_sec.get(_sc, [])) if _c2sec else 0,
            'sector_rise2pct_count_on_ignition_day': None,   # 数据源未接入：LLM 按红线3标数据不足
            'announcements_10d': [], 'news_today': [],
            'liquidity_flag': '未知', 'liquidity_percentile': None,
            'ma5': h.get('ma5'), 'above_ma5': bool(h.get('above_ma5', False)),
        })""",
    'pool_ma5')

# ============ 5. 渲染"站上5日线"标记 ============
rep_file(r'D:\QuantMonitorV6\tools\cloud_daily_review.py',
    """            '<div style="font-size:12px;color:' + TEAL + ';margin-top:4px;">建仓手法：' + str(r.get('method') or '') + ('（' + str(hh2.get('method_type') or '') + '·' + str(hh2.get('state') or '') + '）' if hh2.get('method_type') else '') + ('　复核：' + str(r.get('method_review') or '') if r.get('method_review') else '') + '</div>'""",
    """            '<div style="font-size:12px;color:' + TEAL + ';margin-top:4px;">建仓手法：' + str(r.get('method') or '') + ('（' + str(hh2.get('method_type') or '') + '·' + str(hh2.get('state') or '') + '）' if hh2.get('method_type') else '') + ('　复核：' + str(r.get('method_review') or '') if r.get('method_review') else '') + ('　✅站上5日线 ' + str(hh2.get('ma5') or '') + '元' if hh2.get('above_ma5') else '') + '</div>'""",
    'render_ma5')

print('FIX21 done')
