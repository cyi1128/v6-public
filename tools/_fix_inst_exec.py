# -*- coding: utf-8 -*-
"""机构/量化执行标准落地：
涨停股侧  封成比 + 烂板识别（④）
可介入侧  流动性门槛 + 容量门槛 + 量化算法单痕迹（VWAP 偏离）
"""
import os
import shutil
import sys
import py_compile

sys.stdout.reconfigure(encoding='utf-8')
P = r'D:\QuantMonitorV6\services\board_anomaly_engine.py'
raw = open(P, 'rb').read()
assert raw.count(b'\r\n') == 0, '本文件应为纯 LF'
s = raw.decode('utf-8')
print('原行数 %d / %d bytes' % (len(s.splitlines()), len(raw)))


def rep(old, new, desc):
    global s
    n = s.count(old)
    assert n == 1, '[%s] 锚点命中 %d 次' % (desc, n)
    s = s.replace(old, new)
    print('  ✓ %s' % desc)


# ---------- 门槛常量 ----------
rep(
"""_PICK_TOP = 5""",
"""_PICK_MIN_AMOUNT = 2.0e8     # 机构门槛：当日成交额 ≥ 2 亿
_PICK_MIN_CMV = 20.0         # 机构门槛：流通市值 ≥ 20 亿（游资盘不碰）
_VWAP_DEV_MAX = 0.5          # 量化痕迹：|最新价 − VWAP| ≤ 0.5%
_VWAP_VR_MIN = 1.5           # 量化痕迹：量比 ≥ 1.5
_SEAL_ROTTEN = 0.10          # 封成比 < 0.10 且 ≥2 板 = 烂板
_PICK_TOP = 5""",
    '机构门槛常量')

# ---------- 封成比 / 烂板 ----------
rep(
"""def _dragon_key(rec, pct):
    \"\"\"① 情绪龙头排序键（升序）：连板身位 > 封板时段 > 封单强度 > 秒级时间。

    身位（连板高度）代表题材情绪高度，权重最高，用来判断题材能走多高；
    同身位比封板时段（越早越强，尾盘偷袭最弱）；
    同档再比封单强度；最后才用秒级首封时间兜底并列。
    它回答的是「这个题材谁最强」，不是「明天买谁」。
    \"\"\"
    t = (rec.get('time') or '').strip()
    return (0 if t else 1,
            -(rec.get('lbc') or 0),
            _seal_slot(t)[0],
            -_seal_strength(rec),
            t or '99:99')""",
"""def _seal_ratio(rec):
    \"\"\"封成比 = 封单额 / 当日成交额。

    业内判涨停板强度的主口径，衡量「封单还能接住今天多少卖盘」。
    实测 2026-10-09 的 69 只涨停股：
      时代万恒 5板 0.69 亿成交 封成比 3.33 ｜ 新华传媒 9板 6.26 亿 2.27
      澳弘电子 9板 10.67 亿成交 封成比 0.03 ｜ 九阳股份 5板 20.63 亿 0.04
      三人行   1板（炸板 6 次）    封成比 0.01
    也就是说：高位板不等于强板，封单相对成交额薄如纸的，是烂板。
    \"\"\"
    amt = rec.get('amount') or 0.0
    if amt <= 0:
        return 0.0
    return (rec.get('fund') or 0.0) / amt


def _is_rotten(rec):
    \"\"\"烂板：2 板及以上，且封成比 < 0.10（封单远小于当日成交额）。\"\"\"
    return ((rec.get('lbc') or 0) >= 2) and _seal_ratio(rec) < _SEAL_ROTTEN


def _dragon_key(rec, pct):
    \"\"\"① 情绪龙头排序键（升序）：
    连板身位 > 烂板(沉底) > 封板时段 > 封成比 > 封单强度 > 秒级时间。

    身位（连板高度）代表题材情绪高度，权重最高，用来判断题材能走多高；
    同身位内先把烂板沉到最后（封成比 < 0.10 的高位板是假板）；
    好板之间比封板时段（越早越强，尾盘偷袭最弱），
    再比封成比、封单强度，最后秒级时间兜底。
    它回答的是「这个题材谁最强」，不是「明天买谁」。
    \"\"\"
    t = (rec.get('time') or '').strip()
    return (0 if t else 1,
            -(rec.get('lbc') or 0),
            1 if _is_rotten(rec) else 0,
            _seal_slot(t)[0],
            -_seal_ratio(rec),
            -_seal_strength(rec),
            t or '99:99')""",
    '封成比 + 烂板识别 + 重写 _dragon_key')

