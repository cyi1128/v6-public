# -*- coding: utf-8 -*-
"""一次性补丁：新闻逐条解读升级为三要素（🎯影响/🧠大白话/💡操作）+ build_news2h 内容加量与规则兜底。
勿重跑。备份：.bak_before_news3elem"""
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

# ========== 1. _parse_ds_json → 四元组 (t, i, w, a)，兼容旧二元组 ==========
rep("        out = []\n"
    "        for it in items:\n"
    "            if isinstance(it, dict) and (it.get('t') or it.get('title')):\n"
    "                out.append((str(it.get('t') or it.get('title')), str(it.get('p') or it.get('note') or '')))\n"
    "        return out or None",
    "        out = []\n"
    "        for it in items:\n"
    "            if isinstance(it, dict) and (it.get('t') or it.get('title')):\n"
    "                out.append((str(it.get('t') or it.get('title')),\n"
    "                            str(it.get('i') or it.get('impact') or ''),\n"
    "                            str(it.get('w') or it.get('p') or it.get('note') or ''),\n"
    "                            str(it.get('a') or it.get('op') or '')))\n"
    "        return out or None")

# ========== 2. _news_ds_lines prompt → 三要素 ==========
rep("    fmt = ('你是10年A股超短线交易员。下面{num}条财经消息，逐条用一句大白话解读：\\n'\n"
    "           '只输出 JSON，不要任何其他文字，格式：\\n'\n"
    "           '{\"items\":[{\"t\":\"消息标题\",\"p\":\"大白话（这句人话要戳破：对A股哪个板块/方向有影响、是真消息还是纯情绪、重要不重要）\"}]}\\n'\n"
    "           '必须覆盖全部{num}条，不许漏、不许编消息里没有的内容。')",
    "    fmt = ('你是10年A股超短线交易员。下面{num}条财经消息，逐条完整解读，必须三要素齐全：\\n'\n"
    "           '只输出 JSON，不要任何其他文字，格式：\\n'\n"
    "           '{\"items\":[{\"t\":\"消息标题\",\"i\":\"影响：具体板块/题材/个股（猜不到写「暂看不出直接关联」，不许编）\",\"w\":\"大白话：一句话戳穿真假+为什么（影响逻辑）\",\"a\":\"操作：买/躲/看，具体怎么应对\"}]}\\n'\n"
    "           '必须覆盖全部{num}条，不许漏、不许编消息里没有的内容。每条 i/w/a 都要有实质内容，不许只写标题。')")

# ========== 3. _news_html_lines 渲染 → 三行 ==========
rep("    if pairs:\n"
    "        rows = []\n"
    "        for t0, p in pairs[:max_show]:\n"
    "            p_html = f'<div style=\"margin:2px 0 8px 16px;color:{TEAL};font-size:12px;\">👉 {p}</div>' if p else ''\n"
    "            rows.append(f'<div style=\"color:#ced4da;font-size:12px;margin:6px 0 0 0;\">· {t0}</div>' + p_html)\n"
    "        return '<div>' + ''.join(rows) + '</div>', True",
    "    if pairs:\n"
    "        rows = []\n"
    "        for it in pairs[:max_show]:\n"
    "            t0 = it[0]\n"
    "            i, w, a = (it[1], it[2], it[3]) if len(it) >= 4 else ('', it[1] if len(it) > 1 else '', '')\n"
    "            rows.append(f'<div style=\"color:#ced4da;font-size:12px;margin:8px 0 0 0;\">· {t0}</div>'\n"
    "                        + (f'<div style=\"margin:2px 0 0 16px;color:{GOLD};font-size:12px;\">🎯 影响：{i}</div>' if i else '')\n"
    "                        + (f'<div style=\"margin:2px 0 0 16px;color:{TEAL};font-size:12px;\">🧠 大白话：{w}</div>' if w else '')\n"
    "                        + (f'<div style=\"margin:2px 0 8px 16px;color:{RED};font-size:12px;\">💡 操作：{a}</div>' if a else ''))\n"
    "        return '<div>' + ''.join(rows) + '</div>', True")

