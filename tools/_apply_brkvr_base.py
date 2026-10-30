# -*- coding: utf-8 -*-
"""一次性补丁：A「破位—收复」+ B「量能分位 / 缩量上涨」两个观察因子。

插入 strategy\\base.py（纯 CRLF，1713 行）：
  1) 常量块 BRK_* / VR_*，紧跟 MARKUP_POS_MAX 之后（L141 之后）
  2) TechnicalIndicators.detect_breakdown_recover()   —— A
  3) TechnicalIndicators.volume_percentile()          —— B 的公共工具
  4) TechnicalIndicators.detect_volume_regime()       —— B
位置：插在 detect_markup 之后、`# K线数据解析` 之前。
本批只加因子，**不改任何既有函数**（C 项 markup② 等标定后再定）。
执行一次即失效，勿重跑。
"""
import io
import os
import shutil

ROOT = r'D:\QuantMonitorV6'
os.chdir(ROOT)
P = os.path.join('strategy', 'base.py')
s = io.open(P, encoding='utf-8', newline='').read()
NL = '\r\n'
assert s.count(NL) > 1000 and s.count('\n') == s.count(NL), 'base.py 应为纯 CRLF，停止'

CONST = """
# ------------------------------------------------------------------
# 破位—收复 双向判据（BRK_*，2026-10-11 A 项新增）
# 出处：主力手法里「洗盘 vs 出货」的分水岭 ——
#   破位【缩量】后 N 根内快速收回支撑位、且收回那天放量  -> 洗盘
#   破位【放量】且始终收不回                              -> 出货
# 只用 open/high/low/close/volume，全部取「当日及之前」的窗口，无未来数据。
# 位置上限 BRK_POS_LOW：高位破位交给出货形态（detect_distribution_pattern）判，
# 避免两个因子在同一位置区间重复报警。
# ------------------------------------------------------------------
BRK_LOOKBACK = 12         # 在最近这么多根里找「破位日」
BRK_SUPPORT_WIN = 20      # 支撑位 = 破位日之前 20 根的最低价最小值
BRK_RECOVER_WIN = 5       # 破位后最多 5 根内要收回支撑位
BRK_SHRINK_MAX = 1.00     # 破位日「缩量」上限：当日量 / 前5日均量 <= 该值
BRK_EXPAND_MIN = 1.50     # 破位日「放量」下限：当日量 / 前5日均量 >= 该值
BRK_RECOVER_VOL = 1.20    # 收回日「放量」下限：当日量 / 前5日均量 >= 该值
BRK_POS_LOW = 0.55        # 位置上限（>= 该值不判，交给出货形态）
BRK_SCORE_OK = 70.0       # 同 PROBE_SCORE_OK：ok=True 必 >=70，未通过必 <=60
BRK_MIN_BARS = 60         # 最少K线根数

# ------------------------------------------------------------------
# 量能分位 / 缩量上涨（VR_*，2026-10-11 B 项新增）
# 出处：材料里的「地量见地价、天量见顶」「缩量上涨 = 高度控盘」。
# 现有口径只有「对前 5 日均量」的短口径，这里补长周期分位。
# 分位只用「当日及之前 VR_WIN 根」，不含未来。
# ------------------------------------------------------------------
VR_WIN = 60               # 分位窗口
VR_LOW_PCT = 20.0         # 地量：分位 <= 该值
VR_HIGH_PCT = 80.0        # 天量：分位 >= 该值
VR_SU_WIN = 5             # 「缩量上涨」窗口
VR_SU_VOL_MAX = 0.90      # 窗口内阳线均量 / 窗口前5日均量 的上限
VR_SU_GAIN_MIN = 0.03     # 窗口累计涨幅下限
VR_SU_YANG_MIN = 0.60     # 窗口阳线占比下限
VR_SCORE_OK = 70.0        # ok=True 必 >=70，未通过必 <=60
VR_MIN_BARS = 60          # 最少K线根数
"""
CONST = CONST.replace('\n', NL)

old_c = "MARKUP_POS_MAX = 0.45       # 位置门槛（1010m 新增）：只保留 pos120 < 0.45 的低位子集" + NL
assert s.count(old_c) == 1, 'MARKUP_POS_MAX 锚点不唯一'
s = s.replace(old_c, old_c + CONST)