# ---------- 接力键 ----------
rep(
"""def _entry_key(rec):
    \"\"\"次日接力排序键（升序）：身位低 > 封板早 > 封单强度大

    1 板和 2 板归同一档：首板是「发动」、二板是「确认」，各有各的道理，
    不能让身位把封板时段和封单强度架空 —— 否则就退回到「板数大者胜」，
    而板数恰恰是刚才被证伪的那个判据。
    \"\"\"
    lbc = rec.get('lbc') or 1
    pos = 0 if lbc <= 2 else (1 if lbc == 3 else 2)
    return (pos, _seal_slot(rec.get('time'))[0], -_seal_strength(rec))""",
"""def _entry_key(rec):
    \"\"\"次日接力排序键（升序）：身位低 > 封板早 > 封成比大 > 封单强度大

    1 板和 2 板归同一档：首板是「发动」、二板是「确认」，各有各的道理，
    不能让身位把封板时段和封成比架空 —— 否则就退回到「板数大者胜」，
    而板数恰恰是被封成比证伪的那个判据。
    \"\"\"
    lbc = rec.get('lbc') or 1
    pos = 0 if lbc <= 2 else (1 if lbc == 3 else 2)
    return (pos, _seal_slot(rec.get('time'))[0],
            -_seal_ratio(rec), -_seal_strength(rec))""",
    '接力键加封成比')

rep(
"""    cand = [m for m in mem
            if (m.get('lbc') or 1) <= _ENTRY_MAX_LBC
            and _seal_slot(m.get('time'))[0] <= _ENTRY_MAX_SLOT]
    if not cand:
        return None
    m = sorted(cand, key=_entry_key)[0]
    slot = _seal_slot(m.get('time'))
    return {'code': m['code'], 'name': m['name'],
            'pct': pct.get(m['code'], 0.0),
            'time': (m.get('time') or ''), 'slot_name': slot[1],
            'lbc': m.get('lbc') or 0, 'fund': m.get('fund') or 0.0,
            'strength': _seal_strength(m), 'zbc': m.get('zbc') or 0}""",
"""    cand = [m for m in mem
            if (m.get('lbc') or 1) <= _ENTRY_MAX_LBC
            and _seal_slot(m.get('time'))[0] <= _ENTRY_MAX_SLOT
            and not _is_rotten(m)]          # 烂板不做接力标的
    if not cand:
        return None
    m = sorted(cand, key=_entry_key)[0]
    slot = _seal_slot(m.get('time'))
    return {'code': m['code'], 'name': m['name'],
            'pct': pct.get(m['code'], 0.0),
            'time': (m.get('time') or ''), 'slot_name': slot[1],
            'lbc': m.get('lbc') or 0, 'fund': m.get('fund') or 0.0,
            'amount': m.get('amount') or 0.0,
            'ratio': _seal_ratio(m),
            'strength': _seal_strength(m), 'zbc': m.get('zbc') or 0}""",
    '接力候选排除烂板 + 带出封成比')

# ---------- 可介入池：机构门槛 + 量化痕迹 ----------
rep(
"""        if vr and vr < _PICK_MIN_VR:        # 量比取不到时不拦
            continue
        gap = None
        m20 = ma20.get(code)
        if m20:
            if px < m20:                    # 跌破 20 日均线不碰
                continue
            gap = round((px - m20) / m20 * 100.0, 2)   # 距MA20 涨幅%
        out.append([code, q.get('name') or '', round(pct, 2),
                    round(vr, 2), round(px, 2), gap])
    out.sort(key=lambda x: -x[2])
    return out[:_PICK_TOP]""",
"""        if vr and vr < _PICK_MIN_VR:        # 量比取不到时不拦
            continue
        # ---- 机构/量化执行标准 ----
        # 1) 流动性门槛：算法单按参与率拆单，成交额太小的票冲击成本吃不住
        # 2) 容量门槛：流通市值过小的游资盘/庄股，机构不进
        # 3) 量化痕迹：|最新价 − VWAP| 小且量比高 —— 算法单执行完的典型
        #    结果是价格贴着当日均价走，而不是脉冲式拉升
        amt = float(q.get('amount') or 0.0)
        cmv = float(q.get('circ_mv') or 0.0)
        hs = float(q.get('turnover') or 0.0)
        vol = float(q.get('volume') or 0.0)
        if amt and amt < _PICK_MIN_AMOUNT:
            continue
        if cmv and cmv < _PICK_MIN_CMV:
            continue
        vwap = (amt / (vol * 100.0)) if (amt > 0 and vol > 0) else 0.0
        dev = ((px - vwap) / vwap * 100.0) if vwap > 0 else None
        inst = 1 if (dev is not None and abs(dev) <= _VWAP_DEV_MAX
                     and vr >= _VWAP_VR_MIN) else 0
        gap = None
        m20 = ma20.get(code)
        if m20:
            if px < m20:                    # 跌破 20 日均线不碰
                continue
            gap = round((px - m20) / m20 * 100.0, 2)   # 距MA20 涨幅%
        out.append([code, q.get('name') or '', round(pct, 2),
                    round(vr, 2), round(px, 2), gap,
                    round(amt / 1e8, 2), round(cmv, 1), round(hs, 2),
                    (round(dev, 2) if dev is not None else None), inst])
    # 排序即机构标准：量化痕迹优先 → 成交额大优先 → 涨幅优先
    out.sort(key=lambda x: (-x[10], -x[6], -x[2]))
    return out[:_PICK_TOP]""",
    '可介入池加机构门槛 + 量化痕迹')

shutil.copy2(P, P + '.bak_before_inst_exec')
open(P, 'wb').write(s.encode('utf-8'))
print()
print('已写入 %s (%d bytes, %d 行)' % (P, os.path.getsize(P),
                                      len(s.splitlines())))
py_compile.compile(P, doraise=True)
print('py_compile OK')
