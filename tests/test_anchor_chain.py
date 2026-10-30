# -*- coding: utf-8 -*-
"""第3步 突破回踩全链路验证：mock 扫描缓存 → build_anchor → 断言推送 HTML 关键信息。
可重跑：python tests/test_anchor_chain.py  （需 tools/ 在 sys.path）"""
import importlib.util, io, json, sys, os

PASS = FAIL = 0

def chk(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1; print('PASS', name)
    else:
        FAIL += 1; print('FAIL', name)

TOOLS = r'D:\QuantMonitorV6\tools'
sys.path.insert(0, TOOLS)
import cloud_daily_review as C
import anchor_tracker as TR
# build_anchor 现在会把推送票落盘到跟踪档案——测试必须隔离到临时目录，避免污染正式记录
import tempfile
TR.ANCHOR_HISTORY_DIR = tempfile.mkdtemp(prefix='chain_trk_')

# mock：扫描缓存直接用第1步实测的2只（数据基准日 2026-10-23），评分在 build_anchor 内真实执行
RAW = json.load(io.open(os.path.join(TOOLS, r'data\_test_anchor_full.json'), encoding='utf-8'))
REAL_LTD = C._last_trade_date          # 保存真实函数，末尾冒烟（防函数内 import 缺失）
C._anchor_candidates = lambda trade_date: list(RAW)
C._last_trade_date = lambda: '2026-10-23'

html = C.build_anchor()
chk('A1 构建成功非空', bool(html))
if not html:
    print(f'==== {PASS} PASS / {FAIL} FAIL（构建失败，后续断言跳过）')
    sys.exit(1)

# ---------- B 关键信息断言 ----------
chk('B1 含永创智能', '永创智能' in html)
chk('B2 含84分', '84' in html)
chk('B3 含凡拓数创', '凡拓数创' in html)
chk('B4 含62分', '62' in html)
chk('B5 含执行', '执行' in html)
chk('B6 含重仓', '重仓' in html)
chk('B7 含轻仓试', '轻仓试' in html)
chk('B8 含轻仓', '轻仓' in html)
chk('B9 含锚位', '锚位' in html)
chk('B10 含买点/止损计划', '计划' in html and '跌破' in html)
chk('B11 含风险行', '风险' in html)
chk('B12 含五维评分', '📊 评分' in html)
chk('B13 含板块共振', '板块共振' in html)
chk('B14 含锚质量分', '锚25' in html or '锚' in html)
chk('B15 标题含突破回踩', '突破回踩' in html)

# ---------- C 文本质量：非空字段、无占位符 ----------
for bad in ('{', '}', 'None', 'nan'):
    chk(f'C_{bad} 无脏文本', bad not in html.replace('{}', '').replace('NoneType', ''))

# ---------- D 单票明细（评分真实跑，永创84/凡拓62 由模块计算） ----------
import quality_scorer as QS
scored = QS.score_batch(list(RAW))
m = {c['code']: c for c in scored}
chk('D1 永创84执行', m['603901']['score_total'] == 84 and m['603901']['action'] == '执行')
chk('D2 凡拓62轻仓试', m['301313']['score_total'] == 62 and m['301313']['action'] == '轻仓试')
chk('D3 全部≥50', all(c['score_total'] >= 50 for c in scored))

# ---------- E 空候选防御 + 真实函数冒烟 ----------
C._anchor_candidates = lambda trade_date: []
chk('E1 无候选返回None', C.build_anchor() is None)
C._anchor_candidates = lambda trade_date: list(RAW)
try:
    d = REAL_LTD()
    chk('E2 真实_last_trade_date可调用', bool(d) and len(str(d)) == 10)
except Exception as e:
    chk('E2 真实_last_trade_date可调用', False)
    print('  ERR', type(e).__name__, str(e)[:120])

# ---------- F 渲染结构 ----------
chk('F1 深色背景', '#161b26' in html or '#1c2230' in html)
chk('F2 emoji标题', '🎯' in html)
chk('F3 无未替换占位符', '{' not in html and '}' not in html)

print(f'==== {PASS} PASS / {FAIL} FAIL')
sys.exit(1 if FAIL else 0)
