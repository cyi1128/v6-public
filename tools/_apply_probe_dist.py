# -*- coding: utf-8 -*-
"""一次性补丁：新增「试盘识别」与「出货形态确认」两条观察规则。

执行一次即生效，**不可重跑**（锚点会被自己改掉）。
改动：
  strategy/base.py             —— 常量 + TechnicalIndicators.detect_probe()
                                  + TechnicalIndicators.detect_distribution_pattern()
  services/band_pattern_engine.py —— 常量/漏斗 + _ctrl_note/_observe_tags 接文案
                                  + _ALL_COLS / INSERT 三处同步 + scan_stock 计算
                                  + scan_all 漏斗清零与汇总打印
行尾：base.py 纯 CRLF；band_pattern_engine.py 纯 LF（各自写回原行尾）。
"""
import py_compile
import shutil
import sys

sys.stdout.reconfigure(encoding='utf-8')

BASE = r'D:\QuantMonitorV6\strategy\base.py'
ENG = r'D:\QuantMonitorV6\services\band_pattern_engine.py'
SUF = '.bak_before_probedist'


def load(path):
    raw = open(path, 'rb').read()
    crlf = raw.count(b'\r\n')
    lf = raw.count(b'\n') - crlf
    return raw, crlf, lf, raw.decode('utf-8')


def save(path, text, crlf_mode):
    raw = text.replace('\r\n', '\n')
    if crlf_mode:
        raw = raw.replace('\n', '\r\n')
    open(path, 'wb').write(raw.encode('utf-8'))
    py_compile.compile(path, doraise=True)
    r2 = open(path, 'rb').read()
    return r2.count(b'\r\n'), r2.count(b'\n') - r2.count(b'\r\n')


def one(text, old, new, tag):
    cnt = text.count(old)
    assert cnt == 1, '[%s] 锚点命中 %d 次' % (tag, cnt)
    return text.replace(old, new)


# ============================================================ base.py
raw_b, crlf_b, lf_b, s = load(BASE)
print('base.py     改前：CRLF=%d 裸LF=%d 行数=%d' % (crlf_b, lf_b, s.count('\n') + 1))
assert crlf_b > 500 and lf_b == 0
shutil.copy2(BASE, BASE + SUF)
s = s.replace('\r\n', '\n')

CONST_ANCHOR = '''C6_MIN_BARS = 120       # 位置/振幅窗口要求的最少K线根数（不足直接判不可用）
'''
CONST_NEW = CONST_ANCHOR + r'''
# ---- 试盘识别（观察规则）阈值（2026-10-10）----
# 「主力测试抛压」的量化近似：放量冲高收长上影 -> 随后缩量回调/横盘不破。
# 实盘标定见 tools\\probe_dist_calib.txt（tools\\_calib_probe_dist.py 生成）。
# 只做【观察】不进 signal_level / 建仓价 / 排序；依据见函数 docstring。
PROBE_LOOKBACK = 11      # 在最近这么多根里找「试盘日」（不含最后一根时才算确认过）
PROBE_POS_MAX = 0.75     # 位置上限：高位长上影归「出货形态」，不按试盘计
PROBE_SHADOW_MIN = 0.50  # 上影线占当日全幅 (high-low) 的比例下限
PROBE_SPIKE_MIN = 0.05   # 冲高幅度下限：(当日最高 - 昨收) / 昨收
PROBE_VOL_MIN = 1.20     # 试盘日量比下限：当日量 / 前5日均量
PROBE_AFTER_SHRINK = 0.80  # 试盘后均量 / 试盘日量 的上限（缩量）
PROBE_HOLD_TOL = 0.03    # 试盘后允许跌破试盘日低点的容忍度
PROBE_SCORE_OK = 70.0    # ok=True 时的最低分（分数两段不重叠：ok>=70，未通过<=60）
PROBE_MIN_BARS = 60      # 最少K线根数

# ---- 出货形态确认（观察规则）阈值（2026-10-10）----
# 在「高位 + stage_guess=distribute」之上加形态级确认，用来降低误报。
# 三种形态：① 高位放量滞涨 ② 高位破位 ③ 双顶雏形。只做【观察】。
DIST_POS_HIGH = 0.65     # ① 高位口径（近120根收盘位置）
DIST_NEWHIGH_TOL = 0.98  # ① 当日最高 >= 近60日最高 x 该值 = 创新高/接近前高
DIST_STALL_CLOSE_WEAK = 0.45  # ① 收盘位于当日振幅的位置上限（<= 视为收弱）
DIST_STALL_VOL = 1.80    # ① 量比下限（当日量 / 前5日均量）
DIST_POS_BREAK = 0.40    # ② 破位口径的位置下限
DIST_PLATFORM_AMP = 0.18  # ② 平台振幅上限（近20根不含当日）
DIST_BREAK_VOL = 1.50    # ② 破位当日量比下限
DIST_DT_WINDOW = 40      # ③ 双顶搜索窗口
DIST_DT_GAP = 6          # ③ 两个高点最小间隔（根）
DIST_DT_BACK = 12        # ③ 第二个高点必须落在最近这么多根内
DIST_DT_DIFF = 0.03      # ③ 两个高点接近程度 |h2-h1|/h1 上限
DIST_DT_DIP = 0.06       # ③ 中间回撤幅度下限（相对两顶较低者）
DIST_DT_VOLFADE = 0.90   # ③ 二次冲高量能 / 一次冲高量能 的上限（力度减弱）
DIST_DT_POS_MIN = 0.55   # ③ 双顶的位置下限
DIST_SCORE_OK = 70.0     # 同 PROBE_SCORE_OK：ok>=70，未通过<=60
DIST_MIN_BARS = 60       # 最少K线根数
'''
s = one(s, CONST_ANCHOR, CONST_NEW, 'base 常量')

