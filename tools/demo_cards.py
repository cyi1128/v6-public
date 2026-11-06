# -*- coding: utf-8 -*-
"""样卡演示驱动：**不另写一套拼装逻辑**，直接调用真实 build_auction() / build_eod()。

与真实卡唯一的差别是数据时点：
  · 竞价卡：把"全市场收盘涨幅榜"还原成"竞价涨幅"——用 11-06 开盘价 / 前收 计算，
    因为收盘价与竞价价语义不同（这正是上一版样卡失真之处）；时间冻结到 11-06 09:26，
    让情绪行、LLM 预算、打分截止都按竞价窗口走。
  · eod 卡：完全走真实 build_eod()，不做任何数据替换（当前时点=11-06 收盘后）。
  · 卡头统一加「📋 样卡演示（2026-11-06 真实数据）· 非实时建议」横幅。
已知偏差（卡面同时声明）：竞价量历史不存档，量能项取当日全日量（偏宽）。

用法：
  python -u tools/demo_cards.py                 # 本地渲染两个 HTML
  python -u tools/demo_cards.py --push          # 渲染 + 经 PushPlus 正常通道推送
"""
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, ROOT)
import cloud_daily_review as c   # noqa: E402

DEMO_DAY = '20261106'
OUT = os.path.join(ROOT, 'demo')
# 11-05 收盘冻结值（前夜口径，实测：腾讯快照 usSOXX/usNDX/usAAPL/usNVDA/usTSLA + hf_CL/hf_GC）
OV_1105 = {'usSOXX': -12.15, 'usNDX': -6.36, 'hf_CL': 0.62, 'hf_GC': -1.60,
           'usAAPL': -1.53, 'usNVDA': -9.26, 'usTSLA': -10.77}
BANNER = ('<div style="background:#2a2438;border:1px solid #a78bfa;border-radius:10px;'
          'padding:9px 12px;margin-bottom:10px;font-size:13px;color:#e5dbff;line-height:1.6;">'
          '📋 样卡演示（2026-11-06 真实数据）· 非实时建议<br>'
          '<span style="font-size:12px;color:#c0b3e6;">本卡由真实构建函数渲染（竞价卡=build_auction，'
          'eod 卡=build_eod），仅数据时点回放：竞价涨幅=11-06 开盘价还原（前收→开盘）；'
          '竞价量≈09:30 首根累计量（含集合竞价成交）；隔夜外盘=11-05 收盘冻结值。'
          '情绪周期行空缺：11-05 收盘状态文件未留存，真实 09:25 卡会展示前一日定档。</span></div>')


CLIST = ('https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=120&po=1&np=1&fltt=2&invt=2'
         '&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048'
         '&fields=f2,f3,f5,f6,f8,f12,f14,f15,f16,f17,f18,f10')


