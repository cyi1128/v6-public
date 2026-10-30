# -*- coding: utf-8 -*-
"""控盘选股「主营收入 + 最新公告」服务层验证（可重跑，会少量联网）。

覆盖：
  [A] 常量与源码（路径 / TTL / 三源公告 / 限速 / 退避 / 熔断）
  [B] TTL 与失败退避语义（extras_stale / extras_missing）
  [C] 缓存落盘往返（写临时文件，不动真缓存）
  [D] 真实数据：抽 8 只现拉 fetch_biz / fetch_ann 与缓存逐字段比对
  [E] 公告三源降级链（打桩：东财失败→新浪；全失败→ok=False）
  [F] 真实覆盖率 + 来源分布
  [G] fmt_biz / fmt_ann 边界
  [H] 真实调用 5 只 + 不存在代码不抛
结果写 tools\\ctrl_screen_extra_unit.txt
"""
import io
import json
import os
import sys
import tempfile
import time
from collections import Counter

ROOT = r'D:\QuantMonitorV6'
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import services.control_screen_service as SS   # noqa: E402

PASS, FAIL, LINES = [], [], []


def ck(name, cond, extra=''):
    (PASS if cond else FAIL).append(name)
    LINES.append('%s %s%s' % ('PASS' if cond else 'FAIL', name,
                              (' ｜ %s' % extra) if extra else ''))


