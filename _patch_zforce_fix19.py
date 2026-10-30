# -*- coding: utf-8 -*-
"""FIX19：量比字段修正(f49换手率→f43真量比) + confirm_ds 缺量比防误杀 + 共享提示词市值/量能红线 + zscan theme 模型知识兜底"""
import io, sys, re
sys.stdout.reconfigure(encoding='utf-8')
P = r'D:\QuantMonitorV6\tools\cloud_daily_review.py'
src = io.open(P, encoding='utf-8').read()
orig = src

def rep(old, new, tag):
    global src
    assert old in src, 'NOT FOUND: ' + tag
    assert src.count(old) == 1, 'AMBIG: ' + tag + ' count=%d' % src.count(old)
    src = src.replace(old, new, 1)
    print('[OK]', tag)

# 1. _qt 量比字段 f49(换手率) → f43(真量比)
rep("""                    'prev': float(f[4]), 'lb': float(f[49] or 0), 'vol': float(f[6] or 0),
                    'avg': avg}""",
    """                    'prev': float(f[4]), 'lb': float(f[43] or 0), 'vol': float(f[6] or 0),
                    'avg': avg}""",
    'qt_lb_f43')

# 2. _deep6_collect：lb 取 f43 真量比；amp 改高低价实算（f43 不是振幅）
rep("""                 'pct': float(f[32] or 0), 'vol': float(f[6] or 0),
                 'amt': float(f[37] or 0), 'turn': float(f[38] or 0),
                 'lb': float(f[49] or 0), 'float_mv': float(f[44] or 0),
                 'amp': float(f[43] or 0)}""",
    """                 'pct': float(f[32] or 0), 'vol': float(f[6] or 0),
                 'amt': float(f[37] or 0), 'turn': float(f[38] or 0),
                 'lb': float(f[43] or 0), 'float_mv': float(f[44] or 0),
                 'amp': (float(f[33] or 0) - float(f[34] or 0)) / float(f[4] or 1) * 100}""",
    'deep6_lb_amp')

# 3. confirm_ds fmt：量比未取得标注，禁止按 0 否决
rep("""    lines = '\\n'.join(f"- {x['name']}({x['code']}) 高开{x['op']:+.1f}% 量比{x['lb']:.1f} 题材{x['sec']} 判定={'可跟' if x['ok'] else '放弃'}（规则原因：{x['why']}）" for x in infos)
    fmt = ('你是10年A股超短线交易员，竞价确认阶段，对下面每只票逐一解释判定，不许只说"不在区间"：\\n'
           + FIVE_BRIEF + '\\n'
           + '竞价名单：\\n' + lines + '\\n'""",
    """    lines = '\\n'.join(f"- {x['name']}({x['code']}) 高开{x['op']:+.1f}% 量比{'未取得' if not x.get('lb') or float(x.get('lb') or 0) <= 0 else ('%.1f' % x['lb'])} 题材{x['sec']} 判定={'可跟' if x['ok'] else '放弃'}（规则原因：{x['why']}）" for x in infos)
    fmt = ('你是10年A股超短线交易员，竞价确认阶段，对下面每只票逐一解释判定，不许只说"不在区间"：\\n'
           + FIVE_BRIEF + '\\n'
           + '竞价名单：\\n' + lines + '\\n'
           + '【量比红线】量比标注"未取得"的票说明数据源没取到该字段，绝不得把"未取得"当作量比0来解读，更不得以量比不足为由否决它——只凭高开幅度/题材热度/位置判定；\\n'""",
    'confirm_ds_missing_lb')

def rep_all(old, new, tag):
    global src
    n = src.count(old)
    assert n >= 1, 'NOT FOUND: ' + tag
    src = src.replace(old, new)
    print('[OK]', tag, 'x%d' % n)

# 4. 共享提示词 _ASK_DS_SYS_AC 与 _ASK_DS_SYS：市值红线 + 量能红线（覆盖 pre/auction/hourly/noon/news/eod）
rep_all("""               '高开>4% 强制标注「谨慎」；默认半仓起步，严禁建议满仓。'
               '所有操作必须给出明确买点、止损、仓位。'""",
    """               '高开>4% 强制标注「谨慎」；默认半仓起步，严禁建议满仓。'
               '【市值红线·用户铁律】点名推荐前先自问流通市值：只在30亿-150亿之间写（个股操作/埋伏标的/实战标的全部适用）；银行/白酒/运营商/万亿权重/千亿大盘蓝筹一律不推荐不写为操作标的，可作板块风向提及但必须标注不可操作。'
               '【量能红线】禁止编造或引用绝对量能数字（多少万手/万股/万元成交额），只写相对倍数（较前日放大3倍/缩至昨日一半）+价格锚（回踩X元）；没有实时量能数据的场景写"量能未取得"。'
               '所有操作必须给出明确买点、止损、仓位。'""",
    'shared_redlines')

# 5. ZSYS：theme 未取得时用模型知识兜底
rep("""⑤ 主线归属（补丁3·带时间戳）：theme_status 三选一——"当前主线"（所属板块在今日热点板块榜Top3且板块涨停≥3家）/"近期主线"（所属板块7个交易日内曾进过热点榜前5）/"冷门"（都不属于）。冷门池票若后续板块重新进主线，自动升级优先级。""",
    """⑤ 主线归属（补丁3·带时间戳）：theme_status 三选一——"当前主线"（所属板块在今日热点板块榜Top3且板块涨停≥3家）/"近期主线"（所属板块7个交易日内曾进过热点榜前5）/"冷门"（都不属于）。冷门池票若后续板块重新进主线，自动升级优先级。输入中个股所属板块为"未取得"时，用你的产业链知识补齐 theme/resonance/theme_status 并标注"据模型知识："，禁止整卡 theme_status 全部输出"未取得"。""",
    'zscan_theme_fallback')

io.open(P, 'w', encoding='utf-8', newline='').write(src)
print('patched, delta=%d bytes' % (len(src) - len(orig)))