METHOD_ANCHOR = '''            r['reason'] = type(_e).__name__
            return r


# ============================================================
# K线数据解析
# ============================================================'''

METHOD_NEW = r'''            r['reason'] = type(_e).__name__
            return r


    @staticmethod
    def detect_probe(df):
        """试盘识别（观察规则）：长上影放量冲高 -> 缩量回调/横盘不破。

        主力「测试抛压」的量化近似：某日放量冲高（最高价相对昨收明显跳升，
        冲击涨停后回落更好），收出长上影（上影占当日全幅 >= 50% 且不短于实体），
        随后 1~11 个交易日缩量回调或横盘、且不有效跌破试盘日低点。

        这是【观察】规则，不是建仓触发 —— 只说明「这里可能发生过一次试盘」，
        禁止参与 signal_level / 建仓价 / 排序 / 等级。

        参数
        ----
        df : pandas.DataFrame
            至少含 open/high/low/close/volume，且不少于 PROBE_MIN_BARS(60) 根。

        返回
        ----
        dict :
            {'ok': bool, 'stage': str, 'score': float, 'hits': list[bool],
             'n_ok': int, 'shadow_ratio': float|None, 'spike': float|None,
             'vol_ratio': float|None, 'post_vol_ratio': float|None,
             'probe_idx': int|None, 'bars_after': int, 'pos120': float|None,
             'reason': str}
            ok       —— P1~P6 全部满足（「缩量回调/横盘不破」已由后续K线确认）
            stage    —— 'confirmed' 已确认；'pending' 试盘日就是最后一根、还没后续K线
                        （pending 只写分数、不出文案）；'' 未发现试盘形态
            score    —— 0~100 两段不重叠：ok=True 必 >= PROBE_SCORE_OK(70)，
                        未通过必 <= 60
            hits     —— [P1..P6] 逐个 bool
            probe_idx—— 试盘日在 df 里的行号（0 基）

        判据
        ----
        P1 长上影：upper/(high-low) >= PROBE_SHADOW_MIN(0.50) 且 上影 >= 实体
        P2 冲高：  (high - prev_close)/prev_close >= PROBE_SPIKE_MIN(0.05)
        P3 放量：  当日量 / 前5日均量 >= PROBE_VOL_MIN(1.20)
        P4 回落：  收盘 <= 当日最高 x 0.97
        P5 缩量：  试盘后均量 <= 试盘日量 x PROBE_AFTER_SHRINK(0.80)，或单日量都不超过试盘日
        P6 不破：  试盘后最低价 >= min(试盘日最低, 试盘日收盘) x (1 - PROBE_HOLD_TOL)
        前置：位置 pos120 <= PROBE_POS_MAX(0.75)。
        """
        _bad = {'ok': False, 'stage': '', 'score': 0.0, 'hits': [], 'n_ok': 0,
                'shadow_ratio': None, 'spike': None, 'vol_ratio': None,
                'post_vol_ratio': None, 'probe_idx': None, 'bars_after': 0,
                'pos120': None, 'reason': ''}
        try:
            if df is None or len(df) < PROBE_MIN_BARS:
                r = dict(_bad)
                r['reason'] = 'bars<%d' % PROBE_MIN_BARS
                return r
            for _c in ('open', 'high', 'low', 'close', 'volume'):
                if _c not in df.columns:
                    r = dict(_bad)
                    r['reason'] = 'missing:%s' % _c
                    return r
            o = np.asarray(df['open'].values, dtype=float)
            h = np.asarray(df['high'].values, dtype=float)
            lw = np.asarray(df['low'].values, dtype=float)
            c = np.asarray(df['close'].values, dtype=float)
            v = np.asarray(df['volume'].values, dtype=float)
            n = len(c)
            c120 = c[-120:]
            _mn, _mx = float(np.min(c120)), float(np.max(c120))
            pos = (float(c[-1]) - _mn) / (_mx - _mn + 1e-8)
            r = dict(_bad)
            r['pos120'] = float(pos)
            if pos > PROBE_POS_MAX:
                r['reason'] = 'pos>%.2f' % PROBE_POS_MAX
                return r

            def _c01(x):
                return min(1.0, max(0.0, float(x)))

            # 找最靠后的一根「试盘日」
            p = None
            for i in range(n - 1, max(n - 1 - PROBE_LOOKBACK, 5) - 1, -1):
                rng = h[i] - lw[i]
                pc = c[i - 1]
                if rng <= 0 or pc <= 0:
                    continue
                upper = h[i] - max(o[i], c[i])
                body = abs(c[i] - o[i])
                sr = upper / rng
                spike = (h[i] - pc) / pc
                v5 = float(np.mean(v[max(0, i - 5):i]))
                vr = v[i] / (v5 + 1e-9)
                if (sr >= PROBE_SHADOW_MIN and upper >= body
                        and spike >= PROBE_SPIKE_MIN and vr >= PROBE_VOL_MIN
                        and c[i] <= h[i] * 0.97):
                    p = int(i)
                    break
            if p is None:
                r['reason'] = 'no_probe'
                return r

            rng = h[p] - lw[p]
            pc = c[p - 1]
            upper = h[p] - max(o[p], c[p])
            body = abs(c[p] - o[p])
            sr = upper / (rng + 1e-9)
            spike = (h[p] - pc) / pc
            v5 = float(np.mean(v[max(0, p - 5):p]))
            vr = v[p] / (v5 + 1e-9)
            bars_after = int(n - 1 - p)
            lo_next = lw[p + 1:] if bars_after >= 1 else np.array([])
            post_vol = v[p + 1:] if bars_after >= 1 else np.array([])
            post_mean = float(np.mean(post_vol)) if bars_after >= 1 else 0.0
            post_max = float(np.max(post_vol)) if bars_after >= 1 else 0.0
            post_ratio = post_mean / (v[p] + 1e-9) if bars_after >= 1 else 0.0
            p5_ok = bool(bars_after >= 1
                         and (post_mean <= PROBE_AFTER_SHRINK * v[p]
                              or post_max <= v[p]))
            floor = min(lw[p], c[p]) * (1.0 - PROBE_HOLD_TOL)
            p6_ok = bool(bars_after >= 1 and float(np.min(lo_next)) >= floor)
            hits = [True, True, True, True, p5_ok, p6_ok]   # P1~P4 是候选门槛，必为 True
            n_ok = int(sum(1 for x in hits if x))
            if p == n - 1:
                stage, ok = 'pending', False
            else:
                ok = bool(p5_ok and p6_ok)
                stage = 'confirmed' if ok else ''
            if ok:
                extra = (0.30 * _c01((sr - PROBE_SHADOW_MIN) / 0.35)
                         + 0.30 * _c01((spike - PROBE_SPIKE_MIN) / 0.06)
                         + 0.25 * _c01((vr - PROBE_VOL_MIN) / 1.30)
                         + 0.15 * _c01((PROBE_AFTER_SHRINK - post_ratio) / 0.40))
                score = PROBE_SCORE_OK + 30.0 * _c01(extra)
            else:
                part = (0.28 * _c01((sr - 0.30) / 0.45)
                        + 0.27 * _c01((spike - 0.02) / 0.08)
                        + 0.20 * _c01((vr - 0.90) / 1.10)
                        + 0.15 * (1.0 if p5_ok else 0.30)
                        + 0.10 * (1.0 if p6_ok else 0.20))
                score = 60.0 * _c01(part)
            return {'ok': bool(ok), 'stage': stage, 'score': float(score),
                    'hits': hits, 'n_ok': n_ok,
                    'shadow_ratio': float(sr), 'spike': float(spike),
                    'vol_ratio': float(vr), 'post_vol_ratio': float(post_ratio),
                    'probe_idx': p, 'bars_after': bars_after,
                    'pos120': float(pos), 'reason': ''}
        except Exception as _e:
            r = dict(_bad)
            r['reason'] = type(_e).__name__
            return r

    @staticmethod
    def detect_distribution_pattern(df):
        """出货形态确认（观察规则）：在「高位 + distribute」之上做形态级确认。

        三种形态，命中多个时取分数最高的那个：
          ① 高位放量滞涨 —— 创/近前高，但收盘弱势、量能显著放大
          ② 高位破位     —— 平台下沿被有效跌破且放量
          ③ 双顶雏形     —— 两个高点接近、中间明显回撤、二次冲高力度减弱

        这是【观察】规则：作用是给现有「出货风险警示」加一层形态确认、降低误报，
        不参与 signal_level / 建仓价 / 排序。不依赖 judge_wash_or_distribute 的结果，
        可以独立调用，也可以与它交叉使用。

        参数
        ----
        df : pandas.DataFrame
            至少含 open/high/low/close/volume，且不少于 DIST_MIN_BARS(60) 根。

        返回
        ----
        dict :
            {'ok': bool, 'type': str, 'score': float, 'n_ok': int,
             'hits': list[bool], 'pos120': float|None, 'vol_ratio': float|None,
             'detail': dict, 'reason': str}
            ok     —— 三种形态至少一种成立
            type   —— '高位放量滞涨' / '高位破位' / '双顶雏形' / ''（未命中）
            score  —— 0~100 两段不重叠：ok=True 必 >= DIST_SCORE_OK(70)，未通过 <= 60
            hits   —— 命中形态的逐条判据 bool 列表
            detail —— 关键中间值（close_pos / 平台上下沿 / 两顶价格与回撤等）

        判据
        ----
        ① A1 pos120 >= DIST_POS_HIGH(0.65)；A2 当日最高 >= 近60日最高 x 0.98；
           A3 收盘位于当日振幅下 DIST_STALL_CLOSE_WEAK(0.45) 或收阴；
           A4 量比 >= DIST_STALL_VOL(1.80)；A5 未涨停收盘（涨幅 < 9.5%）
        ② B1 平台振幅 <= 0.18；B2 收盘 < 平台下沿 x 0.98；
           B3 量比 >= DIST_BREAK_VOL(1.50)；B4 pos120 >= DIST_POS_BREAK(0.40)
        ③ C1 两顶间隔 >= 6 根且第二顶在最近12根内；C2 |h2-h1|/h1 <= 0.03；
           C3 中间回撤 >= 0.06；C4 二次冲高量能 <= 一次 x 0.90 或 h2 < h1；
           C5 pos120 >= 0.55；C6 当前收盘 <= 颈线 x 1.03（仍在颈线附近/之下）
        """
        _bad = {'ok': False, 'type': '', 'score': 0.0, 'n_ok': 0, 'hits': [],
                'pos120': None, 'vol_ratio': None, 'detail': {}, 'reason': ''}
        try:
            if df is None or len(df) < DIST_MIN_BARS:
                r = dict(_bad)
                r['reason'] = 'bars<%d' % DIST_MIN_BARS
                return r
            for _c in ('open', 'high', 'low', 'close', 'volume'):
                if _c not in df.columns:
                    r = dict(_bad)
                    r['reason'] = 'missing:%s' % _c
                    return r
            o = np.asarray(df['open'].values, dtype=float)
            h = np.asarray(df['high'].values, dtype=float)
            lw = np.asarray(df['low'].values, dtype=float)
            c = np.asarray(df['close'].values, dtype=float)
            v = np.asarray(df['volume'].values, dtype=float)
            n = len(c)
            c120 = c[-120:]
            _mn, _mx = float(np.min(c120)), float(np.max(c120))
            pos = (float(c[-1]) - _mn) / (_mx - _mn + 1e-8)
            v5 = float(np.mean(v[max(0, n - 6):n - 1]))
            vr = float(v[n - 1] / (v5 + 1e-9))
            pct = float((c[-1] - c[-2]) / (c[-2] + 1e-9))
            rng = float(h[-1] - lw[-1])
            close_pos = float((c[-1] - lw[-1]) / (rng + 1e-9))

            def _c01(x):
                return min(1.0, max(0.0, float(x)))

            # ---------------- ① 高位放量滞涨 ----------------
            hi60 = float(np.max(h[-60:]))
            a = [bool(pos >= DIST_POS_HIGH),
                 bool(h[-1] >= hi60 * DIST_NEWHIGH_TOL),
                 bool(close_pos <= DIST_STALL_CLOSE_WEAK or c[-1] < o[-1]),
                 bool(vr >= DIST_STALL_VOL),
                 bool(pct < 0.095)]
            a_ok = all(a)
            if a_ok:
                a_sc = DIST_SCORE_OK + 30.0 * _c01(
                    0.40 * _c01((vr - DIST_STALL_VOL) / 2.20)
                    + 0.30 * _c01((DIST_STALL_CLOSE_WEAK - close_pos) / 0.45)
                    + 0.30 * _c01((pos - DIST_POS_HIGH) / 0.30))
            else:
                a_sc = 60.0 * _c01(0.30 * _c01((vr - 1.30) / 1.50)
                                   + 0.25 * _c01((0.55 - close_pos) / 0.45)
                                   + 0.25 * _c01((pos - 0.50) / 0.35)
                                   + 0.20 * _c01((h[-1] / (hi60 + 1e-9) - 0.90) / 0.12))
            # ---------------- ② 高位破位 ----------------
            plat_lo = float(np.min(lw[-21:-1]))
            plat_hi = float(np.max(h[-21:-1]))
            plat_amp = float((plat_hi - plat_lo) / (plat_lo + 1e-9))
            b = [bool(plat_amp <= DIST_PLATFORM_AMP),
                 bool(c[-1] < plat_lo * 0.98),
                 bool(vr >= DIST_BREAK_VOL),
                 bool(pos >= DIST_POS_BREAK)]
            b_ok = all(b)
            if b_ok:
                b_sc = DIST_SCORE_OK + 30.0 * _c01(
                    0.45 * _c01(((plat_lo * 0.98) - c[-1]) / (plat_lo * 0.06 + 1e-9))
                    + 0.35 * _c01((vr - DIST_BREAK_VOL) / 1.50)
                    + 0.20 * _c01((DIST_PLATFORM_AMP - plat_amp) / 0.12))
            else:
                b_sc = 60.0 * _c01(0.35 * _c01(((plat_lo * 1.01) - c[-1])
                                               / (plat_lo * 0.06 + 1e-9))
                                   + 0.30 * _c01((vr - 1.10) / 1.20)
                                   + 0.20 * _c01((0.22 - plat_amp) / 0.14)
                                   + 0.15 * _c01((pos - 0.35) / 0.40))
            # ---------------- ③ 双顶雏形 ----------------
            m = int(min(DIST_DT_WINDOW, n))
            off = n - m
            seg = h[off:]
            loc = [i for i in range(2, m - 2)
                   if seg[i] >= max(seg[i - 2], seg[i - 1], seg[i + 1], seg[i + 2])]
            c_best = None
            for _x in range(len(loc)):
                for _y in range(_x + 1, len(loc)):
                    i, j = loc[_x], loc[_y]
                    if j - i < DIST_DT_GAP or j < m - DIST_DT_BACK:
                        continue
                    h1, h2 = float(seg[i]), float(seg[j])
                    if h1 <= 0 or h2 <= 0:
                        continue
                    diff = abs(h2 - h1) / h1
                    if diff > DIST_DT_DIFF:
                        continue
                    gi, gj = off + i, off + j
                    dip_low = float(np.min(lw[gi:gj + 1]))
                    dip = (min(h1, h2) - dip_low) / (min(h1, h2) + 1e-9)
                    if dip < DIST_DT_DIP:
                        continue
                    va = float(np.mean(v[max(0, gi - 1):gi + 2]))
                    vb = float(np.mean(v[max(0, gj - 1):gj + 2]))
                    fade = (vb <= va * DIST_DT_VOLFADE) or (h2 < h1 * 0.995)
                    neck = dip_low
                    c = [True, True, True, bool(fade),
                         bool(pos >= DIST_DT_POS_MIN),
                         bool(c[-1] <= neck * 1.03)]
                    if not all(c):
                        continue
                    sc = DIST_SCORE_OK + 30.0 * _c01(
                        0.35 * _c01((DIST_DT_DIFF - diff) / 0.03)
                        + 0.35 * _c01((dip - DIST_DT_DIP) / 0.10)
                        + 0.30 * _c01(1.0 - vb / (va + 1e-9)))
                    if c_best is None or sc > c_best[0]:
                        c_best = (sc, c, {'h1': h1, 'h2': h2, 'diff': float(diff),
                                          'dip': float(dip), 'neckline': float(neck),
                                          'idx1': int(gi), 'idx2': int(gj)})
            if c_best is not None:
                c_ok, c_sc, c_hits, c_det = True, c_best[0], c_best[1], c_best[2]
            else:
                c_ok, c_sc, c_hits, c_det = False, 0.0, [], {}

            cands = []
            if a_ok:
                cands.append(('高位放量滞涨', a_sc, a))
            if b_ok:
                cands.append(('高位破位', b_sc, b))
            if c_ok:
                cands.append(('双顶雏形', c_sc, c_hits))
            detail = {'close_pos': float(close_pos), 'hi60': hi60,
                      'platform_low': plat_lo, 'platform_high': plat_hi,
                      'platform_amp': plat_amp, 'pct': float(pct)}
            if c_det:
                detail.update(c_det)
            if cands:
                cands.sort(key=lambda x: -x[1])
                _t, _sc, _hits = cands[0]
                return {'ok': True, 'type': _t, 'score': float(_sc),
                        'n_ok': int(sum(1 for x in _hits if x)), 'hits': list(_hits),
                        'pos120': float(pos), 'vol_ratio': vr,
                        'detail': detail, 'reason': ''}
            return {'ok': False, 'type': '', 'score': float(max(a_sc, b_sc, c_sc)),
                    'n_ok': max(int(sum(1 for x in a if x)), int(sum(1 for x in b if x)),
                                len(c_hits)), 'hits': a, 'pos120': float(pos),
                    'vol_ratio': vr, 'detail': detail, 'reason': ''}
        except Exception as _e:
            r = dict(_bad)
            r['reason'] = type(_e).__name__
            return r


# ============================================================
# K线数据解析
# ============================================================'''
s = one(s, METHOD_ANCHOR, METHOD_NEW, 'base 方法')

