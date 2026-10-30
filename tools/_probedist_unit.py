# -*- coding: utf-8 -*-
"""试盘识别 / 出货形态确认 的验证套件。

[A] 造数单测：两个因子的典型形态 + 边界 + 分数分段不重叠
[B] 真实数据：kline_cache 抽 300 只，两因子的分数/命中分布 + 无未来数据核对
[C] _ctrl_note 文案追加与开关；旧参数组合与改动前逐字等价
[D] 落盘链路：DB 5 个新列 + note 与字段一致
输出 tools\\probedist_unit.txt
"""
import importlib.machinery
import importlib.util
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'D:\QuantMonitorV6')
OUT = r'D:\QuantMonitorV6\tools\probedist_unit.txt'
BAK = r'D:\QuantMonitorV6\services\band_pattern_engine.py.bak_before_probedist'
_lines = []


def P(*a):
    s = ' '.join(str(x) for x in a)
    _lines.append(s)
    print(s, flush=True)


PASS = [0, 0]


def check(name, cond, extra=''):
    if cond:
        PASS[0] += 1
        P('  PASS  %s %s' % (name, extra))
    else:
        PASS[1] += 1
        P('  FAIL  %s %s' % (name, extra))


import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from strategy.base import TechnicalIndicators as TI  # noqa: E402
import services.band_pattern_engine as E  # noqa: E402

P('=' * 100)
P('试盘识别 / 出货形态确认 验证')
P('=' * 100)


def df_of(o, h, l, c, v):
    return pd.DataFrame({'open': o, 'high': h, 'low': l, 'close': c, 'volume': v})


def flat(n=80, px=8.0, volv=100.0):
    return ([px] * n, [px * 1.012] * n, [px * 0.994] * n, [px * 1.006] * n,
            [volv] * n)


def hist(n, lo=8.0, hi=9.6, tail=6, volv=100.0):
    """前段从 hi 线性回落到 lo（拉开 120 日区间），最后 tail 根横盘在 lo。

    这样「现价」天然处在区间下沿附近（pos 低），才符合「试盘多在低位/中位」的前提。
    """
    o, h, l, c, v = [], [], [], [], []
    for i in range(n):
        p = hi - (hi - lo) * i / (n - tail - 1) if i < n - tail else lo
        c.append(p)
        o.append(p * 0.998)
        h.append(p * 1.008)
        l.append(p * 0.992)
        v.append(volv)
    return o, h, l, c, v


# ============================================================ A
P('')
P('[A] 造数单测')

# ---------- 试盘：典型形态 ----------
def mk_probe(n=90, spike=0.075, long_shadow=True, vol_mult=3.0, after_shrink=0.5,
             hold=True, pos_high=False, pending=False):
    o, h, l, c, v = hist(n)
    if pos_high:      # 把近 40 根抬到区间顶部，制造 pos120 很高
        for i in range(n - 40, n):
            p = 9.5 - abs(i - (n - 25)) * 0.01
            c[i], o[i], h[i], l[i] = p, p * 0.998, p * 1.008, p * 0.992
    p = n - 1 if pending else n - 4
    pc = c[p - 1]
    o[p] = pc
    h[p] = pc * (1 + spike)
    l[p] = pc * 0.995
    c[p] = h[p] * 0.995 if not long_shadow else pc * 1.02
    v[p] = 100.0 * vol_mult
    for i in range(p + 1, n):
        o[i] = c[i] = c[p] * 0.998
        h[i] = c[p] * 1.005
        l[i] = c[p] * 0.99 if hold else c[p] * 0.90
        v[i] = 100.0 * after_shrink
    return df_of(o, h, l, c, v)


r = TI.detect_probe(mk_probe())
P('  典型试盘: ok=%s stage=%s score=%.1f n_ok=%d shadow=%.3f spike=%.3f vr=%.2f after=%.2f'
  % (r['ok'], r['stage'], r['score'], r['n_ok'], r['shadow_ratio'],
     r['spike'], r['vol_ratio'], r['post_vol_ratio']))
