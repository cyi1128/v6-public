# -*- coding: utf-8 -*-
import io
P = r'D:\QuantMonitorV6\_cloud_work\tools\_verify_news2h.py'
s = io.open(P, encoding='utf-8').read()
old = ('ok("_news_ds_lines(good, 4, \'news2h_good\')" in src, \'利好逐条大白话接入\')\n'
       'ok("_news_ds_lines(bad, 4, \'news2h_bad\')" in src, \'利空逐条大白话接入\')\n'
       'ok("(MODELSCOPE_KEY or DEEPSEEK_KEY) and news" in src, \'LLM 判断兼容 ModelScope\')\n'
       'ok(\'【预期差】市场还没消化的消息1-2条\' in src, \'预期差 prompt\')\n'
       'ok(\'【明日操作建议】结合持仓给明确仓位档位\' in src, \'明日操作建议 prompt\')')
new = ('ok("_news_ds_lines(good, 6, \'news2h_good\')" in src, \'利好深挖 6 条\')\n'
       'ok("_news_ds_lines(bad, 6, \'news2h_bad\')" in src, \'利空深挖 6 条\')\n'
       'ok("(MODELSCOPE_KEY or DEEPSEEK_KEY) and news" in src, \'LLM 判断兼容 ModelScope\')\n'
       'ok(\'【预期差】市场还没消化的消息1-2条\' in src, \'预期差 prompt\')\n'
       'ok(\'【明日操作建议】结合持仓给明确仓位档位\' in src, \'明日操作建议 prompt\')\n'
       'ok(\'【大白话总结】一句话\' in src, \'大白话总结 prompt\')\n'
       'ok("get_news(60)" in src, \'新闻拉取 60 条\')\n'
       'ok("\'max_tokens\': 3000" in src, \'max_tokens 3000（不省）\')\n'
       'ok("timeout=120" in src, \'超时 120s（防长输出超时）\')\n'
       "ok(\"'timed out' in str(e).lower()\" in src, '超时换备选模型不直接降级')\n"
       'ok("def _strip_pre" in src, \'去重复前缀函数\')\n'
       'ok("len(it[1]) < 12 or len(it[2]) < 12 or len(it[3]) < 10" in src, \'逐字段长度校验防偷懒\')\n'
       'ok("pairs[k] = (brief[k][\'t\'], it[1], it[2], it[3])" in src, \'标题以原始新闻为准\')')
assert old in s, 'anchor not found'
s = s.replace(old, new)
io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('updated')