FUNCS = '''
    def detect_breakdown_recover(df):
        """破位—收复 双向判据（观察规则）：区分「洗盘」与「出货」。

        纯量价，无未来数据；只判非高位（pos120 < BRK_POS_LOW），高位破位交给
        detect_distribution_pattern。禁止参与 signal_level / 建仓价 / 排序。

        dict:
            {'ok': bool, 'type': str, 'score': float, 'n_ok': int, 'hits': list[bool],
             'pos120': float|None, 'vol_ratio': float|None, 'recovered': bool,
             'detail': dict, 'reason': str}
            type —— '洗盘收复'（破位缩量 + N 根内收回 + 收回日放量）
                    '破位未收'（破位放量 + 始终收不回）
                    ''（破位成立但不满足任何一侧）
            score —— 0~100 两段不重叠：ok=True 必 >= BRK_SCORE_OK(70)，未通过必 <= 60
        """
        _bad = {'ok': False, 'type': '', 'score': 0.0, 'n_ok': 0, 'hits': [],
                'pos120': None, 'vol_ratio': None, 'recovered': False,
                'detail': {}, 'reason': ''}
        try:
            if df is None or len(df) < BRK_MIN_BARS:
                r = dict(_bad)
                r['reason'] = 'bars<%d' % BRK_MIN_BARS
                return r
            for _c in ('open', 'high', 'low', 'close', 'volume'):
                if _c not in df.columns:
                    r = dict(_bad)
                    r['reason'] = 'missing:%s' % _c
                    return r
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
            if pos >= BRK_POS_LOW:
                r['reason'] = 'pos>=%.2f' % BRK_POS_LOW
                return r

            # ---- 找最近的破位日：当日最低 < 之前 BRK_SUPPORT_WIN 根的最低价最小值
            i_brk, sup = -1, 0.0
            _lo_i = max(BRK_SUPPORT_WIN, n - BRK_LOOKBACK)
            for i in range(n - 1, _lo_i - 1, -1):
                _s = float(np.min(lw[i - BRK_SUPPORT_WIN:i]))
                if lw[i] < _s:
                    i_brk, sup = i, _s
                    break
            if i_brk < 5:
                r['reason'] = 'no_break'
                return r
            _b5 = float(np.mean(v[i_brk - 5:i_brk]))
            vr = float(v[i_brk] / (_b5 + 1e-9))

            # ---- 破位后是否收回支撑位（只看已发生的K线，取第一根收回的）
            rec_j, rec_vr = -1, 0.0
            for j in range(i_brk + 1, min(i_brk + BRK_RECOVER_WIN, n - 1) + 1):
                if c[j] >= sup:
                    rec_j = j
                    if j >= 5:
                        _bv = float(np.mean(v[j - 5:j]))
                        rec_vr = float(v[j] / (_bv + 1e-9))
                    break
            shrink = bool(vr <= BRK_SHRINK_MAX)
            expand = bool(vr >= BRK_EXPAND_MIN)
            r['vol_ratio'] = vr
            r['recovered'] = bool(rec_j >= 0)
            r['detail'] = {'support': float(sup), 'brk_bars_ago': int(n - 1 - i_brk),
                           'brk_low': float(lw[i_brk]), 'brk_vr': float(vr),
                           'recover_bars_ago': int(n - 1 - rec_j) if rec_j >= 0 else -1,
                           'recover_vr': float(rec_vr), 'shrink': shrink,
                           'expand': expand}
            if shrink and rec_j >= 0 and rec_vr >= BRK_RECOVER_VOL:
                r['ok'] = True
                r['type'] = '洗盘收复'
                r['score'] = float(_clamp100(
                    BRK_SCORE_OK + min(20.0, (BRK_SHRINK_MAX - vr) * 40.0)
                    + min(10.0, (rec_vr - BRK_RECOVER_VOL) * 25.0),
                    BRK_SCORE_OK, 100.0))
                r['hits'] = [True, True, True, True]
                r['n_ok'] = 4
                return r
            if expand and rec_j < 0:
                r['ok'] = True
                r['type'] = '破位未收'
                r['score'] = float(_clamp100(
                    BRK_SCORE_OK + min(30.0, (vr - BRK_EXPAND_MIN) * 20.0),
                    BRK_SCORE_OK, 100.0))
                r['hits'] = [True, True, True, False]
                r['n_ok'] = 3
                return r
            # 破位成立但不满足任何一侧：给「半程」分（必须 <= 60）
            _half = 30.0 + (15.0 if shrink else 0.0) + (15.0 if rec_j >= 0 else 0.0)
            r['type'] = ''
            r['score'] = float(min(60.0, _half))
            r['hits'] = [True, bool(shrink), bool(rec_j >= 0), bool(rec_vr >= BRK_RECOVER_VOL)]
            r['n_ok'] = sum(1 for x in r['hits'] if x)
            return r
        except Exception as _e:
            r = dict(_bad)
            r['reason'] = type(_e).__name__
            return r

    def volume_percentile(df, win=VR_WIN):
        """当日成交量在「最近 win 根（含当日）」里的分位（0~100，无未来数据）。

        地量 = 分位很低（量能萎缩到区间下沿）；天量 = 分位很高。
        数据不足或全为 0 时返回 None。
        """
        try:
            if df is None or 'volume' not in df.columns:
                return None
            v = np.asarray(df['volume'].values, dtype=float)
            if len(v) < win:
                return None
            w = v[-win:]
            if float(np.max(w)) <= 0:
                return None
            cur = float(v[-1])
            return float((w <= cur).sum()) / float(win) * 100.0
        except Exception:
            return None

    def detect_volume_regime(df):
        """量能状态（观察规则）：地量 / 天量 / 缩量上涨。

        出处：主力手法里「地量见地价、天量见顶」「缩量上涨 = 高度控盘」。
        本函数只描述**当前量能处在什么档位**，不含位置条件；位置请配合
        pos120 / detect_breakdown_recover / detect_distribution_pattern 一起看。
        禁止参与 signal_level / 建仓价 / 排序。

        dict:
            {'ok': bool, 'tags': list[str], 'score': float, 'pct': float|None,
             'detail': dict, 'reason': str}
            tags —— '地量' / '天量' / '缩量上涨'（可同时出现多个）
        """
        _bad = {'ok': False, 'tags': [], 'score': 0.0, 'pct': None,
                'detail': {}, 'reason': ''}
        try:
            if df is None or len(df) < VR_MIN_BARS:
                r = dict(_bad)
                r['reason'] = 'bars<%d' % VR_MIN_BARS
                return r
            for _c in ('open', 'close', 'volume'):
                if _c not in df.columns:
                    r = dict(_bad)
                    r['reason'] = 'missing:%s' % _c
                    return r
            o = np.asarray(df['open'].values, dtype=float)
            c = np.asarray(df['close'].values, dtype=float)
            v = np.asarray(df['volume'].values, dtype=float)
            n = len(c)
            pct = TechnicalIndicators.volume_percentile(df, VR_WIN)
            tags, detail = [], {}
            if pct is not None:
                detail['pct'] = float(pct)
                if pct <= VR_LOW_PCT:
                    tags.append('地量')
                if pct >= VR_HIGH_PCT:
                    tags.append('天量')

            # ---- 缩量上涨：近 VR_SU_WIN 根阳线占比够、阳线均量萎缩、累计有涨幅
            su_ok, su_vr, su_gain, su_yang = False, 0.0, 0.0, 0.0
            ws = n - VR_SU_WIN
            if ws >= 5:
                _base = float(np.mean(v[ws - 5:ws]))
                _yang = [i for i in range(ws, n) if c[i] > o[i]]
                su_yang = len(_yang) / float(VR_SU_WIN)
                su_gain = (float(c[-1]) - float(c[ws - 1])) / (float(c[ws - 1]) + 1e-9)
                if _yang:
                    su_vr = float(np.mean([v[i] for i in _yang]) / (_base + 1e-9))
                su_ok = bool(su_yang >= VR_SU_YANG_MIN and su_vr <= VR_SU_VOL_MAX
                             and su_gain >= VR_SU_GAIN_MIN)
                if su_ok:
                    tags.append('缩量上涨')
                detail.update({'su_vol_ratio': float(su_vr),
                               'su_gain': float(su_gain),
                               'su_yang_ratio': float(su_yang)})
            r['pct'] = pct
            r['tags'] = tags
            r['detail'] = detail
            r['ok'] = bool(tags)
            if r['ok']:
                _sc = VR_SCORE_OK + 10.0 * len(tags)
                if pct is not None and pct <= VR_LOW_PCT:
                    _sc += min(10.0, (VR_LOW_PCT - pct) * 0.5)
                r['score'] = float(_clamp100(_sc, VR_SCORE_OK, 100.0))
            else:
                r['score'] = 60.0
            return r
        except Exception as _e:
            r = dict(_bad)
            r['reason'] = type(_e).__name__
            return r

'''
FUNCS = FUNCS.replace('\n', NL)

old_f = NL + "# ============================================================" + NL + "# K线数据解析" + NL
assert s.count(old_f) == 1, 'K线数据解析 段头锚点不唯一'
s = s.replace(old_f, FUNCS + old_f.lstrip(NL))

shutil.copy2(P, P + '.bak_before_brkvr')
io.open(P, 'w', encoding='utf-8', newline='').write(s)
chk = io.open(P, encoding='utf-8', newline='').read()
_ok = all(k in chk for k in ['BRK_LOOKBACK', 'VR_SU_WIN', 'def detect_breakdown_recover',
                             'def volume_percentile', 'def detect_volume_regime'])
print('新 %d 行 ｜ CRLF=%d ｜ 裸LF=%d ｜ 关键字齐备=%s'
      % (chk.count('\n'), chk.count(NL), chk.count('\n') - chk.count(NL), _ok))
