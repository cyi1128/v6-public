# -*- coding: utf-8 -*-
"""拉升识别位置门槛（MARKUP_POS_MAX=0.45）专项验证 —— 可重跑。

对应 tools\\_apply_markup_pos45.py（一次性补丁）。四段：
  [A] 常量与源码层：值 = 0.45；25 个 MARKUP_* 常量与备份逐项比对只有新增项不同；
      detect_markup 源码与备份比对，剔掉本次新增的行后逐字一致；reason 格式；
      静态 / 实例两种调法都能走。
  [B] 边界（合成数据，把 pos 精确顶在 0.45 两侧）：0.4499 放行 / 0.4500 拦下 / 0.4501 拦下。
  [C] 真实数据（kline_cache）：自动搜出夹住 0.45 的临界样本；把常量临时改成 1.01 后
      高位样本变为放行（证明差异来自本次改动），验完改回；统计被门槛拦下的只数。
  [D] DB：markup_ok=1 的记录独立重算 pos120 必须全部 < 0.45；
      pos120 >= 0.45 的记录 markup_ok 必须全为 0；引擎漏斗必须有 'pos' 键。
"""
import io
import os
import re
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = r'D:\QuantMonitorV6'
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import numpy as np                      # noqa: E402
import pandas as pd                     # noqa: E402

import strategy.base as B               # noqa: E402
import services.band_pattern_engine as E  # noqa: E402

OUT = os.path.join(ROOT, 'tools', 'markup_pos45_verify.txt')
_lines = []
PASS = FAIL = 0


def P(*a):
    t = ' '.join(str(x) for x in a)
    print(t, flush=True)
    _lines.append(t)


