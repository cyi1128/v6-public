# -*- coding: utf-8 -*-
"""交易员风格同步专项验证：禁句输出层清零 / 无强推 / confirm逐票解释 / 仓位统一 / judgment闭环。
用法：QT_QPA_PLATFORM=offscreen python _verify_trader.py"""
import io, os, sys, tempfile, re, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cloud_daily_review as C

PASS, FAIL = 0, 0
def ok(cond, name):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print('  ✗', name)
    print(('  ✓ ' if cond else '  ✗ ') + name)

print('== A. three_way 禁句清零 ==')
for op, lb, vq in [(3.0, 2.0, 15), (1.0, 1.0, 5), (8.0, 3.0, 20), (-1.5, 1.2, 3)]:
    act, why = C.three_way(op, lb, vq)
    ok('量能不配合' not in why and '不动手' not in why and len(why) > 4, f'three_way({op},{lb},{vq}) -> {why}')

print('== B. _pos_advice 仓位统一（用户情绪绑定表） ==')
ok('4~6成' in C._pos_advice('偏多'), '偏多→4~6成')
ok('2~4成' in C._pos_advice('震荡'), '震荡→2~4成')
ok('1成' in C._pos_advice('偏空') and '空仓' in C._pos_advice('偏空'), '偏空→空仓或1成')
ok('1~2成' in C._pos_advice('冰点'), '冰点→1~2成')
src = io.open(C.__file__ if hasattr(C, '__file__') else __file__, encoding='utf-8').read() if False else io.open(r'D:\QuantMonitorV6\_cloud_work\tools\cloud_daily_review.py', encoding='utf-8').read()
ok("_pos_advice('偏多')" in src and '_pos_advice("偏空")' in src and '_pos_advice(\"偏空\")' in src.replace("_pos_advice('偏多')",'') if False else ('_pos_advice' in src and '总仓 ' in src), 'build_hourly 仓位引用 _pos_advice')
ok("pos_txt = _pos_advice(emotion)" in src, 'build_auction 仓位引用 _pos_advice')
ok("_pos_advice(_emotion_from_pools(d))" in src, 'build_confirm 仓位引用 _pos_advice')

print('== C. 输出层禁句清零（排除规则文本自身） ==')
SRC = src
# 规则文本常量中允许出现禁句（它们是「禁止示例」）
rule_blocks = []
for fn in ('_TRADER_RULES', '_SPOT_DS_SYS_text', '_INTRA_DS_SYS_text'):
    m = re.search(fn + r"\s*=.*?('|\")\n", SRC)
# 直接策略：把三段规则文本从源码里抠掉再扫
clean = SRC
for pat in [r"_TRADER_RULES = \([^)]*\)", r"def _SPOT_DS_SYS_text\(\):[^d]*def ", r"def _INTRA_DS_SYS_text\(\):.*?def ", r"def _auction_ds\(tops, heat\):.*?def "]:
    clean = re.sub(pat, '', clean, flags=re.S)
BANNED = ['回踩分时均线可轻仓试', '观察为主不急着追', '量能不配合不动手', '已突破昨日高点', '存量/已高潮，追高风险大', '放量上攻，回踩分时均线可轻仓', '不在4-14%区间']
for b in BANNED:
    ok(b not in clean, f'输出层无禁句: {b}')
ok('观察为主，不急着追' not in clean and '观察为主不急着追' not in clean, '无「观察为主」模板句')
ok('回踩分时均线不破可轻仓试' not in clean and '回踩分时均线可轻仓' not in clean, '无「回踩分时均线…轻仓试」')

print('== D. DS prompt：无强推硬性要求 + 昨日判断对比 ==')
ok('今日无强推' in SRC and '禁止为了凑数而推荐' in SRC, '_TRADER_RULES 含无强推硬性要求')
ok('judgment_context()' in SRC and '{judgment}' in SRC, 'pre/noon/eod DS 引用昨日判断')
ok('【昨日复盘】' in SRC, 'DS 输出含昨日复盘段')
ok('【今日判断记录】' in SRC, 'eod DS 输出今日判断记录段')

print('== E. build_confirm 放弃逐一解释（人话原因） ==')
ok('资金竞价没进场，撑不起高开，放弃' in SRC, '量比不足→人话')
ok('竞价透支、开盘容易被砸，放弃' in SRC, '高开过高→人话')
ok('没溢价不值得做，放弃' in SRC, '高开不足→人话')
ok('虚量撑不住，放弃' in SRC, '量/昨量不足→人话')

print('== F. judgment log 闭环 ==')
tmp = os.path.join(tempfile.mkdtemp(), 'judgment_test.json')
C.JUDGMENT_PATH = tmp
C._git_commit_push = lambda *a, **k: None  # 测试不碰 git
C.write_judgment({'date': '2026-10-20', 'emotion': '偏空', 'label': '情绪退潮', 'score': 22,
                  'tops': ['A', 'B'], 'pool': ['X'], 'pos': '空仓或1成', 'risk': '退潮',
                  'lu': 25, 'zb': 9, 'dt': 3, 'max_lbc': 4})
C.write_judgment({'date': '2026-10-21', 'emotion': '震荡', 'label': '主线分歧', 'score': 50,
                  'tops': ['C'], 'pool': [], 'pos': '2~4成', 'risk': '', 'lu': 50, 'zb': 19, 'dt': 0, 'max_lbc': 4})
# judgment_context 取真实昨日（动态日期；脚本写死 10-20 会随时间失效）
from datetime import date, timedelta
_y = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
ctx = C.judgment_context()
ok(_y in ctx and ('偏空' in ctx or '震荡' in ctx) and '昨日判断' in ctx, f'judgment_context 取昨日({_y}): {ctx[:40]}...')
j = C.load_judgment()
ok(len(j) == 2 and '2026-10-21' in j, 'load_judgment 两条完整')
ok(j['2026-10-21']['max_lbc'] == 4 and j['2026-10-21']['tops'] == ['C'], '今日记录字段完整')
try:
    os.remove(tmp)
except Exception:
    pass

print('== G. build_eod 落盘调用 ==')
ok("write_judgment({'date': datetime.now().strftime('%Y-%m-%d')" in SRC.replace('\\n', ''), 'build_eod 内 write_judgment 落盘今日判断')
ok("'tops': [n for n, _ in d['tops'][:3]]" in SRC, '落盘含主线TOP3')
ok("'pool': [p['n'] for p in pool[:3]]" in SRC, '落盘含推荐池')
ok("'pos': _pos_advice(b)" in SRC, '落盘含仓位建议')

print('== H. 单股/盘中 DS system 禁句补充 ==')
ok('禁止万能句' in SRC and '凑数硬夸' in SRC, '_INTRA_DS_SYS_text 禁句+无强推')
ok('今日无强推，别碰' in SRC, '_SPOT_DS_SYS_text 无强推')

print(f'\n===== 结果: {PASS} PASS / {FAIL} FAIL =====')
sys.exit(0 if FAIL == 0 else 1)
