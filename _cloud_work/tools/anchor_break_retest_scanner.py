# -*- coding: utf-8 -*-
"""
anchor_break_retest_scanner.py — 突破回踩·主力成本锚 扫描器（云端版，第1步）
收盘后运行，输出候选票 JSON（纯标准库，不依赖 pandas；供第2步 LLM 评分模块使用）。

候选池策略：涨停池(当日) + 全市场涨幅榜 pct>=2 前 N —— 突破回踩票必然在近期强势股中，
全量 4400 只逐票拉 K 线在 Actions 30 分钟窗口内不可行（且东财限流），此池在逻辑上等价。

用法：
    python3 tools/anchor_break_retest_scanner.py                      # 今天收盘后
    python3 tools/anchor_break_retest_scanner.py --date 2026-10-23   # 指定日期
    python3 tools/anchor_break_retest_scanner.py --limit 50 --out test.json  # 本地测试
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

# ==================== 配置区 ====================
LOOKBACK_DAYS = 60          # 回看天数
IGNITION_MIN_PCT = 4.0      # 点火日涨幅≥4%
IGNITION_VOL_MULT = 1.5     # 点火日量≥前5日均量1.5倍
BREAK_ABOVE_ANCHOR = 1.01   # 突破日收盘≥锚×1.01
BREAK_VOL_MULT = 1.5        # 突破日量≥均量1.5倍
WASH_VOL_RATIO = 0.7        # 洗盘日量 < 突破日0.7倍
RETEST_TOLERANCE = 0.02     # 回踩锚±2%
MAX_RETEST_COUNT = 2
MAX_DAYS_AFTER_BREAK = 10   # 突破后超过10天动能散
GAINER_LIMIT = 400          # 涨幅榜候选上限
STD_SLEEP = 0.35            # K线请求间隔（秒，防东财/腾讯限流）

_UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}


def _http_get(url, timeout=15):
    req = urllib.request.Request(url, headers=_UA)
    return urllib.request.urlopen(req, timeout=timeout).read().decode('utf-8', 'ignore')


def _sec_clean(sec):
    s = re.sub(r'[（(].*?[)）]', '', str(sec or '')).strip()
    return re.sub(r'[\u4e00-\u9fff]+(?:板块|概念|行业|产业链)$', '', s).strip() or (sec or '')


# ==================== 数据获取接口（东财，云端可用） ====================
def get_snapshot():
    """全市场快照：code/name/industry/pct。失败返回 []（https→http 降级+重试）。"""
    out = []
    for scheme in ('https', 'http'):
        url = (scheme + '://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=5000&po=1&np=1&fltt=2&invt=2'
               '&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048'
               '&fields=f2,f3,f12,f14,f127')
        for _try in (1, 2, 3):
            try:
                req = urllib.request.Request(url, headers={**_UA, 'Referer': 'https://quote.eastmoney.com/'})
                txt = urllib.request.urlopen(req, timeout=15).read().decode('utf-8', 'ignore')
                diff = (json.loads(txt).get('data') or {}).get('diff') or []
                if len(diff) < 500:  # 有效行太少=降级响应，退避重试
                    time.sleep(1.2)
                    continue
                for x in diff:
                    _c = str(x.get('f12', '')).strip()
                    _n = str(x.get('f14', '')).strip()
                    if not _c or not _n:
                        continue
                    out.append({'code': _c, 'name': _n,
                                'industry': str(x.get('f127') or '').strip() or '其他',
                                'pct': float(x.get('f3') or 0)})
                if out:
                    return out
            except Exception as e:
                if _try < 3:
                    time.sleep(1.0)
                    continue
                print('[snapshot] 异常:', e)
    print('[snapshot] 全市场快照失败，返回 0 只')
    return out


def get_zt_pool(day):
    """当日涨停池（东财 getTopicZTPool）。失败返回 []。day: YYYYMMDD。"""
    url = ('https://push2ex.eastmoney.com/getTopicZTPool?ut=7eea3edcaed734bea9cbfc24409ed989'
           f'&dpt=wz.ztzt&Pageindex=0&pagesize=300&sort=fbt:asc&date={day}')
    try:
        txt = _http_get(url)
        pool = (json.loads(txt).get('data') or {}).get('pool') or []
        return [{'code': str(x.get('c') or ''), 'name': str(x.get('n') or ''), 'hybk': x.get('hybk') or ''}
                for x in pool if x.get('c')]
    except Exception as e:
        print('[zt_pool] 异常:', e)
        return []


def get_kline(code, n=90):
    """日线K线：腾讯 ifzq 主源 → 新浪备源（多源降级，本地/云端均通）。
    volume 统一为股。返回 list[{date,open,close,high,low,volume,amount}] 或 None。"""
    sym = ('sh' if code.startswith('6') else 'bj' if code.startswith(('4', '8')) else 'sz') + code
    out = None
    # 主源：腾讯
    try:
        url = f'http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,,,{n},qfq'
        txt = _http_get(url, timeout=12)
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
    # 备源：新浪
    try:
        url = ('http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData'
               f'?symbol={sym}&scale=240&ma=no&datalen={n}')
        txt = _http_get(url, timeout=12)
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


def get_news(code, name):
    """个股新闻标题（东财搜索 API）：前 3 条。失败/无返回 '无'。"""
    try:
        kw = name or code
        param = json.dumps({"uid": "", "keyword": kw, "type": ["cmsArticleWebOld"],
                            "client": "web", "clientType": "web", "clientVersion": "curr"}, ensure_ascii=False)
        url = 'https://search-api-web.eastmoney.com/search/jsonp?cb=cb&param=' + urllib.parse.quote(param)
        req = urllib.request.Request(url, headers={**_UA, 'Referer': 'https://so.eastmoney.com/'})
        h = urllib.request.urlopen(req, timeout=10).read().decode('utf-8', 'ignore')
        m = re.search(r'cb\((.*)\)', h, re.S)
        if m:
            titles = []
            for a in ((json.loads(m.group(1)).get('result') or {}).get('cmsArticleWebOld') or []):
                t = re.sub(r'<[^>]+>', '', str(a.get('title') or '')).strip()
                if t and t not in titles:
                    titles.append(t)
                if len(titles) >= 3:
                    break
            return '；'.join(titles) if titles else '无'
        return '无'
    except Exception:
        return '无'


# ==================== 锚位识别 ====================
def find_anchor(kl, lookback=40):
    """在最近 lookback 根K线内找高质量锚。
    返回 {'price': float, 'type': str, 'date': str} 或 None。
    优先级：前高 > 箱体顶 > 套牢区 > 无名。"""
    recent = kl[-lookback:]
    if len(recent) < 20:
        return None
    # 1. 前高（最近明显高点，至少被测试过一次）
    for i in range(len(recent) - 5, 5, -1):
        win = [recent[j]['high'] for j in range(max(0, i - 5), min(len(recent), i + 6))]
        if recent[i]['high'] == max(win):
            return {'price': round(recent[i]['high'], 2), 'type': '前高',
                    'date': recent[i]['date'][:10]}
    # 2. 箱体顶 / 平台颈线（近20日高点密集、振幅小）
    last20 = recent[-20:]
    hs = sorted(x['high'] for x in last20)
    box_high = hs[int(len(hs) * 0.9)]
    mean_c = sum(x['close'] for x in last20) / len(last20)
    hi = max(x['high'] for x in last20)
    lo = min(x['low'] for x in last20)
    if hi - lo < mean_c * 0.12:
        return {'price': round(box_high, 2), 'type': '箱体顶', 'date': last20[-1]['date'][:10]}
    # 3. 套牢区上沿（简化：按收盘价15桶累计量，最密区上沿）
    bins = {}
    for x in recent:
        b = round(x['close'] / (mean_c / 30)) if mean_c else 0
        bins.setdefault(b, 0)
        bins[b] += x['volume']
    if bins:
        dense_bin = max(bins, key=bins.get)
        up_edge = (dense_bin + 0.5) * (mean_c / 30)
        return {'price': round(up_edge, 2), 'type': '套牢区', 'date': recent[-1]['date'][:10]}
    # 4. 无名（最近大阳收盘价）
    return {'price': round(recent[-1]['close'], 2), 'type': '无名', 'date': recent[-1]['date'][:10]}


# ==================== 六步验收核心 ====================
def analyze_single(code, name, industry, end_date, snapshot_by_ind=None):
    """单票完整六步验收。返回候选 dict 或 None。"""
    start = (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=int(LOOKBACK_DAYS * 1.5))).strftime('%Y-%m-%d')
    kl = get_kline(code, 90)
    if not kl or len(kl) < 30:
        return None
    # 截取 end_date 之前的数据（避免未来数据）
    kl = [x for x in kl if x['date'] <= end_date]
    if len(kl) < 30:
        return None
    n = len(kl)
    # 预计算 ma5_vol / pct_chg
    ma5_vol = []
    pct_chg = [0.0] * n
    for i in range(n):
        lo5 = max(0, i - 4)
        ma5_vol.append(sum(x['volume'] for x in kl[lo5:i + 1]) / (i - lo5 + 1))
        if i > 0 and kl[i - 1]['close']:
            pct_chg[i] = (kl[i]['close'] / kl[i - 1]['close'] - 1) * 100

    # ---------- 第0步：找点火日 ----------
    ignition_idx = None
    anchor = None
    for i in range(10, n - 5):
        row = kl[i]
        if (pct_chg[i] >= IGNITION_MIN_PCT and row['close'] > row['open']
                and row['volume'] >= ma5_vol[i] * IGNITION_VOL_MULT):
            a = find_anchor(kl[:i + 1])
            if a is None:
                continue
            if abs(row['close'] - a['price']) / a['price'] < 0.08:
                ignition_idx = i
                anchor = a
                break
    if ignition_idx is None or anchor is None:
        return None
    ignition = kl[ignition_idx]
    ign_vol_ratio = round(ignition['volume'] / ma5_vol[ignition_idx], 2) if ma5_vol[ignition_idx] else 0

    # ---------- 第1步：突破日 ----------
    break_idx = None
    for j in range(ignition_idx + 1, min(ignition_idx + 8, n)):
        row = kl[j]
        if row['close'] >= anchor['price'] * BREAK_ABOVE_ANCHOR and row['volume'] >= ma5_vol[j] * BREAK_VOL_MULT:
            break_idx = j
            break
    if break_idx is None:
        return None
    break_row = kl[break_idx]
    break_vol_ratio = round(break_row['volume'] / ma5_vol[break_idx], 2) if ma5_vol[break_idx] else 0

    # ---------- 第2步：洗盘判定 ----------
    wash_dates = []
    for k in range(break_idx + 1, min(break_idx + 6, n)):
        row = kl[k]
        if row['close'] < anchor['price']:
            vol_ratio = row['volume'] / break_row['volume'] if break_row['volume'] else 9
            if (row['close'] < row['open'] and vol_ratio < WASH_VOL_RATIO
                    and row['close'] >= ignition['open']):
                wash_dates.append(row['date'][:10])
            else:
                return None  # 出货证伪
    wash_vol_ratio = (round(kl[min(break_idx + 1, n - 1)]['volume'] / break_row['volume'], 2)
                      if wash_dates and break_row['volume'] else None)

    # ---------- 第3步：二次突破 ----------
    second_break_idx = None
    for m in range(break_idx + 1, min(break_idx + 10, n)):
        if kl[m]['close'] >= anchor['price']:
            second_break_idx = m
            break
    if second_break_idx is None:
        return None
    second_break = kl[second_break_idx]
    second_vol_ratio = round(second_break['volume'] / break_row['volume'], 2) if break_row['volume'] else 0

    # ---------- 第4步：回踩检测（可选，当天可能还没回踩） ----------
    retest_date = None
    retest_vol_ratio = None
    retest_count = 0
    for nn in range(second_break_idx + 1, n):
        row = kl[nn]
        if abs(row['close'] - anchor['price']) / anchor['price'] <= RETEST_TOLERANCE:
            retest_count += 1
            if retest_count > MAX_RETEST_COUNT:
                return None  # 踩漏
            prev5 = sum(x['close'] for x in kl[max(0, nn - 5):nn]) / min(5, nn)
            if (row['volume'] < break_row['volume'] * 0.7
                    and row['low'] <= anchor['price'] * 1.02
                    and row['close'] >= prev5):
                retest_date = row['date'][:10]
                retest_vol_ratio = round(row['volume'] / break_row['volume'], 2) if break_row['volume'] else None
                break

    # ---------- 板块共振 ----------
    sector_count = 0
    if industry and snapshot_by_ind is not None:
        sector_count = snapshot_by_ind.get(industry, 0)

    # ---------- 新闻 ----------
    news = get_news(code, name)

    # ---------- 硬过滤最终判断 ----------
    days_since_break = n - 1 - break_idx
    hard_passed = True
    if days_since_break > MAX_DAYS_AFTER_BREAK and retest_date is None:
        hard_passed = False

    kline_desc = (f"锚类型{anchor['type']}；点火日放量{pct_chg[ignition_idx]:.1f}%；"
                  f"突破日量比{break_vol_ratio:.1f}；二次突破量比{second_vol_ratio:.1f}")
    return {
        "code": code, "name": name,
        "anchor_price": anchor['price'], "anchor_type": anchor['type'],
        "ignition_date": ignition['date'][:10], "ignition_open": round(float(ignition['open']), 2),
        "ignition_close": round(float(ignition['close']), 2), "ignition_vol_ratio": ign_vol_ratio,
        "break_date": break_row['date'][:10], "break_close": round(float(break_row['close']), 2),
        "break_vol_ratio": break_vol_ratio,
        "wash_dates": wash_dates, "wash_vol_ratio": wash_vol_ratio,
        "second_break_date": second_break['date'][:10], "second_break_vol_ratio": second_vol_ratio,
        "retest_date": retest_date, "retest_vol_ratio": retest_vol_ratio, "retest_count": retest_count,
        "sector_count": sector_count, "news_summary": news, "kline_desc": kline_desc,
        "hard_filter_passed": hard_passed, "days_since_break": days_since_break,
    }


def build_pool(day_yyyymmdd, snapshot):
    """候选池 = 当日涨停池 ∪ 涨幅榜 pct>=2 前 GAINER_LIMIT。返回 [(code, name, industry)] 去重。
    涨幅榜(东财 push2)在部分网络被风控时返回空 → 池退化为涨停池。"""
    pool = {}
    for z in get_zt_pool(day_yyyymmdd):
        pool[z['code']] = (z['name'], _sec_clean(z.get('hybk') or '') or '其他')
    if snapshot:
        gainers = [s for s in snapshot if s['pct'] >= 2][:GAINER_LIMIT]
        for s in gainers:
            pool.setdefault(s['code'], (s['name'], s['industry']))
    return [(c, nm, ind) for c, (nm, ind) in pool.items()]


def run_scanner(end_date=None, limit=None, out=None):
    """主入口。end_date: YYYY-MM-DD；limit: 只数上限（测试用）。返回候选列表。"""
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')
    day_yyyymmdd = end_date.replace('-', '')
    print(f'[scanner] end_date={end_date} 拉全市场快照...')
    snapshot = get_snapshot()
    print(f'[scanner] 快照 {len(snapshot)} 只')
    # 板块共振索引：industry -> 当日涨>=2% 家数；快照失败时用涨停池行业计数兜底（保守下界）
    snap_by_ind = {}
    for s in snapshot:
        snap_by_ind[s['industry']] = snap_by_ind.get(s['industry'], 0) + (1 if s['pct'] >= 2 else 0)
    if not snap_by_ind:
        for z in get_zt_pool(day_yyyymmdd):
            _hy = _sec_clean(z.get('hybk') or '') or '其他'
            snap_by_ind[_hy] = snap_by_ind.get(_hy, 0) + 1
    pool = build_pool(day_yyyymmdd, snapshot)
    if limit:
        pool = pool[:limit]
    print(f'[scanner] 候选池 {len(pool)} 只（涨停池+涨幅榜前{GAINER_LIMIT}）')
    candidates = []
    for i, (code, name, industry) in enumerate(pool, 1):
        try:
            res = analyze_single(code, name, industry, end_date, snap_by_ind)
            if res and res['hard_filter_passed']:
                candidates.append(res)
                print(f'[scanner] #{i} {code} {name} 命中 锚={res["anchor_type"]}{res["anchor_price"]} '
                      f'点火{res["ignition_date"]} 突破{res["break_date"]} 回踩{res["retest_date"] or "-"}')
        except Exception as e:
            print(f'[scanner] #{i} {code} 异常 {type(e).__name__}: {str(e)[:60]}')
        if i % 50 == 0:
            print(f'[scanner] 进度 {i}/{len(pool)} 当前命中 {len(candidates)}')
        time.sleep(STD_SLEEP)
    candidates.sort(key=lambda x: x['ignition_vol_ratio'], reverse=True)
    print(f'[scanner] 完成：扫描 {len(pool)} 只，命中 {len(candidates)} 只')
    if out:
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(candidates, f, ensure_ascii=False, indent=2)
        print(f'[scanner] 已保存 {out}')
    return candidates


def main():
    end_date = None
    limit = None
    out = None
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
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')
    if out is None:
        out = f"tools/data/anchor_candidates_{end_date.replace('-', '')}.json"
    results = run_scanner(end_date=end_date, limit=limit, out=out)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