check('典型试盘形态 -> ok=True / stage=confirmed', r['ok'] and r['stage'] == 'confirmed')
check('ok=True 时分数 >= 70（两段不重叠）', r['score'] >= 70.0, '%.1f' % r['score'])
check('P1~P6 六条全 True', r['n_ok'] == 6, str(r['hits']))

r2 = TI.detect_probe(mk_probe(long_shadow=False))
check('收长阳（无上影）-> 不成立', not r2['ok'], 'score=%.1f' % r2['score'])
check('未通过时分数 <= 60', r2['score'] <= 60.0, '%.1f' % r2['score'])

r3 = TI.detect_probe(mk_probe(spike=0.02))
check('冲高只有 2%（不足 5%）-> 不成立', not r3['ok'])

r4 = TI.detect_probe(mk_probe(vol_mult=1.05))
check('试盘日没有放量（1.05倍）-> 不成立', not r4['ok'])

r5 = TI.detect_probe(mk_probe(hold=False))
check('试盘后跌破试盘日低点（超 3%）-> 不成立', not r5['ok'],
      'score=%.1f hits=%s' % (r5['score'], r5['hits']))

r6 = TI.detect_probe(mk_probe(pending=True))
check('试盘日就是最后一根 -> pending、不出结论', r6['stage'] == 'pending' and not r6['ok'])
check('pending 分数也 <= 60', r6['score'] <= 60.0, '%.1f' % r6['score'])

r7 = TI.detect_probe(mk_probe(pos_high=True))
check('高位长上影（pos>0.75）-> 直接排除（归出货形态）',
      not r7['ok'] and r7['reason'].startswith('pos>'), r7['reason'])

r8 = TI.detect_probe(df_of(*hist(90)))
check('一路下跌后横盘、无冲高 -> 不成立且分数低', not r8['ok'] and r8['score'] <= 30.0,
      '%.1f reason=%s' % (r8['score'], r8['reason']))

# 边界
check('bars<60 -> reason', TI.detect_probe(df_of(*flat(59)))['reason'] == 'bars<60')
check('df=None 不抛异常', TI.detect_probe(None)['ok'] is False)
_o, _h, _l, _c, _v = hist(90)
_d = df_of(_o, _h, _l, _c, _v)
_d['close'] = np.array([np.nan] * 90)
check('含 NaN 不抛异常', TI.detect_probe(_d)['ok'] is False)
_d3 = pd.DataFrame({'open': _o, 'high': _h, 'low': _l, 'close': _c})
check('缺 volume 列 -> reason=missing:volume',
      TI.detect_probe(_d3)['reason'] == 'missing:volume')


# ---------- 出货形态 ----------
def mk_stall(n=120):
    o, h, l, c, v = flat(n, px=9.0)
    for i in range(n):                      # 稳步上涨 -> 高位
        c[i] = 9.0 + i * 0.03
        o[i], h[i], l[i] = c[i] - 0.02, c[i] + 0.05, c[i] - 0.06
    # 最后一根：高开冲高（创/近前高）但收盘弱、量能显著放大
    o[-1], h[-1], c[-1], l[-1] = (c[-2] * 1.010, c[-2] * 1.020,
                                  c[-2] * 1.005, c[-2] * 0.995)
    v[-1] = 300.0
    return df_of(o, h, l, c, v)


def mk_break(n=120):
    o, h, l, c, v = flat(n, px=8.0)
    for i in range(0, 60):                  # 低位一段（拉开 120 日区间）
        c[i] = 7.9 + (i % 5) * 0.01
        o[i], h[i], l[i] = c[i] - 0.05, c[i] + 0.05, c[i] - 0.12
    for i in range(60, n - 1):              # 平台 9.8~10.2
        c[i] = 10.0 + 0.02 * ((i - 60) % 3)
        o[i], h[i], l[i] = c[i] - 0.03, 10.2, 9.8
    o[-1], h[-1], c[-1], l[-1] = 9.95, 9.98, 9.50, 9.45
    v[-1] = 300.0
    return df_of(o, h, l, c, v)