crlf2, lf2 = save(BASE, s, True)
print('base.py     改后：CRLF=%d 裸LF=%d 行数=%d' % (crlf2, lf2, s.count('\n') + 1))
assert lf2 == 0

# ============================================================ band_pattern_engine.py
raw_e, crlf_e, lf_e, s = load(ENG)
print('engine.py   改前：CRLF=%d 裸LF=%d 行数=%d' % (crlf_e, lf_e, s.count('\n') + 1))
assert lf_e > 1000 and crlf_e == 0
shutil.copy2(ENG, ENG + SUF)
s = s.replace('\r\n', '\n')

s = one(s, """_C6_FUNNEL = {'ok': 0, 'insuf': 0, 'pos': 0, 'amp': 0, 'c6': 0, 'note': 0}
""", """_C6_FUNNEL = {'ok': 0, 'insuf': 0, 'pos': 0, 'amp': 0, 'c6': 0, 'note': 0}

# ---- 试盘识别（2026-10-10）放量冲高收长上影 -> 缩量回调不破 ----
# 因子本体在 strategy/base.py 的 TechnicalIndicators.detect_probe()。
# 实盘标定见 tools\\probe_dist_calib.txt（_calib_probe_dist.py 生成，无未来数据）。
# 只做【观察】：不参与 signal_level / 建仓价 / 排序 / 等级。
# 只有 stage='confirmed'（试盘之后确实缩量回调且不破试盘日低点）才出文案；
# 试盘日就是最后一根的 'pending' 只写分数，避免「当天长上影」的噪音刷屏。
_PROBE_NOTE_MODE = 'watch'   # 'watch' 追加观察文案（默认）；'off' 只写字段不提示
_PROBE_FUNNEL = {'ok': 0, 'insuf': 0, 'pos': 0, 'no': 0, 'pending': 0,
                 'hit': 0, 'note': 0}

# ---- 出货形态确认（2026-10-10）高位放量滞涨 / 高位破位 / 双顶雏形 ----
# 因子本体在 strategy/base.py 的 TechnicalIndicators.detect_distribution_pattern()。
# 作用：给现有「出货风险警示」（stage_guess=distribute 且位置>=0.65）加一层
# 形态级确认，降低误报；两者并存，互不替代。只做【观察】。
_DISTP_NOTE_MODE = 'watch'   # 'watch' 追加观察文案（默认）；'off' 只写字段不提示
_DISTP_FUNNEL = {'ok': 0, 'insuf': 0, 'stall': 0, 'break': 0, 'dtop': 0,
                 'hit': 0, 'note': 0}
""", 'engine 常量')