# ========== 4. build_news2h：数量 5/5 + 三要素 _rows + 预期差规则兜底 + 大白话总结 ==========
rep("    good_pairs = _news_ds_lines(good, 4, 'news2h_good') or [(g.get('title',''), '') for g in good[:4]]\n"
    "    bad_pairs = _news_ds_lines(bad, 4, 'news2h_bad') or [(b.get('title',''), '') for b in bad[:4]]\n"
    "\n"
    "    def _rows(pairs, is_good):\n"
    "        if not pairs:\n"
    "            return '<div style=\"color:' + GREY + ';font-size:12px;\">今日无明显' + ('利好' if is_good else '利空') + '消息</div>'\n"
    "        return ''.join(\n"
    "            f'<div style=\"color:#fff;font-size:13px;margin:6px 0 0 0;\">· {t0}</div>'\n"
    "            + (f'<div style=\"margin:2px 0 8px 16px;color:{TEAL};font-size:12px;\">👉 {p}</div>' if p else '')\n"
    "            for t0, p in pairs)",
    "    good_pairs = _news_ds_lines(good, 5, 'news2h_good') or [(g.get('title',''), '', '', '') for g in good[:5]]\n"
    "    bad_pairs = _news_ds_lines(bad, 5, 'news2h_bad') or [(b.get('title',''), '', '', '') for b in bad[:5]]\n"
    "\n"
    "    def _rows(pairs, is_good):\n"
    "        if not pairs:\n"
    "            return '<div style=\"color:' + GREY + ';font-size:12px;\">今日无明显' + ('利好' if is_good else '利空') + '消息</div>'\n"
    "        out = []\n"
    "        for it in pairs:\n"
    "            t0 = it[0]\n"
    "            i, w, a = (it[1], it[2], it[3]) if len(it) >= 4 else ('', it[1] if len(it) > 1 else '', '')\n"
    "            out.append(f'<div style=\"color:#fff;font-size:13px;margin:8px 0 0 0;\">· {t0}</div>'\n"
    "                       + (f'<div style=\"margin:2px 0 0 16px;color:{GOLD};font-size:12px;\">🎯 影响：{i}</div>' if i else '')\n"
    "                       + (f'<div style=\"margin:2px 0 0 16px;color:{TEAL};font-size:12px;\">🧠 大白话：{w}</div>' if w else '')\n"
    "                       + (f'<div style=\"margin:2px 0 8px 16px;color:{RED};font-size:12px;\">💡 操作：{a}</div>' if a else ''))\n"
    "        return ''.join(out)")

rep("        fmt = (_TRADER_RULES + '\\n'\n"
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
    "        ds_html = md2html(t) if t else ''",
    "        fmt = (_TRADER_RULES + '\\n'\n"
    "               + '当前消息：利好{good}｜利空{bad}｜其他/中性{neu}\\n持仓：{hold}\\n'\n"
    "               + '请严格按以下格式输出（全大白话，禁模板句，不许加板块，不许罗列所有消息）：\\n'\n"
    "               + '【预期差】市场还没消化的消息1-2条（没有就写「今日无明显预期差消息，都是明牌」）\\n'\n"
    "               + '【怎么跟/怎么避】具体动作1-2条（结合利好利空说买什么、躲什么）\\n'\n"
    "               + '【明日操作建议】结合持仓给明确仓位档位（用1-2成/2-4成/半仓/空仓这类明确数字）\\n'\n"
    "               + '【大白话总结】一句话（今天消息面对A股整体偏暖还是偏冷、最该记的一个点）')\n"
    "        t = ask_deepseek({'task': 'news2h_summary',\n"
    "                          'good': [g.get('title','')[:40] for g in good[:5]],\n"
    "                          'bad': [b.get('title','')[:40] for b in bad[:5]],\n"
    "                          'neu': '；'.join((n.get('title') or '')[:50] for n in neu[:6]) or '无',\n"
    "                          'hold': hold_txt, 'format': fmt}, purpose='news2h')\n"
    "        if t:\n"
    "            ds_html = md2html(t)\n"
    "        else:\n"
    "            # LLM 全挂（超时/欠费/降级失败）→ 纯规则兜底，段不空\n"
    "            _bias = '偏暖' if len(good_pairs) >= len(bad_pairs) else '偏冷'\n"
    "            ds_html = ('<div style=\"font-size:13px;color:#e2e8f0;\">【预期差】今日无明显预期差消息，都是明牌。<br>'\n"
    "                       '【怎么跟】' + ('利好多于利空，优先盯领涨方向，不追高位，等回踩低吸。' if len(good_pairs) >= len(bad_pairs)\n"
    "                                       else '利空占优，管住手，仓位下调一档，回避消息面利空方向。')\n"
    "                       + '持仓道恩/冰轮按关键位执行，破位减仓，不破位持有。<br>'\n"
    "                       + f'【明日操作建议】消息面整体{_bias}，建议总仓位2-4成，只做主线龙头，不接高位。<br>'\n"
    "                       + f'【大白话总结】今日利好{len(good_pairs)}条/利空{len(bad_pairs)}条，消息面{_bias}，核心看主线能否延续，别追高。</div>')")

io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('OK', cnt['ok'], '替换；失败：')
for f_ in cnt['fail']:
    print('  [%s] 次数=%s 期望=%s' % f_)
sys.exit(0 if not cnt['fail'] else 1)
