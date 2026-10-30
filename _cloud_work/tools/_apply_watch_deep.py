# -*- coding: utf-8 -*-
"""一次性补丁v2：异动·新闻发酵卡深挖。行级定位，避免引号地狱。勿重跑。"""
import io

P = r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py'
lines = io.open(P, encoding='utf-8').read().split('\n')

# ---- 1. 在 news_drive 函数 return out 后插入 _news_drive_deep ----
fn = '''def _news_drive_deep(item, purpose='watch_news'):
    """盘中异动·新闻发酵卡深挖：ModelScope 对单条事件生成五要素 JSON。
    失败返回 None（调用方用原模板兜底，不打断实时推送）。"""
    if not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return None
    hold = '；'.join(f"{h['name']}(成本{h['cost']})" for h in HOLDINGS)
    fmt = ('你是10年A股超短线交易员。盘中出现一条市场异动新闻，请深度挖掘，不许偷懒：\\n'
           '只输出 JSON，不要任何其他文字：\\n'
           '{"items":[{"t":"事件标题","i":"影响板块/题材，至少15字（猜不到写「暂看不出直接关联」，不许编）","s":"代表个股深挖：点名1-2只能代表这条异动的股票代码+名称，深挖它自己的逻辑（业绩/催化/位置/为什么它能代表/有没有暗雷），至少30字，不许泛泛而谈","w":"大白话：一句话戳穿真假+为什么，至少25字","a":"操作：买/躲/看，写具体（加自选什么条件下跟/买点/止损/仓位），至少20字"}]}\\n'
           '当前持仓：{hold}，若异动与持仓相关必须点名联动提醒。')
    t = ask_deepseek({'task': purpose, 'title': item.get('title', ''),
                      'sec': item.get('sec', ''), 'leaders': '、'.join(item.get('leaders', [])) or '无',
                      'hold': hold, 'format': fmt}, purpose=purpose)
    pairs = _parse_ds_json(t)
    if pairs and len(pairs[0]) >= 5 and len(pairs[0][2]) >= 20:
        return pairs[0]
    return None
'''
anchor_out = [i for i, l in enumerate(lines) if l.strip() == '    return out']
# news_drive 的 return out 是第一个匹配（在 news_drive 内）；其后跟空行+BEAR_KW
if anchor_out:
    ins_at = anchor_out[0] + 1
    lines[ins_at:ins_at] = ['', fn]
    print('inserted _news_drive_deep at line', ins_at)
else:
    print('ANCHOR return out NOT FOUND')

# ---- 2. 替换新闻发酵卡渲染块 ----
start = None
end = None
for i, l in enumerate(lines):
    if "tag = '📰 事件驱动' if item['merged'] else '📰 新闻发酵'" in l:
        start = i
    if start is not None and i > start and "return _wrap(f'<div style=\"color:{GOLD};font-size:14px;font-weight:700;\">⏰" in l:
        end = i
        break
if start is None or end is None:
    print('RENDER BLOCK anchors not found:', start, end)
else:
    new_block = """            tag = '📰 事件驱动' if item['merged'] else '📰 新闻发酵'
            _deep = _news_drive_deep(item, 'watch_news')
            if _deep:
                _i = _strip_pre(_deep[1], ('影响：', '影响:'))
                _s2 = _strip_pre(_deep[2], ('代表个股：', '代表个股:', '个股：', '个股:'))
                _w = _strip_pre(_deep[3], ('大白话：', '大白话:', '人话：', '解读：'))
                _a = _strip_pre(_deep[4], ('操作：', '操作:'))
                _sec_txt = _i or item['sec']
                _lead_html = ('<div style="color:' + GREEN + ';font-size:12px;margin-top:4px;">📌 历史强势股：' + '、'.join(item['leaders']) + '</div>') if item['leaders'] else ''
                cards = ('<div style="background:#1f2635;border:2px solid ' + GOLD + ';border-radius:12px;padding:12px 14px;margin:10px 0;">'
                         '<div style="font-size:16px;font-weight:900;color:' + GOLD + ';">' + tag + '</div>'
                         '<div style="color:#fff;font-size:13px;margin-top:6px;line-height:1.7;">' + item['title'] + '</div>'
                         '<div style="color:' + GOLD + ';font-size:12px;margin-top:6px;">🎯 影响板块：' + _sec_txt + '</div>'
                         '<div style="color:#b197fc;font-size:12px;margin-top:4px;">🏆 代表个股：' + _s2 + '</div>'
                         '<div style="color:' + TEAL + ';font-size:12px;margin-top:4px;">🧠 大白话：' + _w + '</div>'
                         '<div style="color:' + RED + ';font-size:12px;margin-top:4px;">💡 操作：' + _a + '</div>'
                         + _lead_html + '</div>')
            else:
                _lead_html = ('<div style="color:' + GREEN + ';font-size:12px;margin-top:4px;">📌 历史强势股：' + '、'.join(item['leaders']) + '</div>') if item['leaders'] else ''
                cards = ('<div style="background:#1f2635;border:2px solid ' + GOLD + ';border-radius:12px;padding:12px 14px;margin:10px 0;">'
                         '<div style="font-size:16px;font-weight:900;color:' + GOLD + ';">' + tag + '</div>'
                         '<div style="color:#fff;font-size:13px;margin-top:6px;line-height:1.7;">' + item['title'] + '</div>'
                         '<div style="color:' + TEAL + ';font-size:13px;margin-top:6px;">影响板块：' + item['sec'] + '</div>'
                         + _lead_html
                         + '<div style="color:' + TEAL + ';font-size:12px;margin-top:6px;">👉 ' + ('板块已动，盯龙头，破-3%走' if item['merged'] else '暂未动，先加自选，板块放量再跟') + '</div></div>')
"""
    lines[start:end] = new_block.split('\n')
    print('render block replaced, lines', start, '->', end)

io.open(P, 'w', encoding='utf-8', newline='').write('\n'.join(lines))
print('done')