s = one(s, "def _ctrl_note(ctrl, stage, pos, stack=None, redfat=None, c4=None, c6=None):",
        "def _ctrl_note(ctrl, stage, pos, stack=None, redfat=None, c4=None, c6=None,\n"
        "               probe=None, distpat=None):", 'ctrl_note 签名')

s = one(s, """    与 C4 / 建仓因子互相独立，任一条不通过都不影响其他文案。
    \"\"\"
    _low_ctrl = bool(ctrl >= _CTRL_HIGH and pos is not None and pos < _CTRL_CAND_POS)
    return ' ｜ '.join(_ctrl_note_tags(ctrl, stage, pos)
                      + _observe_tags(stack, redfat, c4, c6, _low_ctrl))""",
        """    与 C4 / 建仓因子互相独立，任一条不通过都不影响其他文案。

    probe / distpat
    ---------------
    probe  —— 试盘识别是否【确认】（TechnicalIndicators.detect_probe 的 ok），
              默认 None。为 True 时追加「试盘观察：长上影测试抛压」。
    distpat—— 出货形态类型（detect_distribution_pattern 的 type，字符串），
              默认 None。非空时追加「出货形态观察：<类型>」。
              两者同样受 _PROBE_NOTE_MODE / _DISTP_NOTE_MODE 控制。
    \"\"\"
    _low_ctrl = bool(ctrl >= _CTRL_HIGH and pos is not None and pos < _CTRL_CAND_POS)
    return ' ｜ '.join(_ctrl_note_tags(ctrl, stage, pos)
                      + _observe_tags(stack, redfat, c4, c6, _low_ctrl,
                                      probe, distpat))""", 'ctrl_note 文档+调用')

