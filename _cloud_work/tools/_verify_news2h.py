# -*- coding: utf-8 -*-
"""两小时消息汇总 + 旧事件简报独立档 专项验证。"""
import io, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cloud_daily_review as C

PASS, FAIL = 0, 0
def ok(cond, name):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(('  ✓ ' if cond else '  ✗ ') + name)

print('== A. 源码结构 ==')
src = io.open(r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py', encoding='utf-8').read()
ok('def build_news2h():' in src, 'build_news2h 存在')
ok("if slot == 'news2h':" in src, 'main news2h 分支存在')
ok("if slot == 'news':" in src, 'main news 分支存在（旧事件简报独立档）')
ok("build_events('noon' if _bj_now().hour < 14 else 'eod')" in src, 'news 档按时间分 noon/eod')
ok("'news2h': '两小时市场消息汇总'" in src, 'TITLES news2h')
ok("'news': '事件简报'" in src, 'TITLES news')
ok("_news_ds_lines(good, 6, 'news2h_good')" in src, '利好深挖 6 条')
ok("_news_ds_lines(bad, 6, 'news2h_bad')" in src, '利空深挖 6 条')
ok("(MODELSCOPE_KEY or DEEPSEEK_KEY) and news" in src, 'LLM 判断兼容 ModelScope')
ok('【预期差】市场还没消化的消息1-2条' in src, '预期差 prompt')
ok('【明日操作建议】结合持仓给明确仓位档位' in src, '明日操作建议 prompt')
ok('【大白话总结】一句话' in src, '大白话总结 prompt')
ok("get_news(60)" in src, '新闻拉取 60 条')
ok("'max_tokens': 3000" in src, 'max_tokens 3000（不省）')
ok("timeout=120" in src, '超时 120s（防长输出超时）')
ok("'timed out' in str(e).lower()" in src, '超时换备选模型不直接降级')
ok("def _strip_pre" in src, '去重复前缀函数')
ok("len(it[1]) < 12 or (len(it) >= 5 and len(it[2]) < 20)" in src, '代表个股字段长度校验(≥20字)')
ok("pairs[k] = (brief[k]['t'], it[1], it[2], it[3], it[4])" in src, '标题以原始新闻为准')

print('== B. workflow 调度 ==')
wf = io.open(r'D:\QuantMonitorV6\.github\workflows\daily-review2.yml', encoding='utf-8').read()
ok("'news2h'" in wf, 'options 含 news2h')
ok("cron: '0 4,8 * * 1-5'" in wf, '12:00/16:00 news2h cron')
ok("cron: '1 6 * * 1-5'" in wf, '14:01 news2h cron')
ok("cron: '35 7 * * 1-5'" in wf, '15:35 news cron')
ok("cron: '0 2,3,5,6 * * 1-5'" in wf, 'hourly 挪整点 10/11/13/14')
ok('03:4[0-4])      T=news' in wf, '11:40 news case')
ok('07:1[0-4])      T=news' in wf, '15:10 news case')
ok('07:3[5-9])      T=news' in wf, '15:35 news case')
ok('04:00|08:00)    T=news2h' in wf, '12:00/16:00 news2h case')
ok('06:0[1-4])      T=news2h' in wf, '14:01 news2h case')
# case 顺序：news 的 07:xx 必须在 07:* eod 之前
ok(wf.index('07:1[0-4])      T=news') < wf.index('07:*)        T=eod'), 'news 15:10 case 在 eod 之前')
ok(wf.index('07:3[5-9])      T=news') < wf.index('07:*)        T=eod'), 'news 15:35 case 在 eod 之前')
# 无残留旧 hourly case
ok('01:30|02:30|05:30|06:30) T=hourly' not in wf, '旧 hourly case 已移除')

print('== C. 本地构建（规则/降级路径，无 LLM key） ==')
os.environ.pop('MODELSCOPE_API_KEY', None)
os.environ.pop('DEEPSEEK_API_KEY', None)
import importlib
importlib.reload(C)
try:
    h = C.build_news2h()
    ok(h is not None and '两小时市场消息汇总' in h, '无 LLM key 时仍产出卡（降级标题列表）')
    ok('不构成投资建议' in h, '含风险提示')
except Exception as e:
    ok(False, 'build_news2h 无 key 不崩: ' + str(e)[:80])
# news 独立档
try:
    b = C.build_events('noon')
    ok(b is not None, 'build_events noon 档可用（news 卡数据源）')
except Exception as e:
    ok(False, 'build_events noon: ' + str(e)[:80])

print(f'\n===== 结果: {PASS} PASS / {FAIL} FAIL =====')
sys.exit(0 if FAIL == 0 else 1)
