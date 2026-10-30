# -*- coding: utf-8 -*-
"""一次性补丁：在 strategy/base.py 里加入「拉升阶段识别」detect_markup()（2026-10-11）。

只做两件事：
  1. 在 DIST_MIN_BARS 常量之后插入 MARKUP_* 常量块
  2. 在「K线数据解析」分隔线之前插入 TechnicalIndicators.detect_markup()

不动任何既有常量 / 既有方法。写完 py_compile + 实调验证。
"""
import io
import os
import py_compile
import shutil
import sys

sys.stdout.reconfigure(encoding='utf-8')

ROOT = r'D:\QuantMonitorV6'
TGT = os.path.join(ROOT, 'strategy', 'base.py')
BAK = TGT + '.bak_before_markup'

CONSTS = '''
# ---- 拉升阶段识别（观察规则）阈值（2026-10-11）----
# 识别「主力已经进入拉升阶段」的三种可量化形态（与试盘/出货形态同族，只做【观察】）：
#   ① 阶梯式上行（趋势型拉升）：均线多头排列 + 整体抬升 + 上涨放量/回调缩量 + 回调不破 MA20
#   ② 缩量强势（锁仓式拉升）：连续收阳/低点抬高 + 量能反而萎缩或维持低位 + 位置偏高
#   ③ 加速迹象（末段急拉）  ：短窗口涨幅大 + 量能放大 + 接近或创阶段新高
# ⚠ 方向说明（别用反）：C4 / C6 / 试盘找的是「低位、启动前」；本函数找的是「已经拉起来」。
#   在本项目「买在启动前、不接飞刀」的框架下，它是【追高提示 / 排他标记】，不是买入提示。
# 标定见 tools\\markup_calib.txt（tools\\_calib_markup.py 生成；锚点 k=20/40/60/80，无未来数据）。
MARKUP_MA_FAST = 5          # ① 均线多头排列：MA5 > MA10 > MA20
MARKUP_MA_MID = 10
MARKUP_MA_SLOW = 20
MARKUP_TREND_WIN = 10       # ① 近 10 根做「整体抬升 / 上涨放量回调缩量 / 不破 MA20」判定
MARKUP_TREND_GAIN = 0.06    # ① 近窗口累计涨幅下限（收盘口径）
MARKUP_PULLBACK_TOL = 0.03  # ① 回调容忍度：窗口最低价 >= MA20 x (1 - 该值)
MARKUP_UP_DN_VOL = 1.00     # ① 上涨日均量 / 下跌日均量 下限
MARKUP_LOCK_WIN = 8         # ② 锁仓式窗口
MARKUP_LOCK_YANG_MIN = 0.60  # ② 阳线占比下限（连续收阳/稳步抬升）
MARKUP_LOCK_VOL_MAX = 1.00  # ② 近窗口均量 / 更早窗口均量 上限（萎缩或维持低位）
MARKUP_LOCK_POS_MIN = 0.55  # ② 位置下限（锁仓拉升必然已离开底部）
MARKUP_ACC_WIN = 5          # ③ 加速窗口
MARKUP_ACC_GAIN = 0.12      # ③ 近窗口累计涨幅下限
MARKUP_ACC_VOL = 1.30       # ③ 近窗口均量 / 前窗口均量 下限（量能放大）
MARKUP_ACC_HI_TOL = 0.98    # ③ 收盘 >= 近60日最高 x 该值 = 接近/创阶段新高
MARKUP_SCORE_OK = 70.0      # 同 PROBE_SCORE_OK：ok=True 必 >=70，未通过必 <=60
MARKUP_MIN_BARS = 60        # 最少K线根数
'''

