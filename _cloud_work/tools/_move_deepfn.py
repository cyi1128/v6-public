# -*- coding: utf-8 -*-
import io
P = r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py'
s = io.open(P, encoding='utf-8').read()

# 1. 删除误插在 get_global 内的 _news_drive_deep 块
marker = '\n\ndef _news_drive_deep(item, purpose=\'watch_news\'):'
idx = s.find(marker)
if idx == -1:
    print('marker not found')
    raise SystemExit(1)
# 函数体到 return None\n 结束（后面跟两个换行+下一个 def/注释）
end = s.find('\n\n', idx)
body = s[idx:end]
if 'return None' not in body or 'ask_deepseek' not in body:
    print('unexpected body range')
    raise SystemExit(1)
s = s[:idx] + s[end:]
print('removed misplaced block, len', len(body))

# 2. 插回 news_drive 的 return out 之后（第一个匹配，前文含 out.append({'title'）
anchor = "        out.append({'title': nw['title'], 'sec': sec,\n                    'leaders': old, 'merged': merged, 'hot': hot})\n    return out\n"
pos = s.find(anchor)
if pos == -1:
    print('news_drive anchor not found')
    raise SystemExit(1)
pos = pos + len(anchor)
insert = '''
def _news_drive_deep(item, purpose='watch_news'):
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
s = s[:pos] + insert + s[pos:]
io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('re-inserted after news_drive return out')
