# -*- coding: utf-8 -*-
"""主力痕迹扫描器 zhu_force_scan v2：六条件规则扫描（地量死寂/红肥绿瘦/坑底指纹/试盘脉冲/换手窗口/突破确认）
设计：
  1. get_snapshot 用 ABR 已验证字段集（f2,f3,f12,f14,f127）拉全市场 5000 只（东财 push2，云端可用）
  2. ThreadPoolExecutor 多线程拉 40 根 K 线 + 五条件预筛（1/2/3/4/6），≥4 条进预备池
  3. 预备池内腾讯 qt 单票补流通市值(f44)/换手(f38) → 流通股本 → 条件5 → 六条件≥5条 → 评分100 → JSON
剔除：ST/科创/北交/次新<365天(东财f26云端探针，失败降级K线长度近似)/流通市值<30亿。"""
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')

_UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
WORKERS = 16


def _http_get(url, timeout=15):
    req = urllib.request.Request(url, headers=_UA)
    return urllib.request.urlopen(req, timeout=timeout).read().decode('utf-8', 'ignore')


def get_snapshot():
    """全市场快照（沪深A股）：新浪 Market_Center 分页。code/name/pct/float_mv_yi(nmc万)/turn_today。
    node=hs_a 沪深A股全市场；分页 num=100；失败返回 []。"""
    out = []
    page = 1
    while page <= 80:
        url = ('http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData'
               f'?page={page}&num=100&sort=symbol&asc=1&node=hs_a&symbol=&_s_r_a=init')
        try:
            req = urllib.request.Request(url, headers={**_UA, 'Referer': 'https://finance.sina.com.cn/'})
            txt = urllib.request.urlopen(req, timeout=12).read().decode('utf-8', 'ignore')
            d = json.loads(txt)
            if not isinstance(d, list) or not d:
                break
            for x in d:
                c = str(x.get('code') or '').strip()
                n = str(x.get('name') or '').strip()
                if not c or not n:
                    continue
                try:
                    nmc = float(x.get('nmc') or 0) / 10000.0      # 流通市值 万->亿
                except (TypeError, ValueError):
                    nmc = 0.0
                out.append({'code': c, 'name': n, 'industry': '其他',
                            'pct': float(x.get('changepercent') or 0),
                            'float_mv_yi': nmc,
                            'turn_today': float(x.get('turnoverratio') or 0)})
            if len(d) < 100:
                break
            page += 1
            if page % 20 == 0:
                print(f'[snapshot] 新浪分页 {page} 已拉 {len(out)} 只')
        except Exception as e:
            # 分页失败退避重试 2 次（盘中新浪接口限速常见）；仍失败则用已拉到的数据继续
            ok_page = False
            for _rt in (1, 2):
                time.sleep(1.0 * _rt)
                try:
                    req = urllib.request.Request(url, headers={**_UA, 'Referer': 'https://finance.sina.com.cn/'})
                    txt = urllib.request.urlopen(req, timeout=15).read().decode('utf-8', 'ignore')
                    d = json.loads(txt)
                    if isinstance(d, list) and d:
                        for x in d:
                            c = str(x.get('code') or '').strip()
                            n = str(x.get('name') or '').strip()
                            if not c or not n:
                                continue
                            try:
                                nmc = float(x.get('nmc') or 0) / 10000.0
                            except (TypeError, ValueError):
                                nmc = 0.0
                            try:
                                t0 = float(x.get('turnoverratio') or x.get('turnratio') or 0)
                            except (TypeError, ValueError):
                                t0 = 0.0
                            out.append({'code': c, 'name': n, 'pct': float(x.get('changepercent') or 0),
                                        'float_mv_yi': nmc, 'turn_today': t0})
                        ok_page = True
                        print(f'[snapshot] 新浪分页 {page} 重试成功 {len(out)} 只')
                        break
                except Exception:
                    continue
            if not ok_page:
                print('[snapshot] 新浪分页异常(重试后仍失败) page', page, type(e).__name__, str(e)[:60])
                break
    print(f'[snapshot] 新浪快照 {len(out)} 只')
    return out


