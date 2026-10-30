# -*- coding: utf-8 -*-
"""一次性补丁：⑦ 两小时市场消息汇总卡（build_news2h）+ 旧事件简报独立档（slot news）。
勿重跑。备份：.bak_before_news2h"""
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

# ========== 1. 新增 build_news2h（放 _parse_ds_json 函数之后） ==========
rep("def _parse_ds_json(t):",
    "def build_news2h():\n"
    "    \"\"\"两小时市场消息汇总（北京 12:00/14:01/16:00）：利好/利空逐条大白话 +\n"
    "    预期差 + 怎么跟/怎么避 + 明日操作建议（结合持仓关键位）。\"\"\"\n"
    "    news = []\n"
    "    try:\n"
    "        news = get_news(30)\n"
    "    except Exception:\n"
    "        pass\n"
    "    good, bad, neu = [], [], []\n"
    "    for nw in news:\n"
    "        tag, _c = classify_news((nw.get('title') or '') + (nw.get('summary') or ''))\n"
    "        if tag in ('利好', '重大利好', '正面', '政策利好'):\n"
    "            good.append(nw)\n"
    "        elif tag in ('利空', '重大利空', '负面', '风险提示'):\n"
    "            bad.append(nw)\n"
    "        else:\n"
    "            neu.append(nw)\n"
    "    good_pairs = _news_ds_lines(good, 4, 'news2h_good') or [(g.get('title',''), '') for g in good[:4]]\n"
    "    bad_pairs = _news_ds_lines(bad, 4, 'news2h_bad') or [(b.get('title',''), '') for b in bad[:4]]\n"
    "\n"
    "    def _rows(pairs, is_good):\n"
    "        if not pairs:\n"
    "            return '<div style=\"color:' + GREY + ';font-size:12px;\">今日无明显' + ('利好' if is_good else '利空') + '消息</div>'\n"
    "        return ''.join(\n"
    "            f'<div style=\"color:#fff;font-size:13px;margin:6px 0 0 0;\">· {t0}</div>'\n"
    "            + (f'<div style=\"margin:2px 0 8px 16px;color:{TEAL};font-size:12px;\">👉 {p}</div>' if p else '')\n"
    "            for t0, p in pairs)\n"
    "\n"
    "    ds_html = ''\n"
    "    hold_txt = '；'.join(f\"{h['name']}(成本{h['cost']})\" for h in HOLDINGS)\n"
    "    if DEEPSEEK_KEY and news:\n"
    "        fmt = (_TRADER_RULES + '\\n'\n"
    "               + '当前消息：利好{good}｜利空{bad}｜其他/中性{neu}\\n持仓：{hold}\\n'\n"
    "               + '请严格按以下格式输出（全大白话，禁模板句，不许加板块，不许罗列所有消息）：\\n'\n"
    "               + '【预期差】市场还没消化的消息1-2条（没有就写「今日无明显预期差消息，都是明牌」）\\n'\n"
    "               + '【怎么跟/怎么避】具体动作1-2条（结合利好利空说买什么、躲什么）\\n'\n"
    "               + '【明日操作建议】结合持仓给明确仓位档位（用1-2成/2-4成/半仓/空仓这类明确数字）')\n"
    "        t = ask_deepseek({'task': 'news2h_summary',\n"
    "                          'good': [g.get('title','')[:40] for g in good[:4]],\n"
    "                          'bad': [b.get('title','')[:40] for b in bad[:4]],\n"
    "                          'neu': '；'.join((n.get('title') or '')[:50] for n in neu[:5]) or '无',\n"
    "                          'hold': hold_txt, 'format': fmt}, purpose='news2h')\n"
    "        ds_html = md2html(t) if t else ''\n"
    "    inner = (f'<div style=\"font-size:15px;font-weight:800;color:{RED};\">🔴 今日利好（{len(good_pairs)}条）</div>'\n"
    "             + _rows(good_pairs, True)\n"
    "             + f'<div style=\"margin-top:10px;font-size:15px;font-weight:800;color:{GREEN};\">🟢 今日利空（{len(bad_pairs)}条）</div>'\n"
    "             + _rows(bad_pairs, False)\n"
    "             + (f'<div style=\"margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;\">🤖 预期差 & 怎么跟</div>'\n"
    "                f'<div style=\"padding:10px;background:#1c2230;border-left:4px solid {GOLD};border-radius:8px;font-size:13px;line-height:1.8;color:#e2e8f0;\">{ds_html}</div>' if ds_html else '')\n"
    "             + f'<div style=\"margin-top:8px;font-size:11px;color:{GREY};\">不构成投资建议</div>')\n"
    "    return _wrap(inner, '📰', '两小时市场消息汇总')\n"
    "\n"
    "\n"
    "def _parse_ds_json(t):")

# ========== 2. TITLES 加 news/news2h ==========
rep("TITLES = {'pre': '盘前速递', 'auction': '竞价观察', 'noon': '午间作战', 'eod': '收盘复盘',",
    "TITLES = {'pre': '盘前速递', 'auction': '竞价观察', 'noon': '午间作战', 'eod': '收盘复盘',\n"
    "         'news': '事件简报', 'news2h': '两小时市场消息汇总',")

# ========== 3. main：slot news/news2h 特判（放 eod 分支之前） ==========
rep("    if slot == 'eod':\n"
    "        today = _bj_now().strftime('%Y-%m-%d')",
    "    if slot == 'news':\n"
    "        # 旧事件简报独立档（11:40=noon 档 / 15:10·15:35=eod 档），复用 build_events\n"
    "        _b = build_events('noon' if _bj_now().hour < 14 else 'eod')\n"
    "        if not _b:\n"
    "            print('SLOT news: 无有效事件，不推送')\n"
    "            sys.exit(0)\n"
    "        ok, msg = push(_wrap(_b, '📰', '事件简报'), f'事件简报 {_bj_now().strftime(\"%H:%M\")}')\n"
    "        print('SLOT news PUSH', ok, msg)\n"
    "        sys.exit(0)\n"
    "    if slot == 'news2h':\n"
    "        try:\n"
    "            _n2 = build_news2h()\n"
    "        except Exception as e:\n"
    "            print('[news2h] build exception:', e)\n"
    "            _n2 = None\n"
    "        if _n2 is None:\n"
    "            print('SLOT news2h: 构建失败，不推送')\n"
    "            sys.exit(0)\n"
    "        ok, msg = push(_n2, f'两小时消息汇总 {_bj_now().strftime(\"%H:%M\")}')\n"
    "        print('SLOT news2h PUSH', ok, msg)\n"
    "        sys.exit(0)\n"
    "    if slot == 'eod':\n"
    "        today = _bj_now().strftime('%Y-%m-%d')")

io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('OK', cnt['ok'], '替换；失败：')
for f_ in cnt['fail']:
    print('  [%s] 次数=%s 期望=%s' % f_)
sys.exit(0 if not cnt['fail'] else 1)