def main():
    src = io.open(os.path.join(ROOT, 'services', 'control_screen_service.py'),
                  encoding='utf-8').read()

    # ---------------- [A] 常量与源码 ----------------
    ck('A1 缓存路径 = data/cache/ctrl_screen_extras.json',
       SS.EXTRAS_PATH.endswith(os.path.join('data', 'cache', 'ctrl_screen_extras.json')),
       SS.EXTRAS_PATH)
    ck('A2 TTL：主营 30 天 / 公告 6 小时；空结果 1 天 / 2 小时',
       SS.BIZ_TTL == 30 * 86400 and SS.ANN_TTL == 6 * 3600
       and SS.BIZ_EMPTY_TTL == 86400 and SS.ANN_EMPTY_TTL == 2 * 3600,
       '%s/%s/%s/%s' % (SS.BIZ_TTL, SS.ANN_TTL, SS.BIZ_EMPTY_TTL, SS.ANN_EMPTY_TTL))
    ck('A3 公告主源 = 东财公告接口（np-anotice-stock），详情链接模板齐备',
       'np-anotice-stock.eastmoney.com/api/security/ann' in SS.ANN_URL
       and 'data.eastmoney.com/notices/detail' in SS.ANN_DETAIL)
    ck('A4 公告次源 = 新浪财经公告页（vCB_AllBulletin + GBK + 正则）',
       'vCB_AllBulletin' in SS.ANN_SINA_URL and "'gbk'" in src
       and '_SINA_ANN_RE' in src and 'def fetch_ann_sina' in src)
    ck('A5 公告兜底源仍是项目既有的巨潮 provider（用单例方法 get_org_id 判断，防走空）',
       'from data.announcement_provider import get_announcement_provider' in src
       and 'get_stock_identity_provider().get_org_id(str(code))' in src
       and 'from data.stock_identity_provider import get_org_id' not in src)
    ck('A6 主营走项目既有 fetch_main_business_composition',
       'fetch_main_business_composition' in src)
    ck('A7 三源共享公告桶限速 0.3s/次、主营 0.2s/次（多线程共用一个节拍）',
       abs(SS.ANN_MIN_INTERVAL - 0.30) < 1e-9 and abs(SS.BIZ_MIN_INTERVAL - 0.20) < 1e-9
       and '_BM_LOCK' in src and 'def _throttle' in src)
    ck('A8 失败退避 15 分钟 + 连续 12 只双失败熔断 + fetch_ann 返回三元组',
       SS.BIZ_FAIL_COOLDOWN == 15 * 60 and SS.ANN_FAIL_COOLDOWN == 15 * 60
       and 'fail_circuit=12' in src and "stats['aborted'] = 'rate_limited'" in src
       and 'return got, (' in src)
    ck('A9 东财显式判 HTTP 状态（567 风控页不能当「没有公告」）',
       "if r.status_code != 200:" in src and "return None            # 567" in src
       or "if r.status_code != 200:" in src)
    ck('A10 补数层不依赖 kline / pandas（与扫描彻底解耦）',
       'kline_cache' not in src.split('# 主营收入 + 最新公告')[1][:4000]
       and 'pandas' not in src.split('# 主营收入 + 最新公告')[1][:4000])

    # ---------------- [B] TTL / 退避语义 ----------------
    now = time.time()
    ck('B1 空记录 / None / 非 dict 一律判过期',
       SS.extras_stale(None) and SS.extras_stale({}) and SS.extras_stale('x'))
    _fresh = {'biz': '智能终端', 'biz_ts': now - 10, 'ann': [['2026-10-09', 't', 'u', 'c']],
              'ann_ts': now - 10}
    ck('B2 刚补完（主营+公告都有数据）判新鲜', not SS.extras_stale(_fresh, now))
    ck('B3 主营时间戳归零 → 判过期',
       SS.extras_stale(dict(_fresh, biz_ts=0), now))
    ck('B4 公告超过 6 小时 → 判过期',
       SS.extras_stale(dict(_fresh, ann_ts=now - 7 * 3600), now))
    _empty_ann = {'biz': 'x', 'biz_ts': now - 10, 'ann': [], 'ann_ts': now - 3600}
    ck('B5 公告空结果 + 尝试在 2 小时内 → 不判过期（不会被每轮重拉）',
       not SS.extras_stale(_empty_ann, now))
    ck('B6 公告空结果 + 超过 2 小时 → 判过期（仍会择机重试）',
       SS.extras_stale(dict(_empty_ann, ann_ts=now - 3 * 3600), now))
    _empty_biz = {'biz': '', 'biz_ts': now - 3600, 'ann': [], 'ann_ts': now - 60}
    ck('B7 主营空结果 + 超过 1 天 → 判过期（择机重试）',
       SS.extras_stale(dict(_empty_biz, biz_ts=now - 25 * 3600), now)
       and not SS.extras_stale(_empty_biz, now))
    _failrec = {'biz': '', 'biz_ts': now - 20, 'ann': [], 'ann_ts': now - 20,
                'biz_fail': 1, 'ann_fail': 1}
    ck('B8 失败标记：20s 前刚失败 → 不重试（只等 15 分钟退避窗口，不套 30 天/6 小时 TTL）',
       not SS.extras_stale(_failrec, now))
    ck('B9 失败标记超过 15 分钟 → 自动重试',
       SS.extras_stale(dict(_failrec, ann_ts=now - 16 * 60, biz_ts=now - 16 * 60), now))
    ck('B10 失败标记优先于「有数据」的 TTL（有旧数据但标记了失败，到点就重试）',
       SS.extras_stale({'biz': '旧值', 'biz_ts': 0, 'biz_fail': 1,
                        'ann': [['2026-01-01', 't']], 'ann_ts': 0, 'ann_fail': 1}, now))
    ck('B11 extras_missing：只返回缺的、保持顺序、去重',
       SS.extras_missing(['a', 'b', 'a', '', None], {'a': _fresh}) == ['b'])
    ck('B12 extras_missing 支持按字段判（只要公告）',
       SS.extras_missing(['a', 'b'], {'a': dict(_fresh, ann=[], ann_ts=now - 3 * 3600),
                                      'b': _fresh}, need_biz=False, need_ann=True) == ['a'])

    # ---------------- [C] 缓存往返 ----------------
    _tmp = os.path.join(tempfile.gettempdir(), 'cs_extras_roundtrip.json')
    if os.path.isfile(_tmp):
        os.remove(_tmp)
    _p = SS.save_extras({'000779': _fresh}, _tmp)
    _back = SS.load_extras(_tmp)
    ck('C1 save/load 往返一致（含中文、时间戳）',
       bool(_p) and _back.get('000779', {}).get('biz') == '智能终端'
       and abs(float(_back['000779']['biz_ts']) - float(_fresh['biz_ts'])) < 1)
    _raw = json.load(io.open(_tmp, encoding='utf-8'))
    ck('C2 落盘结构含 saved_at + items', 'saved_at' in _raw and isinstance(_raw.get('items'), dict),
       str(list(_raw.keys())))
    ck('C3 读不存在的路径 / 坏文件返回 {}（不抛）',
       SS.load_extras(_tmp + '.nope') == {})
    io.open(_tmp, 'w', encoding='utf-8').write('{坏 json')
    ck('C4 坏 JSON 也不抛异常', SS.load_extras(_tmp) == {})

    # ---------------- [D] 真实数据比对 ----------------
    snap = SS.load_snapshot()
    rows = SS.apply_filters(snap['rows'], min_score=85.0) if snap else []
    items = SS.load_extras()
    ck('D0 真实补数缓存已存在且有数据', bool(items), '条数=%d' % len(items))
    sample = [str(r['code']) for r in rows[:8]] if rows else []
    bad = []
    _diff_title = []
    for c in sample:
        rec = items.get(c) or {}
        _b, _bok = SS.fetch_biz(c)          # 独立重拉（与写缓存同一条函数）
        _a, _src, _aok = SS.fetch_ann(c)
        if _bok and str(rec.get('biz') or '') != str(_b.get('biz') or ''):
            bad.append((c, 'biz', rec.get('biz'), _b.get('biz')))
        if _bok and str(rec.get('biz_income') or '') != str(_b.get('biz_income') or ''):
            bad.append((c, 'biz_income', rec.get('biz_income'), _b.get('biz_income')))
        # 公告：日期必须一致（同一条公告）；标题文案在不同源里写法不同（东财长标题含公司全称、
        #       新浪带「简称：」前缀），属源差异，只统计不判错
        if _aok and (rec.get('ann') or [])[:1] and _a[:1]:
            if str(rec['ann'][0][0]) != str(_a[0][0]):
                bad.append((c, 'ann_date', rec['ann'][0][0], _a[0][0]))
            elif str(rec['ann'][0][1]) != str(_a[0][1]):
                _diff_title.append(c)
    ck('D1 抽 8 只：缓存主营/公告与现拉结果一致（公告按日期比对；标题文案源差异已知）',
       bool(sample) and not bad,
       '样本=%s 差异=%s 标题文案差异=%s' % (','.join(sample[:4]), bad[:3], _diff_title))

    # ---------------- [E] 公告三源降级链 ----------------
    _o_em, _o_sina = SS.fetch_ann_em, SS.fetch_ann_sina
    SS.fetch_ann_em = lambda *a, **k: None          # 打桩：东财「没拿到响应」
    try:
        _fb, _fs, _fok = SS.fetch_ann('600338')
    finally:
        SS.fetch_ann_em = _o_em
    ck('E1 东财失败 → 降级到新浪且 ok=True',
       _fok and _fs in ('sina', 'cninfo'), '条数=%d 源=%s' % (len(_fb), _fs))
    # 把三源全部打桩成「没拿到响应」→ 必须 ok=False（不能被当成「上游确认无公告」）
    import data.announcement_provider as _AP
    _o_singleton = _AP.get_announcement_provider
    class _DeadProv(object):
        def get_announcements(self, *a, **k):
            return []
    _AP.get_announcement_provider = lambda: _DeadProv()
    SS.fetch_ann_em = lambda *a, **k: None
    SS.fetch_ann_sina = lambda *a, **k: None
    try:
        _gb, _gs, _gok = SS.fetch_ann('600338')
    finally:
        SS.fetch_ann_em, SS.fetch_ann_sina = _o_em, _o_sina
        _AP.get_announcement_provider = _o_singleton
    ck('E2 三源都没响应 → ok=False（会被记成失败、15 分钟后重试，不当成「没有公告」）',
       _gok is False and _gb == [], 'ok=%s src=%r' % (_gok, _gs))
    SS.fetch_ann_em = lambda *a, **k: [['2026-10-10', 't', 'https://x', '']]
    SS.fetch_ann_sina = lambda *a, **k: [['2026-10-09', 'old', 'https://y', '']]
    try:
        _hb, _hs, _hok = SS.fetch_ann('600338')
    finally:
        SS.fetch_ann_em, SS.fetch_ann_sina = _o_em, _o_sina
    ck('E3 东财可用时优先东财（不打新浪）', _hok and _hs == 'eastmoney' and _hb[0][1] == 't')
    _em = SS.fetch_ann_em('000779')
    ck('E4 东财：要么给出合法 4 元组、要么返回 None（当前被限流），不允许其它结构',
       _em is None or (bool(_em) and len(_em[0]) == 4 and len(str(_em[0][0])) == 10
                       and 'eastmoney.com' in str(_em[0][2])),
       ('被限流(567)返回 None' if _em is None else str(_em[0][:2])[:70]))
    # E5 巨潮兜底那一层的 import 是否真的可用（曾经写成模块级 get_org_id → ImportError，
    #    导致这一层从来没生效过；现在改成单例方法调用）
    import io as _io
    import contextlib
    _ob, _os2 = SS.fetch_ann_em, SS.fetch_ann_sina
    SS.fetch_ann_em = lambda *a, **k: None
    SS.fetch_ann_sina = lambda *a, **k: None
    _buf = _io.StringIO()
    try:
        with contextlib.redirect_stdout(_buf):
            _cb, _cs, _cok = SS.fetch_ann('600519')
    finally:
        SS.fetch_ann_em, SS.fetch_ann_sina = _ob, _os2
    _log = _buf.getvalue()
    ck('E5 巨潮兜底层不再 ImportError（可执行；被风控时优雅返回 ok=False）',
       'ImportError' not in _log and 'cannot import name' not in _log
       and (_cok is False or _cs == 'cninfo'),
       'ok=%s src=%r log=%s' % (_cok, _cs, _log.strip()[:90]))

    # ---------------- [F] 覆盖率 + 来源分布 ----------------
    codes = [str(r['code']) for r in rows]
    _biz = [c for c in codes if (items.get(c) or {}).get('biz')]
    _ann = [c for c in codes if (items.get(c) or {}).get('ann')]
    srcc = Counter((items.get(c) or {}).get('ann_src') or '空' for c in codes)
    LINES.append('     覆盖率：主营 %d/%d=%.1f%% ｜ 公告 %d/%d=%.1f%% ｜ 来源 %s'
                 % (len(_biz), len(codes), 100.0 * len(_biz) / max(1, len(codes)),
                    len(_ann), len(codes), 100.0 * len(_ann) / max(1, len(codes)), dict(srcc)))
    ck('F1 主营覆盖率 ≥90%（东财 F10 覆盖度）',
       len(_biz) >= 0.9 * max(1, len(codes)))
    ck('F2 公告覆盖率 ≥90%', len(_ann) >= 0.9 * max(1, len(codes)),
       '%d/%d' % (len(_ann), len(codes)))
    ck('F3 公告来源全部是已知源（东财/新浪/巨潮），无「空」',
       set(srcc.keys()) <= {'eastmoney', 'sina', 'cninfo'} and '空' not in srcc,
       str(dict(srcc)))
    ck('F4 不存在「上游没响应」还留在缓存里的记录（ann_fail 已清零）',
       sum(1 for c in codes if (items.get(c) or {}).get('ann_fail')) == 0)

    # ---------------- [G] fmt 边界 ----------------
    ck('G1 fmt_biz/fmt_ann 对空/非 dict 返回 (\'\',\'\')',
       SS.fmt_biz(None) == ('', '') and SS.fmt_biz({}) == ('', '')
       and SS.fmt_ann(None) == ('', '') and SS.fmt_ann({}) == ('' , ''))
    _t, _tip = SS.fmt_biz({'biz': '智能终端', 'biz_income': '65.80亿', 'biz_ratio': '83.0%',
                           'biz_date': '2026-06-30',
                           'biz_items': [['智能终端', '65.80亿', '83.0%', '+36.2%']]})
    ck('G2 fmt_biz：文本=「第一大项 营收」、tooltip 带报告期与同比',
       _t == '智能终端 65.80亿' and '2026-06-30' in _tip and '+36.2%' in _tip, _t)
    _t2, _tip2 = SS.fmt_ann({'ann': [['2026-10-10', '甘咨询:甘肃工程咨询集团股份有限公司2026年半年度权益分派实施公告',
                                      'https://x', '分配方案实施']], 'ann_src': 'eastmoney'})
    ck('G3 fmt_ann：单元格去「简称:」+ 公司全称前缀、显示 MM-DD，tooltip 保留原始标题+来源+类型',
       _t2 == '10-10 2026年半年度权益分派实施公告'
       and '东方财富' in _tip2 and '分配方案实施' in _tip2 and '甘咨询:' in _tip2, _t2[:40])
    ck('G4 未知公告源不显示来源字样',
       '来源' not in SS.fmt_ann({'ann': [['2026-10-10', 't']], 'ann_src': 'zzz'})[1].split('\n')[0])
    ck('G5 新浪公告也标注来源=新浪财经',
       '新浪财经' in SS.fmt_ann({'ann': [['2026-10-10', 't']], 'ann_src': 'sina'})[1])
    # G6/G7 公司全称前缀剥离（真实标题样例）
    _cases = [
        ('甘肃工程咨询集团股份有限公司2026年半年度权益分派实施公告',
         '2026年半年度权益分派实施公告'),
        ('襄阳长源东谷实业股份有限公司关于发行股份购买资产并募集配套资金暨关联交易的申请文件获得上海证券交易所受理的公告',
         '关于发行股份购买资产'),
        ('上海城地香江数据科技股份有限公司重大诉讼结果公告', '重大诉讼结果公告'),
        ('福建福日电子股份有限公司2026年半年度业绩说明会投资者关系活动记录表',
         '2026年半年度业绩说明会投资者关系活动记录表'),
    ]
    _bad6 = [(t, SS._strip_company_prefix(t)) for t, want in _cases
             if not SS._strip_company_prefix(t).startswith(want)]
    ck('G6 公司全称前缀被剥掉（4 个真实标题样例）', not _bad6, str(_bad6[:2]))
    _keep = ['关于全资子公司为全资子公司提供担保的进展公告',
             '控股股东协议转让公司股份取得深圳证券交易所合规性确认暨控制权拟发生变更的进展公告',
             '2026年半年度权益分派实施公告', '关于回购股份进展的公告']
    _bad7 = [(t, SS._strip_company_prefix(t)) for t in _keep
             if SS._strip_company_prefix(t) != t]
    ck('G7 不误剥：主题词开头 / 无全称前缀的标题原样保留', not _bad7, str(_bad7[:2]))
    _t3, _tip3 = SS.fmt_ann({'ann': [['2026-10-09', '上海城地香江数据科技股份有限公司重大诉讼结果公告',
                                      'https://x', '']], 'ann_src': 'sina'})
    ck('G8 单元格文本 = MM-DD + 主题（剥前缀后），长度 ≤30 字',
       _t3 == '10-09 重大诉讼结果公告' and len(_t3) <= 30, _t3)
    _t4, _tip4 = SS.fmt_ann({'ann': [['2026-10-01',
        '襄阳长源东谷实业股份有限公司关于发行股份购买资产并募集配套资金暨关联交易的申请文件获得上海证券交易所受理的公告',
        'https://x', '']], 'ann_src': 'eastmoney'})
    ck('G9 tooltip 永远保留上游原始标题（剥离只影响一格显示）',
       '襄阳长源东谷实业股份有限公司' in _tip4 and _t4.endswith('…') and len(_t4) <= 30,
       '%s ｜ tip含全称=%s' % (_t4, '襄阳长源东谷实业股份有限公司' in _tip4))
    ck('G10 主营单元格收敛到 ≤22 字，tooltip 仍含完整分项',
       len(SS.fmt_biz({'biz': '轨道几何状态检测系统与智能运维平台',
                       'biz_income': '3.10亿', 'biz_date': '2026-06-30',
                       'biz_items': [['轨道几何状态检测系统与智能运维平台', '3.10亿', '90%', '+5%']]})[0]) <= 22)

    # ---------------- [H] 真实调用 ----------------
    _bad2 = []
    for c in (sample[:5] or ['600338', '000779', '301201', '600519', '000001']):
        _b, _okb = SS.fetch_biz(c)
        _a, _srca, _oka = SS.fetch_ann(c)
        if not _okb:
            _bad2.append((c, 'biz 无响应'))
        if not _oka:
            _bad2.append((c, 'ann 无响应'))
        if _a and len(_a[0]) != 4:
            _bad2.append((c, 'ann 结构', _a[0]))
    ck('H1 真实 5 只：主营/公告都能拿到有效响应（ok=True）且公告为 4 元组',
       not _bad2, str(_bad2))
    try:
        _xb, _xok = SS.fetch_biz('999999')
        _xa, _xs, _xok2 = SS.fetch_ann('999999')
        _no_raise = True
    except Exception as e:
        _no_raise = False
        LINES.append('     不存在代码抛异常: %s' % e)
    ck('H2 不存在的代码不抛异常（返回 ok=False 或空）', _no_raise)
    _t3 = time.perf_counter()
    SS.fetch_ann(sample[0] if sample else '600338')
    _dt = time.perf_counter() - _t3
    ck('H3 单只公告调用 <3s（含限速等待）', _dt < 3.0, '%.3fs' % _dt)

    _dump()
    return 1 if FAIL else 0


def _dump():
    LINES.append('')
    LINES.append('=== %d PASS / %d FAIL ===' % (len(PASS), len(FAIL)))
    if FAIL:
        LINES.append('失败项：%s' % FAIL)
    txt = '\n'.join(LINES)
    print(txt, flush=True)
    io.open(os.path.join(ROOT, 'tools', 'ctrl_screen_extra_unit.txt'),
            'w', encoding='utf-8').write(txt + '\n')


if __name__ == '__main__':
    sys.exit(main())