def get_kline(code, n=40):
    """日线K线：腾讯 ifzq 主源 → 新浪备源。返回 list[{date,open,close,high,low,volume,amount}] 或 None。"""
    sym = ('sh' if code.startswith('6') else 'sz') + code
    try:
        url = f'http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,,,{n},qfq'
        txt = _http_get(url, timeout=10)
        node = (json.loads(txt).get('data') or {}).get(sym, {}) or {}
        rows = node.get('qfqday') or node.get('day') or []
        if len(rows) >= 30:
            out = []
            for p in rows:
                try:
                    c = float(p[2])
                    out.append({'date': p[0], 'open': float(p[1]), 'close': c,
                                'high': float(p[3]), 'low': float(p[4]),
                                'volume': float(p[5]) * 100, 'amount': float(p[5]) * c * 10000})
                except Exception:
                    continue
            return out
    except Exception:
        pass
    try:
        url = ('http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData'
               f'?symbol={sym}&scale=240&ma=no&datalen={n}')
        txt = _http_get(url, timeout=10)
        d = json.loads(txt)
        if isinstance(d, list) and len(d) >= 30:
            out = []
            for x in d:
                try:
                    c = float(x['close'])
                    v = float(x['volume'])
                    out.append({'date': x['day'][:10], 'open': float(x['open']), 'close': c,
                                'high': float(x['high']), 'low': float(x['low']),
                                'volume': v, 'amount': v * c})
                except Exception:
                    continue
            return out
    except Exception:
        pass
    return None


def _qt_float_quote(code):
    """腾讯 qt 单票：返回 {float_mv_yi(f44), turn_today(f38)} 或 None。"""
    sym = ('sh' if code.startswith('6') else 'sz') + code
    try:
        txt = _http_get(f'http://qt.gtimg.cn/q={sym}', timeout=8)
        m = re.search(r'"([^"]*)"', txt)
        if not m:
            return None
        f = m.group(1).split('~')
        # f38=当日换手率(%), f44=流通市值(亿), f45=总市值(亿)
        def _g(i):
            try:
                return float(f[i]) if len(f) > i and f[i] else None
            except (ValueError, IndexError):
                return None
        return {'float_mv_yi': _g(44), 'turn_today': _g(38)}
    except Exception:
        return None


def _list_date_approx(kl):
    """上市日期近似：K线首根日期 + 根数推断。返回 'YYYYMMDD' 或 ''。"""
    if not kl:
        return ''
    d0 = kl[0]['date']
    try:
        dt = datetime.strptime(d0[:10], '%Y-%m-%d')
        # 40根≈56自然日；上市日 ≈ 首根前 40交易日 约为 首根-56天 偏保守
        return (dt - timedelta(days=56)).strftime('%Y%m%d')
    except Exception:
        return ''


# ==================== 六条件 ====================
def cond_dead(kl):
    """条件1 地量死寂：近8日内连续≥5日 量<60日均量*0.5（不足60日用30日均量*0.45），箱体振幅≤0.15。"""
    vols = [r['volume'] for r in kl]
    if len(vols) < 12:
        return False, 0, None, None, False
    base = 60 if len(vols) >= 60 else 30
    avg60 = sum(vols[-base - 8:-8]) / base if len(vols) >= base + 8 else sum(vols[:-8]) / max(len(vols) - 8, 1)
    thr = avg60 * (0.5 if base == 60 else 0.45)
    best = sum(1 for r in kl[-12:] if r['volume'] < thr)
    seg_kl = kl[-12:]
    lo = min(r['low'] for r in seg_kl)
    hi = max(r['high'] for r in seg_kl)
    amp = (hi - lo) / lo if lo else 1
    at_pit = bool(kl) and (kl[-1]['close'] - lo) / lo <= 0.03
    if amp > 0.18 or (best < 4 and at_pit):
        # 补丁4: 现价在近12日窗低位=打压吸筹候选（砸盘段不受箱体振幅<=18%限制、死寂改坑底段算）
        if at_pit:
            return True, best, lo, hi, True
        return False, best, lo, hi, False
    if best < 4:
        return False, 0, None, None, False
    return True, best, lo, hi, False


