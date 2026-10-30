# -*- coding: utf-8 -*-
"""一次性补丁：外盘窗口升级（全球行情+全球消息+DS大白话）+ 新增晚间消息汇总卡（evening slot）。
勿重跑。备份：.bak_before_global"""
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

# ========== 1. 新增 _global_markets()（build_ext 之前） ==========
rep("def build_ext():",
    "def _global_markets():\n"
    "    \"\"\"全球行情采集（多源：腾讯美股/商品 + 新浪恒生 + OKX比特币）。缺哪个标哪个，绝不编造。\n"
    "    返回 [(名称, 涨跌%, 备注)]，涨跌% 为 None 表示未取得。\"\"\"\n"
    "    out = []\n"
    "    for nm, code in (('纳指', 'usIXIC'), ('道指', 'usDJI'), ('标普', 'usINX')):\n"
    "        try:\n"
    "            txt, ok = _getm('http://qt.gtimg.cn/q=' + code, 'ext_' + code)\n"
    "            if not ok or not txt:\n"
    "                out.append((nm, None, '未取得'))\n"
    "                continue\n"
    "            f = txt.split('~')\n"
    "            prev = float(f[4]) if len(f) > 4 and f[4] not in ('', '0.00') else 0\n"
    "            pct = (float(f[3]) / prev - 1) * 100 if prev else None\n"
    "            out.append((nm, pct, ''))\n"
    "        except Exception:\n"
    "            out.append((nm, None, '未取得'))\n"
    "    try:\n"
    "        req = urllib.request.Request('https://hq.sinajs.cn/list=int_hangseng',\n"
    "                                     headers={**UA, 'Referer': 'https://finance.sina.com.cn/'})\n"
    "        txt = urllib.request.urlopen(req, timeout=8).read().decode('gbk', 'ignore')\n"
    "        f = txt.split('\"')[1].split(',')\n"
    "        if len(f) > 2 and f[1]:\n"
    "            cur = float(f[1]); chg = float(f[2])\n"
    "            out.append(('恒生', chg / (cur - chg) * 100 if cur != chg else 0.0, ''))\n"
    "        else:\n"
    "            out.append(('恒生', None, '未取得'))\n"
    "    except Exception:\n"
    "        out.append(('恒生', None, '未取得'))\n"
    "    for nm, code in (('原油', 'hf_CL'), ('黄金', 'hf_GC')):\n"
    "        try:\n"
    "            txt, ok = _getm('http://qt.gtimg.cn/q=' + code, 'ext_' + code)\n"
    "            if not ok or not txt:\n"
    "                out.append((nm, None, '未取得'))\n"
    "                continue\n"
    "            v = txt.split('\"')[1].split(',')\n"
    "            out.append((nm, float(v[1]), ''))\n"
    "        except Exception:\n"
    "            out.append((nm, None, '未取得'))\n"
    "    try:\n"
    "        b = _btc_quote()\n"
    "        if b:\n"
    "            out.append(('比特币', b[1], ''))\n"
    "        else:\n"
    "            out.append(('比特币', None, '未取得'))\n"
    "    except Exception:\n"
    "        out.append(('比特币', None, '未取得'))\n"
    "    return out\n"
    "\n"
    "\n"
    "def _global_markets_html(gl):\n"
    "    \"\"\"全球行情区块 HTML（红涨绿跌，有数据的才显示）。\"\"\"\n"
    "    if not gl:\n"
    "        return '<div style=\"color:' + GREY + ';font-size:13px;\">全球行情未取得</div>'\n"
    "    rows = []\n"
    "    for nm, pct, note in gl:\n"
    "        if pct is None:\n"
    "            rows.append(f'{nm} <span style=\"color:{GREY}\">{note or \"未取得\"}</span>')\n"
    "        else:\n"
    "            rows.append(f'{nm} <b style=\"color:{RED if pct >= 0 else GREEN}\">{pct:+.2f}%</b>')\n"
    "    return '<div style=\"font-size:13px;color:#e2e8f0;\">' + '　'.join(rows) + '</div>'\n"
    "\n"
    "\n"
    "def build_ext():")