def mk_dtop(n=120):
    o, h, l, c, v = flat(n, px=9.0)
    for i in range(0, n - 20):              # 拉到第一个顶
        c[i] = 9.0 + i * 0.025
        o[i], h[i], l[i] = c[i] - 0.02, c[i] + 0.04, c[i] - 0.05
    t1 = n - 20
    h[t1], c[t1], o[t1], l[t1] = 12.00, 11.90, 11.80, 11.75
    for i in range(t1 + 1, n - 6):          # 回撤到 11.0（颈线）
        c[i] = 11.05
        o[i], h[i], l[i] = 11.10, 11.20, 11.00
    t2 = n - 6
    for i in range(t2, n):                  # 二次冲高 11.98（接近但不过前高）
        pass
    o[t2], h[t2], c[t2], l[t2] = 11.20, 11.50, 11.45, 11.15
    t2b = n - 5
    o[t2b], h[t2b], c[t2b], l[t2b] = 11.45, 11.98, 11.55, 11.40
    for i in range(t2b + 1, n):             # 冲高回落到颈线附近
        o[i], h[i], c[i], l[i] = 11.55 - (i - t2b) * 0.12, 11.60, 11.20, 11.10
    v[t1 - 1:t1 + 2] = [120.0, 150.0, 130.0]
    v[t2b - 1:t2b + 2] = [60.0, 70.0, 65.0]
    return df_of(o, h, l, c, v)


for _fn, _exp, _name in ((mk_stall, '高位放量滞涨', '①高位放量滞涨'),
                         (mk_break, '高位破位', '②高位破位'),
                         (mk_dtop, '双顶雏形', '③双顶雏形')):
    _r = TI.detect_distribution_pattern(_fn())
    P('  %s: ok=%s type=%s score=%.1f n_ok=%d' % (_name, _r['ok'], _r['type'],
                                                   _r['score'], _r['n_ok']))
    check('%s 造数 -> 命中且类型正确' % _name, _r['ok'] and _r['type'] == _exp,
          'type=%s' % _r['type'])
    check('%s ok 时分数 >= 70' % _name, _r['score'] >= 70.0, '%.1f' % _r['score'])

_r = TI.detect_distribution_pattern(df_of(*flat(120)))
check('横盘无形态 -> 不命中且分数 <= 30', not _r['ok'] and _r['score'] <= 30.0,
      '%.1f' % _r['score'])
check('未命中时分数 <= 60', _r['score'] <= 60.0)
check('bars<60 -> reason', TI.detect_distribution_pattern(df_of(*flat(59)))['reason'] == 'bars<60')
check('detect_distribution_pattern(None) 不抛异常',
      TI.detect_distribution_pattern(None)['ok'] is False)
check('缺 volume 列 -> reason', TI.detect_distribution_pattern(
    pd.DataFrame({'open': [1.0] * 70, 'high': [1.0] * 70, 'low': [1.0] * 70,
                  'close': [1.0] * 70}))['reason'] == 'missing:volume')

# ============================================================ B
P('')
P('[B] 真实数据（kline_cache 抽 300 只）')
import duckdb  # noqa: E402
from services.band_pattern_engine import _bars_to_df  # noqa: E402

con = duckdb.connect(r'D:\QuantMonitorV6\data\cache\kline_cache.duckdb', read_only=True)
rows = con.execute(
    "SELECT code,date,open,high,low,close,volume FROM ("
    " SELECT *,ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) rn FROM kline_cache)"
    " WHERE rn<=260 ORDER BY code,date").fetchdf()