def cond_redgreen(kl):
    """条件2 红肥绿瘦：近10日 阳线日均量/阴线日均量 ≥1.2。"""
    last10 = kl[-10:]
    yang = [r['volume'] for r in last10 if r['close'] > r['open']]
    yin = [r['volume'] for r in last10 if r['close'] < r['open']]
    avg_yang = sum(yang) / len(yang) if yang else 0
    avg_yin = sum(yin) / len(yin) if yin else 0
    if avg_yin == 0:
        return True, 999.0
    if avg_yang == 0:
        return False, 0.0
    ratio = avg_yang / avg_yin
    return ratio >= 1.2, round(ratio, 2)


def cond_pit(kl):
    """条件3 坑底指纹：近10日 单日量<5日均量*0.5 且（长下影 下影≥实体*2 或 十字星 实体/振幅<0.3）。"""
    vols = [r['volume'] for r in kl]
    if len(vols) < 10:
        return False
    for i, r in enumerate(kl[-10:]):
        j = len(vols) - 10 + i
        ma5 = sum(vols[max(0, j - 4):j + 1]) / 5
        if r['volume'] >= ma5 * 0.6:
            continue
        amp = r['high'] - r['low']
        if amp <= 0:
            continue
        body = abs(r['close'] - r['open'])
        lower_shadow = min(r['close'], r['open']) - r['low']
        if body > 0 and lower_shadow >= body * 2:
            return True
        if body / amp < 0.3:
            return True
    return False


def cond_trial(kl):
    """条件4 试盘脉冲：近10日 1-2根 量在5日均量1.5-2.5倍 且涨幅3-7% 且次日守住涨幅一半以上。"""
    vols = [r['volume'] for r in kl]
    n = len(vols)
    if n < 11:
        return False, 0
    cnt = 0
    for i in range(max(0, n - 10), n):
        ma5 = sum(vols[max(0, i - 4):i + 1]) / 5
        r = kl[i]
        vratio = r['volume'] / ma5 if ma5 else 0
        if not (1.3 <= vratio <= 2.5):
            continue
        pct = (r['close'] - r['open']) / r['open'] * 100 if r['open'] else 0
        if not (3 <= pct <= 7):
            continue
        if i + 1 < n:
            half = r['open'] + (r['close'] - r['open']) * 0.5
            if kl[i + 1]['close'] < half:
                continue
        cnt += 1
    return 1 <= cnt <= 2, cnt


def cond_break(kl):
    """条件6 突破确认：近3日 量≥5日均量2.5倍阳线收盘破近20日箱体上沿，次日缩量(<0.8倍)且不破。"""
    vols = [r['volume'] for r in kl]
    n = len(vols)
    if n < 25:
        return None
    for i in range(max(0, n - 3), n):
        r = kl[i]
        if r['close'] <= r['open']:
            continue
        ma5 = sum(vols[max(0, i - 4):i + 1]) / 5
        if ma5 <= 0 or r['volume'] < ma5 * 2.0:
            continue
        box_high = max(kl[j]['high'] for j in range(max(0, i - 20), i))
        if r['close'] <= box_high:
            continue
        if i + 1 < n:
            nxt = kl[i + 1]
            if nxt['volume'] >= r['volume'] * 1.0:
                continue
            if nxt['close'] < box_high:
                continue
        full = r['volume'] >= ma5 * 2.5
        return (True, full)
    return None