def _fetch_clist():
    """自己抓东财涨幅榜（不依赖模块内备用源，避免云端备用源被拦时整卡空转）。"""
    import json
    import urllib.request
    try:
        req = urllib.request.Request(CLIST, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Referer': 'https://quote.eastmoney.com/'})
        d = json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8'))
        lst = ((d.get('data') or {}).get('diff') or [])
    except Exception as e:
        print('[demo] 涨幅榜取数失败 %s' % str(e)[:80])
        return []
    rows = []
    for x in lst:
        code = str(x.get('f12') or '')
        name = str(x.get('f14') or '')
        if not code or not name:
            continue
        rows.append({'code': code, 'name': name,
                     'price': float(x.get('f2') or 0) if str(x.get('f2')) not in ('-', '') else 0.0,
                     'pct': 0.0, 'vol': int(float(x.get('f5') or 0) / 100.0),
                     'amount': float(x.get('f6') or 0),
                     'turn': float(x.get('f8') or 0) if str(x.get('f8')) not in ('-', '') else 0.0,
                     'lb': 0.0,
                     'high': float(x.get('f15') or 0), 'low': float(x.get('f16') or 0),
                     'prev': float(x.get('f18') or 0), 'list_date': '',
                     'industry': c._IND_CACHE.get(code, '其他')})
    return rows


def _pool_rows():
    """兜底全集：当日涨停池 + 炸板池（带真实行业 hybk，云端被拦涨幅榜时仍能出卡）。"""
    rows = []
    try:
        import sentiment_cycle as sc
        for fn in ('fetch_pool', 'fetch_zb'):
            for x in (getattr(sc, fn)(DEMO_DAY) or []):
                code = str(x.get('c') or '')
                name = str(x.get('n') or '')
                if not code or not name:
                    continue
                rows.append({'code': code, 'name': name, 'price': 0.0, 'pct': 0.0,
                             'vol': 0, 'amount': float(x.get('amount') or 0), 'turn': 0.0,
                             'lb': 0.0, 'high': 0.0, 'low': 0.0, 'prev': 0.0,
                             'list_date': '', 'industry': c._IND_CACHE.get(code, x.get('hybk') or '其他')})
    except Exception as e:
        print('[demo] 涨停/炸板池兜底失败 %s' % str(e)[:80])
    return rows


def _auction_rows():
    """11-06 全市场盘面 → 还原成竞价口径的行（pct=开盘/前收-1，price=开盘价，vol≈09:30首根累计量）。"""
    rows = c._clist_gainers_alt() or []
    if len(rows) < 5:
        rows = _fetch_clist()
        print('[demo] 备用源不足，改用东财涨幅榜 %d 行' % len(rows))
    if len(rows) < 5:
        rows = _pool_rows()
        print('[demo] 涨幅榜不可用，改用涨停/炸板池兜底 %d 行' % len(rows))
    if not rows:
        print('[demo] 当日盘面未取到，无法还原竞价口径')
        return []
    out = []
    mvol = _minute_auction_vol([str(r.get('code') or '') for r in rows])
    for r in rows:
        code = str(r.get('code') or '')
        sym = ('sh' if code.startswith('6') else 'sz') + code
        q = c._qt(sym)
        if not q or not q.get('prev') or not q.get('open'):
            continue
        r = dict(r)
        r['pct'] = round((q['open'] / q['prev'] - 1) * 100, 2)
        r['price'] = q['open']          # 竞价价=开盘价
        r['prev'] = q['prev']
        r['lb'] = float(q.get('lb') or 0)
        if mvol.get(code):
            r['vol'] = mvol[code]      # 竞价量≈09:30 首根累计成交量（手）
        out.append(r)
    print('[demo] 盘面 %d 行 → 还原竞价口径 %d 行（竞价量覆盖 %d 行）'
          % (len(rows), len(out), sum(1 for x in out if mvol.get(x['code']))))
    return out


def _minute_auction_vol(codes):
    """腾讯分时 09:30 首根累计量 ≈ 集合竞价成交量（手）。并发 8、单只失败不影响整体。"""
    import json
    import urllib.request
    from concurrent.futures import ThreadPoolExecutor

    def one(code):
        if not code:
            return code, 0
        sym = ('sh' if code.startswith('6') else 'sz') + code
        for host in ('https://ifzq.gtimg.cn', 'https://web.ifzq.gtimg.cn'):
            url = host + '/appstock/app/minute/query?code=' + sym
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0',
                                                           'Referer': 'https://gu.qq.com/'})
                d = json.loads(urllib.request.urlopen(req, timeout=8).read().decode('utf-8'))
                arr = (((d.get('data') or {}).get(sym) or {}).get('data') or {}).get('data') or []
                if not arr:
                    continue
                f = str(arr[0]).split()
                return code, int(float(f[2])) if len(f) >= 3 else 0
            except Exception:
                continue
        return code, 0

    res = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for code, v in ex.map(one, codes):
            if v:
                res[code] = v
    return res


class _Resp(object):
    """极小响应壳：只需 read()/context-manager，供缓存回放时代替真实 urlopen。"""

    def __init__(self, body):
        self._b = body

    def read(self, *a, **k):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _net_cache(record=None, replay=None):
    """数据时点冻结：把 11-06 的全部行情取数录成缓存（record）或从缓存回放（replay）。

    云端（GitHub runner）访问国内行情接口不稳定，导致真实构建在取数阶段就中断；
    缓存只存"当天真实返回的字节"，不改变任何组装逻辑——卡仍是 build_auction/build_eod 出的。
    LLM（modelscope）不进缓存，云端用真实 secret 跑真暗线。
    """
    import base64
    import json
    import urllib.request
    orig = urllib.request.urlopen
    if replay is not None:
        data = replay

        def fake(req, *a, **k):
            url = getattr(req, 'full_url', None) or str(req)
            if url in data:
                return _Resp(base64.b64decode(data[url]))
            print('[cache] miss %s' % url[:90])
            raise OSError('cache miss %s' % url[:60])
        urllib.request.urlopen = fake
        return None

    def rec(req, *a, **k):
        url = getattr(req, 'full_url', None) or str(req)
        resp = orig(req, *a, **k)
        body = resp.read()
        if 'modelscope' not in url:
            record[url] = base64.b64encode(body).decode('ascii')
        return _Resp(body)
    urllib.request.urlopen = rec
    return record


def _load_cache():
    import gzip
    import json
    p = os.path.join(OUT, 'replay_20261106.json.gz')
    if not os.path.exists(p):
        return None
    with gzip.open(p, 'rb') as f:
        d = json.loads(f.read().decode('utf-8'))
    print('[demo] 回放缓存 %d 条：%s' % (len(d), p))
    return d


def _save_cache(d):
    import gzip
    import json
    p = os.path.join(OUT, 'replay_20261106.json.gz')
    with gzip.open(p, 'wb') as f:
        f.write(json.dumps(d).encode('utf-8'))
    print('[demo] 缓存已录 %d 条：%s (%dB)' % (len(d), p, os.path.getsize(p)))
    return p


