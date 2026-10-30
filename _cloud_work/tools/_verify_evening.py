# -*- coding: utf-8 -*-
"""外盘窗口升级 + 晚间消息汇总专项验证。"""
import io, os, sys, re
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

print('== A. _global_markets 全球采集 ==')
gl = C._global_markets()
ok(isinstance(gl, list) and len(gl) >= 6, f'_global_markets 返回 {len(gl)} 项')
names = [g[0] for g in gl]
for want in ('纳指', '道指', '标普', '恒生', '原油', '黄金', '比特币'):
    ok(want in names, f'含 {want}')
ok(all(isinstance(pct, float) or pct is None for _, pct, _ in gl), '涨跌% 都是 float 或 None（无编造）')
html = C._global_markets_html(gl)
ok('+' in html or '-' in html or '未取得' in html, '区块 HTML 正常渲染')

print('== B. build_ext 升级（全球行情+消息+DS大白话） ==')
src = io.open(r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py', encoding='utf-8').read()
ext = src[src.index('def build_ext'):src.index('def _early_watch')]
ok('全球行情（红涨绿跌）' in ext, 'ext 含全球行情区块')
ok('全球消息速览' in ext, 'ext 含全球消息速览')
ok("ask_deepseek({'task': 'ext_global'" in ext, 'ext 调 DS 大白话汇总')
ok('_TRADER_RULES' in ext and '今晚无大事' in ext, 'ext DS 含交易员规范+无大事兜底')
ok('【全球盘面】' in ext and '【今晚大事】' in ext and '【明天A股怎么看】' in ext and '【最大风险】' in ext,
   'ext DS 四段结构')

print('== C. build_evening 晚间消息汇总 ==')
ev = src[src.index('def build_evening'):src.index('def _early_watch')]
ok('def build_evening' in src, 'build_evening 存在')
ok('今日A股全景' in ev and '全球晚间行情' in ev and '今日消息汇总' in ev, 'evening 三段结构（A股/全球/消息）')
ok("ask_deepseek({'task': 'evening_summary'" in ev, 'evening 调 DS')
ok('【今日大事】' in ev and '【明日关注】' in ev and '【最大风险】' in ev, 'evening DS 三段')
ok('今日无大事，平稳过渡' in ev, 'evening 无强推兜底')
ok("if slot == 'evening':" in src, 'slot 分发含 evening')
ok('晚间消息汇总 {_bj_now().strftime' in src, 'evening push 标题')

print('== D. workflow yml ==')
yml = io.open(r'D:\QuantMonitorV6\.github\workflows\daily-review2.yml', encoding='utf-8').read()
ok("'evening'" in yml, 'inputs options 含 evening')
ok("'50 14 * * 1-5'" in yml, 'cron 22:50 北京 evening')
ok('14:5[0-9])      T=evening' in yml, 'case 14:5x → evening')
ok(re.search(r"14:3\[6-9\]\) T=ext", yml) is not None, 'ext case 仍在（未破坏）')

print('== E. 实跑构建（ext/evening 离屏渲染，DS 走降级或真跑） ==')
try:
    C.DEEPSEEK_KEY = None  # 本地验证不烧云端 DS，走规则兜底
    ex = C.build_ext()
    ok(ex is not None and '全球行情' in ex, 'build_ext 实跑成功（规则兜底）')
    ev2 = C.build_evening()
    ok(ev2 is not None and '今日A股全景' in ev2, 'build_evening 实跑成功（规则兜底）')
except Exception as e:
    ok(False, f'实跑异常: {e}')

print(f'\n===== 结果: {PASS} PASS / {FAIL} FAIL =====')
sys.exit(0 if FAIL == 0 else 1)