s = one(s, "def _observe_tags(stack=None, redfat=None, c4=None, c6=None, low_ctrl=False):",
        "def _observe_tags(stack=None, redfat=None, c4=None, c6=None, low_ctrl=False,\n"
        "                  probe=None, distpat=None):", 'observe_tags 签名')

s = one(s, """        if _C6_NOTE_MODE != 'off' and c6 is not None and int(c6) >= 2:
            out.append('C6观察：低位适中振幅')""",
        """        if _C6_NOTE_MODE != 'off' and c6 is not None and int(c6) >= 2:
            out.append('C6观察：低位适中振幅')
        # 试盘识别文案（默认 'watch'；只有 confirmed 才出，依据见 _PROBE_NOTE_MODE 注释）
        if _PROBE_NOTE_MODE != 'off' and bool(probe):
            out.append('试盘观察：长上影测试抛压')
        # 出货形态确认文案（默认 'watch'；与「出货风险警示」并列，不替代）
        if _DISTP_NOTE_MODE != 'off' and distpat:
            out.append('出货形态观察：%s' % distpat)""", 'observe_tags 文案')

s = one(s, """    ('ctrl_tag', 'TEXT'),   # 只存「控盘提示」（候选/出货/洗盘），UI 取短标签用这列""",
        """    ('ctrl_tag', 'TEXT'),   # 只存「控盘提示」（候选/出货/洗盘），UI 取短标签用这列
    ('probe_ok', 'INTEGER'), ('probe_score', 'REAL'),
    ('dist_pattern_ok', 'INTEGER'), ('dist_pattern_type', 'TEXT'),
    ('dist_pattern_score', 'REAL'),""", '_ALL_COLS')