def _quick_conds(kl):
    """五条件预筛（1/2/3/4/6，K线可算，>=3条）。返回 (hits_set, dead_days, rg_ratio, trial_cnt, break_res) 或 None。"""
    ok1, dd, lo, hi, _pitc = cond_dead(kl)
    ok2, rg = cond_redgreen(kl)
    ok3 = cond_pit(kl)
    ok4, tc = cond_trial(kl)
    ok6 = cond_break(kl)
    return {1: ok1, 2: ok2, 3: ok3, 4: ok4, 6: bool(ok6)}, dd, rg, tc, ok6, _pitc


def _pit_validate(kl):
    """打压吸筹三要件（缺一不可，内部找砸盘前箱体）：
    ①砸盘段（跌穿箱体）放量 ≥1.5x 均量（非阴跌缩量滑下去）
    ②坑底出现：单日量 <0.5x 均量 + 长下影(下影≥实体*2)或十字星 ≥1次
    ③坑底日收盘价距砸盘前箱体下沿跌幅 8%-25%（太浅没吓出筹码/太深是出货）
    返回 dict 或 None（缺要件=真破位剔除）。"""
    n = len(kl)
    if n < 25:
        return None
    dump_i = None
    # 找砸盘起点：近14日内 单日跌幅>=4% 或 3日累计跌>=8% 的放量下跌段
    for i in range(max(1, n - 14), n):
        r = kl[i]
        drop = (kl[i - 1]['close'] - r['close']) / kl[i - 1]['close'] if kl[i - 1]['close'] else 0
        if drop >= 0.04:
            dump_i = i
            break
        if i >= 2:
            drop3 = (kl[i - 3]['close'] - r['close']) / kl[i - 3]['close'] if kl[i - 3]['close'] else 0
            if drop3 >= 0.08:
                dump_i = i
                break
    if dump_i is None:
        return None
    # 砸盘前箱体 = 砸盘日前 20 日
    pre = kl[max(0, dump_i - 20):dump_i]
    if len(pre) < 12:
        return None
    pre_low = min(r['low'] for r in pre)
    pre_high = max(r['high'] for r in pre)
    ma_pre = sum(r['volume'] for r in pre) / len(pre)
    if ma_pre <= 0:
        return None
    # ①砸盘段放量 >=1.5x 均量（非阴跌缩量滑下去）
    dump_vol = max(r['volume'] for r in kl[dump_i:min(n, dump_i + 4)])
    if dump_vol < ma_pre * 1.5:
        return None
    # ②坑底：砸盘后 单日量 <0.5x 均量 + 长下影/十字星 >=1次
    pit_ok = False
    for r in kl[dump_i + 1:]:
        body = abs(r['close'] - r['open'])
        amp = (r['high'] - r['low']) or 1
        lower_shadow = min(r['close'], r['open']) - r['low']
        if r['volume'] < ma_pre * 0.5 and (lower_shadow >= body * 2 or body / amp < 0.3):
            pit_ok = True
            break
    if not pit_ok:
        return None
    # ③坑底收盘距砸盘前箱体下沿跌幅 8%-25%
    depth = (pre_low - kl[-1]['close']) / pre_low if pre_low else 0
    if not (0.08 <= depth <= 0.25):
        return None
    return {'dump_i': dump_i, 'depth': round(depth, 3), 'ma_pre': ma_pre,
            'pre_low': pre_low, 'pre_high': pre_high}


def _rally_check(kl, box_high, price):
    """拉高吸筹：近3日 ≥2日 量2-2.5x均量 阳线 且现价>箱体上沿未涨停。返回拉高段均价或 None。"""
    vols = [r['volume'] for r in kl]
    n = len(vols)
    if n < 8:
        return None
    ma5 = sum(vols[-6:-1]) / 5
    if ma5 <= 0:
        return None
    recent = kl[-3:]
    up = [r for r in recent if r['close'] > r['open'] and ma5 * 2 <= r['volume'] <= ma5 * 2.5]
    if len(up) >= 2 and price > box_high:
        return round(sum(r['close'] for r in recent) / 3, 2)
    return None


