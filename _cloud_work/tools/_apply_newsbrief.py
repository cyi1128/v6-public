# -*- coding: utf-8 -*-
"""一次性补丁：新闻逐条大白话解读（外盘窗口/晚间消息汇总的新闻区块）。
- 新增 _news_ds_lines()：DS 一次调用批量解读 N 条新闻 → 解析 JSON 渲染「标题+👉大白话」；
- build_ext / build_evening 的新闻区块接入；DS 失败/解析失败 → 降级纯标题列表（推送不断）。
勿重跑。备份：.bak_before_newsbrief"""
import io, sys

P = r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py'
s = io.open(P, encoding='utf-8').read()
cnt = {'ok': 0, 'fail': []}

def rep(old, new, must=1):
    global s
    n = s.count(old)
    if n != must:
        cnt['fail'].append((old[:70], n, must))
        return
    s = s.replace(old, new)
    cnt['ok'] += 1

# ========== 1. 新增 _news_ds_lines + 解析（放 build_evening 之后、_early_watch 之前） ==========
rep("def _early_watch(market_bias='震荡'):",
    "def _parse_ds_json(t):\n"
    "    \"\"\"解析 DS 返回的 JSON（容忍 markdown 代码块包裹）。失败返回 None。\"\"\"\n"
    "    if not t:\n"
    "        return None\n"
    "    s2 = t.strip()\n"
    "    if s2.startswith('```'):\n"
    "        s2 = s2.split('```', 2)[1] if s2.count('```') >= 2 else s2.replace('```', '')\n"
    "    s2 = s2.strip().strip('`')\n"
    "    try:\n"
    "        d = json.loads(s2)\n"
    "        items = d.get('items') or d.get('data') or []\n"
    "        if not isinstance(items, list) or not items:\n"
    "            return None\n"
    "        out = []\n"
    "        for it in items:\n"
    "            if isinstance(it, dict) and (it.get('t') or it.get('title')):\n"
    "                out.append((str(it.get('t') or it.get('title')), str(it.get('p') or it.get('note') or '')))\n"
    "        return out or None\n"
    "    except Exception:\n"
    "        return None\n"
    "\n"
    "\n"
    "def _news_ds_lines(news, n=10, purpose_key='news_brief'):\n"
    "    \"\"\"新闻逐条大白话解读：DS 一次调用批量解读，返回 [(标题, 大白话)]。\n"
    "    无 LLM / 失败 / 解析失败 → 返回 None（调用方降级纯标题）。\"\"\"\n"
    "    brief = [{'t': nw.get('title', ''), 's': (nw.get('summary') or '')[:60]} for nw in news[:n]]\n"
    "    if not brief:\n"
    "        return None\n"
    "    if not (MODELSCOPE_KEY or DEEPSEEK_KEY):\n"
    "        return None\n"
    "    fmt = ('你是10年A股超短线交易员。下面{num}条财经消息，逐条用一句大白话解读：\\n'\n"
    "           '只输出 JSON，不要任何其他文字，格式：\\n'\n"
    "           '{\"items\":[{\"t\":\"消息标题\",\"p\":\"大白话（这句人话要戳破：对A股哪个板块/方向有影响、是真消息还是纯情绪、重要不重要）\"}]}\\n'\n"
    "           '必须覆盖全部{num}条，不许漏、不许编消息里没有的内容。')\n"
    "    t = ask_deepseek({'task': purpose_key, 'num': len(brief), 'news': brief, 'format': fmt},\n"
    "                     purpose=purpose_key)\n"
    "    pairs = _parse_ds_json(t)\n"
    "    if pairs:\n"
    "        print(f'[LLM] 新闻逐条解读 OK purpose={purpose_key} n={len(pairs)}')\n"
    "    return pairs\n"
    "\n"
    "\n"
    "def _news_html_lines(news, n=10, purpose_key='news_brief', max_show=15):\n"
    "    \"\"\"新闻区块 HTML：优先逐条大白话；DS 失败降级纯标题。\n"
    "    返回 (html, 用了大白话 bool)。\"\"\"\n"
    "    pairs = _news_ds_lines(news, n, purpose_key)\n"
    "    if pairs:\n"
    "        rows = []\n"
    "        for t0, p in pairs[:max_show]:\n"
    "            p_html = f'<div style=\"margin:2px 0 8px 16px;color:{TEAL};font-size:12px;\">👉 {p}</div>' if p else ''\n"
    "            rows.append(f'<div style=\"color:#ced4da;font-size:12px;margin:6px 0 0 0;\">· {t0}</div>' + p_html)\n"
    "        return '<div>' + ''.join(rows) + '</div>', True\n"
    "    rows = ''.join(\n"
    "        f'<div style=\"color:#ced4da;font-size:12px;margin:3px 0;\">· {nw.get(\"ts\",\"\")[-5:]} {nw[\"title\"]}</div>'\n"
    "        for nw in news[:max_show])\n"
    "    if not rows:\n"
    "        rows = '<div style=\"color:' + GREY + ';font-size:13px;\">消息未取得</div>'\n"
    "    return '<div>' + rows + '</div>', False\n"
    "\n"
    "\n"
    "def _early_watch(market_bias='震荡'):")

# ========== 2. build_ext 新闻区块 → 逐条大白话 ==========
rep("    news_rows = ''.join(\n"
    "        f'<div style=\"color:#ced4da;font-size:12px;margin:3px 0;\">· {nw.get(\"ts\",\"\")[-5:]} {nw[\"title\"]}</div>'\n"
    "        for nw in news[:10]) or '<div style=\"color:' + GREY + ';font-size:13px;\">全球消息未取得</div>'",
    "    news_rows, _used_ds = _news_html_lines(news, n=8, purpose_key='ext_news', max_show=10)")

# ========== 3. build_evening 新闻区块 → 逐条大白话 ==========
rep("    news_rows = ''.join(\n"
    "        f'<div style=\"color:#ced4da;font-size:12px;margin:3px 0;\">· {nw.get(\"ts\",\"\")[-5:]} {nw[\"title\"]}</div>'\n"
    "        for nw in news[:15]) or '<div style=\"color:' + GREY + ';font-size:13px;\">消息未取得</div>'",
    "    news_rows, _used_ds = _news_html_lines(news, n=12, purpose_key='eve_news', max_show=15)")

io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('OK', cnt['ok'], '替换；失败：')
for f_ in cnt['fail']:
    print('  [%s] 次数=%s 期望=%s' % f_)
sys.exit(0 if not cnt['fail'] else 1)