# ========== 2. build_ext 整体重构（保留原函数名） ==========
old_ext = '''def build_ext():
    """外盘关键窗口极简提醒（模块11）：美股开盘约30分钟后（北京 21:38/22:38 cron，
    避开盘中 watch 分钟点防重复 run；夏令时下 21:38 无美盘数据则如实标注）。纯规则 ≤5 行，零 DS。"""
    items = [('纳指', 'usIXIC'), ('道指', 'usDJI'), ('标普', 'usINX'), ('原油', 'hf_CL'), ('黄金', 'hf_GC')]
    rows = []
    for nm, code in items:
        try:
            txt, ok = _getm(f'http://qt.gtimg.cn/q={code}', 'ext_' + code)
            if not ok or not txt:
                rows.append(f'{nm} <span style="color:{GREY}">未取得</span>')
                continue
            if code.startswith('hf_'):
                s = txt.split('"')[1].split(',')
                pct = float(s[1])
            else:
                f = txt.split('~')
                prev = float(f[4]) if f[4] not in ('', '0.00') else 0
                pct = (float(f[3]) / prev - 1) * 100 if prev else 0.0
            c = RED if pct >= 0 else GREEN
            rows.append(f'{nm} <b style="color:{c}">{pct:+.2f}%</b>')
        except Exception:
            rows.append(f'{nm} <span style="color:{GREY}">格式异常</span>')
    impact = '中性（数据未取得，不硬编影响）'
    try:
        txt, _ = _getm('http://qt.gtimg.cn/q=usIXIC', 'ext_nas')
        if txt and '~' in txt:
            f = txt.split('~')
            if len(f) > 4 and float(f[4]):
                npct = (float(f[3]) / float(f[4]) - 1) * 100
                impact = ('偏多：纳指' + ('涨' if npct >= 0 else '跌') + f'{abs(npct):.2f}%'
                          + ('，A股科技/成长情绪受益' if npct >= 0 else '，A股科技承压）'))
                if npct < 0:
                    impact = '偏空：纳指跌' + f'{abs(npct):.2f}%' + '，A股科技/成长承压'
                else:
                    impact = '偏多：纳指涨' + f'{npct:.2f}%' + '，A股科技/成长情绪受益'
    except Exception:
        pass
    inner = ('<div style="font-size:13px;color:#e2e8f0;">' + '｜'.join(rows) + '</div>'
             f'<div style="margin-top:6px;font-size:13px;color:{TEAL};">👉 对A股影响：{impact}</div>')
    return _wrap(inner, '🌙', '外盘窗口')'''