s = one(s, """             c6_ok, c6_score, ctrl_tag,
             created_at, updated_at)""",
        """             c6_ok, c6_score, ctrl_tag,
             probe_ok, probe_score,
             dist_pattern_ok, dist_pattern_type, dist_pattern_score,
             created_at, updated_at)""", 'INSERT 列清单')

s = one(s, "            rec.get('ctrl_tag',''),\n",
        """            rec.get('ctrl_tag',''),
            rec.get('probe_ok',0), rec.get('probe_score',0),
            rec.get('dist_pattern_ok',0), rec.get('dist_pattern_type',''),
            rec.get('dist_pattern_score',0),
""", 'INSERT 取值')

# 占位符：在 ctrl_tag 那一行之后补 5 个
_old_ph = "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
assert s.count(_old_ph) == 1, s.count(_old_ph)
s = s.replace(_old_ph, _old_ph[:-1] + ",?,?,?,?,?)")

s = one(s, """        _c6_n, _c6_ok, _c6_sc = 0, False, 0.0""",
        """        _c6_n, _c6_ok, _c6_sc = 0, False, 0.0
        _probe_ok, _probe_sc, _probe_stage = False, 0.0, ''
        _distp_ok, _distp_sc, _distp_type = False, 0.0, ''""", 'scan_stock 局部变量')