con.close()
codes = sorted(rows['code'].unique())[:300]
n_ok_p = n_ok_d = n_calc = 0
p_min_ok, p_max_no = 999.0, -999.0
d_min_ok, d_max_no = 999.0, -999.0
mismatch = []
types = {}
for _cd in codes:
    g = rows[rows['code'] == _cd]
    bars = g.to_dict('records')
    d = _bars_to_df(bars[-120:])
    if d is None:
        continue
    n_calc += 1
    rp = TI.detect_probe(d)
    rd = TI.detect_distribution_pattern(d)
    if rp['ok']:
        n_ok_p += 1
        p_min_ok = min(p_min_ok, rp['score'])
    else:
        p_max_no = max(p_max_no, rp['score'])
    if rd['ok']:
        n_ok_d += 1
        d_min_ok = min(d_min_ok, rd['score'])
        types[rd['type']] = types.get(rd['type'], 0) + 1
    else:
        d_max_no = max(d_max_no, rd['score'])
    # 无未来数据 / 口径核对：量比、位置必须等于手工计算
    c = np.asarray(d['close'].values, float)
    v = np.asarray(d['volume'].values, float)
    c120 = c[-120:]
    pos_hand = (c[-1] - c120.min()) / (c120.max() - c120.min() + 1e-8)
    vr_hand = v[-1] / (np.mean(v[-6:-1]) + 1e-9)
    if abs(rd['pos120'] - pos_hand) > 1e-6 or abs(rd['vol_ratio'] - vr_hand) > 1e-6:
        mismatch.append((_cd, rd['pos120'], pos_hand, rd['vol_ratio'], vr_hand))

P('  可算 %d 只 ｜ 试盘命中 %d 只 ｜ 出货形态命中 %d 只 %s' % (n_calc, n_ok_p, n_ok_d, types))
check('真数据：新因子能在本地缓存上跑通', n_calc > 250, '%d 只' % n_calc)
check('ok=True 的记录分数全部 >= 70（试盘）', p_min_ok >= 70.0 or n_ok_p == 0,
      'min=%.1f' % p_min_ok)
check('未通过的记录分数全部 <= 60（试盘）', p_max_no <= 60.0, 'max=%.1f' % p_max_no)
check('ok=True 的记录分数全部 >= 70（出货形态）', d_min_ok >= 70.0 or n_ok_d == 0,
      'min=%.1f' % d_min_ok)
check('未通过的记录分数全部 <= 60（出货形态）', d_max_no <= 60.0, 'max=%.1f' % d_max_no)
check('pos120 / vol_ratio 与手工计算逐只一致（无错位、无未来数据）',
      not mismatch, str(mismatch[:3]))

# ============================================================ C
P('')
P('[C] 文案追加与开关')
t = E._ctrl_note(50.0, 'unknown', 0.5, None, None, None, None, True, None)
check("probe=True -> 追加「试盘观察：长上影测试抛压」", t == '试盘观察：长上影测试抛压', repr(t))
t = E._ctrl_note(50.0, 'unknown', 0.5, None, None, None, None, False, '高位放量滞涨')
check("distpat='高位放量滞涨' -> 追加对应文案",
      t == '出货形态观察：高位放量滞涨', repr(t))
t = E._ctrl_note(90.0, 'distribute', 0.70, None, None, None, None, True, '高位破位')
check('控盘提示与观察文案并存且顺序为「控盘在前」',
      t == '出货风险警示 ｜ 试盘观察：长上影测试抛压 ｜ 出货形态观察：高位破位', repr(t))
t = E._ctrl_note(90.0, 'unknown', 0.10, None, None, 5, 2, True, '双顶雏形')
check('C4/C6/试盘/出货形态 四条共存',
      t == '高度控盘候选 ｜ C4观察：低位量价结构 ｜ C6观察：低位适中振幅'
           ' ｜ 试盘观察：长上影测试抛压 ｜ 出货形态观察：双顶雏形', repr(t))
check('probe=False / distpat=None 时不追加',
      E._ctrl_note(50.0, 'unknown', 0.5, None, None, None, None, False, None) == '')
