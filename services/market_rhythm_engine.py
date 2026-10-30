# -*- coding: utf-8 -*-
"""
市场节奏引擎（板块轮动 / 持续判断 / 题材记忆 / 题材内强势股）

定位
----
把「今天谁涨停多」升级成「市场在干嘛」：
    · 板块层面 —— 这个炒作是第几天、在升温还是退潮、是轮动还是延续
    · 个股层面 —— 这个题材里谁先动、谁是龙头、梯队怎么排
    · 时间层面 —— 记住哪天涨了哪个题材（题材记忆）

数据源
------
  仅 data/limit_up_reason.db 的 limit_up_reasons 表。
  不拉实时行情、不依赖外部接口 —— 所以它不会卡、不会闪退，
  盘前盘中盘后都能稳定出数（数据由 services/limit_up_collector.py 每日写入）。

关键概念
--------
  run（连续天数）：从最新交易日往回数，该题材连续「家数 >= 2」的天数
  状态：
    🆕 首日启动  今日 >=2 家，且前 3 个交易日都 <2 家（资金刚切进来）
    🔥 发酵中    连续 2 天
    ⚡ 持续      连续 >=3 天，且今日 >= 昨日
    🚀 高潮      今日 >=8 家，且今日 >= 昨日
    📉 退潮      连续 >=2 天，但今日 < 昨日
    💀 熄火      昨日 >=2 家，今日 <2 家
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

DB = os.path.join(_ROOT, 'data', 'limit_up_reason.db')

# ---- 参数 ----
MIN_STOCK = 2          # 一个题材当日 >=2 家涨停才算「成板块」
SPLIT_RE = re.compile(r'[+＋·、/]')
KW_MIN, KW_MAX = 2, 12
MEMORY_DAYS = 10       # 题材记忆回看的交易日数
CACHE_TTL = 60.0       # 结果缓存秒数（盘后固定，盘中也不会频繁重算）

# 属性词：不是炒作题材，是财务/股权属性。不删，只降权排到最后。
ATTRIBUTE_WORDS = {
    '业绩增长', '半年报增长', '三季报增长', '年报增长', '业绩预增', '扭亏为盈',
    '营收增长', '净利增长', '国企改革', '国资', '央企', '地方国资', '股份划转',
    '股权转让', '重大重组', '资产重组', '并购重组', '退市风险', '摘帽', 'ST摘帽',
    '高送转', '分红', '新产品', '新品研发', '专利', '中标', '订单', '员工持股',
    '回购', '增持', '牛散持股', '机构调研', '解禁', '次新股', '超跌反弹',
    '低价股', '小盘股', '高股息', '破净', '重组预期',
}

# 子串级属性词：只要题材名里含这些片段，就不是炒作题材。
# 用来兜住 ATTRIBUTE_WORDS 覆盖不到的变体（如「半年增长」「上海国资」「中报预增」）。
ATTRIBUTE_KW = (
    '国资', '央企', '国企', '股份划转',
    '业绩', '增长', '预增', '预盈', '扭亏', '净利', '营收',
    '年报', '半年报', '半年', '中报', '季报', '报表',
    '重组', '并购', '股权转让', '股权激励', '摘帽', '退市风险',
    '高送转', '分红', '回购', '增持', '解禁', '员工持股',
    '次新', '超跌', '低价股', '小盘股', '高股息', '破净',
    '中标', '订单', '专利', '机构调研', '牛散',
)

# 停用词：拆出来但没有炒作含义的描述性短语，直接不当题材用。
STOPWORDS = {
    '全产业链', '产业链', '供应链', '产品升级', '产业升级', '全国化扩张',
    '全球化布局', '产能扩张', '项目投产', '战略合作', '渠道扩张', '品牌升级',
    '技术领先', '行业龙头', '细分龙头', '区域龙头', '市场份额', '轻资产运营',
    '协同发展', '业务转型', '多元化', '一体化', '高端装备', '智能制造',
    '国产替代', '自主可控', '科技创新', '专精特新', '隐形冠军', '平台化',
    '数字化转型', '降本增效', '提质增效', '完成', '布局',
}

# 状态显示
ST_NEW = '🆕首日启动'
ST_REVIVE = '♻️复活'
ST_FERMENT = '🔥发酵中'
ST_KEEP = '⚡持续'
ST_CLIMAX = '🚀高潮'
ST_FADE = '📉退潮'
ST_DIE = '💀熄火'
ST_SCATTER = '·零星'

_STATE_RANK = {ST_FERMENT: 0, ST_KEEP: 0, ST_NEW: 1, ST_REVIVE: 1, ST_CLIMAX: 1,
               ST_FADE: 3, ST_SCATTER: 4, ST_DIE: 5}


def is_main_board(code):
    """统计主板 + 创业板（沪 600/601/603/605 + 深 000/001/002/003 + 创 300/301）

    2026-10-10：用户可买创业板，放行 300/301。科创板(688)/北交所(8xx/4xx/920)
    仍剔除 —— 30cm 混进来失真更严重。
    注意：创业板是 20cm，放进来后本模块「均涨幅」列会比纯主板时偏高
    （涨停股口径下纯主板约 10%，混合后约 15%），看该列时按此理解。
    """
    return str(code or '')[:3] in ('600', '601', '603', '605',
                                   '000', '001', '002', '003',
                                   '300', '301')


# 主线归并表：顺序 = 从具体到泛指，命中即止。
# 只用于「主线」辅助列和轮动摘要 —— 主表仍按具体题材列，
# 目的是让 AI漫剧 / AI短剧 / 微短剧 / AI视频 这种同一条线
# 在摘要里收成一条，不会看着像 4 个方向。
MAINLINE = [
    ('AI传媒', '漫剧 短剧 影视 院线 传媒 视频 文化 出版 娱乐 内容 IP'),
    ('AI算力', '算力 数据中心 IDC 液冷 服务器 光模块 CPO 交换机 云计算'),
    ('机器人', '机器人 具身智能 减速器 灵巧手 丝杠 谐波 伺服'),
    ('半导体', '芯片 半导体 存储 PCB 封测 光刻 晶圆 覆铜板 载板 MLCC'),
    ('新能源车', '固态电池 磷酸铁锂 锂电池 新能源车 汽车零部 充电桩 '
                 '智能驾驶 一体化压铸 电池 整车 汽配'),
    ('光伏储能', '光伏 储能 风电 硅料 硅片 组件 逆变器 电网 特高压 电力'),
    ('医药', '创新药 抗生素 CRO 疫苗 医疗 生物 中药 减肥药 辅助生殖 制药'),
    ('军工', '军工 航空 航天 导弹 无人机 船舶 卫星 低空经济'),
    ('网络安全', '网络安全 信息安全 数据安全 密码安全 信创 操作系统 数据库'),
    ('国企改革', '国资 国企 央企 重组 划转 混改 并购'),
    ('农业', '种业 农业 养殖 化肥 粮食 转基因 玉米 猪肉 饲料'),
    ('消费', '零售 商业 白酒 食品 饮料 乳业 餐饮 旅游 酒店 纺织 服装 '
             '家居 家电 消费 免税 新零售'),
    ('金融', '券商 银行 保险 金融 黄金 多元金融 证券'),
    ('地产基建', '房地产 基建 建筑 装修 水泥 钢铁 建材 物业 工程'),
    ('AI应用', 'AI 人工智能 大模型 智能体 AIGC 数据要素 数字经济'),
]


def mainline_of(theme):
    """把细分题材归到一条主线；归不上返回 ''"""
    t = str(theme or '')
    for name, kws in MAINLINE:
        for kw in kws.split():
            if kw and kw in t:
                return name
    return ''



_cache = {'ts': 0.0, 'data': None}
_attr_cache = {'ts': 0.0, 'words': None}


# ----------------------------------------------------------------------
# 基础工具
# ----------------------------------------------------------------------
def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def _recent_dates(n):
    c = _conn()
    rows = c.execute('SELECT DISTINCT date FROM limit_up_reasons '
                     'ORDER BY date DESC LIMIT ?', (n,)).fetchall()
    c.close()
    return sorted(r['date'] for r in rows)


def split_reason(reason):
    """'数据中心+AI营销+体育营销' -> ['数据中心','AI营销','体育营销']

    会丢掉停用词（全产业链 / 高端装备 这类没有炒作含义的描述）。
    """
    out, seen = [], set()
    for p in SPLIT_RE.split(reason or ''):
        p = p.strip().strip('* ')
        for ch in ('“', '”', '‘', '’', '「', '」'):
            p = p.replace(ch, '')
        p = p.strip()
        if not (KW_MIN <= len(p) <= KW_MAX) or p in seen:
            continue
        if p in STOPWORDS:
            continue
        seen.add(p)
        out.append(p)
    return out


def _load_day(date):
    """一天的全部涨停记录"""
    c = _conn()
    rows = c.execute(
        'SELECT code,name,reason,industry,time,lbc,pct_chg FROM limit_up_reasons '
        'WHERE date=?', (date,)).fetchall()
    c.close()
    return [dict(r) for r in rows]


def _is_attribute(word):
    """属性词（财务/股权/交易属性）不是炒作题材。

    V17：命中即从板块表里整条剔除，不再只是「降权沉底」——
    用户口径：国资 / 半年增长这类不该占题材位。
    """
    w = str(word or '')
    if w in ATTRIBUTE_WORDS:
        return True
    for a in ATTRIBUTE_WORDS:
        if a in w and len(w) <= len(a) + 2:
            return True
    for kw in ATTRIBUTE_KW:
        if kw in w:
            return True
    return False


def _time_key(t):
    """'09:25:00' -> 可比较的整数；缺值排最后"""
    s = (t or '').strip()
    if not s or len(s) < 5:
        return 999999
    try:
        p = s.split(':')
        return int(p[0]) * 3600 + int(p[1]) * 60 + (int(p[2]) if len(p) > 2 else 0)
    except Exception:
        return 999999


# ----------------------------------------------------------------------
# 主计算
# ----------------------------------------------------------------------
def _build():
    dates = _recent_dates(MEMORY_DAYS + 5)
    if not dates:
        return {'ok': False, 'error': 'limit_up_reasons 表里没有任何数据'}

    # 每个交易日的记录 —— 主板 + 创业板（300/301 已放开）
    day_rows = {d: [r for r in _load_day(d) if is_main_board(r['code'])]
                for d in dates}
    day_rows = {d: v for d, v in day_rows.items() if v}
    used = sorted(day_rows.keys())
    if not used:
        return {'ok': False, 'error': '近期交易日无主板/创业板涨停数据'}

    today = used[-1]
    prev = used[-2] if len(used) > 1 else None
    rows_today = day_rows[today]

    # 每个交易日 -> 题材 -> 成员列表
    day_theme = {}
    for d in used:
        m = defaultdict(list)
        for r in day_rows[d]:
            for kw in split_reason(r['reason']):
                m[kw].append(r)
        day_theme[d] = dict(m)

    cnt = {d: {k: len(v) for k, v in day_theme[d].items()} for d in used}

    # ---------- 同簇题材：与该题材「共享股票最多」的其他题材 ----------
    # 数据驱动，不维护映射表。用来把 AI漫剧/微短剧/AI短剧 这种拆碎的
    # 同一主线重新看出来。
    codes_of = {k: set(r['code'] for r in v) for k, v in day_theme[today].items()}

    def cluster_of(theme, top=3):
        base = codes_of.get(theme) or set()
        if not base:
            return []
        scored = []
        for other, oc in codes_of.items():
            if other == theme:
                continue
            inter = len(base & oc)
            if inter >= 1:
                scored.append((inter, other))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [o for _, o in scored[:top]]

    # ---------- 板块节奏表 ----------
    boards = []
    for theme, members in day_theme[today].items():
        n_today = len(members)
        if n_today < MIN_STOCK:
            continue
        # V17：属性词（国资/半年报增长/股权转让…）不当题材，整条不显示
        if _is_attribute(theme):
            continue
        n_prev = cnt.get(prev, {}).get(theme, 0) if prev else 0

        # run：从今天往回，连续「>=2 家」的天数
        run, i = 0, len(used) - 1
        while i >= 0 and cnt[used[i]].get(theme, 0) >= MIN_STOCK:
            run += 1
            i -= 1
        # 前 3 个交易日（不含今天、不含昨天）里的最大家数
        pre3 = [cnt[used[j]].get(theme, 0)
                for j in range(max(0, len(used) - 4), len(used) - 1)]
        pre3_max = max(pre3) if pre3 else 0

        # 状态机
        # 关键修正：必须用「昨日家数」判断是不是断档，
        # 不能用前 3 日 —— 否则中间断过又被接起来的题材会被误标成「持续」。
        if n_prev >= MIN_STOCK:
            if run >= 3:
                state = ST_FADE if n_today < n_prev else ST_KEEP
            elif run == 2:
                state = ST_FADE if n_today < n_prev else ST_FERMENT
            else:
                state = ST_KEEP
            if n_today >= 8 and n_today >= n_prev:
                state = ST_CLIMAX
        else:
            # 昨天没成板块（0 或 1 家）—— 今天是新接上来的
            state = ST_REVIVE if pre3_max >= MIN_STOCK else ST_NEW

        # 均涨幅（主板 + 创业板混合，20cm 会把这一档从约 10% 抬到约 15%）
        pcts = [r['pct_chg'] or 0 for r in members]
        avg_pct = sum(pcts) / len(pcts) if pcts else 0.0

        # 题材内强势股梯队：连板优先，其次首封时间早
        ladder = sorted(members, key=lambda r: (-(r['lbc'] or 1),
                                                _time_key(r['time'])))
        lbc_max = max((r['lbc'] or 1) for r in members)
        first_time = min((r['time'] for r in members if r['time']),
                         key=_time_key, default='')

        trend = [cnt[d].get(theme, 0) for d in used[-MEMORY_DAYS:]]

        boards.append({
            'theme': theme,
            'state': state,
            'count': n_today,
            'prev_count': n_prev,
            'run': run,
            'avg_pct': round(avg_pct, 2),
            'lbc_max': lbc_max,
            'first_time': first_time,
            'is_attribute': _is_attribute(theme),
            'mainline': mainline_of(theme),
            'trend': trend,
            'cluster': cluster_of(theme),
            'lead': ladder[0]['name'] if ladder else '',
            'lead_code': ladder[0]['code'] if ladder else '',
            'lead_lbc': (ladder[0]['lbc'] or 1) if ladder else 0,
            'lead_time': ladder[0]['time'] if ladder else '',
            'ladder': [{'code': r['code'], 'name': r['name'], 'lbc': r['lbc'] or 1,
                        'time': r['time'],
                        'reason': r['reason']} for r in ladder],
            'industry': members[0].get('industry', '') if members else '',
        })

    # 排序：真题材优先（属性词整体沉底）-> 状态 -> 今日家数 -> 均涨幅
    boards.sort(key=lambda b: (1 if b['is_attribute'] else 0,
                               _STATE_RANK.get(b['state'], 9),
                               -b['count'], -b['avg_pct']))

    # ---------- 轮动方向 ----------
    t_all = cnt.get(today, {})
    p_all = cnt.get(prev, {}) if prev else {}

    def _attr_first(d):
        """排序时属性词沉底"""
        return (1 if _is_attribute(d['name']) else 0, -d['count'], d['name'])

    new_in = sorted([{'name': k, 'count': v, 'mainline': mainline_of(k),
                      'cluster': cluster_of(k)}
                     for k, v in t_all.items()
                     if v >= MIN_STOCK and p_all.get(k, 0) < MIN_STOCK
                     and not _is_attribute(k)],
                    key=_attr_first)
    fade = sorted([{'name': k, 'count': v, 'mainline': mainline_of(k),
                    'cluster': cluster_of(k)}
                   for k, v in p_all.items()
                   if v >= MIN_STOCK and t_all.get(k, 0) < MIN_STOCK
                   and not _is_attribute(k)],
                  key=_attr_first)
    dead = sorted([{'name': k, 'count': v, 'mainline': mainline_of(k),
                    'cluster': cluster_of(k)}
                   for k, v in p_all.items()
                   if v >= 2 and t_all.get(k, 0) == 0
                   and not _is_attribute(k)],
                  key=_attr_first)

    def _main_line(items, top=3):
        """把同一条主线的题材收成一条。

        交易员看盘不会把「AI漫剧 / AI短剧 / 微短剧 / AI视频」当四个方向，
        它们是一条线。这里按主线归并后再拼摘要。
        """
        groups, order = defaultdict(list), []
        for it in items:
            key = it.get('mainline') or it['name']
            if key not in groups:
                order.append(key)
            groups[key].append(it)
        lines = []
        for key in order:
            g = groups[key]
            if len(g) > 1:
                lines.append('%s(%d家)' % (
                    '/'.join(x['name'] for x in g[:3]),
                    sum(x['count'] for x in g)))
            else:
                lines.append('%s(%d家)' % (g[0]['name'], g[0]['count']))
            if len(lines) >= top:
                break
        return lines

    rotation = {
        'new_in': new_in[:12],
        'fade': fade[:12],
        'dead': dead[:12],
        'new_lines': _main_line(new_in),
        'dead_lines': _main_line(dead or fade),
        'summary': '',
    }
    if rotation['new_lines'] and rotation['dead_lines']:
        rotation['summary'] = '资金从 %s 切向 %s' % (
            '、'.join(rotation['dead_lines'][:2]),
            '、'.join(rotation['new_lines'][:2]))
    elif rotation['new_lines']:
        rotation['summary'] = '新方向进场：%s' % '、'.join(rotation['new_lines'])
    elif rotation['dead_lines']:
        rotation['summary'] = '资金撤离：%s' % '、'.join(rotation['dead_lines'])
    else:
        rotation['summary'] = '没有明显切换，延续昨日结构'

    # ---------- 题材记忆（日期 × 题材） ----------
    mem_dates = used[-MEMORY_DAYS:]
    # V17：不再截断，能出多少题材就出多少
    top_themes = [b['theme'] for b in boards]
    series = [{'name': th,
               'data': [cnt.get(d, {}).get(th, 0) or None for d in mem_dates]}
              for th in top_themes]

    lu_count = len(rows_today)
    max_lbc = max((r['lbc'] or 1) for r in rows_today) if rows_today else 0

    return {
        'ok': True,
        'date': today,
        'prev_date': prev,
        'lu_count': lu_count,
        'max_lbc': max_lbc,
        'theme_count': len([b for b in boards if not b['is_attribute']]),
        'boards': boards,
        'rotation': rotation,
        'memory': {
            'dates': [d[4:] for d in mem_dates],
            'raw_dates': mem_dates,
            'series': series,
        },
        'updated': datetime.now().strftime('%H:%M:%S'),
        'dates_used': used,
    }


def get_rhythm(force=False):
    """市场节奏总入口（带缓存）"""
    now = time.time()
    if not force and _cache['data'] and now - _cache['ts'] < CACHE_TTL:
        return _cache['data']
    try:
        d = _build()
    except Exception as e:
        import traceback
        traceback.print_exc()
        d = {'ok': False, 'error': '%s: %s' % (type(e).__name__, e)}
    _cache['ts'] = now
    _cache['data'] = d
    return d


def tail(text, n):
    """截断显示用"""
    s = str(text or '')
    return s if len(s) <= n else s[:n - 1] + '…'


if __name__ == '__main__':
    d = get_rhythm(force=True)
    if not d.get('ok'):
        print('失败: %s' % d.get('error'))
        sys.exit(1)
    print('=' * 96)
    print('市场节奏  数据日=%s  前一交易日=%s  今日涨停=%d家  最高连板=%d板  板块=%d个'
          % (d['date'], d['prev_date'], d['lu_count'], d['max_lbc'], d['theme_count']))
    print('=' * 96)
    print('%-4s %-11s %-10s %-9s %6s %5s %6s %6s %-9s %s' % (
        '#', '题材', '主线', '状态', '今/昨', '连续', '均涨', '最高板', '龙头', '梯队'))
    print('-' * 106)
    for i, b in enumerate(d['boards'], 1):
        lad = ' '.join('%s%d板' % (x['name'], x['lbc']) for x in b['ladder'][:4])
        print('%-4d %-11s %-10s %-9s %4d/%-3d %4d日 %5.1f%% %4d板 %-9s %s' % (
            i, tail(b['theme'], 10), tail(b['mainline'] or '—', 9), b['state'],
            b['count'], b['prev_count'],
            b['run'], b['avg_pct'], b['lbc_max'],
            tail(b['lead'], 8), tail(lad, 40)))
    print()
    r = d['rotation']
    print('【轮动方向】%s' % r['summary'])
    print('  新进: %s' % ('、'.join('%s%d家' % (x['name'], x['count'])
                                  for x in r['new_in'][:8]) or '无'))
    print('  退潮: %s' % ('、'.join('%s%d家' % (x['name'], x['count'])
                                  for x in r['fade'][:8]) or '无'))
    print('  熄火: %s' % ('、'.join('%s(%d→0)' % (x['name'], x['count'])
                                  for x in r['dead'][:8]) or '无'))
    print('  主线条: 新进 %s ｜ 撤离 %s' % (
        '、'.join(r['new_lines']) or '无', '、'.join(r['dead_lines']) or '无'))
    print()
    print('【同簇题材】(共享股票的近邻题材，确认是不是同一条线)')
    for b in d['boards'][:10]:
        if b['cluster']:
            print('  %-10s -> %s' % (b['theme'], '、'.join(b['cluster'])))
    print()
    m = d['memory']
    print('【题材记忆】')
    print('%-12s %s' % ('题材', ' '.join('%5s' % x for x in m['dates'])))
    for s in m['series'][:12]:
        print('%-12s %s' % (tail(s['name'], 11),
                            ' '.join('%5s' % (v if v else '·') for v in s['data'])))