METHOD = r'''    @staticmethod
    def detect_markup(df):
        """拉升阶段识别（观察规则）：阶梯式上行 / 缩量强势 / 加速迹象。

        与 detect_probe（试盘）、detect_distribution_pattern（出货形态）同族：
        都是【观察】规则，禁止参与 signal_level / 建仓价 / 排序 / 等级。

        ⚠ 方向说明（重要，别用反）
        --------------------------
        C4 / C6 / 试盘找的是「低位、启动前」；本函数找的是「已经拉起来」的票。
        结合本项目「买在启动前、不接飞刀」的建仓框架，这个标记的现实用途是
        【追高提示 / 排他标记】——告诉你「这只已经不便宜了」，而不是「可以买」。
        标定结果（tools\\markup_calib.txt）必须按这个口径解读。

        参数
        ----
        df : pandas.DataFrame
            至少含 open/high/low/close/volume，且不少于 MARKUP_MIN_BARS(60) 根。

        返回
        ----
        dict :
            {'ok': bool, 'type': str, 'score': float, 'n_ok': int, 'hits': list[bool],
             'pos120': float|None, 'gain': float|None, 'vol_ratio': float|None,
             'detail': dict, 'reason': str}
            ok     —— 三种形态至少一种成立
            type   —— '阶梯式上行' / '缩量强势' / '加速迹象' / ''（未命中）
            score  —— 0~100 两段不重叠：ok=True 必 >= MARKUP_SCORE_OK(70)，未通过必 <= 60
            hits   —— 命中形态（未命中时为 ① 的判据）逐条 bool
            gain   —— 命中形态对应的窗口累计涨幅（收盘口径）
            vol_ratio —— 命中形态对应的量能比（① 上涨/下跌均量比；② 近/前均量比；③ 加速量比）
            detail —— 关键中间值（均线 / 各形态涨幅与量能比 / 阳线占比 / 近60日最高）

        判据
        ----
        ① 阶梯式上行（趋势型拉升）
           A1 MA5 > MA10 > MA20（多头排列）
           A2 近 MARKUP_TREND_WIN(10) 根累计涨幅 >= MARKUP_TREND_GAIN(6%)
           A3 近窗口「上涨日均量 / 下跌日均量」>= MARKUP_UP_DN_VOL(1.00)
              （没有下跌日时该条不成立 —— 不把「无回调」当成放量上涨）
           A4 近窗口最低价 >= MA20 x (1 - MARKUP_PULLBACK_TOL(3%))（回调不破关键均线）
        ② 缩量强势（锁仓式拉升）
           B1 近 MARKUP_LOCK_WIN(8) 根阳线占比 >= MARKUP_LOCK_YANG_MIN(60%)
           B2 近窗口均量 / 更早窗口均量 <= MARKUP_LOCK_VOL_MAX(1.00)（缩量或低位维持）
           B3 pos120 >= MARKUP_LOCK_POS_MIN(0.55)（锁仓拉升必然已离开底部）
           B4 低点抬高：后半窗口最低价 >= 前半窗口最低价
        ③ 加速迹象（末段急拉）
           C1 近 MARKUP_ACC_WIN(5) 根累计涨幅 >= MARKUP_ACC_GAIN(12%)
           C2 近窗口均量 / 前窗口均量 >= MARKUP_ACC_VOL(1.30)（量能放大）
           C3 收盘 >= 近60日最高 x MARKUP_ACC_HI_TOL(0.98)（接近/创阶段新高）

        命中多个形态时取分数最高的那个（与出货形态同一策略）。
        """
        _bad = {'ok': False, 'type': '', 'score': 0.0, 'n_ok': 0, 'hits': [],
                'pos120': None, 'gain': None, 'vol_ratio': None,
                'detail': {}, 'reason': ''}
        try:
            if df is None or len(df) < MARKUP_MIN_BARS:
                r = dict(_bad)
                r['reason'] = 'bars<%d' % MARKUP_MIN_BARS
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

            def _c01(x):
                return min(1.0, max(0.0, float(x)))

            def _mav(a, k):
                return float(np.mean(a[-k:])) if len(a) >= k else 0.0

            ma5 = _mav(c, MARKUP_MA_FAST)
            ma10 = _mav(c, MARKUP_MA_MID)
            ma20 = _mav(c, MARKUP_MA_SLOW)
            c120 = c[-120:]
            _mn, _mx = float(np.min(c120)), float(np.max(c120))
            pos = (float(c[-1]) - _mn) / (_mx - _mn + 1e-8)
            hi60 = float(np.max(h[-60:]))

            # ---------------- ① 阶梯式上行 ----------------
            tw = MARKUP_TREND_WIN
            base_t = float(c[max(0, n - 1 - tw)])
            gain_t = (float(c[-1]) - base_t) / (base_t + 1e-9)
            up_v, dn_v = [], []
            for i in range(max(1, n - tw), n):
                if c[i] > c[i - 1]:
                    up_v.append(float(v[i]))
                elif c[i] < c[i - 1]:
                    dn_v.append(float(v[i]))
            udv = (float(np.mean(up_v)) / (float(np.mean(dn_v)) + 1e-9)
                   if (up_v and dn_v) else 0.0)
            trend_ma = bool(ma5 > ma10 > ma20)
            trend_up = bool(gain_t >= MARKUP_TREND_GAIN)
            trend_vol = bool(up_v and dn_v and udv >= MARKUP_UP_DN_VOL)
            trend_hold = bool(float(np.min(lw[-tw:])) >= ma20 * (1.0 - MARKUP_PULLBACK_TOL))
            aa = [trend_ma, trend_up, trend_vol, trend_hold]
            a_ok = all(aa)
            if a_ok:
                a_sc = MARKUP_SCORE_OK + 30.0 * _c01(
                    0.30 * _c01((ma5 / (ma20 + 1e-9) - 1.0) / 0.06)
                    + 0.30 * _c01((gain_t - MARKUP_TREND_GAIN) / 0.14)
                    + 0.25 * _c01((udv - MARKUP_UP_DN_VOL) / 0.60)
                    + 0.15 * _c01((pos - 0.35) / 0.45))
            else:
                a_sc = 60.0 * _c01(
                    0.25 * _c01((ma5 / (ma20 + 1e-9) - 0.99) / 0.05)
                    + 0.25 * _c01((gain_t - 0.01) / 0.09)
                    + 0.25 * _c01((udv - 0.70) / 0.60)
                    + 0.25 * _c01(1.0 - abs(float(np.min(lw[-tw:]))
                                            / (ma20 + 1e-9) - 1.0) / 0.10))

            # ---------------- ② 缩量强势 ----------------
            wl = MARKUP_LOCK_WIN
            yang = (sum(1 for i in range(max(0, n - wl), n) if c[i] > o[i]) / float(wl))
            v_rec = float(np.mean(v[-wl:]))
            v_prev = (float(np.mean(v[max(0, n - 3 * wl):n - wl]))
                      if n > wl else v_rec)
            lock_vr = v_rec / (v_prev + 1e-9)
            lock_yang = bool(yang >= MARKUP_LOCK_YANG_MIN)
            lock_vol = bool(lock_vr <= MARKUP_LOCK_VOL_MAX)
            lock_pos = bool(pos >= MARKUP_LOCK_POS_MIN)
            half = max(1, wl // 2)
            lo_prev = float(np.min(lw[max(0, n - wl):max(0, n - half)]))
            lo_last = float(np.min(lw[max(0, n - half):]))
            lock_rise = bool(lo_last >= lo_prev)
            base_l = float(c[max(0, n - 1 - wl)])
            lock_gain = (float(c[-1]) - base_l) / (base_l + 1e-9)
            bb = [lock_yang, lock_vol, lock_pos, lock_rise]
            b_ok = all(bb)
            if b_ok:
                b_sc = MARKUP_SCORE_OK + 30.0 * _c01(
                    0.30 * _c01((yang - MARKUP_LOCK_YANG_MIN) / 0.35)
                    + 0.35 * _c01((MARKUP_LOCK_VOL_MAX - lock_vr) / 0.45)
                    + 0.20 * _c01((pos - MARKUP_LOCK_POS_MIN) / 0.35)
                    + 0.15 * _c01(lock_gain / 0.20))
            else:
                b_sc = 60.0 * _c01(
                    0.30 * _c01((yang - 0.40) / 0.40)
                    + 0.30 * _c01((1.20 - lock_vr) / 0.60)
                    + 0.20 * _c01((pos - 0.40) / 0.40)
                    + 0.20 * (1.0 if lock_rise else 0.30))

            # ---------------- ③ 加速迹象 ----------------
            aw = MARKUP_ACC_WIN
            base_a = float(c[max(0, n - 1 - aw)])
            gain_a = (float(c[-1]) - base_a) / (base_a + 1e-9)
            v_a = v[-aw:]
            v_b = v[max(0, n - 2 * aw):max(0, n - aw)]
            acc_vr = (float(np.mean(v_a) / (np.mean(v_b) + 1e-9))
                      if len(v_b) else 0.0)
            acc_gain = bool(gain_a >= MARKUP_ACC_GAIN)
            acc_vol = bool(acc_vr >= MARKUP_ACC_VOL)
            acc_high = bool(c[-1] >= hi60 * MARKUP_ACC_HI_TOL)
            cc = [acc_gain, acc_vol, acc_high]
            c_ok = all(cc)
            if c_ok:
                c_sc = MARKUP_SCORE_OK + 30.0 * _c01(
                    0.40 * _c01((gain_a - MARKUP_ACC_GAIN) / 0.15)
                    + 0.35 * _c01((acc_vr - MARKUP_ACC_VOL) / 1.20)
                    + 0.25 * _c01((c[-1] / (hi60 + 1e-9) - MARKUP_ACC_HI_TOL) / 0.06))
            else:
                c_sc = 60.0 * _c01(
                    0.40 * _c01((gain_a - 0.03) / 0.12)
                    + 0.35 * _c01((acc_vr - 0.90) / 1.00)
                    + 0.25 * _c01((c[-1] / (hi60 + 1e-9) - 0.90) / 0.10))

            cands = []
            if a_ok:
                cands.append(('阶梯式上行', a_sc, aa))
            if b_ok:
                cands.append(('缩量强势', b_sc, bb))
            if c_ok:
                cands.append(('加速迹象', c_sc, cc))
            detail = {'ma5': ma5, 'ma10': ma10, 'ma20': ma20,
                      'gain_trend': float(gain_t), 'up_dn_vol': float(udv),
                      'yang_ratio': float(yang), 'lock_vr': float(lock_vr),
                      'lock_gain': float(lock_gain), 'gain_acc': float(gain_a),
                      'acc_vr': float(acc_vr), 'hi60': hi60}
            if cands:
                cands.sort(key=lambda x: -x[1])
                _t, _sc, _hits = cands[0]
                if _t == '阶梯式上行':
                    _g, _vr = float(gain_t), float(udv)
                elif _t == '缩量强势':
                    _g, _vr = float(lock_gain), float(lock_vr)
                else:
                    _g, _vr = float(gain_a), float(acc_vr)
                return {'ok': True, 'type': _t, 'score': float(_sc),
                        'n_ok': int(sum(1 for x in _hits if x)), 'hits': list(_hits),
                        'pos120': float(pos), 'gain': _g, 'vol_ratio': _vr,
                        'detail': detail, 'reason': ''}
            return {'ok': False, 'type': '', 'score': float(max(a_sc, b_sc, c_sc)),
                    'n_ok': max(int(sum(1 for x in aa if x)),
                                int(sum(1 for x in bb if x)),
                                int(sum(1 for x in cc if x))),
                    'hits': aa, 'pos120': float(pos), 'gain': float(gain_t),
                    'vol_ratio': float(udv), 'detail': detail, 'reason': ''}
        except Exception as _e:
            r = dict(_bad)
            r['reason'] = type(_e).__name__
            return r

'''