new_ext = '''def build_ext():
    """外盘窗口（升级版）：全球行情采集（美股三指数/恒生/原油/黄金/比特币）+ 全球7x24消息
    → DeepSeek 大白话汇总对A股影响。DS 失败/用尽 → 规则兜底（行情+纳指影响+新闻标题）。"""
    gl = _global_markets()
    news = []
    try:
        news = get_news(14)
    except Exception:
        pass
    markets_txt = '；'.join(f'{nm} {("未取得" if pct is None else "%+.2f%%" % pct)}' for nm, pct, _ in gl)
    news_brief = [{'t': nw['title'], 's': (nw.get('summary') or '')[:50]} for nw in news[:12]]
    # —— DS 大白话汇总（交易员规范；失败/用尽 → 规则兜底）——
    ds_html = ''
    if DEEPSEEK_KEY and news:
        fmt = (_TRADER_RULES + '\\n'
               + '今晚全球行情：{markets}\\n'
               + '全球财经消息（东财7x24）：\\n{news}\\n'
               + '请严格按以下格式输出（全大白话，禁模板句，不许加板块）：\\n'
               + '【全球盘面】一句话（美股/商品/恒生，哪里强哪里弱）\\n'
               + '【今晚大事】3-5条（从消息里挑真正重要的，每条=事实+对A股哪个板块有影响；消息里没有的直说）\\n'
               + '【明天A股怎么看】一句话（影响哪些方向、怎么应对，别绕弯子）\\n'
               + '【最大风险】一句话（今晚最大的雷/变数在哪）')
        t = ask_deepseek({'task': 'ext_global', 'markets': markets_txt, 'news': news_brief,
                          'format': fmt}, purpose='ext')
        ds_html = md2html(t) if t else ''
    # —— 规则兜底影响判断（DS 没出时用）——
    impact = '中性（数据未取得，不硬编影响）'
    try:
        txt, _ = _getm('http://qt.gtimg.cn/q=usIXIC', 'ext_nas')
        if txt and '~' in txt:
            f = txt.split('~')
            if len(f) > 4 and float(f[4]):
                npct = (float(f[3]) / float(f[4]) - 1) * 100
                impact = ('偏空：纳指跌' + f'{abs(npct):.2f}%' + '，A股科技/成长承压'
                          if npct < 0 else '偏多：纳指涨' + f'{npct:.2f}%' + '，A股科技/成长情绪受益')
    except Exception:
        pass
    news_rows = ''.join(
        f'<div style="color:#ced4da;font-size:12px;margin:3px 0;">· {nw.get("ts","")[-5:]} {nw["title"]}</div>'
        for nw in news[:10]) or '<div style="color:' + GREY + ';font-size:13px;">全球消息未取得</div>'
    inner = (f'<div style="font-size:15px;font-weight:800;color:#ff922b;">🌐 全球行情（红涨绿跌）</div>'
             + _global_markets_html(gl)
             + f'<div style="margin-top:6px;font-size:13px;color:{TEAL};">👉 对A股影响（规则兜底）：{impact}</div>'
             + (f'<div style="margin-top:10px;padding:10px;background:#1c2230;border-left:4px solid {GOLD};border-radius:8px;font-size:13px;line-height:1.8;color:#e2e8f0;">🤖 大白话汇总：{ds_html}</div>' if ds_html else '')
             + f'<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">📰 全球消息速览</div>'
             + news_rows)
    return _wrap(inner, '🌙', '外盘窗口')


def build_evening():
    """晚间消息汇总（北京 22:50）：今日A股全景 + 全球晚间行情/消息 → DS 大白话
    「今日大事 + 明日关注」。DS 失败/用尽 → 规则兜底（行情+新闻列表）。"""
    gl = _global_markets()
    news = []
    try:
        news = get_news(20)
    except Exception:
        pass
    d = None
    try:
        d = get_pools()
    except Exception:
        d = None
    # —— 顶部：今日A股全景 ——
    a_sec = ''
    if d:
        try:
            b, _, _, zbr = sentiment(get_indices(), d)
        except Exception:
            b, zbr = '震荡', 0.0
        tops_txt = '、'.join(n for n, _ in d['tops'][:5]) or '无'
        a_sec = (f'<div style="font-size:14px;">🔴涨停<b style="color:{RED}">{d["lu"]}</b> '
                 f'🟢炸板<b style="color:{GREEN}">{d["zb"]}</b> 🟢跌停<b style="color:{GREEN}">{d["dt"]}</b> '
                 f'最高<b style="color:{GOLD}">{d["max_lbc"]}板</b> ｜ 情绪 <b style="color:{_c(0)}">{b}</b>（炸板率{zbr*100:.0f}%）</div>'
                 f'<div style="margin-top:4px;font-size:13px;color:{TEAL};">今日主线：{tops_txt}</div>')
    else:
        a_sec = '<div style="color:' + GREY + ';font-size:13px;">A股盘面数据未取得</div>'
    markets_txt = '；'.join(f'{nm} {("未取得" if pct is None else "%+.2f%%" % pct)}' for nm, pct, _ in gl)
    news_brief = [{'t': nw['title'], 's': (nw.get('summary') or '')[:50]} for nw in news[:18]]
    # —— DS 大白话汇总 ——
    ds_html = ''
    if DEEPSEEK_KEY and news:
        fmt = (_TRADER_RULES + '\\n'
               + '今日A股：{a_sec}\\n'
               + '全球晚间行情：{markets}\\n'
               + '今日+晚间消息（东财7x24）：\\n{news}\\n'
               + '请严格按以下格式输出（全大白话，禁模板句，不许加板块）：\\n'
               + '【今日大事】3-5条（A股和全球各挑真正重要的，每条=事实+一句大白话解释为什么重要；消息里没有的直说）\\n'
               + '【明日关注】2-3条（明天最该盯什么方向/事件，怎么应对）\\n'
               + '【最大风险】一句话\\n'
               + '如果今天没有值得说的，直接写「今日无大事，平稳过渡」并说明原因。')
        t = ask_deepseek({'task': 'evening_summary', 'a_sec': a_sec, 'markets': markets_txt,
                          'news': news_brief, 'format': fmt}, purpose='evening')
        ds_html = md2html(t) if t else ''
    news_rows = ''.join(
        f'<div style="color:#ced4da;font-size:12px;margin:3px 0;">· {nw.get("ts","")[-5:]} {nw["title"]}</div>'
        for nw in news[:15]) or '<div style="color:' + GREY + ';font-size:13px;">消息未取得</div>'
    inner = (f'<div style="font-size:15px;font-weight:800;color:#ff922b;">🇨🇳 今日A股全景</div>' + a_sec
             + f'<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">🌐 全球晚间行情</div>'
             + _global_markets_html(gl)
             + (f'<div style="margin-top:10px;padding:10px;background:#1c2230;border-left:4px solid {GOLD};border-radius:8px;font-size:13px;line-height:1.8;color:#e2e8f0;">🤖 今日大事 & 明日关注：{ds_html}</div>' if ds_html else '')
             + f'<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">📰 今日消息汇总（按时间）</div>'
             + news_rows)
    return _wrap(inner, '🌙', '晚间消息汇总')'''

rep(old_ext, new_ext)

# ========== 3. slot 分发：ext 分支后加 evening ==========
rep("    if slot == 'warn':",
    "    if slot == 'evening':\n"
    "        try:\n"
    "            _ev = build_evening()\n"
    "        except Exception as e:\n"
    "            print('[evening] build exception:', e)\n"
    "            _ev = None\n"
    "        if _ev is None:\n"
    "            print('SLOT evening: 构建失败，不推送')\n"
    "            sys.exit(0)\n"
    "        ok, msg = push(_ev, f'晚间消息汇总 {_bj_now().strftime(\"%H:%M\")}')\n"
    "        print('SLOT evening PUSH', ok, msg)\n"
    "        sys.exit(0)\n"
    "    if slot == 'warn':")

io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('OK', cnt['ok'], '替换；失败：')
for f_ in cnt['fail']:
    print('  [%s] 次数=%s 期望=%s' % f_)
sys.exit(0 if not cnt['fail'] else 1)