s = one(s, """                    if _c6_n >= 2:
                        _C6_FUNNEL['c6'] += 1
        except Exception as _e:""",
        """                    if _c6_n >= 2:
                        _C6_FUNNEL['c6'] += 1
                # 试盘识别（复用同一个 df；只做观察）
                _pr = _ti.detect_probe(_df)
                _probe_ok = bool(_pr.get('ok'))
                _probe_sc = float(_pr.get('score') or 0.0)
                _probe_stage = _pr.get('stage') or ''
                _prr = _pr.get('reason') or ''
                if _prr in ('bars<%d' % 60, 'no_probe'):
                    if _prr == 'no_probe':
                        _PROBE_FUNNEL['no'] += 1
                    else:
                        _PROBE_FUNNEL['insuf'] += 1
                elif _prr.startswith('pos>'):
                    _PROBE_FUNNEL['pos'] += 1
                else:
                    _PROBE_FUNNEL['ok'] += 1
                    if _probe_stage == 'pending':
                        _PROBE_FUNNEL['pending'] += 1
                    if _probe_ok:
                        _PROBE_FUNNEL['hit'] += 1
                # 出货形态确认（复用同一个 df；只做观察）
                _dr = _ti.detect_distribution_pattern(_df)
                _distp_ok = bool(_dr.get('ok'))
                _distp_sc = float(_dr.get('score') or 0.0)
                _distp_type = _dr.get('type') or ''
                if _dr.get('reason'):
                    _DISTP_FUNNEL['insuf'] += 1
                else:
                    _DISTP_FUNNEL['ok'] += 1
                    if _distp_ok:
                        _DISTP_FUNNEL['hit'] += 1
                        if _distp_type == '\\u9ad8\\u4f4d\\u653e\\u91cf\\u6ede\\u6da8':
                            _DISTP_FUNNEL['stall'] += 1
                        elif _distp_type == '\\u9ad8\\u4f4d\\u7834\\u4f4d':
                            _DISTP_FUNNEL['break'] += 1
                        elif _distp_type == '\\u53cc\\u9876\\u96cf\\u5f62':
                            _DISTP_FUNNEL['dtop'] += 1
        except Exception as _e:""", 'scan_stock 计算块')

