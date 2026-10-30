# -*- coding: utf-8 -*-
"""一次性补丁：停用 DeepSeek 付费网关，全走 ModelScope；新闻渲染加原文行。
勿重跑。备份：.bak_before_ds_remove"""
import io

P = r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py'
s = io.open(P, encoding='utf-8').read()
cnt = {'ok': 0, 'fail': []}

def rep(old, new, must=1):
    global s
    n = s.count(old)
    if n != must:
        cnt['fail'].append((old[:60].replace('\n', '\\n'), n, must))
        return
    s = s.replace(old, new)
    cnt['ok'] += 1

# 1. DEEPSEEK_KEY 恒非空占位（兼容旧判断，实际不再走付费网关）
rep("DEEPSEEK_KEY = os.environ.get('DEEPSEEK_API_KEY', '')  # 在 GitHub Secrets 配",
    "DEEPSEEK_KEY = os.environ.get('DEEPSEEK_API_KEY', '') or 'ms-only'  # 已停用 DeepSeek 付费网关（用户退款），恒非空仅兼容旧判断；LLM 全走 ModelScope")

# 2. ask_deepseek 重构：纯 ModelScope，失败重试2次后规则兜底
rep("""def ask_deepseek(payload, purpose='eod', system_text=None):
    \"\"\"统一走 tools/cloud_llm_gateway（预算闸门+远端账本）+ 当日次数预算（≤DS_DAILY_LIMIT 次）；
    任何失败降级为规则文案。system_text 缺省用全局 _ASK_DS_SYS；特殊场景可传独立系统提示词。
    次数用尽时置 _DS_EXHAUSTED=True 并返回 ''（调用方可注明「今日 DS 额度已用」）。\"\"\"
    global _DS_EXHAUSTED
    # —— ModelScope 免费通道优先（成功即返回，不烧 DS 日预算/不记账）——
    if MODELSCOPE_KEY:
        _ms = _modelscope_chat(payload, purpose, system_text or _ASK_DS_SYS)
        if _ms:
            return _ms
        print('[LLM] ModelScope 不可用，自动降级 DeepSeek 付费网关')
    if not DEEPSEEK_KEY:
        return ''
    if _ds_daily_used() >= DS_DAILY_LIMIT:
        _DS_EXHAUSTED = True
        print(f'[LLM] 今日 DS 次数预算已用尽（{_ds_daily_used()}/{DS_DAILY_LIMIT}），降级规则文案')
        return ''
    try:
        from cloud_llm_gateway import chat as _gw_chat
        r = _gw_chat(purpose=purpose,
                     user_text=json.dumps(payload, ensure_ascii=False),
                     system_text=system_text or _ASK_DS_SYS)
        if r.get('ok'):
            _ds_daily_inc()
            if r.get('warn'):
                print('[LLM] 预算预警', r.get('done_cost'))
            _t = r['text']
            if '满仓' in _t or '全仓' in _t:
                _t = _t.replace('满仓', '半仓').replace('全仓', '半仓')
            if any(x in _t for x in ('确定涨停', '必涨', '稳了')):
                _t += '\\n【系统强制风险】短线波动大，严格止损。'
            return _t
        print('[LLM] 未调用:', r.get('reason'))
        return ''
    except Exception as e:
        print('[LLM] 网关异常(降级规则文案):', e)
        return ''""",
    """def ask_deepseek(payload, purpose='eod', system_text=None):
    \"\"\"统一走 ModelScope 免费通道（额度充足不省，max_tokens 3000）。
    已停用 DeepSeek 付费网关（用户申请退款）；失败重试 2 次后返回 ''（调用方规则兜底）。
    system_text 缺省用全局 _ASK_DS_SYS；特殊场景可传独立系统提示词。\"\"\"
    if not MODELSCOPE_KEY:
        return ''
    for _try in range(2):
        _ms = _modelscope_chat(payload, purpose, system_text or _ASK_DS_SYS)
        if _ms:
            return _ms
    print('[LLM] ModelScope 两次尝试均失败，回退规则文案')
    return ''""")

# 3. _modelscope_chat 打印文案：降级 DeepSeek → 规则兜底
rep("print(f'[LLM] ModelScope 认证失败({code})：需绑定阿里云+实名 或 token 无效，降级 DeepSeek')",
    "print(f'[LLM] ModelScope 认证失败({code})：需绑定阿里云+实名 或 token 无效')")
