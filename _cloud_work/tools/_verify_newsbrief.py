# -*- coding: utf-8 -*-
"""新闻逐条大白话解读专项验证（离线断言 + 解析器单测）。"""
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
ok('def _news_ds_lines(news, n=10, purpose_key=' in src, '_news_ds_lines 存在')
ok('def _parse_ds_json(t):' in src, '_parse_ds_json 存在')
ok('def _news_html_lines(news, n=10, purpose_key=' in src, '_news_html_lines 存在')
ok('{"items":[{"t":"消息标题","i":"影响' in src, 'DS 要求 JSON 三要素输出')
ok('禁止关键词缩写' in src, '禁止缩写/偷懒')
ok('"s":"代表个股深挖：点名1-2只能代表这条消息的股票代码+名称' in src, '代表个股深挖要素')
ok('🏆 代表个股' in src, '🏆 代表个股渲染行')
ok("_news_html_lines(news, n=8, purpose_key='ext_news'" in src, 'build_ext 接入逐条解读')
ok("_news_html_lines(news, n=12, purpose_key='eve_news'" in src, 'build_evening 接入逐条解读')
ok("return '<div>' + rows + '</div>', False" in src, 'DS 失败降级纯标题路径存在')
ok("_parse_ds_json(t)" in src and "pairs = _parse_ds_json(t)" in src, '解析器被调用')

print('== B. 解析器单测 ==')
ok(C._parse_ds_json('{"items":[{"t":"A","p":"解读A"},{"t":"B","p":"解读B"}]}') == [('A', '', '', '解读A', ''), ('B', '', '', '解读B', '')],
   '标准 JSON 解析')
ok(C._parse_ds_json('```json\n{"items":[{"t":"X","p":"Y"}]}\n```') == [('X', '', '', 'Y', '')], 'markdown 代码块包裹解析')
ok(C._parse_ds_json('{"data":[{"title":"T1","note":"N1"}]}') == [('T1', '', '', 'N1', '')], 'data/title/note 别名解析')
ok(C._parse_ds_json('not json at all') is None, '坏 JSON → None（降级）')
ok(C._parse_ds_json('') is None, '空串 → None')
ok(C._parse_ds_json('{"items":[]}') is None, '空数组 → None')

print('== C. 降级路径（无 LLM key → 纯标题） ==')
os.environ.pop('MODELSCOPE_API_KEY', None)
os.environ.pop('DEEPSEEK_API_KEY', None)
import importlib
importlib.reload(C)
news = [{'title': '测试新闻一', 'summary': '', 'ts': '2026-10-21 22:00:00'},
        {'title': '测试新闻二', 'summary': '', 'ts': '2026-10-21 22:01:00'}]
h, used = C._news_html_lines(news, n=2, purpose_key='ext_news')
ok(used is False, '无 key 时 used=False（纯标题）')
ok('测试新闻一' in h and '测试新闻二' in h, '标题完整展示')
ok('👉' not in h, '无 key 时不出现大白话（不编造）')

print(f'\n===== 结果: {PASS} PASS / {FAIL} FAIL =====')
sys.exit(0 if FAIL == 0 else 1)