s = one(s, """        _ctrl_tip = _ctrl_note(_ctrl, _stage, _pos, _stack_sc, _redfat_sc, _c4_n, _c6_n)""",
        """        _ctrl_tip = _ctrl_note(_ctrl, _stage, _pos, _stack_sc, _redfat_sc, _c4_n,
                               _c6_n, _probe_ok, _distp_type)""", 'ctrl_tip 调用')

s = one(s, """        if _c6_ok and _C6_NOTE_MODE != 'off':
            _C6_FUNNEL['note'] += 1""",
        """        if _c6_ok and _C6_NOTE_MODE != 'off':
            _C6_FUNNEL['note'] += 1
        if _probe_ok and _PROBE_NOTE_MODE != 'off':
            _PROBE_FUNNEL['note'] += 1
        if _distp_ok and _DISTP_NOTE_MODE != 'off':
            _DISTP_FUNNEL['note'] += 1""", 'note 计数')

s = one(s, """                'ctrl_tag': _ctrl_tag,""",
        """                'ctrl_tag': _ctrl_tag,
                'probe_ok': 1 if _probe_ok else 0, 'probe_score': _probe_sc,
                'dist_pattern_ok': 1 if _distp_ok else 0,
                'dist_pattern_type': _distp_type,
                'dist_pattern_score': _distp_sc,""", 'rec 字段')

s = one(s, """        for _k in _C6_FUNNEL:
            _C6_FUNNEL[_k] = 0""",
        """        for _k in _C6_FUNNEL:
            _C6_FUNNEL[_k] = 0
        for _k in _PROBE_FUNNEL:
            _PROBE_FUNNEL[_k] = 0
        for _k in _DISTP_FUNNEL:
            _DISTP_FUNNEL[_k] = 0""", '漏斗清零')

s = one(s, """            _bf = _BUILD_FUNNEL""",
        """            _prf = _PROBE_FUNNEL
            print('[试盘观察] 可算 %d 只 ｜ 位置超限跳过 %d ｜ 无试盘形态 %d ｜ 试盘当日待确认 %d ｜ 已确认 %d ｜ 文案开关 _PROBE_NOTE_MODE=%s'
                  % (_prf['ok'], _prf['pos'], _prf['no'], _prf['pending'],
                     _prf['hit'], _PROBE_NOTE_MODE), flush=True)
            print('[试盘观察] K线不足60根跳过 %d 只 ｜ 命中并追加观察文案 %d 只'
                  % (_prf['insuf'], _prf['note']), flush=True)
            _dpf = _DISTP_FUNNEL
            print('[出货形态] 可算 %d 只 ｜ 放量滞涨 %d ｜ 高位破位 %d ｜ 双顶雏形 %d ｜ 命中合计 %d ｜ 文案开关 _DISTP_NOTE_MODE=%s'
                  % (_dpf['ok'], _dpf['stall'], _dpf['break'], _dpf['dtop'],
                     _dpf['hit'], _DISTP_NOTE_MODE), flush=True)
            print('[出货形态] K线不足60根跳过 %d 只 ｜ 命中并追加观察文案 %d 只'
                  % (_dpf['insuf'], _dpf['note']), flush=True)
            _bf = _BUILD_FUNNEL""", '扫描汇总打印')

crlf3, lf3 = save(ENG, s, False)
print('engine.py   改后：CRLF=%d 裸LF=%d 行数=%d' % (crlf3, lf3, s.count('\n') + 1))
assert crlf3 == 0

# ---- 自检：占位符数量 == 列数 == 取值个数
import re  # noqa: E402
import importlib  # noqa: E402
sys.path.insert(0, r'D:\QuantMonitorV6')
be = importlib.import_module('services.band_pattern_engine')
ncols = len(be._ALL_COLS)
seg = s[s.index('VALUES ('):]
ph = seg[:seg.index(')""", (')].count('?')
print('自检：_ALL_COLS=%d ｜ INSERT 占位符=%d ｜ 一致=%s' % (ncols, ph, ph == ncols))
assert ph == ncols, 'placeholders %d != cols %d' % (ph, ncols)
print('OK —— 备份后缀 %s' % SUF)