rep("print(f'[LLM] ModelScope http_{code} model={m}，降级 DeepSeek')",
    "print(f'[LLM] ModelScope http_{code} model={m}')")
rep("print(f'[LLM] ModelScope 异常: {str(e)[:120]}，降级 DeepSeek')",
    "print(f'[LLM] ModelScope 异常: {str(e)[:120]}')")
rep("print('[LLM] ModelScope 全部模型不可用，降级 DeepSeek')",
    "print('[LLM] ModelScope 全部模型不可用，规则兜底')")

# 4. 新闻 brief 摘要加长（帮助模型深挖）
rep("brief = [{'t': nw.get('title', ''), 's': (nw.get('summary') or '')[:60]} for nw in news[:n]]",
    "brief = [{'t': nw.get('title', ''), 's': (nw.get('summary') or '')[:120]} for nw in news[:n]]")

# 5. build_news2h._rows：标题下加 📰 原文行
rep("""        out = []
        for it in pairs:
            t0 = it[0]
            i, w, a = (it[1], it[2], it[3]) if len(it) >= 4 else ('', it[1] if len(it) > 1 else '', '')
            i = _strip_pre(i, ('影响：', '影响:'))
            w = _strip_pre(w, ('大白话：', '大白话:', '人话：', '解读：'))
            a = _strip_pre(a, ('操作：', '操作:'))
            out.append(f'<div style=\"color:#fff;font-size:13px;margin:8px 0 0 0;\">· {t0}</div>'""",
    """        out = []
        for it in pairs:
            t0 = it[0]
            i, w, a = (it[1], it[2], it[3]) if len(it) >= 4 else ('', it[1] if len(it) > 1 else '', '')
            i = _strip_pre(i, ('影响：', '影响:'))
            w = _strip_pre(w, ('大白话：', '大白话:', '人话：', '解读：'))
            a = _strip_pre(a, ('操作：', '操作:'))
            _sum = _brief_sum.get(t0, '')
            out.append(f'<div style=\"color:#fff;font-size:13px;margin:8px 0 0 0;\">· {t0}</div>'
                       + (f'<div style=\"margin:2px 0 0 16px;color:{GREY};font-size:11px;\">📰 {_sum}</div>' if _sum else '')""")

# 6. build_news2h 构造 _brief_sum（标题→原文映射）
rep("""    def _rows(pairs, is_good):""",
    """    _brief_sum = {g.get('title', ''): (g.get('summary') or '')[:100] for g in good}
    _brief_sum.update({b.get('title', ''): (b.get('summary') or '')[:100] for b in bad})

    def _rows(pairs, is_good):""")

# 7. _news_html_lines：加原文行
rep("""            t0 = it[0]
            i, w, a = (it[1], it[2], it[3]) if len(it) >= 4 else ('', it[1] if len(it) > 1 else '', '')
            i = _strip_pre(i, ('影响：', '影响:'))
            w = _strip_pre(w, ('大白话：', '大白话:', '人话：', '解读：'))
            a = _strip_pre(a, ('操作：', '操作:'))
            rows.append(f'<div style=\"color:#ced4da;font-size:12px;margin:8px 0 0 0;\">· {t0}</div>'""",
    """            t0 = it[0]
            i, w, a = (it[1], it[2], it[3]) if len(it) >= 4 else ('', it[1] if len(it) > 1 else '', '')
            i = _strip_pre(i, ('影响：', '影响:'))
            w = _strip_pre(w, ('大白话：', '大白话:', '人话：', '解读：'))
            a = _strip_pre(a, ('操作：', '操作:'))
            _sum = _brief_sum.get(t0, '')
            rows.append(f'<div style=\"color:#ced4da;font-size:12px;margin:8px 0 0 0;\">· {t0}</div>'
                        + (f'<div style=\"margin:2px 0 0 16px;color:{GREY};font-size:11px;\">📰 {_sum}</div>' if _sum else '')""")

# 8. _news_html_lines 构造 _brief_sum
rep("    pairs = _news_ds_lines(news, n, purpose_key)\n    if pairs:\n        rows = []",
    "    pairs = _news_ds_lines(news, n, purpose_key)\n    _brief_sum = {nw.get('title', ''): (nw.get('summary') or '')[:100] for nw in news}\n    if pairs:\n        rows = []")

io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('OK', cnt['ok'], '替换；失败：')
for f_ in cnt['fail']:
    print('  [%s] 次数=%s 期望=%s' % f_)
sys.exit(0 if not cnt['fail'] else 1)