def score_conditions(kl, conds, dead_days, rg_ratio):
    """评分（100分）。conds: dict(1..6)。"""
    s = 0
    if conds.get(1):
        s += min(30, 20 + max(0, dead_days - 5) * 2)
    if conds.get(2) and rg_ratio and rg_ratio < 999:
        s += min(25, 15 + int((rg_ratio - 1.2) * 10) * 2)
    elif conds.get(2) and rg_ratio == 999:
        s += 20
    if conds.get(3):
        s += 15
    if conds.get(4):
        s += 10
    br = conds.get(6)
    if br:
        s += 15 if (isinstance(br, tuple) and br[1]) else 8
    if conds.get(1):
        lo = min(r['low'] for r in kl[-dead_days:])
        hi = max(r['high'] for r in kl[-dead_days:])
        if lo and (hi - lo) / lo <= 0.10:
            s += 5
    return s


def _finish_hit(s, kl, pre, float_info, list_date_str):
    """预备池内补齐：条件5换手 + 流通市值/次新过滤 + 评分 + 输出 dict。"""
    code, name, industry = s['code'], s['name'], s['industry']
    price = float(kl[-1]['close'])
    # FIX21: 现价 >= 5日线（用户铁律：只做站上5日线的票；等于5日线算通过）
    ma5 = sum(r['close'] for r in kl[-5:]) / 5 if len(kl) >= 5 else price
    above_ma5 = price >= ma5
    float_mv_yi = float_info or 0
    if float_mv_yi < 30:
        return None
    float_mv = float_mv_yi * 1e8
    float_share = float_mv / price if price else 0
    # 次新过滤（<365天）：东财f26探针失败时用 K线长度近似
    if list_date_str and len(list_date_str) >= 8:
        try:
            if (datetime.now() - datetime.strptime(list_date_str[:8], '%Y%m%d')).days < 365:
                return None
        except Exception:
            pass
    elif len(kl) < 35:
        return None                                   # 40根不满≈次新
    is_cyb = code.startswith('30')
    avg_turn = None
    if float_share > 0:
        avg_turn = sum(r['volume'] / float_share * 100 for r in kl[-10:]) / 10
    ok5 = (2.0 <= avg_turn <= 7.0) if is_cyb else (0.3 <= avg_turn <= 6.0) if avg_turn is not None else False
    conds, dd, rg, tc, ok6, _pitc = pre
    conds[5] = ok5
    hit = [k for k, v in conds.items() if v]
    # ===== 补丁1: 手法分类 + 位置校验（坑底候选校验先行） =====
    method_type, state, next_watch = '横盘吸筹', '箱体内', ''
    seg12 = kl[-12:]
    lo12 = min(r['low'] for r in seg12)
    hi12 = max(r['high'] for r in seg12)
    at_pit = (price - lo12) / lo12 <= 0.03 and (hi12 - lo12) / lo12 > 0.12
    pit = _pit_validate(kl) if at_pit else None
    if pit is None and len(hit) < 4:
        return None                                   # 非坑底票通用 >=4 条门槛
    score = score_conditions(kl, conds, dd, rg)
    method_bits = []
    if conds.get(1):
        method_bits.append('地量死寂%d天' % dd)
    if conds.get(2):
        method_bits.append('红肥绿瘦%.2f' % rg if rg < 999 else '全阳吸筹')
    if conds.get(3):
        method_bits.append('坑底长下影/十字星')
    if conds.get(4):
        method_bits.append('试盘脉冲%d次' % tc)
    if ok6:
        method_bits.append('突破确认%s' % ('满格' if ok6[1] else '温和'))
    if ok5:
        method_bits.append('换手%.2f%%' % avg_turn)
    box_low = box_high = None
    if conds.get(1):
        seg_kl = kl[-dd:]
        box_low = min(r['low'] for r in seg_kl)
        box_high = max(r['high'] for r in seg_kl)
    box_low = box_low or min(r['low'] for r in kl[-20:])
    box_high = box_high or max(r['high'] for r in kl[-20:])
    anchor = round((box_low + box_high) / 2, 2)
    falsify = round(box_low * 0.97, 2)
    if pit:
        # 打压吸筹·坑底期（补丁4专属通道：三要件齐免通用门槛）
        method_type, state = '打压吸筹', '坑底期'
        box_low, box_high = pit['pre_low'], pit['pre_high']
        anchor = round((box_low + box_high) / 2, 2)
        falsify = round(box_low * 0.97, 2)
        next_watch = '放量收复箱体下沿%.2f元=吸筹结束确认' % box_low
        # 补丁4: 死寂期改坑底段计算（砸完后的地量才算死寂），砸盘段不受箱体振幅限制
        conds[1] = False
        pit_kl = kl[pit['dump_i'] + 1:]
        if len(pit_kl) >= 8:
            ok1b, ddb, lo_b, hi_b, _p = cond_dead(pit_kl)
            if ok1b:
                conds[1] = True
                dd = ddb
        hit = [k for k, v in conds.items() if v]
        score = score_conditions(kl, conds, dd, rg)
        method_bits.insert(0, '打压吸筹·坑底')
    elif price > box_high:
        rally = _rally_check(kl, box_high, price)
        if rally:
            method_type, state = '拉高吸筹', '拉高段'
            anchor = rally                                  # 成本区用拉高段均价
            next_watch = '缩量回踩拉高段均价%.2f不破=回踩确认' % rally
            method_bits.insert(0, '拉高吸筹·拉高段')
        else:
            state = '上破'
            next_watch = '放量突破%.2f并站稳=突破确认' % box_high
    kline_brief = [{'d': r['date'][5:], 'pct': round((r['close'] / r['open'] - 1) * 100, 1) if r['open'] else 0,
                    'vol_wan': round(r['volume'] / 10000, 1)} for r in kl[-12:]]
    return {
        'code': code, 'name': name, 'price': round(price, 2),
        'industry': industry, 'float_mv_yi': float_mv_yi,
        'hit_conditions': hit, 'method': '→'.join(method_bits) or '多条件共振',
        'box_low': round(box_low, 2), 'box_high': round(box_high, 2), 'anchor': anchor,
        'falsify_line': falsify, 'dead_days': dd,
        'red_green_ratio': (rg if rg < 999 else None),
        'avg_turn': round(avg_turn, 2) if avg_turn is not None else None,
        'kline_brief': kline_brief, 'score': score,
        'method_type': method_type, 'state': state, 'next_watch': next_watch,
        'pit_depth': (pit['depth'] if at_pit and pit else None),
        'ma5': round(ma5, 2), 'above_ma5': bool(above_ma5),
    }