E._PROBE_NOTE_MODE = 'off'
check("_PROBE_NOTE_MODE='off' -> 不追加试盘文案",
      '试盘' not in E._ctrl_note(50.0, 'unknown', 0.5, None, None, None, None, True, None))
E._PROBE_NOTE_MODE = 'watch'
E._DISTP_NOTE_MODE = 'off'
check("_DISTP_NOTE_MODE='off' -> 不追加出货形态文案",
      '出货形态' not in E._ctrl_note(50.0, 'unknown', 0.5, None, None, None, None,
                                     None, '高位破位'))
E._DISTP_NOTE_MODE = 'watch'

# 旧参数组合与改动前逐字等价
_ld = importlib.machinery.SourceFileLoader('bpe_old2', BAK)
_sp = importlib.util.spec_from_loader('bpe_old2', _ld)
Old = importlib.util.module_from_spec(_sp)
_ld.exec_module(Old)
diff, ncase = [], 0
for ctrl in (0.0, 50.0, 84.9, 85.0, 90.0, 99.0):
    for stage in (None, 'wash', 'distribute', 'unknown'):
        for pos in (None, 0.10, 0.25, 0.65, 0.90):
            for c4 in (None, 0, 4, 5):
                for c6 in (None, 0, 1, 2):
                    ncase += 1
                    a = E._ctrl_note(ctrl, stage, pos, None, None, c4, c6)
                    b = Old._ctrl_note(ctrl, stage, pos, None, None, c4, c6)
                    # 2026-10-11 起 wash 文案默认关闭：把旧版输出里的那一段剥掉后，
                    # 其余文案必须逐字一致（这才是本次要守的不变量）。
                    b = ' ｜ '.join(x for x in b.split(' ｜ ')
                                    if x != '高度控盘 + 疑似洗盘，关注启动')
                    if a != b:
                        diff.append((ctrl, stage, pos, c4, c6, b, a))
P('  旧参数组合数 %d' % ncase)
check('旧参数组合下 _ctrl_note 输出与改动前逐字一致（已剔除 2026-10-11 关闭的洗盘文案）', not diff,
      '不一致 %d 例 %s' % (len(diff), diff[:2]))

# ============================================================ D
P('')
P('[D] 落盘链路（字段定义）')
cols = dict(E._ALL_COLS)
for n, t in (('probe_ok', 'INTEGER'), ('probe_score', 'REAL'),
             ('dist_pattern_ok', 'INTEGER'), ('dist_pattern_type', 'TEXT'),
             ('dist_pattern_score', 'REAL')):
    check('_ALL_COLS 含 %s (%s)' % (n, t), cols.get(n) == t, str(cols.get(n)))
check('列数 = 59', len(E._ALL_COLS) == 59, '%d' % len(E._ALL_COLS))  # 1010i=56 -> 1010l 加 markup 三列 = 59
src = open(r'D:\QuantMonitorV6\services\band_pattern_engine.py', encoding='utf-8').read()
check('INSERT 占位符数量 == 列数',
      src[src.index('VALUES ('):src.index(')""", (')].count('?') == len(E._ALL_COLS))
check('引擎行尾仍为纯 LF',
      open(r'D:\QuantMonitorV6\services\band_pattern_engine.py', 'rb').read().count(b'\r\n') == 0)
check('base.py 行尾仍为纯 CRLF',
      open(r'D:\QuantMonitorV6\strategy\base.py', 'rb').read().count(b'\n')
      - open(r'D:\QuantMonitorV6\strategy\base.py', 'rb').read().count(b'\r\n') == 0)

P('')
P('=' * 100)
P('总计：PASS %d ｜ FAIL %d' % (PASS[0], PASS[1]))
P('=' * 100)
with open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(_lines) + '\n')
print('\n已写出 %s' % OUT)
sys.exit(1 if PASS[1] else 0)