def _noop(*a, **k):
    return None


def _seal_writes():
    """演示必须零落盘：账本/竞价池/回写全禁，避免污染生产数据（上一版就地跑曾误写 4 条 auction）。"""
    c._git_commit_push = _noop
    c._factor_signal_write = _noop
    c._auction_pool_record = _noop
    for _n in ('_zt_hist_save', '_sent_state_save', '_ind_cache_save'):
        if hasattr(c, _n):
            setattr(c, _n, _noop)


def _ov_line_frozen():
    """11-06 09:26 能看到的"前夜"= 11-05 美股/商品收盘。实时接口此刻已开盘，必须冻结。"""
    import overnight_map as om
    cfg = om.load_cfg()
    rng = cfg.get('score_range') or [-40, 40]
    parts = []
    for rule in cfg.get('rules') or []:
        syms = [s for s in (rule.get('symbols') or []) if s in OV_1105]
        if not syms:
            continue
        pct = sum(OV_1105[s] for s in syms) / float(len(syms))
        parts.append('%s %+.2f%% → %s %+.0f' % (rule.get('label'), pct, rule['sector'],
                                                om._score(pct, float(rule.get('factor') or 0), rng)))
    return ('🌙 隔夜外盘（前夜=2026-11-05 收盘）：' + '｜'.join(parts)
            + '（参考分，仅作开盘情绪偏移，不构成投资建议）')


def build_auction_card():
    rows = _auction_rows()
    if not rows:
        raise SystemExit('[demo] 无行，终止')
    c._bj_now = lambda: datetime(2026, 11, 6, 9, 26, 0)
    c._clist_gainers = lambda: rows
    c._overnight_line_for_auction = _ov_line_frozen
    html = c.build_auction('竞价观察·样卡演示')
    return html


def build_eod_card():
    c._bj_now = lambda: datetime(2026, 11, 6, 15, 5, 0)
    return c.build_eod()


def _banner(html):
    mark = '<div style="background:#161b26'
    if mark in html:
        return html.replace(mark, BANNER + mark, 1)
    return BANNER + html


def _key_facts(html):
    """结构自检：真实路径才有的段落必须都在。"""
    facts = {
        'Top3速判段': 'Top3 速判（小白版·含暗线）' in html,
        '速判阈值行': '≥75分可轻仓试 / 60~74观察' in html,
        '共振阈值行': '共振分≥60 优先 / 40-59 观察' in html,
        'TOP10标题': 'TOP10（量价×0.60+题材×0.20+共振×0.20' in html,
        '每票共振明细': '共振 ' in html and '_reson' not in html,
        '行业题材风向': '行业/题材风向' in html,
        '情绪周期行空缺已说明': '情绪周期行空缺' in html,
        '隔夜外盘行': '隔夜外盘' in html,
        '样卡横幅': '样卡演示（2026-11-06 真实数据）' in html,
        '无问号': ('?' not in html and '？' not in html),
        '免责声明': '仅供参考' in html,
    }
    return facts


def main():
    os.makedirs(OUT, exist_ok=True)
    _seal_writes()
    rec_bag = {}
    if '--record-cache' in sys.argv:
        _net_cache(record=rec_bag)
        print('[demo] 录缓存模式（不推送）')
    else:
        cache = _load_cache()
        if cache:
            _net_cache(replay=cache)
        else:
            print('[demo] 无缓存，走实时取数')
    a = _banner(build_auction_card())
    e = _banner(build_eod_card())
    if rec_bag:
        _save_cache(rec_bag)
    pa = os.path.join(OUT, 'auction_card_20261106.html')
    pe = os.path.join(OUT, 'eod_card_20261106.html')
    for p, h in ((pa, a), (pe, e)):
        with open(p, 'w', encoding='utf-8') as f:
            f.write(h)
    print('[demo] 写出 %s (%dB) / %s (%dB)' % (pa, len(a), pe, len(e)))
    ok = True
    for name, v in _key_facts(a).items():
        print(('PASS ' if v else 'FAIL ') + '竞价卡·' + name)
        ok = ok and v
    print(('PASS ' if '主线体检' in e or '梯队' in e else 'FAIL ') + 'eod卡·主线体检段')
    if '--push' in sys.argv:
        # 用户已授权：这两张历史样卡经 PushPlus 正常通道推送（真实卡同一通道）
        for html, title in ((a, '📋 样卡演示·竞价观察（11-06 真实数据）·非实时建议'),
                            (e, '📋 样卡演示·收盘复盘（11-06 真实数据）·非实时建议')):
            r = c.push(html, title)
            print('[push] %s -> %s' % (title, r))
    print('[demo] RESULT ' + ('PASS' if ok else 'FAIL'))
    return 0 if ok else 7


if __name__ == '__main__':
    try:
        print('[demo] key=%s token=%s python=%s'
              % (bool(c.MODELSCOPE_KEY), bool(c.PUSHPLUS_TOKEN), sys.version.split()[0]))
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(3)