def run_scanner(end_date=None, limit=None, out=None):
    """主入口。end_date: YYYY-MM-DD；limit: 只数上限（测试用）。返回命中列表。"""
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')
    today = datetime.strptime(end_date, '%Y-%m-%d')
    snap = get_snapshot()
    print(f'[zforce] 快照 {len(snap)} 只，开始过滤')
    pool = []
    for s in snap:
        nm = s['name']
        if 'ST' in nm.upper() or '*' in nm:
            continue
        if s['code'].startswith(('688', '689', '4', '8', '920', '83', '87')):
            continue
        if s.get('float_mv_yi') and s['float_mv_yi'] < 30:
            continue                                   # 流通市值<30亿（新浪nmc预滤）
        pool.append(s)
    print(f'[zforce] 过滤ST/科创/北交/流通<30亿后候选 {len(pool)} 只')
    if limit:
        pool = pool[:limit]
    # —— 多线程预筛：K线 + 五条件 ——
    pre_pool = []
    t0 = time.time()

    def _pre(s):
        kl = get_kline(s['code'], 40)
        if not kl or len(kl) < 30:
            return None
        pre = _quick_conds(kl)
        if not pre:
            return None
        conds, dd, rg, tc, ok6, _pitc = pre
        if sum(1 for v in conds.values() if v) < 3 and not _pitc:
            return None
        return (s, kl, pre)

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(_pre, s): s for s in pool}
        done = 0
        for i, fu in enumerate(as_completed(futs), 1):
            try:
                r = fu.result()
                if r:
                    pre_pool.append(r)
            except Exception as e:
                print(f'[zforce] 预筛异常 {type(e).__name__}: {str(e)[:50]}')
            if i % 1000 == 0:
                print(f'[zforce] 预筛进度 {i}/{len(pool)} 预备 {len(pre_pool)} ({int(time.time()-t0)}s)')
    print(f'[zforce] 预筛完成 {len(pool)} 只 → 预备池 {len(pre_pool)} 只 ({int(time.time()-t0)}s)')

    for _s, _kl, _pre in pre_pool:
        _conds, _dd, _rg, _tc, _ok6, _pitc2 = _pre

    # —— 预备池补齐：qt流通市值 + 条件5 + 评分 ——
    hits = []
    for i, (s, kl, pre) in enumerate(pre_pool, 1):
        try:
            r = _finish_hit(s, kl, pre, s.get('float_mv_yi') or 0, '')
            if r:
                hits.append(r)
                print(f'[zforce] 命中 {s["code"]} {s["name"]} 分{r["score"]} {r["method"]}')
        except Exception as e:
            print(f'[zforce] 补齐异常 {s["code"]} {type(e).__name__}: {str(e)[:50]}')
    # FIX16: 用户铁律——当日涨跌幅>=7% 的票不进补涨池（已涨停/大涨不追；大跌结构坏）
    _before = len(hits)
    hits = [h for h in hits if abs(float((h.get('kline_brief') or [{}])[-1].get('pct') or 0)) < 7.0]
    if len(hits) != _before:
        print(f'[zforce] FIX16涨幅过滤: 剔除 {_before - len(hits)} 只 (当日|涨跌|>=7%)')
    # FIX21: 用户铁律——现价 >= 5日线（价格大于五日线或等于五日线才进池）
    _before = len(hits)
    _keng = sum(1 for h in hits if not h.get('above_ma5') and h.get('state') == '坑底期')
    hits = [h for h in hits if h.get('above_ma5', False)]
    if len(hits) != _before:
        print(f'[zforce] FIX21五日线过滤: 剔除 {_before - len(hits)} 只 (现价<5日线，其中坑底期{_keng}只)')
    hits.sort(key=lambda x: -x['score'])
    print(f'[zforce] 完成：扫描 {len(pool)} 只，命中 {len(hits)} 只 ({int(time.time()-t0)}s)')
    if out:
        with open(out, 'w', encoding='utf-8') as f:
            json.dump({'scan_date': end_date, 'hits': hits}, f, ensure_ascii=False, indent=2)
        print(f'[zforce] 已保存 {out}')
    return hits


def main():
    end_date, limit, out = None, None, None
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] == '--date' and i + 1 < len(argv):
            end_date = argv[i + 1]; i += 2
        elif argv[i] == '--limit' and i + 1 < len(argv):
            limit = int(argv[i + 1]); i += 2
        elif argv[i] == '--out' and i + 1 < len(argv):
            out = argv[i + 1]; i += 2
        else:
            i += 1
    if out is None:
        out = f"tools/data/zhu_force_{(end_date or datetime.now().strftime('%Y-%m-%d')).replace('-', '')}.json"
    hits = run_scanner(end_date=end_date, limit=limit, out=out)
    print(json.dumps(hits, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