def check(name, cond, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        P('  PASS  %s %s' % (name, extra))
    else:
        FAIL += 1
        P('  FAIL  %s %s' % (name, extra))


TI = B.TechnicalIndicators


# ---------------- 合成数据：把 pos120 顶到指定值 ----------------
def make_df(pos_target, n=130):
    """构造一段 K 线，使 (close[-1]-min120)/(max120-min120) == pos_target。

    120 日窗口取最后 120 根；把收盘价固定在 [10, 20]，最后一根 = 10 + pos*10。
    """
    base = np.full(n, 12.0)
    base[-120:] = 12.0
    base[-120] = 10.0        # 窗口内最低
    base[-121] = 20.0 if n >= 121 else 20.0   # 窗口外，避免影响 min/max
    base[-60] = 20.0         # 窗口内最高
    base[-1] = 10.0 + float(pos_target) * 10.0
    close = base
    open_ = close * 0.995
    high = close * 1.01
    low = close * 0.99
    vol = np.full(n, 1000.0)
    df = pd.DataFrame({'open': open_, 'high': high, 'low': low, 'close': close, 'volume': vol})
    return df


def pos_of(df):
    c = np.asarray(df['close'].values, dtype=float)
    c120 = c[-120:]
    _mn, _mx = float(np.min(c120)), float(np.max(c120))
    return (float(c[-1]) - _mn) / (_mx - _mn + 1e-8)


P('=' * 100)
P('拉升识别位置门槛验证（MARKUP_POS_MAX=0.45）  %s' % __import__('datetime').datetime.now())
P('=' * 100)

# ============================ [A] 常量与源码 ============================
P('\n[A] 常量与源码层')
P('-' * 100)
check('MARKUP_POS_MAX == 0.45', B.MARKUP_POS_MAX == 0.45, repr(B.MARKUP_POS_MAX))

_rd = lambda p: io.open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')   # 统一成 \n 再比对
src = _rd(os.path.join(ROOT, 'strategy', 'base.py'))
bak = _rd(os.path.join(ROOT, 'strategy', 'base.py.bak_before_markup_pos45'))


def consts(text):
    d = {}
    for m in re.finditer(r'^(MARKUP_[A-Z0-9_]+)\s*=\s*([^\n#]+)', text, re.M):
        d[m.group(1)] = m.group(2).strip()
    return d


cb, cs = consts(bak), consts(src)
added = sorted(set(cs) - set(cb))
changed = sorted(k for k in cb if k in cs and cb[k] != cs[k])
removed = sorted(set(cb) - set(cs))
check('常量：只新增 MARKUP_POS_MAX', added == ['MARKUP_POS_MAX'] and changed == [] and removed == [],
      '新增=%s 改了=%s 删了=%s' % (added, changed, removed))
check('常量总数 +1（只多 MARKUP_POS_MAX）', len(cs) == len(cb) + 1, '%d -> %d' % (len(cb), len(cs)))
check('门槛比较符用的是 >=（恰好等于门槛也要拦）', src.count('if pos >= MARKUP_POS_MAX:') == 1,
      '出现 %d 次' % src.count('if pos >= MARKUP_POS_MAX:'))
check('备份里没有这行门槛', bak.count('if pos >= MARKUP_POS_MAX:') == 0)


def func_src(text, name):
    i = text.index('def %s(' % name)
    j = text.index('\n    @staticmethod', i + 10) if '\n    @staticmethod' in text[i:] else len(text)
    seg = text[i:i + (j - i)]
    return seg


DOC_PARAGRAPH = """        前置：位置 pos120 < MARKUP_POS_MAX(0.45)（1010m 新增）。
        依据 tools\\\\markup_calib.txt：整体命中的均值增量只有 +0.06pp（噪音），
        只有 pos<0.45 那一段是正期望（+1.10% / 胜率 54.3% / t=+3.31），
        pos>=0.45 三档全部显著为负 -> 高位一律不判「拉升」。
        边界：0.45 归入负期望档，故判定写 pos >= MARKUP_POS_MAX 即拦。
        ⚠ 连带后果：形态②缩量强势要求 pos>=0.55，被本门槛完全覆盖后【不可达】。

"""
GATE = """            # 位置门槛（1010m）：只保留低位有效子集，高位一律不判拉升（依据见 MARKUP_POS_MAX 注释）
            r = dict(_bad)
            r['pos120'] = float(pos)
            if pos >= MARKUP_POS_MAX:
                r['reason'] = 'pos>=%.2f' % MARKUP_POS_MAX
                return r
"""
DEC_ANCHOR = """        判据
        ----
"""
POS_ANCHOR = """            pos = (float(c[-1]) - _mn) / (_mx - _mn + 1e-8)
"""

fs_new, fs_old = func_src(src, 'detect_markup'), func_src(bak, 'detect_markup')
# 构造式比对：新函数 == 备份函数 + 恰好这两处插入（docstring 段 + 门槛块），其余逐字一致
expected = fs_old.replace(DEC_ANCHOR, DOC_PARAGRAPH + DEC_ANCHOR, 1)
expected = expected.replace(POS_ANCHOR, POS_ANCHOR + GATE, 1)
check('detect_markup == 备份 + 恰好两处插入（docstring 段 + 门槛块），其余逐字一致',
      fs_new == expected, '新 %d / 构造 %d / 备份 %d 字符' % (len(fs_new), len(expected), len(fs_old)))
check('detect_markup 源码确实变了', len(fs_new) > len(fs_old), '+%d 字符' % (len(fs_new) - len(fs_old)))

df_over = make_df(0.4501)                       # pos 略高于门槛 -> 必被拦
r_over = TI.detect_markup(df_over)
check('门槛触发时 reason 格式 = "pos>=0.45"', r_over.get('reason') == 'pos>=0.45', repr(r_over.get('reason')))
check('门槛触发时 ok=False / type 为空',
      r_over.get('ok') is False and (r_over.get('type') or '') == '')
check('门槛触发时 pos120 仍照常回填', isinstance(r_over.get('pos120'), float),
      repr(r_over.get('pos120')))
check('reason.startswith("pos>")（引擎漏斗据此分类）', (r_over.get('reason') or '').startswith('pos>'))
try:
    _inst = TI()
    r_inst = _inst.detect_markup(df_over)
    check('实例调法也能走（返回同结构）', r_inst.get('reason') == r_over.get('reason'))
except Exception as _e:
    check('实例调法也能走（返回同结构）', False, '%s: %s' % (type(_e).__name__, _e))

# ============================ [B] 边界 ============================
P('\n[B] 边界（合成数据，pos 精确顶在 0.45 两侧）')
P('-' * 100)
# 注意：0.45 在二进制浮点里不可精确表示（10 + 0.45*10 实际算得 0.44999999999999996），
# 所以「恰好等于门槛」这一档用可精确表示的 0.5 单独做（见下），不要拿 0.45 当等值用例。
cases = [(0.30, False), (0.4499, False), (0.449999, False), (0.4501, True), (0.80, True)]
for tgt, should_block in cases:
    d = make_df(tgt)
    actual_pos = pos_of(d)
    r = TI.detect_markup(d)
    blocked = (r.get('reason') or '').startswith('pos>')
    check('pos=%.6f -> %s' % (actual_pos, '拦下' if should_block else '放行'),
          blocked == should_block, 'reason=%r' % (r.get('reason') or ''))

_save_eq = B.MARKUP_POS_MAX
d_eq = make_df(0.5)
_cc = np.asarray(d_eq['close'].values, dtype=float)
_c120 = _cc[-120:]
# 用与 detect_markup 完全相同的公式算出「该样本的 pos」，再把它设成门槛 ——
# 这样两边是同一个浮点结果，能真正考出「相等时是否拦下」（考 >= 还是 >）。
_pos_exact = (float(_cc[-1]) - float(np.min(_c120))) / (float(np.max(_c120)) - float(np.min(_c120)) + 1e-8)
B.MARKUP_POS_MAX = _pos_exact
try:
    r_eq = TI.detect_markup(d_eq)
    check('恰好等于门槛（pos=%.17g，门槛设成同一个浮点值）-> 拦下（证明用 >= 而非 >）' % _pos_exact,
          (r_eq.get('reason') or '').startswith('pos>'),
          'reason=%r pos120=%r' % (r_eq.get('reason') or '', r_eq.get('pos120')))
finally:
    B.MARKUP_POS_MAX = _save_eq
check('常量已改回 0.45（等值用例后）', B.MARKUP_POS_MAX == 0.45, repr(B.MARKUP_POS_MAX))

# ============================ [C] 真实数据 ============================
P('\n[C] 真实数据（kline_cache，抽样找夹住 0.45 的临界样本）')
P('-' * 100)
import duckdb                           # noqa: E402

DDB = os.path.join(ROOT, 'data', 'cache', 'kline_cache.duckdb')
con = duckdb.connect(DDB, read_only=True)
codes = [r[0] for r in con.execute(
    "SELECT code FROM kline_cache_meta ORDER BY code").fetchall()]
try:
    limit = int(os.environ.get('MP45_SAMPLE', '400'))
except Exception:
    limit = 400
step = max(1, len(codes) // limit)
sample = codes[::step][:limit]

rows = []
for code in sample:
    try:
        q = con.execute(
            "SELECT date, open, high, low, close, volume FROM kline_cache WHERE code=? ORDER BY date",
            [code]).fetchall()
        if len(q) < 120:
            continue
        df = pd.DataFrame(q, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
        c120 = df['close'].values[-120:].astype(float)
        pos = (float(c120[-1]) - float(np.min(c120))) / (float(np.max(c120)) - float(np.min(c120)) + 1e-8)
        r = TI.detect_markup(df)
        reason = r.get('reason') or ''
        rows.append((code, q[-1][0], float(pos), bool(r.get('ok')), reason))
    except Exception:
        continue
con.close()
check('真实样本量 >= 200', len(rows) >= 200, '%d 只' % len(rows))

blocked_rows = [x for x in rows if x[4].startswith('pos>')]
scored_rows = [x for x in rows if not x[4].startswith('pos>') and not x[4]]
check('样本里确实有被门槛拦下的（>0）', len(blocked_rows) > 0, '%d 只' % len(blocked_rows))
check('被拦下的样本 pos 全部 >= 0.45', all(x[2] >= 0.45 for x in blocked_rows),
      '最低 %.4f' % (min([x[2] for x in blocked_rows]) if blocked_rows else -1))
check('未被拦下的样本 pos 全部 < 0.45',
      all(x[2] < 0.45 for x in scored_rows + [y for y in rows if y[4] and not y[4].startswith('pos>')]),
      '最高 %.4f' % (max([x[2] for x in scored_rows]) if scored_rows else -1))

# 自动搜临界样本
lo_ok = [x for x in rows if x[2] < 0.45]
hi_no = [x for x in rows if x[2] >= 0.45]
if lo_ok and hi_no:
    a = max(lo_ok, key=lambda x: x[2])     # 最贴近门槛的放行样本
    b = min(hi_no, key=lambda x: x[2])     # 最贴近门槛的拦下样本
    P('  临界样本（放行侧）：%s %s pos=%.4f ok=%s reason=%r' % (a[0], a[1], a[2], a[3], a[4]))
    P('  临界样本（拦下侧）：%s %s pos=%.4f ok=%s reason=%r' % (b[0], b[1], b[2], b[3], b[4]))
    check('临界样本夹住 0.45（放行侧 < 0.45 <= 拦下侧）', a[2] < 0.45 <= b[2],
          '%.4f < 0.45 <= %.4f' % (a[2], b[2]))
    # 开关可逆：临时放到 1.01
    _save = B.MARKUP_POS_MAX
    B.MARKUP_POS_MAX = 1.01
    try:
        d = None
        con2 = duckdb.connect(DDB, read_only=True)
        q = con2.execute(
            "SELECT date, open, high, low, close, volume FROM kline_cache WHERE code=? ORDER BY date",
            [b[0]]).fetchall()
        con2.close()
        d = pd.DataFrame(q, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
        r2 = TI.detect_markup(d)
        check('把 MARKUP_POS_MAX 临时改 1.01 后，同一只不再被位置拦下',
              not (r2.get('reason') or '').startswith('pos>'),
              'reason=%r' % (r2.get('reason') or ''))
    finally:
        B.MARKUP_POS_MAX = _save
    check('常量已改回 0.45', B.MARKUP_POS_MAX == 0.45, repr(B.MARKUP_POS_MAX))
else:
    check('自动搜出临界样本', False, '放行侧 %d 只 / 拦下侧 %d 只' % (len(lo_ok), len(hi_no)))

# ============================ [D] DB ============================
P('\n[D] DB（band_pattern.db 的 markup_ok 与独立重算 pos120）')
P('-' * 100)
check("引擎 _MARKUP_FUNNEL 有 'pos' 键", 'pos' in E._MARKUP_FUNNEL, str(sorted(E._MARKUP_FUNNEL)))
DBP = os.path.join(ROOT, 'data', 'cache', 'band_pattern.db')
c = sqlite3.connect(DBP)
tot = c.execute('SELECT COUNT(*) FROM pattern_record').fetchone()[0]
markup1 = c.execute('SELECT code FROM pattern_record WHERE markup_ok=1').fetchall()
P('  DB 总记录 %d 条，其中 markup_ok=1 共 %d 条' % (tot, len(markup1)))
check('markup_ok=1 的记录数 > 0', len(markup1) > 0)
check('markup_ok=1 的记录数 明显少于改动前的 50（门槛在起作用）', len(markup1) < 50, '%d 条' % len(markup1))

codes1 = [r[0] for r in markup1]
q_marks = ','.join('?' * len(codes1)) if codes1 else ''
allrows = c.execute('SELECT code, markup_ok FROM pattern_record').fetchall()
c.close()

con3 = duckdb.connect(DDB, read_only=True)
bad_hi, bad_lo, checked = [], [], 0
for code, mok in allrows:
    q = con3.execute(
        "SELECT close FROM kline_cache WHERE code=? ORDER BY date", [code]).fetchall()
    if len(q) < 120:
        continue
    cc = np.asarray([x[0] for x in q[-120:]], dtype=float)
    pos = (float(cc[-1]) - float(np.min(cc))) / (float(np.max(cc)) - float(np.min(cc)) + 1e-8)
    checked += 1
    if mok == 1 and pos >= 0.45:
        bad_hi.append((code, round(pos, 4)))
    if mok == 0 and code in codes1:
        bad_lo.append((code, round(pos, 4)))
con3.close()
check('逐只独立重算覆盖 >= 200 条', checked >= 200, '%d 条' % checked)
check('markup_ok=1 的记录 pos120 全部 < 0.45', not bad_hi, '越界=%s' % bad_hi[:5])
check('改前会命中、现在被门槛拦下的记录 markup_ok 全为 0', not bad_lo, '异常=%s' % bad_lo[:5])

P('\n' + '=' * 100)
P('总计：PASS %d ｜ FAIL %d' % (PASS, FAIL))
P('=' * 100)
io.open(OUT, 'w', encoding='utf-8').write('\n'.join(_lines) + '\n')
print('已写出 %s' % OUT)