def main():
    raw = io.open(TGT, 'rb').read()
    crlf, lf = raw.count(b'\r\n'), raw.count(b'\n') - raw.count(b'\r\n')
    print('改动前：CRLF=%d 裸LF=%d 行数=%d' % (crlf, lf, raw.count(b'\n')))
    assert lf == 0, 'base.py 不是纯 CRLF，先人工确认'

    shutil.copy2(TGT, BAK)
    print('已备份 ->', os.path.basename(BAK))

    s = raw.decode('utf-8').replace('\r\n', '\n')
    lines = s.splitlines(keepends=True)

    # --- 1) 常量块：插在 DIST_MIN_BARS 那一行之后 ---
    idx_c = [i for i, ln in enumerate(lines) if ln.startswith('DIST_MIN_BARS = 60')]
    assert len(idx_c) == 1, 'DIST_MIN_BARS 锚点数量异常: %d' % len(idx_c)
    ic = idx_c[0]
    assert lines[ic + 1].strip() == '', 'DIST_MIN_BARS 之后不是空行'
    lines[ic + 1:ic + 1] = [CONSTS.lstrip('\n')]
    print('常量块插在第 %d 行之后' % (ic + 1))

    # --- 2) 方法：插在「K线数据解析」分隔线之前 ---
    idx_k = [i for i, ln in enumerate(lines) if ln.strip() == '# K线数据解析']
    assert len(idx_k) == 1, 'K线数据解析 锚点数量异常: %d' % len(idx_k)
    ik = idx_k[0]
    assert lines[ik - 1].startswith('# ====='), '分隔线位置异常'
    lines[ik - 1:ik - 1] = [METHOD]
    print('方法插在第 %d 行之前（原分隔线）' % (ik))

    out = ''.join(lines)
    assert 'def detect_markup(df):' in out
    assert out.count('def detect_probe(df):') == 1
    assert out.count('def detect_distribution_pattern(df):') == 1
    io.open(TGT, 'wb').write(out.replace('\n', '\r\n').encode('utf-8'))

    raw2 = io.open(TGT, 'rb').read()
    crlf2, lf2 = raw2.count(b'\r\n'), raw2.count(b'\n') - raw2.count(b'\r\n')
    print('改动后：CRLF=%d 裸LF=%d 行数=%d' % (crlf2, lf2, raw2.count(b'\n')))
    assert lf2 == 0
    py_compile.compile(TGT, doraise=True)
    print('py_compile OK')


if __name__ == '__main__':
    main()
