# FOLLOW_V6
# FOLLOW_V5
# BRIEF_TOTAL_V1
# FOLLOW_V4
# BRIEF_SIDE_V1
# FOLLOW_V3
# EVENING_PLAIN_V1
# WHY_LABEL_HIDE_V1
# BOARD_WHY_CLEAN_V1
# BOARD_ACTION_PATCH_V1
# REP_FIVE_PATCH_V1
# -*- coding: utf-8 -*-
"""
云端全天复盘推送 v2（多时段 + DeepSeek 大白话研判）
=====================================================
推送时间（北京时间，工作日）：
  08:20  pre     盘前
  09:30  auction 竞价后
  11:40  noon    午间
  15:05  eod     尾盘/收盘
数据：腾讯行情 + 东财涨停/跌停/炸板池。
推送：PushPlus（深色 HTML）。
大模型：DeepSeek（Key 缺失则自动降级为规则文案）。
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
try:
    from resonance_engine import compute_resonance as _reson_compute, resonance_banner as _reson_banner_html, \
        record_today as _reson_record, reconcile_today as _reson_reconcile, load_ledger as _reson_ledger
    _RESON_OK = True
except Exception as _re:
    _RESON_OK = False  # 共振引擎缺失/异常时全部降级，不阻断推送
try:
    import factor_engine as _fe
    _FACTOR_OK = True
except Exception as _fe_err:
    _fe = None
    _FACTOR_OK = False   # 因子引擎缺失时因子行静默不显示，不阻断推送
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

MEM_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'theme_memory.json')
ALERT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'last_alerts.json')
DIRTY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dirty_data_log.json')
THEMES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'last_valid_themes.json')
LIFECYCLE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'theme_lifecycle.json')
PUSHES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'theme_pushes.json')
JUDGMENT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'judgment_log.json')
HEALTH_STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data_health_state.json')
_AMT_HIGH = 5e8   # 板块高潮判定：成交额总和阈值（元），可配置

# ============ 数据质量监控 ============
HEALTH = {'calls': [], 'sources': {}}


def _record(src, ok, sec, note=''):
    HEALTH['calls'].append({'src': src, 'ok': ok, 'sec': round(sec, 2), 'note': note})
    HEALTH['sources'][src] = {'ok': ok, 'sec': round(sec, 2), 'note': note,
                              'ts': datetime.now().strftime('%H:%M:%S')}


def _git_commit_push(path, msg):
    """git add/commit/push，失败重试一次，返回是否成功；全程打印日志。"""
    for attempt in (1, 2):
        try:
            subprocess.run(['git', 'add', path], check=False, timeout=15, capture_output=True)
            r = subprocess.run(['git', '-c', 'user.name=bot', '-c', 'user.email=bot@local',
                                'commit', '-m', msg], check=False, timeout=15, capture_output=True)
            if r.returncode != 0 and 'nothing to commit' not in (r.stdout or b'').decode(errors='ignore') + (r.stderr or b'').decode(errors='ignore'):
                print(f'[git] commit attempt{attempt}: {r.stderr[:100] if r.stderr else ""}')
            # 先 rebase 远端再 push：并发 run 都会各自 commit 状态文件，直接 push 会因远端推进而冲突失败，
            # 导致去重状态（eod_status/slot_done）写不回仓库、下一 run 重复推送（11-03 收盘复盘双推实证）
            subprocess.run(['git', 'pull', '--rebase', '--autostash'], check=False, timeout=30, capture_output=True)
            rp = subprocess.run(['git', 'push'], check=False, timeout=30, capture_output=True)
            if rp.returncode == 0:
                print(f'[git] writeback ok attempt{attempt}')
                return True
            print(f'[git] push fail attempt{attempt}: {(rp.stderr or b"")[:120]}')
        except Exception as e:
            print(f'[git] exception attempt{attempt}: {e}')
        time.sleep(2)
    print('[git] WRITEBACK FAILED after retry; 状态仅本次有效')
    return False


def load_alerts():
    try:
        with open(ALERT_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_alerts(al):
    with open(ALERT_PATH, 'w', encoding='utf-8') as f:
        json.dump(al, f, ensure_ascii=False, indent=1)
    _git_commit_push(ALERT_PATH, 'update alerts')

# ============ 配置 ============
PUSHPLUS_TOKEN = os.environ.get('PUSHPLUS_TOKEN', '')  # 在 GitHub Secrets 配，无默认硬编码
PUSHPLUS_API = 'http://www.pushplus.plus/send'
DEEPSEEK_KEY = os.environ.get('DEEPSEEK_API_KEY', '') or 'ms-only'  # 已停用 DeepSeek 付费网关（用户退款），恒非空仅兼容旧判断；LLM 全走 ModelScope
MODELSCOPE_KEY = os.environ.get('MODELSCOPE_API_KEY', '')  # 魔搭免费通道（GitHub Secrets 配，形如 ms-xxx，勿入库）

FIVE_BRIEF = ('【主力游资五步铁律】第一步·先看筹码后说话：先判断主力现在处于吸筹/洗盘/拉升/出货/对倒哪一阶段，不许上来就喊涨跌；'
              '第二步·问三个主力问题：①主力为什么动它——建仓痕迹、筹码真空、股东户数、盘口托砸；②跟我什么关系——能不能跟主力吃肉、会不会被当炮灰；③主力下一步想干什么——继续吸、准备拉、准备出；'
              '第三步·翻译成人话：用游资黑话（挖坑洗盘/红肥绿瘦/上方真空/脉冲试盘/对倒出货），结论先行+动作可执行；'
              '第四步·套游资纪律：高位连板一律不接飞刀，没有明显建仓痕迹的票只看戏，加仓只加主力还没出货的，破点火开盘价或成本区无条件走；'
              '第五步·自查：说机会必须同时说出主力可能出货的信号，能扛住兄弟反推。')
_DEEP_DIG_RULE = ('【暗线业务深挖铁律·全场强制】凡提到任何一只股票，必须先完整挖完再下结论。必须严格按以下顺序挖透，缺任一项视为未完成深挖，整段作废：'
                  '①本质：一句话大白话说清公司到底靠什么赚钱（禁止「XX龙头」「XX概念」标签糊弄）；'
                  '②暗线业务深挖：具体产品/技术/业务是什么、当前进展到哪个阶段、在产业链哪个环节、有没有卡位或壁垒（技术/客户/牌照/成本/渠道等）、这个业务目前对业绩的真实贡献（占比高/开始贡献/纯故事预期）、有没有跟当前主线或今日最强题材直接相关的业务；挖不出来必须如实写「未见明确暗线业务」，禁止用「相关」「涉及」「布局」「受益于」等词糊弄；'
                  '③真实关联与弹性：跟今日/近期最强题材是【实受益】【沾边】还是【纯蹭】、这波题材能给它带来多少实际增量、弹性大不大，给明确判断，禁止模糊；'
                  '④为什么是它：资金凭什么选它不选别人（主业匹配度、位置、筹码、业绩、催化剂，用真实数据说）；'
                  '⑤破灭点：这个逻辑什么时候会破（催化兑现/业绩证伪/位置透支/主力出货/消息证伪），必须写；'
                  '⑥动作：具体触发条件（价位/量能/板块信号）+动作+失效条件；逻辑不硬就明确写「不碰」，绝不硬推。'
                  '输出前必须先自问：如果今天不推这只票，最硬的理由是什么？如果这个理由成立，就直接写「不碰」。'
                  '最终给用户看的内容必须用大白话、连贯段落写出，像跟兄弟连麦盯盘一样，禁止一问一答，禁止条目清单式罗列。'
                  '禁止任何模板句、规则套话、万能公式。宁可明确说「数据不足/暗线不硬」，也不许说正确的废话。')
_FIVE_BRIEF_OLD = ('【大白话五步铁律】第一步·先干活后说话：先把数据事实说清，不许上来就喊涨跌；'
                   '第二步·问三个问题：①为什么涨/跌——驱动是政策/业绩/资金/纯情绪，给依据；②跟我什么关系——能买吗、踩雷吗；③风险藏在哪——位置/业绩/暗雷（解禁/担保/减持）；'
                   '第三步·翻译成人话：术语必须配翻译，打比方优先（击鼓传花/接飞刀/烧到头的鞭炮/装死/开奖日），结论先行+动作可执行；'
                   '第四步·套纪律：高位连板一律别追，四重共振不够就「看戏不追」，加仓只加确定性（缩量企稳才算信号），放量破位止损位给死；'
                   '第五步·自查：结论和逻辑不许矛盾，说机会必须带风险位，能扛住用户反推。')
MODELSCOPE_URL = 'https://api-inference.modelscope.cn/v1/chat/completions'
# 首模型可被环境变量 MODELSCOPE_MODEL 覆盖；429/404 时依次轮换备选（单模型日额度用完自动换）
# 实测可用链（2026-10-21，GET /v1/models 核实）：Qwen2.5-72B 已下线，Qwen3.5/3.8 为现役
_MODELSCOPE_MODELS = ('Qwen/Qwen3.5-122B-A10B', 'Qwen/Qwen3.8-27B',
                      'Qwen/Qwen3.5-35B-A3B', 'Qwen/Qwen3.8-Flash-Next',
                      'ZhipuAI/GLM-4.7-Flash')  # 智谱Flash，魔搭放量(429=错峰可用)，轮换兜底
DEEPSEEK_URL = 'https://api.deepseek.com/chat/completions'

HOLDINGS = [
    {'code': 'sz002838', 'name': '道恩股份', 'cost': 25.823, 'qty': 8500, 'sector': '塑料'},
    {'code': 'sz000811', 'name': '冰轮环境', 'cost': 37.571, 'qty': 4300, 'sector': '通用设备'},
]
INDICES = [('sh000001', '上证'), ('sz399001', '深成'), ('sz399006', '创业'), ('sh000688', '科创50')]
GLOBAL = [('usDJI', '道指'), ('usIXIC', '纳指'), ('usINX', '标普')]
UA = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://quote.eastmoney.com/'}

RED, GREEN, GOLD, TEAL, GREY = '#c2504a', '#3e9863', '#b1852e', '#2f8fa1', '#6b7280'

# ============ 小白友好版新增配置（可调） ============
AUCTION_TOP_N = 10         # 竞价输出数量（v3：Top10）
TRACK_POOL_N = 6           # 收盘可跟踪池数量（可配置）
FOCUS_N = 6                # 盘前重点个股数（可配置）

# ============ A 股交易日历（休市日判定，2026-10-19 新增） ============
# 数据来源：沪深北交易所官方公告——上证公告〔2025〕45号《关于上海证券交易所2026年部分节假日休市安排的通知》
#   及后续元旦/春节/清明/劳动/端午/中秋/国庆各节日补充公告（深交所、北交所同步）。
#   A 股周六日不交易；法定节假日及调休中落在周一至周五的日子也休市。
#   【重要】2026 全年已覆盖；2027 年休市安排待交易所发布（预计 2026 年末），未覆盖日期一律按"保守休市"处理
#   （只发新闻汇总，不推股票分析），避免节假日误推股票报告。
#   （2026 官方休市安排核对：元旦 1/1-1/3；春节 2/15-2/23；清明 4/4-4/6；劳动 5/1-5/5；
#     端午 6/19-6/21；中秋 9/25-9/27；国庆 10/1-10/7。此处只登记其中落在周一至周五的工作日休市日。）
HOLIDAY_WEEKDAYS_2026 = {
    # 元旦：1/1(四)~1/3(六)休市，1/5(一)开市
    '2026-01-01', '2026-01-02',
    # 春节：2/15(日)~2/23(一)休市，2/24(二)开市
    '2026-02-16', '2026-02-17', '2026-02-18', '2026-02-19', '2026-02-20', '2026-02-23',
    # 清明：4/4(六)~4/6(一)休市，4/7(二)开市
    '2026-04-06',
    # 劳动节：5/1(五)~5/5(二)休市，5/6(三)开市
    '2026-05-01', '2026-05-04', '2026-05-05',
    # 端午：6/19(五)~6/21(日)休市，6/22(一)开市
    '2026-06-19',
    # 中秋：9/25(五)~9/27(日)休市，9/28(一)开市
    '2026-09-25',
    # 国庆：10/1(四)~10/7(三)休市，10/8(四)开市
    '2026-10-01', '2026-10-02', '2026-10-05', '2026-10-06', '2026-10-07',
}
TRADE_CAL_START = '2026-01-01'
TRADE_CAL_END = '2026-12-31'


def _bj_now():
    """北京时间（GitHub Actions runner 系统时区为 UTC，需 +8 小时）。"""
    from datetime import timedelta
    return datetime.utcnow() + timedelta(hours=8)


def is_trading_day(d=None):
    """A 股交易日判定：周一至五 且 不在休市表。日历未覆盖的日期保守按休市处理。

    降级策略（保守）：交易日历缺失/超出覆盖范围 → 返回 False（休市），只发新闻汇总不推股票分析，
    宁缺勿错。返回前打印明确日志。
    """
    d = d or _bj_now().strftime('%Y-%m-%d')
    try:
        dt = datetime.strptime(d, '%Y-%m-%d')
    except Exception:
        print(f'[cal] 日期格式无效: {d} → 按休市处理（保守降级）')
        return False
    if d < TRADE_CAL_START or d > TRADE_CAL_END:
        print(f'[cal] {d} 超出日历覆盖范围({TRADE_CAL_START}~{TRADE_CAL_END})，保守按休市处理（2027 休市安排待交易所发布）')
        return False
    if dt.weekday() >= 5:
        return False
    if d in HOLIDAY_WEEKDAYS_2026:
        print(f'[cal] {d} 在 2026 休市表中（法定节假日/调休休市）')
        return False
    return True

DRY_RUN = '--dry-run' in sys.argv


# ============ 基础工具 ============
def _get(url, encoding='utf-8', timeout=15, _retries=3):
    """带退避重试的请求：东财等源偶发 RemoteDisconnected，重试可稳。"""
    _last = None
    for _i in range(_retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=timeout).read().decode(encoding, errors='ignore')
        except Exception as _e:
            _last = _e
            if _i < _retries - 1:
                time.sleep(0.8 * (_i + 1))
    raise _last


def _getm(url, src, encoding='utf-8', timeout=15):
    """带监控的请求：返回 (text|None, ok)。失败不抛，由调用方决定。"""
    t0 = time.time()
    try:
        txt = _get(url, encoding=encoding, timeout=timeout)
        _record(src, True, time.time() - t0, f'{len(txt)}B')
        return txt, True
    except Exception as e:
        _record(src, False, time.time() - t0, repr(e)[:80])
        return None, False


def _c(pct):
    return RED if pct >= 0 else GREEN


def _hhmm(t):
    t = int(t or 0)
    return f'{t//10000:02d}:{(t % 10000)//100:02d}'


def _qt(code):
    f = _get(f'http://qt.gtimg.cn/q={code}', encoding='gbk').split('~')
    if len(f) > 50:
        avg = None
        for i in (71, 70):  # 腾讯 f71=今日均价（分时均线近似），f70 兜底
            if len(f) > i:
                try:
                    avg = float(f[i] or 0) or None
                except ValueError:
                    avg = None
                if avg:
                    break
        def _fv(i):
            try:
                return float(f[i] or 0) if len(f) > i else 0.0
            except ValueError:
                return 0.0
        # f[7]外盘 / f[8]内盘 / f[44]流通市值(亿) / f[38]换手率%：只增字段不改旧键，不影响既有调用方
        _o, _i2, _cp, _tn = _fv(7), _fv(8), _fv(44), _fv(38)
        try:
            return {'price': float(f[3]), 'pct': float(f[32]), 'open': float(f[5]),
                    'prev': float(f[4]), 'lb': float(f[43] or 0), 'vol': float(f[6] or 0),
                    'avg': avg, 'out': _o, 'in': _i2, 'cap': _cp, 'turn': _tn}
        except ValueError:
            return {'price': float(f[3]), 'pct': float(f[32]), 'open': float(f[5]),
                    'prev': float(f[4]), 'lb': 0.0, 'vol': float(f[6] or 0), 'avg': avg,
                    'out': _o, 'in': _i2, 'cap': _cp, 'turn': _tn}
    return None


# ============ 行情数据 ============
def get_global():
    out = []
    for code, nm in GLOBAL:
        f = _get(f'http://qt.gtimg.cn/q={code}', encoding='gbk').split('~')
        if len(f) > 5 and f[3] and f[4]:
            out.append((nm, float(f[3]), (float(f[3]) / float(f[4]) - 1) * 100))
    return out


def _news_drive_deep(item, purpose='watch_news', rows=None):
    """盘中异动·新闻发酵卡深挖：ModelScope 对单条事件生成五要素 JSON。
    失败返回 None（调用方用原模板兜底，不打断实时推送）。"""
    if not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return None
    _rel = []
    _zt = {}
    try:
        for _x in _follow_pool(datetime.now().strftime('%Y%m%d')):
            _zt[_x.get('c')] = _x
    except Exception:
        pass
    try:
        if rows:
            _kw = [str(item.get('sec') or '')] + [str(x) for x in (item.get('leaders') or [])] + [str(item.get('title') or '')[:12]]
            for _r in rows:
                _nm = str(_r.get('name') or '')
                _ind = str(_r.get('industry') or '')
                if any(_k and len(_k) >= 2 and (_k in _nm or _k in _ind) for _k in _kw):
                    _code = str(_r.get('code') or '')
                    _f10 = _stock_f10(_code)
                    _inc = _stock_income(_code)
                    _nws = '；'.join(_stock_news(_nm, _code)[:3])
                    _zx = _zt.get(_code)
                    _extra = (' 主业:' + _f10[:60]) if _f10 else ''
                    _extra += (' 主营:' + _inc[:60]) if _inc else ''
                    if _zx:
                        _extra += (' 今日涨停' + str(int(_zx.get('lbc') or 1)) + '连板(首封' + str(_zx.get('fbt') or '') + ')')
                    if _nws:
                        _extra += ' 新闻:' + _nws[:80]
                    _rel.append(f"{_nm}({_code}) 涨{float(_r.get('pct') or 0):+.1f}% 量比{float(_r.get('lb') or 0):.1f} 换手{float(_r.get('turn') or 0):.1f}% 板块{_ind}{_extra}")
    except Exception:
        pass
    # ============ 数据不足补充检索：全市场涨幅榜 + 涨停池 用事件关键词再捞（避免「暂无」空话） ============
    if not _rel:
        _kw2 = ([str(item.get('sec') or '')] + [str(x) for x in (item.get('leaders') or [])]
                + [str(item.get('title') or '')[:12]])
        _seen2 = set()
        try:
            for _r in _clist_gainers():
                _nm = str(_r.get('name') or '').strip()
                _ind = str(_r.get('industry') or '').strip()
                _code = str(_r.get('code') or '').strip()
                if not _nm or not _code or _code in _seen2:
                    continue
                if not any(_k and len(_k) >= 2 and (_k in _nm or _k in _ind) for _k in _kw2):
                    continue
                _seen2.add(_code)
                _f10 = _stock_f10(_code)
                _inc = _stock_income(_code)
                _nws = '；'.join(_stock_news(_nm, _code)[:3])
                _zx = _zt.get(_code)
                _extra = (' 主业:' + _f10[:60]) if _f10 else ''
                _extra += (' 主营:' + _inc[:60]) if _inc else ''
                if _zx:
                    _extra += (' 今日涨停' + str(int(_zx.get('lbc') or 1)) + '连板(首封' + str(_zx.get('fbt') or '') + ')')
                if _nws:
                    _extra += ' 新闻:' + _nws[:80]
                _rel.append(f"{_nm}({_code}) 涨{float(_r.get('pct') or 0):+.1f}% 量比{float(_r.get('lb') or 0):.1f} 换手{float(_r.get('turn') or 0):.1f}% 板块{_ind}{_extra}")
            for _x2 in _follow_pool(datetime.now().strftime('%Y%m%d')):
                _nm2 = str(_x2.get('n') or '').strip()
                _code2 = str(_x2.get('c') or '').strip()
                _ind2 = str(_x2.get('hybk') or '').strip()
                if not _nm2 or not _code2 or _code2 in _seen2:
                    continue
                if not any(_k and len(_k) >= 2 and (_k in _nm2 or _k in _ind2) for _k in _kw2):
                    continue
                _seen2.add(_code2)
                _f10 = _stock_f10(_code2)
                _inc = _stock_income(_code2)
                _nws = '；'.join(_stock_news(_nm2, _code2)[:3])
                _extra = (' 主业:' + _f10[:60]) if _f10 else ''
                _extra += (' 主营:' + _inc[:60]) if _inc else ''
                _extra += (' 今日涨停' + str(int(_x2.get('lbc') or 1)) + '连板(首封' + str(_x2.get('fbt') or '') + ')')
                if _nws:
                    _extra += ' 新闻:' + _nws[:80]
                _rel.append(f"{_nm2}({_code2}) 今日涨停{int(_x2.get('lbc') or 1)}连板 板块{_ind2}{_extra}")
        except Exception as _e:
            print('[news_refill] 补充检索异常:', _e)
    rel_txt = ('当日涨幅榜真实盘面（代表股必须从下面挑，历史强势股仅作线索不作数）：\n' + '\n'.join(_rel[:6])) if _rel else '当日涨幅榜+涨停池均未检索到与该事件/板块直接相关的异动个股：代表股字段只写一句如实结论（如「今日盘面暂无与该事件直接共振的代表个股」）+一句盘面观察说明为什么暂无，禁止五维逐条填「无/未取到/沾边/先观察」模板堆砌。'
    fmt = ('你是一线游资操盘手。盘中出现一条市场异动新闻，严格按主力视角深度挖掘，不许偷懒：\n'
           '【股票深挖铁律·代表股必做】提到代表股必须完整输出六要素：①本质（一句话大白话说清它是干什么的，禁标签糊弄）；②暗线业务（手里真正值钱的底牌：具体产品+阶段+对业绩真实贡献，挖不出写「未见明确暗线业务」，禁「相关/涉及/布局/受益于」糊弄）；③真实关联与弹性（实受益/沾边/纯蹭+弹性大小，明确判断）；④为什么是它（资金凭什么选它，真实数据）；⑤破灭点（逻辑什么时候破，必写）；⑥动作（具体触发条件+失效条件）。没有挖出有价值暗线或弹性不足，直接写「逻辑不硬，不碰」。\n'
           '【第零步·先看当日真实盘面与筹码】' + rel_txt + '\n'
           '【第一步·先看筹码后说话】先把事实说清（谁发布/干了什么/涉及谁），并判断这条消息是主力真要拉的借口，还是借消息出货的烟幕。\n'
           '【第二步·问三个主力问题】①主力为什么动它——有没有前期建仓痕迹（横盘吸筹/挖坑洗盘/红肥绿瘦）、上方筹码是否真空；②跟我什么关系——能不能跟、会不会被当接盘；③主力下一步想干什么。\n'
           '【第三步·翻译成人话】用游资黑话，结论先行+动作可执行（具体价位/仓位/止损）。\n'
           '【第四步·套游资纪律】高位连板一律不接；没有建仓痕迹的票只看戏；破点火开盘价无条件走。\n'
           '【第五步·自查】结论和逻辑不许矛盾，说机会必须带主力出货信号。\n'
           '只输出 JSON，不要任何其他文字：\n'
           '{"items":[{"t":"事件标题","i":"影响板块/题材+主力意图判断，至少15字（猜不到写「暂看不出直接关联」，不许编）","s":"代表个股深挖——【有真实相关个股时】必须完整执行深挖铁律：本质一句话+暗线业务（具体产品+阶段+真实贡献，写不出写「未见明确暗线业务」）+真实关联与弹性（实受益/沾边/纯蹭）+为什么资金今天选它（建仓痕迹/筹码真空/主业）。禁止万能句和模板堆砌。【没有直接相关个股时】只写「今日盘面暂无与该事件直接共振的代表个股」+检索结果依据，禁止编造盘面。","w":"大白话：一句话戳穿真假+主力意图，至少25字","a":"操作：买/躲/看，必须绑定具体票+价位+触发条件+止损（破点火开盘价或成本区）；逻辑不硬直接写「不碰」，代表股为空时写「今日无直接标的」+具体等待条件（点名真实公司名）。禁止万能套话和编造数值。至少20字"}]}\n'
           '')
    t = ask_deepseek({'task': purpose, 'title': item.get('title', ''),
                      'sec': item.get('sec', ''), 'leaders': '、'.join(item.get('leaders', [])) or '无',
                      'format': fmt}, purpose=purpose)
    pairs = _parse_ds_json(t)
    if pairs and len(pairs[0]) >= 5:
        if isinstance(pairs[0], tuple):
            pairs[0] = list(pairs[0])
        _s0 = str(pairs[0][2] or '')
        _a0 = str(pairs[0][4] or '')
        _s_bad = ('缩量横盘', '恐慌性砸盘', '抢筹迹象', '未现恐慌', '普涨无梯队')
        _a_bad = ('破位即跑', '空仓不动', '等盘中出现', '跌破昨日低点无条件离场', '核心票',
                  '回踩20日线', '5日均量', '缩量至', 'XX元低吸', 'XX元半路')
        _s_fix = '今日盘面暂无与该事件直接共振的代表个股。当日涨幅榜与涨停池均未检索到与该事件相关的放量异动个股，缺乏资金点火确认。'
        _a_fix = '今日无直接标的。等待该板块出现放量异动龙头（量比放大、换手抬升、有真实买盘确认）后再评估，具体价位以实时行情为准。'
        if any(w in _s0 for w in _s_bad):
            pairs[0][2] = _s_fix
        if any(w in _a0 for w in _a_bad):
            pairs[0][4] = _a_fix
    if pairs and len(pairs[0]) >= 5 and len(pairs[0][2]) >= 20:
        return pairs[0]
    return None


def get_indices():
    return [{'name': nm, 'pct': _qt(c)['pct']} for c, nm in INDICES if _qt(c)]


def commodities():
    """商品+中概，盘前背景。失败/休市标注，不造假。"""
    items = [('🛢️原油', 'hf_CL'), ('🥇黄金', 'hf_GC'),
             ('🥉伦铜', 'hf_CAD'), ('🐉中概金龙', 'usHXC')]
    rows = []
    for nm, code in items:
        txt, ok = _getm(f'http://qt.gtimg.cn/q={code}', f'comm_{code}')
        if not ok or not txt:
            rows.append(f'{nm} <span style="color:{GREY}">未取得</span>')
            continue
        try:
            if code.startswith('hf_'):
                s = txt.split('"')[1].split(',')
                price, pct = s[0], float(s[1])
            else:
                f = txt.split('~')
                price = f[3]
                pct = (float(f[3]) / float(f[4]) - 1) * 100 if f[4] not in ('', '0.00') else 0.0
            c = RED if pct >= 0 else GREEN
            rows.append(f'{nm} <b style="color:{c}">{pct:+.2f}%</b> <span style="color:{GREY}">{price}</span>')
        except Exception:
            rows.append(f'{nm} <span style="color:{GREY}">格式异常</span>')
    return '<br>'.join(rows)


def _qt_batch(codes):
    """批量实时行情 {纯code: (price, prev_close)}"""
    out = {}
    cs = [c if c.startswith(('sh', 'sz')) else ('sh' if c.startswith('6') else 'sz') + c for c in codes]
    for i in range(0, len(cs), 60):
        txt, ok = _getm('http://qt.gtimg.cn/q=' + ','.join(cs[i:i + 60]), 'qt_batch', encoding='gbk')
        if not ok:
            continue
        for line in txt.strip().split(';'):
            if '~' not in line:
                continue
            f = line.split('~')
            try:
                out[f[2][2:]] = (float(f[3]), float(f[4]))
            except Exception:
                pass
    return out


def yesterday_premium():
    """昨日涨停股今日溢价。名单=最近有数据交易日ZTPool。"""
    from datetime import timedelta
    day = datetime.now()
    pool = []
    for back in range(1, 6):
        d = (day - timedelta(days=back)).strftime('%Y%m%d')
        txt, ok = _getm(
            f'https://push2ex.eastmoney.com/getTopicZTPool?ut=7eea3edcaed734bea9cbfc24409ed989'
            f'&dpt=wz.ztzt&Pageindex=0&pagesize=300&sort=fbt:asc&date={d}',
            f'yest_{d}')
        if ok and txt:
            pool = (json.loads(txt).get('data') or {}).get('pool') or []
            if pool:
                break
    if not pool:
        return '<b>昨日涨停：</b><span style="color:#e6a23c">未取得（盘前/非交易日）</span>'
    now = _qt_batch([x['c'] for x in pool if x.get('c')])
    pcts, up, ldt = [], 0, 0
    for x in pool:
        q = now.get(x['c'])
        if not q or not q[1]:
            continue
        p = (q[0] / q[1] - 1) * 100
        pcts.append(p)
        if p > 0:
            up += 1
        if p <= -9.5:
            ldt += 1
    n = len(pcts)
    if n == 0:
        return f'<b>昨日涨停溢价：</b><span style="color:{GREY}">昨日{len(pool)}只，盘前暂无今日行情</span>'
    avg = sum(pcts) / n
    c = RED if avg >= 0 else GREEN
    return (f'<b>昨日涨停溢价：</b><span style="color:{c}">均{avg:+.2f}%</span> '
            f'红盘占{up / n * 100:.0f}%({up}/{n}) 跌停{ldt}｜样本{len(pool)}/有效{n}')


def money_flow_note():
    """资金流向：push2在当前网络被墙，改用两市成交额做量级参考；成交额也拿不到才如实标注。"""
    try:
        amt = 0.0
        for c in ('sh000001', 'sz399001'):
            f = _get(f'http://qt.gtimg.cn/q={c}', encoding='gbk').split('~')
            if len(f) > 37:
                amt += float(f[37] or 0)
        if amt > 0:
            yi = amt / 10000.0
            return f'<b>资金流向：</b><span style="color:#888">两市成交约 {yi:.0f} 亿（主力净流入接口被墙，仅供参考量级）</span>'
    except Exception:
        pass
    return '<b>资金流向：</b><span style="color:#888">免费接口被墙，主力净流入未取得（成交额≠净流入）</span>'


def coarse_linkage(d):
    """粗联动：今日涨停最多板块 vs 昨日记忆，判断是新点火还是延续。"""
    mem = load_memory()
    days = sorted(mem.keys(), reverse=True)
    prev = set()
    for pd in days[1:3]:
        prev |= set(mem.get(pd, {}).keys())
    now = [n for n, _ in d['tops'][:5]]
    new = [n for n in now if n not in prev]
    if new:
        return f'🆕 新点火：{"、".join(new[:3])}（昨日无记录，观察跟风是否持续）'
    return f'🔁 主线延续：{"、".join(now[:3])}（昨日已活跃）'


# ============ 抽样广度 + 龙头分歧 ============
SAMPLE_BASKET = ['600519','601318','600036','000858','600030','601166','600276','000333',
                 '601899','600900','601012','300750','002594','600031','601888','600050',
                 '601988','600028','601088','600585','601668','600048','000002','002415',
                 '300059','600837','601211','600196','000725','601919','600009','002230',
                 '300760','603259','688981','688111','688036','300274','002475','600519']


def breadth_sample():
    """抽样广度：固定蓝筹篮子，统计涨跌比/MA20站上率。标注抽样。"""
    q = _qt_batch(SAMPLE_BASKET)
    up = down = flat = 0
    for code, (price, prev) in q.items():
        if not prev:
            continue
        chg = (price / prev - 1) * 100
        if chg > 0.05:
            up += 1
        elif chg < -0.05:
            down += 1
        else:
            flat += 1
    n = up + down + flat
    if n == 0:
        return '<b>市场广度(抽样)：</b><span style="color:#e6a23c">未取得</span>'
    ar = up / n * 100
    c = RED if ar >= 60 else (GREEN if ar <= 30 else GOLD)
    return (f'<b>市场广度(抽样{n}只)：</b>涨{up} 平{flat} 跌{down} '
            f'｜红盘占比<span style="color:{c};font-weight:700">{ar:.0f}%</span>'
            f'<span style="color:#888">（蓝筹抽样，非全市场）</span>')


def leader_divergence(d):
    """龙头分歧：今日在炸板池(ZB)里、且连板数≥2的票 = 高位分歧。"""
    # d['dt_sec'] 是跌停；炸板行业在 d['worst']；这里直接读ZB池
    txt, ok = _getm(
        f'https://push2ex.eastmoney.com/getTopicZBPool?ut=7eea3edcaed734bea9cbfc24409ed989'
        f'&dpt=wz.ztzt&Pageindex=0&pagesize=200&sort=fbt:asc&date={datetime.now().strftime("%Y%m%d")}',
        'zb_div')
    if not ok or not txt:
        return ''
    zb = (json.loads(txt).get('data') or {}).get('pool') or []
    high = [x for x in zb if int(x.get('lbc') or 0) >= 2]
    if not high:
        return ''
    names = '、'.join(f"{x.get('n')}({x.get('lbc')}板)" for x in high[:5])
    return (f'<div style="margin-top:8px;padding:8px 10px;background:#2a1f22;border-left:3px solid {RED};'
            f'border-radius:8px;color:{RED};font-size:13px;">⚠️ 高位炸板分歧：{names}，这几只是连板到高位又炸开的，分歧已经出来了</div>')


# ============ 盘后信号复盘 signals.json ============
SIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'signals.json')


def load_signals():
    try:
        with open(SIG_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def save_signals(sig):
    with open(SIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(sig, f, ensure_ascii=False, indent=1)
    _git_commit_push(SIG_PATH, 'update signals')


def record_signals(cands):
    """收盘记录今日可跟踪信号（code/name/close/date），次日回填。"""
    day = datetime.now().strftime('%Y-%m-%d')
    sig = load_signals()
    have = {(s['date'], s['code']) for s in sig}
    added = 0
    for c in cands[:10]:
        code = c.get('code')
        if not code or (day, code) in have:
            continue
        q = _qt(('sh' if code.startswith('6') else 'sz') + code)
        sig.append({'date': day, 'code': code, 'name': c.get('n'),
                    'close': q['price'] if q else None, 'pct': q['pct'] if q else None,
                    'next_open_pct': None})
        added += 1
    if added:
        save_signals(sig[-200:])
    return added


def backfill_signals():
    """给昨天未回填信号补今日开盘溢价。"""
    sig = load_signals()
    today = datetime.now().strftime('%Y-%m-%d')
    n = 0
    for s in sig:
        if s.get('next_open_pct') is None and s.get('close') and s['date'] != today:
            q = _qt(('sh' if s['code'].startswith('6') else 'sz') + s['code'])
            if q and q['open']:
                s['next_open_pct'] = (q['open'] / s['close'] - 1) * 100
                n += 1
    if n:
        save_signals(sig)
    return n


# 新增F：信号复盘日志路径
SIGNAL_REVIEW_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'review_log.json')


def _signal_review_llm():
    """🧪 信号复盘机（新增F）：昨日推荐信号 → 今日开盘结果 → LLM 归因（对在哪/错在哪/规则过严或过松）→ 写 data/review_log.json。失败/无样本 → ''。"""
    if not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return ''
    from datetime import timedelta  # 修复：_signal_review_llm 缺 timedelta 局部导入（reson_td_fix）
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    sig = [s for s in load_signals() if s.get('date') == yesterday and s.get('next_open_pct') is not None]
    if not sig:
        return ''
    rows_txt = '；'.join(f"{s.get('name')}({s.get('code')}) 开盘溢价{s.get('next_open_pct'):+.1f}%" for s in sig[:10])
    fmt = ('你是一线游资，对昨日推荐信号做复盘归因。重点回答：昨天推荐的票，主力今天是继续做还是出货了。只输出 JSON：\n'
           '{"verdict":"昨日推荐整体对/错/一半一半","good":["对在哪1-2条（含主力行为）"],"bad":["错在哪1-2条（含主力出货信号）"],"rule":"规则是过严/过松/合适","next":"明日是否延续/如何修正(≤2句)"}\n'
           '昨日信号：' + rows_txt)
    t = ask_deepseek({'task': 'signal_review', 'signals': [s.get('code') for s in sig[:10]], 'format': fmt}, purpose='signal_review')
    if not t:
        return ''
    try:
        _j = json.loads(t)
    except Exception:
        return ''
    try:
        os.makedirs(os.path.dirname(SIGNAL_REVIEW_PATH), exist_ok=True)
        with open(SIGNAL_REVIEW_PATH, 'w', encoding='utf-8') as f:
            json.dump({'date': _bj_now().strftime('%Y-%m-%d'), **{k: _j.get(k, '') for k in ('verdict', 'good', 'bad', 'rule', 'next')}}, f, ensure_ascii=False, indent=1)
        _git_commit_push(SIGNAL_REVIEW_PATH, 'update signal review log')
    except Exception:
        pass
    g = '、'.join(_j.get('good') or []) or '—'
    b2 = '、'.join(_j.get('bad') or []) or '—'
    return (f'<div style="margin-top:8px;padding:9px 11px;background:#1c2230;border-left:4px solid {GOLD};border-radius:8px;font-size:12px;color:#ced4da;line-height:1.7;">'
            f'🧪 <b style="color:#ffd43b;">信号复盘归因</b>：{_j.get("verdict","")}<br>'
            f'✅ 对在哪：{g}<br>❌ 错在哪：{b2}<br>'
            f'📏 规则：{_j.get("rule","")} ｜ 🔭 明日：{_j.get("next","")}</div>')


def signals_review_html():
    """近20条已结算信号的开盘溢价统计。"""
    sig = [s for s in load_signals() if s.get('next_open_pct') is not None]
    if not sig:
        return '<b>信号复盘：</b><span style="color:#888">暂无已结算样本（信号从今日开始记录）</span>'
    recent = sig[-20:]
    pcts = [s['next_open_pct'] for s in recent]
    avg = sum(pcts) / len(pcts)
    win = sum(1 for p in pcts if p > 0) / len(pcts) * 100
    c = RED if avg >= 0 else GREEN
    return (f'<b>信号复盘：</b>近{len(recent)}条平均开盘溢价<span style="color:{c}">{avg:+.2f}%</span>，'
            f'红盘{win:.0f}%（样本积累中，不代表实盘胜率）')


def _klines_em(sym, n):
    """东方财富前复权日K（腾讯 fqkline 限流 501 时的 fallback）。行格式与腾讯一致：[日期,开,收,高,低,量]。"""
    sec = ('1.' if sym.startswith('sh') else '0.') + sym[2:]
    url = (f'https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={sec}'
           f'&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58'
           f'&klt=101&fqt=1&beg=0&end=20500101&lmt={n}')
    d = json.loads(_get(url))
    kl = (d.get('data') or {}).get('klines') or []
    out = []
    for row in kl:
        p = row.split(',')
        if len(p) < 6:
            continue
        try:
            out.append([p[0], float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5])])
        except ValueError:
            continue
    return out


def get_klines(code, n=20):
    url = f'https://ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,{n},qfq'
    try:
        d = json.loads(_get(url))
        _data = d.get('data') or {}
        if isinstance(_data, dict):
            node = _data.get(code, {}) or {}
            ks = node.get('qfqday') or node.get('day') or []
            if ks:
                return ks
    except Exception:
        pass
    # 腾讯接口限流/异常（HTTP 501）时回退东财，保证周期视角真实出数据
    try:
        return _klines_em(code, n)
    except Exception:
        return []


# —— 多周期视角引擎（券商量化配置：超短线/短线/中长线/长线 + 原因）——
_CYCLE_CACHE = {}

def _cycle_tag(code, industry='', heat=0):
    """基于日K(70)算 MA5/10/20/60 与位置/量能/回撤，输出 (主周期, 原因串)。
    口径：超短线1-3日(动量/接力)、短线3-10日(趋势低吸)、中长线1-6月(趋势仓)、长线6月+(底仓/配置)。
    拉取失败/数据不足静默返回 ('','')，不破坏卡片；结果按 code 缓存（当日一次）。"""
    if not code:
        return '', ''
    if code in _CYCLE_CACHE:
        return _CYCLE_CACHE[code]
    out = ('', '')
    try:
        sym = ('sh' if code.startswith('6') else ('bj' if code.startswith(('4', '8')) else 'sz')) + code
        ks = get_klines(sym, 70)
        if not ks or len(ks) < 25:
            return '', ''
        closes = [float(k[2]) for k in ks]
        vols = [float(k[5]) for k in ks]
        cur = closes[-1]
        def _ma(n):
            return (sum(closes[-n:]) / n) if len(closes) >= n else None
        ma5, ma10, ma20, ma60 = _ma(5), _ma(10), _ma(20), _ma(60)
        if ma5 is None or ma20 is None:
            return '', ''
        vol5 = (sum(vols[-5:]) / 5) if len(vols) >= 5 else 0
        vol20 = (sum(vols[-20:]) / 20) if len(vols) >= 20 else vol5
        vr = (vol5 / vol20) if vol20 else 1.0
        highs60 = max(float(k[3]) for k in ks[-60:]) if len(ks) >= 5 else cur
        dd = ((highs60 - cur) / highs60 * 100) if highs60 else 0.0
        chg5 = ((cur / closes[-6] - 1) * 100) if len(closes) >= 6 else 0.0
        above20 = cur >= ma20 if ma20 is not None else False
        above60 = cur >= ma60 if ma60 is not None else False
        bull = bool(ma20 and ma60 and ma20 > ma60)
        _ht = f'、题材热度{heat:.0f}' if heat >= 55 else ''
        if above60 and bull and dd < 12:
            if vr < 1.3:
                out = ('长线（6月+）', f'MA20>MA60多头排列、距60日高点回撤仅{dd:.0f}%、量能温和({vr:.1f}倍)——机构趋势特征，可作底仓/波段持有{_ht}')
            else:
                out = ('中长线（1-6月）', f'多头排列、回撤{dd:.0f}%、量能放大({vr:.1f}倍)、5日涨幅{chg5:+.1f}%，趋势仓波段参与{_ht}')
        elif cur >= ma5 and chg5 > 8 and vr >= 1.8 and not bull:
            out = ('超短线（1-3日）', f'非趋势急拉：5日涨幅{chg5:+.1f}%、量能放大({vr:.1f}倍)，次日竞价/分时博弈，快进快出')
        elif above20 and vr >= 1.2:
            out = ('短线（3-10日）', f'站上MA20、5日量能{"放大" if vr >= 1.5 else "温和"}({vr:.1f}倍)、5日涨幅{chg5:+.1f}%，回踩MA10/MA20参与{_ht}')
        elif cur >= ma5 and (chg5 > 8 or vr >= 1.8):
            out = ('超短线（1-3日）', f'MA5上方强动量、5日涨幅{chg5:+.1f}%、量能放大({vr:.1f}倍)——次日竞价/分时博弈，快进快出')
        elif above20:
            out = ('短线（3-10日）', f'站上MA20但量能未跟上({vr:.1f}倍)，等放量确认再参与')
        else:
            out = ('短线观察', f'未站上MA20{"（跌破MA60，趋势偏弱）" if not above60 else ""}，趋势未修复，观望为主')
    except Exception:
        out = ('', '')
    _CYCLE_CACHE[code] = out
    return out


def get_pools():
    day = datetime.now().strftime('%Y%m%d')
    sectors = defaultdict(list)
    dt_sec = defaultdict(list)
    zb_sec = defaultdict(int)
    lu = zb = dt = max_lbc = 0
    ok_zt = ok_zb = ok_dt = False   # 三池各自是否接口成功

    def _pool(tag):
        return (f'https://push2ex.eastmoney.com/getTopic{tag}Pool?ut=7eea3edcaed734bea9cbfc24409ed989'
                f'&dpt=wz.ztzt&Pageindex=0&pagesize=300&sort=fbt:asc&date={day}')
    txt, ok_zt = _getm(_pool('ZT'), 'zt_pool')
    if ok_zt and txt:
        pool = (json.loads(txt).get('data') or {}).get('pool') or []
        lu = len(pool)
        for x in pool:
            sectors[x.get('hybk') or '其他'].append(x)
            max_lbc = max(max_lbc, int(x.get('lbc') or 0))
            _hy = _sec_clean(x.get('hybk') or '')
            if _hy and x.get('c'):
                _IND_CACHE[str(x['c'])] = _hy
    zbp_raw = []
    txt, ok_zb = _getm(_pool('ZB'), 'zb_pool')
    zb_names = set()
    if ok_zb and txt:
        zbp = (json.loads(txt).get('data') or {}).get('pool') or []
        zbp_raw = zbp
        zb = len(zbp)
        for x in zbp:
            zb_sec[x.get('hybk') or '其他'] += 1
            if x.get('n'):
                zb_names.add(x.get('n'))
            _hy = _sec_clean(x.get('hybk') or '')
            if _hy and x.get('c'):
                _IND_CACHE[str(x['c'])] = _hy
    if _IND_CACHE:
        _ind_cache_save()
    txt, ok_dt = _getm(_pool('DT'), 'dt_pool')
    if ok_dt and txt:
        dtp = (json.loads(txt).get('data') or {}).get('pool') or []
        dt = len(dtp)
        for x in dtp:
            dt_sec[x.get('hybk') or '其他'].append(x.get('n'))
    themes = {n: st for n, st in sectors.items() if len(st) >= 3}
    tops = sorted(sectors.items(), key=lambda kv: -len(kv[1]))[:20]
    worst = sorted(zb_sec.items(), key=lambda kv: -kv[1])[:5]
    ladder = defaultdict(list)
    for st in sectors.values():
        for s in st:
            if int(s.get('lbc') or 0) >= 2:
                ladder[int(s.get('lbc'))].append(s.get('n'))
    return {'lu': lu, 'zb': zb, 'dt': dt, 'max_lbc': max_lbc,
            'sectors': sectors, 'themes': themes, 'tops': tops, 'worst': worst,
            'dt_sec': dict(dt_sec), 'ladder': sorted(ladder.items(), reverse=True),
            'zb_names': zb_names, 'zb_pool': zbp_raw,
            'pool_ok': {'zt': ok_zt, 'zb': ok_zb, 'dt': ok_dt}}


# ============ 工单11：涨停板质量精修（封成比 + 断板/回封基因） ============
def _lpq_tmin(t):
    """涨停池 fbt/lbt 的 HHMMSS 整数 → 当日分钟数（09:25 => 565）。"""
    try:
        t = int(t or 0)
        if not t:
            return 0
        return (t // 10000) * 60 + ((t // 100) % 100)
    except Exception:
        return 0


def _lpq_hhmm(t):
    _m = _lpq_tmin(t)
    return ('%02d:%02d' % (_m // 60, _m % 60)) if _m else ''


def _limitup_quality(d):
    """涨停质量（工单11）：封成比=封板资金/成交额（真封假封）；炸板后回封速度（洗盘 vs 出货）。
    返回 {code: {name, ratio, zbc, fbt, lbt, gap, tag, amt, score}}；失败返回 {}。"""
    out = {}
    try:
        for _sec, _sts in (d.get('sectors') or {}).items():
            for x in (_sts or []):
                _c = str(x.get('c') or '')
                if not _c:
                    continue
                _fund = float(x.get('fund') or 0)
                _amt = float(x.get('amount') or 0)
                _fbt = int(x.get('fbt') or 0)
                _lbt = int(x.get('lbt') or 0)
                _zbc = int(x.get('zbc') or 0)
                _ratio = (_fund / _amt) if _amt > 0 else 0.0
                _gap = (_lpq_tmin(_lbt) - _lpq_tmin(_fbt)) if (_fbt and _lbt and _zbc) else 0
                if _zbc == 0:
                    _tag = '首封未炸'
                elif _gap and _gap <= 20:
                    _tag = '炸板快速回封·洗盘'
                elif _lpq_tmin(_lbt) >= 14 * 60:
                    _tag = '尾盘勉强回封·弱'
                else:
                    _tag = '炸板后回封'
                _score = 0
                if _ratio >= 1.0:
                    _score += 5
                elif _ratio >= 0.5:
                    _score += 4
                elif _ratio >= 0.25:
                    _score += 2
                elif _ratio >= 0.1:
                    _score += 1
                if _ratio >= 0.5 and _amt >= 1.5e9:
                    _score -= 2          # 封单大但成交也爆 = 对倒出货嫌疑
                if _zbc == 0:
                    _score += 3
                elif _gap and _gap <= 20:
                    _score += 2
                elif _gap and _gap <= 60:
                    _score += 1
                if _lpq_tmin(_lbt) >= 14 * 60:
                    _score -= 2
                out[_c] = {'name': str(x.get('n') or ''), 'ratio': _ratio, 'zbc': _zbc,
                           'fbt': _fbt, 'lbt': _lbt, 'gap': _gap, 'tag': _tag,
                           'amt': _amt, 'score': max(0, min(10, _score))}
        # 断板不回封：在炸板池、却不在涨停池 → 出货，次日不追
        for x in (d.get('zb_pool') or []):
            _c = str(x.get('c') or '')
            if not _c or _c in out:
                continue
            out[_c] = {'name': str(x.get('n') or ''), 'ratio': 0.0,
                       'zbc': int(x.get('zbc') or 1), 'fbt': int(x.get('fbt') or 0),
                       'lbt': 0, 'gap': 0, 'tag': '断板未回封·出货',
                       'amt': float(x.get('amount') or 0), 'score': 0}
    except Exception as e:
        print('[lpq] 涨停质量计算异常:', e)
    return out


def _lpq_line(q):
    """涨停质量一句话（卡面用）：封成比41% · 首封09:25 · 炸板1次09:30回封 · 炸板快速回封·洗盘。"""
    if not q:
        return ''
    _bits = []
    if q.get('ratio'):
        _bits.append('封成比%.0f%%' % (q['ratio'] * 100))
    if q.get('fbt'):
        _bits.append('首封' + _lpq_hhmm(q['fbt']))
    if q.get('zbc'):
        _bits.append('炸板%d次' % q['zbc'])
        if q.get('lbt'):
            _bits.append(_lpq_hhmm(q['lbt']) + '回封')
    if q.get('tag'):
        _bits.append(q['tag'])
    return ' · '.join(_bits)


def _lqtrack_pool(d, min_score=6):
    """可跟踪池（工单11）：封成比高/快速回封的票，次日溢价概率更高。
    返回 [(name, code, line)]，最多 5 条。"""
    try:
        _m = _limitup_quality(d)
    except Exception:
        return []
    _rows = sorted([(_c, q) for _c, q in _m.items() if q.get('score', 0) >= min_score],
                   key=lambda kv: -kv[1]['score'])[:5]
    return [(q['name'] or _c, _c, _lpq_line(q)) for _c, q in _rows]


# ============ 核心规则 ============
def sentiment(idx, d):
    avg = sum(x['pct'] for x in idx) / len(idx) if idx else 0
    zbr = d['zb'] / (d['lu'] + d['zb']) if (d['lu'] + d['zb']) else 0.3
    if zbr >= 0.42 or d['dt'] >= 40 or avg <= -0.6:
        b, r = '偏空', '高'
    elif avg >= 0.4 and d['lu'] >= 55 and zbr < 0.28 and d['dt'] <= 15:
        b, r = '偏多', '低'
    else:
        b, r = '震荡', '中'
    return b, r, avg, zbr


def three_way(open_pct, lb, vq_ratio=None):
    """持仓竞价三分法（档位由代码阈值实算，动作文案交 AI 判读；此处只给档位与数据）：
    - 开幅≥7% → 档位：高开过大（代码阈值）
    - 2%~7% 且量比≥1.8 且 竞价量/昨量≥10% → 档位：量价达标（代码阈值）
    - 低开<0 且跌幅<3% → 档位：小幅低开未破位（代码阈值）
    - 其余 → 档位：量价不达标（代码阈值）"""
    if open_pct is None:
        return '待数据', '今开还没出来，这会儿看不出东西'
    if open_pct >= 7:
        return '高开过大（档位）', f'开{open_pct:+.1f}%，高开这么多追进去就是接盘'
    if 2 <= open_pct < 7 and lb >= 1.8 and (vq_ratio is None or vq_ratio >= 10):
        return '量价达标（档位）', (f'开{open_pct:+.1f}%·量比{lb:.1f}≥1.8'
                                    + (f'·竞价量能是昨量的{vq_ratio:.0f}%' if vq_ratio else '') + '，买盘是真在接')
    if open_pct < 0 and open_pct > -3:
        return '小幅低开（档位）', f'低开{open_pct:+.1f}%，没破3个点，坑不算深'
    return '量价不达标（档位）', f'开幅{open_pct:+.1f}%、量比{lb:.1f}，量价都没达标，这种不碰'


def contagion(d):
    """持仓所在板块同板块≥3只跌停/大跌 → 传染风险。"""
    out = []
    for h in HOLDINGS:
        sec = h['sector']
        hits = d['dt_sec'].get(sec, [])
        if len(hits) >= 3:
            out.append(f"{h['name']}：{sec}板块{len(hits)}只跌停（{'、'.join(hits[:4])}），传染风险")
    return out


def eod_candidates(d):
    """尾盘承接：点火板块里 十字星/缩量 且近15日有涨停基因。"""
    cands = []
    seen = set()
    for name, stocks in list(d['themes'].items())[:6]:
        for s in stocks:
            code = s.get('c')
            if code in seen:
                continue
            seen.add(code)
            sym = ('sh' if code.startswith('6') else 'sz') + code
            try:
                arr = get_klines(sym, 16)
                if len(arr) < 15:
                    continue
                today = arr[-1]
                o, c, v = float(today[1]), float(today[2]), float(today[5])
                avgv = sum(float(r[5]) for r in arr[-6:-1]) / 5
                body = abs(c - o) / o if o else 0
                # 近15日有涨停（单日≥9.8%）
                has_gene = any(float(r[2]) / float(r[1]) >= 1.095 for r in arr[-15:] if float(r[1]) > 0)
                shrink = v / avgv if avgv else 1
                if has_gene and (body < 0.015 or shrink < 0.8):
                    cands.append({'name': s.get('n'), 'code': code, 'sec': name,
                                  'body': body, 'shrink': shrink})
            except Exception:
                pass
    return cands[:10]


# ============ 题材记忆 ============
def load_memory():
    try:
        with open(MEM_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_memory(mem):
    with open(MEM_PATH, 'w', encoding='utf-8') as f:
        json.dump(mem, f, ensure_ascii=False, indent=1)
    _git_commit_push(MEM_PATH, 'update theme memory')


def load_judgment():
    try:
        with open(JUDGMENT_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def write_judgment(entry):
    """每日收盘落盘「今日判断」关键点（供次日模型对比）；失败静默。"""
    try:
        j = load_judgment()
        j[entry['date']] = entry
        with open(JUDGMENT_PATH, 'w', encoding='utf-8') as f:
            json.dump(j, f, ensure_ascii=False, indent=1)
        _git_commit_push(JUDGMENT_PATH, 'update judgment log')
    except Exception:
        pass


JUDGMENT_V2_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'judgment.json')
POSITION_GAUGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'position_gauge.json')


def load_judgment_v2():
    """结构化今日判断 data/judgment.json：{date: {emotion,mainline,recommend,risk,tomorrow_plan,position}}。"""
    try:
        with open(JUDGMENT_V2_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def write_judgment_v2(entry):
    """结构化落盘 data/judgment.json（五词条 + position）；失败静默。"""
    try:
        j = load_judgment_v2()
        j[entry['date']] = entry
        os.makedirs(os.path.dirname(JUDGMENT_V2_PATH), exist_ok=True)
        with open(JUDGMENT_V2_PATH, 'w', encoding='utf-8') as f:
            json.dump(j, f, ensure_ascii=False, indent=1)
        _git_commit_push(JUDGMENT_V2_PATH, 'update structured judgment')
    except Exception as e:
        print('[judgment-v2] 写入失败:', e)


def load_position_gauge():
    """当前仓位仪表盘 data/position_gauge.json（跨模块注入）；无/过期返回 None。"""
    try:
        with open(POSITION_GAUGE_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def save_position_gauge(entry):
    """落盘仓位仪表盘（suggest/emotion/reason/valid_until）；失败静默。"""
    try:
        os.makedirs(os.path.dirname(POSITION_GAUGE_PATH), exist_ok=True)
        with open(POSITION_GAUGE_PATH, 'w', encoding='utf-8') as f:
            json.dump(entry, f, ensure_ascii=False, indent=1)
        _git_commit_push(POSITION_GAUGE_PATH, 'update position gauge')
    except Exception as e:
        print('[position-gauge] 写入失败:', e)


def judgment_context():
    """上一个交易日「昨日判断」文本（供 DS 对比）；优先 data/judgment.json 结构化，回退旧 judgment_log.json。"""
    today = datetime.now().strftime('%Y-%m-%d')
    j2 = load_judgment_v2()
    if j2:
        days = sorted(j2.keys())
        if days and days[-1] != today:
            p = j2[days[-1]]
            if isinstance(p, dict) and (p.get('emotion') or p.get('mainline')):
                parts = [f"情绪：{p.get('emotion', '')}",
                         f"主线：{p.get('mainline', '')}",
                         f"推荐：{p.get('recommend', '')}",
                         f"风险：{p.get('risk', '')}",
                         f"明日预案：{p.get('tomorrow_plan', '')}",
                         f"仓位：{p.get('position', '')}"]
                txt = '；'.join(x for x in parts if x and not x.endswith('：'))
                if txt.strip():
                    return txt
    j = load_judgment()
    days = sorted(j.keys())
    if not days:
        return ''
    if days[-1] == today:
        days.pop()
    if not days:
        return ''
    y = j[days[-1]]
    return ('昨日判断（%s）：情绪%s·%s（%s分）；主线：%s；推荐池：%s；仓位建议：%s；风险点：%s' % (
        y.get('date', ''), y.get('emotion', ''), y.get('label', ''), y.get('score', ''),
        '、'.join((y.get('tops') or [])[:3]) or '无',
        '、'.join((y.get('pool') or [])[:3]) or '无强推',
        y.get('pos', ''), y.get('risk', '') or '未记'))


def write_today_memory(d):
    """尾盘：记录当天强势题材+龙头（含最高连板/封板时间/是否分歧转一致）。"""
    today = datetime.now().strftime('%Y-%m-%d')
    mem = load_memory()
    today_sec = {}
    for name, stocks in d['tops'][:8]:
        if len(stocks) < 2:
            continue
        stocks.sort(key=lambda s: (-int(s.get('lbc') or 0), s.get('fbt') or 0))
        leaders = [s.get('n') for s in stocks[:3]]
        strength = min(10, 5 + len(stocks) + int(stocks[0].get('lbc') or 0))
        lead = stocks[0]
        divergence = bool(d.get('zb_names') and lead.get('n') in d.get('zb_names', set()))
        today_sec[name] = {'leaders': leaders,
                           'reason': f'{len(stocks)}只涨停·龙头{stocks[0].get("n")}',
                           'strength': strength,
                           'max_lbc': int(lead.get('lbc') or 0),
                           'fbt': lead.get('fbt'),
                           'divergence': divergence}
    mem[today] = today_sec
    # 只保留最近 10 天
    days = sorted(mem.keys(), reverse=True)[:10]
    save_memory({k: mem[k] for k in days})
    return today_sec


def market_behavior(d):
    """判断：主线持续 还是 板块轮动（档位由代码算，文案只陈述数据）。"""
    mem = load_memory()
    days = sorted(mem.keys(), reverse=True)
    today_top = {n for n, _ in d['tops'][:3]}
    prev_top = set()
    for pd in days[1:3]:  # 昨天+前天
        prev_top |= set(mem.get(pd, {}).keys())
    overlap = today_top & prev_top
    if len(overlap) >= 2:
        return '主线持续', f"今日最强{len(overlap)}个板块（{'、'.join(list(overlap)[:2])}）昨日也在榜（代码比对）。", overlap
    return '板块轮动', f"今日最强方向（{'、'.join(list(today_top)[:2])}）与前两日榜单无重叠（代码比对）。", overlap


def detect_anomalies(d):
    """异动检测：返回 [{type, stocks, why, action}]。"""
    out = []
    mem = load_memory()
    days = sorted(mem.keys(), reverse=True)
    yest = days[1] if len(days) > 1 else None
    yest_sec = set(mem.get(yest, {}).keys()) if yest else set()

    # 1) 题材启动：今天新出现≥3只涨停、昨天没有
    for name, stocks in d['themes'].items():
        if name not in yest_sec:
            out.append({'type': '🔥题材启动',
                        'stocks': [s.get('n') for s in stocks[:4]],
                        'why': f'{name}今天突然{len(stocks)}只涨停，昨天还没有',
                        'action': ''})
    # 2) 老龙头回流：记忆里的leaders今日涨>3%
    seen = set()
    for pd in days[:3]:
        for sec, info in mem.get(pd, {}).items():
            for nm in (info.get('leaders', []) if isinstance(info, dict) else []):  # 数据异常防御（WATCH_GUARD）
                if nm in seen:
                    continue
                seen.add(nm)
                # 找代码：从今天池或直接猜
                code = None
                for _, stocks in d['sectors'].items():
                    for s in stocks:
                        if s.get('n') == nm:
                            code = s.get('c')
                if not code:
                    continue
                sym = ('sh' if code.startswith('6') else 'sz') + code
                try:
                    q = _qt(sym)
                    if q and q['pct'] >= 3 and q.get('lb', 0) >= 1.5:
                        out.append({'type': '⭐老龙头回流', 'stocks': [nm],
                                    'why': f'{sec}上次强势股{nm}今天{q["pct"]:+.1f}%·量比{q.get("lb",0):.1f}',
                                    'action': ''})
                except Exception:
                    pass
    return out[:6]


_WARN_DIAG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'warn_diag.txt')


_WARN_DIAG_LINES = []      # warn 排障：本次 run 诊断行收集
_WECOM_DEBUG_URL = 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=7249aadb-841a-4e8f-a952-d0b69efcb072'


def _warn_diag_wecom(text):
    """warn 排障：诊断双通道 = 企微 webhook（备用）+ PushPlus（主，云端已验证可达）。
    任一路成功即达用户微信；失败静默不阻塞主流程。"""
    try:
        body = json.dumps({'msgtype': 'markdown',
                           'markdown': {'content': '**🚨warn排障** ' + text}},
                          ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(_WECOM_DEBUG_URL, data=body,
                                     headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:
        pass
    # PUSHPLUS 兜底：云端 Actions 连不上企微/新闻域时，PushPlus 是历史验证可达的唯一外发通道。
    # 绕过静默：诊断属于排障信息，不受 data/silence.json 限制（否则凌晨跑会被吞，排障无从谈起）
    try:
        _html = _wrap('<div style="color:#e2e8f0;font-size:13px;line-height:1.7;">' + text + '</div>', '🔧', 'warn排障')
        _body = json.dumps({'token': PUSHPLUS_TOKEN, 'title': '【warn排障】' + text[:28],
                            'content': _html, 'template': 'html'}).encode('utf-8')
        _req = urllib.request.Request(PUSHPLUS_API, data=_body, headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(_req, timeout=15).read()
    except Exception:
        pass


def _diag_append(line):
    """warn 排障诊断：追加一行到 tools/data/warn_diag.txt（云端 run 持久化会提交回仓库）。
    文件不存在则创建；目录不存在自动建。"""
    try:
        os.makedirs(os.path.dirname(_WARN_DIAG), exist_ok=True)
        with open(_WARN_DIAG, 'a', encoding='utf-8') as f:
            f.write(datetime.now().strftime('%H:%M:%S') + ' ' + line + chr(10))
    except Exception:
        pass


def get_news(n=15):
    """全市场新闻（多源，任一出数即返回）：
    主源=东财7x24快讯老接口（newsapi /getlist_102_ajaxResult，LivesList）；
    备源=新浪7x24滚动（feed.mix.sina.com.cn/api/roll，result.data）。
    两源都失败才返回 []（调用方按"无有效新闻"处理，不伪造）。"""
    # 源1：东财 7x24 老接口（新接口 np-listapi 需 sortEnd 且仍 data=null，弃用）
    try:
        u = 'https://newsapi.eastmoney.com/kuaixun/v1/getlist_102_ajaxResult_50_1_.html'
        r = _get(u)
        txt = r[r.find('{'):]
        d = json.loads(txt)
        lst = d.get('LivesList') or []
        if lst:
            out = []
            for i, x in enumerate(lst[:n]):
                title = re.sub(r'<[^>]+>', '', x.get('title') or '')
                digest = re.sub(r'<[^>]+>', '', x.get('digest') or '')
                out.append({'id': str(x.get('newsid') or x.get('id') or i),
                            'title': title.strip(),
                            'summary': digest.strip(),
                            'ts': x.get('showtime', '')})
            return out
    except Exception as _e:
        print(f'[news] 源1东财失败: {type(_e).__name__} {str(_e)[:60]}')
        _diag_append('[get_news] 源1东财失败: %s %s' % (type(_e).__name__, str(_e)[:60]))
        _WARN_DIAG_LINES.append('源1东财失败:%s' % str(_e)[:50])
    # 源2：新浪 7x24 滚动
    try:
        u = 'https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=%d&page=1' % n
        d = json.loads(_get(u))
        data = d.get('result', {}).get('data') or []
        if data:
            out = []
            for i, x in enumerate(data[:n]):
                ct = x.get('ctime')
                ts = datetime.fromtimestamp(int(ct)) if ct else None
                out.append({'id': str(x.get('docid') or i),
                            'title': (x.get('title') or '').strip(),
                            'summary': (x.get('summary') or '').strip(),
                            'ts': ts.strftime('%Y-%m-%d %H:%M:%S') if ts else ''})
            return out
    except Exception as _e:
        print(f'[news] 源2新浪失败: {type(_e).__name__} {str(_e)[:60]}')
        _diag_append('[get_news] 源2新浪失败: %s %s' % (type(_e).__name__, str(_e)[:60]))
        _WARN_DIAG_LINES.append('源2新浪失败:%s' % str(_e)[:50])
    # 源3：新浪财经7x24直播（zhibo 接口，结构 result.data.feed.list）
    try:
        u = 'https://zhibo.sina.com.cn/api/zhibo/feed?page=1&page_size=%d&zhibo_id=152&tag_id=0&dire=f&dpc=1' % n
        d = json.loads(_get(u))
        lst = d.get('result', {}).get('data', {}).get('feed', {}).get('list') or []
        if lst:
            out = []
            for i, x in enumerate(lst[:n]):
                rich = x.get('rich_text') or ''
                txt = re.sub(r'<[^>]+>', '', rich).strip()
                t2 = x.get('title') or ''
                if not txt and t2:
                    txt = t2.strip()
                if txt:
                    out.append({'id': str(x.get('id') or i),
                                'title': txt[:80],
                                'summary': txt[:90],
                                'ts': x.get('create_time', '')})
            if out:
                return out
    except Exception as _e:
        print(f'[news] 源3新浪直播失败: {type(_e).__name__} {str(_e)[:60]}')
    return []


HOT_KW = ['政策', '批复', '规划', '中标', '签约', '重组', '收购', '突破', '首发',
          '业绩', '涨价', '补贴', '降息', '降准', '会议', '印发', '支持', '涨停', '获批']


def news_drive(news, d, mem):
    """新闻发酵：高权重 + 命中题材/个股，返回 [{title, sec, leaders, merged}]。"""
    out = []
    today_sec = list(d['sectors'].keys())
    for nw in news[:15]:
        text = nw['title'] + nw['summary']
        hot = any(k in text for k in HOT_KW)
        hit_sec = next((s for s in today_sec if s in text), None)
        hit_hold = next((h['name'] for h in HOLDINGS if h['name'] in text), None)
        if not (hot or hit_sec or hit_hold):
            continue
        # 历史强势股
        old = []
        for days in list(mem.values())[-5:]:
            for sec, info in days.items():
                if (hit_sec and sec == hit_sec) or (hit_hold and hit_hold in info.get('leaders', [])):
                    old = info.get('leaders', [])
        merged = bool(hit_sec and d['sectors'].get(hit_sec))  # 有价格反应=合并
        sec = hit_sec or (hit_hold + '(个股)') if hit_hold else (hit_sec or '宏观/全市场')
        out.append({'title': nw['title'], 'sec': sec,
                    'leaders': old, 'merged': merged, 'hot': hot})
    return out


BEAR_KW = ['处罚', '立案', '大跌', '收紧', '被罚', '退市', '减持', '调查', '下跌', '暴雷', '违约']
BULL_KW = ['支持', '批复', '中标', '降息', '降准', '突破', '签约', '补贴', '利好', '增长', '上涨', '获批', '印发', '规划', '合作']


def classify_news(text):
    if '不减持' in text or ('承诺' in text and '不减持' in text):
        return '利好', RED  # 不减持承诺=减少抛压，先于'减持'判定
    if any(k in text for k in BEAR_KW):
        return '利空', GREEN
    if any(k in text for k in BULL_KW):
        return '利好', RED
    return '中性', GREY


# ============ 事件驱动量化层（Event Intelligence，2026-11-05 券商量化机构配置） ============
# 新闻强度分级(S/A/B/C) + 时间衰减 + 板块事件热度聚合 + 预期差标记。纯计算，不耗 LLM。
# S=重大(政策/规划/宏观/大厂重磅) A=产业催化(涨价/订单/量产/补贴) B=公司公告(业绩/回购/中标) C=一般
_EV_S_KW = ['国常会', '国务院', '发改委', '央行', '证监会', '降准', '降息', 'LPR', '印发', '规划', '规划纲要',
            '重大突破', '重组', '并购', '收购', '首发', '全球首', '量产', '大基金', '专项债', '万亿', '白名单',
            '座谈会', '一号文', '试点', '挂牌', '上市', '退市新规']
_EV_A_KW = ['涨价', '提价', '上调', '补贴', '中标', '订单', '签约', '招标', '装机', '并网', '招标公告',
            '预增', '增持', '回购', '业绩', '净利', '同比', '扩产', '投产', '交付', '出口', '涨超', '创新高']
_EV_B_KW = ['公告', '披露', '协议', '合作', '合资', '入股', '注册', '获批', '许可', '通过', '验收', '下线']
# 情绪加分词（在 classify_news 基础上加程度）
_EV_SENT_UP = ['超预期', '大幅', '首个', '首次', '创纪录', '历史新高', '全面', '重磅', '重大', '顶格', '翻倍', '突破']
_EV_SENT_DN = ['不及预期', '下滑', '亏损', '处罚', '立案', '调查', '退市', '暴雷', '违约', '下调', '收紧', '清仓']


def _ev_ts_min(ts):
    """新闻时间戳 → 分钟级 datetime；解析失败返回 None。"""
    if not ts:
        return None
    s = str(ts).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def _ev_sec(text):
    """新闻文本 → 板块题材。细粒度 _EVENT_SEC_MAP 优先（数据中心/存储/低空等专词），
    NEWS_THEME_MAP 兜底（泛板块）。未命中返回 ''。"""
    for k, sec in _EVENT_SEC_MAP:
        if k in text:
            return sec
    for kws, sec, _stocks, _plain in NEWS_THEME_MAP:
        if any(k in text for k in kws):
            return sec
    return ''


def _score_event(nw, now=None):
    """单条事件评分：返回 dict(score, level, sent, sec, age_h)。
    score = 强度基数 × 情绪符号 × 时间衰减(exp(-age_h/6))，保留1位。"""
    text = (nw.get('title') or '') + ' ' + (nw.get('summary') or '')
    if '注册资本' in text or '工商变更' in text or '经营范围' in text:
        if not any(k in text for k in ('业绩', '净利', '订单', '中标', '重组')):
            return None  # 注册类噪音直接丢弃
    if any(k in text for k in _EV_S_KW):
        base, level = 10, 'S'
    elif any(k in text for k in _EV_A_KW):
        base, level = 7, 'A'
    elif any(k in text for k in _EV_B_KW):
        base, level = 4, 'B'
    else:
        base, level = 1, 'C'
    tag, _ = classify_news(text)
    # 利空否定覆盖（券商级语义修正）：文本出现强利空语义词时，即使命中利好关键词也按利空计
    # （如「客单价下降/销量下滑」文本含"增长"字样会被 classify_news 误判利好）
    _EV_NEG_COVER = ['下降', '下滑', '回落', '下跌', '亏损', '处罚', '立案', '调查', '退市',
                     '暴雷', '违约', '收紧', '下调', '减少', '降价', '承压', '放缓', '都降了']
    if any(k in text for k in _EV_NEG_COVER):
        _neg_strength = any(k in text for k in ('大幅', '超预期', '清仓', '顶格', '超50%', '腰斩'))
        if _neg_strength or tag != '利好':
            sign = -2 if _neg_strength else -1
        else:
            sign = -1  # 文本同时有"增长"和"下降"（如"增速下滑"）→ 按利空处理
    elif tag == '利好':
        sign = 2 if any(k in text for k in _EV_SENT_UP) else 1
    elif tag == '利空':
        sign = -2 if any(k in text for k in _EV_SENT_DN) else -1
    else:
        sign = 0
    now = now or _bj_now()
    dt = _ev_ts_min(nw.get('ts'))
    if dt:
        age_h = max((now - dt).total_seconds() / 3600.0, 0.0)
    else:
        age_h = 0.0
    w = 2.718281828 ** (-age_h / 6.0)
    return {'score': round(base * sign * w, 1), 'level': level, 'sent': sign,
            'sec': _ev_sec(text), 'age_h': round(age_h, 1)}


def _event_intel(news, top=5, new_min=60):
    """时事情报包（紧跟时事核心）：
      mainlines: 板块事件热度 Top3（事件数/净情绪/最新时间/代表标题/是否已定价）
      top_events: 全市场事件评分 Top5
      overnight: 隔夜(昨日15:00后)重大事件标题
      new_1h: 过去 new_min 分钟新事件标题（盘中跟突发用）
    """
    scored = []
    now = _bj_now()
    for nw in news:
        ev = _score_event(nw, now)
        if ev is None:
            continue
        ev['title'] = nw.get('title') or ''
        ev['ts'] = nw.get('ts') or ''
        scored.append(ev)
    scored.sort(key=lambda x: -x['score'])
    # 板块事件热度聚合（只用 情绪非中性 且 有板块 的事件；C级不计入热度避免噪音）
    sec_stat = {}
    for ev in scored:
        if ev['sent'] == 0 or not ev['sec'] or ev['level'] == 'C':
            continue
        st = sec_stat.setdefault(ev['sec'], {'n': 0, 'net': 0.0, 'latest': ev['ts'], 'tops': []})
        st['n'] += 1
        st['net'] += ev['score']
        if ev['ts'] > st['latest']:
            st['latest'] = ev['ts']
        if len(st['tops']) < 3:
            st['tops'].append(ev['title'][:42])
    mainlines = []
    for sec, st in sorted(sec_stat.items(), key=lambda kv: (-kv[1]['net'], -kv[1]['n']))[:3]:
        mainlines.append({'sec': sec, 'n': st['n'], 'net': round(st['net'], 1),
                          'latest': st['latest'], 'tops': st['tops']})
    top_events = []
    for ev in scored[:top]:
        top_events.append({'title': ev['title'][:60], 'ts': ev['ts'], 'level': ev['level'],
                           'sec': ev['sec'], 'sent': ev['sent'], 'score': ev['score']})
    # 隔夜情报：昨日 15:00 之后的 S 级或 |sent|>=2 事件（盘前紧跟隔夜大事）
    overnight = []
    for ev in scored:
        if ev['sent'] == 0:
            continue
        dt = _ev_ts_min(ev['ts'])
        if dt and (dt.hour >= 15 or dt.date() < now.date()):
            if ev['level'] == 'S' or abs(ev['sent']) >= 2:
                overnight.append(ev['title'][:50])
    # 过去 new_min 分钟新事件（盘中跟突发）
    new_1h = []
    for ev in scored:
        if ev['sent'] == 0:
            continue
        dt = _ev_ts_min(ev['ts'])
        if dt and (now - dt).total_seconds() <= new_min * 60:
            new_1h.append('[' + ev['level'] + '] ' + ev['title'][:48])
    return {'mainlines': mainlines, 'top_events': top_events,
            'overnight': overnight[:6], 'new_1h': new_1h[:6]}


# ============ 休市日新闻汇总（2026-10-19 新增） ============
# 关键词 → (板块/题材, 相关个股示例, 大白话一句话)。纯规则匹配，不调 LLM、不编造；
# 未命中映射表的新闻不标注板块（仅在有可靠依据时标注）。
NEWS_THEME_MAP = [
    (['降准', '降息', 'MLF', '逆回购'], '金融/地产', '银行、券商、地产链', '资金面宽松，利好金融和地产链条'),
    (['光伏', '组件', '硅料', '逆变器', 'TOPCon'], '光伏', '隆基绿能、通威股份、阳光电源', '光伏产业链有消息刺激'),
    (['锂电', '电池', '碳酸锂', '储能', '固态电池'], '锂电/储能', '宁德时代、亿纬锂能', '新能源电池方向受到关注'),
    (['半导体', '芯片', '晶圆', '光刻', '集成电路', '封测'], '半导体', '中芯国际、北方华创', '半导体产业链有催化'),
    (['AI', '人工智能', '大模型', '算力', '机器人', '智能体'], 'AI/算力', '科大讯飞、中际旭创', 'AI 相关方向热度高'),
    (['军工', '国防', '航空', '航天', '无人机'], '军工', '中航沈飞、航发动力', '军工方向有事件催化'),
    (['医药', '创新药', '疫苗', '集采', '医疗器械', '生物'], '医药', '恒瑞医药、药明康德', '医药板块有政策或事件'),
    (['汽车', '新能源车', '整车', '智能驾驶', '充电'], '汽车', '比亚迪、长安汽车', '汽车产业链受关注'),
    (['地产', '房地产', '楼市', '房贷', '城中村'], '地产', '保利发展、万科A', '地产链有政策信号'),
    (['基建', '水利', '铁路', '工程', '一带一路'], '基建', '中国建筑、中国中铁', '基建投资方向有动作'),
    (['消费', '白酒', '家电', '零售', '旅游', '免税'], '消费', '贵州茅台、美的集团', '大消费方向有催化'),
    (['煤炭', '石油', '油气', '天然气', '原油'], '能源', '中国神华、中国石油', '能源资源方向受关注'),
    (['黄金', '白银', '有色', '铜', '稀土'], '有色/贵金属', '紫金矿业、山东黄金', '有色金属价格或政策相关'),
    (['证券', '券商', '投行'], '券商', '中信证券、东方财富', '券商板块情绪相关'),
    (['银行', '信贷', '存款', '净息差'], '银行', '招商银行、工商银行', '银行板块消息'),
    (['消费电子', '苹果', '折叠屏', 'PCB'], '消费电子', '立讯精密、歌尔股份', '消费电子新品或供应链消息'),
    (['航运', '集装箱', '港口'], '航运港口', '中远海控、上港集团', '航运港口方向有变化'),
    (['农业', '粮食', '种业', '养殖', '猪'], '农业', '牧原股份、隆平高科', '农业板块有消息'),
]


def news_tags(title, summary):
    """休市日新闻的板块题材标注：返回 (板块/题材, 相关个股示例, 大白话)。无命中返回 (None, None, None)。"""
    text = title + ' ' + summary
    for kws, sector, stocks, plain in NEWS_THEME_MAP:
        if any(k in text for k in kws):
            return sector, stocks, plain
    return None, None, None


# 新闻事件 → 板块影响映射（按关键词命中，映射不到则如实写“暂看不出直接板块影响”）
_EVENT_SEC_MAP = [
    ('芯片', '半导体'), ('半导体', '半导体'), ('光刻', '半导体设备'), ('存储', '存储芯片'),
    ('AI', 'AI算力'), ('算力', 'AI算力'), ('大模型', 'AI应用'), ('机器人', '机器人'),
    ('新能源', '新能源'), ('光伏', '光伏'), ('锂电', '锂电'), ('电池', '锂电'),
    ('储能', '储能'), ('智能驾驶', '智能驾驶'), ('汽车', '汽车链'),
    ('创新药', '创新药'), ('医药', '医药'), ('中药', '中药'), ('医疗', '医疗器械'),
    ('白酒', '白酒'), ('消费', '消费'), ('旅游', '旅游'), ('酒店', '酒店餐饮'),
    ('券商', '券商'), ('银行', '银行'), ('保险', '保险'), ('地产', '地产'),
    ('基建', '基建'), ('工程', '基建'), ('中标', '基建/工程'), ('钢铁', '钢铁'),
    ('有色', '有色'), ('煤炭', '煤炭'), ('石油', '石油'), ('化工', '化工'),
    ('军工', '军工'), ('航天', '航天'), ('卫星', '卫星'), ('消费电子', '消费电子'),
    ('面板', '面板'), ('软件', '软件'), ('数据要素', '数据要素'), ('数据中心', '数据中心'),
    ('通信', '通信设备'), ('低空经济', '低空经济'), ('商业航天', '航天'), ('核电', '核电'),
    ('氢能', '氢能'), ('风电', '风电'), ('预增', '业绩预增股'), ('业绩', '业绩股'),
    ('回购', '回购概念'), ('增持', '增持概念'), ('减持', '减持利空'),
    ('降准', '银行/流动性'), ('降息', '银行/流动性'), ('LPR', '银行/流动性'),
]


def _brief_deep(items):
    """事件简报·大白话五步深挖：对已筛事件批量 LLM 生成五要素。失败返回 {}（调用方用原模板兜底）。"""
    if not items or not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return {}
    evs = '\n'.join(f"- {x['title']}（标签：{x['tag']}）" for x in items[:15])
    fmt = ('你是一线游资。以下是一批市场事件，做成「事件汇总」：有多少写多少，每条按主力意图拆解，不许偷懒、不许漏条：\n'
           '【第一步·先看筹码后说话】先把事实说清，并判断是主力真催化还是借题出货。\n'
           '【第二步·问三个主力问题】①主力为什么动/会不会动；②跟我什么关系；③主力下一步想干什么。\n'
           '【第三步·翻译成人话】用游资黑话，结论先行+动作可执行。\n'
           '【第四步·套游资纪律】高位连板不接飞刀，无建仓痕迹只看戏。\n'
           '【第五步·自查】说机会必须带主力出货信号。\n'
           '事件列表：\n' + evs + '\n'
           '只输出 JSON，不要任何其他文字：\n'
           '{"items":[{"t":"事件标题（照抄原文）","good":"利好哪个板块/题材/个股+主力可能怎么做，至少12字（无明显利好写「无明显直接利好」）；如果提到个股，必须执行「股票深挖铁律」：本质一句话+暗线业务（写不出写「未见明确暗线业务」）+真实关联与弹性","bad":"利空哪个板块/题材/个股+主力可能怎么跑，至少12字（无明显利空写「无明显直接利空」）；如果提到个股，同样执行深挖铁律","logic":"逻辑原因：主力意图深挖，至少25字","why":"大白话：一句话戳穿真假+怎么应对，至少22字","act":"操作：必须执行深挖铁律——有硬逻辑的具体股票才写（股票名+代码+本质+暗线业务+买点/止损/仓位），没有硬逻辑就写「无明确可操作标的」，绝不硬凑"}]}，【单边定性铁律】同一条事件 good 与 bad 必须二选一，禁止又✅又⚠️。必须覆盖每条事件。')
    t = ask_deepseek({'task': 'event_brief', 'events': [x['title'] for x in items[:6]],
                      'format': fmt}, purpose='brief')
    for _try in range(2):
        if not t:
            break
        try:
            _j0 = json.loads(t)
        except Exception:
            break
        _bad = [it for it in (_j0.get('items') or []) if len(str(it.get('logic') or '')) < 25 or len(str(it.get('why') or '')) < 22]
        if not _bad:
            break
        t = ask_deepseek({'task': 'event_brief', 'events': [x['title'] for x in items[:6]],
                          'format': fmt + f'上次有{len(_bad)}条字数不达标（如{_bad[0].get("t", "")}），重写：logic≥25字、why≥22字、act≥20字，禁止敷衍！'},
                         purpose='brief_retry')
    out = {}
    if not t:
        return out
    try:
        _j = json.loads(t)
        for it in _j.get('items') or []:
            tt = str(it.get('t') or '').strip()
            if tt and (it.get('logic') or it.get('why')):
                out[tt] = {'good': str(it.get('good') or ''),
                           'bad': str(it.get('bad') or ''),
                           'logic': str(it.get('logic') or ''),
                           'why': str(it.get('why') or ''),
                           'act': str(it.get('act') or '')}
    except Exception:
        pass
    return out


def _brief_summary(items):
    """事件简报·顶部大白话汇总V3（游资降维：精准映射板块/个股/买卖点）。失败返回''。"""
    if not items or not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return ''
    evs = '\n'.join(f"- 【{x['tag']}】{x['title']}（影响：{x['rel']}）" for x in items[:20])
    sys_text = '''你是深谙A股游资与主力资金运作的一线游资操盘手，擅长把宏观新闻精准降维成具体交易指令。
下面是今日事件简报（每条已标【利好】【利空】【中性】）。把新闻精准映射到【具体板块/题材】、【核心个股/平替个股】、【具体买卖点】。
不要笼统说「看好半导体」「看空金融」，直接给操作剧本，大白话，不讲虚的。
### 拆解规则
1. 利好信息的精准打击：
- 【明牌龙头】：新闻直接点名的板块龙头，如果已经涨停或大涨，明确告知「买不到，不追」。
- 【细分暗线与平替】：顺着利好判断哪个细分最受益，指出可操作方向（优先有前期建仓痕迹的）。
- 【个股与操作】：推荐1-2只「容量中军」或「低位补涨」特征的个股，必须有建仓痕迹或筹码优势，结合突破回踩体系给操作：等缩量回踩均价线低吸，或放量突破平台半路扫，并写清防守底线。【深挖铁律·每只票必做】完整输出六要素：本质（一句话大白话，禁标签糊弄）+暗线业务（具体产品+进展阶段+对业绩真实贡献，挖不出写「未见明确暗线业务」，禁「相关/涉及/布局/受益于」糊弄）+真实关联与弹性（实受益/沾边/纯蹭，弹性大不大）+为什么是它+破灭点（逻辑什么时候破，必写）+动作（价位/量能触发条件+失效条件）。逻辑不硬就写「今日无买点」，绝不硬推。输出前先自问：如果不推这只票，最硬的理由是什么？
2. 利空信息的排雷避险：
- 【危险板块】：新闻打击的具体板块/题材。
- 【个股与操作】：指出哪些高位票或资金正在出逃的个股必须立刻规避，手里有的怎么处理（竞价核按钮/盘中反抽止损）。
3. 中性信息防忽悠：识别看似利好实则「借消息出货」的新闻，大白话点破。
### 输出格式（连贯陈述，绝不分栏）
必须写成三段连贯的话，每段开头加编号「01」「02」「03」，段与段之间空一行。
1. 绝对禁止「- 题材细分 / - 明面龙头 / - 实战标的 / - 怎么买」这类子项清单，绝对禁止【】标签，绝对禁止问号或设问句。
2. 01 段：一句话定调今天的方向，接着说清这条利好到底落在哪个细分、哪只票是真受益、为什么是它、什么价位和什么量能才动手、跌破哪里就撤。
3. 02 段：说清利空打在哪个板块、哪类票最危险、手里有的怎么处理、反抽到哪个位置必须清。
4. 03 段：说清哪个消息是假利好（看似利好实则借消息出货），真正的暗线落在哪只票上、它到底做什么生意、对业绩有没有真实贡献、逻辑什么时候破。
5. 每段不超过 5 句，用长句顺下来，单只票的深挖铁律全部揉进句子内部讲完，不要拆成条目。
要求：必须绑定上面输入新闻的具体内容；禁止空话套话；没有价格数据时写「待盘中确认」，不许硬编价位；禁止把推测当已核实事实。'''
    fmt = ('以下是今日事件清单（每条含标签与影响板块）：\n' + evs + '\n'
           '严格按系统提示词输出：只写三段连贯的话，每段开头加编号「01」「02」「03」'
           '（01=利好落在哪个细分和哪只票，02=利空打在哪类票、手里有的怎么跑，03=假利好与真正的暗线）。'
           '绝对不要子项清单、不要【】标签、不要问号、不要「题材细分/明面龙头/怎么买」这类小标题，'
           '直接输出连贯段落，不要JSON、不要任何额外说明。'
           '先利好后利空，把最重要的结论放前面。')
    t = ask_deepseek({'task': 'event_summary_v3', 'events': [x['title'] for x in items[:20]],
                      'format': fmt}, purpose='brief_summary_v3', system_text=sys_text)
    if not t or len(t.strip()) < 60:
        return ''
    import html as _h
    _badges = [('01', GOLD), ('02', RED), ('03', GREEN), ('04', '#ffd666')]
    parts = []
    for ln in t.strip().split('\n'):
        ln = ln.strip()
        if not ln:
            continue
        e = _h.escape(ln)
        _num, _numc = '', GREY
        for _n, _c in _badges:
            if _n in ln[:6]:
                _num, _numc = _n, _c
                ln = ln.replace(_n, '', 1).strip()
                e = _h.escape(ln)
                break
        if '【今日核心大方向】' in ln:
            parts.append('<div style="color:' + GOLD + ';font-size:14px;font-weight:900;margin-top:8px;">🧭 ' + e + '</div>')
        elif '🔥' in ln:
            parts.append('<div style="color:' + RED + ';font-size:14px;font-weight:900;margin-top:10px;">🔥 ' + e.replace('🔥', '').strip() + '</div>')
        elif '💣' in ln:
            parts.append('<div style="color:' + GREEN + ';font-size:14px;font-weight:900;margin-top:10px;">💣 ' + e.replace('💣', '').strip() + '</div>')
        elif '💡' in ln:
            parts.append('<div style="color:#ffd666;font-size:14px;font-weight:900;margin-top:10px;">💡 ' + e.replace('💡', '').strip() + '</div>')
        elif ln.startswith('-'):
            parts.append('<div style="color:#cfd6e4;font-size:13px;margin-top:3px;margin-left:6px;">' + e + '</div>')
        else:
            parts.append('<div style="color:#e9ecef;font-size:13px;margin-top:3px;">' + e + '</div>')
    body = ''.join(parts)
    return ('<div style="background:#17212b;border:2px solid ' + GOLD + ';border-radius:12px;padding:12px 14px;margin:10px 0;">'
            '<div style="font-size:15px;font-weight:900;color:' + GOLD + ';">🧭 今日实战速览（游资降维版）</div>'
            '<div style="line-height:1.7;">' + body + '</div></div>')


# ============ 工单13：事件加减分层（独立于量价因子） ============
_EVT_RULES = (
    (('回购', '增持'), 5, '公司自己掏钱买'),
    (('业绩预增', '预增', '净利润同比增长', '扭亏为盈', '同比大增'), 4, '业绩落地'),
    (('减持', '拟减持'), -8, '股东要卖'),
    (('解禁', '限售股上市流通', '限售股解禁'), -5, '筹码要放出来'),
    (('大宗交易', '折价成交', '折价转让'), -4, '折价甩货'),
    (('中标', '签订合同', '签署合同', '新签订单'), 3, '订单落地'),
    (('立案', '行政处罚', '违规', '问询函'), -6, '监管风险'),
    (('终止减持', '不减持', '终止回购'), 0, '撤回原计划'),
)


def _event_layer(rows, limit=6):
    """从新闻/公告标题里抽事件，给方向与加减分（工单13）。
    返回 [{'title','kind','delta','why','ts'}]；没有命中返回 []。"""
    out = []
    seen = set()
    for r in (rows or []):
        _title = str(r.get('title') or '')
        _text = _title + ' ' + str(r.get('summary') or '')
        if len(_text.strip()) < 8:
            continue
        _key = _title[:16]
        if _key in seen:
            continue
        for _kws, _delta, _why in _EVT_RULES:
            if not any(k in _text for k in _kws):
                continue
            if _delta == 0:
                # 终止/不减持这类撤回消息：单独标注，不参与加减分
                out.append({'title': _title[:40], 'kind': '撤回', 'delta': 0,
                            'why': _why, 'ts': r.get('ts') or ''})
                seen.add(_key)
                break
            # “拟减持但终止”不扣分
            if _delta < 0 and ('终止' in _text or '不减持' in _text or '取消' in _text):
                break
            out.append({'title': _title[:40], 'kind': _kws[0], 'delta': _delta,
                        'why': _why, 'ts': r.get('ts') or ''})
            seen.add(_key)
            break
        if len(out) >= limit:
            break
    return out


def _event_line_html(evs, limit=4):
    """「事件提醒」行：只列方向与分数，不绑定个股。"""
    if not evs:
        return ''
    _rows = ''
    for e in evs[:limit]:
        _d = int(e.get('delta') or 0)
        _c = TEAL if _d > 0 else (RED if _d < 0 else GREY)
        _s = ('+%d' % _d) if _d > 0 else ('%d' % _d if _d < 0 else '±0')
        _rows += ('<div style="color:#ced4da;font-size:12px;margin-top:2px;">'
                  '<span style="color:' + _c + ';font-weight:800;">' + str(e.get('kind') or '') + _s + '</span> '
                  + str(e.get('title') or '')[:34]
                  + '<span style="color:' + GREY + ';">（' + str(e.get('why') or '') + '）</span></div>')
    return ('<div style="background:#1c2230;border-left:4px solid ' + GOLD + ';border-radius:8px;padding:8px 10px;margin:6px 0;">'
            '<div style="font-size:12px;font-weight:800;color:' + GOLD + ';">📋 事件提醒（独立于量价的加减分）</div>'
            + _rows + '</div>')


def build_events(slot, news=None):
    """早盘/午间/尾盘事件精华。slot=pre/noon/eod。"""
    news = news if news is not None else get_news(30)
    mem = load_memory()
    days = sorted(mem.keys(), reverse=True)
    out = []
    seen = set()
    for nw in news:
        text = nw['title'] + nw['summary']
        if len(text) < 12:
            continue
        tag, color = classify_news(text)
        # 关联板块/个股（昨日强势题材 > 行业关键词映射 > 如实兜底）
        rel = []
        for pd in days[:3]:
            for sec, info in mem.get(pd, {}).items():
                if sec in text:
                    rel.append(sec + '(龙头:' + '/'.join(info['leaders'][:2]) + ')')
        if not rel:
            for kw, bd in _EVENT_SEC_MAP:
                if kw in text:
                    rel.append(bd)
                    break
        rel_s = '、'.join(rel[:3]) or '暂看不出直接板块影响'
        out.append({'tag': tag, 'color': color, 'title': nw['title'][:60],
                    'time': (nw.get('ts') or '')[-8:-3] or '', 'rel': rel_s})
    # —— 事件简报改版（11-05 指令④）：按利好→利空→中性排序（段落排序），最多12条（内容紧密）——
    _pri = {'利好': 0, '重大利好': 0, '正面': 0, '政策利好': 0, '中性': 2, '利空': 1, '重大利空': 1, '负面': 1, '风险提示': 1}
    out.sort(key=lambda x: (_pri.get(x['tag'], 2), x['time'] or ''))
    out = out[:12]
    if not out:
        return ''
    _sum_html = _brief_summary(out)      # 顶部大白话汇总（做减法+实战映射）
    try:
        _evt_html = _event_line_html(_event_layer(news))
    except Exception as _ee:
        print('[event] 事件分层异常:', _ee)
        _evt_html = ''
    cards = []
    for i, x in enumerate(out, 1):
        cards.append(f"""<div style="background:#1f2635;border-left:4px solid {x['color']};border-radius:10px;padding:7px 11px;margin:5px 0;display:flex;gap:8px;align-items:flex-start;">
<div style="flex:0 0 auto;min-width:22px;height:22px;line-height:22px;text-align:center;border-radius:50%;background:{x['color']}22;color:{x['color']};font-weight:900;font-size:11px;margin-top:1px;">{i:02d}</div>
<div style="flex:1 1 auto;min-width:0;">
<div style="color:#fff;font-size:13px;line-height:1.5;"><span style="font-weight:800;color:{x['color']};">{x['tag']}</span>　{x['title']}</div>
<div style="color:{GREY};font-size:12px;margin-top:2px;">{x['time'] or ''}｜影响：{x['rel']}</div></div></div>""")
    cards = ''.join(cards)
    head = {'pre': '📰 早盘事件汇总', 'noon': '📰 午间事件汇总', 'eod': '📰 尾盘事件汇总'}[slot]
    # 写入事件日志
    try:
        log = os.path.join(os.path.dirname(ALERT_PATH), 'events.json')
        data = {}
        if os.path.exists(log):
            with open(log, encoding='utf-8') as f:
                data = json.load(f)
        data.setdefault(datetime.now().strftime('%Y-%m-%d'), []).extend([x['title'] for x in out])
        with open(log, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    return f'<div style="margin-top:12px;font-size:15px;font-weight:800;color:{GOLD};">{head}</div>{_sum_html}{_evt_html}{cards}'


# ============ 量化评分 ============
def market_score(idx, d):
    """市场状态评分 0-100。"""
    avg = sum(x['pct'] for x in idx) / len(idx) if idx else 0
    zbr = d['zb'] / (d['lu'] + d['zb']) if (d['lu'] + d['zb']) else 0.5
    s = 50
    s += min(20, d['lu'] * 0.3)
    s += max(-20, -zbr * 40)
    s += max(-15, min(15, avg * 8))
    top = len(d['tops'][0][1]) if d['tops'] else 0
    s += min(10, top)
    s = max(0, min(100, s))
    if s >= 70:
        label, why = '主线持续', '涨停多、炸板低、指数强，资金集中在主线'
    elif s >= 55:
        label, why = '震荡分化', '有方向但不集中，挑着做'
    elif s >= 40:
        label, why = '快速轮动', '涨停一般，资金到处试，仓位要轻、止损要严'
    else:
        label, why = '情绪退潮', '炸板高/涨停少/指数弱，不新开仓'
    return round(s, 1), label, why


def _risk_engine(d, idx=None):
    """盘中风险体检引擎（纯规则、零 LLM、符合 DS_DAILY_LIMIT 预算）：
    炸板率/连板高度/跌停数/涨停数/指数破位/情绪降幅 → 风险分0-100 + 等级 + 动作。
    返回 {'level','score','act','evid',...} 或 {}（数据不可得/异常）。"""
    try:
        lu = int(d.get('lu') or 0)
        zb = int(d.get('zb') or 0)
        dt = int(d.get('dt') or 0)
        max_lbc = int(d.get('max_lbc') or 0)
        # 三池全空 = 接口失败/非交易日，静默（不推送误报）
        if lu == 0 and zb == 0 and dt == 0 and max_lbc == 0:
            return {}
        zbr = (zb / (lu + zb) * 100) if (lu + zb) else 0.0
        evid, score = [], 0
        # 炸板率（打板资金退潮核心指标）
        if zbr >= 45:
            score += 40; evid.append(f'炸板率{zbr:.0f}%（≥45%）高位——打板资金退潮，追高容易被砸')
        elif zbr >= 35:
            score += 30; evid.append(f'炸板率{zbr:.0f}%（35~45%）——资金追高意愿明显转弱')
        elif zbr >= 28:
            score += 18; evid.append(f'炸板率{zbr:.0f}%（28~35%）——分歧加大')
        elif zbr >= 25:
            score += 12; evid.append(f'炸板率{zbr:.0f}%（25~28%）——承接转弱')
        # 连板高度（题材梯队）
        if max_lbc <= 1 and lu >= 30:
            score += 16; evid.append(f'最高仅{max_lbc}板，无高度——纯情绪轮动，隔日难有溢价')
        elif max_lbc <= 2:
            score += 8; evid.append(f'连板高度仅{max_lbc}板，题材无龙头梯队')
        # 跌停扩散（亏钱效应）
        if dt >= 30:
            score += 40; evid.append(f'跌停{dt}家（≥30）——恐慌扩散，资金夺路')
        elif dt >= 15:
            score += 28; evid.append(f'跌停{dt}家（15~30）——亏钱效应显现')
        elif dt >= 8:
            score += 16; evid.append(f'跌停{dt}家（8~15）——亏钱效应抬头')
        # 涨停匮乏（情绪冰点）
        if lu < 30 and dt >= 8:
            score += 20; evid.append(f'涨停仅{lu}家——情绪冰点，赚钱效应枯竭')
        elif lu < 40:
            score += 8; evid.append(f'涨停{lu}家偏少')
        # 指数破位
        if idx:
            avg = (sum(float(x.get('pct') or 0) for x in idx) / len(idx)) if idx else 0
            if avg <= -2.0:
                score += 32; evid.append(f'指数平均{avg:+.1f}% 深度破位——系统性风险窗口')
            elif avg <= -1.5:
                score += 24; evid.append(f'指数平均{avg:+.1f}% 破位下杀')
            elif avg <= -0.8:
                score += 16; evid.append(f'指数平均{avg:+.1f}% 转弱')
            elif avg >= 0.8:
                score -= 6
        # 情绪降幅（对比昨日涨停家数账本）
        try:
            mem = load_memory()
            days = sorted(mem.keys())
            if days:
                prev = mem.get(days[-1], {}) or {}
                prev_zt = sum(float(v) for v in prev.values() if isinstance(v, (int, float)))
                if prev_zt >= 30 and lu < prev_zt * 0.6:
                    score += 12; evid.append(f'涨停{lu}家 &lt; 昨日{prev_zt:.0f}家的60%——情绪退潮加速')
        except Exception:
            pass
        score = max(0, min(100, score))
        if score >= 65:
            level, act = '红', '红档·防守级'
        elif score >= 45:
            level, act = '橙', '橙档·降仓级'
        elif score >= 25:
            level, act = '黄', '黄档·谨慎级'
        else:
            level, act = '绿', '绿档·常规级'
        return {'level': level, 'score': score, 'act': act, 'evid': evid,
                'lu': lu, 'zb': zb, 'dt': dt, 'zbr': zbr, 'max_lbc': max_lbc}
    except Exception:
        return {}


def mainline_health(idx, d, fin, fout):
    """主线健康度 0-100（连续性25/龙头封板20/昨日溢价20/资金持续20/炸板率15）。
    无历史账本处如实用当日近似并注明，不伪造。
    返回 (score, label, aggr, subs)。label：主线仍强/开始分化/即将退潮。"""
    mem = load_memory()
    days = sorted(mem.keys(), reverse=True)
    prev2 = set()
    for pd in days[1:3]:
        prev2 |= set(mem.get(pd, {}).keys())
    top_sec = d['tops'][0][0] if d['tops'] else ''
    # 连续性：最强板块近3日是否连续活跃（家数趋势以"是否连续进入记忆"近似）
    cont = 25 if top_sec in prev2 else (18 if d['tops'] else 0)
    # 龙头封板：最强板块最早封板时间
    fbt = 0
    if d['tops']:
        for st in d['tops'][0][1]:
            v = int(st.get('fbt') or 0)
            fbt = min(fbt, v) if fbt else v
    lead = 20 if 0 < fbt <= 93500 else (12 if 0 < fbt <= 100000 else 5)
    # 昨日溢价（解析 yesterday_premium 文本，失败按 0）
    prem = 0.0
    try:
        m = re.search(r'均([+-]?\d+\.\d+)%', yesterday_premium())
        if m:
            prem = float(m.group(1))
    except Exception:
        pass
    prem_s = 20 if prem >= 2 else (12 if prem >= 0 else 0)
    # 资金持续：当日净流入（无连续账本 → 中性 10；净流入 15；净流出 5）
    net = 0.0
    if fin and fout:
        net = sum(v for _, v in fin[:5]) + sum(v for _, v in fout[:5])
    fund = 15 if net > 0 else (5 if net < 0 else 10)
    # 炸板率
    zbr = d['zb'] / (d['lu'] + d['zb']) if (d['lu'] + d['zb']) else 0.3
    zbr_s = 15 if zbr < 0.28 else (8 if zbr < 0.42 else 0)
    total = cont + lead + prem_s + fund + zbr_s
    if total >= 75:
        label, aggr = '主线仍强', '积极加仓（总仓可6-8成）'
    elif total >= 55:
        label, aggr = '开始分化', '控仓（3-5成，只做龙头）'
    else:
        label, aggr = '即将退潮', '兑现/空仓该方向'
    subs = {'continuity': cont, 'lead': lead, 'premium': prem_s, 'fund': fund, 'zbr': zbr_s}
    return total, label, aggr, subs


def health_bar(idx, d, fin, fout):
    """主线健康度状态条 HTML（noon/eod 顶部 + 底部仓位建议行）。"""
    hs, hl, ha, subs = mainline_health(idx, d, fin, fout)
    hc = RED if hl == '主线仍强' else (GOLD if hl == '开始分化' else GREEN)
    return (f'<div style="margin-top:6px;background:#232a3a;border-left:4px solid {hc};border-radius:8px;'
            f'padding:8px 11px;font-size:13px;">🧭 主线健康度 <b style="color:{hc}">{hs}/100</b>（{hl}）'
            f'｜{ha}<span style="color:{GREY};font-size:12px;">（连续{subs["continuity"]}/封板{subs["lead"]}/溢价{subs["premium"]}/资金{subs["fund"]}/炸板{subs["zbr"]}）</span></div>')


# ============ 模块6：动态仓位建议引擎 ============
_TRADER_RULES = '''你是一线游资操盘手，不是分析师。要求：大白话、直接、狠、带盘口细节，说话像真人游资在微信群里盯盘。禁止官方腔、书面语、堆砌形容词。硬性要求：如果今日没有明确主力建仓或拉升痕迹，必须明确写「今日无明确可操作方向」并说明原因，空推送是正确行为，禁止为了凑数而推荐。禁止万能句。仓位必须与主力阶段绑定且全天一致，不能前后矛盾。只允许空仓/1成试探/2成/半仓。任何「买/跟」必须同时给出触发条件+失效/止损条件。最终输出用连贯的大白话段落，像跟兄弟连麦盯盘一样把结论和原因讲完，禁止一问一答、禁止条目清单式罗列。'''
def _pos_advice(emotion):
    """情绪→总仓位档位（代码实算，只给比例；具体动作交 AI 判读，全天一致）。"""
    return {'偏多': '4~6成',
            '震荡': '2~4成',
            '偏空': '空仓或1成',
            '冰点': '1~2成'}.get(emotion or '震荡', '2~4成')


def dynamic_pos_cap(emotion, health_label):
    """动态总仓位上限（成）。emotion∈偏多/震荡/偏空；health∈主线仍强/开始分化/即将退潮。
    表：偏多 8/6/2 · 震荡 5/4/2 · 偏空 3/2/1（用户指定矩阵）。"""
    tbl = {
        ('偏多', '主线仍强'): 8, ('偏多', '开始分化'): 6, ('偏多', '即将退潮'): 2,
        ('震荡', '主线仍强'): 5, ('震荡', '开始分化'): 4, ('震荡', '即将退潮'): 2,
        ('偏空', '主线仍强'): 3, ('偏空', '开始分化'): 2, ('偏空', '即将退潮'): 1,
    }
    return tbl.get((emotion, health_label), 3)


def _health_from_mscore(mscore):
    """无主线健康度实算档位（pre/auction/hourly/watch/warn）用市场分近似并注明口径。"""
    return '主线仍强' if mscore >= 75 else ('开始分化' if mscore >= 55 else '即将退潮')


def _emotion_from_pools(d):
    """无指数行情档位（pre/auction/hourly/warn）用涨停/炸板/跌停池近似情绪（零额外网络）。"""
    zbr = d['zb'] / (d['lu'] + d['zb']) if (d['lu'] + d['zb']) else 0.3
    if zbr >= 0.42 or d['dt'] >= 40:
        return '偏空'
    if d['lu'] >= 55 and zbr < 0.28:
        return '偏多'
    return '震荡'


def pos_cap_line(emotion, health_label, mscore=None):
    """重要推送底部固定仓位行：「📊 当前建议总仓位上限：X成（情绪=… · 主线=…）」。
    主线健康度只在 noon/eod 实算，其余档位标注「实算见午间/收盘」，绝不冒充。"""
    if health_label is None and mscore is not None:
        health_label = _health_from_mscore(mscore)
    cap = dynamic_pos_cap(emotion, health_label or '开始分化')
    tip = '⚠ 注意兑现' if (emotion == '偏多' and cap >= 8) else ''
    hl_txt = health_label if health_label else '—（noon/eod 实算）'
    return (f'<div style="margin-top:8px;font-size:13px;color:#adb5bd;border-top:1px dashed #444;padding-top:6px;">'
            f'📊 当前建议总仓位上限：<b style="color:{GOLD}">{cap}成</b>（情绪={emotion} · 主线={hl_txt}）{tip}</div>')


def theme_score(name, stocks, cont):
    n = len(stocks)
    lbc_max = max(int(s.get('lbc') or 0) for s in stocks)
    s = min(3, n * 0.6) + min(3, lbc_max * 0.8) + (1.5 if cont else 0)
    s += min(2, sum(1 for x in stocks if int(x.get('lbc') or 0) >= 2) * 0.7)
    lv = '强' if s >= 7 else ('中' if s >= 4 else '弱')
    return round(s, 1), lv


def stock_score(stock, mem):
    s = 5.0 + min(2, int(stock.get('lbc') or 0))
    fbt = int(stock.get('fbt') or 0)
    if fbt and fbt < 100000:
        s += 1.5
    nm = stock.get('n')
    for days in list(mem.values())[-5:]:
        for info in days.values():
            if nm in info.get('leaders', []):
                s += 1.5
    return round(min(10, s), 1)


def suggestion(stock, sec_n, sec_s, stype, mkt_label):
    sc = stock_score(stock, load_memory())
    if sc >= 7.5:
        act, buy, pos = '评分档位：强', '等技术位回踩再进', '20%'
    elif sc >= 5.5:
        act, buy, pos = '评分档位：中', '等技术位回踩再进', '10%'
    else:
        act, buy, pos = '评分档位：弱', '等技术位回踩再进', '0%'
    if mkt_label in ('快速轮动', '情绪退潮'):
        pos = '≤5%'
    reason = f'{sec_n}题材强度{sec_s}分，该股在板块里是{stype}。'
    reason += '市场档位：' + str(mkt_label) + '。'
    return {'n': stock.get('n'), 'code': stock.get('c'), 'sec': sec_n,
            'type': stype, 'score': sc, 'act': act, 'buy': buy,
            'stop': '破成本-3%或当日最低价', 'pos': pos, 'why': reason}


_ASK_DS_SYS_AC = '''你是有10年以上实战经验的一线游资，服务竞价、主题点火、尾盘深水星、午间作战、收盘复盘、消息解读场景。
【主力游资运作逻辑·强制】
1. 先看筹码后说话：对每条数据先判断主力阶段（吸筹中/洗盘中/拉升中/出货中/对倒中），再问三个问题——主力为什么动它、跟我什么关系、主力下一步想干什么。
2. 翻译成人话：用游资黑话（挖坑洗盘/红肥绿瘦/上方真空/脉冲试盘/对倒出货），结论先行+动作可执行。
3. 套游资纪律：高位连板一律不接飞刀；没有明显建仓痕迹的票只看戏；加仓只加主力还没出货的；破点火开盘价或成本区无条件走。
4. 自查反推：说机会必须同时说出主力可能出货的信号。
5. 输出前先自问：如果今天不推这只票，最硬的理由是什么？理由成立就直接写「不碰」。
【输出规范】语言最接地气，像跟兄弟连麦。推荐标准极严：优先真正有建仓痕迹的龙头/中军；竞价买卖比严重失衡直接降级；高开>4%强制标注「谨慎」；默认半仓起步，严禁满仓。【市值红线】只在30亿-800亿之间写操作标的。【量能红线】禁止编造绝对量能数字，只写相对倍数+价格锚。最终结论只能是：跟主力 / 观察 / 不碰。
【输出风格·强制】最终给用户看的内容用连贯的大白话段落写出，像跟兄弟连麦盯盘一样，先说结论再讲原因、逻辑、暗线和动作，讲完就停，禁止一问一答、禁止条目清单式罗列、禁止任何模板句和规则套话。没有硬逻辑就明确写「今日无明确可操作方向」。
【三层认知结构】①信息密度压缩；②因果链显影（谁在动→为什么动→动到哪一步）；③决策接口（触发条件+动作+失败出口）。比喻优先于术语，结论先行，坏消息不软化。'''


_ASK_DS_SYS = '''你是有10年以上实战经验的一线游资，服务竞价、主题点火、尾盘深水星、午间作战、收盘复盘、消息解读场景。
【主力游资运作逻辑·强制】
1. 先看筹码后说话：先判断主力阶段（吸筹/洗盘/拉升/出货/对倒），再问三个主力问题。
2. 翻译成人话：游资黑话优先，结论先行+动作可执行。
3. 套游资纪律：高位连板不接飞刀；无建仓痕迹只看戏；破点火开盘价无条件走。
4. 自查反推：说机会必须带主力出货信号。
5. 输出前先自问：如果今天不推这只票，最硬的理由是什么？理由成立就直接写「不碰」。
【输出规范】语言最接地气，像跟兄弟连麦。推荐标准极严：优先真正有建仓痕迹的龙头/中军；竞价买卖比严重失衡直接降级；高开>4%强制标注「谨慎」；默认半仓起步，严禁满仓。【市值红线】只在30亿-800亿之间写操作标的。【量能红线】禁止编造绝对量能数字，只写相对倍数+价格锚。最终结论只能是：跟主力 / 观察 / 不碰。
【确定性层·强制】1. 任何「买/跟」必须同时给出：触发价位或条件 + 量能条件 + 失效/止损条件（破点火开盘价或成本区）。2. 任何「不碰」只写唯一主因（位置过高/无建仓痕迹/题材末段/暗雷/资金出逃）。3. 证据不足只能输出「观察」或「不碰」。4. 仓位只允许：空仓 / 1成试探 / 2成 / 半仓。5. 任何强票必须先判主力阶段。6. 推荐须满足：题材主线 + 有建仓痕迹或筹码优势 + 位置非高位连板 + 有明确买点止损，不足强制观察或不碰。
【输出风格·强制】最终给用户看的内容用连贯的大白话段落写出，像跟兄弟连麦盯盘一样，先说结论再讲原因、逻辑、暗线和动作，讲完就停，禁止一问一答、禁止条目清单式罗列、禁止任何模板句和规则套话。没有硬逻辑就明确写「今日无明确可操作方向」。'''

# —— 大模型当日次数预算（2026-10-24 升级：上限 12 次，ask_deepseek 统一入口检查+计数；
#    用尽后置 _DS_EXHAUSTED 卡片注明「今日 DS 额度已用」；任一调用失败置 _DS_FAILED 卡片红字提示；
#    计数写入 data/ds_daily_count.json + writeback）——
DS_DAILY_LIMIT = 60          # ask_ds_diag：ModelScope 免费通道额度充足（12 是 DeepSeek 付费时代的旧值）；watch 每 10 分钟 2 次 ≈ 每日 50 次，留余量
DS_DAILY_COUNT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'ds_daily_count.json')
_DS_EXHAUSTED = False  # 本次 run 内 DS 次数用尽（供卡片注明「今日 DS 额度已用」）
_DS_FAILED = False     # 本次 run 内任一 LLM 调用失败（供卡片红字「模型失败，以下为规则结论」）


def _ds_daily_used():
    """当日已用 DS 次数（跨 run 持久：data/ds_daily_count.json；失败视为 0，金额闸门仍兜底）。"""
    try:
        with open(DS_DAILY_COUNT_PATH, encoding='utf-8') as f:
            d = json.load(f)
        return d.get('n', 0) if d.get('date') == _bj_now().strftime('%Y-%m-%d') else 0
    except Exception:
        return 0


def _ds_daily_inc():
    """当日 DS 次数 +1 并 writeback；失败不阻断（gateway 金额闸门兜底）。"""
    try:
        os.makedirs(os.path.dirname(DS_DAILY_COUNT_PATH), exist_ok=True)
        with open(DS_DAILY_COUNT_PATH, 'w', encoding='utf-8') as f:
            json.dump({'date': _bj_now().strftime('%Y-%m-%d'), 'n': _ds_daily_used() + 1}, f, ensure_ascii=False)
        _git_commit_push(DS_DAILY_COUNT_PATH, 'update ds daily count')
    except Exception as e:
        print('[ds-count] 当日计数写入失败（不影响推送，gateway 金额闸门仍兜底）:', e)


def _modelscope_chat(payload, purpose, system_text):
    """魔搭免费通道（OpenAI 兼容端点，urllib 原生零依赖）。
    成功返回文本；401/403/429/404/网络失败返回 None（调用方降级 DeepSeek 付费网关）。
    429/404 自动轮换备选模型（最多试完 _MODELSCOPE_MODELS 全部）。"""
    models = list(_MODELSCOPE_MODELS)
    override = os.environ.get('MODELSCOPE_MODEL', '')
    if override and override not in models:
        models.insert(0, override)
    msgs = [{'role': 'system', 'content': system_text or _ASK_DS_SYS},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]
    for m in models:
        try:
            body = json.dumps({'model': m, 'messages': msgs,
                              'temperature': 0.5,
                              'max_tokens': (8000 if purpose == 'zforce_radar' else 6000)}).encode('utf-8')
            req = urllib.request.Request(MODELSCOPE_URL, data=body, headers={
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + MODELSCOPE_KEY,
                'User-Agent': 'quantmonitor/1.0'})
            r = json.loads(urllib.request.urlopen(req, timeout=120).read().decode('utf-8'))
            _ch = (r.get('choices') or [{}])[0]
            txt = (_ch.get('message') or {}).get('content') or ''
            _fin = _ch.get('finish_reason') or ''
            if txt.strip():
                if _fin == 'length':
                    print('[LLM] 输出被截断 model=%s purpose=%s len=%d' % (m, purpose, len(txt)))
                    _diag_append('[llm] 输出截断 purpose=%s len=%d finish=length' % (purpose, len(txt)))
                print(f'[LLM] ModelScope OK model={m} purpose={purpose} finish={_fin}')
                return txt.strip()
            _diag_append('[llm] 空回复 purpose=%s finish=%s' % (purpose, _fin))
            print(f'[LLM] ModelScope 空回复 model={m} finish={_fin}，试下一个')
        except urllib.error.HTTPError as e:
            code = e.code
            if code in (401, 403):
                print(f'[LLM] ModelScope 认证失败({code})：需绑定阿里云+实名 或 token 无效')
                return None
            if code in (429, 404):
                print(f'[LLM] ModelScope {code} model={m} 额度/模型不可用，换备选')
                continue
            print(f'[LLM] ModelScope http_{code} model={m}')
            return None
        except Exception as e:
            if 'timed out' in str(e).lower() or isinstance(e, TimeoutError):
                print(f'[LLM] ModelScope 超时 model={m}，换备选重试')
                continue
            print(f'[LLM] ModelScope 异常: {str(e)[:120]}')
            return None
    print('[LLM] ModelScope 全部模型不可用，规则兜底')
    return None


_ANTI_TEMPLATE_BLOCK = ('''【反模板与空推送规则·全局铁律·输出前逐句自查，违反即整段重写】
一、禁止句式（含任何变体）：「值得关注」「建议留意」「板块强势带动」「XX概念+龙头」「资金认可」「结构改善」「情绪回暖」「市场有波动」「建议谨慎」「或将刺激相关板块」「具备投资价值」「风险与机会并存」「当前市场情绪」「没有安全垫」「确认企稳」「管住手」等空话套话，一个字都不许写。
二、每条结论必须绑定当天真实数据：谁（具体票/板块）、多少（涨幅/量比/换手/封单/家数/分数/成交额）、何时（几点封板/几点启动/数据采集时间）。禁止无数字的定性结论（"资金进场/情绪回暖/结构改善"必须有数字支撑）。
三、每个操作判断必须给当天唯一主因（位置过高/量能造假/题材末段/暗雷/资金出逃，或当天真实独有主因），禁止列一堆笼统理由凑数。
四、今日无符合条件的标的时，必须明确写「今日无明确可操作方向」或「当前无符合条件的标的」。空推送是正确行为，禁止为了推送而降低标准。
五、同一句式不得在不同日期或不同票之间复用；每段内容必须有当天输入数据可逐条追溯。宁可明确说"数据不足不能判断"，也不许说正确的废话。
''')
_TEMPLATE_BLACKLIST = (
    '值得关注', '建议留意', '板块强势带动', '资金认可', '结构改善', '情绪回暖',
    '市场有波动', '建议谨慎', '或将刺激', '具备投资价值', '风险与机会并存',
    '板块刚萌芽', '情绪有点过热', '资金都在抢筹码', '没有安全垫', '不是低吸是接力',
    '半山腰', '违背纪律', '确认企稳', '管住手', '先看板块别追', '当前市场情绪',
)


def _antitemplate_hits(text):
    """扫描 LLM 输出中的黑名单模板句，返回命中词列表（空=通过）。"""
    t = text or ''
    return [w for w in _TEMPLATE_BLACKLIST if w in t]





def ask_deepseek(payload, purpose='eod', system_text=None):
    """统一走 ModelScope 免费通道（额度充足不省，max_tokens 3000）。
    已停用 DeepSeek 付费网关（用户申请退款）；失败重试 2 次后返回 ''（调用方规则兜底）。
    system_text 缺省用全局 _ASK_DS_SYS；特殊场景可传独立系统提示词。"""
    global _DS_EXHAUSTED, _DS_FAILED
    system_text = system_text or _ASK_DS_SYS
    if purpose not in ('zforce_radar', 'deep6', 'board', 'risk_card', 'theme_health_card', 'factor_weekly_card', 'board_reverse'):
        # 全局「股票深挖铁律」注入所有模块（主力雷达 ZSYS 已有等价 bottom_logic 必填、deep6 手动完整版、board 小白通俗150字硬限 不注入）
        # risk_card/theme_health_card/factor_weekly_card 是大盘级/统计级判读、不含个股，注入个股深挖铁律会诱导编造个股，故豁免
        system_text = _DEEP_DIG_RULE + '\n' + system_text
    if '反模板强化' not in system_text:
        system_text += _ANTI_TEMPLATE_BLOCK
    if not MODELSCOPE_KEY:
        _DS_FAILED = True
        _diag_append('[ask_deepseek] MODELSCOPE_KEY 为空，purpose=%s' % purpose)
        return ''
    if _ds_daily_used() >= DS_DAILY_LIMIT:
        _DS_EXHAUSTED = True
        print(f'[LLM] 当日预算已用尽({_ds_daily_used()}/{DS_DAILY_LIMIT})，跳过 purpose={purpose}')
        _diag_append('[ask_deepseek] 当日LLM预算用尽(%s/%s)，purpose=%s' % (_ds_daily_used(), DS_DAILY_LIMIT, purpose))
        return ''
    for _try in range(2):
        _ms = _modelscope_chat(payload, purpose, system_text)
        if _ms:
            _hits = _antitemplate_hits(_ms)
            print('[LLM_OUT:%s] %s' % (purpose, _ms[:1200].replace(chr(10), ' ')))
            if _hits:
                print('[反模板命中:%s] 第%d次命中 %s → 强制重写' % (purpose, _try + 1, '/'.join(_hits)))
                _diag_append('[反模板命中:%s] %s (try%d)' % (purpose, '/'.join(_hits), _try + 1))
                if _try == 0:
                    continue
                print('[反模板仍命中:%s] 二次仍命中，放行' % purpose)
            _ds_daily_inc()
            return _ms
    _DS_FAILED = True
    print('[LLM] ModelScope 两次尝试均失败，不输出规则结论（调用方只出数据事实）')
    _diag_append('[ask_deepseek] ModelScope 两次尝试均失败，purpose=%s' % purpose)
    return ''


def _json_loose(txt):
    """容错解析 LLM 输出的 JSON：先正常解析，失败则补括号救截断，再失败退到最后一个完整对象。
    LLM 被 max_tokens 截断时 json.loads 必抛异常，原逻辑直接判空→暗线全丢，这里把能救的救回来。"""
    if not txt:
        return {}
    s = txt[txt.find('{'):]
    if not s:
        return {}
    try:
        j = json.loads(s)
        if isinstance(j, dict):
            return j
    except Exception:
        pass
    # 括号配平扫描：截出第一个完整 JSON 对象（容忍模型在前后写废话）
    _depth = 0
    _in_str = False
    _esc = False
    for _i, _ch in enumerate(s):
        if _in_str:
            if _esc:
                _esc = False
            elif _ch == '\\':
                _esc = True
            elif _ch == '"':
                _in_str = False
            continue
        if _ch == '"':
            _in_str = True
        elif _ch == '{':
            _depth += 1
        elif _ch == '}':
            _depth -= 1
            if _depth == 0:
                try:
                    j = json.loads(s[:_i + 1])
                    if isinstance(j, dict):
                        return j
                except Exception:
                    pass
                break
    cut = s.rstrip()
    while cut and cut[-1] in ',:\n\r\t ':
        cut = cut[:-1]
    for _ in range(3):
        need_c = cut.count('{') - cut.count('}')
        need_s = cut.count('[') - cut.count(']')
        need_c = max(need_c, 0)
        need_s = max(need_s, 0)
        try:
            j = json.loads(cut + ']' * need_s + '}' * need_c)
            if isinstance(j, dict):
                return j
        except Exception:
            pass
        idx = max(cut.rfind('},'), cut.rfind('},{'))
        if idx < 0:
            break
        cut = cut[:idx + 1]
        while cut and cut[-1] in ',:\n\r\t ':
            cut = cut[:-1]
    return {}


def md2html(t):
    """极简 markdown 转 HTML。"""
    out = []
    for line in t.split('\n'):
        line = line.strip()
        if not line:
            continue
        if line.startswith('【'):
            out.append(f'<div style="color:{GOLD};font-weight:800;margin-top:10px;">{line}</div>')
        elif line[0].isdigit() and '.' in line[:3]:
            out.append(f'<div style="color:#e9ecef;font-size:13px;line-height:1.7;">{line}</div>')
        else:
            out.append(f'<div style="color:#ced4da;font-size:13px;line-height:1.7;">{line}</div>')
    return ''.join(out)


def _ds_status_banner():
    """卡片顶部状态条：**不再向用户暴露模型状态**。
    「模型未返回/额度用尽/只列数据事实」这类自说明属于工程口径，卡面一律不出现（用户明确要求去规则性回答）。
    模型没返回时，各卡用自己的盘口判断句兜底，观感与有模型时一致。"""
    return ''


# ============ HTML 片段 ============
# ============ 共振因子·总闸（reson_b1） ============
_RESON_CACHE = {}

def _resonance():
    """当日共振（模块级惰性缓存）：对最强板块做五重计分，输出档位 A/B/C。
    失败返回 None → 卡片头部无档位行、低吸卡无仓位约束，全部优雅降级不阻断。
    数据源全部复用现有函数：get_pools(lu/zb/tops) + _clist_gainers(量比/涨幅) +
    _board_start(板块共振) + market_score(情绪分) + theme_lifecycle.json(发酵天数)。"""
    if not _RESON_OK:
        return None
    if '_r' in _RESON_CACHE:
        return _RESON_CACHE['_r']
    try:
        idx = get_indices()
        d = get_pools()
        rows = _clist_gainers()
        board = None
        try:
            board = _board_start(rows, '震荡', min_cnt=2, min_pct=2.5, min_lb=1.5)  # 早期观察降门槛
        except Exception:
            board = None
        stocks = []
        sector = ''
        if board and board.get('stocks'):
            stocks = board['stocks']
            sector = board.get('sec') or ''
        if not stocks and d.get('tops'):
            # 无规则共振命中 → 用最强涨停板块补位（涨停股 pct 近似 9.9/19.8 无法区分，lb 中性 1.0）
            sector = d['tops'][0][0]
            stocks = [{"name": x.get('n'), "code": x.get('c'), 'pct': 9.9, 'lb': 1.0} for x in d['tops'][0][1][:5]]
        mscore = 50
        try:
            _, mscore, _ = market_score(idx, d)
        except Exception:
            pass
        mem = load_memory()
        seen = 1
        try:
            lc = {}
            if os.path.exists(LIFECYCLE_PATH):
                with open(LIFECYCLE_PATH, encoding='utf-8') as f:
                    lc = json.load(f)
            seen = int((lc.get(sector) or {}).get('seen_count') or 1)
        except Exception:
            seen = 1
        ctx = {"stocks": stocks, "sector": sector, "lu": d.get('lu', 0), "zb": d.get('zb', 0),
               "mscore": mscore, "memory": mem, "today": _bj_now().strftime('%Y-%m-%d'),
               "seen_count": seen}
        res = _reson_compute(idx, d, ctx)
        _RESON_CACHE['_r'] = res
        return res
    except Exception as _re2:
        _RESON_CACHE['_r'] = None
        return None

# ============ 批次A1：卡面元说明统一清洗（2026-11-07 用户指令） ============
# 用户要求卡面「只要结论、不要解释这句是谁算的」：代码统计/代码筛选/见 AI 判读/
# 模型未返回/不给规则版结论 这类元说明一律不上卡片。
_META_KW = ('模型未返回', 'AI 判读未返回', 'AI 研判未返回', 'AI 结论未返回', 'AI 深挖未返回', '深挖未返回', 'AI 未返回',
            '模型通道未就绪', '模型额度已用尽', '不给规则版', '只列数据事实', '只列标题',
            '只列上面这些', '只列上方', '只列聚类', '只列六条件', '只出上面这些',
            '仅展示数据', '右侧档位仅由代码阈值实算', '档位仅由代码阈值实算',
            '每条=带来什么信息', '📌 筛选逻辑：', '📌 数据时点：',
            '仓位与买卖动作不给规则版')
_META_TOKENS = ('（代码统计，方向判读见本卡 AI 段）', '（代码统计，方向判读见 AI 段）',
                '（仓位档位·代码实算）', '（代码统计；动作见 AI 判读）', '，方向判读见 AI 段',
                '（技术位·代码算）', '（技术位·代码算，非 AI 判读）',
                '（代码统计口径）', '（代码统计）', '（代码筛选口径）', '（还没涨停）',
                '（代码阈值）', '· 代码筛选：昨日涨停票已剔除', '（四类打包，≤12条，每条带利好/利空）',
                ' · 代码过滤口径，只观察不操作', '（综合评分排序）')
_META_SENT = ('；动作见 AI 判读', '，动作见 AI 判读', '｜仓位 见 AI 判读',
              '，买不买、买多少由本卡 AI 判读给', '',
              '，风控动作见 AI 判读')


def _strip_meta(html):
    """清掉卡面上的规则性元说明（保内容、去解释）。纯文本 div 命中关键词整段删除。"""
    if not html:
        return html
    def _kill_div(m):
        txt = m.group(1)
        if any(k in txt for k in _META_KW):
            return ''
        return m.group(0)
    html = re.sub(r'<div[^>]*>((?:[^<]|<br[^>]*>)*?)</div>', _kill_div, html, flags=re.S)
    # 「可跟踪跟风…暂无（量能未达标）」这类空态行整行不显示
    html = re.sub(r'<div[^>]*>((?:[^<]|<br[^>]*>)*?可跟踪跟风[^<]*?暂无(?:[^<]|<br[^>]*>)*?)</div>', '', html, flags=re.S)
    for tok in _META_TOKENS:
        html = html.replace(tok, '')
    for tok in _META_SENT:
        html = html.replace(tok, '')
    # 括号里的「家数 X 家 ｜ 龙头 Y 连板」
    html = re.sub(r'（家数 [0-9]+ 家 ｜ 龙头 [0-9]+ 连板）', '', html)
    # 括号里删完只剩空白 → 连括号一起去掉；括号内尾部空格清掉
    html = re.sub(r'（\s*）', '', html)
    html = re.sub(r'（([^（）]*?)\s+）', lambda m: '（' + m.group(1) + '）', html)
    # AI 未返回确认深挖，仅展示数据
    html = re.sub(r' ?— ?AI 未返回确认深挖，仅展示数据', '', html)
    # 连续空 div 清理
    html = re.sub(r'(<div[^>]*></div>)+', '', html)
    return html


_BR_ONE = re.compile(r'<div[^>]*>(?:<[^>]+>)*[ 　]*【[^<>【】]{1,14}】[ 　]*(?:</div>)')
_BR_TWO = re.compile(r'(<div[^>]*>)(?:<[^>]+>)*[ 　]*【[^<>【】]{1,14}】[ 　]*')


def _strip_bracket_heads(html):
    """兜底：删掉 LLM 自己加的【xxx】分栏小标题（只清行首标签与纯标题段，不动卡头与正文）。"""
    if not html or '【' not in html:
        return html
    try:
        html = _BR_ONE.sub('', html)
        html = _BR_TWO.sub(lambda m: m.group(1), html)
    except Exception:
        pass
    return html


def _wrap(inner, emoji, title, show_reson=False):
    """通用卡片壳。共振只作内部因子参与判定/打分，一律不上卡片（2026-11-07 用户指令）。
    参数 show_reson 仅为兼容历史调用保留，默认 False 即不渲染头部共振档位行。
    出口统一过 _strip_meta：卡面不出现规则性元说明。"""
    _body = _strip_meta(_strip_bracket_heads(_ds_status_banner() + (inner or '')))
    return f"""<div style="background:#161b26;color:#e9ecef;font-family:-apple-system,'Microsoft YaHei',sans-serif;padding:14px;border-radius:12px;">
<div style="font-size:20px;font-weight:800;color:{GOLD};">{emoji} {title} · {_bj_now().strftime('%m/%d %H:%M')}</div>
{_reson_head() if show_reson else ''}{_body}{health_footer()}
<div style="margin-top:14px;font-size:12px;color:{GREY};">— 清一盘 · 公开行情，仅供参考 —</div></div>"""




def _reson_head():
    """卡片头部共振档位行：🎚共振档位:B(58分)·资金强·龙头稳·结构平·情绪平·时3天新。失败返回空串。"""
    try:
        _r = _resonance()
        if not _r:
            return ''
        return _reson_banner_html(_r)
    except Exception:
        return ''

def _sector_cards(tops, zb_names=None):
    """板块强度卡：强度分 = 涨停家数×0.4 + 平均涨幅×0.3 + 封板时间加权×0.3；
    龙头在炸板池（zb_names）→ 标注分歧。"""
    _dm = _sector_deep(tops)
    out = []
    for i, (name, stocks) in enumerate(tops, 1):
        stocks.sort(key=lambda s: (-int(s.get('lbc') or 0), s.get('fbt') or 0))
        lead = stocks[0]
        lbc = int(lead.get('lbc') or 0)
        # 强度分
        n = len(stocks)
        avg_pct = sum(float(s.get('pct') or 0) for s in stocks) / max(n, 1)
        ftimes = [int(s.get('fbt') or 0) for s in stocks if s.get('fbt')]
        fbt_score = 0.0
        if ftimes:
            mins = [(t // 100 * 60 + t % 100) for t in ftimes]
            fbt_score = sum(max(0.0, 1 - m / 900.0) for m in mins) / len(mins) * 100  # 越早封板越高
        strength = n * 0.4 + min(avg_pct, 20) * 0.3 + fbt_score * 0.3
        lt = f"{lead.get('n')} {_hhmm(lead.get('fbt'))}封" + (f'·{lbc}连板' if lbc >= 2 else '')
        fol = '、'.join(s.get('n') for s in stocks[1:4])
        tag = '🔥主题启动' if n >= 3 else ''
        div = ''
        if zb_names and lead.get('n') in zb_names:
            div = ' <span style="color:' + GREEN + ';">⚠️龙头分歧（炸板）</span>'
        _dp = _dm.get(name)
        _dp_html = ''
        if _dp and _dp.get('why'):
            _dp_html = (f'<div style="color:#a78bfa;font-size:12px;margin-top:3px;">🧠 逻辑：{_dp.get("logic", "")}</div>'
                        f'<div style="color:#e9ecef;font-size:12px;margin-top:2px;">👉 大白话：{_dp.get("why", "")}</div>'
                        + (f'<div style="color:{TEAL};font-size:12px;margin-top:2px;">🎯 操作：{_dp.get("act", "")}</div>' if _dp.get('act') else ''))
        out.append(f"""<div style="background:#1f2635;border-left:4px solid {GOLD};border-radius:10px;padding:10px 12px;margin:7px 0;">
<div style="font-size:14px;font-weight:700;color:{GOLD};">{i}. {name} <span style="color:{RED};">涨停{n}只</span> <span style="color:{TEAL};font-size:12px;">强度{strength:.0f}</span> <span style="color:{TEAL};font-size:12px;">{tag}</span></div>
<div style="color:#ced4da;font-size:13px;margin-top:4px;">👑 {lt}{div}</div>
{f'<div style="color:{GREY};font-size:13px;">跟涨：{fol}</div>' if fol else ''}{_dp_html}</div>""")
    return ''.join(out)


# ============ 竞价强选（09:20 用户指定算法：全市场涨幅榜→硬过滤→双重打分→Top20+DeepSeek） ============
def _clist_gainers():
    """全市场涨幅榜（仅沪深主板+创业板，剔除科创/北交所）。失败返回 []。https 优先，失败换 http。
    分页取数 pn=1..3：东财 clist 单页实际只返回前 100（pz=600 也会被截断），
    竞价/盘中涨幅前 100 基本全是 7%+ 的大涨票，2-7% 高开票大量在 100 名外——
    单页取数会导致硬过滤后全滤（实证 2026-11-02 竞价「今日无符合」），必须分页拼接。"""
    rows = []
    for scheme in ('https', 'http'):
        merged = []
        for pn in (1, 2, 3):
            url = (scheme + '://push2.eastmoney.com/api/qt/clist/get?pn=%d&pz=100&po=1&np=1&fltt=2&invt=2'
                   '&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23'
                   '&fields=f2,f3,f5,f6,f8,f10,f12,f14,f15,f16,f18,f20,f26,f127') % pn
            _rows = None
            for _try in (1, 2, 3):
                try:
                    txt, ok = _getm(url, 'clist_auction')
                    if not ok or not txt:
                        if _try < 3:
                            time.sleep(1.0)
                            continue
                        break
                    d = json.loads(txt)
                    _cand = []
                    for x in (d.get('data') or {}).get('diff') or []:
                        _c12 = str(x.get('f12', '')).strip() if x else ''
                        _c14 = str(x.get('f14', '')).strip() if x else ''
                        if not _c12 or not _c14:
                            continue                      # 东财空壳限流行(缺code/name)，丢弃
                        _cand.append(x)
                    if len(_cand) < 30 and _try < 3:     # 有效行太少=降级响应，退避重试
                        time.sleep(1.2)
                        continue
                    _rows = _cand
                    break
                except Exception as _e:
                    if _try < 3:
                        print('[auction] clist 解析异常(重试):', _e)
                        time.sleep(1.0)
                        continue
                    break
            if _rows:
                merged.extend(_rows)
            else:
                break                                # 某页连续失败即停（避免拿不全的降级数据）
        if not merged:
            continue
        # 按 code 去重（分页边界可能重复），保持涨幅降序
        seen = set()
        rows = []
        for x in merged:
            try:
                code = str(x.get('f12', '')).strip()
                if code in seen:
                    continue
                seen.add(code)
                rows.append({
                    'code': code,
                    'name': str(x.get('f14', '')).strip(),
                    'price': float(x.get('f2') or 0),
                    'pct': float(x.get('f3') or 0),       # 竞价/现价涨幅
                    'vol': float(x.get('f5') or 0),       # 成交量(手)
                    'amount': float(x.get('f6') or 0),    # 成交额(元)
                    'turn': float(x.get('f8') or 0),      # 换手率(%)
                    'lb': float(x.get('f10') or 0),       # 量比
                    'high': float(x.get('f15') or 0),
                    'low': float(x.get('f16') or 0),
                    'prev': float(x.get('f18') or 0),
                    'list_date': str(x.get('f26') or ''),
                    'industry': str(x.get('f127') or '').strip() or '其他',
                })
            except Exception:
                continue
        if rows:
            break
    for x in rows:
        if x.get('industry') and x['industry'] != '其他':
            _IND_CACHE[str(x['code'])] = x['industry']
    if _IND_CACHE:
        _ind_cache_save()
    return rows


def _clist_gainers_alt():
    """东财 clist 不可用（收盘后/断连）时的当日盘面替代源：新浪 hs_a 涨幅排行 + 腾讯批量补量比。
    字段对齐 _clist_gainers：code/name/price/pct/vol(手)/amount/turn/lb/high/low/prev/industry/list_date。
    收盘后当日涨幅榜语义 = 「当日涨幅」（非竞价高开），调用方需在卡片标注数据时点。失败返回 []。"""
    rows = []
    try:
        for pn in (1, 2, 3):
            url = ('https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/'
                   'Market_Center.getHQNodeData?page=%d&num=100&sort=changepercent&asc=0&node=hs_a'
                   '&symbol=&_s_r_a=page') % pn
            txt, ok = _getm(url, 'clist_alt_p%d' % pn)
            if not ok or not txt:
                continue
            d = json.loads(txt)
            for x in d:
                code = str(x.get('code') or '').strip()
                name = str(x.get('name') or '').strip()
                if not code or not name:
                    continue
                # 仅沪深主板+创业板，剔除科创/北交所
                if code.startswith(('688', '689', '8', '4', '920', '92', 'bj')):
                    continue
                try:
                    pct = float(x.get('changepercent') or 0)
                    if pct < 0:
                        continue
                except Exception:
                    continue
                try:
                    rows.append({
                        'code': code,
                        'name': name,
                        'price': float(x.get('trade') or 0),
                        'pct': pct,
                        'vol': round(float(x.get('volume') or 0) / 100.0),  # 新浪 volume 单位=股 → 手
                        'amount': float(x.get('amount') or 0),
                        'turn': float(x.get('turnoverratio') or 0),
                        'lb': 0.0,   # 下方腾讯批量补
                        'high': float(x.get('high') or 0),
                        'low': float(x.get('low') or 0),
                        'prev': float(x.get('settlement') or 0),
                        'list_date': '',   # 新浪无上市日期 → 跳过次新过滤（非竞价时段可接受）
                        'industry': _IND_CACHE.get(code, '其他'),
                    })
                except Exception:
                    continue
            if len(rows) >= 100:
                break
    except Exception as e:
        print('[auction] 替代源拉取失败:', e)
    # 腾讯批量补量比（f43）
    if rows:
        _lbq = {}
        cs = [('sh' if c.startswith('6') else 'sz') + c for c in [r['code'] for r in rows]]
        for i in range(0, len(cs), 60):
            try:
                txt, ok = _getm('http://qt.gtimg.cn/q=' + ','.join(cs[i:i + 60]), 'clist_alt_lb', encoding='gbk')
                if not ok:
                    continue
                for line in txt.strip().split(';'):
                    if '~' not in line:
                        continue
                    f = line.split('~')
                    try:
                        # 腾讯批量 f[2] 即完整代码（6位，如 600519），不要切前缀
                        _lbq[f[2]] = float(f[43] or 0)
                    except Exception:
                        pass
            except Exception:
                pass
        for r in rows:
            r['lb'] = _lbq.get(r['code'], 0.0)
    return rows


def _auction_filter(rows, zt_lbc=None):
    """硬过滤：仅沪深主板+创业板；剔除ST/退市、次新(<365天)、高开/换手区间外、
    竞价量/昨量不足（主板<8%/创业<12%）、近5日累计涨幅>25%（连板龙头除外）。
    不设市值限制、不设均线（MA20）硬限制（用户指令：早盘/尾盘竞价取消市值与MA20限制）。"""
    out = []
    try:
        from datetime import date
        yy, mm, dd = map(int, _bj_now().strftime('%Y-%m-%d').split('-'))
        today = date(yy, mm, dd)
    except Exception:
        today = None
    for s in rows:
        code, name = s['code'], s['name']
        if not code or not name:
            continue
        # 板块：仅沪深主板 + 创业板（688/689/8xx/4xx/920=科创/北交所 剔除）
        if code.startswith(('688', '689', '8', '4', '920', '92')):
            continue
        if code.startswith('6'):
            s['board'] = 'main'
        elif code.startswith(('000', '001', '002', '003')):
            s['board'] = 'main'
        elif code.startswith(('300', '301')):
            s['board'] = 'gem'
        else:
            continue
        # ST / 退市
        if 'ST' in name.upper() or '退' in name:
            continue
        # 次新：上市 < 365 天剔除
        if s['list_date'] and len(s['list_date']) == 8 and today:
            try:
                ld = date(int(s['list_date'][:4]), int(s['list_date'][4:6]), int(s['list_date'][6:8]))
                if (today - ld).days < 365:
                    continue
            except Exception:
                pass
        # 高开幅度区间：主板 2%~7%，创业板 4%~14%
        lo, hi = (2, 7) if s['board'] == 'main' else (4, 14)
        if not (lo <= s['pct'] <= hi):
            continue
        # 换手率：主板 0.5%~15%，创业板 ≤30%
        turn_max = 30.0 if s['board'] == 'gem' else 15.0
        if not (0.5 <= s['turn'] <= turn_max):
            continue
        sym = ('sh' if code.startswith('6') else 'sz') + code
        # 竞价量/昨量：主板≥8%，创业板≥12%（K线失败放行）
        try:
            arr = get_klines(sym, 2)
            if len(arr) >= 2 and float(arr[-2][5]) > 0:
                vq = (s['vol'] * 100) / float(arr[-2][5]) * 100
                vq_min = 8.0 if s['board'] == 'main' else 12.0
                if vq < vq_min:
                    continue
        except Exception:
            pass
        # 近5日累计涨幅>25% 剔除（连板龙头除外：今日涨停池内且连板≥2）
        try:
            arr = get_klines(sym, 6)
            if len(arr) >= 6 and float(arr[-6][2]) > 0:
                chg5 = (float(arr[-1][2]) / float(arr[-6][2]) - 1) * 100
                if chg5 > 25 and not (zt_lbc and zt_lbc.get(code, 0) >= 2):
                    continue
        except Exception:
            pass
        out.append(s)
    return out


_IND_CACHE = {}
_IND_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'ind_cache.json')


def _ind_cache_load():
    try:
        with open(_IND_CACHE_PATH, encoding='utf-8') as f:
            _IND_CACHE.update(json.load(f))
    except Exception:
        pass


def _ind_cache_save():
    try:
        with open(_IND_CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(_IND_CACHE, f, ensure_ascii=False)
    except Exception:
        pass


def _stock_industry(code):
    """单股行业兜底：缓存(内存→文件) → 东财单股接口。sec='其他'/空 时用，失败返回 ''。"""
    c = str(code)
    if _IND_CACHE.get(c):
        return _IND_CACHE[c]
    try:
        mk = '1' if c.startswith('6') else '0'
        url = ('http://push2.eastmoney.com/api/qt/stock/get?secid=' + mk + '.' + c + '&fields=f57,f58,f127')
        txt, ok = _getm(url, 'stock_ind')
        if ok and txt:
            dd = json.loads(txt).get('data') or {}
            ind = str(dd.get('f127') or '').strip()
            if ind:
                _cl = _sec_clean(ind)
                if _cl:
                    _IND_CACHE[c] = _cl
                    _ind_cache_save()
                    return _cl
    except Exception:
        pass
    return ''


def _today_top(d):
    """今日主线名单：涨停板块 TOP6 + 题材热度 TOP，去重拼接。供单股卡判断主线归属。"""
    names = []
    for sec in (d.get('sectors') or {}).keys():
        if sec not in names:
            names.append(sec)
    for nm in (d.get('themes') or {}).keys():
        if nm not in names:
            names.append(nm)
    return '、'.join(names[:6]) or '（今日暂无明确主线）'


def _sec_clean(sec):
    """题材名清洗（单股链路）：去噪声词→黑名单→纯数字→中文占比；无效返回 ''。"""
    if not sec:
        return ''
    s2 = re.sub(r'[行业板块概念\s]+', '', str(sec)).strip()
    if not s2 or s2 in _BLACKLIST:
        return ''
    if _is_digit_serial(s2):
        return ''
    if len(s2) < 2 or len(s2) > 12:
        return ''
    if not _is_valid_chinese_ratio(s2):
        return ''
    return s2


def _stock_industry(code):
    """单股行业兜底：东财 stock/get 接口取行业(f127)。sec='其他'/空 时用，失败返回 ''。"""
    try:
        mk = '1' if str(code).startswith('6') else '0'
        url = ('http://push2.eastmoney.com/api/qt/stock/get?secid=' + mk + '.' + str(code)
               + '&fields=f57,f58,f127')
        txt, ok = _getm(url, 'stock_ind')
        if ok and txt:
            dd = json.loads(txt).get('data') or {}
            ind = str(dd.get('f127') or '').strip()
            if ind:
                return _sec_clean(ind) or ''
    except Exception:
        pass
    return ''


# ============ 最终版硬性筛选（2026-11-02 定稿 13条，仅 spot/anchor/deep6/zscan） ============
_HARD_FILTER_RULES = ('''【硬性筛选条件·强制·仅限本模块】
必须先满足以下全部条件，否则直接剔除（不进入候选/radar）：
1. 当前价格 > 近8个月最高价的70%
2. 当前价格 < 近8个月最高价的105%
3. 前一日没有涨停
4. 近一年涨停次数 ≥ 3次
5. 仅限主板、创业板，非ST
6. 剔除地产、农业、白酒、保险
7. 总市值 >30亿 且 ≤800亿
8. 剔除股价 >120元
9. 剔除股价 <5元
10. 距离近8个月最高价回撤 <15%（现价 ≥ 近8个月最高价的85%）
11. 当日收盘价 ≥ 5日均线
12. 剔除当日涨停板
13. 剔除当日跌停板
执行顺序：先硬性筛选出股票池 → 再在池子里按原规则 + 暗线深挖铁律推送。通过筛选但暗线不硬，照样写「不碰」。数据不足的项目按「未取得」保守剔除并注明原因，不猜不编。''')
_HF_INDUSTRY_BLOCK = ('地产', '农业', '白酒', '保险')


def _stock_mv(code):
    """单股总市值（亿元）：东财 stock/get f20（元→亿）。失败返回 None。"""
    try:
        mk = '1' if str(code).startswith('6') else '0'
        url = ('http://push2.eastmoney.com/api/qt/stock/get?secid=' + mk + '.' + str(code) + '&fields=f20')
        txt, ok = _getm(url, 'stock_mv')
        if ok and txt:
            dd = json.loads(txt).get('data') or {}
            f20 = dd.get('f20')
            if f20 not in (None, '-', ''):
                return float(f20) / 1e8   # 元→亿元
    except Exception:
        pass
    return None


def _hard_filter_pass(code, name='', price=None, industry='', klines=None, mv=None):
    """最终版13条硬性筛选。返回 (ok, reason)。
    数据不足的项目按「未取得」保守剔除（不猜不编）；klines/mv 可复用调用方已拉数据（省接口）。
    price 为判定用现价（盘中）或收盘价（收盘模块）；未传则用K线最后一根收盘。"""
    if not code:
        return False, '无代码'
    _c = str(code)
    # ⑤ 仅限主板、创业板，非ST
    if _c.startswith(('688', '689', '8', '4', '920', '92')):
        return False, '非主板/创业板'
    _nm = str(name or '')
    if 'ST' in _nm.upper() or '退' in _nm:
        return False, 'ST/退市'
    # ⑥ 剔除地产、农业、白酒、保险
    if industry and any(k in industry for k in _HF_INDUSTRY_BLOCK):
        return False, '行业剔除:' + str(industry)
    # K线（近250日）
    arr = klines
    if not arr:
        try:
            sym = ('sh' if _c.startswith('6') else 'sz') + _c
            arr = get_klines(sym, 250)
        except Exception:
            arr = []
    if not arr:
        return False, 'K线未取得'
    closes = [float(r[2]) for r in arr]
    highs = [float(r[3]) for r in arr]
    seg_h = highs[-160:] if len(highs) >= 160 else highs
    _hi8 = max(seg_h) if seg_h else 0.0
    _cur = float(price) if price is not None else (closes[-1] if closes else 0.0)
    if _cur <= 0 or _hi8 <= 0:
        return False, '价格/最高价无效'
    # ⑧⑨ 股价区间 5~120
    if _cur > 120:
        return False, '股价>120元'
    if _cur < 5:
        return False, '股价<5元'
    # ① 现价 > 8月最高*0.70
    if _cur <= _hi8 * 0.70:
        return False, '低于8月最高价70%'
    # ② 现价 < 8月最高*1.05
    if _cur >= _hi8 * 1.05:
        return False, '高于8月最高价105%'
    # ⑩ 回撤<15%：现价 >= 8月最高*0.85
    if _cur < _hi8 * 0.85:
        return False, '距8月最高价回撤≥15%'
    # ⑪ 当日收盘价 ≥ 5日均线
    ma5 = sum(closes[-5:]) / 5.0 if len(closes) >= 5 else None
    if ma5 is None:
        return False, '5日均线未取得'
    if _cur < ma5:
        return False, '收盘价<5日均线'
    # ③④ 前一日涨停 / 近一年涨停次数（主板≥9.5%，创业板≥19.5%）
    _th = 19.5 if _c.startswith(('30', '300')) else 9.5
    _lts = 0
    _prev_pct = None
    for i in range(1, len(closes) - 1):   # 不含最后一根（视为当日）
        _p = closes[i - 1]
        if _p > 0:
            _pc = (closes[i] / _p - 1) * 100
            if _pc >= _th:
                _lts += 1
            if i == len(closes) - 2:
                _prev_pct = _pc
    if _prev_pct is not None and _prev_pct >= _th:
        return False, '前一日涨停'
    if _lts < 3:
        return False, '近一年涨停次数<3'
    # ⑫⑬ 当日涨停/跌停（现价 vs 昨收）
    if len(closes) >= 2 and closes[-2] > 0:
        _td_pct = (_cur / closes[-2] - 1) * 100
        if _td_pct >= _th:
            return False, '当日涨停'
        if _td_pct <= -_th:
            return False, '当日跌停'
    # ⑦ 总市值 30~800亿
    _mv = mv if mv is not None else _stock_mv(_c)
    if _mv is None:
        return False, '总市值未取得'
    if not (30 < _mv <= 800):
        return False, '总市值%.0f亿不在30-800亿' % _mv
    return True, '通过'


def _deep6_reject_html(code, name, reason):
    """硬性筛选未通过时的深度分析拒绝卡（文档：不做深度分析并结束）。"""
    import html as _h
    return ('<div style="background:#17212b;border:2px solid ' + GREY + ';border-radius:12px;padding:12px 14px;margin:10px 0;">'
            '<div style="font-size:15px;font-weight:900;color:' + GOLD + ';">🔬 个股深度六层分析</div>'
            '<div style="color:#e9ecef;font-size:13px;margin-top:6px;line-height:1.7;">'
            + _h.escape(str(name) + '(' + str(code) + ')') + ' 未通过硬性筛选（' + _h.escape(reason) + '），不做深度分析。'
            '<div style="color:' + GREY + ';font-size:12px;margin-top:4px;">硬性筛选13条：仅主板/创业板非ST、剔除地产农业白酒保险、总市值30-800亿、股价5-120元、现价位于近8月最高价70%~105%且回撤<15%、收盘≥5日均线、前日非涨停、近一年涨停≥3次、当日非涨停跌停。</div>'
            '</div></div>')



def _today_top(d):
    """今日主线名单：涨停板块 TOP6 + 题材热度 TOP，去重拼接。供单股卡判断主线归属。"""
    names = []
    for sec in (d.get('sectors') or {}).keys():
        if sec not in names:
            names.append(sec)
    for nm in (d.get('themes') or {}).keys():
        if nm not in names:
            names.append(nm)
    return '、'.join(names[:6]) or '（今日暂无明确主线）'


_STOCK_NEWS_CACHE = {}

_STOCK_F10_CACHE = {}
_STOCK_INCOME_CACHE = {}

def _stock_f10(code):
    """公司底层基本面（东财 F10）：公司简介(主业/行业地位) + 核心题材关键词。失败返回 ''。带内存缓存。"""
    if not code:
        return ''
    if code in _STOCK_F10_CACHE:
        return _STOCK_F10_CACHE[code]
    out = ''
    try:
        mk = 'SH' if code.startswith('6') else 'SZ'
        url = 'https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/PageAjax?code=%s%s' % (mk, code)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                                                   'Referer': 'https://emweb.securities.eastmoney.com/'})
        d = json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8', 'ignore'))
        jb = (d.get('jbzl') or [{}])[0]
        prof = re.sub(r'\s+', '', str(jb.get('ORG_PROFILE') or ''))
        if len(prof) > 120:
            prof = prof[:120]
        out = ('公司简介：' + prof) if prof else ''
    except Exception as e:
        print('[stock_f10] survey 失败:', code, e)
    try:
        url = 'https://emweb.securities.eastmoney.com/PC_HSF10/CoreConception/PageAjax?code=%s%s' % (mk, code)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                                                   'Referer': 'https://emweb.securities.eastmoney.com/'})
        d = json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8', 'ignore'))
        kws = [str(r.get('KEYWORD') or '') for r in (d.get('hxtc') or []) if r.get('KEYWORD')]
        if kws:
            out += ('｜核心题材：' + '/'.join(kws[:5])) if out else ('核心题材：' + '/'.join(kws[:5]))
    except Exception as e:
        print('[stock_f10] conception 失败:', code, e)
    _STOCK_F10_CACHE[code] = out
    return out


def _stock_income(code):
    """主营收入构成（东财 F10 主营构成：最近报告期 行业/产品 前3项+占比）。失败返回 ''。带内存缓存。"""
    if not code:
        return ''
    if code in _STOCK_INCOME_CACHE:
        return _STOCK_INCOME_CACHE[code]
    out = ''
    out = ''
    try:
        secu = code + ('.SH' if code.startswith('6') else '.SZ')
        url = ('https://datacenter.eastmoney.com/securities/api/data/get?type=RPT_F10_FN_MAINOP&sty=ALL'
               '&filter=(SECUCODE%3D%22' + secu + '%22)&p=1&ps=20&sr=-1&st=REPORT_DATE&source=HSF10&client=PC')
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                                                   'Referer': 'https://emweb.securities.eastmoney.com/'})
        d = json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8', 'ignore'))
        data = (d.get('result') or {}).get('data') or []
        if data:
            _tag = {'1': '行业', '2': '产品', '3': '地区'}
            rows = [r for r in data if str(r.get('MAINOP_TYPE') or '') in ('1', '2')]
            if not rows:
                rows = [r for r in data if str(r.get('MAINOP_TYPE') or '') == '3']
            items = []
            for r in rows:
                it = str(r.get('ITEM_NAME') or '').strip()
                if not it or it == '其他(补充)':
                    continue
                _s = it
                ratio = r.get('MBI_RATIO')
                if ratio is not None:
                    try:
                        _s += ' 占约%.1f%%' % (float(ratio) * 100)
                    except Exception:
                        pass
                inc = r.get('MAIN_BUSINESS_INCOME')
                if inc is not None:
                    try:
                        _v = float(inc)
                        if _v >= 1e8:
                            _s += '(%.1f亿)' % (_v / 1e8)
                    except Exception:
                        pass
                items.append(_s)
                if len(items) >= 3:
                    break
            if items:
                _rp = str(data[0].get('REPORT_NAME') or '')
                out = '主营构成(%s)：%s%s' % (_tag.get(str(rows[0].get('MAINOP_TYPE') or ''), ''),
                                             '/'.join(items), ('（' + _rp + '）') if _rp else '')
    except Exception as e:
        print('[stock_income] 失败:', code, e)
    _STOCK_INCOME_CACHE[code] = out
    return out
    return out


def _stock_news(name, code):
    """个股新闻标题（东财搜索 API）：返回前 4 条去重标题，失败/风控返回 []。带内存缓存。"""
    key = code or name
    if key in _STOCK_NEWS_CACHE:
        return _STOCK_NEWS_CACHE[key]
    out = []
    try:
        kw = name or code
        param = json.dumps({"uid": "", "keyword": kw, "type": ["cmsArticleWebOld"],
                            "client": "web", "clientType": "web", "clientVersion": "curr"}, ensure_ascii=False)
        url = 'https://search-api-web.eastmoney.com/search/jsonp?cb=cb&param=' + urllib.parse.quote(param)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                                                   'Referer': 'https://so.eastmoney.com/'})
        h = urllib.request.urlopen(req, timeout=10).read().decode('utf-8', 'ignore')
        m = re.search(r'cb\((.*)\)', h, re.S)
        if m:
            d = json.loads(m.group(1))
            for a in ((d.get('result') or {}).get('cmsArticleWebOld') or []):
                t = re.sub(r'<[^>]+>', '', str(a.get('title') or '')).strip()
                if t and t not in out and not any(t[:10] in o for o in out):
                    out.append(t)
                if len(out) >= 4:
                    break
    except Exception as e:
        print('[stock_news]', name, '失败:', e)
    _STOCK_NEWS_CACHE[key] = out
    return out


def _SPOT_DS_SYS_text():
    return ('''你是一个深谙A股游资与主力资金运作手法的实战派老手。现在的场景是：板块绝对核心的龙头已经涨停（或涨幅超9%），散户和部分踏空资金已经买不到了。
你的任务是：用大白话（像跟兄弟连麦盯盘一样），顺着资金外溢的逻辑，从盘中异动池里，给我挖出1-2只现在可以买入的"补涨代表股"，并讲透为什么是它、主力前期怎么建仓洗盘、技术面和评分是否支持上车。
### 执行顺序·强制
_HARD_FILTER_RULES_
第一步：先按硬性筛选条件把股票池过滤一遍，不满足的直接剔除（不进入候选）。
第二步：在池子里按原规则 + 暗线深挖推送。
### 推演逻辑（必须连贯叙述，拒绝死板表格）
**第一步：点明现状与资金外溢逻辑**
开场直接说清楚：今天最强的板块、龙头现在封单多少、有多死。说明大资金极度看好这个方向，但在前排买不到筹码。既然资金要赚钱，必然要外溢，这就构成了咱们去低位埋伏"补涨代表"的底层逻辑。
**第二步：为什么选它当补涨代表（优势与底层暗线）**
【深挖铁律·每只票必做】先讲本质（一句话大白话说清它是干什么的，禁止「XX概念/龙头」标签糊弄）→ 再挖暗线业务（它手里真正值钱的底牌：具体产品/业务+进展到哪个阶段+对业绩的真实贡献；挖不出如实写「未见明确暗线业务」，禁止「相关/涉及/布局/受益于」糊弄）→ 判断真实关联与弹性（与龙头同链是实受益、沾边、还是纯蹭，弹性大不大）→ 为什么是它 → 破灭点 → 动作（触发条件+失效）。没有清晰底仓逻辑或弹性不足的，直接写「不碰」，绝不硬推。
直接说出它的核心优势：
- **辨识度与共振**：判断它是否拥有跟龙头一样的最正宗题材，或叠加另一个大热概念。
- **资金偏好**：判断它是盘子够大能容纳机构的"中军平替"，还是盘子极小、位置极低、游资最喜欢拉的"弹性先锋"。
- **主力建仓与洗盘痕迹**：判断前期是否在底部横盘时有主力偷偷建仓（小阳线吸筹、红肥绿瘦），现在拉起来是否上方筹码真空、没有套牢盘砸盘。没有明显建仓痕迹的票直接降级或不推。
**第三步：技术评分与定仓**
判断今天是否带量突破前期震荡平台、量能是否温和放量（主升初期）而非爆量滞涨（主力出逃）。
共振评分：龙头封死（+25分），题材正+双概念（+20分），洗盘缩量彻底（+20分），温和放量突破（+15分）。总分超过80分上标准仓（1-2成）；60分左右只能上底仓（1成）。逻辑强可以给1到2成，逻辑一般只给1成，逻辑不硬不给仓位。
**第四步：实战怎么买**
结合现在的分时图，大白话给策略：说明现在涨了几个点、能不能直接追，还是等回踩分时均线（给出大概价位）再吸；如果跌破哪个关键位说明咱们埋伏失败，必须止损。
**输出前自问**：如果不推这只票，最硬的理由是什么？理由成立就写「不碰」。没有清晰暗线或弹性不足的直接写「不碰」。
### 输出格式（自然段大白话，不列生硬标题）
开头先交代今天的盘面情况（龙头几板了，封单多大，为什么咱们要找补涨）。
接着直接推演这只补涨标的的底层逻辑（为什么资金会选它，它有什么别人没有的题材或筹码优势）。
然后算算它的技术面评分（锚在哪，洗盘怎样，主力是不是在偷偷建仓拉主升，分数多少，给多少仓位）。
最后给个实操剧本（大白话讲怎么低吸，怎么半路，怎么止损）。''')


def _spot_ds(sgs, mem=None, days=None, today_top=''):
    """单股异动卡 DeepSeek 大白话（深度挖掘版）：一次调用喂本次所有信号卡，每只附K线近况+板块历史+今日主线。
    返回 {name: 大白话}；失败/用尽返回 {}（模板降级）。"""
    if not sgs:
        return {}
    stk = []
    for sg in sgs:
        code = sg.get('code') or ''
        price = sg.get('price') or 0
        kctx = _kline_ctx(code, price) if code and price else {}
        kline_txt = ''
        if kctx:
            bits = []
            if kctx.get('new_high'):
                bits.append('创60日新高')
            if kctx.get('vol_r') and kctx['vol_r'] >= 1.3:
                bits.append(f'近3日量能放大{kctx["vol_r"]}倍')
            if kctx.get('g5') is not None:
                bits.append(f'5日累涨{kctx["g5"]:+.1f}%')
            if kctx.get('pos60') is not None:
                bits.append(f'60日位置{kctx["pos60"]:.2f}' + ('(高位)' if kctx['pos60'] > 0.85 else '(低位)' if kctx['pos60'] < 0.3 else ''))
            if kctx.get('up_days'):
                bits.append(f'连阳{kctx["up_days"]}天')
            kline_txt = '；'.join(bits) or 'K线无明显趋势特征'
        stk.append({'name': sg.get('n'), 'code': code, 'type': sg.get('type'),
                    'pct': sg.get('pct'), 'lb': sg.get('lb'), 'turn': sg.get('turn'),
                    'sec': sg.get('sec') or '热点方向', 'score': sg.get('score'),
                    'act': sg.get('act'),
                    'kline': kline_txt,
                    'news': _stock_news(sg.get('n') or '', code),
                    'f10': _stock_f10(code),
                    'board_hist': _board_hist(sg.get('sec') or '', mem, days)})
    payload = {
        'task': 'intraday_spot',
        'stocks': stk,
        'today_top': today_top or '（今日暂无明确主线）',
        'format': ('当前场景：板块龙头已涨停（或涨幅超9%），前排买不到筹码，资金必然外溢。\n'
                   '今日主线名单：' + (today_top or '（今日暂无明确主线）') + '。\n'
                   '请你从下面盘中异动池里，按系统提示词的四步推演，挖出 1-2 只现在可以买入的补涨代表股，用大白话连麦风格写自然段（拒绝 JSON、拒绝生硬标题、拒绝模板句）：\n'
                   '①点明现状与资金外溢逻辑（今天最强板块+龙头封单/几板+为什么必须找补涨）；\n'
                   '②为什么选它（最正宗题材/双题材共振/中军平替或弹性先锋/主力底部建仓与洗盘痕迹/上方筹码真空）；\n'
                   '③技术评分与定仓（突破锚在哪/量能温和放量还是爆量滞涨/共振评分给几分/80分以上标准仓1-2成、60分左右底仓1成）；\n'
                   '④实战怎么买（现在涨几个点能不能追/等回踩分时均线哪个价位吸/跌破哪个关键位止损）。\n'
                   '每只票必须给出：名称、为什么是它、评分多少、建议仓位、具体买入区间、止损位。'
                   '只许用我给的盘面数据下判断，f10/news 有就用（f10 先把主业翻译成一句人话），没有就直说，不许编；'
                   '证据不足必须降级直说；大白话要让完全不懂股票的人听懂、老手觉得说到点子上。'),
    }
    txt = ask_deepseek(payload, purpose='intra_spot', system_text=_SPOT_DS_SYS_text().replace('_HARD_FILTER_RULES_', _HARD_FILTER_RULES))
    if not txt:
        return {}
    out = {}
    try:
        import json as _json
        _j = _json.loads(txt)
        for it in _j.get('per') or []:
            if not isinstance(it, dict):
                continue
            nm = str(it.get('name') or '').strip().split('（')[0].strip()
            if nm and (it.get('logic') or it.get('why')):
                out[nm] = {'logic': str(it.get('logic') or ''), 'why': str(it.get('why') or ''),
                           'op': str(it.get('op') or ''), 'buy': str(it.get('buy') or ''),
                           'stop': str(it.get('stop') or ''), 'theme': str(it.get('theme') or '')}
        _mk = _j.get('market')
        if isinstance(_mk, dict) and (_mk.get('state') or _mk.get('risk_budget') is not None):
            out['_market'] = {'state': str(_mk.get('state') or ''),
                              'risk_budget': _mk.get('risk_budget'),
                              'yesterday_check': str(_mk.get('yesterday_check') or '')}
        if out:
            return out
    except Exception:
        pass
    # V4 新契约：自然段伏击推演（非JSON）→ 全文存 _global，渲染层整段展示
    _t = (txt or '').strip()
    if _t and len(_t) > 30 and not any(k for k in out if k != '_market'):
        out['_global'] = _t
    return out

def _spot_global_html(txt):
    """V4 补涨代表股·伏击推演 全文卡（自然段渲染）。"""
    import html as _h
    body = _h.escape(txt).replace('\n', '<br>')
    return ('<div style="background:#17212b;border:2px solid ' + TEAL + ';border-radius:12px;padding:12px 14px;margin:10px 0;">'
            '<div style="font-size:15px;font-weight:900;color:' + TEAL + ';">🎯 补涨代表 · 伏击推演</div>'
            '<div style="color:#e9ecef;font-size:13px;margin-top:6px;line-height:1.7;">' + body + '</div></div>')
DEEP6_SYS = '''你是A股个股深度分析模型，按一线游资视角思考：这只票现在主力处于什么阶段、上涨/下跌的理由哪条是真的、什么价位是关键、明天开盘三种情况各该干什么。
【执行顺序·强制】
第一步：硬性筛选（13条）。不满足直接说「未通过硬性筛选，不做深度分析」并结束。
_HARD_FILTER_RULES_
第二步：通过后按六层 + 暗线深挖输出。
【红线5条·违反任一条整段作废】
1. 只用输入中实际存在的数据；没给的写"未取得"。
2. 区分数据时间：盘中/收盘/历史不混用。
3. 每条因果判断必须绑定具体数据。
4. 消息分级：公司公告/交易所>董秘公开表态>财经媒体>传闻。
5. 不给"必涨/稳了"；不建议满仓；操作建议必须可执行。
【第一层·盘面事实】列出：现价/涨跌幅/量比/换手/成交额/日内开高低收；近10-12个交易日逐日K线。禁止在摆数据前下任何结论。
【第二层·阶段判定 + 主力阶段】把近期走势切成段落，判定当前处于：高位崩落/缩量横盘出清/试盘点火/确认反包/加速/高位分歧/退潮。同时判断主力阶段：吸筹中/洗盘中/拉升中/出货中。判定必须引用具体日期和量能。
【第三层·消息核验与预期差】对每个上涨理由排序：硬逻辑（公告级）还是软逻辑（题材沾边）。重点挖预期差。
【第四层·题材拆解 + 建仓痕迹 + 暗线深挖】列业务分层表。必须写：有没有前期建仓痕迹（横盘吸筹/挖坑洗盘/红肥绿瘦）、上方筹码是否真空。按暗线业务深挖铁律完整挖：本质（一句话大白话，禁标签糊弄）→暗线业务（具体产品+进展阶段+产业链环节+卡位壁垒+对业绩真实贡献，挖不出写「未见明确暗线业务」，禁「相关/涉及/布局/受益于」糊弄）→真实关联与弹性（实受益/沾边/纯蹭+弹性大小）→为什么是它→破灭点→动作（触发条件+失效）。
【第五层·关键价位 + 主力成本区】上方压力、下方支撑、证伪线。明确主力大概成本区。
【第六层·操作判定】操作评级：持有/加仓条件/减仓触发/止损，全部绑定具体价位和主力阶段。明日预案分三种情况写全。
【输出格式】按六层顺序输出，每层用小标题；每个关键判断后跟👉大白话一句。每层内容用连贯的大白话段落讲清楚（不是条目堆砌、不是问答）。结尾总评一段 + "不构成投资建议"。'''

# ============ 六层深度分析器 DEEP6（2026-10-28 用户模型） ============
def _DEEP6_SYS_text():
    """六层深度分析系统提示词。"""
    return DEEP6_SYS.replace('_HARD_FILTER_RULES_', _HARD_FILTER_RULES)


def _deep6_collect(code, name=''):
    """六层数据收集：快照+K线12日+F10主营+新闻+涨停池状态。失败字段=未取得，绝不编造。"""
    sym = ('sh' if str(code).startswith('6') else 'sz') + str(code)
    q = {}
    try:
        f = _get('http://qt.gtimg.cn/q=' + sym, encoding='gbk').split('~')
        if len(f) > 50:
            q = {'name': f[1], 'price': float(f[3]), 'prev': float(f[4]), 'open': float(f[5]),
                 'high': float(f[41] or f[33] or 0), 'low': float(f[42] or f[34] or 0),
                 'pct': float(f[32] or 0), 'vol': float(f[6] or 0),
                 'amt': float(f[37] or 0), 'turn': float(f[38] or 0),
                 'lb': float(f[43] or 0), 'float_mv': float(f[44] or 0),
                 'amp': (float(f[33] or 0) - float(f[34] or 0)) / float(f[4] or 1) * 100}
    except Exception:
        q = {}
    arr = []
    try:
        arr = get_klines(sym, 16)
    except Exception:
        pass
    f10 = ''
    try:
        f10 = _stock_f10(code) or ''
    except Exception:
        pass
    inc = ''
    try:
        inc = _stock_income(code) or ''
    except Exception:
        pass
    nws = []
    try:
        nws = _stock_news(name or q.get('name') or '', code)[:5]
    except Exception:
        pass
    zt = ''
    try:
        for _x in _follow_pool(datetime.now().strftime('%Y%m%d')):
            if str(_x.get('c')) == str(code):
                zt = '今日涨停%d连板（首封%s）' % (int(_x.get('lbc') or 1), _x.get('fbt') or '')
                break
    except Exception:
        pass
    return {'q': q, 'klines': arr[-12:], 'f10': f10, 'inc': inc, 'news': nws, 'zt': zt}


def _deep_six(code, name=''):
    """六层深度分析主入口：数据收集→LLM六层→渲染HTML。失败返回''（调用方兜底不打断推送）。"""
    if not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return ''
    c = _deep6_collect(code, name)
    q = c.get('q') or {}
    if not q:
        return ''
    # 最终版硬性筛选（13条，2026-11-02）：不满足 → 直接输出「未通过硬性筛选，不做深度分析」并结束
    _ok, _rs = _hard_filter_pass(code, q.get('name') or name, q.get('price'),
                                 industry=_stock_industry(code))
    if not _ok:
        print(f'[deep6] 硬性筛选未通过 {code}: {_rs}')
        return _deep6_reject_html(code, q.get('name') or name, _rs)
    klines_txt = '；'.join('%s 开%s 收%s 高%s 低%s 量%s' % (r[0], r[1], r[2], r[3], r[4], r[5]) for r in c['klines']) or '未取得'
    data = (
        '个股：%s(%s)%s\n'
        '盘中快照（截至最新）：现价%s 涨跌幅%s%% 量比%s 换手%s%% 成交额%s亿 今开%s 最高%s 最低%s 昨收%s 流通市值%s亿 振幅%s%%\n'
        '近12个交易日逐日K线：%s\n'
        '主营业务F10：%s\n'
        '主营构成：%s\n'
        '个股新闻：%s\n'
        '涨停池状态：%s\n'
        '数据时点：盘中快照，非收盘数据。' % (
            q.get('name') or name, code, ('（' + c['zt'] + '）') if c['zt'] else '',
            q.get('price', '未取得'), q.get('pct', '未取得'), q.get('lb', '未取得'),
            q.get('turn', '未取得'), round((q.get('amt') or 0) / 10000, 2),
            q.get('open', '未取得'), q.get('high', '未取得'), q.get('low', '未取得'),
            q.get('prev', '未取得'), round(q.get('float_mv') or 0, 1), q.get('amp', '未取得'),
            klines_txt, (c['f10'] or '未取得')[:200], (c['inc'] or '未取得')[:200],
            ('；'.join(str(x) for x in c['news'][:5]) or '未取得'), (c['zt'] or '未涨停/未入池')))
    payload = {'task': 'deep6', 'data': data}
    txt = ask_deepseek(payload, purpose='deep6', system_text=_DEEP6_SYS_text())
    if not txt or len(txt.strip()) < 50:
        return ''
    return _deep6_html(txt)


def _deep6_html(t):
    """六层文本渲染：小标题金标、大白话行青标、正文白字。"""
    import html as _h
    out = []
    for ln in (t or '').split('\n'):
        s = ln.strip()
        if not s:
            continue
        esc = _h.escape(s)
        if s.startswith('【第') and '·' in s:
            out.append('<div style="font-size:14px;font-weight:900;color:' + GOLD + ';margin-top:8px;">' + esc + '</div>')
        elif s.startswith('👉') or s.startswith('大白话'):
            out.append('<div style="color:' + TEAL + ';font-size:13px;margin:2px 0;">' + esc + '</div>')
        elif s.startswith('总评') or s.startswith('定性'):
            out.append('<div style="font-size:13px;font-weight:800;color:' + GOLD + ';margin-top:8px;">' + esc + '</div>')
        else:
            out.append('<div style="color:#e9ecef;font-size:13px;line-height:1.65;margin:2px 0;">' + esc + '</div>')
    return ('<div style="background:#17212b;border:2px solid ' + GOLD + ';border-radius:12px;padding:12px 14px;margin:10px 0;">'
            '<div style="font-size:15px;font-weight:900;color:' + GOLD + ';">🔬 个股深度六层分析</div>'
            + ''.join(out) + '</div>')

def _deep6_for_spot(spot_out, sel):
    """从伏击推演结果解析被点名的未涨停代表股 → 六层深析HTML。限1只（LLM额度保护）。"""
    if not spot_out or not sel:
        return ''
    txt = ''
    if isinstance(spot_out, dict):
        _g = spot_out.get('_global')
        if _g:
            txt = str(_g)
        else:
            for _k, _v in spot_out.items():
                if _k == '_market' or not isinstance(_v, dict):
                    continue
                txt += str(_k)   # JSON 模式：key 即票名
                for _f in ('logic', 'why', 'op', 'buy', 'stop', 'theme'):
                    if _v.get(_f):
                        txt += str(_v[_f])
    if not txt:
        return ''
    hit = None
    for _, _sg in sel:
        _nm = str(_sg.get('n') or '')
        if _nm and _nm in txt:
            try:
                _pct = float(_sg.get('pct') or 0)
            except (TypeError, ValueError):
                _pct = 0
            if _pct < 9.5:      # 未涨停（涨停票只作热度证据，不跑买入型深析）
                hit = _sg
                break
    if not hit:
        return ''
    

def build_deep6(code=''):
    """🔬 个股深度六层槽位：指定代码或自动挑当日非涨停强势股 → 六层深析。
    返回 inner HTML 或 ''（调用方 _wrap 包卡头推送）。"""
    code = str(code or '').strip()
    name = ''
    if not code:
        try:
            rows = _clist_gainers()
        except Exception:
            rows = []
        pick = None
        for r in rows:
            try:
                pct = float(r.get('pct') or 0)
                if 3.0 <= pct < 9.5 and float(r.get('lb') or 0) >= 1.5:
                    pick = r
                    break
            except (TypeError, ValueError):
                continue
        if not pick and rows:
            for r in rows:
                try:
                    if float(r.get('pct') or 0) < 9.5:
                        pick = r
                        break
                except (TypeError, ValueError):
                    continue
        if not pick:
            return ''
        code = str(pick.get('code') or '')
        name = str(pick.get('name') or '')
    else:
        try:
            sym = ('sh' if code.startswith('6') else 'sz') + code
            f = _get('http://qt.gtimg.cn/q=' + sym, encoding='gbk').split('~')
            if len(f) > 5:
                name = f[1]
        except Exception:
            pass
    if not code:
        return ''
    return _deep_six(code, name)

ZSYS = '''你是主力建仓痕迹研判模型。输入是扫描器命中池和今日热点板块榜。你的任务：逐只识别建仓手法、匹配建仓模式、判断序列阶段、评估锚与洗盘质量、判断板块共振与主线归属、讲清底层逻辑、剔除确认假信号、排出最值得跟踪的观察名单。输出仅作概率研判和观察参考，不构成投资建议。
【执行顺序·强制】
第一步：硬性筛选出股票池（13条，不满足不得进入 radar）。
_HARD_FILTER_RULES_
第二步：在池子里按原规则 + 暗线深挖推送。
【一、输入数据与边界】只依据输入数据和产业链知识，不得虚构。字段缺失标"未取得/未知"。
【二、红线】建仓痕迹是概率证据，不是买入信号。当日涨幅>=7%或涨停的票一律不得进入 radar。禁止编造绝对量能数字。观察条件只能用"价格锚+相对量能"。
【三、硬门槛与过滤】涨幅红线、确认假信号、流动性枯竭直接excluded；现价<5日均线（含未站上5日线）的票不得进入radar，保留judged_all并注明「未站上5日线」（用户铁律：只做站上或回踩5日线企稳的票）；当日涨幅>=7%或涨停直接excluded。
【四、逐只研判·九问】手法归类 + 四模式匹配；突破日验收；回抽洗盘判定；建仓成本区 + 锚质量；板块题材共振；主线归属；二次突破与序列阶段；回踩买点五条；底层逻辑 + 题材催化 + 离场规则。
【五、质量评分表】锚质量、板块共振、利好新鲜度、洗盘质量、二次突破量型。质量分→观察优先级参考（非投资建议）。
【六、暗线业务深挖·每只必做】先写本质（一句话大白话，禁标签糊弄）→ 暗线业务（具体产品+进展阶段+产业链环节+卡位壁垒+对业绩真实贡献，挖不出写「未见明确暗线业务」，禁「相关/涉及/布局/受益于」糊弄）→ 真实关联与弹性（与今日最强题材实受益/沾边/纯蹭+弹性大小）→ 为什么是它 → 破灭点 → 动作（触发条件+失效）。通过筛选但暗线不硬的，写入 excluded 或明确不推。
【七、输出前自问】如果今天不推这只票，最硬的理由是什么？理由成立就写不推。
【输出】必须是完整闭合的 JSON 对象（meta / radar / judged_all / excluded），radar 最多3只，radar 内每只必须含暗线逻辑摘要。
【六、输出JSON】完整结构保持原样（meta/radar/judged_all/excluded），radar最多3只，judged_all精简字段，全篇控制在合理字数，必须完整闭合，禁止截断。'''


def _sina_sector_pct():
    """新浪行业板块当日行情。返回 {板块名: {'pct':涨跌幅%, 'cnt':成分数}}，失败返回 {}。"""
    try:
        txt = _get('http://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php', encoding='gbk', timeout=12)
        m = re.search(r'= (\{.*\})', txt, re.S)
        if not m:
            return {}
        d = json.loads(m.group(1))
        out = {}
        for v in d.values():
            f = v.split(',')
            if len(f) >= 6 and len(f[1]) > 1:
                try:
                    out[f[1]] = {'pct': float(f[5]), 'cnt': int(f[2])}
                except Exception:
                    pass
        return out
    except Exception:
        return {}


def _sector_pct_for(theme, sec_map):
    """theme→板块涨跌幅：精确匹配→子串匹配（前2字）→None。"""
    if not theme or not sec_map:
        return None
    if theme in sec_map:
        return sec_map[theme]
    for nm, v in sec_map.items():
        if len(theme) >= 2 and theme[:2] in nm:
            return v
        if len(nm) >= 2 and nm[:2] in theme:
            return v
    return None


def _repair_json(s):
    """截断 JSON 容错：剥掉尾部残缺 token → 按括号深度补全 → 解析。成功返回对象，失败返回 None。"""
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    def _try(cand):
        try:
            return json.loads(cand)
        except Exception:
            return None
    # 第一遍：原样补全
    r = _try(s)
    if r is not None:
        return r
    # 第二遍：剥到最后一个逗号（丢掉残缺 token）再补全
    for _attempt in range(2):
        cut = s.rfind(',')
        if cut <= 0:
            break
        s = s[:cut]
        r = _try(s)
        if r is not None:
            return r
        stack = []
        in_str, esc = False, False
        for ch in s:
            if in_str:
                if esc:
                    esc = False
                elif ch == '\\':
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch in '{[':
                stack.append('}' if ch == '{' else ']')
            elif ch in '}]' and stack:
                stack.pop()
        out = s
        for _ in range(len(stack) + 2):
            r = _try(out)
            if r is not None:
                return r
            if stack:
                out += stack.pop()
            else:
                break
    return None


def _extract_zscan_lists(_j):
    """从 LLM JSON 对象提取 (radar, judged_all, excluded, meta)，兼容 V4 主结构与旧嵌套结构。"""
    radar = [x for x in (_j.get('radar') or _j.get('radar_data') or _j.get('stocks') or _j.get('analysis_items')
                         or _j.get('selected_stocks') or []) if isinstance(x, dict) and (x.get('code') or x.get('stock_code') or x.get('symbol'))]
    judged_all = [x for x in (_j.get('judged_all') or []) if isinstance(x, dict)] if isinstance(_j.get('judged_all'), list) else []
    excluded = [x for x in (_j.get('excluded') or []) if isinstance(x, dict)] if isinstance(_j.get('excluded'), list) else []
    meta = _j.get('meta') if isinstance(_j.get('meta'), dict) else {}
    _rr = _j.get('radar_report') if isinstance(_j.get('radar_report'), dict) else {}
    if not radar:
        radar = [x for x in (_rr.get('selected_stocks') or _rr.get('stocks') or [])
                 if isinstance(x, dict) and (x.get('code') or x.get('stock_code') or x.get('symbol'))]
    if not radar:
        for _v in _j.values():
            if isinstance(_v, list) and _v and isinstance(_v[0], dict) and ('code' in _v[0] or 'stock_code' in _v[0]):
                radar = [x for x in _v if isinstance(x, dict)]
                break
            if isinstance(_v, dict):
                for _v2 in _v.values():
                    if isinstance(_v2, list) and _v2 and isinstance(_v2[0], dict) and ('code' in _v2[0] or 'stock_code' in _v2[0]):
                        radar = [x for x in _v2 if isinstance(x, dict)]
                        break
                if radar:
                    break
    return radar, judged_all, excluded, meta


def _divergence_label(hh, theme, sec_map, hot_board):
    """补丁5: 板块-个股背离校验。返回标签或 ''。
    抗跌: 板块跌>1% 且个股缩量抗跌(跌幅<0.5%或收红、量<0.8x)
    借势出货嫌疑: 板块涨>2% 且个股放量收阴(量>1.2x)
    补涨候选: 板块涨停>=5只 且个股涨幅<1%、红肥绿瘦合格"""
    sp = _sector_pct_for(theme, sec_map)
    kb = hh.get('kline_brief') or []
    if len(kb) < 2:
        return ''
    last, prev = kb[-1], kb[-2]
    try:
        stk_pct = float(last.get('pct') or 0)
        vol_now = last.get('vol_wan') or 0
        vol_prev = prev.get('vol_wan') or 0
        vr = (vol_now / vol_prev) if vol_prev else 0
    except Exception:
        return ''
    hb = None
    for b in hot_board:
        if theme and (theme[:2] in b['sec'] or b['sec'][:2] in theme):
            hb = b
            break
    if sp and sp.get('pct') is not None:
        b_pct = sp['pct']
        if b_pct < -1 and stk_pct < 0.5 and stk_pct > -0.5 and vr < 0.8:
            return '🛡️抗跌（板块跌%.1f%%个股缩量扛住=锁仓证据）' % b_pct
        if b_pct > 2 and stk_pct < -0.5 and vr > 1.2:
            return '⚠️借势出货嫌疑（板块涨%.1f%%个股放量收阴，剔除观察）' % b_pct
    if hb and hb['cnt'] >= 5 and stk_pct < 1 and hh.get('red_green_ratio'):
        return '🚀补涨候选（板块涨停%d只个股滞涨，等放量>1.5x触发）' % hb['cnt']
    return ''


def build_zscan(limit=None):
    """主力雷达：全市场六条件扫描→LLM四问研判→Top5推送（独立槽位 zscan）。
    LLM 失败/用尽→规则降级（按评分推 Top5 基础信息）。返回 inner HTML 或 ''。"""
    try:
        import zhu_force_scan as ZF
    except Exception as e:
        print('[zscan] 扫描器导入失败:', e)
        return ''
    trade_date = _last_trade_date()
    out = os.path.join(os.path.dirname(ALERT_PATH) if 'ALERT_PATH' in globals() else '.', 'zhu_force_%s.json' % trade_date.replace('-', ''))
    try:
        hits = ZF.run_scanner(end_date=trade_date, limit=limit, out=out)
    except Exception as e:
        print('[zscan] 扫描异常:', e)
        return ''
    if not hits:
        return '<div style="color:' + GREY + ';font-size:13px;">今日无建仓痕迹票（六条件扫描 0 命中）</div>'
    # —— 板块题材共振：涨停池按板块聚合，命中票硬判共振加分 ——
    hot_board, res_bonus, _by_sec = [], {}, defaultdict(list)
    _c2sec = {}
    try:
        _pool = _follow_pool(trade_date.replace('-', ''))
        if _pool:
            _by_sec = defaultdict(list)
            for x in _pool:
                _sec = _sec_clean(x.get('hybk') or '') or '其他'
                _by_sec[_sec].append(x)
            hot_board = [{'sec': k, 'cnt': len(v)} for k, v in
                         sorted(_by_sec.items(), key=lambda kv: -len(kv[1]))[:8]]
            _c2sec = {str(x.get('c')): (_sec_clean(x.get('hybk') or '') or '其他') for x in _pool}
            for h in hits:
                _sc = _c2sec.get(str(h['code']))
                if _sc and _sc in _by_sec:
                    _cnt = len(_by_sec[_sc])
                    res_bonus[h['code']] = 15 if _cnt >= 5 else 10 if _cnt >= 3 else 5 if _cnt >= 1 else 0
        else:
            print('[zscan] 涨停池未取到，板块共振分跳过')
            _c2sec = {}
    except Exception as e:
        print('[zscan] 板块共振计算异常:', e)
        _c2sec = {}
    # 加权分（含板块共振加分）重排序
    for h in hits:
        h['res_bonus'] = res_bonus.get(h['code'], 0)
        h['score_w'] = int(h['score']) + h['res_bonus']
    # FIX16: LLM 输入前双保险——当日涨跌幅>=7% 剔除（防旧JSON缓存/扫描器漏网）
    _bf = len(hits)
    hits = [h for h in hits if abs(float((h.get('kline_brief') or [{}])[-1].get('pct') or 0)) < 7.0]
    if len(hits) != _bf:
        print(f'[zscan] FIX16涨幅过滤: 剔除 {_bf - len(hits)} 只 (当日|涨跌|>=7%)')
    # 最终版硬性筛选（13条，2026-11-02 定稿）：不满足直接剔除，不再进 LLM 池
    _bh = len(hits)
    _hf_ok, _hf_rej = [], []
    for _h in hits:
        _ok, _rs = _hard_filter_pass(_h['code'], _h.get('name', ''), _h.get('price'),
                                     industry=_c2sec.get(str(_h['code'])) or _h.get('industry') or '')
        if _ok:
            _hf_ok.append(_h)
        else:
            _hf_rej.append((_h.get('name'), _h['code'], _rs))
    if _hf_rej:
        print(f'[zscan] 硬性筛选剔除 {len(_hf_rej)} 只: ' + '；'.join('%s(%s)%s' % x for x in _hf_rej[:15]))
    hits = _hf_ok
    hits.sort(key=lambda h: -h['score_w'])
    # —— 补丁5: 板块-个股背离校验数据源 ——
    _sec_map = _sina_sector_pct()
    if not _sec_map:
        print('[zscan] 新浪板块行情未取到，背离校验跳过')
    # —— LLM 研判（V4 输入 schema：pool 数组 + hot_sectors + 历史榜空数组）——
    brief = '\n'.join(
        '- %s(%s) 现价%s 评分%s(+板块共振%s) 所属板块:%s 命中条件%s 手法:%s 扫描器分类:%s(%s) 箱体%s-%s 锚%s 证伪%s 换手%s%% 下一信号:%s 近12日K线:%s' % (
            h['name'], h['code'], h['price'], h['score_w'], h['res_bonus'],
            _c2sec.get(str(h['code'])) or h.get('industry') or '未取得',
            h['hit_conditions'], h['method'],
            h.get('method_type') or '未分类', h.get('state') or '',
            h['box_low'], h['box_high'], h['anchor'], h['falsify_line'],
            h.get('avg_turn') or '未取得',
            h.get('next_watch') or '未取得',
            ' '.join('%s:%s%%/%s万股' % (k['d'], k['pct'], k['vol_wan']) for k in h['kline_brief'])) for h in hits[:30])
    hot_txt = '；'.join('%s(%s家涨停)' % (b['sec'], b['cnt']) for b in hot_board) or '未取得'
    _pool_in = []
    for h in hits[:30]:
        _kb = h.get('kline_brief') or []
        _last = _kb[-1] if _kb else {}
        _sc = _c2sec.get(str(h['code'])) or h.get('industry') or '未取得'
        _pool_in.append({
            'code': h['code'], 'name': h['name'], 'close': float(h.get('price') or 0),
            'pct_chg': float(_last.get('pct') or 0), 'limit_up': False,
            'kline_summary': '近12日K线: %s' % (' '.join('%s:%s%%/%s万股' % (k['d'], k['pct'], k['vol_wan']) for k in _kb) or '未取得'),
            'condition_hits': h['hit_conditions'], 'scan_score': int(h.get('score_w') or h.get('score') or 0),
            'method_type': h.get('method_type') or '未分类', 'state': h.get('state') or '',
            'sector': _sc,
            'sector_limit_up_count': len(_by_sec.get(_sc, [])) if _c2sec else 0,
            'sector_rise2pct_count_on_ignition_day': None,   # 数据源未接入：LLM 按红线3标数据不足
            'announcements_10d': [], 'news_today': [],
            'liquidity_flag': '未知', 'liquidity_percentile': None,
            'ma5': h.get('ma5'), 'above_ma5': bool(h.get('above_ma5', False)),
        })
    _hot_sectors_in = [{'sector': b['sec'], 'rank': i + 1, 'limit_up_count': b['cnt']} for i, b in enumerate(hot_board)]
    payload = {'task': 'zforce_radar', 'scan_date': trade_date,
               'hits_count': len(hits), 'hits_brief': brief,
               'hot_themes': hot_txt,
               'hot_sectors': _hot_sectors_in,
               'hot_sector_history_7d': [],   # 历史热点榜数据源未接入：LLM 按红线3标数据不足，不硬判
               'pool': _pool_in,
               'format': '按系统提示词逐只九问研判命中池，输出 meta/radar/judged_all/excluded 完整 JSON 对象（radar 最多3只）。'}
    t = ask_deepseek(payload, purpose='zforce_radar', system_text=ZSYS.replace('_HARD_FILTER_RULES_', _HARD_FILTER_RULES))
    radar, _judged_all, _excluded, _meta = [], [], [], {}
    _hmap = {h['code']: h for h in hits}
    if t:
        _t = (t or '').strip()
        try:
            _st = _t.strip()
            _i, _j2 = _st.find('{'), _st.rfind('}')
            # 纯数组结构优先：整体以[开头]结尾即为裸数组（LLM 常输出裸数组，原逻辑截{..}只剩首票导致解析失败降级）
            if _st.startswith('[') and _st.endswith(']'):
                _arr = json.loads(_st)
                radar = [x for x in _arr if isinstance(x, dict) and (x.get('code') or x.get('stock_code') or x.get('symbol'))]
                _j = {}
            else:
                if _i >= 0 and _j2 > _i:
                    _st = _st[_i:_j2 + 1]
                _j = json.loads(_st)
                radar, _judged_all, _excluded, _meta = _extract_zscan_lists(_j)
        except Exception as e:
            print('[zscan] radar JSON 解析失败:', str(e)[:80])
            # FIX20 容错：截断 JSON 修复（V4 长 schema 易被 max_tokens 截断）
            _jf = _repair_json(_t)
            if _jf is not None:
                print('[zscan] 截断JSON修复成功（保留已解析部分）')
                _j = _jf
                radar, _judged_all, _excluded, _meta = _extract_zscan_lists(_j)
        # 字段映射（LLM 可能用自定义字段名/嵌套 data_traceability）
        if radar:
            for r in radar:
                c = r.get('code') or r.get('stock_code') or r.get('symbol') or ''
                hh = _hmap.get(c) or {}
                dt = r.get('data_traceability') if isinstance(r.get('data_traceability'), dict) else {}
                r.setdefault('name', r.get('name') or r.get('stock_name') or hh.get('name') or c)
                r.setdefault('method', r.get('method') or r.get('analysis_detail') or r.get('analysis_logic')
                             or r.get('main_reason') or r.get('single_main_reason') or r.get('unique_main_reason')
                             or r.get('operation_status') or hh.get('method') or '')
                _dt = r.get('data_trace') or r.get('data_evidence')
                if _dt and r.get('method'):
                    r['method'] = str(r['method']) + '；' + str(_dt)
                r.setdefault('cost_zone', r.get('cost_zone') or r.get('box_range') or dt.get('box_range')
                             or (('锚' + str(r.get('anchor_price') or dt.get('anchor_price'))) if (r.get('anchor_price') or dt.get('anchor_price')) else '')
                             or str(hh.get('anchor') or ''))
                r.setdefault('credibility', r.get('credibility') or r.get('confidence') or '中')
                r.setdefault('bottom_logic', r.get('bottom_logic') or r.get('logic') or r.get('core_logic')
                             or r.get('underlying_logic') or r.get('business_logic')
                             or r.get('analysis') or r.get('logic_analysis') or r.get('logic_anchor')
                             or ('模型未输出产业链逻辑。客观数据：现价' + str(hh.get('price') or '') + '元，箱体' + str(hh.get('box_low') or '') + '-' + str(hh.get('box_high') or '') + '，评分' + str(hh.get('score') or '') + '，换手' + str(hh.get('avg_turn') or '未取得') + '%。主营与产业链信息不在输入内。'))
                _hindu = hh.get('industry') if hh.get('industry') not in ('其他', '') else ''
                _reson = r.get('resonance') or r.get('resonance_level') or r.get('board_strength')
                _ana_txt = str(r.get('analysis') or '') + '；' + str(r.get('main_reason') or '') + '；' + str(r.get('method') or '') + '；' + str(r.get('logic_anchor') or '')
                _cntm = re.search(r'(\d+)\s*家涨停', _ana_txt)
                if _cntm and not _reson:
                    _rc = int(_cntm.group(1))
                    _reson = '强' if _rc >= 5 else '中' if _rc >= 3 else '弱'
                if not _reson:
                    _reson = ('强' if hh.get('res_bonus', 0) >= 15 else '中' if hh.get('res_bonus', 0) >= 5 else '弱' if hh.get('res_bonus', 0) else '未判')
                _thm = r.get('theme') or r.get('sector') or r.get('sector_theme') or r.get('belong_theme') or _hindu
                if not _thm:
                    _thm2 = re.search(r'(?:同属|属于|为|是)?([\u4e00-\u9fa5]{2,8}?)(?:方向|板块|概念|链)[\s\S]*?(\d+)\s*家涨停', _ana_txt)
                    if _thm2:
                        _thm = _thm2.group(1)
                r.setdefault('theme', _thm or '')
                r.setdefault('resonance', _reson)
                r.setdefault('theme_status', r.get('theme_status') or r.get('main_line') or r.get('mainline_status') or '未判')
                r.setdefault('ignite_theme', r.get('ignite_theme') or r.get('theme') or hh.get('industry') or '')
                r.setdefault('next_watch', r.get('next_watch') or r.get('watch_signal') or r.get('entry_trigger')
                             or r.get('entry_trigger_condition') or r.get('action_plan') or r.get('unique_wait_condition')
                             or r.get('specific_trigger') or r.get('wait_condition') or r.get('trigger')
                             or r.get('trigger_condition') or r.get('action_condition') or r.get('condition')
                             or '放量突破' + str(hh.get('box_high') or '') + '=建仓完成确认')
                _fr = r.get('false_alarm_risk') or r.get('risk') or r.get('risk_point')
                if not _fr and (r.get('stop_loss') or r.get('stop_loss_level') or r.get('falsification_point') or dt.get('falsify_price')):
                    _fr = ('止损' + str(r.get('stop_loss') or r.get('stop_loss_level') or dt.get('falsify_price'))) + \
                          ('；证伪' + str(r.get('falsification_point') or dt.get('falsify_price')))
                r.setdefault('false_alarm_risk', _fr)
                # V4 字段兜底映射（LLM 输出 V4 规范字段，缺失时从旧字段/命中池兜底）
                for _k, _alts in (('pattern_match', ('pattern_match', 'pattern', 'mode_match')),
                                  ('pattern_basis', ('pattern_basis',)),
                                  ('sequence_stage', ('sequence_stage', 'stage_phase', 'stage')),
                                  ('anchor_price', ('anchor_price',)),
                                  ('anchor_type', ('anchor_type',)),
                                  ('anchor_quality_score', ('anchor_quality_score',)),
                                  ('cost_basis', ('cost_basis',)),
                                  ('quality_total', ('quality_total', 'total_score', 'quality_score')),
                                  ('observation_priority', ('observation_priority',)),
                                  ('position_ref', ('position_ref',)),
                                  ('exit_rule', ('exit_rule', 'exit_rule_plan')),
                                  ('method_review', ('method_review',)),
                                  ('false_alarm_status', ('false_alarm_status',)),
                                  ('rank_score', ('rank_score',)),
                                  ('rank_reason', ('rank_reason',)),
                                  ('scan_score', ('scan_score',)),
                                  ('resonance_basis', ('resonance_basis',)),
                                  ('theme_status_basis', ('theme_status_basis',))):
                    if r.get(_k) is None:
                        for _a in _alts:
                            if r.get(_a) is not None:
                                r[_k] = r[_a]
                                break
                for _k in ('breakout_check', 'washout_check', 'second_breakout', 'pullback_check', 'quality_score_detail'):
                    if r.get(_k) is None:
                        r[_k] = {}
                if not r.get('sequence_stage'):
                    r['sequence_stage'] = '找锚中'
                if r.get('quality_total') is None:
                    r['quality_total'] = int(hh.get('score_w') or hh.get('score') or 0)
                _eg = r.get('evidence_gaps')
                if isinstance(_eg, list):
                    r['evidence_gaps'] = '；'.join(str(x) for x in _eg) if _eg else '无'
    if not radar:
        # 用户硬约束：LLM 未返回时禁止用规则字段拼研判结论，只列客观数据事实
        print('[zscan] LLM 未返回，已禁规则版兜底（不拼四问结论）')
        _fact = ''.join(
            '<div style="color:#ced4da;font-size:12px;margin:3px 0;">• %s(%s) %s｜评分%s｜现价%s｜箱体%s~%s｜换手%s%%</div>'
            % (h.get('name') or '', h.get('code') or '', h.get('method') or '',
               int(h.get('score_w') or h.get('score') or 0), h.get('price') or '-',
               h.get('box_low') or '-', h.get('box_high') or '-', h.get('avg_turn') or '-')
            for h in hits[:5])
        return ('<div style="font-size:15px;font-weight:900;color:' + GOLD + ';">🛰 主力雷达 · 建仓痕迹</div>'
                + _fact)
    # FIX16: 渲染前终拦——LLM 越权补票兜底（当日涨幅>=7% 剔除并从命中池补位）
    def _r_pct(r):
        for _k in ('daily_change_percent', 'daily_change', 'pct', 'change_percent'):
            _v = r.get(_k)
            if _v is not None:
                try:
                    return float(_v)
                except (TypeError, ValueError):
                    return 0.0
        return 0.0
    _pr = len(radar)
    radar = [r for r in radar if abs(_r_pct(r)) < 7.0]
    if len(radar) != _pr:
        print(f'[zscan] FIX16渲染终拦: 剔除 {_pr - len(radar)} 只已大涨票，从命中池补位')
        if hits:
            _used = {r.get('code') for r in radar}
            for h in hits:
                if len(radar) >= 5:
                    break
                if h['code'] in _used:
                    continue
                radar.append({'code': h['code'], 'name': h['name'], 'method': h['method'],
                              'cost_zone': str(h['anchor']), 'credibility': '中(规则补位)',
                              'ignite_theme': h['industry'],
                              'next_watch': '放量突破' + str(h['box_high']) + '=建仓完成确认',
                              'false_alarm_risk': '涨幅过滤补位'})
    # —— 渲染：主力雷达卡（V4 版式） ——
    lines = ['<div style="font-size:15px;font-weight:900;color:' + GOLD + ';">🛰 主力雷达 · 建仓痕迹（' + str(len(hits)) + ' 只扫描命中，Top' + str(len(radar)) + '）</div>',
             '<div style="margin-top:2px;font-size:12px;color:' + GREY + ';">数据日 ' + trade_date + '：六条件扫描 → 板块共振加权 → 模型九问研判（建仓手法/四模式/序列阶段/锚与洗盘质量/底层逻辑）</div>',
             '<div style="margin-top:4px;font-size:12px;color:' + RED + ';">🔥 今日热点板块（涨停家数）：' + (('；'.join('%s(%s家)' % (b['sec'], b['cnt']) for b in hot_board)) if hot_board else '未取得') + '</div>']
    def _strip_abs_vol(t):
        """量能红线渲染终拦：剔除 LLM 输出的绝对量能数字（万手/万股/万元/亿），保留相对表述与价格锚。"""
        if not t:
            return t
        t = str(t)
        t = re.sub(r'成交金额超?\s*\d+(?:\.\d+)?\s*万元', '大单放量确认', t)
        t = re.sub(r'成交量\s*\d+(?:\.\d+)?\s*万股?', '成交量放量', t)
        t = re.sub(r'\d+(?:\.\d+)?\s*(?:万手|万股|万元|亿元|亿股|手)', '', t)
        t = re.sub(r'\s{2,}', ' ', t).strip(' ，。、；')
        return t
    def _bc(r, k, d=''):
        v = r.get(k) or {}
        return str(v.get(d) or '') if isinstance(v, dict) else ''
    def _pr(r, k):
        v = r.get(k) or {}
        return v.get('verdict') if isinstance(v, dict) and v.get('verdict') else '数据不足'

    for r in radar[:5]:
        for _k in ('method', 'cost_zone', 'bottom_logic', 'ignite_theme', 'next_watch', 'false_alarm_risk',
                   'theme', 'reason', 'condition', 'risk', 'observation_logic', 'trigger_condition',
                   'data_trace', 'logic', 'why', 'pattern_basis', 'exit_rule', 'method_review',
                   'resonance_basis', 'theme_status_basis', 'cost_basis', 'rank_reason'):
            if r.get(_k):
                r[_k] = _strip_abs_vol(r[_k])
        c = r.get('code') or r.get('stock_code') or ''
        nm = r.get('name') or r.get('stock_name') or ''
        cred = str(r.get('credibility') or '中')
        hh2 = _hmap.get(c) or {}
        cred_c = '#52c41a' if cred.startswith('高') else '#ffd43b' if cred.startswith('中') else '#ff6b6b'
        _dvg = _divergence_label(hh2, str(r.get('theme') or ''), _sec_map, hot_board)
        _qt = r.get('quality_total') or 0
        _prk = str(r.get('observation_priority') or ('高' if _qt >= 80 else '中' if _qt >= 60 else '低' if _qt >= 40 else '放弃'))
        _prc = '#52c41a' if _prk.startswith('高') else '#ffd43b' if _prk.startswith('中') else '#ff922b' if _prk.startswith('低') else '#ff6b6b'
        _pri = ('观察优先级：' + _prk + '（质量分 ' + str(_qt) + '）｜参考仓位：' + str(r.get('position_ref') or '未取得')) if (_qt is not None) else ('观察优先级：' + _prk)
        _bchk = _pr(r, 'breakout_check')
        _wchk = _pr(r, 'washout_check')
        _bchk_txt = ('收盘站上锚' + _bc(r, 'breakout_check', 'close_above_anchor_pct') + '%｜量能' + _bc(r, 'breakout_check', 'volume_ratio') + '倍｜板块' + _bc(r, 'breakout_check', 'sector_background')) if _bchk != '数据不足' else '突破数据不足'
        _wchk_txt = ('缩量' + _bc(r, 'washout_check', 'volume_shrink_ratio') + '倍｜红肥绿瘦' + _bc(r, 'washout_check', 'red_fat_green_thin')) if _wchk not in ('数据不足无法判定', '') else '洗盘数据不足'
        _sb = r.get('second_breakout') or {}
        _sb_txt = ('已二次突破·' + str(_sb.get('volume_type') or '数据不足')) if (_sb.get('done') if isinstance(_sb, dict) else False) else '未二次突破'
        _pb = r.get('pullback_check') or {}
        _pb_n = len(_pb.get('five_conditions_met') or []) if isinstance(_pb, dict) else 0
        _pb_txt = ('回踩五条满足 %d/%d｜时间窗 %s' % (_pb_n, 5, str(_pb.get('time_window') or '未到'))) if (_pb.get('verdict') if isinstance(_pb, dict) else '') not in ('未到', '', None) else '回踩未到（' + str(_pb.get('verdict') or '未到') + '）'
        lines.append(
            '<div style="margin-top:10px;padding:10px;background:#1c2230;border-left:4px solid ' + GOLD + ';border-radius:8px;">'
            '<div style="font-size:14px;color:#fff;font-weight:700;">' + nm + '（' + c + '）'
            '<span style="margin-left:8px;font-size:11px;color:' + cred_c + ';">可信度' + cred + '</span>'
            '<span style="margin-left:8px;font-size:11px;color:' + _prc + ';">' + _prk + '</span></div>'
            '<div style="font-size:12px;color:' + TEAL + ';margin-top:4px;">建仓手法：' + str(r.get('method') or '') + ('（' + str(hh2.get('method_type') or '') + '·' + str(hh2.get('state') or '') + '）' if hh2.get('method_type') else '') + ('　复核：' + str(r.get('method_review') or '') if r.get('method_review') else '') + ('　✅站上5日线 ' + str(hh2.get('ma5') or '') + '元' if hh2.get('above_ma5') else '') + '</div>'
            '<div style="font-size:12px;color:#66d9e8;margin-top:2px;">模式匹配：' + str(r.get('pattern_match') or '不匹配') + ('｜' + str(r.get('pattern_basis') or '') if r.get('pattern_basis') else '') + '　序列阶段：' + str(r.get('sequence_stage') or '找锚中') + '</div>'
            '<div style="font-size:12px;color:' + GOLD + ';margin-top:2px;">锚：' + str(r.get('anchor_price') or '') + '（' + str(r.get('anchor_type') or '未取得') + '，质量' + str(r.get('anchor_quality_score') or 0) + '分）｜成本区：' + str(r.get('cost_zone') or '') + ('（' + str(r.get('cost_basis') or '') + '）' if r.get('cost_basis') else '') + '</div>'
            '<div style="font-size:12px;color:#e9ecef;margin-top:2px;">突破验收：' + _bchk + '（' + _bchk_txt + '）｜洗盘判定：' + _wchk + '（' + _wchk_txt + '）</div>'
            '<div style="font-size:12px;color:#e9ecef;margin-top:2px;">二次突破：' + _sb_txt + '　' + _pb_txt + '</div>'
            '<div style="font-size:12px;color:#ff6b6b;margin-top:2px;">板块共振：' + str(r.get('theme') or '未判') + '｜强度' + str(r.get('resonance') or '未判') + ('（板块共振+' + str(hh2.get('res_bonus') or 0) + '分）' if hh2.get('res_bonus') else '') + ('　主线：' + ('🔥当前主线' if str(r.get('theme_status') or '').startswith('当前') else '📅近期主线' if str(r.get('theme_status') or '').startswith('近期') else '❄️冷门·仓位减半' if str(r.get('theme_status') or '').startswith('冷门') else str(r.get('theme_status') or ''))) + '</div>'
            '<div style="font-size:12px;color:' + RED + ';margin-top:2px;">底层逻辑：' + str(r.get('bottom_logic') or '未取得') + '</div>'
            '<div style="font-size:12px;color:#e9ecef;margin-top:2px;">👉 观察剧本：' + str(r.get('next_watch') or '') + '</div>'
            '<div style="font-size:12px;color:' + TEAL + ';margin-top:2px;">离场规则：' + str(r.get('exit_rule') or '') + '</div>'
            '<div style="font-size:11px;color:' + GREY + ';margin-top:2px;">' + _pri + '｜假信号：' + str(r.get('false_alarm_status') or '数据不足无法判定') + '｜' + str(r.get('false_alarm_risk') or '') + '｜点火题材预判：' + str(r.get('ignite_theme') or '') + '</div>'
            + ('<div style="font-size:12px;color:#66d9e8;margin-top:2px;">' + _dvg + '</div>' if _dvg else '') + '</div>')
    if _excluded:
        lines.append('<div style="margin-top:8px;font-size:11px;color:#ff6b6b;">🗑 硬剔除：' + '；'.join('%s(%s) %s' % (x.get('name') or '', x.get('code') or '', x.get('exclude_reason') or '') for x in _excluded[:6]) + '</div>')
    if _judged_all:
        lines.append('<div style="margin-top:4px;font-size:11px;color:' + GREY + ';">📋 全池研判 ' + str(len(_judged_all)) + ' 只（含冷门池/数据不足保留，不优先入榜）</div>')
    lines.append('<div style="margin-top:8px;font-size:11px;color:' + GREY + ';">⚠️ 建仓痕迹是概率证据非买入信号；position_ref 仅为观察优先级参考，不构成投资建议；主力雷达票已入火点观察池，等放量点火信号。</div>')
    return ''.join(lines)

def _theme_heat(cands):
    """题材热度：题材内平均竞价涨幅 + 强势家数占比（0~100）。清洗=去掉空值/噪声词。"""
    grp = defaultdict(list)
    for s in cands:
        ind = _sec_clean(s['industry']) or '其他'
        grp[ind].append(s)
    heat, cnt = {}, {}
    for sec, lst in grp.items():
        cnt[sec] = len(lst)
        if sec in ('其他', '热点方向'):
            heat[sec] = 0.0    # 无题材信息的杂毛桶不虚标热度
            continue
        avg_gap = sum(x['pct'] for x in lst) / max(len(lst), 1)
        strong = sum(1 for x in lst if x['pct'] >= (4 if (x.get('board') or ('gem' if x['code'].startswith('300') else 'main')) == 'gem' else 2)) / max(len(lst), 1)
        heat[sec] = min(100.0, avg_gap / 8.0 * 50 + strong * 50)
    return heat, cnt


def _calc_resonance(cands, heat, cnt, mem_days=None, is_tail=False):
    """共振因子（2026-11-05 升级规格）：共振分 = 主题共振(0-40) + 量价共振(0-30) + 板块热度共振(0-30)。
    早盘量能指标=竞价量比归一 vr；尾盘=量比 lb。板块平均在过滤后池内按题材聚合（禁止全市场数据）。
    结果挂 s['_reson']（分数）与 s['_reson_det']（明细，供渲染/提示词）。
    早盘同时预计算 _vr/_avg_vol5/_ref_vol/_pos60/_bars 供 _auction_score_v3 复用（K线全程只拉一次）。"""
    if not cands:
        return cands
    grp = defaultdict(list)
    sec_of = {}
    for s in cands:
        ind = _sec_clean(s['industry']) or '其他'
        grp[ind].append(s)
        sec_of[id(s)] = ind
    # persist 天数：mem_days 近3日该题材出现天数（逐日去重累加，≥2天=持续2天）
    persist_days = defaultdict(int)
    if mem_days:
        for pd, pv in list(mem_days.items())[:3]:
            for sec in set(sec_of.values()):
                if sec in pv:
                    persist_days[sec] += 1
    hot_sorted = [k for k, _ in sorted(heat.items(), key=lambda kv: -kv[1])]
    hot3, hot6 = set(hot_sorted[:3]), set(hot_sorted[:6])
    # 早盘：预计算 vr（竞价量比归一）并缓存 K 线数据，_auction_score_v3 复用
    if not is_tail:
        for s in cands:
            if s.get('_vr') is not None:
                continue
            code = s['code']
            sym = ('sh' if code.startswith('6') else 'sz') + code
            avg_vol5 = ref_vol = 0.0
            bars = []
            try:
                arr = get_klines(sym, 130)
                if arr:
                    today_s = _bj_now().strftime('%Y-%m-%d')
                    b = arr[:-1] if str(arr[-1][0]) == today_s else arr
                    bars = b
                    if len(b) >= 2:
                        h5 = b[-5:]
                        vs = [float(r[5]) for r in h5 if float(r[5]) > 0]
                        avg_vol5 = sum(vs) / len(vs) if vs else 0.0
                        ref_vol = float(b[-1][5])
                        hi60 = max(float(r[3]) for r in b[-60:])
                        lo60 = min(float(r[4]) for r in b[-60:])
                        if hi60 > lo60:
                            s['_pos60'] = (s['price'] - lo60) / (hi60 - lo60)
            except Exception:
                pass
            s['_bars'] = bars
            s['_avg_vol5'] = avg_vol5
            s['_ref_vol'] = ref_vol
            elapsed = _auction_elapsed_minutes()
            expected = avg_vol5 / 240.0 * elapsed if avg_vol5 > 0 and elapsed > 0 else 0.0
            vol = (s['vol'] or 0) * 100.0
            vr = vol / expected if expected > 0 else (s['lb'] or 0)
            s['_vr'] = round(vr, 2)
    # 量价共振：题材内均值 + 个股相对强度
    qmean = {}
    for sec, lst in grp.items():
        if is_tail:
            qmean[sec] = sum(float(x.get('lb') or 0) for x in lst) / max(len(lst), 1)
        else:
            qmean[sec] = sum(float(x.get('_vr') or 0) for x in lst) / max(len(lst), 1)
    pmean = {}
    for sec, lst in grp.items():
        pmean[sec] = sum(float(x['pct'] or 0) for x in lst) / max(len(lst), 1)
    for s in cands:
        sec = sec_of[id(s)]
        q = float(s.get('lb') or 0) if is_tail else float(s.get('_vr') or 0)
        qv = qmean.get(sec, 0.0)
        ratio = (q / qv) if qv > 0 else (1.0 if q > 0 else 0.0)
        s['_qratio'] = round(ratio, 2)
        pm = pmean.get(sec, 0.0)
        pr = (float(s['pct'] or 0) / pm) if pm > 0 else 0.0
        s['_pratio'] = round(pr, 2)
    # 逐票共振分
    for s in cands:
        sec = sec_of[id(s)]
        n = cnt.get(sec, 0)
        if is_tail:
            theme_r = 40 if n >= 4 else (28 if n >= 3 else (15 if n >= 2 else 0))
        else:
            theme_r = 40 if n >= 5 else (28 if n >= 4 else (15 if n >= 3 else 0))
        ratio = s.get('_qratio') or 0
        pr = s.get('_pratio') or 0
        if ratio >= 1.5 and pr >= 0.8:
            vol_r = 30
        elif ratio >= 1.2:
            vol_r = 20
        elif ratio >= 1.0:
            vol_r = 10
        else:
            vol_r = 0
        pd_ = persist_days.get(sec, 0)
        if sec in hot3 and pd_ >= 2:
            hot_r = 30
        elif sec in hot6 and pd_ >= 1:
            hot_r = 18
        elif sec in hot6:
            hot_r = 8
        else:
            hot_r = 0
        s['_reson'] = theme_r + vol_r + hot_r
        s['_reson_det'] = ('主题%d家+量价%.1fx+%s' % (n, ratio, ('前3' if sec in hot3 else ('前6' if sec in hot6 else '冷'))))
    return cands


# ============ 批次D-2：竞价 v3（对齐本地 auction_filter_widget 五因子） ============
_GAP_SCORE_MAIN = (3.0, 4.0, 2.0, 5.0)    # 满分下限/上限、次优下限/上限
_GAP_SCORE_CYB = (6.0, 8.0, 4.0, 10.0)


def _auction_elapsed_minutes():
    """当日已交易分钟数（含竞价5分钟），量比归一化用。对齐本地 _elapsed_trading_minutes。"""
    now = _bj_now()
    hm = now.hour * 60 + now.minute
    t_open, t_close = 9 * 60 + 30, 15 * 60
    if hm < t_open:
        return 5 if hm >= (9 * 60 + 25) else 0
    if hm <= 11 * 60 + 30:
        return 5 + (hm - t_open)
    if hm < 13 * 60:
        return 5 + 120
    if hm <= t_close:
        return 5 + 120 + (hm - 13 * 60)
    return 5 + 240


def _auction_revise(s, vr, pos60, bars):
    """反推修正（日K代理判定，无逐笔分时）。返回 (修正值, 标签)。
    对齐 v3 定义：暴力反抽-20 / 无量反弹-12 / 高位区(60日区间>85%)-5 /
    低位放量启动+8 / 走势平稳+8。高位>100% 由风险扣分单独计，不重复扣。
    注：原「缩量回踩启动+15」依赖昨收≥MA20，随用户指令取消 MA20 限制一并删除。"""
    if not bars or len(bars) < 3:
        return 0.0, ''
    code = s.get('code') or ''
    cyb = code.startswith(('300', '301'))
    gap = s['pct'] or 0
    try:
        y1, y2 = bars[-1], bars[-2]
        c1, v1, v2 = float(y1[2]), float(y1[5]), float(y2[5])
        # 暴力反抽：近2日累计涨幅≥15% 且今日竞价仍高开
        if len(bars) >= 3:
            c3 = float(bars[-3][2])
            if c3 > 0 and (c1 / c3 - 1) * 100 >= 15 and gap >= (5.0 if not cyb else 10.0):
                return -20.0, '暴力反抽'
        # 无量反弹：高开但量不足
        if gap >= 2.0 and vr < 2.0:
            return -12.0, '无量反弹'
        # 高位区：60日区间位置 >85%
        if pos60 is not None and pos60 > 0.85:
            return -5.0, '高位区'
        # 低位放量启动：60日区间低位(<40%) 且 竞价放量 vr≥2（替代原「缩量回踩启动」，不依赖MA20）
        if pos60 is not None and pos60 < 0.4 and vr >= 2.0:
            return 8.0, '低位放量启动'
        # 走势平稳：竞价分时代理「平稳」（高开适中+量比适中）
        sl, sh = (4.0, 6.0) if cyb else (2.0, 3.0)
        if sl <= gap < sh and 2.0 <= vr < 5.0:
            return 8.0, '走势平稳'
    except Exception:
        pass
    return 0.0, ''


def _auction_score_v3(s, heat, cnt, mem_days=None):
    """竞价 v3 综合分 = 量价五因子×0.60 + 题材分×0.20 + 共振分×0.20 − 风险扣分 + 反推修正
    （2026-11-05 共振因子升级：原 0.72/0.28 调整，co20→co10，共振分来自 _calc_resonance）。
    五因子对齐本地 auction_filter_widget._score_volume_price：
    高开幅度20 / 竞价量比(分钟归一)25 / 换手×量比情绪25 / 量能占比(竞价量/昨量)15 / 分时形态代理15。"""
    code = s['code']
    cyb = code.startswith(('300', '301'))
    sym = ('sh' if code.startswith('6') else 'sz') + code
    gap = max(0.0, s['pct'] or 0)
    # —— K线：一次拉 130 根（5日均量/昨量/60日区间/MA20 共用）；共振因子已预拉则直接复用 ——
    bars = None
    avg_vol5 = ref_vol = 0.0
    pos60 = None
    if s.get('_bars') is not None:
        bars = s['_bars']
        avg_vol5 = s.get('_avg_vol5') or 0.0
        ref_vol = s.get('_ref_vol') or 0.0
        pos60 = s.get('_pos60')
    else:
        try:
            arr = get_klines(sym, 130)
            if arr:
                today_s = _bj_now().strftime('%Y-%m-%d')
                b = arr[:-1] if str(arr[-1][0]) == today_s else arr
                bars = b
                if len(b) >= 2:
                    h5 = b[-5:]
                    vs = [float(r[5]) for r in h5 if float(r[5]) > 0]
                    avg_vol5 = sum(vs) / len(vs) if vs else 0.0
                    ref_vol = float(b[-1][5])
                    hi60 = max(float(r[3]) for r in b[-60:])
                    lo60 = min(float(r[4]) for r in b[-60:])
                    if hi60 > lo60:
                        pos60 = (s['price'] - lo60) / (hi60 - lo60)
        except Exception:
            pass
    # 1 高开幅度 20
    o1, o2, s1, s2 = _GAP_SCORE_CYB if cyb else _GAP_SCORE_MAIN
    if o1 <= gap <= o2:
        gap_score = 20
    elif (s1 <= gap < o1) or (o2 < gap <= s2):
        gap_score = 15
    else:
        gap_score = 8
    # 2 竞价量比 25（分钟归一化：竞价量/预期量）
    elapsed = _auction_elapsed_minutes()
    expected = avg_vol5 / 240.0 * elapsed if avg_vol5 > 0 and elapsed > 0 else 0.0
    vol = (s['vol'] or 0) * 100.0   # 手→股
    vr = vol / expected if expected > 0 else (s['lb'] or 0)
    s['_vr'] = round(vr, 2)
    if vr >= 5:
        vr_score = 25
    elif vr >= 3:
        vr_score = 18
    elif vr >= 2:
        vr_score = 10
    else:
        vr_score = 0
    # 3 情绪值 25（换手×量比）
    emo = (s['turn'] or 0) * vr
    if emo >= 12:
        em_score = 25
    elif emo >= 10:
        em_score = 18
    elif emo >= 8:
        em_score = 10
    else:
        em_score = 0
    # 4 量能占比 15（竞价量/昨量）
    vref = vol / ref_vol if ref_vol > 0 else 0.0
    if vref >= 0.5:
        ar_score = 15
    elif vref >= 0.3:
        ar_score = 10
    else:
        ar_score = 5
    # 5 分时形态代理 15
    sh, sl, sf = (6.0, 4.0, 5.0) if cyb else (3.0, 2.0, 2.5)
    if gap >= sh and vr >= 5:
        shape_score, shape = 15, '红柱递增'
    elif gap >= sl and vr >= 2:
        shape_score, shape = 10, '价格攀升'
    elif gap < sf:
        shape_score, shape = 0, '绿柱扩大'
    else:
        shape_score, shape = 5, '平稳'
    s['_shape'] = shape
    base = gap_score + vr_score + em_score + ar_score + shape_score
    # —— 题材分（100，云端 heat 体系：热度60+同题材≥5家10+主线持续20；co20 已按共振升级降为 co10）——
    ind = re.sub(r'[行业板块概念\s]+', '', s['industry']) or '其他'
    heat60 = min(60.0, heat.get(ind, 0.0) / 100.0 * 60.0)
    co10 = 10.0 if cnt.get(ind, 0) >= 5 else 0.0
    persist = 0.0
    if mem_days:
        for pd, pv in list(mem_days.items())[:3]:
            if ind in pv:
                persist = 20.0
                break
    theme_score_v = min(100.0, heat60 + co10 + persist)
    # —— 风险扣分：高位+10 / 题材弱+5 / 接近涨停+2 ——
    risk = 0.0
    if pos60 is not None and pos60 >= 0.95:
        risk += 10.0
    if heat.get(ind, 0) < 40:
        risk += 5.0
    if s['pct'] >= (9.0 if not cyb else 18.0):
        risk += 2.0
    # —— 反推修正 ——
    rv, rtag = _auction_revise(s, vr, pos60, bars)
    s['_revise'], s['_rtag'] = rv, rtag
    total = base * 0.60 + theme_score_v * 0.20 + (s.get('_reson') or 0) * 0.20 - risk + rv
    return round(total, 1)


# ============ 工单12：高开承接形态因子（专治竞价骗炮） ============
def _auction_form(code):
    """09:30 起前 15 分钟承接形态：高开后守住=真抢筹，高开后半小时内跌破开盘价 2%=假高开。
    返回 {'gap','low_gap','last_gap','tag','score'}；取不到分时返回 {}（不参与打分）。"""
    try:
        _c = str(code or '')
        if not _c:
            return {}
        _mk = '1' if _c.startswith('6') else '0'
        u = ('https://push2his.eastmoney.com/api/qt/stock/trends2/get?secid=%s.%s'
             '&fields1=f1,f2,f3,f4,f5,f6,f7,f8&fields2=f51,f52,f53,f54,f55,f56,f57,f58&iscr=0&ndays=1'
             % (_mk, _c))
        _txt, _ok = _getm(u, 'trends2_' + _c)
        if not _ok or not _txt:
            return {}
        _d = json.loads(_txt).get('data') or {}
        _prev = float(_d.get('preClose') or 0)
        _tr = _d.get('trends') or []
        if _prev <= 0 or len(_tr) < 3:
            return {}
        _rows = [x.split(',') for x in _tr[:15]]
        _open = float(_rows[0][1] or 0)
        _low = min(float(r[4] or 0) for r in _rows)
        _last = float(_rows[-1][2] or 0)
        if _open <= 0 or _low <= 0:
            return {}
        _gap = (_open / _prev - 1) * 100
        _lowg = (_low / _open - 1) * 100
        _lastg = (_last / _open - 1) * 100
        if _gap >= 2 and _lowg > -1.0 and _lastg >= 0:
            _tag, _sc = '真抢筹', 2
        elif _gap >= 2 and _lowg <= -2.0:
            _tag, _sc = '假高开·竞价骗炮', -3
        elif _gap >= 2:
            _tag, _sc = '高开走弱', -1
        elif _gap < 1 and _lastg >= 1:
            _tag, _sc = '低开抢筹', 1
        else:
            _tag, _sc = '平开无信号', 0
        return {'gap': _gap, 'low_gap': _lowg, 'last_gap': _lastg, 'tag': _tag, 'score': _sc}
    except Exception as _e:
        print('[aform] 异常:', type(_e).__name__, str(_e)[:60])
        return {}


def _auction_fact_read(s):
    """竞价卡的一句话判断：只用竞价数据（涨幅/量比/换手/市值）出结论，档内再细分，不同票不同说法。"""
    try:
        pct = float(s.get('pct') or 0)
        lb = float(s.get('lb') or 0)
        turn = float(s.get('turn') or 0)
        mv = float(s.get('mv') or 0)
    except Exception:
        return '这票今天不参与'
    if pct >= 7:
        if lb >= 8:
            return '高开这么多还堆着量，是资金在竞价里拼命抢，冲高回落的风险一样大，别去接最后一棒'
        return '高开太多，开盘价很容易就是当天最高价，在这种位置竞价里接就是给别人送钱'
    if pct >= 3:
        if lb >= 8:
            return '高开带大量，竞价里就有人真金白银往里砸，开盘只要量不缩还能继续往前走'
        if lb >= 3:
            if turn >= 8:
                return '高开带量又换得快，筹码在竞价就换了一轮，开盘第一分钟的方向就是答案'
            return '高开还带量，竞价里有真金白银在抢，开盘后看能不能站稳竞价价位'
        if turn >= 10:
            return '高开但量没跟上、换手却先堆起来，是有人借着高开往外倒货'
        return '高开但量没跟上，这种多半是虚高，开盘后随时会被打回去'
    if pct <= -3:
        if lb >= 6:
            return '低开但有人在竞价里接货，说明跌下去有支撑，先看能不能重新站回昨收'
        if mv >= 150:
            return '低开走弱、盘子又大，想拉起来要天量，今天别指望它自己翻身'
        return '低开走弱、竞价没人接，今天先看能不能翻红再说'
    if lb >= 8:
        return '平开附近爆量，有大单在低位埋伏，开盘第一波拉升的力度就是真假分界线'
    if lb >= 4:
        return '平开附近放量，有资金在低位埋伏，开盘盯第一波拉升的力度'
    if mv >= 150:
        return '平开缩量、盘子又大，今天大概率还是原地磨，别急着进'
    return '竞价不温不火，没给方向，等开盘半小时看承接再决定'


def _form_line(f):
    """承接形态一句话（卡面用）：说人话，不罗列口径数字、不加括号注解。"""
    if not f:
        return ''
    _sc = int(f.get('score') or 0)
    _col = TEAL if _sc > 0 else (RED if _sc < 0 else GREY)
    try:
        _gap = float(f.get('gap') or 0)
        _low = float(f.get('low_gap') or 0)
        _last = float(f.get('last_gap') or 0)
    except Exception:
        _gap, _low, _last = 0.0, 0.0, 0.0
    _tag = (f.get('tag') or '').strip()
    if _gap < -1 and _last > 0:
        _low_txt = ('盘中最多只回撤%.1f个点' % abs(_low)) if _low < 0 else '盘中一直站在昨收上面没破过'
        _w = '低开%.1f个点，一路抢到开盘价上方%.1f个点，%s' % (abs(_gap), _last, _low_txt)
    elif _gap > 1 and _last < 0:
        _w = '高开%.1f个点没守住，现在比开盘价还低%.1f个点' % (_gap, abs(_last))
    elif _gap > 1:
        _w = '高开%.1f个点后继续往上走，现价比开盘高%.1f个点' % (_gap, _last)
    else:
        _low_txt = ('盘中最多只回撤%.1f个点' % abs(_low)) if _low < 0 else '盘中一直没跌破昨收'
        if _last > 0:
            _w = '基本平开，%s，现在比开盘价高%.1f个点' % (_low_txt, _last)
        else:
            _w = '基本平开，%s，现在比开盘价低%.1f个点' % (_low_txt, abs(_last))
    if _tag:
        _w = _w + '，' + _tag
    return ('<div style="color:%s;font-size:12px;margin-top:2px;">🧭 今日承接：%s</div>' % (_col, _w))


def _auction_score(s, heat, cnt, mem_days=None):
    """双重打分：综合分=量价分×0.65 + 题材分×0.35 − 风险分。
    量价分（100）：高开幅度15 + 竞价量比20 + 竞价量/昨量20 + 换手×量比情绪15 + 分时结构代理20 + 突破昨日高点10
    题材分（100）：题材热度60 + 同题材榜内≥5家20 + 主线持续性(近3日持续有涨停)20"""
    # —— 量价分 ——
    mid, half = (4.5, 2.5) if s['board'] == 'main' else (9.0, 5.0)   # 高开区间中枢
    gap = max(0.0, 1 - abs(s['pct'] - mid) / half) * 15.0            # 高开幅度 15
    lb = min(20.0, s['lb'] / 3.0 * 20.0)                              # 竞价量比 20（量比≥3 满分）
    emo = min(15.0, (s['turn'] * max(s['lb'], 0.1)) / 6.0 * 15.0)     # 换手×量比情绪值 15
    vq = 0.0
    sym = ('sh' if s['code'].startswith('6') else 'sz') + s['code']
    try:
        arr = get_klines(sym, 2)
        if len(arr) >= 2 and float(arr[-2][5]) > 0:
            vq = (s['vol'] * 100) / float(arr[-2][5])                 # 竞价量(股)/昨量(股)
    except Exception:
        pass
    vqs = min(20.0, vq / 1.5 * 20.0)                                  # 竞价量/昨量 20
    shape = 0.0
    if s['high'] > s['prev']:
        shape = min(20.0, max(0.0, (s['price'] - s['prev']) / (s['high'] - s['prev'])) * 20.0)  # 分时结构代理 20
    brk = 0.0
    try:
        arr = get_klines(sym, 2)
        if len(arr) >= 2 and float(arr[-2][3]) > 0:
            if s['price'] > float(arr[-2][3]):
                brk = 10.0                                            # 突破昨日高点 10
    except Exception:
        pass
    price_score = gap + lb + emo + vqs + shape + brk
    # —— 题材分（100）：热度60 + 同题材≥5家20 + 主线持续性20 ——
    ind = re.sub(r'[行业板块概念\\s]+', '', s['industry']) or '其他'
    heat60 = min(60.0, heat.get(ind, 0.0) / 100.0 * 60.0)
    co20 = 20.0 if cnt.get(ind, 0) >= 5 else 0.0                     # 同题材榜内≥5家
    persist = 0.0
    if mem_days:
        for pd, pv in list(mem_days.items())[:3]:
            if ind in pv:
                persist = 20.0                                        # 近3日该题材持续有涨停
                break
    theme_score_v = min(100.0, heat60 + co20 + persist)
    # —— 风险扣分：高位+10、题材弱+5 ——
    risk = 0.0
    try:
        arr = get_klines(sym, 125)
        if len(arr) >= 60:
            hi60 = max(float(r[2]) for r in arr[-60:])
            if s['price'] >= hi60 * 0.95:
                risk += 10.0                                          # 高位
    except Exception:
        pass
    if heat.get(ind, 0) < 40:
        risk += 5.0                                                   # 题材弱
    if s['pct'] >= (9.0 if s.get('board') == 'main' else 18.0):
        risk += 2.0                                                   # 已接近涨停：可操作价值低，降权
    total = price_score * 0.65 + theme_score_v * 0.35 - risk
    return round(total, 1)


AUCTION_POOL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'auction_pool.json')


def _auction_pool_record(tops):
    """竞价观察仓：记录今日竞价批次（入选价=竞价价），只留最近10天。"""
    try:
        today = _bj_now().strftime('%Y-%m-%d')
        data = {}
        if os.path.exists(AUCTION_POOL_PATH):
            try:
                data = json.load(open(AUCTION_POOL_PATH, encoding='utf-8'))
            except Exception:
                data = {}
        data[today] = [{'code': s['code'], 'name': s['name'], 'price': float(s['price']),
                        'score': round(float(s['score']), 1), 'pct': round(float(s['pct']), 2)}
                       for s in tops]
        days = sorted(data)
        for dd in days[:-10]:
            data.pop(dd, None)
        with open(AUCTION_POOL_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print('[auction_pool] record fail:', e)


def _auction_pool_stats(date_str=None):
    """竞价观察仓结算：每只 当日收盘/入选价-1 → 赚钱/亏钱百分比。date_str 空=最近一个非今日批次。返回 HTML 或 ''。"""
    try:
        if not os.path.exists(AUCTION_POOL_PATH):
            return ''
        data = json.load(open(AUCTION_POOL_PATH, encoding='utf-8'))
        if not data:
            return ''
        if date_str is None:
            today = _bj_now().strftime('%Y-%m-%d')
            batch_dates = [d for d in sorted(data) if d != today]
            if not batch_dates:
                return ''
            date_str = batch_dates[-1]
        batch = data.get(date_str)
        if not batch:
            return ''
        rets = []
        for it in batch:
            sym = ('sh' if it['code'].startswith('6') else 'sz') + it['code']
            arr = get_klines(sym, 30)
            close = None
            if arr:
                d8 = date_str.replace('-', '')
                for r in reversed(arr):
                    if r[0] == d8:
                        close = float(r[2])
                        break
            if not close or not it.get('price'):
                continue
            rets.append((close / it['price'] - 1) * 100)
        if not rets:
            return ''
        win = [r for r in rets if r > 0]
        loss = [r for r in rets if r <= 0]
        avg = sum(rets) / len(rets)
        pct_win = len(win) / len(rets) * 100
        pct_loss = len(loss) / len(rets) * 100
        return (f'<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">📊 竞价观察仓结算（{date_str} 选股 → 当日收盘）</div>'
                f'<div style="font-size:13px;color:#e9ecef;background:#1c2830;border-left:4px solid {GOLD};border-radius:8px;padding:8px 10px;">'
                f'共 {len(rets)} 只｜🟢 赚钱 {len(win)} 只（<b style="color:{GREEN}">{pct_win:.0f}%</b>）｜🔴 亏钱 {len(loss)} 只（<b style="color:{RED}">{pct_loss:.0f}%</b>）'
                f'｜平均 <b>{avg:+.1f}%</b>｜最好 {max(rets):+.1f}%｜最差 {min(rets):+.1f}%<br>'
                f'<span style="color:{GREY};font-size:12px;">口径：09:25竞价入选价→当日收盘，未含手续费/滑点</span></div>')
    except Exception as e:
        print('[auction_pool] stats fail:', e)
        return ''


def _auction_ds(tops, heat, zt_themes=None, mkt_ctx=None, mscore=None, lu=None, zb=None):
    """竞价深挖（模板型回答版）：单次 LLM 调用同时输出
    per（每只：dark 暗线/ reason 选中原因/ why 大白话/ op 建议/ buy/ stop/ drop 放弃）
    + cap_advice（盘面档位建议）+ wind_strong/wind_weak（最强/最弱题材暗线原因）。
    已按用户指令删除 overall（今日整体）与 reson_reason（共振原因）输出。
    返回 dict 或 {}；失败由调用方渲染「数据事实行」（不落回规则模板句）。"""
    if not tops:
        return {}
    # 持仓诊断纯文本（供 LLM 终审参考）
    hold_txt = []
    for h in HOLDINGS:
        q = _qt(h['code'])
        if not q:
            continue
        op = (q['open'] / q['prev'] - 1) * 100 if q['prev'] else 0
        vq_ratio = None
        try:
            arr = get_klines(h['code'], 2)
            if len(arr) >= 2 and float(arr[-2][5]) > 0 and q.get('vol'):
                vq_ratio = (q['vol'] * 100) / float(arr[-2][5]) * 100
        except Exception:
            pass
        act, _ = three_way(op, q.get('lb', 0), vq_ratio)
        hold_txt.append(f"{h['name']} 开幅{op:+.1f}% 量比{q.get('lb',0):.1f} {act}")
    _zt = (zt_themes or [])[:8]
    _zt_txt = '、'.join(f'{n}(涨停{int(c)}家)' for n, c in _zt) or '暂无'
    _heat_txt = '、'.join(f'{k}(热度{v:.0f})' for k, v in sorted(heat.items(), key=lambda kv: -kv[1])[:6]) or '暂无'
    _mkt = mkt_ctx or ''
    payload = {
        'task': 'auction_top_deep',
        'stocks': [{'name': s['name'], 'code': s['code'], 'score': round(float(s['score']), 1),
                    'pct': s['pct'], 'industry': s['industry'],
                    'vr': round(float(s.get('_vr') or 0), 1), 'revise': round(float(s.get('_revise') or 0), 1),
                    'rtag': s.get('_rtag', '')} for s in tops],
        'hot_sectors': sorted(heat.items(), key=lambda kv: -kv[1])[:6],
        'zt_themes': _zt_txt,
        'mkt_ctx': _mkt,
        'holding_diagnosis': '\n'.join(hold_txt) or '无持仓',
        'format': ('你是A股竞价短线交易员。对以下每只竞价强票做「暗线业务深挖+题材+市场关联」多因素深挖（禁止单条件结论）：\n'
                   '0.【暗线业务深挖·每只必做】先一句话说清公司本质（靠什么赚钱，禁「XX龙头/XX概念」标签）；再挖暗线业务——具体产品/技术/业务是什么、进展到哪个阶段、在产业链哪个环节、有没有卡位壁垒、对业绩是真实贡献还是纯故事/预期；然后判断跟今日最强主线（{hot_sectors}）是【实受益】【沾边】还是【纯蹭】、弹性大不大。挖不出来如实写「未见明确暗线业务」，禁止用「相关」「涉及」「布局」「受益于」等词糊弄。\n'
                   '1. 题材归属：判断属于什么题材、是不是今日主线、题材里的地位（龙头/中军/跟风/补涨）。\n'
                   '2. 板块共振：看同题材几只一起动，判断是真合力还是一只独涨。\n'
                   '3. 资金逻辑：用量比/竞价量比/反推修正说明谁在抢，判断抢筹还是出货。\n'
                   '4. 位置与预期差：看60日位置高低，判断有没有市场还没消化的东西（业绩预期/错杀修复/政策外溢/龙头扩散）。\n'
                   '5. 为什么是它：资金凭什么选它不选别人（主业匹配/位置/筹码/业绩/催化），用真实数据说。\n'
                   '6. 破灭点与动作：逻辑什么时候会破（催化兑现/业绩证伪/位置透支/主力出货），破了怎么走人；逻辑不硬就明确写「不碰」。\n'
                   '7. 禁止编新闻猜消息、禁止万能句（「回踩分时均线可轻仓试」等）及变体、禁止满仓/必涨/稳了。\n'
                   '7.5 周期适配：先判定每只票当前最适合的参与周期（超短线1-3日/短线3-10日/中长线1-6月/长线6月+），'
                   'buy/stop 必须按该周期口径给——超短线看分时与MA5、短线看MA10/MA20回踩、中长线看MA20/MA60趋势仓；buy 字段开头用【周期：XXX】标注。\n'
                   '8. 共振判断：必须明确写出「主题共振（同题材几只一起动）+ 量价共振（个股量能是否明显强于板块）+ 板块热度共振（是否今日最强主线、持续几天）」，三者缺一就降级为「沾边/观望」，禁止只谈单票。\n'
                   '9. 只输出 JSON，不要其他文字：\n'
                   '{"cap_advice":"当前档位建议：结合 mkt_ctx（涨停家数/炸板/情绪分/指数涨跌）直接给仓位档位建议与一句话理由，禁止万能句，至少20字",'
                   '"wind_strong":"最强题材的暗线原因：一句话说透它今天为什么最强（涨停家数/催化/资金逻辑），至少20字",'
                   '"wind_weak":"最弱题材的暗线原因：一句话说透它为什么最弱（为什么别碰），至少15字",'
                   '"per":[{"name":"股票名称","dark":"一句话暗线（这条票真正炒的是什么，禁标签糊弄，10-30字）","reason":"选中原因/暗线逻辑：为什么筛出它（主业匹配+位置+筹码+业绩+催化，真实数据，至少20字）","logic":"暗线业务深挖+题材归属+市场关联：公司本质→暗线业务(产品/技术/阶段/业绩贡献)→与今日主线相关性(实受益/沾边/纯蹭+弹性)→题材地位+板块共振+资金逻辑+位置+预期差+共振判断(主题X家+量价共振强/弱+板块热度共振强/中/无)→破灭点，为什么值得看/不看不碰，多因素连贯大白话，至少60字，禁止单条件、禁止相关/涉及/布局/受益于糊弄","why":"大白话：一句话戳穿真假+该不该追，至少20字，禁止万能句","op":"别追/看/轻仓试/观望/不碰","buy":"具体买点条件","stop":"具体止损条件","drop":"放弃条件：什么情况出现就不做（破位/量能/情绪/高开透支等具体条件，10-25字）"}]}，'
                   'per 必须覆盖我给的每只股票。'),
    }
    t = ask_deepseek(payload, purpose='auction', system_text=_ASK_DS_SYS_AC)
    if not t:
        return {}
    out = {}
    try:
        j = json.loads(t[t.find('{'):t.rfind('}') + 1])
        if isinstance(j, dict):
            out['overall'] = str(j.get('overall', '') or '')
            out['reson_reason'] = str(j.get('reson_reason', '') or '')
            out['cap_advice'] = str(j.get('cap_advice', '') or '')
            out['wind_strong'] = str(j.get('wind_strong', '') or '')
            out['wind_weak'] = str(j.get('wind_weak', '') or '')
            per = {}
            for it in (j.get('per') or []):
                nm = str(it.get('name', '')).split('（')[0].split('(')[0].strip()
                if nm:
                    per[nm] = {'dark': str(it.get('dark', '') or ''),
                               'reason': str(it.get('reason', '') or ''),
                               'logic': str(it.get('logic', '') or ''),
                               'why': str(it.get('why', '') or ''),
                               'op': str(it.get('op', '') or ''),
                               'buy': str(it.get('buy', '') or ''),
                               'stop': str(it.get('stop', '') or ''),
                               'drop': str(it.get('drop', '') or '')}
            out['per'] = per
    except Exception:
        return {}
    return out


def _news_summary_rows(news):
    """新闻汇报总结：标题/时间 + 利好/利空/中性 + 板块题材 + 大白话。"""
    rows = []
    for nw in news[:15]:
        text = nw['title'] + ' ' + (nw.get('summary') or '')
        tag, col = classify_news(text)
        sec, stocks, plain = news_tags(nw['title'], nw.get('summary') or '')
        t = str(nw.get('ts') or '')[-5:]
        sec_txt = f'｜板块: <b style="color:{TEAL}">{sec}</b>' if sec else ''
        plain_txt = f'<div style="color:{GREY};font-size:12px;margin-top:2px;">💬 {plain}</div>' if plain else ''
        rows.append(f"""<div style="background:#1f2635;border-left:3px solid {col};border-radius:8px;padding:8px 10px;margin:6px 0;">
<div style="font-size:13px;color:#e9ecef;">{nw['title']} <span style="color:{col};font-weight:700;">【{tag}】</span></div>
<div style="color:{GREY};font-size:12px;margin-top:2px;">{t}{sec_txt}</div>{plain_txt}</div>""")
    return ''.join(rows)


def _stock_goodbad(news):
    """利好/利空个股榜（规则提取：新闻文本命中 NEWS_THEME_MAP 示例股 + 方向）。
    过滤板块词（板块名/以'链'结尾/AI等通用词），只保留真实个股名，避免把板块当个股。"""
    sec_words = {sec for _, sec, _, _ in NEWS_THEME_MAP}
    good, bad = [], []
    for nw in news[:15]:
        text = nw['title'] + ' ' + (nw.get('summary') or '')
        tag, _ = classify_news(text)
        for kws, sec, stocks, plain in NEWS_THEME_MAP:
            for stk in stocks.split('、'):
                stk = stk.strip()
                if not stk or len(stk) < 3 or stk in sec_words or stk.endswith('链'):
                    continue
                if stk in text and stk not in good and stk not in bad:
                    (good if tag == '利好' else bad if tag == '利空' else good).append(stk)
    return good[:8], bad[:8]


def _pre_ds(news, intel=None):
    """盘前 DeepSeek 大白话总结：新闻→AI看多/看空板块 + 点名关注股（催化+新闻匹配）；失败返回 ''。
    intel=_event_intel 时，用「事件驱动量化评分」喂主线候选（紧跟时事核心）。"""
    if not news:
        return ''
    brief = [{'t': nw['title'], 's': (nw.get('summary') or '')[:60]} for nw in news[:12]]
    intel = intel or _event_intel(news)
    jc = judgment_context()
    ev_lines = ''
    if intel.get('mainlines'):
        ev_lines += '\n'.join(f"- 板块「{m['sec']}」事件{m['n']}条 净情绪分{m['net']} 最新{m['latest'][11:16] if len(m.get('latest',''))>=16 else m.get('latest','')} 代表：{'；'.join(m['tops'][:2])}" for m in intel['mainlines'])
    if intel.get('overnight'):
        ev_lines += '\n隔夜重大：' + '；'.join(intel['overnight'][:3])
    t = ask_deepseek({'task': 'pre_news_summary', 'news': brief, 'judgment': jc,
                      'events': ev_lines or '（今日暂无高情绪事件）',
                      'format': (_TRADER_RULES + '\n'
                                + (('昨日判断（开盘前先对照它，别重复昨天的错）：\n{judgment}\n' if jc else '昨日判断：无（今日首卡）\n')
                                   + '【事件驱动主线·量化评分】（板块事件数/净情绪分/最新时间，权重最高的排前面，这是今日最可能被资金点火的候选）：\n{events}\n'
                                   + '今日新闻（12条）：\n{news}\n'
                                   + '请严格按以下格式输出，不许加其他板块、不许打乱：\n'
                                   + '① 今日一句话总判断（今日情绪：强势/震荡/偏空/冰点 + 建议总仓位：空仓/1成试探/2成/半仓 + 主基调：进攻/防守/观望/做分歧）\n'
                                   + '② 今日主线预判：只给【1个主攻方向+最多2个备选】，优先从「事件驱动主线·量化评分」里选（方向名+驱动(用新闻数据)+代表股+为什么现在值得做(禁万能句)+放弃条件）；评分里没有明确主线就写「今日无明确主线，只做观察」，禁止硬凑、禁止罗列式废话\n'
                                   + '③ 重点标的（最多2只；没有就写「今日无强推」并说明缺哪项共振；昨日涨停/连板票禁止列入）\n'
                                   + '每只格式：名称 代码 | 阶段(启动/中段/高位) | 共振x/4 | 为什么现在值得看(禁万能句) | 关键位置：支撑X/阻力X | 买入条件 | 放弃条件 | 仓位(仅1成试探/2成/半仓) | 唯一主风险\n'
                                   + '④ 今日最大风险（一句话，必须是具体的：哪个板块/哪类票/哪个消息会砸盘）\n'
                                   + '【昨日复盘】若给了昨日判断：用今日新闻对照它，先写一句哪些说对了/哪些说错了（最多3条）\n'
                                   + '【仓位仪表盘】今日建议总仓位一档（空仓/1成试探/2成/半仓）+ 一句理由（供全天其他模块引用）' + '\n【自检】输出前自查：是否违反高位连板别追？是否缺止损？是否有万能句（值得关注/建议留意/具备投资价值）？是否与仓位仪表盘矛盾？有问题降级改写；无问题结尾写「自检通过」。'))},
                     purpose='pre')
    return md2html(t) if t else ''


# ============ 盘中最强 TOP10 加厚版（小白友好版） ============
def _batch_deep(items, kind='stock'):
    """批量 LLM 深挖（TOP10 卡/板块卡共用）。kind='stock' 输出每只股的逻辑/大白话/操作；kind='sector' 输出板块点评。
    失败返回 {}（调用方回退规则文案）。"""
    if not items or not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return {}
    if kind == 'sector':
        lines = '\n'.join(f"- 板块「{x['name']}」涨停{x['n']}家 均涨{x['avg_pct']:+.1f}% 强度{x['strength']:.0f} 龙头{x['lead']}({x['lbc']}板) 跟涨:{x['fol']}" for x in items)
        fmt = ('你是一线游资，盘中看盘，对下面每个板块点评（严格按主力游资五步铁律）：\n'
               + FIVE_BRIEF + '\n'
               + '先判断主力阶段（刚启动吸筹 / 拉升中 / 出货中 / 对倒中），再给操作。高位连板板块直接写「不接飞刀」。\n'
               + '【深挖铁律·龙头必做】提到板块龙头或代表股时，必须执行「股票深挖铁律」：本质一句话+暗线业务（写不出写「未见明确暗线业务」）+真实关联与弹性（实受益/沾边/纯蹭），禁「相关/涉及/布局/受益于」糊弄。\n板块数据：\n' + lines + '\n'
               + '只输出 JSON：{"per":[{"name":"板块名(照抄)","logic":"主力阶段+为什么现在强/弱：驱动+资金+持续性判断(≥25字)","why":"大白话(≥20字，游资黑话优先)","act":"操作：追/低吸/看戏+条件(≥15字)"}]}，必须覆盖每个板块，推不出的如实说看不出来，不许硬编。')
    else:
        lines = '\n'.join(
            f"- {x['name']}({x['code']}) 板块「{x['sec']}」({x['sec_count']}家涨停) {x['lbc']}连板 涨{x['pct']:+.1f}% 量比{x['lb']:.1f} {'已封板' if x['sealed'] else '未封'}" + (f' 60日位置{x["pos"]*100:.0f}%' if x.get('pos') is not None else '')
            for x in items)
        fmt = ('你是一线游资，盘中看盘，对下面每只票点评（严格按主力游资五步铁律）：\n'
               + FIVE_BRIEF + '\n'
               + '每只票必须写：主力建仓痕迹有没有、上方筹码真空不真空、今天盘口托单还是砸盘、处于什么阶段。高位连板(lbc≥3)或60日位置>0.85强制「不碰」。\n'
               + '【深挖铁律·每只票必做】完整执行「股票深挖铁律」：本质（一句话大白话）+暗线业务（具体产品+阶段+真实贡献，写不出写「未见明确暗线业务」，禁「相关/涉及/布局/受益于」糊弄）+真实关联与弹性（实受益/沾边/纯蹭）+为什么是它+破灭点（必写）+动作。没有硬逻辑直接写「不碰」。\n涨停/强势股数据：\n' + lines + '\n'
               + '只输出 JSON：{"per":[{"name":"股票名(照抄)","logic":"本质+暗线业务+真实关联与弹性+为什么是它+破灭点+驱动+暗雷(≥25字)","why":"大白话(≥20字)","op":"别追/轻仓试/看/观望(只能一个)","buy":"买入条件(≥12字)","stop":"止损条件(≥10字)","stage":"启动日|中段接力|末段高位|退潮反抽","verdict":"终审推荐|观察|不碰","evidence":["证据1","证据2"],"dark_risk":["解禁/减持/担保/业绩亏损等暗雷，无则写空数组"]}]}，dark_risk非空时verdict必须为「不碰」或「观察」；必须覆盖每只。')
    t = ask_deepseek({'task': 'batch_deep_' + kind, 'items': items[:12], 'format': fmt}, purpose='batch_deep')
    out = {}
    if not t:
        return out
    try:
        _j = json.loads(t)
        for it in _j.get('per') or []:
            nm = str(it.get('name') or '').strip()
            if nm:
                out[nm] = {k: str(it.get(k) or '') for k in ('logic', 'why', 'op', 'buy', 'stop', 'act', 'stage', 'verdict', 'evidence', 'dark_risk')}
    except Exception:
        pass
    return out


def _top_deep(d):
    """TOP10 涨停股卡批量深挖。"""
    zt_codes = set()
    for _sec, sts in d['sectors'].items():
        for st in sts:
            zt_codes.add(st.get('c'))
    try:
        gainers = {g['code']: g for g in _clist_gainers()}
    except Exception:
        gainers = {}
    items = []
    for sec, stocks in d['tops'][:10]:
        if not stocks:
            continue
        st = stocks[0]
        code = st.get('c', '')
        g = gainers.get(code)
        items.append({
            'name': st.get('n', ''), 'code': code, 'sec': sec, 'sec_count': len(stocks),
            'lbc': int(st.get('lbc') or 0), 'pct': float(st.get('pct') or 0) or (g.get('pct', 0) if g else 0),
            'lb': float(st.get('lb') or 0) or (g.get('lb', 0) if g else 0), 'sealed': code in zt_codes,
        })
    return _batch_deep(items, 'stock')


def _sector_deep(tops):
    """板块强度卡批量点评。"""
    items = []
    for name, stocks in tops[:10]:
        if not stocks:
            continue
        lead = max(stocks, key=lambda s_: (int(s_.get('lbc') or 0), -(int(s_.get('fbt') or 0) or 99999)))
        n = len(stocks)
        avg_pct = sum(float(x.get('pct') or 0) for x in stocks) / max(n, 1)
        strength = n * 0.4 + min(avg_pct, 20) * 0.3
        items.append({'name': name, 'n': n, 'avg_pct': avg_pct, 'strength': strength,
                      'lead': lead.get('n', ''), 'lbc': int(lead.get('lbc') or 0),
                      'fol': '、'.join(x.get('n', '') for x in stocks[1:4])})
    return _batch_deep(items, 'sector')


def _pre_news_deep(news):
    """盘前新闻逐条大白话批量深挖：{key: {'good','bad','logic','why','act','sec'}}。失败 {}。"""
    if not news or not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return {}
    out = {}
    # 分批 6 条/组（一次 12 条 LLM 常输出不全，分批提升覆盖率；额度放开不用省）
    for chunk in (news[:12][i:i + 6] for i in range(0, min(len(news), 12), 6)):
        lines = '\n'.join(f"- {x['title'][:60]}（摘要：{(x.get('summary') or '')[:50]}）" for x in chunk)
        fmt = ('你是一线游资，盘前读新闻，对下面每条新闻深挖（严格按主力游资五步铁律）：\n'
               + FIVE_BRIEF + '\n'
               + '先判断：主力会不会借此点火，还是借机出货。act必须写「开盘后看哪些票的竞价和盘口托单」而不是直接给买入价；纯凑数、不改变交易决策的新闻直接写「无交易价值，跳过」。\n'
               + '【深挖铁律·落到个股必做】新闻落到个股时，完整执行「股票深挖铁律」：本质（一句话大白话）+暗线业务（具体产品+阶段+真实贡献，写不出写「未见明确暗线业务」）+真实关联与弹性（实受益/沾边/纯蹭）+为什么是它+破灭点+动作。没有硬逻辑的写「逻辑不硬，不碰」。\n新闻：\n' + lines + '\n'
               + '只输出 JSON：{"per":[{"t":"标题(照抄前18个字即可)","good":"✅利好哪个板块/题材/个股+为什么，至少12字（无明显利好写「无明显直接利好」）","bad":"⚠️利空哪个板块/题材/个股+为什么，至少12字（无明显利空写「无明显直接利空」）","logic":"逻辑原因：主力意图深挖，至少25字","why":"大白话：一句话戳穿真假+怎么应对，至少22字","act":"操作：开盘后验证条件（点名关注哪些票的竞价/盘口），至少20字","sec":"影响的板块(≥4字，猜不到写「暂看不出直接关联」)"}]}，必须覆盖每条。')
        t = ask_deepseek({'task': 'pre_news_deep', 'news': [{'t': x['title'][:60], 's': (x.get('summary') or '')[:50]} for x in chunk],
                          'format': fmt}, purpose='pre_news_deep')
        if not t:
            continue
        try:
            _j = json.loads(t)
        except Exception:
            continue
        for it in _j.get('per') or []:
            tt = str(it.get('t') or '').strip()
            if tt and (it.get('why') or it.get('plain')):
                key = _pre_key(tt)
                out[key] = {'good': str(it.get('good') or ''), 'bad': str(it.get('bad') or ''),
                            'logic': str(it.get('logic') or ''), 'why': str(it.get('why') or it.get('plain') or ''),
                            'act': str(it.get('act') or ''), 'sec': str(it.get('sec') or '')}
    return out


def _pre_key(title):
    """标题→匹配键：去空白标点，取前18字符（LLM照抄易截断，用前缀容错匹配）。"""
    import re as _re
    s = _re.sub(r'[\s\u3000，。！？、；：""''（）【】—…-]', '', str(title or ''))
    return s[:18]


def _focus_deep(focus):
    """盘前重点个股批量深挖：{nm: {'plain','tip'}}。失败 {}。"""
    if not focus or not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return {}
    lines = '\n'.join(f"- {nm}({code}) 昨收{prev} 题材{sec} 角色{role}" for nm, code, prev, sec, _p, _t, role in focus[:8])
    fmt = ('你是一线游资，盘前重点个股参考，对下面每只深挖（严格按主力游资五步铁律）：\n'
           + FIVE_BRIEF + '\n'
           + '只推有明显前期建仓痕迹、位置不高的票。共振不足3项或高位直接写「今日无买点」。昨日涨停/连板票禁止推荐（一律写「昨日已涨停，今日只观察不操作」）。\n'
           + '【深挖铁律·每只票必做】完整执行「股票深挖铁律」：本质（一句话大白话）+暗线业务（具体产品+进展阶段+对业绩真实贡献，写不出写「未见明确暗线业务」，禁「相关/涉及/布局/受益于」糊弄）+真实关联与弹性（实受益/沾边/纯蹭+弹性大小）+为什么是它+破灭点+动作。没有清晰暗线业务或弹性不足的写「今日无买点」，禁止硬推。\n个股：\n' + lines + '\n'
           + '只输出 JSON：{"per":[{"nm":"股票名(照抄)","stage":"启动/中段/高位","resonance":"满足共振几项(题材/资金/位置/买点, x/4)","plain":"本质+暗线业务+真实关联与弹性+为什么是它+破灭点(≥30字)","tip":"操作建议：买点+止损+仓位档(仅1成试探/2成/半仓)(≥20字)；不满足3项共振或无建仓痕迹或逻辑不硬则写「今日无买点」"}]}，必须覆盖每只。')
    t = ask_deepseek({'task': 'focus_deep', 'items': [{'nm': x[0], 'code': x[1], 'prev': x[2], 'sec': x[3], 'role': x[6]} for x in focus[:8]],
                      'format': fmt}, purpose='focus_deep')
    out = {}
    if not t:
        return out
    try:
        _j = json.loads(t)
        for it in _j.get('per') or []:
            nm = str(it.get('nm') or '').strip()
            if nm and it.get('plain'):
                out[nm] = {'plain': str(it['plain']), 'tip': str(it.get('tip') or '')}
    except Exception:
        pass
    return out


def _top10_cards(d):
    """盘中最强 TOP10 加厚版：每只含涨幅/题材/量比/封单状态/差异化大白话/是否可操作。
    大白话按真实数据组合（连板/封板时间/60日位置/量比/板块家数），杜绝千篇一律模板。"""
    zt_codes = set()
    for _sec, sts in d['sectors'].items():
        for st in sts:
            zt_codes.add(st.get('c'))
    rows = ''
    try:
        gainers = {g['code']: g for g in _clist_gainers()}
    except Exception:
        gainers = {}
    _dm = _top_deep(d)
    n = 0
    for sec, stocks in d['tops'][:10]:
        sec_count = len(stocks)
        # 板块内最早封板 = 龙头（fbt 非0取最小）
        leader_code = None
        fbt_min = 0
        for st in stocks:
            v = int(st.get('fbt') or 0)
            if v and (not fbt_min or v < fbt_min):
                fbt_min, leader_code = v, st.get('c')
        for st in stocks[:1]:
            n += 1
            if n > 10:
                break
            code = st.get('c', '')
            g = gainers.get(code)
            lb = (g.get('lb', 0) if g else 0) or st.get('lb') or 0
            pct = (g.get('pct', 0) if g else 0) or st.get('pct') or 0
            lbc = int(st.get('lbc') or 0) or 0
            sealed = code in zt_codes
            # 60日位置（K线失败降级 None）
            pos = None
            try:
                sym = ('sh' if code.startswith('6') else 'sz') + code
                q = _qt(sym)
                if q and q['price']:
                    pos, _tag = _pos_risk(sym, q['price'])
            except Exception:
                pos = None
            # —— 差异化大白话（LLM 深挖优先，失败按信息优先级规则组合）——
            _dp = _dm.get(st.get('n'))
            _llm_html = ''
            if _dp and _dp.get('why'):
                _opcol = {'别追': RED, '轻仓试': TEAL, '看': GOLD, '观望': GREY}.get(_dp.get('op', ''), GOLD)
                _llm_html = (f'<div style="color:#a78bfa;font-size:12px;margin-top:3px;">🧠 逻辑深挖：{_dp.get("logic", "")}</div>'
                             f'<div style="color:#e9ecef;font-size:12px;margin-top:2px;">👉 大白话：{_dp.get("why", "")}</div>'
                             + (f'<div style="color:#ced4da;font-size:12px;margin-top:2px;">🎯 操作：<b style="color:{_opcol};">{_dp.get("op", "")}</b> ｜ 买点：{_dp.get("buy", "")} ｜ 止损：{_dp.get("stop", "")}</div>' if _dp.get('op') or _dp.get('buy') or _dp.get('stop') else ''))
            if lbc >= 2 and pos is not None and pos >= 0.85:
                plain = f'{st.get("n")} 已{lbc}连板，处60日高位（{pos*100:.0f}%分位，代码算）'
            elif lbc >= 2:
                plain = f'{st.get("n")} 已经{lbc}连板，{_hhmm(fbt_min) if fbt_min else "盘中"}封的板'
            elif sec_count >= 3 and code == leader_code:
                plain = f'{sec} 今日{sec_count}家涨停，{st.get("n")}最早封板（{_hhmm(fbt_min)}）· 板块里就是它先封的，龙头是它'
            elif sec_count >= 3:
                plain = f'{sec} 今日{sec_count}家涨停，{st.get("n")}是跟着涨停的'
            elif sec_count == 1 and lb >= 2:
                plain = f'{sec} 就{st.get("n")}一只涨停，量比{lb:.1f}'
            elif lb >= 1.5:
                plain = f'{st.get("n")} 量比{lb:.1f}、涨幅{pct:+.1f}%'
            elif lb < 0.5:
                plain = f'{st.get("n")} 涨停了但量比只有{lb:.1f}，缩量封的，虚'
            else:
                plain = f'{st.get("n")} 首板量比{lb:.1f}（代码算）'
            seal_txt = ('已封板' if sealed
                        else ('量比≥1.5（代码算）' if lb >= 1.5 else '量比<1.5（代码算）'))
            _plain_html = ('' if _llm_html else
                           f'<div style="color:#ced4da;font-size:12px;margin-top:3px;">🧠 数据：{plain}</div>')
            rows += f"""<div style="background:#1f2635;border-left:3px solid {RED if sealed else TEAL};border-radius:8px;padding:8px 10px;margin:6px 0;">
<div style="font-size:14px;font-weight:700;color:#fff;">{n}. {st.get('n')} <span style="color:{GREY};font-size:12px;">{code}</span> <span style="color:{_c(pct)};font-weight:800;float:right;">{pct:+.1f}%</span></div>
<div style="color:{GREY};font-size:12px;">题材：{sec} ｜ 量比 {lb:.1f} ｜ {seal_txt}{f' ｜ {lbc}连板' if lbc >= 2 else ''}</div>
{_plain_html}{_llm_html}</div>"""
        if n > 10:
            break
    return rows or '<div style="color:' + GREY + ';font-size:13px;">今天没有哪个方向真正走强，资金分散在各处，别硬找主线去追</div>'

def _sector_heat_block(d, rows=None):
    """行业/题材热度：突出「正在启动」（题材内≥3只 涨幅≥2.5%+量比≥1.8 共振）的板块，而非已高潮；
    + 弱方向（今天别碰）。rows 缺省时内部拉取（打桩兼容）。"""
    tops = d['tops'][:6]
    if not tops:
        return '<div style="color:' + GREY + ';font-size:13px;">今日无题材热度数据</div>'
    if rows is None:
        try:
            rows = _clist_gainers()
        except Exception:
            rows = []
    resonance = {}
    for s in rows:
        ind = re.sub(r'[行业板块概念\s]+', '', s.get('industry') or '') or '其他'
        if float(s.get('pct') or 0) >= 2.5 and float(s.get('lb') or 0) >= 1.8:
            resonance[ind] = resonance.get(ind, 0) + 1
    blocks = []
    order = sorted(tops[:3], key=lambda t: -resonance.get(t[0], 0))   # 🆕正在启动的排最前（用户口径）
    for i, (sec, stocks) in enumerate(order):
        lbc_max = max((int(st.get('lbc') or 0) for st in stocks), default=0)
        fbt_list = [int(st.get('fbt') or 0) for st in stocks if int(st.get('fbt') or 0)]
        fbt_min = min(fbt_list) if fbt_list else 0
        meta = f'涨停{len(stocks)}家 · 最高{lbc_max}板' + (f' · 最早{_hhmm(fbt_min)}封' if fbt_min else '')
        tag = '最强' if i == 0 else ('次强' if i == 1 else '第三')
        n_res = resonance.get(sec, 0)
        mark = (f' <span style="color:{RED};font-weight:700;">🆕 同步启动 {n_res}只（阈值≥3）</span>'
                if n_res >= 3 else f'（最高{lbc_max}板，代码算）')
        blocks.append(f'<div style="font-size:13px;margin:3px 0;">{tag}：<b style="color:{GOLD}">{sec}</b>（{meta}）{mark}</div>')
    weak = d.get('worst', [])[:2]
    w_txt = '、'.join(n for n, _ in weak) if weak else '暂无'
    return ('<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">🏷️ 行业/题材热度</div>'
            + ''.join(blocks)
            + f'<div style="font-size:13px;color:{GREEN};margin:3px 0;">弱：{w_txt}（今天别碰）</div>')


def _hourly_ds(idx, d, b, zbr):
    """每小时行情 LLM 深度解读（五步大白话）。失败返回 ''（原规则操作建议保留）。"""
    if not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return ''
    # 过去1小时新事件（紧跟时事：盘中突发优先纳入整点解读；失败不影响主链路）
    _ev1h = []
    try:
        _ev1h = _event_intel(get_news(20), new_min=70).get('new_1h') or []
    except Exception:
        _ev1h = []
    try:
        idx_txt = '、'.join(f"{x['name']}{x['pct']:+.2f}%" for x in idx) or '未取得'
        tops = '、'.join(f"{sec}({len(sts)}只)" for sec, sts in sorted(d['sectors'].items(), key=lambda kv: -len(kv[1]))[:5]) or '无'
        _g = load_position_gauge()
        _g_txt = (f'（当前仓位仪表盘：{_g.get("suggest", "")}，来自 {_g.get("source", "")}，不得与其矛盾）' if _g else '（仓位仪表盘未生成）')
        fmt = ('【主力游资五步铁律】先看筹码后说话，问三个主力问题，翻译成人话，套游资纪律，自查。\n'
               + '你是一线游资，基于以下盘中数据做整点解读，先判断市场是主力进攻还是主力出货环境，再给仓位。炸板率>45%时，op不得出现「轻仓试」，只能观察或防守。整体偏空时 op 必须直接写「建议空仓」，不推个股；没有明确信号写「等」，不硬凑。\n'
               + '【聚焦原则·强制】op 只给「现在最该做的一个动作」，禁止同时罗列多个方向；next_watch 只给下个整点前最该盯的1个点；contagion 只给1个最确定的传染方向。信息再多也只挑最重要的讲，宁缺毋滥。\n'
               + '【传染研判·硬要求】必须单独回答 contagion：今天哪个板块在突发异动（用最强板块/领涨数据），它最可能传染到哪个「还没启动」的题材和个股，讲清传染逻辑、原因、暗线（为什么资金会顺着产业链/比价/情绪扩散过去）以及确认传染的信号（什么时候算真传染）。没有可传染方向就写「暂无明确传染方向」。\n只输出 JSON：\n'
               + '{"overall":"现在盘面真正什么情况(用数据)+主力阶段，一句大白话+能不能做","emotion_score":0-100,"op":"该干什么：具体动作+仓位档(空仓/1成/2成/半仓)，只给最该做的一个动作","risk":"最大风险+什么情况必须撤","next_watch":"下一小时最该盯的1个点","contagion":"突发异动板块→传染方向：板块名→题材+未启动个股（点名具体股票）+传染逻辑与暗线+确认信号，≥40字"}\n'
               + '数据：指数 ' + idx_txt + '；涨停{d["lu"]}家 炸板{d["zb"]}家(炸板率{zbr*100:.0f}%) 跌停{d["dt"]}家 最高{d["max_lbc"]}板；情绪=' + b + '；最强板块 ' + tops + _g_txt + '\n'
               + '【过去1小时新事件】（紧跟时事：只挑真正能改变盘面的，纳入 overall/op/risk 判断；没有就写「无」）：' + ('；'.join(_ev1h) if _ev1h else '无') + '\n炸板率>45% 时，op 不得出现「轻仓试」，只能观察或防守。')
        t = ask_deepseek({'task': 'hourly_ds', 'idx': idx_txt, 'tops': tops, 'b': b,
                          'lu': d['lu'], 'zb': d['zb'], 'dt': d['dt'], 'max_lbc': d['max_lbc'],
                          'news_1h': ('；'.join(_ev1h) if _ev1h else '无'),
                          'format': fmt}, purpose='hourly_ds')
        if not t:
            return ''
        _j = json.loads(t)
        out = []
        if _j.get('overall'):
            out.append('<div style="color:#e9ecef;font-size:13px;">🧭 盘面：' + str(_j['overall']) + '</div>')
        _es = _j.get('emotion_score')
        if _es not in (None, ''):
            try:
                out.append('<div style="color:' + GOLD + ';font-size:13px;margin-top:3px;">📊 情绪分：' + str(int(float(_es))) + '/100</div>')
            except Exception:
                pass
        _op = str(_j.get('op') or '')
        if zbr > 0.45 and '轻仓试' in _op:
            _op = _op.replace('轻仓试', '观察')
        if _op:
            out.append('<div style="color:' + GOLD + ';font-size:13px;margin-top:3px;">💡 操作：' + _op + '</div>')
        if _j.get('risk'):
            out.append('<div style="color:' + RED + ';font-size:13px;margin-top:3px;">⚠️ 风险：' + str(_j['risk']) + '</div>')
        if _j.get('next_watch'):
            out.append('<div style="color:' + GREY + ';font-size:13px;margin-top:3px;">👀 下一盯点：' + str(_j['next_watch']) + '</div>')
        if _j.get('contagion'):
            out.append('<div style="color:#94d4d0;font-size:13px;margin-top:3px;line-height:1.6;">🔄 传染方向：' + str(_j['contagion']) + '</div>')
        if not out:
            return ''
        return '<div style="margin-top:8px;padding:10px;background:#1c2230;border-left:4px solid ' + TEAL + ';border-radius:8px;">' + ''.join(out) + '</div>'
    except Exception:
        return ''


# ============ 新增B·持仓全天诊断卡（涨跌≥3%或破位触发；LLM 五字段；小时级去重） ============
DIAG_DEDUPE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'diag_dedupe.json')


def _diag_dedupe(key):
    """新增卡去重（类型+标的+日期小时）；已推过返回 True。"""
    try:
        with open(DIAG_DEDUPE_PATH, encoding='utf-8') as f:
            d = json.load(f)
    except Exception:
        d = {}
    if d.get(key) == _bj_now().strftime('%Y-%m-%d %H'):
        return True
    d[key] = _bj_now().strftime('%Y-%m-%d %H')
    try:
        os.makedirs(os.path.dirname(DIAG_DEDUPE_PATH), exist_ok=True)
        with open(DIAG_DEDUPE_PATH, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        _git_commit_push(DIAG_DEDUPE_PATH, 'update diag dedupe')
    except Exception:
        pass
    return False


def _hold_diag_card():
    """🐉 持仓诊断：任一持仓涨跌幅≥3%（或破5日线/触及止损）时触发，LLM 逐只给 stage/act/trigger/stop/reason/hold_link。
    预算用尽/失败 → 不推（不空推）。返回 HTML 片段或 ''。"""
    if not HOLDINGS or not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return ''
    rows = []
    for h in HOLDINGS:
        q = _qt(h['code'])
        if not q or not q.get('price'):
            continue
        pct = float(q.get('pct') or 0)
        if abs(pct) < 3.0:
            continue
        rows.append({'name': h['name'], 'code': h['code'].replace('sz', '').replace('sh', ''),
                     'cost': h.get('cost'), 'price': round(float(q['price']), 2), 'pct': round(pct, 1),
                     'sector': h.get('sector', '')})
    if not rows:
        return ''
    key = 'diag|' + _bj_now().strftime('%Y-%m-%d') + '|' + '、'.join(r['name'] for r in rows)
    if _diag_dedupe(key):
        return ''
    today_main = ''
    try:
        d0 = get_pools()
        today_main = '、'.join(n for n, _ in (d0.get('tops') or [])[:3])
    except Exception:
        pass
    _g = load_position_gauge()
    _g_txt = ('仓位仪表盘：' + str(_g.get('suggest', '')) + '（' + str(_g.get('source', '')) + '）' if _g else '仓位仪表盘未生成')
    hold_data = '；'.join(f"{r['name']}({r['code']}) 成本{r['cost']} 现价{r['price']} 涨跌{r['pct']:+.1f}% 板块{r['sector']}" for r in rows)
    fmt = ('对以下每只持仓做诊断，只输出 JSON（全大白话，禁模板句）：\n'
           '{"per":[{"name":"持仓名","stage":"启动/中段/高位/破位","act":"持有|减半|止损","trigger":"触发信号(价位/量能/形态,可观察)","stop":"止损位","reason":"大白话≥20字","hold_link":"与今日主线关系：同题材传染/无联动/反向"}],"overall":"总仓位建议一档(空仓/1成/2成/半仓)"}\n'
           '持仓数据：' + hold_data + '\n'
           '今日主线：' + (today_main or '未取得') + '\n'
           + _g_txt + '\n'
           '涨跌≥3%说明有异动，重点给触发与止损；破5日线必须 act=减半或止损，不得持有。')
    t = ask_deepseek({'task': 'hold_diag_card', 'holdings': rows, 'mainline': today_main,
                      'gauge': _g, 'format': fmt}, purpose='hold_diag')
    if not t:
        return ''
    try:
        _j = json.loads(t)
    except Exception:
        return ''
    per = _j.get('per') or []
    if not per:
        return ''
    card = []
    card.append('<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ffd43b;">🐉 持仓诊断</div>')
    for it in per:
        nm = str(it.get('name') or '')
        act = str(it.get('act') or '')
        ac = RED if act == '止损' else (GOLD if act == '减半' else TEAL)
        card.append(f'<div style="background:#1c2230;border-left:4px solid {ac};border-radius:8px;padding:8px 10px;margin:5px 0;font-size:13px;">'
                    f'<b style="color:#fff;">{nm}</b> <span style="color:{ac};font-weight:700;">建议：{act}</span>'
                    f'<span style="color:{GREY};font-size:12px;"> ｜ 阶段：{it.get("stage","")} ｜ 触发：{it.get("trigger","")} ｜ 止损：{it.get("stop","")}</span><br>'
                    f'<span style="color:#ced4da;font-size:12px;">🧠 {it.get("reason","")}</span><br>'
                    f'<span style="color:#66d9e8;font-size:12px;">🔗 主线关系：{it.get("hold_link","")}</span></div>')
    if _j.get('overall'):
        card.append(f'<div style="margin-top:4px;font-size:13px;color:{GOLD};">📊 总仓位建议：{_j.get("overall")}</div>')
    return ''.join(card)


def build_hourly():
    """每小时行情解读+操作建议（09:30/10:30/13:30/14:30；纯数据播报，不调 LLM 控预算）。"""
    idx = get_indices()
    d = get_pools()
    b, r, avg, zbr = sentiment(idx, d)
    bits = '<span style="color:#495057">｜</span>'.join(
        f"<span style='color:{_c(x['pct'])};font-weight:700'>{x['name']}{x['pct']:+.2f}%</span>" for x in idx)
    # 档位：情绪偏多/偏空/震荡 → 总仓档位；操作判读一律交大模型，不再出规则版建议
    ac = TEAL if b == '偏多' else (GREEN if b == '偏空' else GOLD)
    advice = ''
    risk_line = (f'炸板率 {zbr*100:.0f}%｜涨停 {d["lu"]}家｜炸板 {d["zb"]}家'
                 f'｜跌停 {d["dt"]}家｜最高 {d["max_lbc"]}板')
    rc = GREY
    _overall = (f'<div style="margin-top:4px;padding:8px 10px;background:#1c2830;border-left:4px solid {ac};'
                f'border-radius:8px;font-size:13px;color:#e9ecef;">🧭 今天整体：{b}，涨停{d["lu"]}家炸板{d["zb"]}家'
                f'（炸板率 {zbr*100:.0f}%），最高{d["max_lbc"]}板；仓位档位 {_pos_advice(b)}。</div>')
    _ds_block = _hourly_ds(idx, d, b, zbr)
    inner = f"""{_overall}
<div style="font-size:14px;">{bits}</div>
<div style="margin-top:6px;font-size:14px;">🔴涨停<b style="color:{RED}">{d['lu']}</b> 🟢炸板<b style="color:{GREEN}">{d['zb']}</b> 🟢跌停<b style="color:{GREEN}">{d['dt']}</b> 最高<b style="color:{GOLD}">{d['max_lbc']}板</b> ｜ 情绪 <b style="color:{_c(avg)}">{b}</b>（炸板率 {zbr*100:.0f}%）</div>
<div style="margin-top:4px;font-size:13px;">{breadth_sample()}</div>
<div style="margin-top:4px;font-size:13px;">{money_flow_note()}</div>
{_ds_block or ''}
<div style="margin-top:8px;padding:9px 11px;background:#2a1f22;border-left:4px solid {rc};border-radius:8px;font-size:13px;color:{rc};">⚠️ {risk_line}</div>{leader_divergence(d)}
<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">🔥 当前最强 TOP10（每只带题材/量比/能否操作）</div>{_top10_cards(d)}
{_sector_heat_block(d)}
<div style="margin-top:8px;font-size:13px;color:{TEAL};">🔗 {coarse_linkage(d)}</div>{_health_card(d['lu'], d['zb'], zbr, d['max_lbc'], '、'.join(n for n, _ in (d.get('tops') or [])[:3]), money_flow_note())}{_hold_diag_card()}{build_events('noon')}{pos_cap_line(b, None)}"""
    return _wrap(inner, '⏱️', '盘中解读')


def _fx(code):
    """新浪外汇：返回 (最新价str, 涨跌幅%) 或 (None, None)。"""
    try:
        req = urllib.request.Request(f'https://hq.sinajs.cn/list={code}',
                                     headers={**UA, 'Referer': 'https://finance.sina.com.cn/'})
        txt = urllib.request.urlopen(req, timeout=8).read().decode('gbk', errors='ignore')
        f = txt.split('"')[1].split(',')
        if len(f) > 11 and f[8]:
            return f[8], float(f[10])
    except Exception:
        pass
    return None, None


def _btc_quote():
    """比特币行情（OKX/币安，超时即 None，不造假）。"""
    for u in ('https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT',
              'https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT'):
        try:
            txt = _get(u, timeout=5)
            d = json.loads(txt)
            if isinstance(d, dict) and 'data' in d and d.get('data'):
                t = d['data'][0]
                return t.get('last'), float(t.get('changePc') or 0)
            if isinstance(d, dict) and 'lastPrice' in d:
                return d.get('lastPrice'), float(d.get('priceChangePercent') or 0)
        except Exception:
            continue
    _record('btc', False, 5, 'timeout')  # 诚实记录缺源
    return None


def _global_one_line():
    """① 隔夜外盘一句话：美股均值+原油+黄金+美元+日元+比特币（只说对A股有影响的）。"""
    out = []
    try:
        gl = get_global()
        if gl:
            avg = sum(p for _, _, p in gl) / len(gl)
            out.append('美股均值%+.1f%%' % avg)
    except Exception:
        pass
    for nm, code in (('原油', 'hf_CL'), ('黄金', 'hf_GC')):
        try:
            txt, ok = _getm('http://qt.gtimg.cn/q=' + code, 'gl_' + code, timeout=10)
            if ok and txt and '"' in txt:
                s = txt.split('"')[1].split(',')
                if len(s) > 1 and s[1]:
                    out.append(nm + '%+.2f%%' % float(s[1]))
        except Exception:
            pass
    usd = _fx('fx_susdcny')
    if usd[0]:
        try:
            out.append('美元兑人民币 %.4f' % float(usd[0]))
        except Exception:
            out.append('美元兑人民币 ' + usd[0])
    jpy = _fx('fx_susdjpy')
    if jpy[0]:
        try:
            out.append('美元兑日元 %.1f' % float(jpy[0]))
        except Exception:
            pass
    btc = _btc_quote()
    if btc:
        out.append('比特币 $%s(%+.2f%%)' % (btc[0], btc[1]))
    return '；'.join(out) if out else '外盘数据未取得'


_CAT_POL = ('政策', '央行', '证监会', '监管', '发改委', '国务院', '财政部', '外汇', '金融监管', '降准', '降息', 'LPR', '试点', '制度', '办法', '条例', '改革', '部署')
_CAT_INT = ('美联储', '美国', '欧盟', '欧洲', '日本', '韩国', '印度', '全球', '海外', '出口', '关税', '贸易', '美股', '港股', '中概', '原油', '黄金', '美元', '日元', '欧央行', '英国', '国际')
_CAT_COM = ('净利', '营收', '业绩', '预增', '预减', '重组', '收购', '增持', '回购', '中标', '合同', '分红', '退市', '募资', '质押', '股东', '减持', '不减持', '转让', '承诺')
_CAT_IND = ('芯片', '半导体', '新能源', '汽车', '电池', '光伏', '储能', 'AI', '算力', '机器人', '消费', '医药', '地产', '钢铁', '有色', '面板', '存储', '军工', '通信', '软件', '数据', '行业', '产业', '订单', '出货', '装机', '涨价', '智能')


def _cat_news(news):
    """④ 新闻四类分类（规则）：政策/产业/公司/国际，各取≤3条，过滤注册类。返回 (dict, 丢弃数)。"""
    cats = {'政策/监管': [], '产业/行业': [], '公司大事': [], '国际/外围': []}
    drop = 0
    for nw in news:
        text = nw['title'] + ' ' + (nw.get('summary') or '')
        if ('注册资本' in text or '工商变更' in text or '经营范围' in text) and not any(k in text for k in ('业绩', '净利', '订单', '中标', '重组')):
            drop += 1
            continue
        cat = '产业/行业'
        if any(k in text for k in _CAT_POL):
            cat = '政策/监管'
        elif any(k in text for k in _CAT_INT):
            cat = '国际/外围'
        elif any(k in text for k in _CAT_COM):
            cat = '公司大事'
        elif any(k in text for k in _CAT_IND):
            cat = '产业/行业'
        if len(cats[cat]) < 3:
            cats[cat].append(nw)
    return cats, drop


def _plain_for(nw, cat):
    """新闻大白话：命中 NEWS_THEME_MAP 用板块大白话+真实个股，否则按类模板+真实个股。返回 (plain, sec)。"""
    text = nw['title'] + ' ' + (nw.get('summary') or '')
    hit = _stock_hits(text)
    for kws, sec, stocks, plain in NEWS_THEME_MAP:
        if any(k in text for k in kws):
            return (plain + (f'｜相关：{hit}' if hit else '')), sec
    base = {'政策/监管': '政策定调，留意受益方向', '产业/行业': '行业消息，关注产业链动向',
            '公司大事': '个股消息，注意对应标的波动', '国际/外围': '外围消息，对A股影响待观察'}[cat]
    return (base + (f'｜相关：{hit}' if hit else '')), ''


def _stock_hits(text):
    """新闻文本里命中的真实个股名（去板块词）。"""
    sec_words = {sec for _, sec, _, _ in NEWS_THEME_MAP}
    hits = []
    for kws, sec, stocks, plain in NEWS_THEME_MAP:
        for stk in stocks.split('、'):
            stk = stk.strip()
            if stk and len(stk) >= 3 and stk not in sec_words and not stk.endswith('链') and stk in text and stk not in hits:
                hits.append(stk)
    return '、'.join(hits[:3])


def _mainline_3(gl_avg, news, d):
    """② 今日主线方向 3 行（纯数据事实，判读交大模型）。"""
    w1 = ''
    cats, _ = _cat_news(news)
    npol, nind, ncom, nint = (len(cats[k]) for k in ('政策/监管', '产业/行业', '公司大事', '国际/外围'))
    w2 = ''
    tops = d.get('tops') or []
    if tops:
        sec, sts = tops[0]
        lead = sorted(sts, key=lambda x: -(int(x.get('lbc') or 0)))[0] if sts else None
        w3 = ('昨日最强板块：%s，%d 家涨停%s' % (sec, len(sts), ('，龙头 ' + lead['n']) if lead else ''))
    else:
        w3 = ''
    return w1, w2, w3


def _sector_wind(d, news):
    """③ 板块风向标：强势/弱势只列代码实算数据，不写"可关注/今天别碰"这类判读。"""
    strong = []
    for sec, sts in (d.get('tops') or [])[:3]:
        lu = len(sts)
        lead = sorted(sts, key=lambda x: -(int(x.get('lbc') or 0)))[0] if sts else None
        lbc = int(lead.get('lbc') or 0) if lead else 0
        cont = ('%d 连板' % lbc) if lead else ''
        if lead:
            _ct = (' ' + cont) if cont else ''
            strong.append((sec, '昨日%d家涨停、龙头%s%s' % (lu, lead['n'], _ct)))
        else:
            strong.append((sec, '昨日%d家涨停' % lu))
    weak = []
    for sec, sts in (d.get('worst') or [])[:2]:
        # worst 来自 get_pools 的 zb_sec.items()，第二项是「家数」int（不是列表），
        # 2026-11-07 修：原来直接 len() 会 TypeError: object of type 'int' has no len()，整张盘前卡崩掉
        _n = sts if isinstance(sts, int) else (len(sts) if sts else 0)
        weak.append((sec, '跌停/炸板集中 %d 家' % _n))
    for nw in news[:12]:
        text = nw['title'] + ' ' + (nw.get('summary') or '')
        tag, _ = classify_news(text)
        if tag == '利空':
            for kws, sec, stocks, plain in NEWS_THEME_MAP:
                if any(k in text for k in kws) and sec not in [w[0] for w in weak]:
                    weak.append((sec, '利空消息：' + str(nw.get('title') or '')[:24]))
                    break
    return strong[:3], weak[:3]


def _goodbad_action(news, pre_map=None):
    """⑤ 利好利空精选（行动版）：利好≤3、利空≤3。利好/利空标签与影响面只认大模型判读；
    模型未判读的条目不入选，不再用 classify_news + _plain_for 规则版凑数。"""
    good, bad = [], []
    pre_map = pre_map or {}
    for nw in news[:20]:
        _dn = pre_map.get(_pre_key(nw['title'])) or {}
        _gd, _bd = str(_dn.get('good') or '').strip(), str(_dn.get('bad') or '').strip()
        _wh = str(_dn.get('why') or '').strip()
        if not _dn or not _wh:
            continue
        _rg2 = bool(_gd) and ('无明显' not in _gd)
        _rb2 = bool(_bd) and ('无明显' not in _bd)
        if _rb2 and not _rg2:
            tag = '利空'
        elif _rg2 and not _rb2:
            tag = '利好'
        else:
            continue
        if tag == '利好' and len(good) >= 3:
            continue
        if tag == '利空' and len(bad) >= 3:
            continue
        _sec2 = str(_dn.get('sec') or '').strip()
        impact = _sec2 if _sec2 else '未标注板块'
        _txt = _gd if tag == '利好' else _bd
        item = ('<b>' + nw['title'][:38] + '</b> <span style="color:' + GREY + '">→ 影响：'
                + impact + '</span> ' + _txt + '<br><span style="color:#ced4da;">👉 ' + _wh + '</span>')
        (good if tag == '利好' else bad).append(item)
    return good, bad


def _action_list(news, d, gl_avg, pre_map=None):
    """⑧ 今日操作清单（核心）：可关注3-5、坚决回避3-5、持仓提示。
    代码只做筛选与标签（昨日涨停/连板一律进回避、可关注只许未涨停低位票），
    仓位与买卖动作不给规则版，统一标注"见 AI 判读"。"""
    try:
        zt = _zt_pool_names()
    except Exception:
        zt = set()
    watch = []
    avoid = []
    for sec, sts in (d.get('tops') or [])[:5]:
        for st in sts[:3]:
            nm, cd = str(st.get('n') or ''), str(st.get('c') or '')
            if not nm:
                continue
            if nm not in [a[0] for a in avoid]:
                # 昨日涨停/连板一律只观察：这种票今天要么一字要么秒板，推给用户就是买不到
                avoid.append((nm + '（' + sec + '）', '昨日涨停/连板，今天只观察不接力'))
    # 可关注池：从昨收涨幅榜里挑「明天真能上手」的票（未涨停 + 涨幅温和 + 量能放大 + 不在最高位）
    _strong_secs = {s for s, _ in (d.get('tops') or [])[:5]}
    try:
        _gainer_rows = _clist_gainers() or []
    except Exception:
        _gainer_rows = []
    for _g in _gainer_rows:
        _nm, _cd = str(_g.get('name') or ''), str(_g.get('code') or '')
        if not _nm or _nm in zt or _cd in zt:
            continue                      # 昨日涨停的票直接不列
        _pct, _lb, _turn = (_g.get('pct') or 0), (_g.get('lb') or 0), (_g.get('turn') or 0)
        if not (2.0 <= _pct <= 7.0) or _lb < 1.5 or _turn < 1.5:
            continue                      # 涨幅太小没弹性、太大明天买不到、量能不够不做
        _hi, _pr = (_g.get('high') or 0), (_g.get('price') or 0)
        if _hi and _pr and _pr >= _hi * 0.995:
            continue                      # 收在当日最高=情绪透支
        _sec_n = _sec_clean(_g.get('industry') or '') or '其他'
        if any(_nm in w[0] for w in watch):
            continue
        _why = ('昨日涨%.1f%%、量比%.1f、换手%.1f%%，%s' % (
            _pct, _lb, _turn,
            ('所属' + _sec_n + '是昨日强势方向') if _sec_n in _strong_secs else '放量温和上涨、位置不高'))
        watch.append((_nm + '（' + _sec_n + '）', _why, ''))
        if len(watch) >= 5:
            break
    good, _ = _goodbad_action(news, pre_map)
    for g in good[:3]:
        hit = _stock_hits(re.sub(r'<[^>]+>', '', g))
        if hit and not any(hit.split('、')[0] in w[0] for w in watch):
            stk = hit.split('、')[0]
            if stk in zt:
                avoid.append((stk, '昨日涨停/连板，只观察不操作'))
                continue
            watch.append((stk, '新闻利好催化', ''))
    bad_secs = _sector_wind(d, news)[1]
    for sec, why in bad_secs[:2]:
        avoid.append((sec, why))
    _, bad = _goodbad_action(news, pre_map)
    for b in bad[:2]:
        hit = _stock_hits(re.sub(r'<[^>]+>', '', b))
        if hit:
            avoid.append((hit.split('、')[0], '利空消息压着'))
    hold_rows = [h['name'] + '（成本%.2f）' % h['cost'] for h in HOLDINGS]
    return watch[:5], avoid[:5], hold_rows


# ============ 盘前重点个股参考（小白友好版：昨收/题材/操作提示） ============
def _focus_stocks(d, news):
    """重点个股参考（FOCUS_N 只）：昨日主线低位跟风 + 新闻命中个股。只选真实数据，不编造。
    规则强制：昨日涨停/连板票一律排除（禁止把涨停票列为可操作，规格硬约束）。
    返回 [(name, code, prev_close, sector, plain, tip, role)]。"""
    out, seen = [], set()
    try:
        zt = _zt_pool_names()
    except Exception:
        zt = set()
    # ① 昨日主线板块中的低位/未涨停代表（涨停池排除后剩跟风票；全涨停则跳过，宁缺毋滥）
    tops5 = {x[0] for x in d['tops'][:5]}
    for n, stocks in d['sectors'].items():
        if n not in tops5:
            continue
        for st in stocks[:2]:
            nm = st.get('n', '')
            cd = st.get('c', '')
            if nm in seen or not nm:
                continue
            if nm in zt or cd in zt:
                continue  # 昨日涨停/连板：禁止列为可操作
            seen.add(nm)
            out.append((nm, cd, st.get('pc') or '—', n,
                        f'{n}板块昨日强势，该股未涨停处低位，补涨/跟风候选。',
                        '今天看竞价是否高开2~5%且量比>1.5，可低吸试仓；低开超过3%先观望',
                        '低位跟风'))
            if len(out) >= FOCUS_N:
                return out[:FOCUS_N]
    # ② 新闻命中个股（NEWS_THEME_MAP 规则提取，涨停池同样排除，角色=关注）
    for nw in news[:12]:
        text = nw['title'] + ' ' + (nw.get('summary') or '')
        for _kws, sec, stocks, plain in NEWS_THEME_MAP:
            for stk in (stocks or '').split('、'):
                stk = stk.strip()
                if not stk or len(stk) < 2 or stk in seen:
                    continue
                if stk in zt:
                    continue  # 昨日涨停/连板：禁止列为可操作
                if stk in text:
                    seen.add(stk)
                    out.append((stk, '—', '—', sec, plain or '新闻催化', '看竞价强度，放量再低吸，禁止追高', '关注'))
        if len(out) >= FOCUS_N:
            break
    return out[:FOCUS_N]


def build_pre():
    """盘前速递 08:30：今日操盘地图（外盘一句话→事件驱动主线→主线方向→板块风向→新闻四类→利好利空精选→操作清单）。"""
    gl = get_global()
    gl_avg = sum(p for _, _, p in gl) / max(len(gl), 1) if gl else 0.0
    news = get_news(40)
    intel = _event_intel(news)
    d = get_pools()
    one = _global_one_line()
    w1, w2, w3 = _mainline_3(gl_avg, news, d)
    strong, weak = _sector_wind(d, news)
    cats, _ = _cat_news(news)
    _pre_news_map = _pre_news_deep(news)
    good, bad = _goodbad_action(news, _pre_news_map)
    watch, avoid, hold_rows = _action_list(news, d, gl_avg, _pre_news_map)
    ds_html = _pre_ds(news, intel)
    # —— 事件驱动主线小节（量化评分 Top3，紧跟时事核心）——
    _ev_rows = ''
    for m in intel.get('mainlines') or []:
        _lt = m['latest'][11:16] if len(m.get('latest', '')) >= 16 else m.get('latest', '')
        _ev_rows += ('<div style="background:#1f2635;border-left:3px solid ' + GOLD + ';border-radius:6px;padding:6px 8px;margin:5px 0;">'
                     '<div style="font-size:13px;color:#fff;"><b>' + m['sec'] + '</b> '
                     '<span style="color:' + GREY + ';font-size:12px;">事件' + str(m['n']) + '条 ｜ 净情绪' + ('+' if m['net'] > 0 else '') + str(m['net']) + ' ｜ 最新' + _lt + '</span></div>'
                     '<div style="font-size:12px;color:' + TEAL + ';">代表：' + '；'.join(m['tops'][:2]) + '</div></div>')
    if not _ev_rows:
        _ev_rows = '<div style="color:' + GREY + ';font-size:13px;">今天没有能带动板块的硬事件，消息面偏散，等明天的新催化</div>'
    _ev_block = ('<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">📡 事件驱动主线（量化评分·紧跟时事）</div>' + _ev_rows)
    s_strong = ''.join('<div style="margin:4px 0;font-size:13px;">🟢 <b>' + sec + '</b> — ' + why + '</div>' for sec, why in strong)
    s_weak = ''.join('<div style="margin:4px 0;font-size:13px;">🔴 <b>' + sec + '</b> — ' + why + '</div>' for sec, why in weak)
    news_rows = ''
    for cat in ('政策/监管', '产业/行业', '公司大事', '国际/外围'):
        items = cats[cat]
        if not items:
            continue
        rows = ''
        for nw in items:
            _dn = _pre_news_map.get(_pre_key(nw['title']))
            if _dn and _dn.get('why'):
                _gd, _bd = _dn.get('good') or '', _dn.get('bad') or ''
                _lg, _wh, _ac = _dn.get('logic') or '', _dn['why'], _dn.get('act') or ''
                _sec2 = _dn.get('sec') or ''
                plain = ('✅ ' + _gd + '<br>⚠️ ' + _bd + '<br>🧠 逻辑：' + _lg + '<br>👉 大白话：' + _wh
                         + ('<br>💡 操作：' + _ac if _ac else '')
                         + (('｜板块：' + _sec2) if _sec2 else ''))
                _rg2 = bool(_gd) and ('无明显' not in _gd)
                _rb2 = bool(_bd) and ('无明显' not in _bd)
                tag = '利好' if (_rg2 and not _rb2) else ('利空' if (_rb2 and not _rg2) else ('双向' if (_rg2 and _rb2) else '待判读'))
            else:
                # 模型未判读：只列标题/时间，不再用 _plain_for 规则生成大白话与板块
                plain = ''
                _sec2 = ''
                tag = '待判读'
            tag_html = (f'<span style="background:{RED if tag=="利好" else GREEN if tag=="利空" else GREY};'
                        f'color:#161b26;border-radius:4px;padding:0 6px;font-size:11px;font-weight:700;">{tag}</span>')
            rows += ('<div style="background:#1f2635;border-left:3px solid ' + GOLD + ';border-radius:6px;padding:6px 8px;margin:5px 0;">'
                     '<div style="font-size:12px;color:' + GREY + ';">' + (nw['ts'][11:16] if len(nw.get('ts', '')) >= 16 else nw.get('ts', '')) + ' ' + tag_html + '</div>'
                     '<div style="font-size:13px;color:#e9ecef;">' + nw['title'][:60] + '</div>'
                     '<div style="font-size:12px;color:' + TEAL + ';line-height:1.6;">👉 ' + plain + (('｜板块：' + _sec2) if _sec2 else '') + '</div></div>')
        news_rows += '<div style="margin-top:8px;font-size:14px;font-weight:800;color:#ff922b;">▍' + cat + '</div>' + rows
    if not news_rows:
        news_rows = '<div style="color:' + GREY + ';font-size:13px;">今日暂未获取到有效新闻（不伪造内容）</div>'
    # ⑤ 重点个股参考（昨日主线龙头 + 新闻命中，带昨收/题材/操作提示）
    focus = _focus_stocks(d, news)
    _foc_map = _focus_deep(focus)
    focus_rows = ''.join(
        (lambda nm, code, prev, sec, plain, tip, role:
            f"""<div style="background:#1f2635;border-left:3px solid {GOLD};border-radius:8px;padding:8px 10px;margin:6px 0;">
<b style="color:#fff;">{nm}</b> <span style="color:{GREY};font-size:12px;">{code}</span>
<span style="color:{GREY};font-size:12px;">昨收 {prev} ｜ 题材：{sec} ｜ 角色：<b style="color:{GOLD};">{role}</b></span>
<div style="color:#ced4da;font-size:12px;margin-top:3px;">🧠 {(_foc_map.get(nm) or {}).get("plain", "") or ''}</div>
<div style="color:{TEAL};font-size:12px;margin-top:3px;">👉 {(_foc_map.get(nm) or {}).get("tip", "") or ''}</div></div>"""
        )(nm, code, prev, sec, plain, tip, role)
        for nm, code, prev, sec, plain, tip, role in focus)
    focus_block = (f'<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">⑤ 重点个股参考（{len(focus)}只）</div>{focus_rows}'
                   if focus_rows else '<div style="margin-top:10px;font-size:13px;color:' + GREY + ';">代码筛选下今日无未涨停低位标的（昨日涨停票不列）</div>')
    g_rows = ''.join('<div style="margin:5px 0;font-size:13px;">🟢 ' + g + '</div>' for g in good)
    b_rows = ''.join('<div style="margin:5px 0;font-size:13px;">🔴 ' + b + '</div>' for b in bad)
    w_rows = ''.join('<div style="margin:5px 0;font-size:13px;">✅ <b>' + nm + '</b> — ' + why + '｜<span style="color:' + GOLD + ';">仓位 ' + pos + '</span></div>' for nm, why, pos in watch)
    a_rows = ''.join('<div style="margin:5px 0;font-size:13px;">⛔ <b>' + nm + '</b> — ' + why + '</div>' for nm, why in avoid)
    h_rows = ''
    if hold_rows:
        h_rows = ('<div style="margin-top:8px;font-size:14px;font-weight:800;color:#ff922b;">▍已持仓提示</div>'
                  + ''.join('<div style="margin:4px 0;font-size:13px;">🏦 ' + h + '</div>' for h in hold_rows))
    ds_block = ('<div style="margin-top:10px;padding:10px;background:#1c2230;border-left:4px solid ' + GOLD + ';border-radius:8px;">'
                '<div style="font-size:15px;font-weight:800;color:' + GOLD + ';">🤖 DeepSeek 大白话研判</div>' + ds_html + '</div>') if ds_html else ''
    inner = ("""<div style="margin-top:8px;font-size:15px;font-weight:800;color:#ff922b;">🧭 今日操盘地图｜方向 + 买什么 + 避开什么</div>
<div style="margin-top:8px;font-size:13px;color:#e9ecef;">🌏 隔夜外盘一句话：""" + one + """</div>
""" + _ev_block + """
""" + (('<div style="margin-top:10px;font-size:13px;color:#e9ecef;">' + w3 + '</div>') if w3 else '') + """
<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">③ 板块风向标</div>
<div style="font-size:13px;color:""" + RED + ';">强势风向（可关注）</div>' + s_strong + """
<div style="margin-top:6px;font-size:13px;color:""" + GREEN + ';">弱势/回避（今天别碰）</div>' + s_weak + """
""" + focus_block + """
<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">⑥ 新闻汇总</div>""" + news_rows + """
<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">⑦ 利好利空精选（行动版）</div>
<div style="font-size:13px;color:""" + RED + ';">利好（≤3条）</div>' + (g_rows if g_rows else '<div style="font-size:13px;color:' + GREY + ';">今日暂无明确利好</div>') + """
<div style="margin-top:6px;font-size:13px;color:""" + GREEN + ';">利空（≤3条）</div>' + (b_rows if b_rows else '<div style="font-size:13px;color:' + GREY + ';">今日暂无明确利空</div>') + """
<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">⑧ 今日操作清单</div>
<div style="font-size:13px;color:""" + RED + ';">可关注/可低吸（3-5只）</div>' + (w_rows if w_rows else '<div style="font-size:13px;color:' + GREY + ';">今日代码筛选无合适标的（买卖动作见本卡 AI 段）</div>') + """
<div style="margin-top:6px;font-size:13px;color:""" + GREEN + ';">坚决回避（3-5只/板块）</div>' + (a_rows if a_rows else '<div style="font-size:13px;color:' + GREY + ';">今日暂无明确回避标的</div>') + h_rows + ds_block + """
""" + build_events('pre') + pos_cap_line(_emotion_from_pools(d), None) + '"""')
    return _wrap(inner, '🧭', '今日操盘地图')


# ============ 各时段 ============



def auction_scan():
    """竞价强票：扫昨日涨停股今日竞价（开幅+量比三分法）。"""
    day = datetime.now().strftime('%Y%m%d')
    # 昨日日期
    y = datetime.fromtimestamp(datetime.now().timestamp() - 86400).strftime('%Y%m%d')
    cands = []
    for dt in (day, y):
        try:
            pool = (json.loads(_get(
                f'https://push2ex.eastmoney.com/getTopicZTPool?ut=7eea3edcaed734bea9cbfc24409ed989'
                f'&dpt=wz.ztzt&Pageindex=0&pagesize=200&sort=fbt:asc&date={dt}')
            ).get('data') or {}).get('pool') or []
            if pool:
                break
        except Exception:
            pool = []
    for s in pool[:80]:
        code = s.get('c')
        sym = ('sh' if code.startswith('6') else 'sz') + code
        try:
            q = _qt(sym)
            if not q or not q['prev']:
                continue
            op = (q['open'] / q['prev'] - 1) * 100
            act, why = three_way(op, q.get('lb', 0))
            if act == '观察':
                continue
            cands.append({'n': s.get('n'), 'code': code, 'op': op,
                          'lb': q.get('lb', 0), 'act': act, 'why': why})
        except Exception:
            pass
    cands.sort(key=lambda x: (0 if x['act'] == '直接买' else 1, -x['op']))
    return cands[:10]


def _pos_risk(sym, price):
    """位置风险：近60日位置。返回 (pos, 标签)。K线失败返回 (None,'')。"""
    try:
        arr = get_klines(sym, 125)
        if len(arr) >= 60:
            hi60 = max(float(r[2]) for r in arr[-60:])
            lo60 = min(float(r[1]) for r in arr[-60:])
            pos = (price - lo60) / (hi60 - lo60) if hi60 > lo60 else 0.5
            tag = '低位' if pos < 0.5 else ('中位' if pos < 0.75 else '⚠️高位')
            return pos, tag
    except Exception:
        pass
    return None, ''


def build_auction(title='竞价观察'):
    """竞价观察 09:25（集合竞价最后阶段数据更可靠；数据延迟最多重试到 09:27，超时跳过不推空卡）：
    持仓竞价诊断 + 全市场涨幅榜→硬过滤→双重打分→TOP8 + 行业风向 + DeepSeek 大白话总结。
    title 参数：尾盘竞价筛选（14:55 触发）复用本函数，标题区分。"""
    # FIX18: 早触发等待——09:20-24 触发时等齐集合竞价(09:25)再取数，避免推数据不全的早卡
    _bj0 = _bj_now()
    if _bj0.hour == 9 and 0 <= _bj0.minute < 25:
        _wait = (_bj0.replace(hour=9, minute=25, second=6, microsecond=0) - _bj0).total_seconds()
        if 0 < _wait <= 360:
            print(f'[auction] FIX18早触发等待竞价集合 {int(_wait)}s')
            time.sleep(_wait)
    # —— 持仓竞价诊断（三分法，先出；数据超时也保留持仓卡，不推空卡）——
    own = []
    for h in HOLDINGS:
        try:
            q = _qt(h['code'])
            if not q:
                continue
            op = None
            if q.get('open') and q['prev']:
                op = (q['open'] / q['prev'] - 1) * 100
            vq_ratio = None
            try:
                arr = get_klines(h['code'], 2)
                if len(arr) >= 2 and float(arr[-2][5]) > 0 and q.get('vol'):
                    vq_ratio = (q['vol'] * 100) / float(arr[-2][5]) * 100
            except Exception:
                pass
            lb_v = q.get('lb')
            lb_txt = f'{lb_v:.1f}' if (lb_v or 0) else '未取得'
            act, why = three_way(op, lb_v or 0, vq_ratio)
            op_txt = f'{op:+.1f}%' if op is not None else '未就绪'
            op_col = _c(op) if op is not None else GREY
            _, ptag = _pos_risk(h['code'], q['price'])
            own.append(f"""<div style="background:#1f2635;border-left:3px solid {TEAL};border-radius:8px;padding:9px 11px;margin:6px 0;">
<b style="color:#fff;">🐉 {h['name']}</b> <span style="color:{op_col};font-weight:800;float:right;">开{op_txt}</span>
<div style="color:{GREY};font-size:12px;">量比{lb_txt}｜{act}{f'｜位置 {ptag}' if ptag else ''}<br>{why}</div></div>""")
        except Exception:
            continue
    own_block = (''.join(own) if own else '<div style="color:' + GREY + ';font-size:13px;">持仓行情未取得（腾讯快照失败），稍后看盘中解读</div>')
    own_section = (f'<div style="margin-top:8px;font-size:14px;font-weight:800;color:#ff922b;">🛡 持仓竞价诊断</div>{own_block}')
    # —— 数据拉取（09:26:30 硬截止，预留选股+LLM+推送时间，保证 09:27 前强制出卡；https/http 双通道）——
    bj = _bj_now()
    deadline = bj.replace(hour=9, minute=26, second=30, microsecond=0)
    _alt_used = False
    _alt_note = ''
    rows_all = None
    for attempt in range(6):
        try:
            rows_all = _clist_gainers()
            if rows_all:
                break
        except Exception as e:
            print(f'[auction] 第{attempt+1}次拉竞价数据失败: {e}')
        if _bj_now() >= deadline:
            print('[auction] 09:26:30 已过且数据未就绪，尝试当日盘面替代源（非竞价时段强制出小白速判卡）')
            # 非竞价时段（收盘后/盘中手动触发）：东财竞价快照不可用 → 用当日盘面数据强制出完整卡
            rows_all = _clist_gainers_alt()
            _alt_used = bool(rows_all)
            if _alt_used:
                _alt_note = ('<div style="color:#e6a23c;font-size:12px;margin-top:6px;">📌 非竞价时段：以下为当日盘面数据（涨幅榜）生成，非实时竞价快照，仅供参考</div>')
                break
            return _wrap(own_section + '<div style="color:#e2e8f0;font-size:13px;margin-top:8px;">⚠️ 全市场竞价数据未按时就绪且当日盘面替代源未取得，本次不筛选股票；持仓诊断照常。下一时段：10:00 盘中解读。</div>',
                         '🔔', title, show_reson=False)
        time.sleep(20)
    if not rows_all:
        # 6 次重试都失败且未过截止（竞价为 09:25 前窗口）→ 也尝试替代源兜底
        rows_all = _clist_gainers_alt()
        _alt_used = bool(rows_all)
        if _alt_used:
            _alt_note = ('<div style="color:#e6a23c;font-size:12px;margin-top:6px;">📌 竞价快照未就绪：以下为当日盘面数据（涨幅榜）生成，非实时竞价快照，仅供参考</div>')
        else:
            return _wrap(own_section + '<div style="color:#e2e8f0;font-size:13px;margin-top:8px;">⚠️ 全市场竞价数据未取得，本次不筛选股票；持仓诊断照常。下一时段：10:00 盘中解读。</div>', '🔔', title, show_reson=False)
    # —— 全市场涨幅榜 → 硬过滤 → 双重打分 → TOP8 ——
    d = get_pools()
    # 行业补强：get_pools 已把涨停池股票行业写入 _IND_CACHE，替代源(新浪)无行业字段的用缓存补
    for _s in rows_all:
        if not _s.get('industry') or _s['industry'] in ('', '其他'):
            _ic = _IND_CACHE.get(_s.get('code') or '')
            if _ic:
                _s['industry'] = _ic
    zt_lbc = {}
    for sec, sts in d['sectors'].items():
        for st in sts:
            zt_lbc[st.get('c')] = int(st.get('lbc') or 0)
    cands = _auction_filter(rows_all, zt_lbc)
    heat, cnt = _theme_heat(cands)
    # 共振升级-弱共振剔除：同题材候选<2家 且 题材热度<50 的「独涨+冷题材」剔除（早盘口径）
    cands = [s for s in cands
             if not (cnt.get(_sec_clean(s['industry']) or '其他', 0) < 2
                     and heat.get(_sec_clean(s['industry']) or '其他', 0) < 50)]
    heat, cnt = _theme_heat(cands)
    mem = load_memory()
    _calc_resonance(cands, heat, cnt, mem, is_tail=False)
    _score_dead = _bj_now().replace(hour=9, minute=25, second=50, microsecond=0)
    for i, s in enumerate(cands):
        if _bj_now() >= _score_dead and i >= AUCTION_TOP_N:
            print(f'[auction] 打分截止 {_bj_now()}，已算 {i} 只，截断保证 09:27 前推送')
            break
        s['score'] = _auction_score_v3(s, heat, cnt, mem)
    # 兜底：被截断未打分的候选补 0 分，避免后续 sort 访问缺失键抛 KeyError('score')
    for s in cands:
        s.setdefault('score', 0)
    cands.sort(key=lambda x: -x['score'])
    tops = cands[:AUCTION_TOP_N]
    # —— 并发：选股深挖 + 实盘确认深挖并行，压缩 LLM 串行耗时，保证 09:27 前推送 ——
    _cinfos = []
    for s in tops[:5]:
        sym2 = ('sh' if s['code'].startswith('6') else 'sz') + s['code']
        q2 = _qt(sym2)
        if not q2 or not q2['prev'] or not q2['open']:
            continue
        op2 = (q2['open'] / q2['prev'] - 1) * 100
        lb2 = float(q2.get('lb', 0))
        gem2 = s.get('board') == 'gem'
        lo2, hi2 = (2, 7) if not gem2 else (4, 14)
        lb_min2 = 2.0 if not gem2 else 1.5
        ok2 = lo2 <= op2 <= hi2 and lb2 >= lb_min2
        why2 = ''
        if not ok2:
            why2 = (f'量比{lb2:.1f}<{lb_min2}，资金竞价没进场，撑不起高开' if lb2 < lb_min2
                    else f'高开{op2:+.1f}%超过{hi2}%，竞价透支、开盘容易被砸' if op2 > hi2
                    else f'高开{op2:+.1f}%不足{lo2}%，没溢价不值得做')
        _cinfos.append({'name': s['name'], 'code': s['code'], 'op': op2, 'lb': lb2, 'sec': s['industry'], 'ok': ok2, 'why': why2})
    _ex = ThreadPoolExecutor(max_workers=2)
    # 8项强制修复：大盘上下文（涨停/炸板/情绪/指数）+ 涨停板块题材 → 喂给 LLM，禁止规则性回答
    try:
        _idx = get_indices()
        _mscore, _mlabel, _ = market_score(_idx, d)
    except Exception:
        _mscore, _mlabel = 50, '—'
    _lu = int(d.get('lu') or 0)
    _zb = int(d.get('zb') or 0)
    _zbr = (_zb / (_lu + _zb) * 100) if (_lu + _zb) else 0.0
    _zt_list = []
    for _sec_n, _sec_sts in (d.get('sectors') or {}).items():
        if len(_sec_sts) >= 2:
            _zt_list.append((_sec_n, len(_sec_sts)))
    _zt_list.sort(key=lambda kv: -kv[1])
    _zt_top = _zt_list[:6]
    _mkt_ctx = (f'大盘：涨停{_lu}家/炸板{_zb}家({_zbr:.0f}%) 情绪分{int(_mscore)}({_mlabel}) '
                f'最强板块{(_zt_top[0][0] if _zt_top else "—")}')
    _ds_fut = _ex.submit(_auction_ds, tops, heat, _zt_top, _mkt_ctx, _mscore, _lu, _zb)
    _cf_fut = _ex.submit(_confirm_ds, _cinfos, _mkt_ctx)
    try:
        _auction_pool_record(tops)
    except Exception:
        pass
    # —— LLM 时间门双轨：竞价窗口 09:25-09:27 保推送(短预算)；非竞价/尾盘给足 LLM 时间(禁规则回退) ——
    _now = _bj_now()
    _in_auction_win = (_now.hour == 9 and _now.minute >= 25)
    _llm_budget = (max(5, int((_bj_now().replace(hour=9, minute=26, second=50, microsecond=0) - _bj_now()).total_seconds()))
                   if _in_auction_win else 90)
    try:
        _ds_res = _ds_fut.result(timeout=_llm_budget)
        if not isinstance(_ds_res, dict):
            _ds_res = {}
        if not _ds_res.get('per'):
            print('[auction] 深挖空结果，渲染数据事实行')
    except Exception:
        _ds_res = {}
        print(f'[auction] 深挖超时({_llm_budget}s)，渲染数据事实行(非规则模板)')
    ds_map = _ds_res.get('per') or {}
    ds_overall = _ds_res.get('overall') or ''
    reson_reason = _ds_res.get('reson_reason') or ''
    cap_advice = _ds_res.get('cap_advice') or ''
    wind_strong = _ds_res.get('wind_strong') or ''
    wind_weak = _ds_res.get('wind_weak') or ''
    emotion = _emotion_from_pools(d)
    # （用户指令：已删除「🤖 竞价深挖总结」ds_block 与「🧭 今日整体」overall 两段；卡面改为模板型速判结构）
    # —— 因子引擎（第3步）：情绪分是市场级指标，全票相同，算一次复用 ——
    _jq_res = None
    if _FACTOR_OK:
        try:
            _jq_res = _fe.score_emotion(lu=_lu, zb=_zb,
                                        max_lbc=(d or {}).get('max_lbc'),
                                        yest_premium_pct=None)
        except Exception as _je:
            print(f'[factor-auction] 情绪分异常 {str(_je)[:60]}')
    rows = ''
    for i, s in enumerate(tops, 1):
        buy_low = round(max(0.0, s['price'] * 0.995), 2)
        buy_high = round(min(10.0, s['price'] * 1.01), 2)
        stop = round(buy_low * 0.97, 2)
        brk_txt = '站上昨收' if s['price'] > (s.get('prev') or 0) else '未站上昨收'
        _deep = (ds_map or {}).get(s['name'])
        if _deep and _deep.get('logic'):
            _opcol = {'别追': RED, '轻仓试': TEAL, '看': GOLD, '观望': GREY, '不碰': RED}.get(_deep.get('op', ''), GOLD)
            _deep_html = (f"""<div style="color:#a78bfa;font-size:12px;margin-top:3px;">🔍 暗线：{_deep.get('dark','')}（{_deep.get('reason','')}）</div>
<div style="color:#a78bfa;font-size:12px;margin-top:2px;">🧠 题材深挖：{_deep.get('logic','')}</div>
<div style="color:#e9ecef;font-size:12px;margin-top:2px;">👉 大白话：{_deep.get('why','')}</div>
<div style="color:#ced4da;font-size:12px;margin-top:2px;">🎯 建议：<b style="color:{_opcol};">{_deep.get('op','')}</b> ｜ 买点：{_deep.get('buy','')} ｜ 止损：{_deep.get('stop','')} ｜ 放弃：{_deep.get('drop','')}</div>""")
        else:
            # LLM 未返回时给一句盘口判断：不暴露模型状态、不落规则模板句
            _deep_html = (f"""<div style="color:#ced4da;font-size:12px;margin-top:3px;">📊 竞价：高开{s['pct']:+.1f}%、量比{s['lb']:.1f}、{brk_txt}——{_auction_fact_read(s)}</div>""")
        _fl_line = ''
        if _FACTOR_OK and _jq_res is not None:
            _fres = _factor_for_auction(s, heat, cnt, _jq_res)
            if _fres:
                s['_factor'] = _fres  # 供 signal_log.csv 落库（不改变卡片渲染）
                _fcol = '#ff6b6b' if _fres.get('vetoed') else '#8ce99a'
                _fwt = '700' if _fres.get('vetoed') else '400'
                _fl_line = (f'<div style="color:{_fcol};font-size:12px;margin-top:4px;font-weight:{_fwt};">'
                            f'🔬 因子：{_fres["line"]}</div>')
        rows += f"""<div style="background:#1f2635;border-left:3px solid {GOLD if s['score'] >= 70 else TEAL};border-radius:8px;padding:9px 11px;margin:6px 0;">
<div style="font-size:14px;font-weight:700;color:#fff;">{i}. {s['name']} <span style="color:{GREY};font-size:12px;">{s['code']}</span> <span style="color:{GOLD};font-weight:800;float:right;">{s['score']:.0f}分</span></div>
<div style="color:{GREY};font-size:12px;">竞价高开 <b style="color:{_c(s['pct'])}">{s['pct']:+.2f}%</b> ｜ 量比 {s['lb']:.1f} ｜ 竞价量比(归一) {s.get('_vr', 0):.2f} ｜ 题材：{s['industry']}{f' ｜ <b style="color:{RED if s.get('_revise',0)<0 else TEAL}">{s.get('_rtag','')}{s.get('_revise',0):+.0f}</b>' if s.get('_rtag') else ''}</div>
{_deep_html}{_fl_line}</div>"""
    try:
        _sig_rows = []
        for _s2 in tops:
            _f2 = _s2.get('_factor')
            if not _f2:
                continue
            _sig_rows.append({'code': _s2.get('code'), 'name': _s2.get('name'),
                              'price': _s2.get('price'), 'jq': _f2.get('jq'),
                              'lj': _f2.get('lj'), 'zj': _f2.get('zj'),
                              'tc': _f2.get('tc'), 'dl': _f2.get('dl'),
                              'total': _f2.get('total'), 'combined': _f2.get('combined'),
                              'vetoed': _f2.get('vetoed')})
        _factor_signal_write('auction', _sig_rows)
    except Exception as _sig_e:
        print(f'[sigcsv] auction 接入异常 {_sig_e}')
    # —— Top3 重点点评（v3）——
    top3_txt = ''
    if tops:
        def _quick_act(s_):
            bad = (s_.get('_rtag') or '') in ('暴力反抽', '无量反弹')
            if bad or s_['score'] < 60:
                return '降权/不追', RED
            if s_['score'] >= 75:
                return '强', TEAL
            return '中', GOLD
        _t3 = []
        for i, s_ in enumerate(tops[:3], 1):
            _a, _col = _quick_act(s_)
            _d3 = (ds_map or {}).get(s_['name']) or {}
            _dark_txt = (f'｜🔍暗线:{_d3.get("dark","")}' if _d3.get('dark') else '')
            _t3.append(f'<b style="color:{_col}">{i}.{s_["name"]} {_a}</b>{_dark_txt}')
        top3_txt = (f'<div style="margin-top:10px;padding:9px 11px;background:#1c2830;border-left:4px solid #a78bfa;'
                    f'border-radius:8px;font-size:13px;color:#e9ecef;"><b>🎯 Top3 速判（小白版·含暗线）：</b>'
                    + ('<br>'.join(_t3) if _t3 else '—')
                    + '</div>')
    try:
        _pool_prev = _auction_pool_stats()
    except Exception:
        _pool_prev = ''
    pick = f"""{top3_txt}<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">🎯 今日可关注 TOP{AUCTION_TOP_N}（综合评分排序）</div>
{rows or '<div style="color:' + GREY + ';font-size:13px;">今日无符合硬过滤条件的竞价票（涨幅榜未取得或全被过滤）</div>'}{_pool_prev}"""
    # —— 行业/题材风向（8项修复⑤：补涨停板块题材数据 + 最强/最弱暗线原因）——
    hot = sorted(heat.items(), key=lambda kv: -kv[1])[:3]
    hot_txt = '、'.join(k for k, _ in hot) or '暂无'
    weak_lst = sorted(heat.items(), key=lambda kv: kv[1])
    weak_txt = (weak_lst[0][0] if weak_lst else '暂无')
    # 涨停板块题材补强：heat 只有行业维度，叠加真实涨停板块（竞价涨幅榜+涨停池双口径）
    if _zt_top:
        _zt_hot = '、'.join(f'{n}({c}家)' for n, c in _zt_top[:3])
    else:
        _zt_hot = ''
    # 共振强度已于 2026-11-07 从卡片移除：共振只作内部因子参与打分，不对用户展示
    _rs_txt = ''
    _ws = (f'<div style="font-size:13px;color:#e9ecef;">{wind_strong}</div>' if wind_strong else '')
    _ww = (f'<div style="font-size:13px;color:#e9ecef;">{wind_weak}</div>' if wind_weak else '')
    wind = ((f'<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">🌬️ 行业/题材风向</div>{_ws}{_ww}')
            if (_ws or _ww) else '')
    # —— 竞价实盘确认（8项修复⑦：结合大盘实时总结；AI逐票深挖；无AI时只给数据事实行）——
    _confirm_block = ''
    try:
        _crows = []
        _dmap2 = {}
        try:
            _llm_left2 = (max(5, int((_bj_now().replace(hour=9, minute=26, second=55, microsecond=0) - _bj_now()).total_seconds()))
                          if _in_auction_win else 90)
            _dmap2 = _cf_fut.result(timeout=_llm_left2)
            if not _dmap2:
                print('[auction] 确认深挖空结果，渲染数据事实行')
        except Exception:
            _dmap2 = {}
            print(f'[auction] 确认深挖超时({_llm_left2}s)，渲染数据事实行(非规则模板)')
        _mkt_sum = (_dmap2.get('market') or '') if isinstance(_dmap2, dict) else ''
        _per2 = (_dmap2.get('per') or {}) if isinstance(_dmap2, dict) else {}
        for _cf in _cinfos:
            _nm2 = _cf['name']
            _rz2 = _per2.get(_nm2) or ''
            if _rz2:
                _crows.append(f'<div style="margin:4px 0;font-size:13px;background:#1c2830;border-left:3px solid {TEAL};border-radius:8px;padding:6px 10px;">🧠 <b style="color:#fff;">{_nm2}({_cf["code"]})</b> 高开{_cf["op"]:+.1f}% 量比{_cf["lb"]:.1f}<br>{_rz2}</div>')
            else:
                _crows.append(f'<div style="margin:4px 0;font-size:13px;background:#1f2635;border-left:3px solid {GREY};border-radius:8px;padding:6px 10px;">📊 <b style="color:#fff;">{_nm2}({_cf["code"]})</b> 高开{_cf["op"]:+.1f}% 量比{_cf["lb"]:.1f} — AI 未返回确认深挖，仅展示数据</div>')
        if _mkt_sum:
            _crows.insert(0, f'<div style="margin:4px 0;font-size:13px;background:#1a2029;border-left:3px solid {GOLD};border-radius:8px;padding:6px 10px;">🌍 大盘实时：{_mkt_sum}</div>')
        if _crows:
            _confirm_block = ('<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">🔔 竞价实盘确认</div>'
                              + ''.join(_crows))
    except Exception as e:
        print('[auction] 确认段失败:', e)
        _confirm_block = ''
    # 8项修复⑥：当前档位建议（LLM 按盘面），保留数据行 pos_cap_line
    _cap_advice_row = (f'<div style="margin-top:8px;padding:7px 10px;background:#1c2230;border-left:4px solid {GOLD};'
                       f'border-radius:8px;font-size:13px;color:#e9ecef;">📊 当前档位建议（按盘面）：{cap_advice}</div>') if cap_advice else ''
    # （用户指令：已删除「🎚 共振原因」_reson_reason_row 段）
    sec_sent = _sentiment_line_for_auction()
    sec_sent_html = ('<div style="background:#1f2635;border-radius:8px;padding:8px 10px;'
                     'margin-bottom:8px;font-size:14px;font-weight:700;color:#ffd43b;">%s</div>' % sec_sent) if sec_sent else ''
    # 工单10：隔夜外盘定量参考行（只作开盘情绪偏移，不进 aggregator、不单独成 engine）
    _ov_line = _overnight_line_for_auction()
    sec_ov_html = ('<div style="background:#1f2635;border-radius:8px;padding:8px 10px;'
                   'margin-bottom:8px;font-size:13px;color:#91a7ff;">%s</div>' % _ov_line) if _ov_line else ''
    inner = (sec_sent_html + sec_ov_html + f'<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">🔔 持仓竞价诊断（先看自己的）</div>'
             + (''.join(own) or '<div style="color:' + GREY + ';font-size:13px;">无持仓</div>')
             + pick + wind + _cap_advice_row + pos_cap_line(emotion, None) + _confirm_block + _alt_note)
    _ex.shutdown(wait=False)
    return _wrap(inner, '🔔', title, show_reson=False)


# ============ 尾盘竞价筛选（独立于早盘竞价，14:55-14:58） ============
def _tail_gainers(max_pages=15, cover_pct=2.5):
    """尾盘数据源：新浪 hs_a 涨幅排行动态翻页（页内粗滤 0.5~9%，缓冲覆盖 v2 硬过滤 2.5~8.5%），
    直到本页最低涨幅 < cover_pct 或到 max_pages。
    返回粗滤后的当日盘面行（code/name/price/pct/vol/amount/turn/lb/high/low/prev/industry/list_date），
    lb 初 0 由 _tail_qt_fill 批量补。区别于早盘 _clist_gainers_alt：覆盖 2.5~8.5% 强票区间而非仅头部大涨。"""
    rows = []
    try:
        for pn in range(1, max_pages + 1):
            url = ('https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/'
                   'Market_Center.getHQNodeData?page=%d&num=100&sort=changepercent&asc=0&node=hs_a'
                   '&symbol=&_s_r_a=page') % pn
            txt, ok = _getm(url, 'tail_gainers_p%d' % pn)
            if not ok or not txt:
                break
            d = json.loads(txt)
            if not d:
                break
            page_min = 100.0
            page_new = 0
            for x in d:
                code = str(x.get('code') or '').strip()
                name = str(x.get('name') or '').strip()
                if not code or not name:
                    continue
                if code.startswith(('688', '689', '8', '4', '920', '92', 'bj')):
                    continue
                try:
                    pct = float(x.get('changepercent') or 0)
                    page_min = min(page_min, pct)
                    if not (0.5 <= pct <= 9.0):
                        continue
                except Exception:
                    continue
                if 'ST' in name.upper() or '退' in name:
                    continue
                rows.append({
                    'code': code,
                    'name': name,
                    'price': float(x.get('trade') or 0),
                    'pct': pct,
                    'vol': round(float(x.get('volume') or 0) / 100.0),
                    'amount': float(x.get('amount') or 0),
                    'turn': float(x.get('turnoverratio') or 0),
                    'lb': 0.0,
                    'high': float(x.get('high') or 0),
                    'low': float(x.get('low') or 0),
                    'prev': float(x.get('settlement') or 0),
                    'list_date': '',
                    'industry': _IND_CACHE.get(code, '其他'),
                })
                page_new += 1
            print('[tail] page%d: n=%d 粗滤=%d 页min=%.2f' % (pn, len(d), page_new, page_min))
            if page_min < cover_pct:
                break
    except Exception as e:
        print('[tail] 尾盘涨幅榜拉取失败:', e)
    return rows


def _tail_qt_fill(rows):
    """腾讯批量补量比(f43)/换手(f38)/总市值(f44, 亿)。f[2] 为完整 6 位 code，勿切前缀。"""
    try:
        cs = [('sh' if r['code'].startswith('6') else 'sz') + r['code'] for r in rows]
        for i in range(0, len(cs), 60):
            txt, ok = _getm('http://qt.gtimg.cn/q=' + ','.join(cs[i:i + 60]), 'tail_qt', encoding='gbk')
            if not ok:
                continue
            for line in txt.strip().split(';'):
                if '~' not in line:
                    continue
                f = line.split('~')
                try:
                    code = f[2]
                    for r in rows:
                        if r['code'] == code:
                            r['lb'] = float(f[43] or 0)
                            r['turn'] = float(f[38] or 0)
                            r['mv'] = float(f[44] or 0)
                            break
                except Exception:
                    pass
    except Exception:
        pass
    return rows


def _tail_filter(rows, heat=None, zt_names=None):
    """尾盘硬过滤（v4「买在涨停前」版，用户核心诉求=不要接飞刀）：
    仅沪深主板+创业板；剔除ST/退市、次新(<365天)；当日涨幅 2.5~8.5%（还在路上、没封板）；
    量比>=2.0；换手>=2.5%；量能真实性二选一：量比>=2.5 或(量比>=2.0 且换手>=4%)。
    **四道位置硬闸（v4 新增，全部靠日K自证，不依赖外部历史接口）**：
      ①近年6个交易日有过涨停(主板>=9.4%/创业板>=19.4%) → 剔除（连板、昨日涨停一律不推）；
      ②距60日最高收盘回撤 <10% → 剔除（贴前高/创新高不追，这是「接飞刀」的根源）；
      ③近5日涨幅 >12% → 剔除（题材热度>=70 且属当日最强主线放宽至 15%）；
      ④K线拉取失败 → 剔除（v3 的「失败放行」会让近5日/位置约束整体失效，已废除）。
    不设市值硬限制、不设 MA20 硬门槛（趋势由打分层的 MA5/当日均价代理）。
    过滤阶段缓存 _ma5_up/_chg5/_pos60/_zt_n 供 _tail_score_v2 复用。"""
    out = []
    pending = []   # 通过基础硬过滤、待并发拉K线做趋势判定的候选
    try:
        from datetime import date
        yy, mm, dd = map(int, _bj_now().strftime('%Y-%m-%d').split('-'))
        today = date(yy, mm, dd)
    except Exception:
        today = None
    for s in rows:
        code, name = s['code'], s['name']
        if not code or not name:
            continue
        if code.startswith(('688', '689', '8', '4', '920', '92', 'bj')):
            continue
        if code.startswith('6'):
            s['board'] = 'main'
        elif code.startswith(('000', '001', '002', '003')):
            s['board'] = 'main'
        elif code.startswith(('300', '301')):
            s['board'] = 'gem'
        else:
            continue
        if 'ST' in name.upper() or '退' in name:
            continue
        if s['list_date'] and len(s['list_date']) == 8 and today:
            try:
                ld = date(int(s['list_date'][:4]), int(s['list_date'][4:6]), int(s['list_date'][6:8]))
                if (today - ld).days < 365:
                    continue
            except Exception:
                pass
        try:
            pct = float(s['pct'] or 0)
            if not (2.5 <= pct <= 8.5):
                continue
            lb = float(s['lb'] or 0)
            if lb < 2.0:
                continue
            turn = float(s['turn'] or 0)
            if turn < 2.5:
                continue
        except Exception:
            continue
        # 量能真实性二选一：量比>=2.5 或(量比>=2.0 且换手>=4%)（在量比>=2.0 硬条件之上）
        try:
            if not (lb >= 2.5 or (lb >= 2.0 and turn >= 4.0)):
                continue
        except Exception:
            continue
        # 趋势代理（K线段）：先收集，后并发单次拉 25 根一次算完 MA5/近5日，再统一判定
        # （避免数百候选串行 2 次 HTTP 导致云端超时；语义不变：近5日超限才剔除，K线失败放行；MA20 已按用户指令取消）
        s['_kline_ok'] = False
        s['_ma5_up'] = False
        s['_chg5'] = None
        pending.append(s)
    # —— 并发拉 K 线（每只 1 次 25 根请求，MA5 用后5/前5根、近5日用 arr[-6] 基准）——
    def _kline_fetch(s):
        try:
            sym = ('sh' if s['code'].startswith('6') else 'sz') + s['code']
            arr = get_klines(sym, 70)
            if len(arr) >= 6:
                s['_kline_ok'] = True
                c = [float(r[2]) for r in arr]
                ma5_now = sum(c[-5:]) / 5.0
                ma5_prev = sum(c[-6:-1]) / 5.0
                s['_ma5_up'] = ma5_now > ma5_prev
                if c[-6] > 0:
                    s['_chg5'] = round((s['price'] / c[-6] - 1) * 100, 2)
                # 距60日最高收盘的回撤（负数=低于前高；用收盘价，避免上影噪声）
                hi60 = max(c[-60:]) if len(c) >= 20 else max(c)
                s['_pos60'] = round((s['price'] / hi60 - 1) * 100, 2) if hi60 > 0 else None
                # 近5个交易日（不含今日）涨停次数：主板>=9.4%、创业板>=19.4%
                _lim = 19.4 if s.get('board') == 'gem' else 9.4
                _zn = 0
                for _i in range(max(1, len(c) - 6), len(c) - 1):
                    _pv = c[_i - 1]
                    if _pv > 0 and (c[_i] / _pv - 1) * 100 >= _lim:
                        _zn += 1
                s['_zt_n'] = _zn
        except Exception:
            pass
        return s
    if pending:
        try:
            with ThreadPoolExecutor(max_workers=16) as _ex:
                list(_ex.map(_kline_fetch, pending))
        except Exception:
            pass
    _kfail = 0
    for s in pending:
        # ①K线失败不再放行（放行会让位置/近5日约束整体失效）
        if not s.get('_kline_ok'):
            _kfail += 1
            continue
        # ②近5个交易日涨停过 → 已经在板上，不推（连板、昨日涨停一律不推）
        if int(s.get('_zt_n') or 0) >= 1:
            continue
        # ③贴前高/创新高不追：距60日最高收盘至少留 10% 空间
        p60 = s.get('_pos60')
        if p60 is not None and p60 > -10.0:
            continue
        # ④近5日涨幅：<=12%；题材热度>=70 且属当日最强主线时放宽至 15%
        chg5 = s.get('_chg5')
        if chg5 is not None:
            limit5 = 15.0
            try:
                ind = _sec_clean(s['industry']) or '其他'
                if not ((heat or {}).get(ind, 0) >= 70 and (zt_names and ind in zt_names)):
                    limit5 = 12.0
            except Exception:
                limit5 = 12.0
            if chg5 > limit5:
                continue
        out.append(s)
    if pending and _kfail / float(len(pending)) >= 0.30:
        print('[tail] K线失败 %d/%d，位置闸可能偏严（数据源异常）' % (_kfail, len(pending)))
    print('[tail] v4过滤：进 %d / 待判 %d（剔除涨停过/贴前高/近5日超限/K线失败）'
          % (len(out), len(pending)))
    return out


def _tail_score_v2(s, heat, cnt, mem_days=None, zt_names=None):
    """尾盘 v2 综合分（无MA20/市值版）= 量价趋势因子×0.60 + 题材因子×0.20 + 共振分×0.20 − 风险扣分
    （2026-11-05 共振因子升级：原 0.75/0.25 调整，co20→co10，共振分来自 _calc_resonance）。
    量价趋势五因子：涨幅适中22 / 量比强度25 / 情绪代理(换手×量比)23 / 趋势强度(MA5向上12+当日价站上均价6)18 / 量能占比代理12；
    题材因子：热度60 + 同题材≥4家20 + 主线持续(近3日持续涨停)20；
    风险扣分：近5日>18% −4 / 题材热度<40 −5 / 当日涨幅>7.5% −3 / 跌破分时均线且量比回落 −3（日K代理）。
    注：原「趋势强度(MA20+MA5向上)」随用户指令取消 MA20 限制，改为 MA5向上 + 当日均价代理。"""
    sc = 0.0
    # —— 量价趋势五因子 ——
    try:
        pct = float(s['pct'] or 0)
        if 3.5 <= pct <= 6.5:
            sc += 22
        elif 2.5 <= pct < 3.5 or 6.5 < pct <= 8.5:
            sc += 15
        else:
            sc += 8
    except Exception:
        sc += 8
    try:
        lb = float(s['lb'] or 0)
        sc += 25 if lb >= 4.0 else (18 if lb >= 3.0 else (10 if lb >= 2.0 else 0))
    except Exception:
        pass
    try:
        turn = float(s['turn'] or 0)
        emo = turn * float(s['lb'] or 0)
        sc += 23 if emo >= 15 else (16 if emo >= 10 else (9 if emo >= 6 else 0))
    except Exception:
        pass
    # 趋势强度 18（无MA20）：MA5向上 12 + 当日价站上当日均价(VWAP) 6；K线失败半补
    if s.get('_ma5_up'):
        sc += 12
    elif s.get('_kline_ok'):
        sc += 6
    try:
        vwap = (s.get('amount') or 0) / (float(s.get('vol') or 0) * 100.0) if (s.get('vol') or 0) else 0.0
        if vwap > 0 and s['price'] >= vwap:
            sc += 6
    except Exception:
        pass
    try:
        turn = float(s['turn'] or 0)
        lb = float(s['lb'] or 0)
        if turn >= 6.0 and lb >= 3.0:
            sc += 12
        elif turn >= 4.0:
            sc += 7
        else:
            sc += 3
    except Exception:
        sc += 3
    # —— 题材因子（100，×0.20；co20 已按共振升级降为 co10）——
    ind = _sec_clean(s['industry']) or '其他'
    heat60 = min(60.0, (heat.get(ind) or 0) / 100.0 * 60.0)
    co10 = 10.0 if cnt.get(ind, 0) >= 4 else 0.0
    persist = 0.0
    if mem_days:
        for pd, pv in list(mem_days.items())[:3]:
            if ind in pv:
                persist = 20.0
                break
    theme_score = min(100.0, heat60 + co10 + persist)
    # —— 风险扣分 ——
    risk = 0.0
    try:
        if (s.get('_chg5') or 0) > 18.0:
            risk += 4.0
    except Exception:
        pass
    if (heat.get(ind) or 0) < 40:
        risk += 5.0
    try:
        if float(s['pct'] or 0) > 7.5:
            risk += 3.0
    except Exception:
        pass
    # 跌破当日均价线(成交额/成交量≈分时均线) 且 量比<3（未持续放量=回落）→ 尾盘走弱信号
    try:
        vwap = (s.get('amount') or 0) / (float(s.get('vol') or 0) * 100.0) if (s.get('vol') or 0) else 0.0
        if vwap > 0 and s['price'] < vwap and float(s['lb'] or 0) < 3.0:
            risk += 3.0
    except Exception:
        pass
    total = sc * 0.60 + theme_score * 0.20 + (s.get('_reson') or 0) * 0.20 - risk
    # 低位加分（用户诉求：买在涨停前，越低位越优先）
    try:
        _p60 = s.get('_pos60')
        if _p60 is not None:
            if _p60 <= -30.0:
                total += 6.0
            elif _p60 <= -18.0:
                total += 3.0
    except Exception:
        pass
    return round(total, 1)


def _tail_ds(tops, heat, zt_themes=None, mkt_ctx=None, mscore=None, lu=None, zb=None):
    """尾盘竞价 LLM 深挖：**分批调用（每批最多5只）**，避免一次要求10只×9字段被 max_tokens 截断。
    每只输出 dark/reason/logic/why/op/buy/stop/drop/next；第一批额外给 cap_advice/wind_strong/wind_weak。
    任一批成功就出该批暗线；全部失败返回 {}（调用方渲染盘口事实行，绝不编假暗线）。"""
    if not tops:
        return {}
    _zt = (zt_themes or [])[:8]
    _zt_txt = '、'.join('%s(涨停%d家)' % (n, int(c)) for n, c in _zt) or '暂无'
    _mkt = mkt_ctx or ''
    _fmt = ('你是A股超短线交易员，现在是尾盘 14:55 竞价筛选窗口，收盘前最后一轮选股。'
            '对下面这几只尾盘强势票逐只做多因素深挖（禁止单条件结论）：\n'
            '0.【暗线业务深挖·每只必做】先用一句话说清公司本质（靠什么赚钱，禁「XX龙头/XX概念」标签）；'
            '再挖暗线业务——具体产品/技术/业务是什么、进展到哪个阶段、在产业链哪个环节、有没有卡位壁垒、'
            '对业绩是真实贡献还是纯故事预期；然后判断跟今日最强主线（见 hot_sectors）是【实受益】【沾边】还是【纯蹭】、弹性大不大。'
            '挖不出来如实写「未见明确暗线业务」，禁止用「相关」「涉及」「布局」「受益于」等词糊弄。\n'
            '1. 量能真实性：用涨幅/量比/换手判断尾盘放量是真突破还是偷量诱多——阶梯式放量+价格稳步抬升是真抢筹；最后3-5分钟脉冲直线拉升是假突破。\n'
            '2. 趋势是否干净：有没有明显上影线、反复炸板后回落、尾盘跳水（干净/有瑕疵/不干净）。\n'
            '3. 次日竞价预期：明天竞价大概率怎么走（高开延续/平开分歧/低开补跌），给具体观察条件（例：竞价量比≥X且高开≥Y%才继续）。\n'
            '4. 题材归属与板块共振：属于什么题材、是不是今日主线、题材内地位（龙头/中军/跟风/补涨）、同题材几只一起动还是独涨。\n'
            '5. 为什么是它：资金凭什么选它不选别人，用真实数据说。\n'
            '6. 破灭点与动作：逻辑什么时候会破，破了怎么走人；逻辑不硬就明确写「不碰」。\n'
            '7. 周期适配：判定每只最适合的参与周期（超短线1-3日/短线3-10日），buy/stop 按该周期口径给，buy 开头用【周期：XXX】标注。\n'
            '8. 禁止编新闻猜消息、禁止万能句、禁止满仓/必涨/稳了。\n'
            '9. 只输出 JSON，不要其他文字：\n'
            '{"cap_advice":"当前档位建议：结合 mkt_ctx 直接给明日仓位档位与一句话理由，至少20字",'
            '"wind_strong":"最强题材为什么最强（涨停家数/催化/资金逻辑），至少20字",'
            '"wind_weak":"最弱题材为什么最弱（为什么别碰），至少15字",'
            '"per":[{"name":"股票名称","dark":"一句话暗线（这票真正炒的是什么，禁标签糊弄，10-30字）",'
            '"reason":"为什么尾盘筛出它（主业匹配+位置+筹码+业绩+催化，至少20字）",'
            '"logic":"暗线业务深挖+题材归属+板块共振+量能真实性+趋势干净度+次日竞价预期+破灭点，连贯大白话，至少40字",'
            '"why":"大白话：一句话戳穿真假+次日该不该追，至少20字",'
            '"op":"别追/看/轻仓试/观望/不碰","buy":"具体买点条件（含次日竞价条件）",'
            '"stop":"具体止损条件","drop":"放弃条件（次日出现什么情况就不做，10-25字）",'
            '"next":"次日竞价预期与观察信号，15-30字"}]}。\n'
            'per 必须覆盖本批每一只股票；本批数量少，把每只写透，但每段按上面字数上限，不要长篇铺陈。')
    out = {'per': {}, 'overall': '', 'reson_reason': '', 'cap_advice': '', 'wind_strong': '', 'wind_weak': ''}
    # 每批 3 只：单批输出体积压在转录上限内，避免 JSON 被截断后整批丢失（失败只影响 3 只，不影响全卡）
    _batches = [tops[i:i + 3] for i in range(0, len(tops), 3)]
    for _bi, _bt in enumerate(_batches):
        if not _bt:
            continue
        payload = {
            'task': 'tail_top_deep',
            'stocks': [{'name': s['name'], 'code': s['code'], 'score': round(float(s['score']), 1),
                        'pct': s['pct'], 'lb': s.get('lb', 0), 'turn': s.get('turn', 0),
                        'mv': round(float(s.get('mv') or 0), 1), 'industry': s['industry'],
                        'ma5_up': bool(s.get('_ma5_up')),
                        'chg5': s.get('_chg5')} for s in _bt],
            'hot_sectors': sorted(heat.items(), key=lambda kv: -kv[1])[:6],
            'zt_themes': _zt_txt,
            'mkt_ctx': _mkt,
            'batch': '%d/%d' % (_bi + 1, len(_batches)),
            'format': _fmt,
        }
        t = ask_deepseek(payload, purpose='tail', system_text=_ASK_DS_SYS_AC)
        if not t:
            print('[tail] 第%d批 LLM 未返回，跳过该批（不编暗线）' % (_bi + 1))
            continue
        j = _json_loose(t)
        if not j:
            print('[tail] 第%d批 JSON 解析失败，跳过该批（不编暗线）' % (_bi + 1))
            continue
        if _bi == 0:
            out['cap_advice'] = str(j.get('cap_advice', '') or '')
            out['wind_strong'] = str(j.get('wind_strong', '') or '')
            out['wind_weak'] = str(j.get('wind_weak', '') or '')
        for it in (j.get('per') or []):
            if not isinstance(it, dict):
                continue
            nm = str(it.get('name', '')).split('（')[0].split('(')[0].strip()
            if not nm:
                continue
            out['per'][nm] = {'dark': str(it.get('dark', '') or ''),
                              'reason': str(it.get('reason', '') or ''),
                              'logic': str(it.get('logic', '') or ''),
                              'why': str(it.get('why', '') or ''),
                              'op': str(it.get('op', '') or ''),
                              'buy': str(it.get('buy', '') or ''),
                              'stop': str(it.get('stop', '') or ''),
                              'drop': str(it.get('drop', '') or ''),
                              'next': str(it.get('next', '') or '')}
    if not out['per']:
        return {}
    print('[tail] 暗线覆盖 %d/%d 只' % (len(out['per']), len(tops)))
    return out



def _cycle_ds(stocks, heat, zt_themes=None, mkt_ctx=None, mscore=None, lu=None, zb=None):
    """多周期视角研判 LLM 深挖（独立语义，purpose='cycle'）：单次调用输出
    per（每只：dark/reason/logic/why/op/buy/stop/drop）+ cap_advice。
    语义=收盘周期视角：周期适配（超短/短/中长/长线，系统已按 MA/量能/回撤/5日涨幅预判 cyc 字段）
    +暗线业务深挖（本质→暗线业务→与主线相关性→为什么买它→风险破灭点）+按周期口径买卖点/止损/仓位档。
    失败或预算耗尽返回 {}（渲染周期分组数据行兜底，不推空卡、不推假暗线）。"""
    if not stocks:
        return {}
    _zt = (zt_themes or [])[:8]
    _zt_txt = '、'.join(f'{n}(涨停{int(c)}家)' for n, c in _zt) or '暂无'
    _heat_txt = '、'.join(f'{k}(热度{v:.0f})' for k, v in sorted(heat.items(), key=lambda kv: -kv[1])[:6]) or '暂无'
    _mkt = mkt_ctx or ''
    payload = {
        'task': 'cycle_top_deep',
        'stocks': [{'name': s['name'], 'code': s['code'], 'pct': s['pct'], 'lb': s.get('lb', 0),
                    'turn': s.get('turn', 0), 'mv': round(float(s.get('mv') or 0), 1),
                    'industry': s['industry'], 'cyc': s.get('_cyc', '')} for s in stocks],
        'hot_sectors': sorted(heat.items(), key=lambda kv: -kv[1])[:6],
        'zt_themes': _zt_txt,
        'mkt_ctx': _mkt,
        'format': ('你是A股实战交易员，现在是收盘后 15:20 多周期视角研判窗口。系统已按 MA5/10/20/60+量能+距60日高点回撤+5日涨幅'
                   '预判每只票的适配周期（stocks 的 cyc 字段：超短线1-3日/短线3-10日/中长线1-6月/长线6月+）。'
                   '对以下每只强势票做多因素深挖（禁止单条件结论）：\n'
                   '0.【暗线业务深挖·每只必做】先一句话说清公司本质（靠什么赚钱，禁「XX龙头/XX概念」标签）；再挖暗线业务——具体产品/技术/业务是什么、进展到哪个阶段、在产业链哪个环节、有没有卡位壁垒、对业绩是真实贡献还是纯故事/预期；然后判断跟今日最强主线（{hot_sectors}）是【实受益】【沾边】还是【纯蹭】、弹性大不大。挖不出来如实写「未见明确暗线业务」，禁止用「相关」「涉及」「布局」「受益于」等词糊弄。\n'
                   '1. 周期适配确认：系统预判 cyc 是否合理？与量价/筹码明显不符可微调，buy/stop 必须按最终周期口径给——超短线看分时与MA5、短线看MA10/MA20回踩、中长线看MA20/MA60趋势仓、长线看多头结构与回撤位置；buy 字段开头用【周期：XXX】标注。\n'
                   '2. 为什么买它：主业匹配/位置/筹码/业绩/催化，用真实数据说清买入逻辑（不能只说周期标签）。\n'
                   '3. 风险与破灭点：逻辑什么时候会破（放量滞涨/跌破MA20/业绩证伪/题材退潮/主力出货），破了怎么走人；逻辑不硬就明确写「不碰」。\n'
                   '4. 仓位档：结合档位给该票建议仓位（轻仓1-2成/中仓2-3成/趋势仓3-5成/底仓），写进 op 与 buy 语境。\n'
                   '5. 市值与风格硬约束：流通市值超800亿、高位连板(>=3板)、今日涨停的票一律「不碰/别追」。\n'
                   '6. 禁止编新闻猜消息、禁止设问句、禁止万能句（「回踩分时均线可轻仓试」等）及变体、禁止满仓/必涨/稳了。\n'
                   '7. 只输出 JSON，不要其他文字：\n'
                   '"cap_advice":"当前档位建议：结合 mkt_ctx（涨停家数/炸板/情绪分/指数涨跌）直接给明日仓位档位建议与一句话理由，禁止万能句，至少20字",'
                   '"per":[{"name":"股票名称","dark":"一句话暗线（这条票真正炒的是什么，禁标签糊弄，10-30字）","reason":"选中原因：为什么筛出它（主业匹配+位置+筹码+业绩+催化，真实数据，至少20字）","logic":"暗线业务深挖+周期适配+买入逻辑：公司本质→暗线业务(产品/技术/阶段/业绩贡献)→与主线相关性(实受益/沾边/纯蹭+弹性)→为什么买它→风险破灭点，多因素连贯大白话，至少60字，禁止单条件、禁止相关/涉及/布局/受益于糊弄","why":"大白话：一句话戳穿真假+该不该买，至少20字，禁止万能句","op":"别追/看/轻仓试/观望/不碰","buy":"具体买点条件（按周期口径：超短看分时MA5、短线看MA10/20回踩、中长看MA20/60）","stop":"具体止损条件","drop":"放弃条件：出现什么情况就不做（跌破MA/放量滞涨/题材退潮等具体条件，10-25字）"}]}，'
                   'per 必须覆盖我给的每只股票。'),
    }
    t = ask_deepseek(payload, purpose='cycle', system_text=_ASK_DS_SYS_AC)
    if not t:
        return {}
    out = {}
    try:
        j = json.loads(t[t.find('{'):t.rfind('}') + 1])
        if isinstance(j, dict):
            out['cap_advice'] = str(j.get('cap_advice', '') or '')
            per = {}
            for it in (j.get('per') or []):
                nm = str(it.get('name', '')).split('（')[0].split('(')[0].strip()
                if nm:
                    per[nm] = {'dark': str(it.get('dark', '') or ''),
                               'reason': str(it.get('reason', '') or ''),
                               'logic': str(it.get('logic', '') or ''),
                               'why': str(it.get('why', '') or ''),
                               'op': str(it.get('op', '') or ''),
                               'buy': str(it.get('buy', '') or ''),
                               'stop': str(it.get('stop', '') or ''),
                               'drop': str(it.get('drop', '') or '')}
            out['per'] = per
    except Exception:
        return {}
    return out


def _tail_fact_read(s):
    """模型未返回时的唯一一句话判断：只用代码实算的盘口数据，不编暗线、不自问自答。
    有承接形态数据（前5只）就按形态说，没有就按涨幅/量比/换手/盘子说。"""
    try:
        pct = float(s.get('pct') or 0)
        lb = float(s.get('lb') or 0)
        turn = float(s.get('turn') or 0)
        mv = float(s.get('mv') or 0)
    except Exception:
        return '数据不全，这票今天不参与'
    f = s.get('_form') or {}
    tag = (f.get('tag') if isinstance(f, dict) else '') or ''
    _lg = f.get('last_gap') if isinstance(f, dict) else None
    _og = f.get('gap') if isinstance(f, dict) else None
    if tag == '低开抢筹':
        _base = abs(float(_og or 0))
        _up = float(_lg or 0)
        if _up >= 6:
            return '低开%.1f个点后硬抢到比开盘还高%.1f个点，尾盘还在往里推，明天别高开太多就还有空间' % (_base, _up)
        if _up >= 2:
            if _base >= 5:
                return '低开%.1f个点这么大的坑还填回%.1f个点，说明有资金真在托，但坑太深明天要二次确认' % (_base, _up)
            return '低开%.1f个点后被拉回开盘上方%.1f个点，抢筹只算中规中矩，明天得看竞价把量接住' % (_base, _up)
        if _base >= 4:
            return '低开%.1f个点只收回1个点上下，坑填得不干脆，这种低位反抽多数是一日游' % _base
        return '低开%.1f个点后没走出坑，只勉强爬回开盘价旁边，抢筹偏弱，明天低开就别跟' % _base
    if tag == '真抢筹':
        return '开盘就往上抢、盘中没给回撤，尾盘还在走强，明天看竞价能不能再接住一波量'
    if tag == '假高开·竞价骗炮':
        return '高开被砸下去又拉回来，这波是做价不是真抢筹，明天高开别接'
    if tag == '高开走弱':
        return '高开一路走弱、靠尾盘才拉回涨幅榜，量能没跟上就是骗量，明天平开都悬'
    if pct >= 7:
        return '涨幅已经把明天的空间提前吃掉，尾盘再追等于把溢价白送人'
    if lb >= 15 and pct < 6:
        return '量能远远顶在涨幅前头、价格还没跟上，说明有资金在试盘，明天看能不能接力'
    if turn >= 15:
        return '换手这么大是筹码在换人，接力盘接不接得住，明天竞价见分晓'
    if 0 < mv < 60:
        return '盘子小容易被推也容易被砸，明天只看竞价量能不猜方向'
    if lb >= 10 and turn >= 6:
        return '量和换手都堆到这个位置，筹码在积极换手，明天竞价只要不低开太多就还能看'
    if lb >= 10:
        return '量比拉到这个高度、涨幅却还在合格区，属于有量没透，明天看能不能顺势再推一波'
    if turn >= 8:
        return '换手已经不低，浮筹洗过一轮，明天能不能起全看竞价那口气'
    if mv >= 120:
        return '盘子偏大，拉起来慢摔下来也慢，明天得看板块能不能给出合力'
    return '量价都在合格区间、没有明显透支，明早竞价不高开就跟不上'


def build_tail(title='尾盘竞价筛选'):
    """尾盘竞价筛选（14:55-14:58 独立卡，不复用早盘 build_auction 语义）：
    当日实时盘面（新浪 hs_a 涨幅榜+腾讯补量比/换手/总市值）→ 尾盘 v2 硬过滤（涨幅2.5-8.5/量比≥2/换手≥2.5/MA20/近5日约束/量能真实性）→
    尾盘 v2 打分（量价趋势×0.75+题材×0.25−风险）→ TOP10，LLM 尾盘深挖（暗线+量能真实性+趋势干净度+次日竞价预期）。
    失败仅兜底数据事实行，无规则模板句。"""
    # 数据：尾盘独立拉取当日涨幅榜（覆盖 2.5~8.5% 强票区间，动态翻页）
    rows_all = None
    try:
        rows_all = _tail_gainers()
    except Exception as e:
        print('[tail] 拉取当日盘面失败:', e)
    if not rows_all:
        return _wrap('<div style="color:#e2e8f0;font-size:13px;">⚠️ 尾盘盘面数据未取得，本次不筛选；下一时段：收盘复盘。</div>', '🔔', title, show_reson=False)
    rows_all = _tail_qt_fill(rows_all)
    # 行业补强：先查内存/文件缓存；最终 TopN 仍为「其他」的再走单股接口兜底（只对选中的票打网络）
    d = get_pools()
    for _s in rows_all:
        if not _s.get('industry') or _s['industry'] in ('', '其他'):
            _ic = _IND_CACHE.get(_s.get('code') or '')
            if _ic:
                _s['industry'] = _ic
    zt_lbc = {}
    for sec, sts in d['sectors'].items():
        for st in sts:
            zt_lbc[st.get('c')] = int(st.get('lbc') or 0)
    # 大盘上下文 + 涨停板块题材（先算：近5日放宽依赖题材热度与最强主线）
    try:
        _idx = get_indices()
        _mscore, _mlabel, _ = market_score(_idx, d)
    except Exception:
        _mscore, _mlabel = 50, '—'
    _lu = int(d.get('lu') or 0)
    _zb = int(d.get('zb') or 0)
    _zbr = (_zb / (_lu + _zb) * 100) if (_lu + _zb) else 0.0
    _zt_list = []
    for _sec_n, _sec_sts in (d.get('sectors') or {}).items():
        if len(_sec_sts) >= 2:
            _zt_list.append((_sec_n, len(_sec_sts)))
    _zt_list.sort(key=lambda kv: -kv[1])
    _zt_top = _zt_list[:6]
    _zt_names = [n for n, _ in _zt_top]
    _mkt_ctx = (f'大盘：涨停{_lu}家/炸板{_zb}家({_zbr:.0f}%) 情绪分{int(_mscore)}({_mlabel}) '
                f'最强板块{(_zt_top[0][0] if _zt_top else "—")}')
    # 题材热度（粗算，供近5日放宽判断；过滤后再用候选池精算供打分）
    heat_pre, _ = _theme_heat(rows_all)
    cands = _tail_filter(rows_all, heat_pre, _zt_names)
    heat, cnt = _theme_heat(cands)
    # 共振升级-弱共振剔除：同题材候选<2家 且 题材热度<45 的「独涨+冷题材」剔除（尾盘口径）
    cands = [s for s in cands
             if not (cnt.get(_sec_clean(s['industry']) or '其他', 0) < 2
                     and heat.get(_sec_clean(s['industry']) or '其他', 0) < 45)]
    heat, cnt = _theme_heat(cands)
    mem = load_memory()
    _calc_resonance(cands, heat, cnt, mem, is_tail=True)
    for s in cands:
        s['score'] = _tail_score_v2(s, heat, cnt, mem, _zt_names)
    cands.sort(key=lambda x: -x['score'])
    tops = cands[:AUCTION_TOP_N]
    # 行业兜底：最终 TopN 里仍是「其他」的，走单股接口取真行业名（_stock_industry 自带缓存，取到后全库复用）
    for _s in tops:
        if not _s.get('industry') or _s['industry'] in ('', '其他'):
            try:
                _f = (_stock_industry(_s.get('code') or '') or '').strip()
                if _f and _f != '其他':
                    _s['industry'] = _f
            except Exception:
                pass
    if not tops:
        return _wrap('<div style="color:#e2e8f0;font-size:13px;">今天尾盘没有一只同时满足「还没上板、放量、离前高还有空间」的票，这一档直接空着，不硬凑。下一时段：收盘复盘。</div>', '🔔', title, show_reson=False)
    _ds_res = _tail_ds(tops, heat, _zt_top, _mkt_ctx, _mscore, _lu, _zb)
    ds_map = (_ds_res or {}).get('per') or {}
    ds_overall = (_ds_res or {}).get('overall') or ''
    reson_reason = (_ds_res or {}).get('reson_reason') or ''
    cap_advice = (_ds_res or {}).get('cap_advice') or ''
    wind_strong = (_ds_res or {}).get('wind_strong') or ''
    wind_weak = (_ds_res or {}).get('wind_weak') or ''
    # （用户指令：已删除「🧭 今日整体」overall 两段；尾盘卡保留 ds_overall 仅用于下方「大盘实时」行）
    # TOP10 渲染（暗线/大白话/建议/次日竞价预期；失败仅数据事实行）
    rows = ''
    for i, s in enumerate(tops, 1):
        _deep = ds_map.get(s['name'])
        # 多周期视角（Top5 打标，缓存免重复拉K；失败静默）
        _cyc_html = ''
        _form_html = ''
        if i <= AUCTION_TOP_N:
            _cyc, _cyc_reason = _cycle_tag(s.get('code') or '', s.get('industry') or '', heat.get(_sec_clean(s.get('industry') or '') or '其他') or 0)
            if _cyc:
                _cyc_html = f'<div style="color:#8bd3c7;font-size:12px;margin-top:2px;">⏱ 周期视角：<b>{_cyc}</b> ｜ {_cyc_reason}</div>'
            try:
                s['_form'] = _auction_form(s.get('code') or '') or {}
                _form_html = _form_line(s['_form'])
            except Exception:
                s['_form'] = {}
                _form_html = ''
        if _deep and _deep.get('logic'):
            _opcol = {'别追': RED, '轻仓试': TEAL, '看': GOLD, '观望': GREY, '不碰': RED}.get(_deep.get('op', ''), GOLD)
            _rows_html = (f"""<div style="color:#a78bfa;font-size:12px;margin-top:3px;">🔍 暗线：{_deep.get('dark','')}（{_deep.get('reason','')}）</div>
<div style="color:#a78bfa;font-size:12px;margin-top:2px;">🧠 题材深挖：{_deep.get('logic','')}</div>
<div style="color:#e9ecef;font-size:12px;margin-top:2px;">👉 大白话：{_deep.get('why','')}</div>
<div style="color:#ffd43b;font-size:12px;margin-top:2px;">🔮 次日竞价预期：{_deep.get('next','')}</div>
<div style="color:#ced4da;font-size:12px;margin-top:2px;">🎯 建议：<b style="color:{_opcol};">{_deep.get('op','')}</b> ｜ 买点：{_deep.get('buy','')} ｜ 止损：{_deep.get('stop','')} ｜ 放弃：{_deep.get('drop','')}</div>""")
        else:
            _rows_html = (f"""<div style="color:#ced4da;font-size:12px;margin-top:3px;">📊 盘口：涨幅{s['pct']:+.1f}%、量比{s['lb']:.1f}、换手{s['turn']:.1f}%、市值{s.get('mv',0):.0f}亿——{_tail_fact_read(s)}</div>""")
        rows += f"""<div style="background:#1f2635;border-left:3px solid {GOLD if s['score'] >= 70 else TEAL};border-radius:8px;padding:9px 11px;margin:6px 0;">
<div style="font-size:14px;font-weight:700;color:#fff;">{i}. {s['name']} <span style="color:{GREY};font-size:12px;">{s['code']}</span> <span style="color:{GOLD};font-weight:800;float:right;">{s['score']:.0f}分</span></div>
<div style="color:{GREY};font-size:12px;">尾盘当日涨幅 <b style="color:{_c(s['pct'])}">{s['pct']:+.2f}%</b> ｜ 量比 {s['lb']:.1f} ｜ 换手 {s['turn']:.1f}% ｜ 市值 {s.get('mv',0):.0f}亿{(' ｜ 行业：' + str(s['industry'])) if str(s.get('industry') or '').strip() not in ('', '其他') else ''}</div>
<div style="color:#8bd3c7;font-size:12px;margin-top:2px;">📉 位置：{('距60日高 ' + ('%.1f%%' % s['_pos60'])) if s.get('_pos60') is not None else '前高未取得'}，近5个交易日没涨停过，这一档不是在上板途中接的</div>
{_cyc_html}
{_form_html}
{_rows_html}</div>"""
    # Top3 速判（含暗线，档位由代码阈值实算，动作交 AI 判读）
    top3_txt = ''
    if tops:
        def _quick_act_tail(s_):
            if s_['score'] < 60:
                return '降权/不追', RED
            if s_['score'] >= 72:
                return '强', TEAL
            return '中', GOLD
        _t3 = []
        for i, s_ in enumerate(tops[:3], 1):
            _a, _col = _quick_act_tail(s_)
            _d3 = ds_map.get(s_['name']) or {}
            _dark_txt = (f'｜🔍暗线:{_d3.get("dark","")}' if _d3.get('dark') else '')
            _t3.append(f'<b style="color:{_col}">{i}.{s_["name"]} {_a}</b>{_dark_txt}')
        top3_txt = (f'<div style="margin-top:10px;padding:9px 11px;background:#1c2830;border-left:4px solid #a78bfa;'
                    f'border-radius:8px;font-size:13px;color:#e9ecef;"><b>🎯 尾盘 Top3 速判（含暗线）：</b>'
                    + ('<br>'.join(_t3) if _t3 else '—')
                    + '</div>')
    # 行业/题材风向（最强/最弱暗线原因）
    hot = sorted(heat.items(), key=lambda kv: -kv[1])[:3]
    hot_txt = '、'.join(k for k, _ in hot) or '暂无'
    weak_lst = sorted(heat.items(), key=lambda kv: kv[1])
    weak_txt = (weak_lst[0][0] if weak_lst else '暂无')
    if _zt_top:
        _zt_hot = '、'.join(f'{n}({c}家)' for n, c in _zt_top[:3])
    else:
        _zt_hot = ''
    # 共振强度已于 2026-11-07 从卡片移除：共振只作内部因子参与打分，不对用户展示
    _rs_txt = ''
    _ws = (f'<div style="font-size:13px;color:#e9ecef;">{wind_strong}</div>' if wind_strong else '')
    _ww = (f'<div style="font-size:13px;color:#e9ecef;">{wind_weak}</div>' if wind_weak else '')
    wind = ((f'<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">🌬️ 行业/题材风向</div>{_ws}{_ww}')
            if (_ws or _ww) else '')
    # 大盘实时确认（结合大盘总结）
    _mkt_sum = ''
    if ds_overall:
        _mkt_sum = f'<div style="margin:4px 0;font-size:13px;background:#1a2029;border-left:3px solid {GOLD};border-radius:8px;padding:6px 10px;">🌍 大盘实时：{_mkt_ctx}</div>'
    _confirm_block = ('<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">🔔 尾盘实盘确认</div>'
                      + _mkt_sum + rows)
    # （用户指令：已删除「🎚 共振原因」_reson_reason_row 段）+ 档位建议 + 数据时点标注
    _cap_advice_row = (f'<div style="margin-top:8px;padding:7px 10px;background:#1c2230;border-left:4px solid {GOLD};'
                       f'border-radius:8px;font-size:13px;color:#e9ecef;">📊 当前档位建议（按盘面）：{cap_advice}</div>') if cap_advice else ''
    _v2_note = ''
    _tail_note = ''
    emotion_t = _emotion_from_pools(d)
    inner = (f'<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">🎯 尾盘竞价筛选 TOP{AUCTION_TOP_N}（低位放量·买在涨停前）</div>'
             + top3_txt + _confirm_block + wind + _cap_advice_row
             + pos_cap_line(emotion_t, None) + _v2_note + _tail_note)
    return _wrap(inner, '🔔', title, show_reson=False)


def _confirm_ds(infos, mkt_ctx=None):
    """竞价确认 LLM 深挖（8项修复⑦）：结合大盘实时总结 + 对 TOP5 每只输出 为什么能跟/为什么放弃。
    返回 {"market": 大盘总结, "per": {name: reason}}；失败返回 {}（渲染数据事实行，不落规则模板）。"""
    if not infos or not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return {}
    lines = '\n'.join(f"- {x['name']}({x['code']}) 高开{x['op']:+.1f}% 量比{'未取得' if not x.get('lb') or float(x.get('lb') or 0) <= 0 else ('%.1f' % x['lb'])} 题材{x['sec']} 判定={'可跟' if x['ok'] else '放弃'}（规则初判：{x['why']}）" for x in infos)
    fmt = ('你是10年A股超短线交易员，竞价确认阶段，先结合大盘实时环境给一句话总结，再对每只票逐一解释判定（不许只说"不在区间"）：\n'
           + _FIVE_BRIEF_OLD + '\n'
           + f'【大盘实时环境】{mkt_ctx or "未提供"}\n'
           + '竞价名单：\n' + lines + '\n'
           + '【暗线业务深挖·每只必做】先一句话说清公司靠什么赚钱（禁「XX龙头/XX概念」标签）；再挖暗线业务——具体产品/技术/业务是什么、进展到哪个阶段、在产业链哪个环节、有没有卡位壁垒、对业绩是真实贡献还是纯故事/预期；然后判断跟今日最强主线是【实受益】【沾边】还是【纯蹭】、弹性大不大。挖不出来如实写「未见明确暗线业务」，禁止用「相关」「涉及」「布局」「受益于」糊弄。暗线不硬就明确写「不碰/放弃」。\n'
           + '【大盘决定仓位】大盘强(涨停多/情绪分高/指数涨)时同票可跟，大盘弱(炸板多/情绪分低/指数跌)时同票必须放弃，理由要落到大盘数据上。\n'
           + '【量比红线】量比标注"未取得"的票说明数据源没取到该字段，绝不得把"未取得"当作量比0来解读，更不得以量比不足为由否决它——只凭高开幅度/题材热度/位置判定；\n'
           + '只输出 JSON：{"market":"大盘实时总结一句话（结合涨停/炸板/情绪分/指数，至少25字，禁止模板句）","per":[{"name":"股票名称","reason":"为什么能跟/为什么放弃(大白话深挖: 大盘环境怎么影响这只+高开是否透支/量比真假/暗线业务(公司靠什么赚钱+暗线产品或技术进展到哪+对业绩真实贡献+与今日主线实受益/沾边/纯蹭，挖不出写未见明确暗线业务)/题材是不是当日主线/有没有暗雷)，至少40字"}]}，'
           + '必须覆盖每只，不许偷懒。')
    t = ask_deepseek({'task': 'confirm_ds', 'stocks': [{'name': x['name'], 'code': x['code'], 'op': x['op'],
                                                        'lb': x['lb'], 'sec': x['sec'], 'ok': x['ok']} for x in infos],
                      'format': fmt}, purpose='confirm_ds', system_text=_ASK_DS_SYS_AC)
    out = {}
    if not t:
        return out
    try:
        _j = json.loads(t[t.find('{'):t.rfind('}') + 1])
        if isinstance(_j, dict):
            out['market'] = str(_j.get('market', '') or '')
            per = {}
            for it in (_j.get('per') or []):
                nm = str(it.get('name') or '').strip()
                if nm and it.get('reason'):
                    per[nm] = str(it['reason'])
            out['per'] = per
    except Exception:
        pass
    return out


def _cycle_verdict(groups, order, lu, zb, mscore):
    """多周期一句话总建议：把各周期分散建议收成一条，避免「超短快进快出」和「中长线波段」互相打架。"""
    _lv = [k for k in order if (groups or {}).get(k)]
    if not _lv:
        return ''
    _zbr = (zb / (lu + zb)) if (lu + zb) else 0.0
    _weak = (float(mscore or 50) < 50) or (_zbr > 0.30)
    if _weak:
        return ('今天情绪偏弱（涨停%d家/炸板%d家、炸板率%.0f%%），只做超短线，次日不连板就走；'
                '中长线仓位一律不加，等情绪回到安全区再谈趋势。' % (lu, zb, _zbr * 100))
    if ('中长线（1-6月）' in _lv) or ('长线（6月+）' in _lv):
        return ('今天情绪还行，主力愿意做趋势：以中长线趋势仓为主，超短线只做最强主线那一两只，'
                '两个周期共用一个总仓位上限，别各自加仓。')
    return ('今天只适合 %s，其他周期不动，仓位在总仓位上限里切分。' % _lv[0])


def build_cycle(title='多周期视角研判'):
    """多周期视角研判（新增独立推送项目 2026-11-05；周期标注不再进竞价卡，竞价已恢复原状）：
    收盘后推送：复用尾盘量价候选（_tail_gainers→_tail_qt_fill→_tail_filter），逐只打 _cycle_tag
    （超短线/短线/中长线/长线+原因），按周期分组展示 + 仓位档建议。纯规则零 LLM 预算，失败静默。"""
    try:
        rows_all = _tail_gainers()
    except Exception:
        rows_all = None
    if not rows_all:
        return None
    try:
        rows_all = _tail_qt_fill(rows_all)
        d = get_pools()
    except Exception:
        return None
    for _s in rows_all:
        if not _s.get('industry') or _s['industry'] in ('', '其他'):
            _ic = _IND_CACHE.get(_s.get('code') or '')
            if _ic:
                _s['industry'] = _ic
    try:
        heat_pre, _ = _theme_heat(rows_all)
        _zt_list = []
        for _sec_n, _sec_sts in (d.get('sectors') or {}).items():
            if len(_sec_sts) >= 2:
                _zt_list.append((_sec_n, len(_sec_sts)))
        _zt_list.sort(key=lambda kv: -kv[1])
        _zt_names = [n for n, _ in _zt_list[:6]]
        cands = _tail_filter(rows_all, heat_pre, _zt_names)
    except Exception:
        return None
    if not cands:
        return None
    heat, cnt = _theme_heat(cands)

    def _sec(s):
        return _sec_clean(s.get('industry') or '') or '其他'

    # 弱共振剔除（同尾盘口径）
    cands = [s for s in cands if not (cnt.get(_sec(s), 0) < 2 and heat.get(_sec(s), 0) < 45)]
    if not cands:
        return None
    groups = {}
    order = ['超短线（1-3日）', '短线（3-10日）', '中长线（1-6月）', '长线（6月+）', '短线观察']
    deep_stocks = []
    for s in cands[:10]:
        cyc, reason = _cycle_tag(s.get('code') or '', s.get('industry') or '', heat.get(_sec(s), 0) or 0)
        if not cyc:
            continue
        s['_cyc'] = cyc
        s['_cyc_reason'] = reason
        deep_stocks.append(s)
        groups.setdefault(cyc, []).append((s, reason))
    if not groups:
        return None
    # LLM 暗线深挖（收盘周期视角语义；失败/预算尽 → {} → 仍推周期分组数据行，不推假暗线）
    ds = {}
    try:
        _idx = get_indices()
        _mscore, _mlabel, _ = market_score(_idx, d)
    except Exception:
        _mscore, _mlabel = 50, '—'
    _lu = int(d.get('lu') or 0)
    _zb = int(d.get('zb') or 0)
    _zbr = (_zb / (_lu + _zb) * 100) if (_lu + _zb) else 0.0
    _mkt_ctx = (f'大盘：涨停{_lu}家/炸板{_zb}家({_zbr:.0f}%) 情绪分{int(_mscore)}({_mlabel}) '
                f'最强板块{(_zt_list[0][0] if _zt_list else "—")}')
    if deep_stocks:
        ds = _cycle_ds(deep_stocks, heat, _zt_list, _mkt_ctx, _mscore, _lu, _zb)
    per = (ds or {}).get('per') or {}
    cap_advice = str((ds or {}).get('cap_advice', '') or '')
    cap = {'超短线（1-3日）': '在这档里最多用总仓位1-2成，次日不连板就走',
           '短线（3-10日）': '回踩MA10/MA20低吸，占2-3成',
           '中长线（1-6月）': '趋势仓3-5成，跌破MA20减',
           '长线（6月+）': '底仓配置，按月跟踪',
           '短线观察': '等放量确认再参与，不提前埋伏'}
    _gcol = {'超短线（1-3日）': TEAL, '短线（3-10日）': GOLD,
             '中长线（1-6月）': '#8bd3c7', '长线（6月+）': '#b1852e', '短线观察': GREY}
    rows = ''
    for g in order:
        items = groups.get(g)
        if not items:
            continue
        _gc = _gcol.get(g, GREY)
        rows += f'<div style="color:{_gc};font-size:14px;font-weight:800;margin:10px 0 4px;">{g}（{len(items)}）</div>'
        for s, reason in items:
            d_i = per.get(s['name'])
            deep_html = ''
            if d_i and d_i.get('logic'):
                _opcol = {'别追': RED, '轻仓试': TEAL, '看': GOLD, '观望': GREY, '不碰': RED}.get(d_i.get('op', ''), GOLD)
                deep_html = (f"""<div style="color:#a78bfa;font-size:12px;margin-top:3px;">🔍 暗线：{d_i.get('dark','')}（{d_i.get('reason','')}）</div>
<div style="color:#a78bfa;font-size:12px;margin-top:2px;">🧠 深挖：{d_i.get('logic','')}</div>
<div style="color:#e9ecef;font-size:12px;margin-top:2px;">👉 大白话：{d_i.get('why','')}</div>
<div style="color:#ced4da;font-size:12px;margin-top:2px;">🎯 建议：<b style="color:{_opcol};">{d_i.get('op','')}</b> ｜ 买点：{d_i.get('buy','')} ｜ 止损：{d_i.get('stop','')} ｜ 放弃：{d_i.get('drop','')}</div>""")
            rows += (f'<div style="background:#1f2635;border-left:3px solid {_gc};border-radius:8px;padding:8px 11px;margin:5px 0;">'
                     f'<div style="font-size:13px;font-weight:700;color:#fff;">{s["name"]} <span style="color:{GREY};font-size:11px;">{s.get("code","")}</span> <span style="color:{_c(s["pct"])};font-size:12px;">{s["pct"]:+.2f}%</span></div>'
                     f'<div style="color:{GREY};font-size:11px;">量比{s["lb"]:.1f} ｜ 换手{s.get("turn",0):.1f}% ｜ 市值{s.get("mv",0):.0f}亿 ｜ 题材:{s.get("industry","")}</div>'
                     f'<div style="color:#8bd3c7;font-size:12px;margin-top:2px;">⏱ {reason}</div>'
                     f'<div style="color:#e6a23c;font-size:11px;margin-top:2px;">仓位：{cap.get(g,"")}</div>'
                     f'{deep_html}</div>')
    if cap_advice:
        rows = (f'<div style="background:#1f2635;border-left:3px solid {GOLD};border-radius:8px;padding:8px 11px;margin:6px 0;">'
                f'<div style="font-size:13px;font-weight:800;color:{GOLD};">💼 档位建议</div>'
                f'<div style="color:#e9ecef;font-size:12px;margin-top:2px;">{cap_advice}</div></div>') + rows
    _mkt = f'涨停{_lu}家/炸板{_zb}家' if (_lu or _zb) else '情绪—'
    _verdict = _cycle_verdict(groups, order, _lu, _zb, _mscore)
    _v_html = (('<div style="background:#1c2230;border-left:4px solid ' + GOLD + ';border-radius:8px;padding:9px 11px;margin:6px 0;">'
                '<div style="font-size:13px;font-weight:800;color:' + GOLD + ';">📌 总建议</div>'
                '<div style="color:#e9ecef;font-size:12px;margin-top:3px;">' + _verdict + '</div></div>')
               if _verdict else '')
    head = (f'<div style="font-size:12px;color:#8490a3;margin-bottom:6px;">{_mkt}</div>')
    return _wrap(head + _v_html + rows, '🔎', title, show_reson=False)


def build_confirm():
    """竞价确认 09:25：重跑与 09:20 相同的双重打分 TOP5，只确认「实际高开 + 量能达标」者。
    纯规则零 DeepSeek；不依赖 09:20 推送结果（GHA 跨 run 无持久性，重算是确定性等价）。"""
    d = get_pools()
    zt_lbc = {}
    for sec, sts in d['sectors'].items():
        for st in sts:
            zt_lbc[st.get('c')] = int(st.get('lbc') or 0)
    cands = _auction_filter(_clist_gainers(), zt_lbc)
    if not cands:
        return _wrap('<div style="color:#e2e8f0;font-size:13px;">今天竞价没有一只票同时满足这几条硬条件，这一档直接跳过</div>', '🔔', '竞价确认')
    heat, cnt = _theme_heat(cands)
    mem = load_memory()
    for s in cands:
        s['score'] = _auction_score(s, heat, cnt, mem)
    cands.sort(key=lambda x: -x['score'])
    rows, ok_n, infos = [], 0, []
    for s in cands[:5]:
        sym = ('sh' if s['code'].startswith('6') else 'sz') + s['code']
        try:
            q = _qt(sym)
            if not q or not q['prev']:
                continue
            op = (q['open'] / q['prev'] - 1) * 100  # 真实高开幅度（open/昨收）
            vq = None
            try:
                arr = get_klines(sym, 2)
                if len(arr) >= 2 and float(arr[-2][5]) > 0 and q.get('vol'):
                    vq = (q['vol'] * 100) / float(arr[-2][5]) * 100
            except Exception:
                pass
            gem = s.get('board') == 'gem'
            lo, hi = (2, 7) if not gem else (4, 14)
            lb_min = 2.0 if not gem else 1.5
            sec_heat = heat.get(re.sub(r'[行业板块概念\s]+', '', s['industry']) or '其他', 0)
            sec_clean2 = re.sub(r'[行业板块概念\s]+', '', s['industry']) or '其他'
            ok_flag = lo <= op <= hi and q.get('lb', 0) >= lb_min and (vq is None or vq >= 8)
            if ok_flag:
                why_r = ''
                rows.append(f'<div style="margin:6px 0;font-size:13px;background:#1c2830;border-left:3px solid {RED};border-radius:8px;padding:7px 10px;">'
                            f'✅ <b style="color:#fff;">{s["name"]}({s["code"]})</b> 高开{op:+.1f}% 量比{q.get("lb", 0):.1f} '
                            f'→ <span style="color:{RED};font-weight:800;">可跟 1成试探，止损-3%</span>'
                            f'<div style="color:{TEAL};font-size:12px;">今日总仓建议：{_pos_advice(_emotion_from_pools(d))}</div>'
                            f'<div style="color:{TEAL};font-size:12px;">题材 {s["industry"]}（热度{sec_heat:.0f}）｜综合分 {s["score"]}</div></div>')
                ok_n += 1
            else:
                if q.get('lb', 0) < lb_min:
                    why_r = f'量比{q.get("lb", 0):.1f}<{lb_min}，资金竞价没进场，撑不起高开，放弃'
                elif op > hi:
                    why_r = f'高开{op:+.1f}%超过{hi}%，竞价透支、开盘容易被砸，放弃'
                elif op < lo:
                    why_r = f'高开{op:+.1f}%不足{lo}%，没溢价不值得做，放弃'
                else:
                    why_r = '竞价量/昨量不足8%，虚量撑不住，放弃'
                rows.append(f'<div style="margin:6px 0;font-size:13px;background:#1f2635;border-left:3px solid {GREY};border-radius:8px;padding:7px 10px;">'
                            f'❌ {s["name"]}({s["code"]}) 高开{op:+.1f}% 量比{q.get("lb", 0):.1f} → <span style="color:{GREY};">放弃（{why_r}）</span></div>')
            infos.append({'name': s['name'], 'code': s['code'], 'op': op, 'lb': float(q.get('lb', 0)),
                          'sec': sec_clean2, 'ok': ok_flag, 'why': why_r})
        except Exception:
            continue
    if not rows:
        return _wrap('<div style="color:#e2e8f0;font-size:13px;">今天竞价没有能确认的标的，这一档直接跳过</div>', '🔔', '竞价确认')
    try:
        _idx = get_indices()
        _mscore, _mlabel, _ = market_score(_idx, d)
    except Exception:
        _mscore, _mlabel = 50, '—'
    _lu = int(d.get('lu') or 0)
    _zb = int(d.get('zb') or 0)
    _mkt_ctx = (f'大盘：涨停{_lu}家/炸板{_zb}家 情绪分{int(_mscore)}({_mlabel}) '
                f'最强板块{(sorted(d.get("sectors", {}).items(), key=lambda kv: -len(kv[1]))[:1] or [["—"]])[0][0] if d.get("sectors") else "—"}')
    _dmap = _confirm_ds(infos, _mkt_ctx)
    rows2 = list(rows)
    _per2 = (_dmap.get('per') or {}) if isinstance(_dmap, dict) else {}
    _mkt2 = (_dmap.get('market') or '') if isinstance(_dmap, dict) else ''
    if _per2 or _mkt2:
        _head2 = (f'<div style="color:#e9ecef;font-size:12px;margin:3px 0;">🌍 大盘实时：{_mkt2}</div>' if _mkt2 else '')
        rows2.append('<div style="margin-top:6px;padding:8px 10px;background:#1c2230;border-left:4px solid ' + TEAL + ';border-radius:8px;">'
                     + _head2
                     + ''.join('<div style="color:#e9ecef;font-size:12px;margin:3px 0;">🧠 ' + nm + '：' + rz + '</div>'
                               for nm, rz in _per2.items()) + '</div>')
    inner = (f'<div style="color:{TEAL};font-size:13px;">基于 09:20 双打分 TOP5 实盘复核（规则复核 + AI 深挖）'
             f'｜确认 {ok_n} 只</div>' + ''.join(rows2))
    return _wrap(inner, '🔔', '竞价确认')


def _money_flow_top(n=5):
    """主力资金流（新浪板块资金接口，netamount 排序）：返回 (净流入前n, 净流出前n) 或 (None, None)。
    过滤 ETF/债券类。"""
    def _f(asc):
        u = ('https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_bkzj_ssggzj'
             '?page=1&num=%d&sort=netamount&asc=%d&fenlei=1') % (n + 8, asc)
        req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'})
        d = json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8', 'ignore'))
        out = []
        for x in d:
            nm = str(x.get('name') or '')
            if any(k in nm for k in ('ETF', '债', '基金', '转债', 'LOF')):
                continue
            out.append((nm, float(x.get('netamount') or 0)))
            if len(out) >= n:
                break
        return out
    try:
        return _f(0), _f(1)
    except Exception as e:
        print('[noon] 资金流未取得:', e)
        return None, None


def build_noon():
    idx = get_indices()
    d = get_pools()
    mem = load_memory()
    days = sorted(mem.keys(), reverse=True)
    bits = '<span style="color:#495057">｜</span>'.join(f"<span style='color:{_c(x['pct'])};font-weight:700'>{x['name']}{x['pct']:+.2f}%</span>" for x in idx)
    lad = ''
    for n, s in d['ladder']:
        names = '、'.join(s)
        if n >= 3:
            lad += f'<div style="color:{GREEN};font-size:13px;"><b style="color:{RED}">{n}板</b>（高度板·分歧风险）：{names}</div>'
        else:
            lad += f'<div style="color:{GREY};font-size:13px;"><b style="color:{GOLD}">{n}板</b>：{names}</div>'
    # —— 资金博弈（新浪资金流）——
    mf = ''
    fin, fout = _money_flow_top(5)
    if fin and fout:
        fin_r = '、'.join(f"{nm}{v/1e8:+.1f}亿" for nm, v in fin[:5])
        fout_r = '、'.join(f"{nm}{v/1e8:+.1f}亿" for nm, v in fout[:5])
        net_total = sum(v for _, v in fin[:5]) + sum(v for _, v in fout[:5])
        judge = '主力净流入>净流出，真强概率大，午后可跟主线。' if net_total > 0 else '净流出占优，警惕诱多/资金离场，午后防守。'
        mf = f"""<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">💰 资金博弈结果</div>
<div style="background:#1f2635;border-radius:10px;padding:10px 12px;margin-top:5px;">
<div style="font-size:13px;color:{RED};">主力净流入前5：{fin_r}</div>
<div style="font-size:13px;color:{GREEN};margin-top:3px;">主力净流出前5：{fout_r}</div>
<div style="font-size:13px;color:{TEAL};margin-top:5px;">👉 {judge}</div></div>"""
    else:
        mf = '<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">💰 资金博弈结果</div><div style="color:' + GREY + ';font-size:13px;">主力资金流接口未取得（免费接口被墙），不编造</div>'
    # —— DeepSeek 午间定性 + 下午作战计划 ——
    _nw = get_news(30)
    ds_md = _noon_ds(idx, d, _nw)
    ds_block = f"""<div style="margin-top:10px;padding:10px;background:#1c2230;border-left:4px solid {GOLD};border-radius:8px;">
<div style="font-size:15px;font-weight:800;color:{GOLD};">🤖 DeepSeek 午间定性 + 下午作战计划</div>{ds_md}</div>""" if ds_md else ''
    inner = f"""{ds_block}{build_events('noon', _nw)}
<div style="font-size:14px;">{bits}</div>{health_bar(idx, d, fin, fout)}
<div style="margin-top:6px;font-size:14px;">🔴涨停<b style="color:{RED}">{d['lu']}</b> 🟢炸板<b style="color:{GREEN}">{d['zb']}</b> 🟢跌停<b style="color:{GREEN}">{d['dt']}</b> 最高<b style="color:{GOLD}">{d['max_lbc']}板</b></div>
<div style="margin-top:6px;font-size:13px;">{yesterday_premium()}</div>
<div style="margin-top:4px;font-size:13px;">{breadth_sample()}</div>
<div style="margin-top:4px;font-size:13px;color:{TEAL};">🔗 {coarse_linkage(d)}</div>
{leader_divergence(d)}{mf}
<div style="margin-top:10px;font-size:16px;font-weight:800;color:#ff922b;">🔥 上午最强方向 TOP15</div>{_sector_cards(d['tops'][:15], d['zb_names'])}
{''.join(f'<div style="margin:3px 0;font-size:12px;color:{GREY};">{life_badge(sec, d, mem, days)} {sec}（今日{len(st)}家）</div>' for sec, st in d['tops'][:3] if len(st) >= 1)}
<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">🪜 连板梯队（3板以上=高度板，谨慎）</div>
<div style="background:#1f2635;border-radius:10px;padding:10px;margin-top:5px;">{lad}</div>{pos_cap_line(sentiment(idx, d)[0], mainline_health(idx, d, fin, fout)[1])}"""
    return _wrap(inner, '☀️', '午间作战')




def _noon_panel_html(t):
    """午间作战V3渲染：极简面板标签配色。"""
    out = []
    for line in t.split('\n'):
        line = line.strip()
        if not line:
            continue
        if line.startswith('【狙击指令面板】'):
            out.append('<div style="color:' + RED + ';font-weight:900;font-size:14px;margin-top:10px;">' + line + '</div>')
        elif line.startswith('【盘面定调】'):
            out.append('<div style="color:' + GOLD + ';font-weight:900;font-size:14px;margin-top:10px;">' + line + '</div>')
        elif line.startswith('【观察池') or line.startswith('【避风港'):
            out.append('<div style="color:' + TEAL + ';font-weight:900;font-size:14px;margin-top:10px;">' + line + '</div>')
        elif line.startswith('🔴'):
            out.append('<div style="color:' + RED + ';font-weight:800;font-size:13px;margin-top:8px;">' + line + '</div>')
        elif line.startswith('🎯'):
            out.append('<div style="color:' + GOLD + ';font-size:13px;margin-top:3px;line-height:1.6;">' + line + '</div>')
        elif line.startswith('🔥'):
            out.append('<div style="color:#ff922b;font-size:13px;margin-top:3px;line-height:1.6;">' + line + '</div>')
        elif line.startswith('⚔️') or line.startswith('⚔'):
            out.append('<div style="color:#ffd43b;font-size:13px;margin-top:3px;line-height:1.6;">' + line + '</div>')
        elif line.startswith('🛑'):
            out.append('<div style="color:' + GREEN + ';font-weight:700;font-size:13px;margin-top:3px;line-height:1.6;">' + line + '</div>')
        else:
            out.append('<div style="color:#ced4da;font-size:13px;line-height:1.7;margin-top:3px;">' + line + '</div>')
    return ''.join(out)


def _noon_para_html(t):
    """午间作战V2渲染：按空行分段，段首行金标，全文无【】。"""
    import re as _re
    paras = [p.strip() for p in _re.split(r'\n\s*\n', t) if p.strip()]
    out = []
    for p in paras:
        lines = [ln.strip() for ln in p.split('\n') if ln.strip()]
        out.append('<div style="margin-top:9px;">')
        for i, ln in enumerate(lines):
            if i == 0:
                out.append('<div style="color:' + GOLD + ';font-weight:800;font-size:13px;line-height:1.6;">' + ln + '</div>')
            else:
                out.append('<div style="color:#ced4da;font-size:13px;line-height:1.7;margin-top:3px;">' + ln + '</div>')
        out.append('</div>')
    return ''.join(out)


def _noon_ds(idx, d, news=None):
    """午间 DeepSeek：老手群语音作战简报（用户强制 V4 结构）。失败返回 ''。"""
    if not DEEPSEEK_KEY:
        return ''
    yest_prem = ''
    try:
        yest_prem = yesterday_premium().replace('<div style="margin-top:6px;font-size:13px;">', '').replace('</div>', '')
    except Exception:
        pass
    mf_note = ''
    try:
        fin, fout = _money_flow_top(5)
        if fin and fout:
            fin_r = '、'.join(f"{nm}{v/1e8:+.1f}亿" for nm, v in fin[:5])
            fout_r = '、'.join(f"{nm}{v/1e8:+.1f}亿" for nm, v in fout[:5])
            net_total = sum(v for _, v in fin[:5]) + sum(v for _, v in fout[:5])
            mf_note = f'上午主力净流入前5板块：{fin_r}；净流出前5板块：{fout_r}；净额合计{net_total/1e8:+.1f}亿，' + ('净流入>净流出，资金在做多。' if net_total > 0 else '净流出占优，警惕诱多。')
        else:
            mf_note = '主力资金流接口未取得，不编造。'
    except Exception:
        mf_note = '主力资金流接口未取得，不编造。'
    hs, hl, ha, _ = mainline_health(idx, d, fin, fout)
    jc = judgment_context()
    news_titles = '；'.join(str(n.get('title') or '')[:40] for n in news[:15]) if news else ''
    if not news_titles:
        try:
            news_titles = '；'.join(str(n.get('title') or '')[:40] for n in get_news(15))
        except Exception:
            news_titles = ''
    payload = {
        'task': 'noon_plan_v4',
        'judgment': jc,
        'indices': [[x['name'], round(x['pct'], 2)] for x in idx],
        'pools': {'lu': d['lu'], 'zb': d['zb'], 'dt': d['dt'], 'max_lbc': d['max_lbc']},
        'yesterday_premium': yest_prem,
        'money_flow_note': mf_note,
        'tops': [[n, len(s)] for n, s in d['tops'][:15]],
        'ladder': [[n, s] for n, s in d['ladder'][:6]],
        'health': [hs, hl, ha],
        'news': news_titles,
    }
    fmt = ('你是十几年经验的一线游资操盘手，任务是给实战交易员写午间作战简报，扒掉主力的底裤，给出明确的狙击目标。不要废话，直接上干货。\n'
           '现在输入：昨日判断、指数简报、涨停/炸板家数、昨日涨停溢价、主力资金净流入/流出前5、上午最强方向、连板梯队、午间事件汇总。\n'
           '【输出格式红线，绝对服从，绝无例外】\n'
           '1. 绝对禁止出现问号或任何设问句，绝对禁止使用列表符号（一二三、1.2.3.）和【】标签。全篇必须像老手在微信群发连串的长语音。\n'
           '2. 绝对禁止推荐千亿大票，总市值必须严格控制在30亿到800亿之间（点名推荐前先自问这票盘子合不合硬筛口径）。\n'
           '3. 全文大白话，极简风格。单只票推演必须用一段话顺到底，字数控制在150字以内。\n'
           '4. 必须详细拆解「题材叠加共振」底牌，并自然揉入以下微观手法：\n'
           '庄家建仓手法：前期挖坑洗盘、缩量横盘熬底、打压吸筹痕迹、股东户数锐减。\n'
           '量化操作手法：盘口频繁拆单托单、脉冲式试盘、锯齿状织布机走势、直线90度点火。\n'
           '联动与情绪因子：上方筹码真空、老妖股记忆、龙虎榜游资接力、大盘跳水逆势抗跌。\n'
           '【执行流程】\n'
           '【禁分栏】下面这几个环节只是你要讲到的内容顺序，输出时绝对不能写成【盘面定调】【资金暗线】这类小标题，要把它们连成一整段长语音顺下来。\n'
           '先说盘面定调：用一两句话点明今天最强主线的龙头是否被通道党顶死，大资金现在在哪个新方向或细分领域做局。\n'
           '接着说资金暗线与传染：必须深挖上午资金去向：为什么资金净流入上面这些板块（原因逻辑，用数据说话）、是什么导致资金异动的核心暗线（主力在打什么算盘：做多主线/高低切/防御/出货）、这笔资金会传染到哪个还没启动的板块/题材/个股（点名具体股+传染逻辑）、下午怎么跟这笔资金（操作建议+条件）。\n'
           '【核心埋伏标的】只推1-2只有硬逻辑的票，每只严格按一段大白话叙述：完整执行「股票深挖铁律」（本质一句话+暗线业务[具体产品+阶段+真实贡献，写不出写「未见明确暗线业务」]+真实关联与弹性[实受益/沾边/纯蹭]+为什么是它+破灭点+动作），把底牌逻辑、微观盘口手法、龙头触发信号和买卖点无缝揉在一起。没有硬逻辑就写「今日无强推」，绝不硬凑。\n'
           '【观察池】列出最多2只备用观察标的（同样限制30到800亿总市值）。用一句话说明它的题材逻辑以及在等什么信号才动手。只留最有希望的，宁缺毋滥。\n'
           '【避风港与仓位】连贯陈述今天必须规避的高位断板风险和大资金流出的诱多板块。给出下午总仓位建议并说明理由。\n'
           '【全文精简硬约束】全文≤320字，像老手在微信群发连串长语音；信息多时优先保证资金暗线与传染、核心埋伏标的完整，观察池/避风港各一句话带过。\n'
           '【自检】检查全文是否无问号无列表；总市值是否在30到800亿之间；是否自然融入了庄家建仓与量化操作手法；买卖点止损是否明确。自检通过才输出。\n'
           '禁止万能句；数据不足以支撑推荐时明确写「今日无强推」；没有真实价位数据时写「待盘中确认」，禁止编造价位；禁止把推测当已核实事实。' + '\n'
           + (('昨日判断（供对照，别重复昨天的错）：\n{judgment}\n' if jc else ''))
           + '请根据以下上午数据输出午间作战简报：\n'
           '指数简报（见 data.indices 字段）：{data.indices}\n'
           '核心数据：涨停{data.pools.lu} 炸板{data.pools.zb} 跌停{data.pools.dt} 最高连板{data.pools.max_lbc} 昨日涨停溢价{data.yesterday_premium}\n'
           '资金博弈：{data.money_flow_note}\n'
           '上午最强方向 TOP15：{data.tops}\n'
           '连板梯队（3板以上已标高度板风险）：{data.ladder}\n'
           '主线健康度：' + str(hs) + '/100（' + hl + '，' + ha + '）\n'
           '午间事件汇总：{data.news}\n'
           '严格按系统提示词输出，全文无问号无列表无【】标签，不要JSON、不要任何额外说明。')
    t = ask_deepseek({'task': 'noon_plan_v4', 'data': payload, 'format': fmt}, purpose='noon_v4')
    if t:
        _save_gauge_from_md(t, source='noon')
    return _noon_para_html(t) if t else ''


def _hold_diag(d, mlabel):
    """持仓个股诊断：今日涨跌/是否主线内/量能/相对强弱/建议；同板块≥2只且板块退潮→标红传染。
    返回 (rows_html, contagion_sec)。"""
    rows = []
    tops_sec = {n for n, _ in d['tops'][:8]}
    worst_sec = {n for n, _ in d['worst']}
    avg_idx = 0.0
    try:
        _idx = get_indices()
        avg_idx = sum(x['pct'] for x in _idx) / max(len(_idx), 1)
    except Exception:
        pass
    for h in HOLDINGS:
        q = _qt(h['code'])
        if not q:
            rows.append("<div style='font-size:13px;'>" + h['name'] + " — 行情未取得</div>")
            continue
        pct = q['pct']
        in_main = h['sector'] in tops_sec
        lb = q.get('lb', 0)
        vol_tag = '放量' if lb >= 1.5 else ('缩量' if 0 < lb < 0.8 else '量能中性')
        rel = '强于大盘' if pct > avg_idx else '弱于大盘'
        if mlabel in ('情绪退潮', '快速轮动') or pct < -3:
            adv, ac = '减仓/止损', GREEN
        elif in_main and pct > 0:
            adv, ac = '持有（主线内）', RED
        elif pct > 0:
            adv, ac = '持有观察', GOLD
        else:
            adv, ac = '减仓', GREEN
        main_txt = '·主线内' if in_main else '·非主线'
        rows.append("""<div style="background:#1f2635;border-left:3px solid """ + ac + """;border-radius:8px;padding:8px 10px;margin:5px 0;font-size:13px;">
<b style="color:#fff;">""" + h['name'] + """</b> <span style="color:""" + _c(pct) + """;">""" + ('%+.1f%%' % pct) + """</span> <span style="color:""" + GREY + """;">｜""" + rel + '｜' + vol_tag + main_txt + """</span>
<span style="color:""" + ac + """;font-weight:700;float:right;">建议：""" + adv + """</span></div>""")
    sec_cnt = {}
    for h in HOLDINGS:
        sec_cnt[h['sector']] = sec_cnt.get(h['sector'], 0) + 1
    contagion_sec = [s for s, c in sec_cnt.items() if c >= 2 and s in worst_sec]
    return ''.join(rows), contagion_sec


# ============ 收盘可跟踪池（小白友好版：禁止已涨停） ============
def _track_pool(d):
    """可跟踪池（禁止已涨停）：只保留两类——
    ① 未涨停但量能放大（量比≥1.5）+ 题材在今日强势主线内 → 明日低吸候选；
    ② 今日大涨未封板（涨幅≥5%、量比≥1.2）→ 明日冲高做T。
    数据源：涨幅榜（未涨停）+ 量比 + 今日强势题材。纯规则零 AI。"""
    zt_codes = set()
    for sec, sts in d['sectors'].items():
        for st in sts:
            zt_codes.add(st.get('c'))
    tops_sec = {n for n, _ in d['tops'][:8]}
    try:
        rows = _clist_gainers()
    except Exception:
        return []
    pool = []
    for s in rows:
        if s['code'] in zt_codes:
            continue                                # 已涨停 → 剔除（对第二天无用）
        if s['pct'] < 1.0:
            continue                                # 涨幅太小不跟踪
        ind = re.sub(r'[行业板块概念\s]+', '', s.get('industry') or '') or '其他'
        vol_ok = s['lb'] >= 1.5                     # 量能放大
        theme_ok = ind in tops_sec                  # 题材共振（在今日强势主线内）
        if vol_ok and theme_ok:                     # 第一类：量能放大 + 题材共振
            pool.append((s, '低吸候选'))
        elif s['pct'] >= 5.0 and s['lb'] >= 1.2:    # 第二类：大涨未封板、分时强势
            pool.append((s, '冲高做T'))
        if len(pool) >= TRACK_POOL_N * 2:
            break
    pool.sort(key=lambda x: -x[0]['lb'])
    return pool[:TRACK_POOL_N]


# ============ 多点cron slot当日去重（2026-10-28：warn/pre/auction/noon/hourly 防重复推送） ============
SLOT_DONE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'slot_done.json')


def _slot_key(slot):
    """去重键：auction/pre/noon/warn 按天；hourly 按天+小时（10/11/13/14 各一次）；
    risk 按 10:35/13:35 两个盘口窗口（各推一次，跨窗口互不干扰）。"""
    today = _bj_now().strftime('%Y-%m-%d')
    if slot == 'hourly':
        return 'hourly|%s|%02d' % (today, _bj_now().hour)
    if slot == 'risk':
        hm = _bj_now().strftime('%H:%M')
        if '10:35' <= hm <= '10:39':
            return 'risk|%s|1035' % today
        if '13:35' <= hm <= '13:39':
            return 'risk|%s|1335' % today
        return 'risk|%s|%s' % (today, hm)
    return '%s|%s' % (slot, today)


def _news_window_key():
    """事件简报窗口键（防同一 5 分钟窗口被多 run 重复推送；不同窗口各推一次）。
    11:40 午间 / 15:10 尾盘 / 15:35 尾盘三窗口独立；其余时刻（手动触发）按当日+分钟兜底。"""
    today = _bj_now().strftime('%Y-%m-%d')
    hm = _bj_now().strftime('%H:%M')
    if '11:40' <= hm <= '11:44':
        return 'news|%s|1140' % today
    if '15:10' <= hm <= '15:14':
        return 'news|%s|1510' % today
    if '15:35' <= hm <= '15:39':
        return 'news|%s|1535' % today
    return 'news|%s|%s' % (today, _bj_now().strftime('%H%M'))


def _slot_window_key(slot):
    """窗口去重键（防同窗口多 run 并发/排队双推）：
    follow 按 14:05/15:05 两个窗口；ext 按 21:38/22:38；news2h 按 12:00/14:00/16:00；
    confirm/zscan/deep6/evening 无固定多点 cron，按天去重。
    watch 为异动档（内容随行情逐次变化），不做窗口去重，靠交易日时段闸门兜底。"""
    today = _bj_now().strftime('%Y-%m-%d')
    hm = _bj_now().strftime('%H:%M')
    if slot == 'follow':
        if '14:05' <= hm <= '14:07':
            return 'follow|%s|1405' % today
        if '15:05' <= hm <= '15:08':
            return 'follow|%s|1505' % today
        return 'follow|%s|%s' % (today, _bj_now().strftime('%H%M'))
    if slot == 'ext':
        if '21:38' <= hm <= '21:39':
            return 'ext|%s|2135' % today
        if '22:38' <= hm <= '22:39':
            return 'ext|%s|2235' % today
        return 'ext|%s|%s' % (today, _bj_now().strftime('%H%M'))
    if slot == 'news2h':
        if '12:00' <= hm <= '12:04':
            return 'news2h|%s|1200' % today
        if '14:01' <= hm <= '14:04':
            return 'news2h|%s|1400' % today
        if '16:00' <= hm <= '16:04':
            return 'news2h|%s|1600' % today
        return 'news2h|%s|%s' % (today, _bj_now().strftime('%H%M'))
    return '%s|%s' % (slot, today)


def _slot_done(key):
    """当日该槽位是否已推送（tools/data/slot_done.json）。失败视为未推送。"""
    try:
        with open(SLOT_DONE_PATH, 'r', encoding='utf-8') as f:
            return bool(json.load(f).get(key, False))
    except Exception:
        return False


def _mark_slot_done(key):
    """标记该槽位当日已推送。"""
    try:
        os.makedirs(os.path.dirname(SLOT_DONE_PATH), exist_ok=True)
        d = {}
        try:
            with open(SLOT_DONE_PATH, 'r', encoding='utf-8') as f:
                d = json.load(f)
        except Exception:
            pass
        d[key] = True
        with open(SLOT_DONE_PATH, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        # 云端 runner 每次全新 checkout，必须把去重状态提交回仓库才能跨 run 生效
        # （否则 09:20 推过竞价后 09:25 的自动 run 仍会重复推送——已实证 11-02 竞价重复推 2 次）
        try:
            rel = os.path.relpath(SLOT_DONE_PATH, os.getcwd())
            _git_commit_push(rel, 'update slot_done')
        except Exception as e:
            print('[slot_done] commit fail:', e)
    except Exception as e:
        print('[slot_done] mark fail:', e)


# ============ eod 当日去重（防手动重复触发推两次） ============
def eod_push_done(today):
    """eod 当日是否已推送（data/eod_status.json）。失败视为未推送。"""
    try:
        with open('data/eod_status.json', 'r', encoding='utf-8') as f:
            return json.load(f).get('date') == today
    except Exception:
        return False


def mark_eod_done(today):
    """标记 eod 当日已推送。"""
    try:
        os.makedirs('data', exist_ok=True)
        with open('data/eod_status.json', 'w', encoding='utf-8') as f:
            json.dump({'date': today, 'pushed_at': _bj_now().strftime('%Y-%m-%d %H:%M:%S')}, f, ensure_ascii=False)
    except Exception:
        pass


def _sec2_deep(scored):
    """收盘主线&强势题材卡批量 LLM 点评。失败 {}（回退规则两句话术）。"""
    if not scored or not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return {}
    lines = '\n'.join(
        f"- 板块「{n}」涨停{len(s)}家 评分{sc}/10 强度{lv} 龙头{sorted(s, key=lambda x: x.get('fbt') or 0)[0].get('n')}"
        for n, s, sc, lv, _ol in scored[:8])
    fmt = ('你是一线游资，收盘复盘，对下面每个强势板块点评明天怎么看（严格按主力游资五步铁律）：\n'
           + FIVE_BRIEF + '\n'
           + '先判断主力明天还会继续做还是准备出货。\n板块数据：\n' + lines + '\n'
           + '只输出 JSON：{"per":[{"name":"板块名(照抄)","logic":"今天为什么强/弱：主力阶段+驱动+资金+持续性(≥25字)","why":"大白话(≥20字)","stage":"启动|接力|分歧|退潮","verdict":"明天能不能跟：跟/看/别追","tomorrow_act":"明天怎么跟：低吸/接力/看戏+条件(≥15字)","dark":"暗线：资金选这个板块真正在做什么局、明天哪个细分最容易接力(≥15字)"}]}，必须覆盖每个板块。')
    t = ask_deepseek({'task': 'sec2_deep', 'items': [{'n': n, 'cnt': len(s), 'sc': sc, 'lv': lv} for n, s, sc, lv, _ol in scored[:8]],
                      'format': fmt}, purpose='sec2_deep')
    out = {}
    if not t:
        return out
    try:
        _j = json.loads(t)
        for it in _j.get('per') or []:
            nm = str(it.get('name') or '').strip()
            if nm:
                out[nm] = {k: str(it.get(k) or '') for k in ('logic', 'why', 'act', 'stage', 'verdict', 'tomorrow_act', 'dark')}
                if not out[nm].get('act') and out[nm].get('tomorrow_act'):
                    out[nm]['act'] = out[nm]['tomorrow_act']
    except Exception:
        pass
    return out


def _eod_review_ds(d, idx, scored, tpool):
    """收盘全面研判（11-05 指令⑤）：TOP10 板块上涨逻辑+涨停个股原因暗线+明日可介入个股原因暗线+
    主线候选/下次爆发题材/主升启动股。失败返回 {}。"""
    if not scored and not tpool:
        return {}
    tops_txt = '；'.join(f"「{n}」涨停{len(s)}家 龙头{sorted(s, key=lambda x: x.get('fbt') or 0)[0].get('n')}" for n, s, *_ in scored[:10])
    pool_txt = '；'.join(f"{s.get('name')}（{s.get('pct')}%，量比{s.get('lb')}，题材{s.get('industry') or '其他'}）" for s, _k in tpool[:8])
    idx_txt = '、'.join(f"{x['name']}{x['pct']:+.2f}%" for x in idx) or '未取得'
    fmt = ('你是深谙A股主力运作的一线游资，收盘后做全面研判。基于以下收盘数据，只输出 JSON：\n'
           '{"tops":[{"sec":"板块名(照抄TOP10)","logic":"上涨核心逻辑：驱动+资金+持续性(≥25字)","leader":"龙头股","leader_dark":"龙头涨停的真实原因与暗线(≥20字)：是板块爆发还是个股利好、资金为什么封它"}],"tomorrow":[{"name":"股票名","reason":"明日可介入原因(≥20字，只从盘面真实异动推导)","dark":"暗线(≥15字)","buy":"买点具体","stop":"止损具体","pos":"仓位"}],"mainline_next":["板块A：为什么可能成主线(≥15字)","板块B：…(最多3个)"],"spark_next":["题材X：下次爆发逻辑(≥15字)","题材Y：…(最多3个)"],"main_start":["股票Z：准备启动主升的理由(≥20字，用盘面数据说话)"]}\n'
           '硬约束：明日可介入/主升启动票禁止推今日涨停/连板票与千亿大盘股；没有把握写「暂无」，禁止万能句；用数据说话。\n'
           '排序要求：tomorrow 数组按「明日最值得介入→次之」排序，只保留最有把握的最多3只，宁缺毋滥；mainline_next/spark_next 同理只给最有把握的方向，禁止罗列凑数。\n'
           '数据：指数 ' + idx_txt + '；涨停' + str(d['lu']) + '炸板' + str(d['zb']) + '跌停' + str(d['dt']) + '；TOP10板块：' + tops_txt + '\n'
           '可跟踪池（今日未涨停、量能放大）：' + (pool_txt or '无'))
    t = ask_deepseek({'task': 'eod_review_ds', 'tops': [n for n, s, *_ in scored[:10]],
                      'pool': [s.get('name') for s, _k in tpool[:8]], 'format': fmt}, purpose='eod_review_ds')
    if not t:
        return {}
    try:
        _j = json.loads(t)
        return _j if isinstance(_j, dict) else {}
    except Exception:
        return {}


def _eod_review_html(rv, scored):
    """渲染收盘全面研判段。"""
    if not rv:
        return ''
    out = []
    _tops = rv.get('tops') or []
    if _tops:
        rows = []
        for t_ in _tops[:10]:
            rows.append(f"""<div style="background:#1f2635;border-left:3px solid {RED};border-radius:8px;padding:8px 11px;margin:5px 0;">
<div style="font-weight:700;color:#fff;">{t_.get('sec','')} <span style="color:{GREY};font-size:12px;">龙头 {t_.get('leader','')}</span></div>
<div style="color:#e9ecef;font-size:12px;margin-top:2px;line-height:1.6;">🧠 上涨逻辑：{t_.get('logic','')}</div>
<div style="color:#a78bfa;font-size:12px;margin-top:2px;">🕳️ 龙头暗线：{t_.get('leader_dark','')}</div></div>""")
        out.append('<div style="margin-top:12px;font-size:15px;font-weight:800;color:' + RED + ';">【TOP10 板块/题材上涨逻辑 & 涨停个股原因暗线】（大模型研判）</div>' + ''.join(rows))
    _tom = rv.get('tomorrow') or []
    if _tom:
        rows = []
        for t_ in _tom[:6]:
            rows.append(f"""<div style="background:#1f2635;border-left:3px solid {TEAL};border-radius:8px;padding:8px 11px;margin:5px 0;">
<div style="font-weight:700;color:#fff;">明日可介入：{t_.get('name','')} <span style="color:{GREY};font-size:12px;">｜{t_.get('pos','')}</span></div>
<div style="color:#e9ecef;font-size:12px;margin-top:2px;line-height:1.6;">🧠 原因：{t_.get('reason','')}</div>
<div style="color:#a78bfa;font-size:12px;margin-top:2px;">🕳️ 暗线：{t_.get('dark','')}</div>
<div style="color:{GOLD};font-size:12px;margin-top:2px;">🎯 买点：{t_.get('buy','待确认')}｜止损：{t_.get('stop','-3%')}</div></div>""")
        out.append('<div style="margin-top:12px;font-size:15px;font-weight:800;color:' + TEAL + ';">【明日可介入个股】（原因+暗线）</div>' + ''.join(rows))
    _main = rv.get('mainline_next') or []
    _spark = rv.get('spark_next') or []
    _start = rv.get('main_start') or []
    if _main or _spark or _start:
        _sent = []
        if _main:
            _sent.append('明天资金最可能回流的是 ' + '、'.join(str(x) for x in _main[:3]) + ' 这条线')
        if _spark:
            _sent.append('还在酝酿、没走出来的方向是 ' + '、'.join(str(x) for x in _spark[:3]))
        if _start:
            _sent.append('已经够格起主升的是 ' + '、'.join(str(x) for x in _start[:3]))
        else:
            _sent.append('眼下没有一只票满足主升启动条件，谁硬做谁接最后一棒')
        out.append('<div style="margin-top:12px;font-size:15px;font-weight:800;color:#ff922b;">【明天怎么做】</div>'
                   + '<div style="background:#232a3a;border-left:4px solid #ff922b;border-radius:10px;padding:10px 12px;font-size:13px;line-height:1.8;color:#e2e8f0;">'
                   + '；'.join(_sent) + '。</div>')
    return ''.join(out)


def _resonance_verdict(res):
    """真假共振鉴别（模型层，reson_b3）：对当日最高分板块输资金流/龙头封单/跟风票表现给模型判真伪。
    失败返回 None → 默认按规则分走，流程不断。"""
    if not res or not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return None
    try:
        sector = res.get('sector') or ''
        f = res.get('factors') or {}
        det = res.get('detail') or {}
        r1t = (f.get('R1') or {}).get('tag', '?') if f else '?'
        r2t = (f.get('R2') or {}).get('tag', '?') if f else '?'
        r3t = (f.get('R3') or {}).get('tag', '?') if f else '?'
        r4t = (f.get('R4') or {}).get('tag', '?') if f else '?'
        r5t = (f.get('R5') or {}).get('tag', '?') if f else '?'
        payload = ('板块「' + sector + '」五重共振：总分' + str(res.get('score')) + '档位' + str(res.get('grade'))
                   + '，资金重' + str(r1t) + ' 龙头重' + str(r2t) + ' 结构重' + str(r3t)
                   + ' 情绪重' + str(r4t) + ' 时间重' + str(r5t) + '；涨停' + str(det.get('lu'))
                   + '家炸板' + str(det.get('zb')) + '家，昨日涨停' + str(det.get('prev_lu'))
                   + '家，板块均量比' + str(det.get('avg_lb')) + '均涨幅' + str(det.get('avg_pct'))
                   + '%，题材发酵' + str(det.get('seen_count')) + '天。请判断这是真共振还是假共振，只输出JSON：')
        payload += '{"板块":"' + sector + '","判定":"真共振|假共振","证据":"资金早盘进场非拉尾盘/封单午后衰减等具体证据","瓦解信号":"明天若XX则共振失效"}'
        txt = ask_deepseek(payload, purpose='resonance_verdict')
        if not txt:
            return None
        t = txt.strip()
        if t.startswith('```'):
            t = re.sub(r'^```[a-zA-Z]*\n?|\n?```$', '', t)
        j = json.loads(t)
        if j and j.get('板块') and j.get('判定') in ('真共振', '假共振'):
            return j
        return None
    except Exception:
        return None

def build_eod():
    idx = get_indices()
    d = get_pools()
    b, r, avg, zbr = sentiment(idx, d)
    mscore, mlabel, mwhy = market_score(idx, d)
    fin, fout = None, None
    try:
        fin, fout = _money_flow_top(5)
    except Exception:
        pass
    mem = load_memory()
    days = sorted(mem.keys(), reverse=True)
    prev_sec = set()
    for pd in days[1:3]:
        prev_sec |= set(mem.get(pd, {}).keys())

    # 1. 市场状态
    mc = RED if mlabel == '主线持续' else (GREEN if mlabel == '情绪退潮' else GOLD)
    bits = '｜'.join(f"<span style='color:{_c(x['pct'])}'>{x['name']}{x['pct']:+.1f}%</span>" for x in idx)
    sec1 = f"""<div style="background:#232a3a;border-radius:10px;padding:11px 13px;border-left:4px solid {mc};">
<div style="font-size:15px;font-weight:800;color:{mc};">【市场状态】{mlabel} · {mscore}/100</div>
<div style="color:#ced4da;font-size:13px;margin-top:5px;">{mwhy}</div>
<div style="color:#ced4da;font-size:13px;margin-top:5px;">{bits}</div>
<div style="color:{GREY};font-size:12px;margin-top:4px;">涨停{d['lu']}｜炸板{d['zb']}｜跌停{d['dt']}｜炸板率{zbr*100:.0f}%｜最高{d['max_lbc']}板</div></div>"""

    # 2. 今日主线/强势题材（评分排序；加厚：龙头封板时间 + 跟风未涨停票 + 大白话）
    scored = []
    for n, s in d['tops'][:10]:
        sc, lv = theme_score(n, s, n in prev_sec)
        old_leaders = []
        for pd in days[:3]:
            if n in mem.get(pd, {}):
                old_leaders = mem[pd][n]['leaders']
                break
        scored.append((n, s, sc, lv, old_leaders))
    scored.sort(key=lambda x: -x[2])
    zt_codes = set()
    for _sec, sts in d['sectors'].items():
        for st in sts:
            zt_codes.add(st.get('c'))
    _lqmap = {}
    try:
        _lqmap = _limitup_quality(d)
    except Exception:
        _lqmap = {}
    _sec2_map = _sec2_deep(scored)
    sec2_rows = ''
    for n, s, sc, lv, old_leaders in scored:
        leader = sorted(s, key=lambda x: x.get('fbt') or 0)[0]
        _lq_txt = _lpq_line(_lqmap.get(str(leader.get('c') or '')) or {})
        # 跟风未涨停票：涨幅榜中该题材、未涨停、量比≥1.5 的前2只
        fg = []
        try:
            for g in _clist_gainers():
                if g['code'] in zt_codes:
                    continue
                ind = re.sub(r'[行业板块概念\s]+', '', g.get('industry') or '') or '其他'
                if ind == n and g['lb'] >= 1.5:
                    fg.append(g['name'])
                if len(fg) >= 2:
                    break
        except Exception:
            pass
        fg_txt = '、'.join(fg) if fg else ''
        _dp2 = _sec2_map.get(n)
        _llm2 = ''
        if _dp2 and _dp2.get('why'):
            _llm2 = (f'<div style="color:#a78bfa;font-size:12px;margin-top:3px;">🧠 逻辑：{_dp2.get("logic", "")}</div>'
                     f'<div style="color:#e9ecef;font-size:12px;margin-top:2px;">👉 大白话：{_dp2.get("why", "")}</div>'
                     + (f'<div style="color:{GOLD};font-size:12px;margin-top:2px;">🎚️ 阶段：{_dp2.get("stage", "")} ｜ 结论：{_dp2.get("verdict", "")}</div>' if _dp2.get('stage') or _dp2.get('verdict') else '')
                     + (f'<div style="color:{TEAL};font-size:12px;margin-top:2px;">🎯 明天：{_dp2.get("act", "")}</div>' if _dp2.get('act') else '')
                     + (f'<div style="color:#a78bfa;font-size:12px;margin-top:2px;">🕳️ 暗线：{_dp2.get("dark", "")}</div>' if _dp2.get('dark') else ''))
        if _dp2 and _dp2.get('why'):
            _plain_html = _llm2
        else:
            _plain_html = ''
        sec2_rows += f"""<div style="background:#1f2635;border-left:4px solid {GOLD if lv=='强' else GREY};border-radius:10px;padding:10px 12px;margin:7px 0;">
<div style="font-weight:700;color:{GOLD};">{n} <span style="color:{RED};">{len(s)}涨停</span> <span style="color:{TEAL};">{sc}/10·{lv}</span></div>
<div style="color:#ced4da;font-size:13px;margin-top:4px;">👑 龙头：{leader.get('n')} {_hhmm(leader.get('fbt'))}首封</div>
{('<div style="color:#8bd3c7;font-size:12px;margin-top:2px;">💧 封板质量：' + _lq_txt + '</div>') if _lq_txt else ''}
{f'<div style="color:{TEAL};font-size:12px;margin-top:3px;">📌 历史强势股：{"、".join(old_leaders)}</div>' if old_leaders else ''}
{('<div style="color:' + TEAL + ';font-size:12px;margin-top:3px;">🔎 可跟踪跟风：' + fg_txt + '</div>') if fg_txt else ''}
{_plain_html}</div>"""
    sec2 = f'<div style="margin-top:12px;font-size:15px;font-weight:800;color:#ff922b;">【今日主线 & 强势题材】（TOP10 上涨逻辑）</div>{sec2_rows}'
    if not sec2_rows:
        sec2 += '<div style="color:' + GREY + ';font-size:13px;margin-top:4px;">今日强势题材数据未取得（涨停池缺源），明日以竞价/开盘验证为准</div>'
    sec2 += ''.join(f'<div style="margin:3px 0;font-size:12px;color:{GREY};">{life_badge(n, d, mem, days)} {n}</div>'
                    for n, s in d['tops'][:3] if len(s) >= 1)
    # 工单3：主线体检（梯队健康分）。数据缺就标"数据未接入"，不编分。
    sec2b = build_theme_health(d)
    # 工单7：当日情绪周期算完落盘，供次日竞价卡顶部展示
    _sentiment_refresh()

    # 3. 可跟踪池（明日操作，禁止已涨停：只保留 未涨停量能放大+题材共振 / 大涨未封板分时强势）
    tpool = _track_pool(d)
    sec4_rows = ''
    for s, kind in tpool:
        deep = _deep_logic(s, re.sub(r'[行业板块概念\s]+', '', s.get('industry') or '') or '其他',
                           None, eod_kind=kind)
        deep_html = deep.replace('\n', '<br>')
        sec4_rows += f"""<div style="background:#1f2635;border-left:3px solid {TEAL};border-radius:8px;padding:9px 11px;margin:6px 0;">
<b style="color:#fff;">{s['name']}</b> <span style="color:{GREY};font-size:12px;">{s['code']}</span>
<span style="color:{_c(s['pct'])};font-weight:700;">收盘{s['pct']:+.1f}%</span>
<span style="color:{GREY};font-size:12px;">｜量比{s['lb']:.1f} ｜ 题材：{s['industry']}（{kind}）</span>
<div style="color:#ced4da;font-size:12px;line-height:1.7;margin-top:4px;">{deep_html}</div></div>"""
    if not sec4_rows:
        sec4_rows = ''
    sec4 = f'<div style="margin-top:12px;font-size:15px;font-weight:800;color:{TEAL};">【可跟踪池】（明日操作，不含已涨停）</div>{sec4_rows}'
    # 兼容变量：后续 DS payload / 信号记录继续用 pool（新语义：可跟踪池）
    pool = [{'n': s['name'], 'code': s['code'], 'sec': s.get('industry', ''),
             'act': '低吸' if kind == '低吸候选' else '冲高做T',
             'buy': f'{round(max(0.0, s["price"]*0.99),2)}~{round(max(0.0, s["price"]*1.01),2)}',
             'stop': f'{round(max(0.0, s["price"]*0.99)*0.97,2)}（-3%）', 'pos': '1-2成',
             'score': round(s.get('lb', 1), 1)} for s, kind in tpool]

    # 4.5 持仓个股诊断（新增）
    hold_html, contagion_sec = _hold_diag(d, mlabel)
    if HOLDINGS and hold_html:
        sec45 = f'<div style="margin-top:12px;font-size:15px;font-weight:800;color:#ff922b;">【持仓个股诊断】</div>{hold_html}'
        if contagion_sec:
            sec45 += f'<div style="margin-top:6px;background:#2a1f22;border-left:4px solid {RED};border-radius:8px;padding:8px 10px;color:{RED};font-size:13px;">⚠️ 板块传染风险：持仓中 {"、".join(contagion_sec)} 板块≥2只持仓且今日退潮/炸板集中，建议统一减仓</div>'
    else:
        sec45 = ''

    # 5. 风险提示
    cont = contagion(d)
    risk = []
    if mlabel in ('快速轮动', '情绪退潮'):
        risk.append(f'市场状态={mlabel}，仓位≤5%，止损收紧')
    if cont:
        risk.append('板块传染：' + '；'.join(cont))
    sec5 = f'<div style="margin-top:12px;background:#2a1f22;border-left:4px solid {RED};border-radius:8px;padding:9px 11px;color:{RED};font-size:13px;">【风险提示】{"<br>".join(risk) or "暂无明显风险"}</div>'

    # 6. 记忆更新 + 信号复盘
    today_sec = write_today_memory(d)
    backfill_signals()
    record_signals([{'code': p['code'] if 'code' in p else None, 'n': p['n']} for p in pool])
    try:
        write_judgment({'date': datetime.now().strftime('%Y-%m-%d'),
                        'emotion': b, 'label': mlabel, 'score': mscore,
                        'tops': [n for n, _ in d['tops'][:3]],
                        'pool': [p['n'] for p in pool[:3]],
                        'pos': _pos_advice(b),
                        'risk': '；'.join(risk[:2]) or '',
                        'lu': d['lu'], 'zb': d['zb'], 'dt': d['dt'], 'max_lbc': d['max_lbc']})
    except Exception:
        pass
    sec6 = f'<div style="margin-top:10px;color:{GREY};font-size:12px;">【题材记忆】今日记录{len(today_sec)}个强势题材：{"、".join(list(today_sec.keys())[:6])}</div>'
    sec7 = f'<div style="margin-top:8px;font-size:13px;">{signals_review_html()}{_signal_review_llm()}</div>'

    # DeepSeek 大白话复盘（经统一预算网关；预算熔断/失败时自动不出本段）
    hold_diag_plain = []
    try:
        for h in HOLDINGS:
            q = _qt(h['code'])
            if q:
                hold_diag_plain.append([h['name'], round(q['pct'], 2), h['sector']])
    except Exception:
        pass
    hs, hl, ha, _ = mainline_health(idx, d, fin, fout)
    jc = judgment_context()
    ds_payload = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'judgment': jc,
        'market': {'label': mlabel, 'score': mscore, 'why': mwhy},
        'indices': [[x['name'], round(x['pct'], 2)] for x in idx],
        'pools': {'lu': d['lu'], 'zb': d['zb'], 'dt': d['dt']},
        'tops': [[n, len(s), sc] for n, s, sc, lv, _ in scored[:6]],
        'pool': [[p['n'], p['act']] for p in pool[:6]],
        'holdings_diag': hold_diag_plain,
        'health': [hs, hl, ha],
        'format': (_TRADER_RULES + '\n'
                   + (('昨日判断（供对照，别重复昨天的错）：\n{judgment}\n' if jc else ''))
                   + '请根据以下收盘数据做大白话复盘 + 明日预案：\n'
                   '市场状态（见 market 字段）：{market}\n'
                   '今日主线 TOP8：{tops}\n'
                   '可跟踪池：{pool}\n'
                   '主线健康度：' + str(hs) + '/100（' + hl + '，' + ha + '）\n'
                   '持仓个股诊断（已逐只给出持有/减仓/止损建议，见 holdings_diag）：\n{holdings_diag}\n'
                   '请严格按以下格式输出（全大白话，禁模板句）：\n'
                   '【今日复盘】三句话（情绪 + 主线阶段「启动|接力|分歧|退潮」 + 资金）\n'
                   '【持仓最终建议】（复述并强化已有诊断，同板块传染标红）\n'
                   '【明日开盘预案】条件-动作表：\n'
                   '- 高开≥2%：…\n'
                   '- 低开≥1.5%：…\n'
                   '- 平开震荡：…\n'
                   '- 主线高开但炸板率升：…\n'
                   '【明日板块优先级】一句话（哪个 + 为什么 + 怎么跟）——提到板块内代表股/龙头时，必须执行「股票深挖铁律」：本质（一句话大白话）+暗线业务（具体产品+阶段+真实贡献，写不出写「未见明确暗线业务」）+今天为什么强+「底仓逻辑明天还在不在」（核心判断，必须写）+明天破灭点+动作，单票≤80字；没有硬逻辑写「逻辑不硬，不碰」。\n'
                   '【核心风险】一句话'
                   + ('【昨日复盘】对照今日实际，哪些对了/错了（最多3条）' if jc else '')
                   + '【今日判断记录】必须可机读，按下面五词条各一句话（供写入 judgment.json）：\n'
                   '情绪：…\n'
                   '主线：…\n'
                   '推荐：…\n'
                   '风险：…\n'
                   '明日预案：…\n'
                   '【仓位仪表盘】明日开盘前建议总仓位一档（空仓/1成试探/2成/半仓）+ 一句理由' + '\n【自检】输出前自查：是否违反高位连板别追？是否缺止损？是否有万能句（值得关注/建议留意/具备投资价值）？是否与仓位仪表盘矛盾？有问题降级改写；无问题结尾写「自检通过」。'),
    }
    ds_md = ask_deepseek(ds_payload)
    if ds_md:
        try:
            _jv2 = _parse_judgment_v2_from_md(ds_md)
            if _jv2:
                write_judgment_v2({'date': datetime.now().strftime('%Y-%m-%d'), **_jv2})
        except Exception:
            pass
        _save_gauge_from_md(ds_md, source='eod')
    sec_ds = f'<div style="margin-top:12px;border-left:4px solid #a78bfa;border-radius:8px;padding:10px 12px;background:#232a3a;font-size:13px;line-height:1.8;color:#e2e8f0;">{md2html(ds_md)}</div>' if ds_md else ''
    if not ds_md:
        sec_ds = ('<div style="margin-top:12px;border-left:4px solid #a78bfa;border-radius:8px;padding:10px 12px;background:#232a3a;'
                  'font-size:13px;color:#9aa4b8;">🧠 大白话复盘生成失败（模型通道不可用），以上方结构化数据为准</div>')

    # 全面研判（11-05 指令⑤）：TOP10 上涨逻辑+涨停个股原因暗线+明日可介入+主线候选/下次爆发/主升启动
    try:
        _rv = _eod_review_ds(d, idx, scored, tpool)
    except Exception as _e:
        print('[eod] 全面研判异常:', _e)
        _rv = {}
    sec8 = _eod_review_html(_rv, scored)

    sec_sell = f"""<div style="margin-top:12px;border-left:4px solid {GREEN};border-radius:8px;padding:9px 11px;background:#1c2830;font-size:13px;color:#e2e8f0;">
<div style="font-weight:800;color:{GREEN};">📋 明日开盘预案</div>
高开≥2%且量能配合 → 先卖一半，剩一半看封板；高开&lt;2%或平开 → 看前15分钟量能和分时结构；低开&gt;1.5% → 竞价直接减仓或清仓。</div>"""

    _st_line = signal_stats()[0] or ''
    try:
        _al0 = load_alerts()
    except Exception:
        _al0 = {'fired': []}
    _miss = miss_review(d, _al0)
    _miss_block = (f'<div style="margin-top:12px;font-size:15px;font-weight:800;color:{GREY};">🔍 今日错过 TOP5（仅规则优化线索，不构成买卖建议）</div>{_miss}'
                   if _miss else '')
    _overall = (f'<div style="margin-top:4px;padding:8px 10px;background:#1c2830;border-left:4px solid {mc};'
                f'border-radius:8px;font-size:13px;color:#e9ecef;">🧭 今天整体：{b}，涨停{d["lu"]}家炸板{d["zb"]}家，'
                f'{mlabel}（{mscore}分）。明天倾向：'
                f'{"偏多可积极" if b=="偏多" else "偏空先防守" if b=="偏空" else "震荡对待"}。</div>')
    try:
        _pool_today = _auction_pool_stats(_bj_now().strftime('%Y-%m-%d'))
    except Exception:
        _pool_today = ''
    # —— 共振账本（reson_b3）：记今日判定 + 模型鉴别 + 昨日对账，失败不阻断 ——
    _reson_sec = ''
    try:
        _r = _resonance()
        if _r:
            _today = _bj_now().strftime('%Y-%m-%d')
            _led = _reson_ledger()
            _rec = (_led.get('records') or {}).get(_today) or {}
            _verdict = None
            if not _rec.get('verdict'):
                # 模型层真假鉴别（每天 1 次，失败走规则分）
                try:
                    _verdict = _resonance_verdict(_r)
                except Exception:
                    _verdict = None
            _rec2 = dict(_r)
            if _verdict:
                _rec2['verdict'] = _verdict
            _reson_record(_rec2)
            _led2 = _reson_ledger()
            _acc, _alert = _reson_reconcile(_led2, _today, cur=_r)
            _rb = _reson_banner_html(_r)
            _vd_txt = ''
            if _verdict:
                _vd_txt = ('<br>🔍 模型鉴别：<b>' + str(_verdict.get('判定')) + '</b>（证据：' + str(_verdict.get('证据'))
                           + '；瓦解：' + str(_verdict.get('瓦解信号')) + '）')
            _acc_html = ('<br>📒 对账：' + _acc) if _acc else ''
            _al_html = ('<div style="margin-top:6px;color:#ff6b6b;">' + _alert + '</div>') if _alert else ''
            _reson_sec = ''  # 共振账本只做内部记账/对账，不上面（2026-11-07 用户指令：共振当因子算、不显示）
    except Exception:
        _reson_sec = ''

    inner = (_overall + health_bar(idx, d, fin, fout) + sec1 + sec2 + sec8 + sec2b + sec4 + sec45 + sec5 + sec_ds + sec_sell + sec7
             + build_events('eod') + sec6 + _pool_today
             + pos_cap_line(sentiment(idx, d)[0], hl)
             + (f'<div style="margin-top:6px;font-size:12px;color:{GREY};">{_st_line}</div>' if _st_line else '')
             + _factor_board_top(d) + _reson_sec + _miss_block)
    return _wrap(inner, '🌆', '收盘复盘')


BUILDERS = {'pre': build_pre, 'auction': build_auction, 'noon': build_noon,
            'eod': build_eod, 'hourly': build_hourly}
WATCH_SLOT = 'watch'
BUILDERS['confirm'] = build_confirm
BUILDERS['cycle'] = build_cycle


def _in_session(bj):
    """盘中时段（北京时间）：09:30-11:30 或 13:00-14:50。14:50 后强制停止，避免收盘前无效推送。"""
    hm = bj.strftime('%H:%M')
    return ('09:30' <= hm <= '11:30') or ('13:00' <= hm <= '14:50')


# ============ 模块4/5：回踩确认 + 持仓风控雷达 ============
def _load_holdings():
    """data/holdings.json 可选：有文件才启用持仓雷达，没有/损坏 → None 完全跳过。
    格式：[{'name','code','cost','qty','sector'}]"""
    try:
        with open('data/holdings.json', 'r', encoding='utf-8') as f:
            arr = json.load(f)
        if isinstance(arr, list) and arr:
            return arr
    except Exception:
        pass
    return None


def holdings_radar(al, secs=None):
    """持仓实时风控雷达（模块5）：盈亏≤-2.5%接近止损 / ≤-3.0%触发止损(无条件) / 跌破分时均线 / 同题材≥2传染。
    仅在本次推送板块与持仓板块有关联（secs 命中持仓 sector）时才输出持仓内容；无关联推送一律不带（用户要求）。
    每只每日每种触发类型只推1次；无 data/holdings.json 直接跳过。返回 HTML 片段。"""
    hs = _load_holdings()
    if not hs:
        return ''
    if secs:
        _secs = {str(s).strip() for s in secs if s}
        _hsectors = {str(h.get('sector', '')).strip() for h in hs if h.get('sector')}
        _hit = False
        for _a in _secs:
            for _b in _hsectors:
                if _a and _b and (_a == _b or _a in _b or _b in _a):
                    _hit = True
                    break
            if _hit:
                break
        if not _hit:
            print('[hold] 本次推送板块与持仓无关联，跳过持仓预警')
            return ''
    today = _bj_now().strftime('%Y-%m-%d')
    done = set(al.get('pos_warn', {}).get(today, []))
    cards, new_keys = [], []
    sec_loss = defaultdict(list)
    for h in hs:
        code, cost = h.get('code', ''), float(h.get('cost') or 0)
        if not code or not cost:
            continue
        sym = ('sh' if code.startswith('6') else 'sz') + code
        try:
            q = _qt(sym)
            if not q or not q['price']:
                continue
        except Exception:
            continue
        price, avg = q['price'], q.get('avg') or 0
        pnl = (price / cost - 1) * 100
        if pnl < 0:
            sec_loss[h.get('sector', '')].append(h.get('name', code))
        trigs = []
        if pnl <= -3.0:
            trigs.append(('止损', '触发止损(-3.0%)，无条件执行', '立即止损离场'))
        elif pnl <= -2.5:
            trigs.append(('止损', '接近止损(-2.5%)，减仓观察', '减仓/严格止损'))
        if avg and price < avg and pnl < 0:
            trigs.append(('均价', '跌破分时均线（腾讯f71均价），弱势', '减仓或等收复'))
        for typ, txt, advice in trigs:
            k = f"{h.get('name')}|{typ}"
            if k in done:
                continue
            cards.append(f"""<div style="background:#3a1c1c;border:2px solid {RED};border-radius:12px;padding:10px 14px;margin:10px 0;">
<div style="font-size:15px;font-weight:900;color:{RED};">⚠️ 持仓预警 · {h.get('name')}（{code}）</div>
<div style="color:#fff;font-size:13px;margin-top:5px;">盈亏 <b style="color:{RED}">{pnl:+.2f}%</b>（成本{cost:.2f}/现价{price:.2f}）｜{txt}</div>
<div style="color:{TEAL};font-size:12px;margin-top:4px;">建议：{advice}</div></div>""")
            new_keys.append(k)
    for sec, names in sec_loss.items():
        if len(names) >= 2:
            k = f'传染|{sec}'
            if k in done:
                continue
            cards.append(f"""<div style="background:#3a1c1c;border:2px solid {RED};border-radius:12px;padding:10px 14px;margin:10px 0;">
<div style="font-size:15px;font-weight:900;color:{RED};">⚠️ 板块传染风险 · {sec}</div>
<div style="color:#e9ecef;font-size:13px;margin-top:5px;">持仓 {'、'.join(names)} 同时走弱，建议整体减仓该方向</div></div>""")
            new_keys.append(k)
    if new_keys:
        al.setdefault('pos_warn', {})[today] = list(done | set(new_keys))
        save_alerts(al)
    return ''.join(cards)


_PULLBACK_DS_SYS = ('你是一线游资，写「回踩确认可加仓」提示。用户今日早盘收到某票买入信号、现在该票回踩缩量企稳（现价≤均价×1.002、量比≤1.2、回撤不破买入区间下沿），你要用大白话讲清楚为什么现在可以加仓（核心是主力是否还在控盘：缩量+托单），以及加仓后的风险与止损。只基于输入数据说话，禁编价格；禁模板句；结论先行；坏消息不软化。只输出 JSON：{"logic":"为什么现在可加仓(≥20字,大白话,必须结合具体量价与主力控盘证据)","risk":"加仓后的风险与止损(≥12字,给具体破位条件)"}，不要其他文字。')


def _pullback_ds(nm, code, price, avg, lb, trigger, buy_low):
    """回踩确认可加仓 LLM 大白话（失败 '' → 调用方回退规则文案）。"""
    if not MODELSCOPE_KEY:
        return ''
    try:
        fmt = ('股票' + nm + '(' + code + ') 现价' + ('%.2f' % price) + ' 当日均价' + ('%.2f' % avg)
               + ' 量比' + ('%.1f' % lb) + ' 较早盘触发价回撤' + ('%.2f' % ((price / trigger - 1) * 100)) + '%'
               + ' 买入区间下沿' + ('%.2f' % buy_low)
               + '\n回踩确认可加仓提示，只输出 JSON：{"logic":"为什么现在可加仓(≥20字,大白话,结合量价与板块背景,禁模板句)","risk":"加仓后风险与止损(≥12字,具体破位条件)"}，不要其他文字')
        t = ask_deepseek({'task': 'pullback_confirm', 'stock': {'name': nm, 'code': code}, 'format': fmt},
                         purpose='pullback', system_text=_PULLBACK_DS_SYS)
        if not t:
            return ''
        _j = json.loads(t)
        _l = str(_j.get('logic') or '').strip()
        if not _l:
            return ''
        _r = str(_j.get('risk') or '').strip()
        _h = ('<div style="background:#1c2830;border:2px solid ' + TEAL + ';border-radius:12px;padding:10px 14px;margin:10px 0;">'
              '<div style="font-size:15px;font-weight:900;color:' + TEAL + ';">🔁 回踩确认可加仓 · ' + nm + '（' + code + '）</div>'
              '<div style="color:#e9ecef;font-size:13px;margin-top:5px;">现价 ' + ('%.2f' % price) + ' ≤ 均价×1.002，量比 ' + ('%.1f' % lb) + '≤1.2，回踩 ' + ('%.2f' % ((price / trigger - 1) * 100)) + '% 不破买入区间下沿 ' + ('%.2f' % buy_low) + '</div>'
              '<div style="color:' + TEAL + ';font-size:12px;margin-top:4px;">🧠 加仓逻辑：' + _l + '</div>'
              + (('<div style="color:' + RED + ';font-size:12px;margin-top:3px;">⚠️ 风险：' + _r + '</div>') if _r else '')
              + '<div style="color:' + TEAL + ';font-size:12px;margin-top:4px;">操作：原仓位 +1成，止损不变（买入价-3%）</div></div>')
        return _h
    except Exception:
        return ''


def pullback_check(al, d, fired):
    """回踩确认二次提醒（模块4）：今日已推过 启动埋伏/逼近涨停 的票，
    现价≤当日均价×1.002 且 量比≤1.2 且 较触发价回撤≥1.5% 且 仍≥买入区间下沿
    → 补发「回踩确认可加仓」（仓位+1成，止损不变）。同股当日最多1次。
    触发价/买入下沿取自 al['sig_ctx']（build_watch 推送时记录）；查不到则跳过，不伪造。"""
    if not fired:
        return ''
    today = _bj_now().strftime('%Y-%m-%d')
    done = set(al.get('pullback', {}).get(today, []))
    ctx = al.get('sig_ctx', {})
    code_map = {}
    for stocks in d['sectors'].values():
        for st in stocks:
            code_map[st.get('n')] = st.get('c')
    cards, new_keys = [], []
    for k in list(fired):
        nm, typ = k.split('|', 1) if '|' in k else (k, '')
        if typ not in ('启动埋伏', '逼近涨停'):
            continue
        code = code_map.get(nm)
        c = ctx.get(k)
        if not code or not c:
            continue
        kk = f'{nm}|回踩'
        if kk in done:
            continue
        sym = ('sh' if code.startswith('6') else 'sz') + code
        try:
            q = _qt(sym)
            if not q or not q['price'] or not q.get('avg'):
                continue
        except Exception:
            continue
        price, avg, lb = q['price'], q['avg'], q.get('lb', 0)
        trigger = c.get('trigger') or 0
        buy_low = c.get('buy_low') or (trigger * 0.995)
        if not trigger:
            continue
        if price <= avg * 1.002 and lb <= 1.2 and price <= trigger * 0.985 and price >= buy_low:
            _pb_llm = _pullback_ds(nm, code, price, avg, lb, trigger, buy_low)
            if not _pb_llm:
                # 加仓判读必须由大模型给；模型未返回则不推规则版加仓卡
                print(f'[pullback] {nm} 模型未返回，不推规则版加仓卡')
                continue
            cards.append(_pb_llm)
            new_keys.append(kk)
    if new_keys:
        al.setdefault('pullback', {})[today] = list(done | set(new_keys))
        save_alerts(al)
    return ''.join(cards)


# ============ 模块7：信号胜率统计（signal_log.jsonl） ============
def _log_signals(slot, sigs):
    """追加信号记录到 data/signal_log.jsonl（date/slot/type/code/name），写回仓库失败降级当日内存+标注。
    sigs: [{'type','code','name'}, ...]"""
    if not sigs:
        return
    try:
        os.makedirs('data', exist_ok=True)  # 云端仓库无 data/ 目录，先建目录再写（2026-10-20 修复）
        with open('data/signal_log.jsonl', 'a', encoding='utf-8') as f:
            for s in sigs:
                f.write(json.dumps({'date': _bj_now().strftime('%Y-%m-%d'), 'slot': slot,
                                    'type': s.get('type', ''), 'code': s.get('code', ''),
                                    'name': s.get('name', ''), 'next_open': '', 'next_close': ''},
                                   ensure_ascii=False) + '\n')
        try:
            _git_commit_push('data/signal_log.jsonl', 'chore: signal_log 追加信号记录')
        except Exception:
            print('[signal_log] 写回仓库失败，降级当日内存（不伪造）')
    except Exception:
        print('[signal_log] 本地写入失败')


def signal_stats():
    """读 jsonl → 用今日 K线回填昨日记录的 next_open/next_close → 统计近5/10/20日各 slot 次日胜率与平均收益。
    绝不伪造：只有 next_open/next_close 双非空才计样本。返回 (汇总行或None, 今日)。"""
    path = 'data/signal_log.jsonl'
    recs = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    recs.append(json.loads(line))
    except Exception:
        return None, None
    today = _bj_now().strftime('%Y-%m-%d')
    changed = False
    for r in recs:
        if r.get('date') and r['date'] < today and not r.get('next_open'):
            sym = ('sh' if r.get('code', '').startswith('6') else 'sz') + r.get('code', '')
            try:
                arr = get_klines(sym, 2)
                if len(arr) >= 2:
                    r['next_open'], r['next_close'] = float(arr[-1][1]), float(arr[-1][2])
                    changed = True
            except Exception:
                pass
    if changed:
        try:
            os.makedirs('data', exist_ok=True)  # 回填写回同样需要 data/ 目录（2026-10-20 修复）
            with open(path, 'w', encoding='utf-8') as f:
                for r in recs:
                    f.write(json.dumps(r, ensure_ascii=False) + '\n')
            try:
                _git_commit_push(path, 'chore: signal_log 次日回填')
            except Exception:
                print('[signal_log] 回填写回仓库失败，降级当日内存')
        except Exception:
            pass
    # 近5/10/20 信号日窗口
    days = sorted({r['date'] for r in recs if r.get('date') and r['date'] < today}, reverse=True)
    parts = []
    for n in (5, 10, 20):
        win = set(days[:n])
        by_slot = defaultdict(lambda: [0, 0, 0.0])  # slot -> [win, total, sum_ret]
        for r in recs:
            if r.get('date') not in win or not r.get('next_open') or not r.get('next_close'):
                continue
            o, c = float(r['next_open']), float(r['next_close'])
            if not o:
                continue
            st = by_slot[r.get('slot', '?')]
            st[1] += 1
            st[2] += (c / o - 1) * 100
            if c > o:
                st[0] += 1
        if by_slot:
            s = '；'.join(f"{k} {v[0]}/{v[1]}胜 {v[2] / v[1]:+.2f}%" for k, v in sorted(by_slot.items()))
            parts.append(f'近{n}日 {s}')
    if not parts:
        return None, today
    return ('📈 信号次日胜率（signal_log 实测，次日开→收）：' + ' ｜ '.join(parts)), today


# ============ 模块7B：因子信号闭环（data/signal_log.csv） ============
_SIG_CSV = 'data/signal_log.csv'
_SIG_HEAD = ['date', 'slot', 'code', 'name', 'push_price', 'jq', 'lj', 'zj', 'tc', 'dl',
             'total', 'combined', 'vetoed', 'close_t1', 'close_t5', 'ret5', 'win']


def _sig_fmt(v, nd=1):
    """数值格式化；None/''/无法转换一律返回空串，绝不填 0 冒充真实数据。"""
    if v is None or v == '':
        return ''
    try:
        return f'{float(v):.{nd}f}'
    except Exception:
        return ''


def _factor_signal_write(slot, rows):
    """推送时写前半段：date/slot/code/name/push_price/各因子分/total/combined/vetoed。
    rows: [{'code','name','price','jq','lj','zj','tc','dl','total','combined','vetoed'}]
    同 date+slot+code 已存在则跳过（同槽重跑不重复记）。写回仓库失败只告警，不阻断推送。
    """
    if not rows:
        return 0
    try:
        os.makedirs('data', exist_ok=True)
        today = _bj_now().strftime('%Y-%m-%d')
        exists = os.path.exists(_SIG_CSV)
        done = set()
        if exists:
            try:
                with open(_SIG_CSV, 'r', encoding='utf-8') as f:
                    for line in f:
                        p = line.rstrip('\n').split(',')
                        if len(p) >= 3 and p[0] == today and p[1] == slot:
                            done.add(p[2])
            except Exception:
                pass
        new_lines = []
        for r in rows:
            code = str(r.get('code') or '').strip()
            if not code or code in done:
                continue
            done.add(code)
            new_lines.append(','.join([
                today, slot, code, str(r.get('name') or '').replace(',', ' ').replace('\n', ' '),
                _sig_fmt(r.get('price'), 2), _sig_fmt(r.get('jq'), 1), _sig_fmt(r.get('lj'), 1),
                _sig_fmt(r.get('zj'), 1), _sig_fmt(r.get('tc'), 1), _sig_fmt(r.get('dl'), 1),
                _sig_fmt(r.get('total'), 1), _sig_fmt(r.get('combined'), 1),
                '1' if r.get('vetoed') else '0', '', '', '', '',
            ]))
        if not new_lines:
            return 0
        with open(_SIG_CSV, 'a', encoding='utf-8') as f:
            if not exists:
                f.write(','.join(_SIG_HEAD) + '\n')
            for ln in new_lines:
                f.write(ln + '\n')
        print(f'[sigcsv] {slot} 写入 {len(new_lines)} 条 → {_SIG_CSV}')
        try:
            _git_commit_push(_SIG_CSV, f'chore: signal_log 追加 {slot} {len(new_lines)} 条')
        except Exception:
            print('[sigcsv] 写回仓库失败（记录已落盘，随下次提交带出）')
        return len(new_lines)
    except Exception as e:
        print(f'[sigcsv] 写入异常 {e}')
        return 0


def _sig_csv_stats():
    """CSV 账本体检（只读）：回填进度，供 11-09 起 T+1 落笔监控。"""
    try:
        with open(_SIG_CSV, 'r', encoding='utf-8') as f:
            raw = f.read().rstrip('\n')
    except Exception:
        return None
    lines = raw.split('\n') if raw else []
    if len(lines) < 2:
        return {'rows': 0, 'dates': [], 't1_filled': 0, 't5_filled': 0, 'first10_t1': 0}
    hdr = lines[0].split(',')
    idx = {n: i for i, n in enumerate(hdr)}
    rows = [ln.split(',') for ln in lines[1:] if ln.strip()]
    dates = sorted({r[idx['date']] for r in rows if len(r) > idx['date']})
    def _filled(name, rows_):
        i = idx.get(name)
        if i is None:
            return 0
        return sum(1 for r in rows_ if len(r) > i and r[i])
    return {'rows': len(rows), 'dates': dates,
            't1_filled': _filled('close_t1', rows),
            't5_filled': _filled('close_t5', rows),
            'first10_t1': _filled('close_t1', rows[:10])}


def _sig_settle_monitor():
    """11-09 起的账本监控点：eod 回填后打印一行体检结果 + 落盘状态并写回仓库。

    验收口径（用户指定）：首批 10 行 close_t1 有值即通过。
    只读账本、只写状态文件，绝不改用例数据。
    """
    st = _sig_csv_stats()
    if st is None:
        print('[sigcsv][monitor] 账本不可读，跳过')
        return
    st['checked_at'] = _bj_now().strftime('%Y-%m-%d %H:%M')
    st['pass_first10'] = st['first10_t1'] > 0
    print('[sigcsv][monitor] rows=%s t1=%s t5=%s first10_t1=%s dates=%s' % (
        st['rows'], st['t1_filled'], st['t5_filled'], st['first10_t1'],
        (','.join(st['dates'][-3:]) if st['dates'] else 'none')))
    print('[sigcsv][monitor] 首批10行T+1回填 %s' % ('PASS' if st['pass_first10'] else 'PENDING'))
    try:
        with open('data/csv_settle_status.json', 'w', encoding='utf-8') as f:
            json.dump(st, f, ensure_ascii=False, indent=2)
        _git_commit_push('data/csv_settle_status.json', 'update csv settle status')
    except Exception as e:
        print('[sigcsv][monitor] 状态落盘失败 %s' % e)


def _factor_signal_settle():
    """T+1 / T+5 回填：按 date 之后的日K回填 close_t1 / close_t5 / ret5 / win。
    口径：close_t1 = 推送次日收盘；close_t5 = 推送后第 5 个交易日收盘；
    ret5 = (close_t5 / push_price - 1) * 100；win = ret5 > 0。
    绝不伪造：K 线不够就留空，不估算。
    """
    try:
        with open(_SIG_CSV, 'r', encoding='utf-8') as f:
            raw = f.read().rstrip('\n')
    except Exception:
        return 0
    lines = raw.split('\n') if raw else []
    if len(lines) < 2:
        return 0
    hdr = lines[0].split(',')
    idx = {n: i for i, n in enumerate(hdr)}
    rows = [ln.split(',') for ln in lines[1:] if ln.strip()]
    changed = 0
    for r in rows:
        if len(r) < len(hdr):
            r += [''] * (len(hdr) - len(r))
        try:
            if r[idx['close_t5']]:
                continue
            code = r[idx['code']]
            if not code:
                continue
            sym = ('sh' if code.startswith('6') else 'sz') + code
            arr = get_klines(sym, 60)
            if not arr:
                continue
            d0 = r[idx['date']]
            after = [k for k in arr if str(k[0])[:10] > d0]
            if not after:
                continue
            if not r[idx['close_t1']]:
                try:
                    r[idx['close_t1']] = f'{float(after[0][2]):.2f}'
                    changed += 1
                except Exception:
                    pass
            if len(after) >= 5:
                try:
                    c5 = float(after[4][2])
                    r[idx['close_t5']] = f'{c5:.2f}'
                    # 基准必须与 close_t5 同口径：日K是前复权序列，push_price 是不复权实时价，
                    # 两者直接相除会把复权差异算成暴涨暴跌（002578 实测 -72.86% 假数据）。
                    # 改用推送日（或之前最近交易日）的复权收盘做基准。
                    base_rows = [k for k in arr if str(k[0])[:10] <= d0]
                    if base_rows:
                        base_c = float(base_rows[-1][2])
                        if base_c > 0:
                            ret = (c5 / base_c - 1) * 100
                            r[idx['ret5']] = f'{ret:.2f}'
                            r[idx['win']] = '1' if ret > 0 else '0'
                    changed += 1
                except Exception:
                    pass
        except Exception:
            continue
    if not changed:
        return 0
    try:
        with open(_SIG_CSV, 'w', encoding='utf-8') as f:
            f.write(','.join(hdr) + '\n')
            for r in rows:
                f.write(','.join(r) + '\n')
        print(f'[sigcsv] 回填 {changed} 处')
        try:
            _git_commit_push(_SIG_CSV, f'chore: signal_log 回填 {changed} 处')
        except Exception:
            print('[sigcsv] 回填写回失败')
    except Exception as e:
        print(f'[sigcsv] 回写异常 {e}')
    return changed


# ============ 模块 7C：周日「因子体检报告」+ 机械调权（第5步） ============
_FW_JSON = 'data/factor_weights.json'
_FW_WIN_HI = 0.60     # 胜率 >60% 视为该因子能打
_FW_WIN_LO = 0.45     # 胜率 <45% 视为该因子不灵
_FW_STEP = 0.05       # 每次调 5 个点
_FW_MIN, _FW_MAX = 0.10, 0.40
_FW_MIN_SAMPLES = 30   # 样本硬门槛：已回填 <30 笔只报「数据不足」，不出胜率、不累计调权
_FW_FACTORS = ('jq', 'lj', 'zj', 'tc', 'dl')
_FW_LABEL = {'jq': '情绪', 'lj': '量价', 'zj': '资金', 'tc': '题材', 'dl': '动量'}


def _fw_load():
    """读权重状态；文件不存在/坏掉都回退引擎默认，绝不阻断。"""
    try:
        with open(_FW_JSON, 'r', encoding='utf-8') as f:
            st = json.load(f)
        return st if isinstance(st, dict) else {}
    except Exception:
        return {}


def _fw_save(st):
    try:
        os.makedirs('data', exist_ok=True)
        with open(_FW_JSON, 'w', encoding='utf-8') as f:
            json.dump(st, f, ensure_ascii=False, indent=2)
        _git_commit_push(_FW_JSON, 'chore: 因子权重更新')
        return True
    except Exception as e:
        print(f'[fw] 权重重写失败 {e}')
        return False


def _factor_weights():
    """运行时权重：有 data/factor_weights.json 就用它，否则回退引擎默认 WEIGHTS_SHORT。
    强制归一（总和=1），防止手工改坏。任何异常都回退默认，绝不阻断打分。"""
    if not _FACTOR_OK:
        return {}
    try:
        w = (_fw_load().get('weights') or {})
        if not w:
            return dict(_fe.WEIGHTS_SHORT)
        v = {k: float(w.get(k) or 0) for k in _FW_FACTORS}
        s = sum(v.values())
        if s <= 0:
            return dict(_fe.WEIGHTS_SHORT)
        return {k: x / s for k, x in v.items()}
    except Exception:
        return dict(_fe.WEIGHTS_SHORT)


def _fw_week_rows(days=7):
    """取最近 days 天、且已回填 win 的 signal_log 记录。没回填的不进统计（不拿半成品算胜率）。"""
    try:
        with open(_SIG_CSV, 'r', encoding='utf-8') as f:
            lines = f.read().rstrip('\n').split('\n')
    except Exception:
        return [], {}
    if len(lines) < 2:
        return [], {}
    hdr = lines[0].split(',')
    idx = {n: i for i, n in enumerate(hdr)}
    cutoff = (_bj_now() - timedelta(days=days)).strftime('%Y-%m-%d')
    out = []
    for ln in lines[1:]:
        if not ln.strip():
            continue
        r = ln.split(',')
        if len(r) < len(hdr):
            r += [''] * (len(hdr) - len(r))
        if r[idx['date']] < cutoff:
            continue
        if r[idx['win']] not in ('0', '1'):
            continue
        out.append(r)
    return out, idx


def _fw_stats(days=7, thresh=70):
    """本周因子体检：总笔数 / 总胜率 / 每因子「看多档胜率 vs 其余档胜率」。
    口径写死：某因子分 >= thresh 视为该因子当时看多；看多那批的实际 5 日胜率 = 该因子胜率。
    某档样本 <3 记 None，不硬算。"""
    rows, idx = _fw_week_rows(days)
    n = len(rows)
    if n == 0:
        return {'n': 0, 'win_rate': None, 'factors': {}, 'avg_ret': None}
    wins = sum(1 for r in rows if r[idx['win']] == '1')
    rets = []
    for r in rows:
        try:
            rets.append(float(r[idx['ret5']]))
        except Exception:
            pass
    fac = {}
    for k in _FW_FACTORS:
        hi = hi_w = lo = lo_w = 0
        for r in rows:
            try:
                v = float(r[idx[k]] or '')
            except Exception:
                continue
            if v >= thresh:
                hi += 1
                hi_w += 1 if r[idx['win']] == '1' else 0
            else:
                lo += 1
                lo_w += 1 if r[idx['win']] == '1' else 0
        fac[k] = {'hi_n': hi, 'hi_win': (hi_w / hi) if hi >= 3 else None,
                  'lo_n': lo, 'lo_win': (lo_w / lo) if lo >= 3 else None}
    return {'n': n, 'win_rate': wins / n, 'factors': fac,
            'avg_ret': (sum(rets) / len(rets)) if rets else None}


def _fw_apply(days=7, thresh=70):
    """机械调权（规格写死，不许人工拍脑袋）：
    连续 2 周胜率 <45% → 权重 -5 点（下限 10%）；连续 2 周 >60% → +5 点（上限 40%）。
    连续计数持久化在 data/factor_weights.json。返回 (新权重, 调整明细, 统计快照)。"""
    st = _fw_load()
    base = dict(_fe.WEIGHTS_SHORT) if _FACTOR_OK else {'jq': .3, 'lj': .3, 'zj': .2, 'tc': .1, 'dl': .1}
    w = {k: float((st.get('weights') or {}).get(k) or base.get(k) or 0) for k in _FW_FACTORS}
    low = dict(st.get('low_streak') or {})
    high = dict(st.get('high_streak') or {})
    s = _fw_stats(days, thresh)
    if (s.get('n') or 0) < _FW_MIN_SAMPLES:
        return w, [], s   # 样本不足：原权重原样返回，不累计 streak、不动权重
    wk = _bj_now().strftime('%Y-%W')
    if st.get('last_week') == wk:
        return w, [], s   # 本周已结算过：同日/同周重复运行不再累计 streak（否则"连续2周"被重跑凑满）
    changes = []
    for k in _FW_FACTORS:
        wr = (s.get('factors', {}).get(k) or {}).get('hi_win')
        if wr is None:
            low[k] = 0
            high[k] = 0
            continue
        if wr < _FW_WIN_LO:
            low[k] = int(low.get(k) or 0) + 1
            high[k] = 0
        elif wr > _FW_WIN_HI:
            high[k] = int(high.get(k) or 0) + 1
            low[k] = 0
        else:
            low[k] = 0
            high[k] = 0
        if int(low.get(k) or 0) >= 2:
            new = max(_FW_MIN, w[k] - _FW_STEP)
            if abs(new - w[k]) > 1e-9:
                changes.append({'k': k, 'from': w[k], 'to': new,
                                'why': '%s连续2周胜率%.0f%%<45%%，减重5点'
                                       % (_FW_LABEL[k], wr * 100)})
            w[k] = new
            low[k] = 0
        elif int(high.get(k) or 0) >= 2:
            new = min(_FW_MAX, w[k] + _FW_STEP)
            if abs(new - w[k]) > 1e-9:
                changes.append({'k': k, 'from': w[k], 'to': new,
                                'why': '%s连续2周胜率%.0f%%>60%%，加重5点'
                                       % (_FW_LABEL[k], wr * 100)})
            w[k] = new
            high[k] = 0
    tot = sum(w.values())
    if tot > 0:
        w = {k: v / tot for k, v in w.items()}
    st['weights'] = w
    st['low_streak'] = low
    st['high_streak'] = high
    hist = (st.get('history') or [])[-51:]
    hist.append({'week': _bj_now().strftime('%Y-%m-%d'), 'n': s.get('n'),
                 'win_rate': s.get('win_rate'),
                 'factors': {k: (s.get('factors', {}).get(k) or {}).get('hi_win') for k in _FW_FACTORS}})
    st['history'] = hist
    st['last_week'] = wk
    # 必须每周都落盘：连续计数（streak）靠它跨周累积。
    # 只在「有变更」时才写会导致 streak 永远到不了 2，"连续2周"规则形同虚设（实测暴露）。
    _fw_save(st)
    return w, changes, s


def _fw_bar(v):
    """胜率进度条（纯 CSS，深色卡内可读）。"""
    try:
        p = max(0.0, min(1.0, float(v)))
    except Exception:
        return ''
    col = '#52c41a' if p >= _FW_WIN_HI else ('#ffb020' if p >= _FW_WIN_LO else '#ff6b6b')
    return (f'<div style="display:inline-block;width:64px;height:7px;background:#2b3345;'
            f'border-radius:4px;vertical-align:middle;margin:0 6px;">'
            f'<div style="width:{p * 100:.0f}%;height:100%;background:{col};border-radius:4px;"></div></div>')


def build_factor_weekly():
    """周日「因子体检报告」：本周 N 笔 / 5日胜率 / 分因子胜率对比 / 机械调权结果。
    样本数、胜率、调权全部由代码实算（绝不编数）；结论与解读交大模型生成，
    模型未返回时只报数据事实、不给规则版结论。没有已回填样本时给明确空态。"""
    if not _FACTOR_OK:
        return ''
    try:
        s = _fw_stats(7)
    except Exception as e:
        print(f'[fw] 统计异常 {e}')
        return ''
    n = s.get('n') or 0
    if n < _FW_MIN_SAMPLES:
        note = ('本周还没有「已回填」的信号。' if n == 0
                else f'本周「已回填」样本只有 {n} 笔。')
        inner = (f'<div style="color:{GREY};font-size:14px;line-height:1.7;">'
                 f'{note}<br>样本未达 <b style="color:#ffb020;">{_FW_MIN_SAMPLES} 笔</b> 门槛 → '
                 f'只报数据不足，不出胜率结论、也不动权重（样本太少会被噪声带偏）。<br>'
                 f'signal_log 要等推送后第 5 个交易日收盘才算得出胜负，第一份成绩单需跑满 5 个交易日。<br>'
                 f'全部记录见 data/signal_log.csv。</div>')
        return _wrap(inner, '📊', '因子体检报告')
    try:
        w, changes, s = _fw_apply(7)
    except Exception as e:
        print(f'[fw] 调权异常 {e}')
        return ''
    wr = s.get('win_rate') or 0
    av = s.get('avg_ret')
    _wcol = '#52c41a' if wr >= _FW_WIN_HI else ('#ffb020' if wr >= _FW_WIN_LO else '#ff6b6b')
    # —— 大模型解读（禁规则结论：结论只认模型输出）——
    _verdict = _weight_read = _plain = ''
    _freads = {}

    def _fw_pct(v):
        return (None if v is None else round(float(v) * 100, 1))

    _fkp = {
        'task': 'factor_weekly_read',
        'n': n,
        'win_rate': round(float(wr) * 100, 1),
        'avg_ret': (round(float(av), 2) if av is not None else None),
        'factors': [{'k': _FW_LABEL[k],
                     'hi_n': (s['factors'].get(k) or {}).get('hi_n', 0),
                     'hi_win': _fw_pct((s['factors'].get(k) or {}).get('hi_win')),
                     'lo_n': (s['factors'].get(k) or {}).get('lo_n', 0),
                     'lo_win': _fw_pct((s['factors'].get(k) or {}).get('lo_win'))}
                    for k in _FW_FACTORS],
        'changes': [{'k': _FW_LABEL[c0['k']], 'why': c0['why'],
                     'from': round(float(c0['from']) * 100), 'to': round(float(c0['to']) * 100)}
                    for c0 in changes],
        'weights': {_FW_LABEL[k]: round(float(w.get(k, 0)) * 100) for k in _FW_FACTORS},
        'min_samples': _FW_MIN_SAMPLES,
        'format': (
            '你是A股量化因子研究员。上面样本数、5日胜率、分因子胜率、调权结果都是程序实算的事实，只许引用不许改、不许推新数字。'
            '只输出 JSON，不要任何其他文字：'
            '{"verdict":"本周结论：这批信号到底赚不赚、赚多少、问题出在哪，必须引用胜率和平均收益，至少40字",'
            '"factor_read":[{"k":"因子名","read":"这个因子本周表现说明什么：给高分的那批真涨了还是虚高，下阶段该加重还是减，引用两组胜率，至少35字"}],'
            '"weight_read":"权重解读：这次调权（或没调）说明什么、下阶段权重怎么走，至少30字",'
            '"plain":"一句大白话给散户：这套因子现在还灵不灵，至少20字"}'
            'factor_read 必须覆盖我给的每个因子。禁止万能句、禁止设问句、禁止列表符号、禁止编造未给出的数字。'),
    }
    _ft = ask_deepseek(_fkp, purpose='factor_weekly_card')
    if _ft:
        try:
            _j = json.loads(_ft[_ft.find('{'):_ft.rfind('}') + 1])
            _verdict = str(_j.get('verdict') or '').strip()
            _weight_read = str(_j.get('weight_read') or '').strip()
            _plain = str(_j.get('plain') or '').strip()
            for _it in (_j.get('factor_read') or []):
                _k = str(_it.get('k') or '').strip()
                _rd = str(_it.get('read') or '').strip()
                if _k and _rd:
                    _freads[_k] = _rd
        except Exception as e:
            print('[fw] LLM JSON 解析失败:', e)
    inner = (f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px;">'
             f'<div style="flex:1 1 100px;background:#1f2635;border-radius:8px;padding:9px 11px;">'
             f'<div style="color:{GREY};font-size:11px;">本周样本</div>'
             f'<div style="color:#fff;font-size:21px;font-weight:800;">{n}<span style="font-size:11px;'
             f'color:{GREY};font-weight:400;"> 笔</span></div></div>'
             f'<div style="flex:1 1 100px;background:#1f2635;border-radius:8px;padding:9px 11px;">'
             f'<div style="color:{GREY};font-size:11px;">5日胜率</div>'
             f'<div style="color:{_wcol};font-size:21px;font-weight:800;">{wr * 100:.0f}%</div></div>'
             f'<div style="flex:1 1 100px;background:#1f2635;border-radius:8px;padding:9px 11px;">'
             f'<div style="color:{GREY};font-size:11px;">平均5日收益</div>'
             f'<div style="color:{_c(av or 0)};font-size:21px;font-weight:800;">'
             f'{(f"{av:+.2f}%" if av is not None else "—")}</div></div></div>')
    if _verdict:
        inner += (f'<div style="background:#1c2830;border-left:4px solid #a78bfa;border-radius:8px;'
                  f'padding:9px 11px;margin-bottom:8px;color:#e9ecef;font-size:13px;line-height:1.65;">'
                  f'🧠 本周结论：{_verdict}</div>')
    else:
        pass
    # —— 分因子胜率对照 ——
    inner += (f'<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">'
              f'🔍 分因子胜率（因子分≥70 那批的实际 5 日胜率）</div>'
              f'<div style="color:{GREY};font-size:11px;margin:2px 0 0;">右侧档位是硬阈值，横线下面的字是大模型给的解读</div>')
    for k in _FW_FACTORS:
        f = s['factors'].get(k) or {}
        hi_w = f.get('hi_win')
        lo_w = f.get('lo_win')
        if hi_w is None and lo_w is None:
            judge, jcol = '样本不足', GREY
        elif hi_w is None:
            judge, jcol = '多样本不足', GREY
        elif hi_w >= _FW_WIN_HI:
            judge, jcol = '能打', '#52c41a'
        elif hi_w < _FW_WIN_LO:
            judge, jcol = '不灵', '#ff6b6b'
        else:
            judge, jcol = '中性', '#ffb020'
        if lo_w is not None and hi_w is not None and hi_w - lo_w < -0.05:
            judge, jcol = '反向', '#ff6b6b'
        _rd = _freads.get(_FW_LABEL[k])
        _rd_html = ((f'<div style="font-size:11px;color:#a78bfa;margin-top:3px;">🧠 {_rd}</div>')
                    if _rd else
                    '')
        inner += (f'<div style="background:#1f2635;border-radius:8px;padding:8px 11px;margin:5px 0;">'
                  f'<div style="font-size:13px;font-weight:700;color:#fff;">{_FW_LABEL[k]}'
                  f'<span style="float:right;color:{jcol};">{judge}</span></div>'
                  f'<div style="font-size:11px;color:{GREY};margin-top:2px;">'
                  f'看多 {f.get("hi_n", 0)} 笔：{"—" if hi_w is None else f"{hi_w * 100:.0f}%"}'
                  f'{_fw_bar(hi_w) if hi_w is not None else ""}'
                  f'｜其余 {f.get("lo_n", 0)} 笔：{"—" if lo_w is None else f"{lo_w * 100:.0f}%"}</div>'
                  f'{_rd_html}</div>')
    # —— 机械调权结果 ——
    inner += (f'<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">'
              f'⚙️ 机械调权（连续2周<45%减5点／>60%加5点，下限10%上限40%）</div>')
    if changes:
        for c0 in changes:
            inner += (f'<div style="background:#2a1f1f;border-left:3px solid #ff6b6b;border-radius:8px;'
                      f'padding:8px 11px;margin:5px 0;color:#e9ecef;font-size:12px;">'
                      f'<b>{_FW_LABEL[c0["k"]]}</b>：{c0["why"]}（{c0["from"] * 100:.0f}% → '
                      f'{c0["to"] * 100:.0f}%）</div>')
    else:
        inner += (f'<div style="color:{GREY};font-size:12px;">本周没有触发调权的因子'
                  f'（需连续 2 周才动，避免被单周噪声带偏）。</div>')
    if _weight_read:
        inner += (f'<div style="color:#a78bfa;font-size:12px;margin-top:5px;">🧠 权重解读：{_weight_read}</div>')
    cur = ' / '.join(f'{_FW_LABEL[k]}{w.get(k, 0) * 100:.0f}%' for k in _FW_FACTORS)
    inner += (f'<div style="margin-top:8px;color:#8ce99a;font-size:12px;">当前生效权重：{cur}</div>')
    if _plain:
        inner += (f'<div style="color:#ced4da;font-size:12px;margin-top:6px;">💬 {_plain}</div>')
    # —— 明细口径说明 ——
    inner += ''
    return _wrap(inner, '📊', '因子体检报告')


# ============ 模块8/9/10：主线生命周期 + 龙头拐点 + 错过信号复盘 ============
def life_cycle(sec, d, mem, days):
    """主线生命周期（模块8）：启动期/加速期/分化期/退潮期。
    规则：今日涨停家数 vs 近3日（mem leaders 长度近似家数；无历史如实按现状判）。"""
    zt_n = len(d['sectors'].get(sec, []) or [])
    hist = []
    for pd in days[:3]:
        hist.append(len((mem.get(pd, {}).get(sec) or {}).get('leaders', [])))
    yest_n = hist[0] if hist else 0
    if zt_n < 2:
        return '退潮期', '家数萎缩，回避该方向'
    if yest_n <= 1 and zt_n >= 3:
        return '启动期', '新点火，轻仓跟龙头'
    if yest_n >= 3 and zt_n < yest_n * 0.7:
        return '分化期', '家数较前日减少，只做龙头'
    return '加速期', '连续强势，可积极'


def life_badge(sec, d, mem, days):
    """生命周期徽标 HTML（noon/eod 板块行 / watch 卡）。"""
    tag, note = life_cycle(sec, d, mem, days)
    col = {'启动期': TEAL, '加速期': RED, '分化期': GOLD, '退潮期': GREEN}[tag]
    return (f'<span style="background:{col};color:#161b26;border-radius:6px;padding:0 6px;'
            f'font-size:11px;font-weight:700;">{tag}</span>')


_PIVOT_DS_SYS = ('你是一线游资，写「龙头情绪拐点·分歧转一致」分析。某龙头连板≥3、今日盘中炸板后回封（同时现身涨停池与炸板池），你要用大白话讲清楚：判断这是主力故意制造分歧洗盘还是真出货，资金在干嘛、接下来怎么走、什么情况必须撤。只基于输入数据说话，禁编盘面；禁模板句；结论先行；坏消息不软化。只输出 JSON：{"logic":"分歧转一致意味着什么(≥25字,大白话,结合连板高度与炸板回封背景+主力意图判断)","risk":"后续风险与撤出条件(≥15字,给具体破位/炸板信号)"}，不要其他文字。')


def _pivot_ds(nm, lbc):
    """龙头分歧转一致 LLM 分析（失败 '' → 调用方回退规则文案）。"""
    if not MODELSCOPE_KEY:
        return ''
    try:
        fmt = ('股票' + nm + ' 连板' + str(lbc) + ' 今日炸板后回封（分歧转一致）。只输出 JSON：'
               '{"logic":"分歧转一致意味着什么(≥25字,大白话,结合连板高度与炸板回封背景,禁模板句)","risk":"后续风险与撤出条件(≥15字,给具体信号)"}，不要其他文字')
        t = ask_deepseek({'task': 'pivot_confirm', 'stock': {'name': nm, 'lbc': lbc}, 'format': fmt},
                         purpose='pivot', system_text=_PIVOT_DS_SYS)
        if not t:
            return ''
        _j = json.loads(t)
        _l = str(_j.get('logic') or '').strip()
        if not _l:
            return ''
        _r = str(_j.get('risk') or '').strip()
        _h = ('<div style="background:#3a1c1c;border:2px solid ' + RED + ';border-radius:12px;padding:10px 14px;margin:10px 0;">'
              '<div style="font-size:15px;font-weight:900;color:' + RED + ';">👑 龙头情绪拐点 · ' + nm + '（连板' + str(lbc) + '）</div>'
              '<div style="color:#e9ecef;font-size:13px;margin-top:5px;">🧠 ' + _l + '</div>'
              + (('<div style="color:' + RED + ';font-size:12px;margin-top:3px;">⚠️ 风险：' + _r + '</div>') if _r else '') + '</div>')
        return _h
    except Exception:
        return ''


def pivot_monitor(d, al):
    """龙头分歧转一致（模块9）：连板≥3 且现身炸板池（同日炸过又回封）→ 「分歧转一致」龙头情绪拐点；
    回封≤30min 过滤：当天池数据未提供该字段，如实标注不硬编。连板≥3 未现身炸板池 → 未炸板，不触发。
    「连板≥3 仅在炸板池（已炸板未回封）」需炸板池连板数，当前东财池数据未提供该字段 → 如实不实现，避免误报。
    每只每日最多1次。"""
    today = _bj_now().strftime('%Y-%m-%d')
    done = set(al.get('pivot', {}).get(today, []))
    zb = d.get('zb_names') or set()
    cards, new_keys = [], []
    for stocks in d['sectors'].values():
        for st in stocks:
            lbc = int(st.get('lbc') or 0)
            nm = st.get('n') or st.get('c') or ''
            if lbc < 3 or not nm:
                continue
            if nm not in zb:
                continue  # 未炸板，正常，不触发
            typ = '分歧转一致'
            k = f'{nm}|{typ}'
            if k in done:
                continue
            txt = (f'{nm} 连板{lbc}，【分歧转一致】同时现身涨停+炸板池，炸板后回封，龙头情绪拐点')
            _pv_llm = _pivot_ds(nm, lbc)
            cards.append(_pv_llm or f"""<div style="background:#3a1c1c;border:2px solid {RED};border-radius:12px;padding:10px 14px;margin:10px 0;">
<div style="font-size:15px;font-weight:900;color:{RED};">👑 龙头情绪拐点 · {nm}</div>
<div style="color:#e9ecef;font-size:13px;margin-top:5px;">{nm} 连板{lbc} 板，今天同时在涨停池和炸板池里出现过，炸了又封回去，龙头那股劲被砸了一下但没散</div></div>""")
            new_keys.append(k)
    if new_keys:
        al.setdefault('pivot', {})[today] = list(done | set(new_keys))
        save_alerts(al)
    return ''.join(cards)


def _miss_deep(miss_items):
    """今日错过 TOP5 的模型归因（说明书 11.3）：错过原因（未进池/过滤过严/信号晚）+ 明日是否仍有效。
    预算/失败回退规则归因。返回 {name: (reason, tomorrow_valid)}。"""
    if not miss_items or not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return {}
    lines = '\n'.join(f"- {it['name']}({it['code']}) 收涨{it['pct']:+.1f}% 题材{it['industry']} 规则归因：{it['reason']}" for it in miss_items)
    fmt = ('你是一线游资，收盘复盘「今日错过 TOP5」（仅规则优化线索，不构成买卖建议）。\n'
           '对下面每只错过票判断：为什么没抓住（未进池/过滤过严/信号晚/建仓痕迹被过滤）+ 明天是否仍有效（能/不能/要看竞价）。\n'
           '只输出 JSON：{"per":[{"name":"股票名(照抄)","reason":"错过原因(≥15字)","tomorrow_valid":"能/不能/要看竞价+一句条件(≥10字)"}]}，\n'
           '不许硬编，不确定写「数据不足」。\n错过列表：\n' + lines)
    t = ask_deepseek({'task': 'miss_deep', 'items': miss_items, 'format': fmt}, purpose='miss_deep')
    out = {}
    if not t:
        return out
    try:
        _j = json.loads(t)
        for it in _j.get('per') or []:
            nm = str(it.get('name') or '').strip()
            if nm:
                out[nm] = (str(it.get('reason') or ''), str(it.get('tomorrow_valid') or ''))
    except Exception:
        pass
    return out


def _save_gauge_from_md(t, source):
    """从 LLM md 文本解析【仓位仪表盘】行 → data/position_gauge.json（供后续模块注入）。失败静默。"""
    try:
        suggest = ''
        for ln in t.splitlines():
            if '仓位仪表盘' in ln:
                suggest = re.sub(r'.*?仓位仪表盘[】》:：]?\s*', '', ln).strip()
                break
        m = re.search(r'(空仓|1成试探|1-2成|半仓|2成)', suggest or '')
        if m:
            suggest = m.group(1)
        save_position_gauge({
            'suggest': suggest or '空仓',
            'emotion': '',
            'reason': suggest,
            'valid_until': '次日竞价',
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'source': source,
        })
    except Exception as e:
        print('[gauge] 解析失败:', e)


def _parse_judgment_v2_from_md(t):
    """解析 eod LLM 输出的【今日判断记录】五词条 → dict（供写 data/judgment.json）。解析失败返回 None。"""
    out = {}
    keys = {'情绪': 'emotion', '主线': 'mainline', '推荐': 'recommend', '风险': 'risk', '明日预案': 'tomorrow_plan'}
    for ln in t.splitlines():
        ln = ln.strip()
        for k, v in keys.items():
            if ln.startswith(k + '：') or ln.startswith(k + ':'):
                out[v] = ln[len(k) + 1:].strip()
                break
    for ln in t.splitlines():
        if '仓位仪表盘' in ln:
            mm = re.search(r'(空仓|1成试探|1-2成|半仓|2成)', ln)
            if mm:
                out['position'] = mm.group(1)
            break
    if not out:
        return None
    return out


def miss_review(d, al):
    """错过信号复盘（模块10）：当日涨幅榜 vs 已推信号 → 今日错过 TOP5 + 简单归因。
    仅作规则优化线索，不给买卖建议。涨幅榜未取得 → 空。"""
    try:
        rows = _clist_gainers()
    except Exception:
        return ''
    fired = set(al.get('fired', []))
    names_fired = {k.split('|')[0] for k in fired if '|' in k}
    miss = [s for s in rows if s['pct'] >= 9.0 and s['name'] not in names_fired]
    out = []
    items = []
    for s in miss[:5]:
        # 简单归因：硬过滤剔除（次新/ST/高位MA20下）或 规则外首动
        reason = '规则外首动（涨幅榜直接拉板，未进盘中监控窗口）'
        sym = ('sh' if s['code'].startswith('6') else 'sz') + s['code']
        if s.get('list_date') and len(s.get('list_date', '')) == 8:
            try:
                from datetime import date
                yy, mm, dd = map(int, _bj_now().strftime('%Y-%m-%d').split('-'))
                ld = date(int(s['list_date'][:4]), int(s['list_date'][4:6]), int(s['list_date'][6:8]))
                if (date(yy, mm, dd) - ld).days < 365:
                    reason = '次新<365天被硬过滤剔除'
            except Exception:
                pass
        items.append({'name': s['name'], 'code': s['code'], 'pct': s['pct'], 'industry': s.get('industry', ''), 'reason': reason})
        out.append(f'{s["name"]}({s["code"]}) +{s["pct"]:.1f}% {s["industry"]} — {reason}')
    try:
        _md = _miss_deep(items)
    except Exception:
        _md = {}
    if _md:
        for it in items:
            r2 = _md.get(it['name'])
            if r2:
                out.append(f'{it["name"]}({it["code"]}) 🧠 模型归因：{r2[0]}｜明日：{r2[1]}')
    else:
        # 模型归因未返回时，只保留代码过滤记录这个事实字段，并明确标注它不是 AI 判读
        out.append('（AI 归因未返回：以上仅列代码过滤记录，不是 AI 判读结论）')
    return ''.join(f'<div style="margin:4px 0;font-size:13px;color:{GREY};">🚫 {o}</div>' for o in out)


# ============ 模块11：外盘关键窗口极简提醒 ============
def _global_markets():
    """全球行情采集（多源：腾讯美股/商品 + 新浪恒生 + OKX比特币）。缺哪个标哪个，绝不编造。
    返回 [(名称, 涨跌%, 备注)]，涨跌% 为 None 表示未取得。"""
    out = []
    for nm, code in (('纳指', 'usIXIC'), ('道指', 'usDJI'), ('标普', 'usINX')):
        try:
            txt, ok = _getm('http://qt.gtimg.cn/q=' + code, 'ext_' + code)
            if not ok or not txt:
                out.append((nm, None, '未取得'))
                continue
            f = txt.split('~')
            prev = float(f[4]) if len(f) > 4 and f[4] not in ('', '0.00') else 0
            pct = (float(f[3]) / prev - 1) * 100 if prev else None
            out.append((nm, pct, ''))
        except Exception:
            out.append((nm, None, '未取得'))
    try:
        req = urllib.request.Request('https://hq.sinajs.cn/list=int_hangseng',
                                     headers={**UA, 'Referer': 'https://finance.sina.com.cn/'})
        txt = urllib.request.urlopen(req, timeout=8).read().decode('gbk', 'ignore')
        f = txt.split('"')[1].split(',')
        if len(f) > 2 and f[1]:
            cur = float(f[1]); chg = float(f[2])
            out.append(('恒生', chg / (cur - chg) * 100 if cur != chg else 0.0, ''))
        else:
            out.append(('恒生', None, '未取得'))
    except Exception:
        out.append(('恒生', None, '未取得'))
    for nm, code in (('原油', 'hf_CL'), ('黄金', 'hf_GC')):
        try:
            txt, ok = _getm('http://qt.gtimg.cn/q=' + code, 'ext_' + code)
            if not ok or not txt:
                out.append((nm, None, '未取得'))
                continue
            v = txt.split('"')[1].split(',')
            out.append((nm, float(v[1]), ''))
        except Exception:
            out.append((nm, None, '未取得'))
    try:
        b = _btc_quote()
        if b:
            out.append(('比特币', b[1], ''))
        else:
            out.append(('比特币', None, '未取得'))
    except Exception:
        out.append(('比特币', None, '未取得'))
    return out


def _global_markets_html(gl):
    """全球行情区块 HTML（红涨绿跌，有数据的才显示）。"""
    if not gl:
        return '<div style="color:' + GREY + ';font-size:13px;">全球行情未取得</div>'
    rows = []
    for nm, pct, note in gl:
        if pct is None:
            rows.append(f'{nm} <span style="color:{GREY}">{note or "未取得"}</span>')
        else:
            rows.append(f'{nm} <b style="color:{RED if pct >= 0 else GREEN}">{pct:+.2f}%</b>')
    return '<div style="font-size:13px;color:#e2e8f0;">' + '　'.join(rows) + '</div>'


def build_ext():
    """外盘窗口（升级版）：全球行情采集（美股三指数/恒生/原油/黄金/比特币）+ 全球7x24消息
    → DeepSeek 大白话汇总对A股影响。DS 失败/用尽 → 规则兜底（行情+纳指影响+新闻标题）。"""
    gl = _global_markets()
    news = []
    try:
        news = get_news(14)
    except Exception:
        pass
    markets_txt = '；'.join(f'{nm} {("未取得" if pct is None else "%+.2f%%" % pct)}' for nm, pct, _ in gl)
    news_brief = [{'t': nw['title'], 's': (nw.get('summary') or '')[:50]} for nw in news[:12]]
    # —— DS 大白话汇总（交易员规范；失败/用尽 → 规则兜底）——
    ds_html = ''
    if DEEPSEEK_KEY and news:
        fmt = (_TRADER_RULES + '\n'
               + '今晚全球行情：{markets}\n'
               + '全球财经消息（东财7x24）：\n{news}\n'
               + '请严格按以下格式输出（全大白话，禁模板句，不许加板块）：\n'
               + '只用一段连贯的话讲完：外盘哪里强哪里弱、只挑对A股有影响的讲、这份外盘数据映射到明天A股哪个板块或题材、明天开盘该追该接还是直接避开、万一外盘反向对应板块怎么处理。\n'
               + '全篇禁止分栏、禁止【】标题、禁止问号、禁止「1.2.3.」列表、禁止「每条=…」这种说明文字；整段不超过 6 句，像朋友连麦一口气说完。\n'
               + '【明天A股怎么看】一句话定调（偏多/偏空/震荡）+ 明天最该做的一件事\n'

               + '如果今晚没有值得说的重要消息，必须写「今晚无大事」并说明原因，禁止硬凑。')
        t = ask_deepseek({'task': 'ext_global', 'markets': markets_txt, 'news': news_brief,
                          'format': fmt}, purpose='ext')
        ds_html = md2html(t) if t else ''
    if not ds_html:
        print('[ext] LLM 未返回且已禁规则版兜底，不推外盘卡')
        return None
    news_rows, _used_ds = _news_html_lines(news, n=8, purpose_key='ext_news', max_show=10)
    inner = (f'<div style="font-size:15px;font-weight:800;color:#ff922b;">🌐 全球行情（红涨绿跌）</div>'
             + _global_markets_html(gl)

             + (f'<div style="margin-top:10px;padding:10px;background:#1c2230;border-left:4px solid {GOLD};border-radius:8px;font-size:13px;line-height:1.8;color:#e2e8f0;">🤖 大白话汇总：{ds_html}</div>' if ds_html else '')
             + f'<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">📰 全球消息速览</div>'
             + news_rows)
    return _wrap(inner, '🌙', '外盘窗口')


# ============ 跟涨三步走·埋伏补涨（follow） ============
_FOLLOW_MIN_FUND = 5e7          # 龙头封单资金下限（元，约5000万）
_FOLLOW_MIN_SECTOR = 3          # 板块涨停家数 ≥3 才算强势板块
_FOLLOW_MAX_LEADERS = 2         # 最多取 2 个强势板块龙头
_FOLLOW_MAX_CANDS = 8           # 每龙头候选池上限


def _follow_pool(day):
    """拉指定日期 ZT 涨停池（fbt 升序）。失败返回 []。"""
    try:
        txt, ok = _getm(f'https://push2ex.eastmoney.com/getTopicZTPool?ut=7eea3edcaed734bea9cbfc24409ed989'
                        f'&dpt=wz.ztzt&Pageindex=0&pagesize=300&sort=fbt:asc&date={day}', 'follow_zt')
        if ok and txt:
            return (json.loads(txt).get('data') or {}).get('pool') or []
    except Exception as e:
        print('[follow] 涨停池异常:', e)
    return []


# ============ 工单3：涨停梯队健康分（主线体检 / 晋级率数据底座） ============
_ZT_HIST_DIR = 'data/zt_pool_history'


def _prev_trade_day(day=None):
    """上一个工作日（YYYYMMDD）。只跳周末，不处理法定节假日——拉不到池子就按"数据未接入"走。"""
    d0 = datetime.strptime(day, '%Y%m%d') if day else _bj_now()
    for i in range(1, 8):
        d1 = d0 - timedelta(days=i)
        if d1.weekday() < 5:
            return d1.strftime('%Y%m%d')
    return (d0 - timedelta(days=1)).strftime('%Y%m%d')


def _theme_health_mod():
    """按路径加载 strategy/theme_health.py（纯 stdlib，云端可直接跑）。"""
    try:
        import importlib.util as _iu
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        p = os.path.join(_root, 'strategy', 'theme_health.py')
        if not os.path.exists(p):
            p = os.path.join('strategy', 'theme_health.py')
        s = _iu.spec_from_file_location('qm_theme_health', p)
        m = _iu.module_from_spec(s)
        s.loader.exec_module(m)
        return m
    except Exception as e:
        print('[theme_health] 加载失败:', e)
        return None


def _zt_pool_history_save(raw_pool, day):
    """当日涨停池落盘 data/zt_pool_history/YYYY-MM-DD.json 并写回仓库（晋级率的持久底座）。"""
    if not raw_pool:
        return
    try:
        os.makedirs(_ZT_HIST_DIR, exist_ok=True)
        path = os.path.join(_ZT_HIST_DIR,
                            '%s-%s-%s.json' % (day[:4], day[4:6], day[6:8]))
        keep = [{'code': str(x.get('c') or x.get('code') or ''),
                 'name': x.get('n') or x.get('name') or '',
                 'lbc': int(x.get('lbc') or 0),
                 'theme': _sec_clean(x.get('hybk') or x.get('theme') or '') or '其他',
                 'fund': x.get('fund')} for x in raw_pool]
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'date': day, 'count': len(keep), 'pool': keep}, f, ensure_ascii=False)
        print('[zt_hist] 已存 %s（%d 家）' % (path, len(keep)))
        _git_commit_push(path, 'update zt pool history %s' % day)
    except Exception as e:
        print('[zt_hist] 落盘失败:', e)


def _theme_health_rows(raw_pool):
    """东财涨停池原始行 → theme_health 入参行（纯映射，不改数）。"""
    rows = []
    for x in raw_pool or []:
        rows.append({'code': str(x.get('c') or x.get('code') or ''),
                     'name': x.get('n') or x.get('name') or '',
                     'lbc': int(x.get('lbc') or x.get('lianchi') or 0),
                     'theme': _sec_clean(x.get('hybk') or x.get('theme') or '') or '其他'})
    return rows


def build_theme_health(d, top_n=5):
    """【主线体检】段落：健康分/档位/梯队/一句大白话。缺数据如实标注，绝不编分。"""
    mod = _theme_health_mod()
    if mod is None or not d:
        return ''
    raw = []
    for _theme, lst in (d.get('sectors') or {}).items():
        raw.extend(lst or [])
    if not raw:
        print('[theme_health] 涨停池为空，主线体检跳过')
        return ''
    today = _bj_now().strftime('%Y%m%d')
    prev_day = _prev_trade_day(today)
    try:
        pool_now = _follow_pool(today)
        _zt_pool_history_save(pool_now or raw, today)
    except Exception as e:
        print('[theme_health] 今日涨停池历史保存异常:', e)
    # 优先用仓库里的昨日快照（自己攒的数据比接口稳），没有再退回接口按日拉
    prev_rows = None
    try:
        _pd = '%s-%s-%s' % (prev_day[:4], prev_day[4:6], prev_day[6:8])
        _pf = os.path.join(_ZT_HIST_DIR, _pd + '.json')
        if os.path.exists(_pf):
            with open(_pf, encoding='utf-8') as f:
                prev_rows = _theme_health_rows((json.load(f) or {}).get('pool'))
            print('[theme_health] 昨日池取自仓库快照 %s' % _pf)
        else:
            _pp = _follow_pool(prev_day)
            prev_rows = _theme_health_rows(_pp) if _pp else None
            if prev_rows:
                print('[theme_health] 昨日池取自接口 %s（%d 家）' % (prev_day, len(prev_rows)))
    except Exception as e:
        print('[theme_health] 昨日池读取异常:', e)
        prev_rows = None
    if not prev_rows:
        print('[theme_health] 昨日(%s)涨停池不可得，晋级率标"数据未接入"' % prev_day)
    res = mod.theme_health(_theme_health_rows(raw), prev_rows=prev_rows, top_n=top_n)
    if not res:
        return ''
    # —— 大模型判读（禁规则大白话：题材判读只认模型输出）——
    _reads = {}
    _overall = ''
    _act = ''
    _hp = {
        'task': 'theme_health_read',
        'prev_day': prev_day,
        'themes': [{'theme': h['theme'], 'score': round(float(h['score']), 1), 'level': h['level'],
                    'ladder': h['ladder'], 'promote': h['promote_note'] or ''} for h in res[:top_n]],
        'format': (
            '你是A股主线交易员。上面每个题材的健康分/档位/梯队是程序按涨停池实算的事实，只许引用不许改。'
            '只输出 JSON，不要任何其他文字：'
            '{"overall":"主线总判断：现在主线处在什么阶段、还能不能上、最该盯哪个题材，至少30字",'
            '"per":[{"theme":"题材名","read":"这个题材的判读：加速还是分歧、梯队还健不健康、明天还能不能做，必须引用分数和梯队家数，至少40字"}],'
            '"act":"动作：跟主线该怎么做——重点看哪几个、避开哪几个，至少25字"}'
            'per 必须覆盖我给的每个题材。禁止万能句、禁止设问句、禁止列表符号、禁止可能/或许这类含糊词。'),
    }
    _ht = ask_deepseek(_hp, purpose='theme_health_card')
    if _ht:
        try:
            _j = json.loads(_ht[_ht.find('{'):_ht.rfind('}') + 1])
            _overall = str(_j.get('overall') or '').strip()
            _act = str(_j.get('act') or '').strip()
            for _it in (_j.get('per') or []):
                _nm = str(_it.get('theme') or '').strip()
                _rd = str(_it.get('read') or '').strip()
                if _nm and _rd:
                    _reads[_nm] = _rd
        except Exception as e:
            print('[theme_health] LLM JSON 解析失败:', e)
    blocks = []
    for h in res:
        _rd = _reads.get(h['theme'])
        if not _rd:
            continue          # 没有 AI 读法就不摆裸指标（用户要总结市场，不要规则条目）
        col = RED if h['level'] == '加速期' else (GOLD if h['level'] == '分歧期' else GREY)
        blocks.append(
            '<div style="background:#1f2635;border-left:4px solid %s;border-radius:8px;padding:8px 10px;margin:6px 0;">'
            '<div style="font-weight:700;color:#fff;">%s <span style="color:%s;font-size:11px;">%s</span></div>'
            '<div style="color:#ced4da;font-size:12px;margin-top:3px;">%s</div></div>'
            % (col, h['theme'], col, h['level'], _rd))
    if not blocks:
        _avg = (sum(float(h['score']) for h in res) / len(res)) if res else 0
        _lv = ('多数题材还在分歧、没有能接力的方向，明天只跟最强的那个，其余一律不碰' if _avg < 50
               else '有题材在加速，明天盯最强的那个能不能继续封住，封不住就一起撤')
        blocks.append('<div style="background:#1f2635;border-left:4px solid %s;border-radius:8px;padding:8px 10px;">'
                      '<div style="color:#ced4da;font-size:12px;">今天主线整体 %.0f 分，%s。</div></div>' % (GREY, _avg, _lv))
    _head_txt = '<div style="margin-top:12px;font-size:15px;font-weight:800;color:#ff922b;">【主线体检】</div>'
    _over_txt = ('<div style="color:#e2e8f0;font-size:12px;margin-top:4px;">🧠 %s</div>' % _overall) if _overall else ''
    _act_txt = ('<div style="color:#ffd43b;font-size:12px;margin-top:4px;">👉 %s</div>' % _act) if _act else ''
    return _head_txt + _over_txt + _act_txt + ''.join(blocks)


# ============ 工单7：情绪周期（eod 算并落盘，次日竞价卡顶部展示） ============
_SENT_PATH = 'data/sentiment_state.json'


def _sc_mod():
    try:
        import importlib.util as _iu
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sentiment_cycle.py')
        if not os.path.exists(p):
            p = os.path.join('tools', 'sentiment_cycle.py')
        s = _iu.spec_from_file_location('qm_sentiment_cycle', p)
        m = _iu.module_from_spec(s)
        s.loader.exec_module(m)
        return m
    except Exception as e:
        print('[sentiment] 加载失败:', e)
        return None


def _sentiment_refresh(day=None):
    """eod 用当日真实涨停池/炸板池/昨涨停溢价算 S 并落盘。失败不阻断推送。"""
    mod = _sc_mod()
    if mod is None:
        return None
    today = day or _bj_now().strftime('%Y%m%d')
    prev = _prev_trade_day(today)
    try:
        res = mod.run_day(today, prev, workers=8)
    except Exception as e:
        print('[sentiment] 计算异常:', e)
        return None
    if not res or res.get('S') is None:
        print('[sentiment] 数据不足，不落盘（避免次日卡面拿旧值冒充）')
        return None
    line = mod.card_line(res)
    try:
        with open(_SENT_PATH, 'w', encoding='utf-8') as f:
            json.dump({'date': today, 'S': res['S'], 'level': res['level'],
                       'position': res['position'], 'guard': res.get('guard', False),
                       'line': line, 'detail': res.get('detail')}, f, ensure_ascii=False)
        print('[sentiment] 已落盘 %s S=%s %s' % (_SENT_PATH, res['S'], res['level']))
        _git_commit_push(_SENT_PATH, 'update sentiment state %s' % today)
    except Exception as e:
        print('[sentiment] 落盘失败:', e)
    return res


def _sentiment_line_for_auction():
    """竞价卡顶行：只认"上一个交易日"的状态，跨日/跨周末不冒充当日。"""
    try:
        with open(_SENT_PATH, encoding='utf-8') as f:
            st = json.load(f) or {}
    except Exception:
        return ''
    d = str(st.get('date') or '')
    if not d:
        return ''
    if d != _prev_trade_day(_bj_now().strftime('%Y%m%d')):
        print('[sentiment] 落盘状态 %s 非上一交易日，竞价卡不展示' % d)
        return ''
    return st.get('line') or ''


def _overnight_line_for_auction():
    """竞价卡「隔夜外盘一句话」定量行（工单10）。

    边界：只作开盘情绪偏移参考，不进 aggregator、不单独成 engine；
    与已有 LLM 文字并存不互斥。数据源全挂 → 「外盘未接入」，绝不编数。
    """
    try:
        from overnight_map import compute, card_line
        return card_line(compute())
    except Exception as e:
        print('[overnight] 参考行生成失败（不影响主卡）:', e)
        return ''


def _follow_leaders(pool):
    """每板块龙头：fbt 最早且封单厚；按板块涨停家数降序取前 N 板块龙头。"""
    by_sec = defaultdict(list)
    for x in pool:
        sec = _sec_clean(x.get('hybk') or '') or '其他'
        by_sec[sec].append(x)
    strong = [(sec, lst) for sec, lst in by_sec.items() if len(lst) >= _FOLLOW_MIN_SECTOR]
    strong.sort(key=lambda kv: -len(kv[1]))
    leaders = []
    for sec, lst in strong[:_FOLLOW_MAX_LEADERS]:
        cands = [x for x in lst if int(x.get('fbt') or 0) > 0 and float(x.get('fund') or 0) >= _FOLLOW_MIN_FUND]
        if not cands:
            cands = [x for x in lst if int(x.get('fbt') or 0) > 0]
        if not cands:
            cands = lst
        lead = min(cands, key=lambda x: (int(x.get('fbt') or 0), -float(x.get('fund') or 0)))
        leaders.append(lead)
    return leaders


def _stock_daily5(code):
    """近5个交易日每日涨跌幅：[{'d':'MM-DD','pct':x},...] 最新在后。失败 None。"""
    try:
        secid = ('1.' if code.startswith(('6', '9')) else '0.') + code
        url = ('https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=' + secid
               + '&fields1=f1,f2,f3,f4,f5&fields2=f51,f53&klt=101&fqt=1&beg=0&end=20500101&lmt=6')
        txt, ok = _getm(url, 'daily5')
        if not ok or not txt:
            return None
        kl = ((json.loads(txt).get('data') or {}).get('klines') or [])
        if len(kl) < 2:
            return None
        pts = [x.split(',') for x in kl]
        res = []
        for i in range(1, len(pts)):
            prev = float(pts[i - 1][1]); cur = float(pts[i][1])
            pct = (cur / prev - 1) * 100 if prev else 0
            res.append({'d': pts[i][0][5:], 'pct': round(pct, 2)})
        return res[-5:]
    except Exception:
        return None


def _follow_kctx(code):
    """轻量 K线：贴5日线比值/5日涨幅/60日位置/量能萎缩。失败 None。"""
    try:
        sym = ('sh' if code.startswith('6') else 'bj' if code.startswith('4') or code.startswith('8') else 'sz') + code
        arr = get_klines(sym, 70)
        if not arr or len(arr) < 8:
            return None
        closes = [float(r[2]) for r in arr]
        vols = [float(r[5]) for r in arr]
        ma5 = sum(closes[-5:]) / 5.0
        price = closes[-1]
        g5 = (price / closes[-6] - 1) * 100 if closes[-6] else 99
        pos60 = None
        if len(closes) >= 60:
            hi, lo = max(closes[-60:]), min(closes[-60:])
            pos60 = (price - lo) / (hi - lo) if hi > lo else 0.5
        v3 = sum(vols[-3:]) / 3.0
        v5p = sum(vols[-8:-3]) / 5.0
        vshr = v3 / v5p if v5p > 0 else None
        return {'price': round(price, 2), 'ma5': round(ma5, 2),
                'ratio_ma5': round(price / ma5, 3) if ma5 else 99,
                'g5': round(g5, 1), 'pos60': round(pos60, 2) if pos60 else None,
                'vshr': round(vshr, 2) if vshr else None}
    except Exception:
        return None


def _follow_candidates(leader, rows, maxn):
    """龙头同行业未涨停候选 + K线过滤（贴5日线/缩量/位置不高/涨幅不大）。"""
    sec = _sec_clean(leader.get('hybk') or '')
    out = []
    for r in rows:
        if r['code'] == str(leader.get('c') or ''):
            continue
        _ri = _sec_clean(r.get('industry') or '')
        if _ri != sec and not (sec and (_ri in sec or sec in _ri)):   # 行业名口径宽松匹配
            continue
        if r.get('pct') and r['pct'] >= 9.5:    # 已涨停的不算补涨
            continue
        out.append(r)
    picked = []
    for r in out:
        k = _follow_kctx(r['code'])
        if k is None:
            continue
        if k['pos60'] is not None and k['pos60'] > 0.9:
            continue
        if k['g5'] > 25:
            continue
        if not (0.95 <= k['ratio_ma5'] <= 1.10):    # 贴5日线（v2：放量不算坏，反而加分）
            continue
        r['_k'] = k
        picked.append(r)
        if len(picked) >= maxn:
            break
    return picked


# ============ 跟涨三步走 v2：龙头综合判定 + 100分评分 + 盘中确认 ============
# 权重为用户规格的经验初始值（rel25/init25/vol20/pos15/sector10/liq5），
# 历史回测验证待做——禁止伪造回测结果；评分只排序，不换算上涨概率。
_FOLLOW2 = {'rel': 25, 'init': 25, 'vol': 20, 'pos': 15, 'sector': 10, 'liq': 5}


def _follow_leader_v2(pool):
    """综合判定龙头（不只看涨幅）。
    返回 [{sec, leader, ltype, reasons, feat}]；ltype: emotion/capacity/divergence。
    无法唯一确认 → ltype='divergence'（龙头存在分歧，不强行指定）。"""
    by_sec = defaultdict(list)
    for x in pool:
        by_sec[_sec_clean(x.get('hybk') or '') or '其他'].append(x)
    sec_counts = {k: len(v) for k, v in by_sec.items()}
    top_secs = {k for k, _ in sorted(sec_counts.items(), key=lambda kv: -kv[1])[:3]}
    out = []
    for sec, lst in by_sec.items():
        if len(lst) < _FOLLOW_MIN_SECTOR:
            continue
        feat = []
        for x in lst:
            fbt = int(x.get('fbt') or 0)
            lbc = int(x.get('lbc') or 0)
            zbc = int(x.get('zbc') or 0)
            fund = float(x.get('fund') or 0)
            amount = float(x.get('amount') or 0)
            hs = float(x.get('hs') or 0)
            ltsz = float(x.get('ltsz') or 0)
            fbt_score = max(0.0, min(1.0, (113000 - fbt) / (113000 - 90000))) if fbt else 0.0
            zbc_pen = max(0.0, 1 - zbc / 10.0)
            emotion = fbt_score * 0.4 + zbc_pen * 0.3 + min(fund / 1e8, 2.0) * 0.15 + min(lbc / 4.0, 1.0) * 0.15
            capacity = (min(amount / 5e8, 1.5) * 0.6 + min(ltsz / 2e10, 1.0) * 0.4) if amount else 0.0
            feat.append({'code': x.get('c'), 'x': x, 'fbt': fbt, 'lbc': lbc, 'zbc': zbc,
                         'fund': fund, 'amount': amount, 'hs': hs, 'ltsz': ltsz,
                         'emotion': round(emotion, 3), 'capacity': round(capacity, 3)})
        em = max(feat, key=lambda f: f['emotion'])
        cap = max(feat, key=lambda f: f['capacity'])
        reasons = []
        if em['code'] == cap['code']:
            leader = em['x']
            ltype = 'capacity' if cap['capacity'] > em['emotion'] else 'emotion'
            reasons.append('封板最早+封单最厚+成交额最大集中在同一只，龙头明确')
        elif em['emotion'] - cap['capacity'] >= 0.1:
            leader, ltype = em['x'], 'emotion'
            reasons.append(f"情绪龙头清晰：{em['x'].get('n')} 封板最早/封单最厚（情绪分{em['emotion']:.2f}），成交额最大的是 {cap['x'].get('n')}（容量核心）但封板弱")
        elif cap['capacity'] - em['emotion'] >= 0.1:
            leader, ltype = cap['x'], 'capacity'
            reasons.append(f"容量核心主导：{cap['x'].get('n')} 成交额最大（容量分{cap['capacity']:.2f}），封板最早的 {em['x'].get('n')} 封单不够厚")
        else:
            leader, ltype = em['x'], 'divergence'
            reasons.append(f"龙头存在分歧：{em['x'].get('n')} 封板最早/封单最厚（情绪龙头），{cap['x'].get('n')} 成交额最大（容量核心），互不压到对方，无法唯一确认")
        lb = next(f for f in feat if f['code'] == leader.get('c'))
        reasons.append(f"{_hhmm(lb['fbt'])}封板·{lb['lbc']}连板·开板{lb['zbc']}次·封单{lb['fund']/1e8:.2f}亿·成交{lb['amount']/1e8:.2f}亿·换手{lb['hs']:.1f}%")
        if lb['zbc'] >= 3:
            reasons.append('⚠ 开板≥3次，封板稳定性差')
        if lb['lbc'] >= 5:
            reasons.append('⚠ 高位连板（≥5板），核按钮风险')
        if sec in top_secs:
            reasons.append(f'板块涨停{len(lst)}只，属全场前3强题材，扩散基础在')
        else:
            reasons.append(f'板块涨停{len(lst)}只，但不在全场前3强题材，题材热度一般')
        out.append({'sec': sec, 'leader': leader, 'ltype': ltype, 'reasons': reasons,
                    'emotion': em, 'capacity': cap, 'feat': feat})
    return out


def _follow_score_v2(cand, leader_info, sec_rows):
    """候选 100 分研究评分。返回 (score, detail, veto, missing)。
    cand 需含 pct/turn/amount/lb（clist 或构造）；_k 为 K线近况。"""
    k = cand.get('_k') or {}
    veto, missing, detail = [], [], {}
    nm = str(cand.get('name') or '')
    if 'ST' in nm.upper() or '*ST' in nm.upper():
        veto.append('ST/退市风险')
    if k.get('pos60') is not None and k['pos60'] > 0.9:
        veto.append(f"60日位置{k['pos60']:.2f}>0.9 高位")
    if k.get('g5') is not None and k['g5'] > 25:
        veto.append(f"5日涨幅{k['g5']:.0f}%>25% 追高")
    # 盘中主动性/相对强度（init，25）
    pct = cand.get('pct')
    lb = cand.get('lb')
    init = 0.0
    if pct is None:
        missing.append('盘中涨幅')
    else:
        if pct >= 2:
            init += 8
        mids = [r.get('pct') for r in sec_rows if r.get('pct') is not None]
        if mids:
            import statistics
            midp = statistics.median(mids)
            if pct >= midp:
                init += 7
        if lb is not None and lb >= 1.2:
            init += 5
        if pct >= 0:
            init += 5
    init = min(init, 25)
    # 量能/承接（vol，20）
    vol = 0.0
    vshr = k.get('vshr')
    if vshr is None:
        missing.append('量能比')
    else:
        if vshr >= 1.2:
            vol += 8
        if vshr >= 1.5:
            vol += 4
    if pct is not None:
        vol += 6        # 当日上涨/承接基础分（收盘位置日线无法精确，留 6 分基础）
    if lb is not None and lb >= 1.5:
        vol += 2
    vol = min(vol, 20)
    # 价格位置/预期差（pos，15）
    pos = 0.0
    if k.get('pos60') is None:
        missing.append('60日位置')
    elif k['pos60'] < 0.4:
        pos += 8
    elif k['pos60'] < 0.6:
        pos += 6
    if k.get('pos60') is not None and k['pos60'] < 0.75:
        pos += 7        # 低位天然有距前高压位空间（预期差）
    pos = min(pos, 15)
    # 板块整体强度（sector，10）
    sector = 0.0
    sec_count = len(sec_rows)
    if sec_count >= 5:
        sector += 6
    if sec_count >= 3:
        sector += 4
    sector = min(sector, 10)
    # 流动性/风险（liq，5）
    liq = 0.0
    amount = cand.get('amount')
    turn = cand.get('turn')
    if amount is None:
        missing.append('成交额')
    elif amount >= 1e8:
        liq += 3
    if turn is None:
        missing.append('换手率')
    elif 3 <= turn <= 20:
        liq += 2
    detail = {'rel': round(_FOLLOW2['rel'], 0), 'init': round(init, 0), 'vol': round(vol, 0),
              'pos': round(pos, 0), 'sector': round(sector, 0), 'liq': round(liq, 0)}
    total = sum(detail.values()) if not veto else 0
    return round(total, 0), detail, veto, missing


def _follow_confirm(cand, leader_info, sec_rows):
    """区分 跟涨信号已确认 / 潜在候选待确认（不把关联当已确认）。"""
    pct = cand.get('pct')
    lb = cand.get('lb')
    vshr = (cand.get('_k') or {}).get('vshr')
    mids = [r.get('pct') for r in sec_rows if r.get('pct') is not None]
    if not mids:
        return '数据不足，无法确认'
    import statistics
    midp = statistics.median(mids)
    if pct is not None and pct >= 2 and pct >= midp and ((lb is not None and lb >= 1.2) or (vshr is not None and vshr >= 1.2)):
        return '跟涨信号已确认'
    if pct is not None and pct >= 2:
        return '跟涨信号已确认' if pct >= midp * 1.2 else '潜在候选（有待确认）'
    return '潜在候选（待确认）'


FOLLOW_V2_PROMPT = """你是一线游资，现在是收盘后或盘中，任务：从已确认的板块龙头出发，给出该板块"待涨埋伏票"的可执行方案。
仓位仪表盘(全天其他模块共用，不得矛盾)：{position_gauge}
━━━ 第一阶段：板块健康度(先判断这个板块现在能不能埋伏) ━━━
输入(系统已实时算好，直接使用)：{leader_input}
板块今日涨停名单(全部已涨停，禁进picks，仅作强度证据)：{zt_list}
用三行大白话输出：
1. 龙头封板质量：强/中/弱 + 依据，会不会炸板
2. 板块今日强度：涨停N只/炸板N只/在全市场排位，是合力还是独苗
3. 埋伏窗口判定：三选一——【可埋伏】/【只可轻仓埋伏】/【不可埋伏】，并一句话说明对下面候选的影响
━━━ 第二阶段：龙二龙三埋伏方案(核心输出) ━━━
候选池(系统已算好分项)：{candidates}
埋伏铁律：
1. 【当日未涨停】才叫埋伏
2. 【共振传导链】：why必须写完整三段——"龙头XX涨停封板 → 资金沿产业链/同题材外溢 → 它是下一个被盯上的，因为(位置低/贴5日线/有建仓痕迹/筹码真空，至少两条实证)"，用连贯大白话写，不要条目堆砌
3. 【低位优先 + 建仓痕迹优先】：龙头≥4板高位时，picks必须全是未涨停的低位有建仓痕迹的补涨票；无建仓痕迹的降为第二优先级或否决
4. 【底仓逻辑关·强制】：候选票必须先过深挖铁律关——本质（一句话大白话）+暗线业务（具体产品+阶段+对业绩真实贡献，写不出写「未见明确暗线业务」，禁「相关/涉及/布局/受益于」糊弄）+真实关联与弹性（与龙头同链实受益/沾边/纯蹭+弹性大小）+为什么是它+破灭点+动作。没有清晰暗线业务或弹性不足的票直接否决，不进picks。picks里每只先写底仓逻辑，再写买点止损。
5. 【禁止偷懒】：哪怕分数不高，也要挑出相对最值得埋伏的1-2只写全方案
6. 【输出前自问】：如果不推这只票，最硬的理由是什么？理由成立就否决。没有符合条件的标的时明确写「当前无符合条件的埋伏标的」，禁止硬凑。空推送是正确行为。
每只候选输出字段(全必填)：name/code/rel/d5_read/why/confirm/buy/stop/grade/pos_score
picks最多2只；veto非空的候选不进picks。
━━━ 输出 JSON(不要其他文字) ━━━
{"board_health":{"leader":"...","seal":"...","sector":"...","window":"...","missed":"..."},"picks":[...],"risk":"..."}
━━━ 自检(输出前逐条过) ━━━
1. 确认picks里没有混入当日已涨停的票；有=作废重写
2. 确认龙头≥4板时picks全是低位未涨停且有建仓痕迹的票
3. 确认每只pick过了底仓逻辑关（有清晰暗线业务+弹性），没过关的已否决
4. 确认每只候选的why有完整传导链
5. 确认confirm/buy/stop可观察、有具体价格
6. 确认无万能句；有=改写
7. 确认与仓位仪表盘不矛盾
8. 确认先自问了「如果不推这只票，最硬的理由是什么」
全部通过，结尾输出「自检通过」。"""


def _render_follow_v2(sec, li, data, cand_payload):
    """跟涨三步走 v2 渲染：board_health(封板/板块/窗口) + picks + risk。"""
    bh = data.get('board_health') or {}
    picks = data.get('picks') or []
    risk = data.get('risk') or ''
    lt = {'emotion': '短线情绪龙头', 'capacity': '板块容量核心', 'divergence': '龙头存在分歧'}.get(li['ltype'], li['ltype'])
    d5map = {str(cd.get('code')): cd.get('d5') or [] for cd in cand_payload}
    b = [f'<div style="font-size:15px;font-weight:800;color:#ffd43b;">🎯 埋伏方向：{sec}板块（龙头已涨停·仅作方向参考）</div>']
    b.append(f'<div style="margin-top:3px;font-size:12px;color:#66d9e8;">🏷️ 类型：{lt} ｜ 板块：{sec}（涨停{len(li["feat"])}只）</div>')
    b.append(f'<div style="margin-top:3px;font-size:12px;color:#9aa4b8;">🔍 判定依据：{bh.get("leader","") or "; ".join(str(s) for s in li["reasons"])}</div>')
    if bh.get('seal'):
        b.append(f'<div style="margin-top:4px;font-size:12px;color:#ffd43b;">🧊 封板质量：{bh.get("seal","")}</div>')
    if bh.get('sector'):
        b.append(f'<div style="margin-top:3px;font-size:12px;color:#66d9e8;">📊 板块强度：{bh.get("sector","")}</div>')
    if bh.get('window'):
        w = bh.get('window', '')
        if '可埋伏' in w and '只可轻仓' not in w and '不可' not in w:
            wc = '#52c41a'
        elif '轻仓' in w:
            wc = '#ffd43b'
        else:
            wc = '#ff6b6b'
        b.append(f'<div style="margin-top:3px;font-size:12px;color:{wc};">🚪 埋伏窗口：{w}</div>')
    if bh.get('missed'):
        b.append(f'<div style="margin-top:3px;font-size:12px;color:#9aa4b8;">⏭️ 已错过涨停（仅作强度证据）：{bh.get("missed","")}</div>')
    if picks:
        b.append(f'<div style="margin-top:8px;font-size:13px;font-weight:800;color:#ff6b6b;">🎯 待涨埋伏票·介入方案（龙头已涨停，埋伏这些还没涨的）</div>')
        for p in picks:
            g = p.get('grade', '')
            gc = '#ffd43b' if '第一' in g else ('#66d9e8' if '第二' in g else '#9aa4b8')
            b.append(f'<div style="margin-top:6px;font-size:13px;color:#fff;">· <b>{p.get("name","")}（{p.get("code","")}）</b> <span style="color:{gc};font-size:12px;">{g}</span> <span style="color:#9aa4b8;font-size:12px;">评分{p.get("pos_score","")}</span></div>')
            b.append(f'<div style="margin:2px 0 0 14px;font-size:12px;color:#9aa4b8;">关系：{p.get("rel","")}</div>')
            b.append(f'<div style="margin:2px 0 0 14px;font-size:12px;color:#fff;">跟涨理由：{p.get("why","")}</div>')
            _d5 = d5map.get(str(p.get('code'))) or []
            if _d5:
                _d5_txt = ' ｜ '.join(f'<span style="color:{RED if x["pct"]>=0 else GREEN};">{x["d"]} {("+" if x["pct"]>=0 else "")}{x["pct"]}%</span>' for x in _d5)
                b.append(f'<div style="margin:2px 0 0 14px;font-size:12px;color:#9aa4b8;">📅 近5日：{_d5_txt}</div>')
            if p.get('d5_read'):
                b.append(f'<div style="margin:2px 0 0 14px;font-size:12px;color:#66d9e8;">🔗 个股深挖：{p.get("d5_read","")}</div>')
            b.append(f'<div style="margin:2px 0 0 14px;font-size:12px;color:#52c41a;">✅ 确认条件：{p.get("confirm","")}</div>')
            b.append(f'<div style="margin:2px 0 0 14px;font-size:12px;color:#ff6b6b;">⛔ 失效条件：{p.get("fail","") or "破5日线无条件止损"}</div>')
            if p.get('buy') and p.get('buy') != '无' and '等confirm' not in str(p.get('buy')):
                b.append(f'<div style="margin:2px 0 0 14px;font-size:12px;color:#ffd43b;">💰 买点：{p.get("buy","")} ｜ 🛑 止损：{p.get("stop","")} ｜ 📐 仓位：{p.get("pos","") or "1成试探"}</div>')
            else:
                b.append(f'<div style="margin:2px 0 0 14px;font-size:12px;color:#9aa4b8;">💰 买点：{p.get("buy","等confirm触发")} ｜ 🛑 止损：{p.get("stop","无")}</div>')
    else:
        b.append(f'<div style="margin-top:6px;font-size:12px;color:#9aa4b8;">板块内暂无介入条件（逐票原因见下方风险）</div>')
    if risk:
        b.append(f'<div style="margin-top:6px;font-size:12px;color:#ff6b6b;">⚠️ 风险：{risk}</div>')
    return '<div style="margin-top:10px;padding:10px;background:#1c2230;border-left:4px solid #ffd43b;border-radius:8px;">' + ''.join(b) + '</div>'


def build_followup(date=None):
    """跟涨三步走 v2：龙头综合判定(含分歧) → 100分评分候选 → 盘中确认 → A10B 大白话 → HTML。
    date: YYYYMMDD（默认今天；盘中/收盘用当天）。返回 (html, None)；无可推返回 (None, 原因)。"""
    day = date or datetime.now().strftime('%Y%m%d')
    pool = _follow_pool(day)
    if not pool:
        return None, '当日无涨停池数据'
    leaders2 = _follow_leader_v2(pool)
    if not leaders2:
        return None, '今日无满足条件的强势板块龙头'
    rows = _clist_gainers()
    items = []
    for li in leaders2[:2]:
        sec = li['sec']
        sec_rows = [r for r in rows if _sec_clean(r.get('industry') or '') == sec or
                    (sec and (_sec_clean(r.get('industry') or '') in sec or sec in _sec_clean(r.get('industry') or '')))]
        cands = _follow_candidates(li['leader'], rows, _FOLLOW_MAX_CANDS)
        cand_payload = []
        for c in cands:
            score, detail, veto, missing = _follow_score_v2(c, li, sec_rows)
            confirm = _follow_confirm(c, li, sec_rows)
            cand_payload.append({'name': c.get('name'), 'code': c.get('code'),
                                 'pct': c.get('pct'), 'turn': c.get('turn'),
                                 'amount': c.get('amount'), 'lb': c.get('lb'),
                                 'score': score, 'detail': detail, 'veto': veto,
                                 'missing': missing, 'confirm': confirm,
                                 'k': c.get('_k'), 'f10': _stock_f10(c.get('code')), 'd5': _stock_daily5(c.get('code'))})
        items.append({'leader': {'name': li['leader'].get('n'), 'code': li['leader'].get('c'),
                                 'ltype': li['ltype'],
                                 'reasons': '；'.join(li['reasons']),
                                 'f10': _stock_f10(li['leader'].get('c') or ''),
                                 'news': _stock_news(li['leader'].get('n') or '', li['leader'].get('c') or '')},
                      'sector': {'name': sec, 'count': len(sec_rows)},
                      'candidates': cand_payload})
    _g = load_position_gauge()
    _g_txt = (f'当前仓位仪表盘：{_g.get("suggest", "")}（来自 {_g.get("source", "")}），风险提示不得与其矛盾；\n' if _g else '仓位仪表盘未生成；\n')
    blocks = []
    for li in leaders2[:2]:
        sec = li['sec']
        sec_rows = [r for r in rows if _sec_clean(r.get('industry') or '') == sec or
                    (sec and (_sec_clean(r.get('industry') or '') in sec or sec in _sec_clean(r.get('industry') or '')))]
        cands = _follow_candidates(li['leader'], rows, _FOLLOW_MAX_CANDS)
        cand_payload = []
        cand_lines = []
        for c in cands:
            score, detail, veto, missing = _follow_score_v2(c, li, sec_rows)
            confirm = _follow_confirm(c, li, sec_rows)
            k = c.get('_k') or {}
            d5 = _stock_daily5(c.get('code'))
            cand_payload.append({'name': c.get('name'), 'code': c.get('code'),
                                 'pct': c.get('pct'), 'turn': c.get('turn'),
                                 'amount': c.get('amount'), 'lb': c.get('lb'),
                                 'score': score, 'detail': detail, 'veto': veto,
                                 'missing': missing, 'confirm': confirm,
                                 'k': k, 'f10': _stock_f10(c.get('code')), 'd5': d5})
            cand_lines.append(
                f"- {c.get('name')}({c.get('code')}) 现价涨幅{c.get('pct')}% 换手{c.get('turn')} 成交额{c.get('amount')} 量比{c.get('lb')} "
                f"pos60={k.get('pos60')} ratio_ma5={k.get('ratio_ma5')} g5={k.get('g5')}% vshr={k.get('vshr')} "
                f"d5={json.dumps(d5, ensure_ascii=False)} score={score} 分项={detail} veto={veto} missing={missing} confirm={confirm}")
        cand_txt = '\n'.join(cand_lines) if cand_lines else '(候选池为空：板块内全部已涨停或已被过滤)'
        lb = next((f for f in li['feat'] if f['code'] == str(li['leader'].get('c') or '')), li['feat'][0])
        lead_txt = (f"{li['leader'].get('n')}({li['leader'].get('c')}) {lb['lbc']}连板 {_hhmm(lb['fbt'])}封板 开板{lb['zbc']}次 "
                    f"封单{lb['fund']/1e8:.2f}亿 成交{lb['amount']/1e8:.2f}亿 换手{lb['hs']:.1f}% 板块涨停{len(li['feat'])}只")
        zt_txt = '；'.join(
            f"{f['x'].get('n')}({f['code']}){f['lbc']}板·封单{f['fund']/1e8:.2f}亿·成交{f['amount']/1e8:.2f}亿"
            for f in li['feat'] if f['code'] != str(li['leader'].get('c') or '')) or '(板块仅龙头一只涨停)'
        fmt = (FOLLOW_V2_PROMPT.replace('{position_gauge}', _g_txt.strip())
               .replace('{leader_input}', lead_txt)
               .replace('{zt_list}', zt_txt)
               .replace('{candidates}', cand_txt))
        t = ask_deepseek({'task': 'follow_up_v2', 'items': cand_payload, 'format': fmt}, purpose='follow')
        if not t:
            continue
        import re as _re
        _m = _re.search(r'\{.*\}', t, _re.S)
        _raw = _m.group(0) if _m else t
        try:
            data = json.loads(_raw)
        except Exception:
            data = None
        if not data:
            continue
        blocks.append(_render_follow_v2(sec, li, data, cand_payload))
    if not blocks:
        return None, '解析后无内容'
    if not blocks:
        return None, '解析后无内容'
    inner = ('<div style="font-size:18px;font-weight:800;color:#ffd43b;">⚡ 跟涨三步走·埋伏补涨 v2</div>'
             + f'<div style="margin-top:2px;font-size:12px;color:#9aa4b8;">先确认龙头（含分歧识别）→ 100分评分排序候选 → 盘中确认信号才参与 → 破5日线止损</div>'
             + ''.join(blocks))
    return _wrap(inner, '⚡', '跟涨三步走·埋伏补涨'), None





# （用户指令 2026-11-04：突破回踩·主力成本锚「策略/复盘/推送」全链路已删除；
#  anchor/review/evaluate 三档 cron 与 slot 选项同步移除；保留 _last_trade_date 供其他模块使用）
def _last_trade_date():
    """最近交易日（含今天；从今天往回找最多12天）：扫描器数据基准日。"""
    from datetime import timedelta
    d = _bj_now()
    for _ in range(12):
        if is_trading_day(d.strftime('%Y-%m-%d')):
            return d.strftime('%Y-%m-%d')
        d = d - timedelta(days=1)
    return _bj_now().strftime('%Y-%m-%d')


# ============ 工单14：龙虎榜席位（晚 8 点后披露，先攒样本） ============
_LHB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
_LHB_PATH = os.path.join(_LHB_DIR, 'lhb_samples.jsonl')
# 公认一日游席位（只列少数几个，避免误伤）
_LHB_YIRIYOU = ('华鑫证券有限责任公司上海分公司', '国泰君安证券股份有限公司上海江苏路',
                '光大证券股份有限公司佛山绿景路', '华泰证券股份有限公司深圳益田路荣超商务中心')


def _lhb_q(rn, day):
    _u = ('https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=%s'
          '&columns=ALL&filter=(TRADE_DATE=%%27%s%%27)&pageNumber=1&pageSize=500&source=WEB&client=WEB'
          % (rn, day))
    try:
        _txt, _ok = _getm(_u, 'lhb_%s_%s' % (rn, day))
        if not _ok or not _txt:
            return []
        return (json.loads(_txt).get('result') or {}).get('data') or []
    except Exception:
        return []


def _lhb_score(a):
    """席位加减分：机构净买 +3 / 机构大幅净卖 -2 / 拉萨天团占比≥30% -2 / 一日游占比≥40% -2。"""
    _s = 0.0
    _b = float(a.get('buy') or 0)
    _inet = float(a.get('inst_net') or 0)
    if _inet > 0:
        _s += 3
    elif _inet < -0.3e8:
        _s -= 2
    if _b > 0:
        if float(a.get('lasa') or 0) / _b >= 0.30:
            _s -= 2
        if float(a.get('yiri') or 0) / _b >= 0.40:
            _s -= 2
    return _s


def _lhb_layer(day=None, need=1):
    """龙虎榜聚合（工单14）：机构净买 / 拉萨天团买入 / 一日游买入占比。
    当天没数据自动回退到前一日（最多退 5 天）。返回 (date, {code: {...}})。"""
    _base = datetime.now()
    _d0 = day or (_base.strftime('%Y-%m-%d') if need else _base.strftime('%Y-%m-%d'))
    _day = _d0
    _res = {}
    for _k in range(6):
        try:
            _day = (datetime.strptime(_d0, '%Y-%m-%d') - timedelta(days=_k)).strftime('%Y-%m-%d')
        except Exception:
            return _d0, {}
        _buy = _lhb_q('RPT_BILLBOARD_DAILYDETAILSBUY', _day)
        _sell = _lhb_q('RPT_BILLBOARD_DAILYDETAILSSELL', _day)
        if not _buy and not _sell:
            continue
        _agg = {}
        for r in _buy:
            _c = str(r.get('SECURITY_CODE') or '')
            if not _c:
                continue
            _nm = str(r.get('OPERATEDEPT_NAME') or '')
            _v = float(r.get('BUY') or 0)
            _a = _agg.setdefault(_c, {'name': '', 'inst_net': 0.0, 'lasa': 0.0,
                                      'yiri': 0.0, 'buy': 0.0, 'sell': 0.0})
            _a['buy'] += _v
            if '机构专用' in _nm:
                _a['inst_net'] += _v
            if '拉萨' in _nm:
                _a['lasa'] += _v
            if any(k in _nm for k in _LHB_YIRIYOU):
                _a['yiri'] += _v
        for r in _sell:
            _c = str(r.get('SECURITY_CODE') or '')
            if not _c:
                continue
            _nm = str(r.get('OPERATEDEPT_NAME') or '')
            _v = float(r.get('SELL') or 0)
            _a = _agg.setdefault(_c, {'name': '', 'inst_net': 0.0, 'lasa': 0.0,
                                      'yiri': 0.0, 'buy': 0.0, 'sell': 0.0})
            _a['sell'] += _v
            if '机构专用' in _nm:
                _a['inst_net'] -= _v
        for r in _lhb_q('RPT_DAILYBILLBOARD_DETAILSNEW', _day):
            _c = str(r.get('SECURITY_CODE') or '')
            if _c in _agg:
                _agg[_c]['name'] = str(r.get('SECURITY_NAME_ABBR') or '')
                _agg[_c]['chg'] = float(r.get('CHANGE_RATE') or 0)
                _agg[_c]['d1'] = r.get('D1_CLOSE_ADJCHRATE')
                _agg[_c]['d5'] = r.get('D5_CLOSE_ADJCHRATE')
        for _c, _a in _agg.items():
            _a['score'] = _lhb_score(_a)
        if _agg:
            _res = _agg
            break
    return _day, _res


def _lhb_save(day, lhb):
    """样本落盘（jsonl，一行一只票），供次日溢价统计；写失败只告警不影响推送。"""
    if not lhb:
        return 0
    try:
        os.makedirs(_LHB_DIR, exist_ok=True)
        _n = 0
        with open(_LHB_PATH, 'a', encoding='utf-8') as f:
            for _c, _a in lhb.items():
                f.write(json.dumps({'date': day, 'code': _c, 'name': _a.get('name'),
                                    'inst_net': round(float(_a.get('inst_net') or 0) / 1e8, 3),
                                    'lasa': round(float(_a.get('lasa') or 0) / 1e8, 3),
                                    'yiri': round(float(_a.get('yiri') or 0) / 1e8, 3),
                                    'buy': round(float(_a.get('buy') or 0) / 1e8, 3),
                                    'score': _lhb_score(_a),
                                    'chg': _a.get('chg'), 'd1': _a.get('d1'),
                                    'd5': _a.get('d5')}, ensure_ascii=False) + '\n')
                _n += 1
        return _n
    except Exception as e:
        print('[lhb] 样本落盘失败:', type(e).__name__, str(e)[:60])
        return 0


def _lhb_stats(min_n=15):
    """次日溢价统计（攒样本阶段）：按席位加减分分档看 D1 平均涨幅。样本不足如实返回。"""
    try:
        if not os.path.exists(_LHB_PATH):
            return {'ok': False, 'n': 0, 'why': '还没有样本'}
        _seen = {}
        for _ln in open(_LHB_PATH, encoding='utf-8').read().splitlines():
            if not _ln.strip():
                continue
            try:
                _r = json.loads(_ln)
            except Exception:
                continue
            _seen[(_r.get('date'), _r.get('code'))] = _r
        _rows = list(_seen.values())
        _v = [r for r in _rows if isinstance(r.get('d1'), (int, float))]
        if len(_v) < min_n:
            return {'ok': False, 'n': len(_v), 'why': '样本不足（需≥%d）' % min_n}
        _g = {'加分席位': [r for r in _v if (r.get('score') or 0) > 0],
              '减分席位': [r for r in _v if (r.get('score') or 0) < 0],
              '中性席位': [r for r in _v if (r.get('score') or 0) == 0]}
        _out = {'ok': True, 'n': len(_v)}
        for _k, _lst in _g.items():
            _out[_k] = {'n': len(_lst),
                        'd1': round(sum(float(r['d1']) for r in _lst) / len(_lst), 2) if _lst else None}
        return _out
    except Exception as e:
        return {'ok': False, 'n': 0, 'why': str(e)[:60]}


def _lhb_html(lhb, limit=5):
    """龙虎榜段（晚间汇总用）：按机构净买绝对值排序，标出扣分项。"""
    if not lhb:
        return ''
    _rows = sorted(lhb.items(), key=lambda kv: -abs(float(kv[1].get('inst_net') or 0)))[:limit]
    _html = ''
    for _c, _a in _rows:
        _b = float(_a.get('buy') or 0)
        _bits = []
        _inet = float(_a.get('inst_net') or 0)
        if _inet:
            _bits.append('<span style="color:%s;">机构净%s%.2f亿</span>'
                         % (TEAL if _inet > 0 else RED, '买' if _inet > 0 else '卖', abs(_inet) / 1e8))
        _lasa = float(_a.get('lasa') or 0)
        if _b > 0 and _lasa / _b >= 0.30:
            _bits.append('<span style="color:%s;">拉萨天团买%.2f亿(%.0f%%)</span>'
                         % (RED, _lasa / 1e8, _lasa / _b * 100))
        _yiri = float(_a.get('yiri') or 0)
        if _b > 0 and _yiri / _b >= 0.40:
            _bits.append('<span style="color:%s;">一日游占%.0f%%</span>' % (RED, _yiri / _b * 100))
        if not _bits:
            _bits.append('<span style="color:%s;">净买入%.2f亿</span>' % (GREY, _b / 1e8))
        _html += ('<div style="color:#ced4da;font-size:12px;margin-top:3px;">'
                  '<b style="color:#fff;">%s</b> <span style="color:%s;">%s</span> ｜ %s</div>'
                  % (_a.get('name') or _c, GREY, _c, ' ｜ '.join(_bits)))
    if not _html:
        return ''
    return ('<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">🐯 龙虎榜席位</div>'
            '<div style="background:#1c2230;border-left:4px solid ' + GOLD + ';border-radius:8px;padding:8px 10px;margin:5px 0;">'
            + _html
            + '<div style="color:' + GREY + ';font-size:11px;margin-top:4px;">机构净买加分、拉萨天团与一日游席位扣分；次日溢价样本仍在累积，暂不并入评分</div></div>')


def build_evening():
    """晚间消息汇总（北京 22:50）：今日A股全景 + 全球晚间行情/消息 → DS 大白话
    「今日大事 + 明日关注」。DS 失败/用尽 → 规则兜底（行情+新闻列表）。"""
    gl = _global_markets()
    news = []
    try:
        news = get_news(20)
    except Exception:
        pass
    d = None
    try:
        d = get_pools()
    except Exception:
        d = None
    # —— 顶部：今日A股全景 ——
    a_sec = ''
    if d:
        try:
            b, _, _, zbr = sentiment(get_indices(), d)
        except Exception:
            b, zbr = '震荡', 0.0
        tops_txt = '、'.join(n for n, _ in d['tops'][:5]) or '无'
        a_sec = (f'<div style="font-size:14px;">🔴涨停<b style="color:{RED}">{d["lu"]}</b> '
                 f'🟢炸板<b style="color:{GREEN}">{d["zb"]}</b> 🟢跌停<b style="color:{GREEN}">{d["dt"]}</b> '
                 f'最高<b style="color:{GOLD}">{d["max_lbc"]}板</b> ｜ 情绪 <b style="color:{_c(0)}">{b}</b>（炸板率{zbr*100:.0f}%）</div>'
                 f'<div style="margin-top:4px;font-size:13px;color:{TEAL};">今日主线：{tops_txt}</div>')
    else:
        a_sec = '<div style="color:' + GREY + ';font-size:13px;">A股盘面数据未取得</div>'
    markets_txt = '；'.join(f'{nm} {("未取得" if pct is None else "%+.2f%%" % pct)}' for nm, pct, _ in gl)
    # 事件驱动量化评分排序（晚间紧跟时事：重要事件优先，避免次要消息淹没重点）
    _ev_news = []
    _bj_e = _bj_now()
    for _nw in news:
        _e = _score_event(_nw, _bj_e)
        if _e is not None:
            _ev_news.append((_nw, _e))
    _ev_news.sort(key=lambda x: -x[1]['score'])
    ev_news = [x[0] for x in _ev_news] or news
    news_brief = [{'t': nw['title'], 's': (nw.get('summary') or '')[:50]} for nw in ev_news[:12]]
    # —— DS 大白话汇总 ——
    ds_html = ''
    if DEEPSEEK_KEY and news:
        fmt = (_TRADER_RULES + '\n'
               + '今日A股：{a_sec}\n'
               + '全球晚间行情：{markets}\n'
               + '今日+晚间消息（东财7x24）：\n{news}\n'
               + '把下面的今日A股、全球行情、今日+晚间消息消化后，用「朋友复盘聊天」式大白话总结，给用户今晚睡前能看懂、明天能用上的东西。\n'
               + '输出写成一段连贯的话，不分栏、不加【】标题、不用「1.2.3.」、不设问、不照抄新闻标题；\n'
               + '顺序是：先说今天盘面到底是什么状态（涨停/炸板/最高板直接读出来，别光念数字，讲清钱在往哪跑、明天能不能接）→ 再说消息面里真正有用的一两件（发生了什么、谁受益谁受伤、对应哪个题材哪只票、今天盘面有没有印证）→ 最后说明天最该防的一件事和对应动作。\n'
               + '整段不超过 8 句，句子短，像朋友睡前发的一段语音转文字；没有值得说的就写「今天平稳过渡」并说明原因。\n'
               + '输出风格：短段落、短句，像微信群里交易员朋友聊天，一段最多两三行；没有值得说的就写「今日无大事，平稳过渡」并说原因。')
        t = ask_deepseek({'task': 'evening_summary', 'a_sec': a_sec, 'markets': markets_txt,
                          'news': news_brief, 'format': fmt}, purpose='evening')
        ds_html = md2html(t) if t else ''
    if not ds_html:
        print('[evening] LLM 未返回且已禁规则版兜底，不推晚间汇总')
        return None
    _lhb_html_block = ''
    try:
        _lhb_day, _lhb = _lhb_layer()
        if _lhb:
            _lhb_save(_lhb_day, _lhb)
            _lhb_html_block = _lhb_html(_lhb)
    except Exception as _le:
        print('[lhb] 段渲染失败:', type(_le).__name__, str(_le)[:60])
    news_rows, _used_ds = _news_html_lines(ev_news, n=8, purpose_key='eve_news', max_show=12)
    inner = (f'<div style="font-size:15px;font-weight:800;color:#ff922b;">🇨🇳 今日A股全景</div>' + a_sec
             + f'<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">🌐 全球晚间行情</div>'
             + _global_markets_html(gl)
             + (f'<div style="margin-top:10px;padding:10px;background:#1c2230;border-left:4px solid {GOLD};border-radius:8px;font-size:13px;line-height:1.8;color:#e2e8f0;">🤖 今日大事 & 明日关注 & 最大风险：{ds_html}</div>' if ds_html else '')
             + _lhb_html_block
             + f'<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">📰 今日消息汇总（按事件强度）</div>'
             + news_rows)
    return _wrap(inner, '🌙', '晚间消息汇总')


def _hold_conflict_html(bad):
    """📢 消息-持仓冲突警报（新增G）：利空消息命中持仓名或持仓板块 → 独立小卡（强制点名持仓+建议）。无命中 → ''。"""
    if not bad:
        return ''
    hits = []
    for nw in bad:
        txt = (nw.get('title') or '') + (nw.get('summary') or '')
        for h in HOLDINGS:
            if (h['name'] and h['name'] in txt) or (h.get('sector') and h.get('sector') in txt):
                hits.append((h['name'], h.get('sector', ''), nw.get('title', '')))
                break
    if not hits:
        return ''
    rows = ''.join(f'<div style="color:#ff8787;font-size:13px;margin:3px 0;">· 持仓<b>{h}</b>（{sec}）：{t}</div>' for h, sec, t in hits)
    return ('<div style="margin-top:10px;padding:9px 11px;background:#2a1f22;border-left:4px solid #ff6b6b;border-radius:8px;">'
            f'<div style="font-size:14px;font-weight:800;color:#ff6b6b;">📢 持仓冲突警报</div>{rows}'
            '<div style="margin-top:4px;color:#ff8787;font-size:12px;">→ 建议：结合个股关键位处理——触止损减仓/破位离场；与持仓无关可忽略。</div></div>')


def build_news2h():
    """两小时市场消息汇总（北京 12:00/14:01/16:00）：利好/利空逐条大白话 +
    预期差 + 怎么跟/怎么避 + 明日操作建议（结合持仓关键位）。"""
    news = []
    try:
        news = get_news(60)
    except Exception:
        pass
    good, bad, neu = [], [], []
    for nw in news:
        tag, _c = classify_news((nw.get('title') or '') + (nw.get('summary') or ''))
        if tag in ('利好', '重大利好', '正面', '政策利好'):
            good.append(nw)
        elif tag in ('利空', '重大利空', '负面', '风险提示'):
            bad.append(nw)
        else:
            neu.append(nw)
    good_pairs = _news_ds_lines(good, 4, 'news2h_good') or [(g.get('title',''), '', '', '') for g in good[:4]]
    bad_pairs = _news_ds_lines(bad, 4, 'news2h_bad') or [(b.get('title',''), '', '', '') for b in bad[:4]]

    _brief_sum = {g.get('title', ''): (g.get('summary') or '')[:100] for g in good}
    _brief_sum.update({b.get('title', ''): (b.get('summary') or '')[:100] for b in bad})

    def _rows(pairs, is_good):
        if not pairs:
            return '<div style="color:' + GREY + ';font-size:12px;">今日无明显' + ('利好' if is_good else '利空') + '消息</div>'
        out = []
        for it in pairs:
            t0 = it[0]
            i, s2, w, a = (it[1], it[2], it[3], it[4]) if len(it) >= 5 else (it[1], '', it[2] if len(it) > 2 else '', it[3] if len(it) > 3 else '')
            i = _strip_pre(i, ('影响：', '影响:'))
            s2 = _strip_pre(s2, ('代表个股：', '代表个股:', '个股：', '个股:'))
            w = _strip_pre(w, ('大白话：', '大白话:', '人话：', '解读：'))
            a = _strip_pre(a, ('操作：', '操作:'))
            _sum = _brief_sum.get(t0, '')
            out.append(f'<div style="color:#fff;font-size:13px;margin:8px 0 0 0;">· {t0}</div>'
                       + (f'<div style="margin:2px 0 0 16px;color:{GREY};font-size:11px;">📰 {_sum}</div>' if _sum else '')
                       + (f'<div style="margin:2px 0 0 16px;color:{GOLD};font-size:12px;">🎯 影响：{i}</div>' if i else '')
                       + (f'<div style="margin:2px 0 0 16px;color:#b197fc;font-size:12px;">🏆 代表个股：{s2}</div>' if s2 else '')
                       + (f'<div style="margin:2px 0 0 16px;color:{TEAL};font-size:12px;">🧠 大白话：{w}</div>' if w else '')
                       + (f'<div style="margin:2px 0 8px 16px;color:{RED};font-size:12px;">💡 操作：{a}</div>' if a else ''))
        return ''.join(out)

    ds_html = ''
    if (MODELSCOPE_KEY or DEEPSEEK_KEY) and news:
        _g = load_position_gauge()
        _g_txt = (f'（当前仓位仪表盘：{_g.get("suggest", "")}，来自 {_g.get("source", "")}，不得与其矛盾）\n' if _g else '（仓位仪表盘未生成）\n')
        fmt = (_TRADER_RULES + '\n' + _g_txt
               + '当前消息：利好{good}｜利空{bad}｜其他/中性{neu}\n'
               + '请严格按以下格式输出（全大白话，禁模板句，不许加板块，不许罗列所有消息）：\n'
               + '【预期差】市场还没消化的1-2条（区分「已定价」与「未定价」；已定价禁止写成机会；没有写「今日无明显预期差，都是明牌」；只挑最重要的，禁止罗列）\n'
               + '【怎么跟/怎么避】具体动作1-2条（结合利好利空说买什么、躲什么；只给最重要的动作，禁止罗列）\n'
               + '【传染方向与暗线】这些消息最可能传染到哪个还没启动的题材/个股/板块（点名具体股+传染逻辑+暗线，最多2个方向；没有写「暂无明确传染方向」）\n'
               + '【明日操作建议】给明确仓位档位（用1-2成/2-4成/半仓/空仓这类明确数字）\n'
               + '【大白话总结】一句话（今天消息面对A股整体偏暖还是偏冷、最该记的一个点）')
        t = ask_deepseek({'task': 'news2h_summary',
                          'good': [g.get('title','')[:40] for g in good[:4]],
                          'bad': [b.get('title','')[:40] for b in bad[:4]],
                          'neu': '；'.join((n.get('title') or '')[:50] for n in neu[:8]) or '无',
                          'format': fmt}, purpose='news2h')
        if t:
            ds_html = md2html(t)
        else:
            print('[news2h] LLM 未返回且已禁规则版兜底，不推两小时消息卡')
            return None
    inner = (_hold_conflict_html(bad)
             + f'<div style="font-size:15px;font-weight:800;color:{RED};">🔴 今日利好（{len(good_pairs)}条）</div>'
             + _rows(good_pairs, True)
             + f'<div style="margin-top:10px;font-size:15px;font-weight:800;color:{GREEN};">🟢 今日利空（{len(bad_pairs)}条）</div>'
             + _rows(bad_pairs, False)
             + (f'<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">🤖 预期差 & 怎么跟</div>'
                f'<div style="padding:10px;background:#1c2230;border-left:4px solid {GOLD};border-radius:8px;font-size:13px;line-height:1.8;color:#e2e8f0;">{ds_html}</div>' if ds_html else '')
             + f'<div style="margin-top:8px;font-size:11px;color:{GREY};">不构成投资建议</div>')
    return _wrap(inner, '📰', '两小时市场消息汇总')


def _parse_ds_json(t):
    """解析 DS 返回的 JSON（容忍 markdown 代码块包裹）。失败返回 None。"""
    if not t:
        return None
    s2 = t.strip()
    if s2.count('```') >= 2:
        # 有 markdown 代码块：按 ``` 切段，取含 { 或 [ 的那段
        for seg in s2.split('```'):
            if '{' in seg or '[' in seg:
                s2 = seg
                break
    else:
        s2 = s2.replace('```', '').strip('`')
    s2 = s2.strip().strip('`')
    # 定位到第一个 { 或 [（容忍代码块语言标记残留）
    cand = [i for i in (s2.find('{'), s2.find('[')) if i >= 0]
    if cand:
        s2 = s2[min(cand):]
    try:
        d = json.loads(s2)
        items = d.get('items') or d.get('data') or []
        if not isinstance(items, list) or not items:
            return None
        out = []
        for it in items:
            if isinstance(it, dict) and (it.get('t') or it.get('title')):
                out.append((str(it.get('t') or it.get('title')),
                            str(it.get('i') or it.get('impact') or ''),
                            str(it.get('s') or it.get('stock') or ''),
                            str(it.get('w') or it.get('p') or it.get('note') or ''),
                            str(it.get('a') or it.get('op') or '')))
        return out or None
    except Exception:
        return None


def _news_ds_lines(news, n=10, purpose_key='news_brief'):
    """新闻逐条大白话解读：DS 一次调用批量解读，返回 [(标题, 大白话)]。
    无 LLM / 失败 / 解析失败 → 返回 None（调用方降级纯标题）。"""
    brief = [{'t': nw.get('title', ''), 's': (nw.get('summary') or '')[:120]} for nw in news[:n]]
    if not brief:
        return None
    if not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return None
    fmt = ('你是10年A股超短线交易员。下面{num}条财经消息，逐条完整深度挖掘，不许偷懒：\n'
           '【深挖铁律·落到代表股必做】提到代表股必须完整执行「股票深挖铁律」：本质（一句话大白话，禁标签糊弄）+暗线业务（具体产品+阶段+对业绩真实贡献，挖不出写「未见明确暗线业务」，禁「相关/涉及/布局/受益于」糊弄）+真实关联与弹性（实受益/沾边/纯蹭+弹性大小）+为什么是它+破灭点+动作。没有硬逻辑的写「逻辑不硬，不碰」。\n'
           '只输出 JSON，不要任何其他文字，格式：\n'
           '{"items":[{"t":"消息标题","i":"影响：写清板块/题材，至少15字（猜不到写「暂看不出直接关联」，不许编）","s":"代表个股深挖：点名1-2只能代表这条消息的股票代码+名称，深挖它自己的逻辑（本质+暗线业务[具体产品+阶段+真实贡献]+真实关联与弹性+为什么它能代表+破灭点），至少30字，不许泛泛而谈","w":"大白话：一句话戳穿真假+为什么+怎么传导，至少25字","a":"操作：买/躲/看，写具体怎么应对（价位/条件/仓位）；逻辑不硬写「不碰」，至少20字"}]}\n'
           '必须覆盖全部{num}条，不许漏。每条 i/w/a 必须详细完整，禁止缩写、禁止「美股事A股不跟」这类敷衍，宁可长不要短。')
    t = ask_deepseek({'task': purpose_key, 'num': len(brief), 'news': brief, 'format': fmt},
                     purpose=purpose_key)
    pairs = _parse_ds_json(t)
    if pairs:
        # 后校验：每条 i/w/a 单独达标（防关键词缩写偷懒），不达标重试最多2次
        for _try in range(2):
            bad_row = [it for it in pairs
                       if len(it[1]) < 12 or (len(it) >= 5 and len(it[2]) < 20) or len(it[3]) < 12 or len(it[4]) < 10]
            if not bad_row:
                break
            t2 = ask_deepseek({'task': purpose_key, 'num': len(brief), 'news': brief,
                               'format': fmt + f'上次有{len(bad_row)}条输出太短不合格（{bad_row[0][0]}），这次每条影响≥20字、大白话≥20字、操作≥15字，禁止关键词缩写，宁可长不要短！'},
                              purpose=purpose_key + '_retry')
            p2 = _parse_ds_json(t2)
            if not p2:
                break
            pairs = p2
        # 标题以原始新闻为准（模型可能把长标题缩写成关键词）
        for k, it in enumerate(pairs):
            if k < len(brief):
                pairs[k] = (brief[k]['t'], it[1], it[2], it[3], it[4])
        print(f'[LLM] 新闻逐条解读 OK purpose={purpose_key} n={len(pairs)}')
    return pairs


def _strip_pre(s, pres):
    """去掉模型输出自带的『影响：』『大白话：』『操作：』前缀，防重复渲染。"""
    s = (s or '').strip()
    for p in pres:
        if s.startswith(p):
            return s[len(p):].strip()
    return s


def _news_html_lines(news, n=10, purpose_key='news_brief', max_show=15):
    """新闻区块 HTML：优先逐条大白话；DS 失败降级纯标题。
    返回 (html, 用了大白话 bool)。"""
    pairs = _news_ds_lines(news, n, purpose_key)
    _brief_sum = {nw.get('title', ''): (nw.get('summary') or '')[:100] for nw in news}
    if pairs:
        rows = []
        for it in pairs[:max_show]:
            t0 = it[0]
            i, s2, w, a = (it[1], it[2], it[3], it[4]) if len(it) >= 5 else (it[1], '', it[2] if len(it) > 2 else '', it[3] if len(it) > 3 else '')
            i = _strip_pre(i, ('影响：', '影响:'))
            s2 = _strip_pre(s2, ('代表个股：', '代表个股:', '个股：', '个股:'))
            w = _strip_pre(w, ('大白话：', '大白话:', '人话：', '解读：'))
            a = _strip_pre(a, ('操作：', '操作:'))
            _sum = _brief_sum.get(t0, '')
            rows.append(f'<div style="color:#ced4da;font-size:12px;margin:8px 0 0 0;">· {t0}</div>'
                        + (f'<div style="margin:2px 0 0 16px;color:{GREY};font-size:11px;">📰 {_sum}</div>' if _sum else '')
                        + (f'<div style="margin:2px 0 0 16px;color:{GOLD};font-size:12px;">🎯 影响：{i}</div>' if i else '')
                        + (f'<div style="margin:2px 0 0 16px;color:#b197fc;font-size:12px;">🏆 代表个股：{s2}</div>' if s2 else '')
                        + (f'<div style="margin:2px 0 0 16px;color:{TEAL};font-size:12px;">🧠 大白话：{w}</div>' if w else '')
                        + (f'<div style="margin:2px 0 8px 16px;color:{RED};font-size:12px;">💡 操作：{a}</div>' if a else ''))
        return '<div>' + ''.join(rows) + '</div>', True
    rows = ''.join(
        f'<div style="color:#ced4da;font-size:12px;margin:3px 0;">· {nw.get("ts","")[-5:]} {nw["title"]}</div>'
        for nw in news[:max_show])
    if not rows:
        rows = '<div style="color:' + GREY + ';font-size:13px;">消息未取得</div>'
    return '<div>' + rows + '</div>', False


def _early_watch(market_bias='震荡'):
    """两级盘中预警（资金量能放大优先，不等涨停；市场情绪偏空时门槛上调）：
    - 启动埋伏：3.5%≤涨幅<6.5%（启动早期）——量比≥2.0、换手≥3%、分时站上昨收（分时均线近似）、
      同题材≥2只放量跟风（板块共振，避免孤立个股噪音）；
    - 逼近涨停：7%≤涨幅<9.5%（接近涨停）——量比≥1.8、资金抢筹（封单开始堆积）。
    偏空（市场情绪闸门）：所有涨幅门槛+1pp、量比门槛+0.5。
    【口径说明】批量行情接口无分时均价字段，"站上分时均线"用 price≥昨收 近似（当日分时走强代理），
    后续可换逐只分时接口增强。
    返回 (埋伏列表, 逼近列表)。"""
    try:
        rows = _clist_gainers()
    except Exception:
        return [], []
    up_bias = 1.0 if market_bias == '偏空' else 0.0
    lb_bias = 0.5 if market_bias == '偏空' else 0.0
    # 题材内放量跟风家数（涨幅≥2% 且量比≥1.5 即算"放量跟风"，不再要求涨停）
    sec_cnt = {}
    for s in rows:
        s['industry'] = s.get('industry') or '其他'
        s['sec_clean'] = _sec_clean(s['industry']) or '其他'
        if s['pct'] >= 2.0 and s['lb'] >= 1.5:
            sec_cnt[s['sec_clean']] = sec_cnt.get(s['sec_clean'], 0) + 1
    ambush, near = [], []
    for s in rows:
        if s['pct'] >= 9.5:
            continue
        if s['pct'] >= 7.0 + up_bias:
            if s['lb'] >= 1.8 + lb_bias:
                s['fzn'] = sec_cnt.get(s['sec_clean'], 0)
                near.append(s)
        elif s['pct'] >= 3.5 + up_bias:
            if (s['lb'] >= 2.0 + lb_bias and s['turn'] >= 3.0
                    and s['price'] >= s['prev']                       # 分时站上昨收（分时均线近似）
                    and sec_cnt.get(s['sec_clean'], 0) >= 2):          # 同题材≥2只跟风
                s['fzn'] = sec_cnt.get(s['sec_clean'], 0)
                ambush.append(s)
    return ambush, near


FORCE_SLOT = None  # --force 强制时段（演示/手动指定；watch 跳过盘中时段闸门）


def _strength(sg):
    """信号强度档位（代码评分阈值实算；"能不能上"交 AI 判读）。"""
    t = sg.get('type', '')
    if sg.get('score', 0) >= 9 and t in ('启动埋伏', '老龙头回流'):
        return 'S', '档位S（评分≥9，代码阈值）'
    if sg.get('score', 0) >= 7:
        return 'A', '档位A（评分≥7，代码阈值）'
    return 'B', '档位B（评分<7，代码阈值）'


def _quote_card(sg):
    """为信号卡补实时三要素：当前价/建议买入区间（现价×0.995~×1.01）/止损（买入价-3%优先，分时均线参考）。
    行情未取得时如实标 '—'，不伪造。"""
    cur = sg.get('price')
    try:
        sym = ('sh' if sg['code'].startswith('6') else 'sz') + sg['code']
        q = _qt(sym)
        if q and q['price']:
            cur = q['price']
    except Exception:
        pass
    if not cur:
        sg['cur'] = '—'
        sg['buy_low'] = sg['buy_high'] = '—'
        sg['stop'] = sg.get('stop', '破位-3%走')
        return sg
    cur = float(cur)
    buy_low = round(cur * 0.995, 2)
    buy_high = round(cur * 1.01, 2)
    stop = round(buy_low * 0.97, 2)  # 止损固定买入价-3%（优先执行）
    sg['cur'] = f'{cur:.2f}'
    sg['buy_low'] = f'{buy_low:.2f}'
    sg['buy_high'] = f'{buy_high:.2f}'
    sg['stop'] = f'{stop:.2f}（买入价-3%优先执行）'
    return sg


_FINAL_BRIDGE = None
_FINAL_BRIDGE_TRIED = False


def _final_pair(code, name, bars, q, ctx, auction_score=None):
    """统一评分仲裁（工单1）：返回 (final_score, 子分串)。

    桥或聚合层任何异常都返回 (None, '')，卡片退回原有格式，绝不阻断推送。
    只做计算，不推送、不写账本。
    """
    global _FINAL_BRIDGE, _FINAL_BRIDGE_TRIED
    if not _FINAL_BRIDGE_TRIED:
        _FINAL_BRIDGE_TRIED = True
        try:
            import importlib.util as _iu
            _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            _p = os.path.join(_root, 'tools', 'cloud_score_bridge.py')
            _sp = _iu.spec_from_file_location('qm_score_bridge', _p)
            _md = _iu.module_from_spec(_sp)
            _sp.loader.exec_module(_md)
            _FINAL_BRIDGE = _md
        except Exception as e:
            print('[final] 评分桥加载失败: %s' % str(e)[:70])
    if _FINAL_BRIDGE is None:
        return None, ''
    try:
        out = _FINAL_BRIDGE.score_all(
            code, name or '', bars=bars, quote=q, ctx=ctx,
            auction_score=auction_score,
            base_dir=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        agg = out.get('agg') or {}
        subs = '|'.join('%s%.0f' % (e['name_cn'], e['score'])
                        for e in (agg.get('engines') or [])
                        if e.get('status') == 'ok' and e.get('weight', 0) > 0)
        return agg.get('final_score'), subs
    except Exception as e:
        print('[final] %s 合成失败: %s' % (code, str(e)[:70]))
        return None, ''


def _factor_for_spot(sg, d):
    """盘中异动票的因子体检（情绪/量价 + 硬闸）。任何异常返回 None，卡片退回原样。
    K线走 get_klines（已带东财 fallback），量比在腾讯 f43 为 0（涨停封板）时用 当日量/5日均量 自算。"""
    if not _FACTOR_OK or not isinstance(sg, dict):
        return None
    code = str(sg.get('code') or '')
    if len(code) != 6:
        return None
    try:
        sym = ('sh' if code.startswith('6') else ('bj' if code.startswith(('4', '8')) else 'sz')) + code
        bars = get_klines(sym, 130)
        _today = _bj_now().strftime('%Y-%m-%d')
        bars_ex = [r for r in (bars or []) if str(r[0]) != _today]
        vol_avg5 = None
        if len(bars_ex) >= 5:
            vs = [float(r[5]) for r in bars_ex[-5:] if float(r[5]) > 0]
            vol_avg5 = sum(vs) / len(vs) if len(vs) == 5 else None
        q = _qt(sym) or {}
        _lb = q.get('lb') if q.get('lb') else sg.get('lb')
        _vol = q.get('vol') if q.get('vol') else sg.get('vol')
        pv = _fe.score_price_volume(bars=bars, lb=_lb,
                                    vol_today=_vol, vol_avg5=vol_avg5)
        dd = d or {}
        emo = _fe.score_emotion(lu=dd.get('lu'), zb=dd.get('zb'),
                                max_lbc=dd.get('max_lbc'), yest_premium_pct=None)
        _lbc = sg.get('lbc')
        if not _lbc and bars_ex:
            # 盘中卡拿不到连板数时，从日K推连续涨停天数（主板≥9.5%，创业板/科创≥19.5%）
            _thr = 9.5 if code.startswith(('60', '00')) else 19.5
            _n = 0
            for _i in range(len(bars_ex) - 1, 0, -1):
                try:
                    _p0 = float(bars_ex[_i - 1][2])
                    _p1 = float(bars_ex[_i][2])
                except (TypeError, ValueError):
                    break
                if _p0 > 0 and (_p1 / _p0 - 1) * 100 >= _thr:
                    _n += 1
                else:
                    break
            _lbc = _n or None
        vt = _fe.veto_check(name=sg.get('n') or sg.get('name'), code=code,
                            float_cap_yi=sg.get('float_cap') or sg.get('cap') or q.get('cap'),
                            lbc=_lbc, turnover_pct=sg.get('turn') or q.get('turn'),
                            list_days=None, bars=bars_ex,
                            price=sg.get('cur') or sg.get('price'))
        # 第3步补齐：资金/题材/动量（与竞价卡、收盘因子榜同口径）
        _pct = float(q.get('pct') or 0)
        _is_lu = (_pct >= 9.5) if code.startswith(('60', '00')) else (_pct >= 19.5)
        zj = _fe.score_fund(out_vol=q.get('out'), in_vol=q.get('in'),
                            bars=bars_ex, is_limit_up=_is_lu)
        dl = _fe.score_momentum(bars=bars_ex)
        _sec = _sec_clean(sg.get('sec') or sg.get('sec_clean') or '') or '其他'
        _heat = {}
        for _hn, _hsl in ((d or {}).get('tops') or []):
            try:
                _heat[_hn] = min(100, len(_hsl) * 20)
            except TypeError:
                continue
        tc = _fe.score_theme(theme_heat=_heat.get(_sec), relation='实受益')
        fs = {'jq': emo.get('score'), 'lj': pv.get('score'), 'zj': zj.get('score'),
              'tc': tc.get('score'), 'dl': dl.get('score')}
        comb = _fe.combine(auction_score=None, factor_scores=fs,
                   weights=_factor_weights())
        fin, subs = _final_pair(code, sg.get('n') or sg.get('name') or '', bars, q,
                                {'today': _today, 'lu': dd.get('lu'), 'zb': dd.get('zb'),
                                 'max_lbc': dd.get('max_lbc'), 'sec': _sec,
                                 'theme_heat': _heat}, auction_score=None)
        line = _fe.fmt_full_line(auction_score=None, jq=fs['jq'], lj=fs['lj'],
                                 zj=fs['zj'], tc=fs['tc'], dl=fs['dl'],
                                 factor_total=comb.get('factor_total'),
                                 combined=comb.get('combined'),
                                 veto=vt.get('reasons'),
                                 final=fin, final_subs=subs)
        return {'jq': fs['jq'], 'lj': fs['lj'], 'zj': fs['zj'], 'tc': fs['tc'], 'dl': fs['dl'],
                'total': comb.get('factor_total'), 'combined': comb.get('combined'),
                'final': fin, 'final_subs': subs,
                'vetoed': bool(vt.get('vetoed')), 'reasons': vt.get('reasons') or [],
                'unknown': vt.get('unknown') or [], 'line': line}
    except Exception as e:
        print(f'[factor] {code} 计算失败: {str(e)[:60]}')
        return None


def _factor_for_auction(s, heat, cnt, jq_res=None):
    """竞价观察卡的因子摘要。复用 _calc_resonance 已缓存的 s['_bars']（零成本，不重复拉 K 线）。

    情绪分是市场级指标，所有票相同 → 由调用方算一次传入 jq_res 复用。
    涨停票自动置 is_limit_up：腾讯快照封板时 f[7]外盘归零，内外盘差会假跌到 -1.0，
    该函数据此把内外盘项标「缺」按中性，避免最强连板票被判成最差资金流。
    返回 {'jq','lj','zj','tc','dl','total','combined','vetoed','reasons','unknown','line'}；异常返回 None。
    """
    if not _FACTOR_OK or not isinstance(s, dict):
        return None
    try:
        code = str(s.get('code') or '')
        if len(code) != 6:
            return None
        bars = list(s.get('_bars') or [])
        if len(bars) < 20:
            return None
        _today = _bj_now().strftime('%Y-%m-%d')
        bars_ex = [r for r in bars if str(r[0]) != _today] or bars
        vol_avg5 = None
        if len(bars_ex) >= 5:
            try:
                vs = [float(x[5]) for x in bars_ex[-5:]]
                vol_avg5 = sum(vs) / len(vs) if len(vs) == 5 else None
            except (TypeError, ValueError):
                vol_avg5 = None
        q = s.get('_q') or _qt(('sh' if code.startswith('6') else
                                ('bj' if code.startswith(('4', '8')) else 'sz')) + code) or {}
        _lb = q.get('lb') if q.get('lb') else s.get('lb')
        _vol = q.get('vol') if q.get('vol') else None
        lj = _fe.score_price_volume(bars=bars_ex, lb=_lb, vol_today=_vol, vol_avg5=vol_avg5)
        # 涨停判定：用当日涨幅（含竞价高开）判断是否封板
        _pct = float(s.get('pct') or 0)
        _is_lu = (_pct >= 9.5) if code.startswith(('60', '00')) else (_pct >= 19.5)
        zj = _fe.score_fund(out_vol=q.get('out'), in_vol=q.get('in'),
                            bars=bars_ex, is_limit_up=_is_lu)
        dl = _fe.score_momentum(bars=bars_ex)
        _sec = _sec_clean(s.get('industry') or '') or '其他'
        tc = _fe.score_theme(theme_heat=(heat or {}).get(_sec), relation='实受益')
        vt = _fe.veto_check(name=s.get('name'), code=code,
                            float_cap_yi=s.get('cap') or q.get('cap'),
                            lbc=s.get('lbc'), turnover_pct=s.get('turn') or q.get('turn'),
                            list_days=None, bars=bars_ex, price=s.get('price'))
        fs = {'jq': (jq_res or {}).get('score'), 'lj': lj.get('score'),
              'zj': zj.get('score'), 'tc': tc.get('score'), 'dl': dl.get('score')}
        comb = _fe.combine(auction_score=s.get('score'), factor_scores=fs,
                   weights=_factor_weights())
        fin, subs = _final_pair(code, s.get('name') or '', bars, q,
                                {'today': _today, 'sec': _sec, 'theme_heat': heat,
                                 'max_lbc': s.get('lbc')}, auction_score=s.get('score'))
        line = _fe.fmt_full_line(auction_score=s.get('score'),
                                 jq=fs['jq'], lj=fs['lj'], zj=fs['zj'],
                                 tc=fs['tc'], dl=fs['dl'],
                                 factor_total=comb.get('factor_total'),
                                 combined=comb.get('combined'),
                                 veto=vt.get('reasons'),
                                 final=fin, final_subs=subs)
        miss = []
        for _nm, _r in (('情绪', jq_res), ('量价', lj), ('资金', zj), ('题材', tc), ('动量', dl)):
            if _r and _r.get('missing'):
                miss.append('%s:%s' % (_nm, ','.join(_r['missing'])))
        return {'jq': fs['jq'], 'lj': fs['lj'], 'zj': fs['zj'], 'tc': fs['tc'], 'dl': fs['dl'],
                'total': comb.get('factor_total'), 'combined': comb.get('combined'),
                'final': fin, 'final_subs': subs,
                'vetoed': bool(vt.get('vetoed')), 'reasons': vt.get('reasons') or [],
                'unknown': vt.get('unknown') or [], 'missing': miss, 'line': line}
    except Exception as e:
        print(f'[factor-auction] {s.get("code")} 计算失败: {str(e)[:60]}')
        return None


def _factor_board_top(d, topn=10, pool=15):
    """收盘复盘「当日因子榜 TOP10」：当日涨停池按连板数降序取前 pool 只算因子，按因子总分排序取 topn。

    规格要求「被否决票不得悄悄过滤」→ 被否决的照样入榜，用红色左边框 + ⛔原因标出。
    任何异常返回 ''，绝不阻断收盘复盘推送。
    """
    if not _FACTOR_OK or not isinstance(d, dict):
        return ''
    try:
        cand = []
        for _sec, _sts in (d.get('sectors') or {}).items():
            for st in (_sts or []):
                _c = str(st.get('c') or '')
                if len(_c) != 6:
                    continue
                cand.append({'code': _c, 'name': st.get('n') or st.get('name') or _c,
                             'lbc': int(st.get('lbc') or 0), 'sec': _sec})
        cand.sort(key=lambda x: -x['lbc'])
        cand = cand[:pool]
        if not cand:
            print('[factor-board] 涨停池为空，跳过因子榜')
            return ''
        heat = {}
        for _n, _s in (d.get('tops') or []):
            try:
                heat[_n] = min(100, len(_s) * 20)
            except TypeError:
                continue
        jq = _fe.score_emotion(lu=d.get('lu'), zb=d.get('zb'),
                               max_lbc=d.get('max_lbc'), yest_premium_pct=None)
        out = []
        _today = _bj_now().strftime('%Y-%m-%d')
        for c0 in cand:
            try:
                sym = ('sh' if c0['code'].startswith('6') else
                       ('bj' if c0['code'].startswith(('4', '8')) else 'sz')) + c0['code']
                bars = get_klines(sym, 40)
                if not bars or len(bars) < 20:
                    continue
                bars_ex = [x for x in bars if str(x[0]) != _today] or bars
                q = _qt(sym) or {}
                lj = _fe.score_price_volume(bars=bars_ex, lb=q.get('lb'))
                # 涨停池里的票必然封板：外盘 f[7] 归零，置 is_limit_up 让内外盘项标缺按中性
                zj = _fe.score_fund(out_vol=q.get('out'), in_vol=q.get('in'),
                                    bars=bars_ex, is_limit_up=True)
                dl = _fe.score_momentum(bars=bars_ex)
                tc = _fe.score_theme(theme_heat=heat.get(c0['sec']), relation='实受益')
                vt = _fe.veto_check(name=c0['name'], code=c0['code'],
                                    float_cap_yi=q.get('cap'), lbc=c0['lbc'],
                                    turnover_pct=q.get('turn'), bars=bars_ex)
                fs = {'jq': jq.get('score'), 'lj': lj.get('score'), 'zj': zj.get('score'),
                      'tc': tc.get('score'), 'dl': dl.get('score')}
                comb = _fe.combine(auction_score=None, factor_scores=fs,
                           weights=_factor_weights())
                out.append({'name': c0['name'], 'code': c0['code'], 'lbc': c0['lbc'],
                            'sec': c0['sec'], 'total': comb.get('factor_total') or 0,
                            'fs': fs, 'vetoed': bool(vt.get('vetoed')),
                            'reasons': vt.get('reasons') or [],
                            'price': q.get('price'), 'combined': comb.get('combined')})
            except Exception as _ce:
                print('[factor-board] %s %s' % (c0.get('code'), str(_ce)[:40]))
                continue
        if not out:
            return ''
        out.sort(key=lambda x: -x['total'])
        try:
            _sig_rows = []
            for _o in out[:topn]:
                _sig_rows.append({'code': _o['code'], 'name': _o['name'],
                                  'price': _o.get('price'),
                                  'jq': _o['fs'].get('jq'), 'lj': _o['fs'].get('lj'),
                                  'zj': _o['fs'].get('zj'), 'tc': _o['fs'].get('tc'),
                                  'dl': _o['fs'].get('dl'), 'total': _o['total'],
                                  'combined': _o.get('combined'), 'vetoed': _o['vetoed']})
            _factor_signal_write('eod', _sig_rows)
        except Exception as _sig_e:
            print(f'[sigcsv] eod 接入异常 {_sig_e}')
        rr = ''
        for i, o in enumerate(out[:topn], 1):
            _col = '#ff6b6b' if o['vetoed'] else '#8ce99a'
            _vt = ('｜⛔%s' % '、'.join(o['reasons'])) if o['vetoed'] else ''
            rr += (f'<div style="background:#1f2635;border-left:3px solid {_col};border-radius:8px;'
                   f'padding:8px 11px;margin:5px 0;">'
                   f'<div style="font-size:13px;font-weight:700;color:#fff;">{i}. {o["name"]} '
                   f'<span style="color:{GREY};font-size:11px;">{o["code"]}</span>'
                   f'<span style="color:{GOLD};float:right;">{o["total"]:.0f}分</span></div>'
                   f'<div style="color:{GREY};font-size:11px;">{o["lbc"]}板｜{o["sec"]}｜'
                   f'情绪{o["fs"]["jq"]:.0f} 量价{o["fs"]["lj"]:.0f} 资金{o["fs"]["zj"]:.0f} '
                   f'题材{o["fs"]["tc"]:.0f} 动量{o["fs"]["dl"]:.0f}{_vt}</div></div>')
        return ('<div style="margin-top:12px;font-size:15px;font-weight:800;color:#ff922b;">'
                '🏆 当日因子榜 TOP%d（按因子总分排序，被否决票照样入榜并标原因）</div>%s' % (topn, rr))
    except Exception as e:
        print('[factor-board] %s' % str(e)[:60])
        return ''


def _watch_card(sg, mscore, ds_plain=None):
    """可操作信号卡（小白友好版）：强度等级 + 大白话理由 + 当前价/买入区间/止损 + 仓位 + 做T思路 + 风险提示。
    大白话只认 DS 动态生成（ds_plain）；模型未返回时不回退 sg['why'] 规则模板。"""
    st_lv, st_txt = _strength(sg)
    st_color = {'S': RED, 'A': GOLD, 'B': GREY}[st_lv]
    _f = sg.get('_factor')
    if isinstance(_f, dict):
        _segs = []
        for _fk, _flab in (('jq', '情绪'), ('lj', '量价'), ('zj', '资金'),
                           ('tc', '题材'), ('dl', '动量')):
            if _f.get(_fk) is not None:
                _segs.append('%s%.0f' % (_flab, _f[_fk]))
        _tot = ('|综合%.0f' % _f['total']) if _f.get('total') is not None else ''
        if _f.get('vetoed'):
            _factor_line = ('<div style="color:#ff6b6b;font-size:12px;margin-top:4px;font-weight:700;">'
                            '⛔ 因子体检：%s%s ｜已否决：%s</div>'
                            % ('|'.join(_segs), _tot, '、'.join(_f.get('reasons') or []) or '见原因'))
        else:
            _factor_line = ('<div style="color:#8ce99a;font-size:12px;margin-top:4px;">'
                            '🔬 因子体检：%s%s ✓无否决</div>' % ('|'.join(_segs), _tot))
    else:
        _factor_line = ''
    fit = f'情绪档位 {mscore} 分'
    t_tgt = sg.get('t_target', '冲高+3%~+5%')          # 做T目标（可配置常量 WATCH_T_TARGET）
    risk = ''
    _dsp = (ds_plain or {}).get(sg['n'])
    _llm_ok = isinstance(_dsp, dict) and bool(_dsp.get('op'))
    if _llm_ok:
        _logic = _dsp.get('logic', '')
        _why = _dsp.get('why', '')
        _op_ai = _dsp.get('op', '')
        _buy_ai = _dsp.get('buy', '')
        _stop_ai = _dsp.get('stop', '')
        _om = {'别追': ('别追（今日无强推）', GREY, '空仓 0', '今日无买点（不参与）', '无（不参与）', ''),
               '看': ('观望为主', GOLD, '0-1成', '今日无买点，等放量企稳信号', '无（不参与）', ''),
               '观望': ('观望为主', GOLD, '0-1成', '今日无买点，等板块放量信号', '无（不参与）', ''),
               '轻仓试': ('可轻仓试', TEAL, '1-2成', _buy_ai or '回踩分时均线企稳再试', _stop_ai or '破-3%无条件止损', t_tgt)}
        if _op_ai in _om:
            _head_txt, _head_col, _pos_txt, _buy_txt, _stop_txt, _t_tgt2 = _om[_op_ai]
            st_color = _head_col
            _act_txt = _head_txt.split('（')[0]
        else:
            # op 不在枚举内：动作/仓位仍不给规则版，只保留代码算出的技术位
            _head_txt, _pos_txt, _buy_txt, _stop_txt, _act_txt, _t_tgt2 = (
                '待判读', '未给（无 AI 判读）',
                f"{sg.get('buy_low', '—')} ~ {sg.get('buy_high', '—')}（技术位·代码算）",
                str(sg.get('stop', '—')) + '（技术位·代码算）', '待判读', t_tgt)
        _logic_html = ('<div style="color:' + TEAL + ';font-size:12px;margin-top:4px;">🧠 个股逻辑：' + _logic + '</div>') if _logic else ''
        _why_html = ('<div style="color:#e9ecef;font-size:12px;margin-top:2px;">👉 大白话：' + _why + '</div>') if _why else ''
        _ai_block = _logic_html + _why_html
    else:
        # 无模型判读：保留代码算出的技术位（买入区间/止损），操作与仓位不给规则结论
        st_color = GREY
        _head_txt = '待判读'
        _act_txt = ''
        _pos_txt = ''
        _buy_txt = f"{sg.get('buy_low', '—')} ~ {sg.get('buy_high', '—')}"
        _stop_txt = str(sg.get('stop', '—'))
        _t_tgt2 = t_tgt
        _ai_block = ''
    _t_line = (f'🎯 做T目标 {_t_tgt2}；留多少出多少看盘口，冲涨停能不能追看量能。<br>'
               if _t_tgt2 else '')
    return f"""<div style="background:#2a1518;border:2px solid {RED};border-radius:12px;padding:12px 14px;margin:10px 0;">
<div style="font-size:17px;font-weight:900;color:{RED};">⚡ {sg['n']}（{sg['code']}）· {sg['type']} <span style="background:{st_color};color:#161b26;border-radius:6px;padding:1px 8px;font-size:12px;font-weight:700;">{_head_txt}</span></div>
<div style="color:#fff;font-size:13px;margin-top:6px;">所属题材：{(_dsp.get('theme') if _llm_ok and _dsp.get('theme') else sg['sec'])}｜得分 <b style="color:{GOLD}">{sg['score']}/10</b>{sg.get('life', '')}</div>
{_factor_line}
{_ai_block}
<div style="color:{TEAL};font-size:13px;margin-top:6px;">💰 当前价 <b>{sg.get('cur', '—')}</b> ｜ 建议买入区间 <b style="color:{GOLD}">{_buy_txt}</b></div>
<div style="color:{GREEN};font-size:13px;margin-top:3px;">🛑 止损 <b>{_stop_txt}</b></div>
<div style="color:{TEAL};font-size:13px;margin-top:4px;"><b>操作：{_act_txt}</b>｜仓位建议 <b>{_pos_txt}</b></div>
<div style="color:#ced4da;font-size:12px;margin-top:6px;border-top:1px dashed #444;padding-top:6px;">
{_t_line}⚠️ 风险：{risk} 市场适配度：{fit}</div></div>"""


# ============ 板块启动雷达（提前预警 + 板块共振；最高优先级触发） ============
def _is_lu(s):
    """统一涨停判定：主板 ≥9.5%，创业板/其他 ≥19.5%（科创/北交所已被 _clist_gainers 剔除）。"""
    return float(s.get('pct') or 0) >= (9.5 if s.get('board') == 'main' else 19.5)


# ============ v3.0 批次A：题材名进化（评分制清洗） ============
_BLACKLIST = {
    "板块", "概念", "热点", "热门", "相关", "其他", "概念板", "热门板块",
    "涨停板", "异动", "龙头", "跟风", "题材", "主线",
}
_INDUSTRY_KEYWORDS = {
    "AI", "人工智能", "算力", "机器人", "半导体", "芯片", "新能源", "光伏",
    "锂电", "储能", "军工", "航天", "卫星", "消费电子", "汽车", "智能驾驶",
    "医药", "创新药", "中药", "白酒", "消费", "旅游", "酒店", "券商", "银行",
    "保险", "地产", "基建", "钢铁", "有色", "煤炭", "石油", "化工",
}


def _is_digit_serial(s):
    """纯数字串（'13.96'/'123' 等）→ True。"""
    return bool(re.fullmatch(r'[-+.\d]+', s or ''))


def _is_valid_chinese_ratio(s):
    """有效中文字符占比 ≥60% → True。"""
    cn = len(re.findall(r'[\u4e00-\u9fff]', s))
    return len(s) > 0 and cn / len(s) >= 0.6


def _contains_only_digits_or_english(s):
    """不含任何中文（纯数字/纯英文/纯符号）→ True。"""
    return not re.search(r'[\u4e00-\u9fff]', s or '')


def _has_industry_keyword(s):
    """命中 _INDUSTRY_KEYWORDS 任一关键词 → True。"""
    return any(k in s for k in _INDUSTRY_KEYWORDS)


def _concept_score(concept):
    """概念有效性评分 0~100（严格按 v3.0 规格顺序累加，可调试）；<50 视为无效。
    ①中文占比≥60% +40 ②长度2~8汉字 +20 ③非纯数字/英文/符号 +15
    ④不在黑名单 +15 ⑤含行业关键词 +10；纯数字串直判 10 分。"""
    s = str(concept or '').strip()
    if not s:
        return 0
    if _is_digit_serial(s):
        return 10
    score = 0
    if _is_valid_chinese_ratio(s):
        score += 40
    cn_len = len(re.findall(r'[\u4e00-\u9fff]', s))
    if 2 <= cn_len <= 8:
        score += 20
    if not _contains_only_digits_or_english(s):
        score += 15
    if s not in _BLACKLIST:
        score += 15
    if _has_industry_keyword(s):
        score += 10
    return score


def _sec_valid(industry):
    """题材名有效性：必须含中文字符、非空、非'其他'、长度≥2 → 才可作为可读题材名。
    纯数字（如东财晚间接口偶发的 '13.96'）、空值、无意义字段一律判无效。"""
    if not industry:
        return False
    s = str(industry).strip()
    if not s or s == '其他' or len(s) < 2:
        return False
    return bool(re.search(r'[\u4e00-\u9fff]', s))


def _board_sec_info(stocks):
    """v3.0 批次A：题材名深度清洗（评分制）。
    流程：评分过滤(<50/黑名单/纯数字丢弃并记脏) → 龙头锚定(涨幅+成交额最大) →
    多数票+时间加权(早盘9点新题材+10；10/13/14点持续题材+5) → 兜底链
    （高质量主题材 score≥80且出现≥2 → 龙头锚定概念 → 「{龙头股票名}相关板块」→「热门板块」）。
    返回 (最终可读题材名, 被丢弃脏概念列表)。绝不输出纯数字/无意义题材名。"""
    now = _bj_now()
    hour = now.hour
    dirty, valid = [], []
    for s in stocks:
        concept = str(s.get('industry') or '').strip() or ''
        if not concept:
            continue
        score = _concept_score(concept)
        if score < 50 or concept in _BLACKLIST or _is_digit_serial(concept):
            dirty.append({'ts': now.strftime('%Y-%m-%d %H:%M:%S'),
                          'concept': concept, 'from_stock': s.get('code', ''),
                          'reason': f'score={score}'})
            continue
        valid.append({'concept': concept, 'score': score, 'code': s.get('code'),
                      'name': s.get('name'), 'pct': float(s.get('pct') or 0),
                      'amount': float(s.get('amount') or 0)})
    if not valid:
        lead = max(stocks, key=lambda x: float(x.get('pct') or 0)) if stocks else None
        if lead and lead.get('name') and _sec_valid(lead.get('name')):
            return f"{lead['name']}相关板块", dirty
        return '热门板块', dirty
    leader = max(valid, key=lambda x: (x['pct'], x['amount']))      # 龙头锚定
    from collections import Counter
    cnt = Counter(v['concept'] for v in valid)
    w = Counter()
    for v in valid:
        base = cnt[v['concept']]
        if hour == 9:                 # 早盘新题材 +10
            base += 10
        elif hour in (10, 13, 14):    # 持续题材 +5
            base += 5
        w[v['concept']] = max(w.get(v['concept'], 0), base)
    hi_cnt = {c: n for c, n in cnt.items() if n >= 2
              and any(v['concept'] == c and v['score'] >= 80 for v in valid)}
    if hi_cnt:                        # ① 高质量主题材（score≥80 且出现≥2）
        final = max(hi_cnt.items(), key=lambda kv: kv[1])[0]
    elif leader and leader['concept']:   # ② 龙头锚定概念
        final = leader['concept']
    else:                             # ③ 兜底
        final = f"{leader['name']}相关板块" if _sec_valid(leader.get('name')) else '热门板块'
    return final, dirty


def _board_sec_name(stocks):
    """兼容层：返回最终题材名（str）。内部走 _board_sec_info（现有调用与测试零破坏）。"""
    return _board_sec_info(stocks)[0] 

def _board_start(rows, market_bias='震荡', min_cnt=3, min_pct=2.5, min_lb=1.8, need_streak=False):
    """板块共振雷达（纯规则零 DS）：同一题材内 ≥min_cnt 只同时 涨幅≥min_pct% 且 量比≥min_lb
    （偏空：涨幅门槛 +1pp、量比 +0.5）。
    - 默认（min_cnt=3/min_pct=2.5/min_lb=1.8）= 🚀 板块启动（最高优先级）
    - min_cnt=2/min_lb=1.5 = 👀 早期观察（更早一步的降门槛版，不占 DS）
    返回最强 1 个板块（按共振家数倒序）：{'sec', 'stocks'(已按涨幅降序并标注 role 龙头/中军/跟风/并列领涨), 'fzn'}；无命中返回 None。
    只推最强 1 个板块（用户确认，防刷屏）。"""
    up_bias = 1.0 if market_bias == '偏空' else 0.0
    lb_bias = 0.5 if market_bias == '偏空' else 0.0
    grp = {}
    for s in rows:
        ind = re.sub(r'[行业板块概念\s]+', '', s.get('industry') or '') or '其他'
        if float(s.get('pct') or 0) >= min_pct + up_bias and float(s.get('lb') or 0) >= min_lb + lb_bias:
            grp.setdefault(ind, []).append(s)
    best = None
    for ind, stocks in grp.items():
        if len(stocks) < min_cnt:
            continue
        if need_streak and not any(_is_lu(s) or float(s.get('pct') or 0) >= 5.0 for s in stocks):
            continue      # v3.0：组内至少 1 只涨幅≥5% 或已涨停（need_streak=True 时）
        stocks.sort(key=lambda x: -(float(x.get('pct') or 0)))
        for i, s in enumerate(stocks):
            if i == 0:
                s['role'] = '龙头' if (len(stocks) == 1 or float(stocks[0]['pct']) - float(stocks[1]['pct']) >= 3.0) else '并列领涨'
            elif i == 1:
                s['role'] = '中军'
            else:
                s['role'] = '跟风'
        if best is None or len(stocks) > len(best['stocks']):
            sec_name, dirty = _board_sec_info(stocks)
            best = {'sec': sec_name, 'stocks': stocks, 'fzn': len(stocks), 'dirty': dirty}
    return best


def _append_dirty_log(dirty_list):
    """脏概念追加写 tools/dirty_data_log.json（与 last_alerts.json 同级，去重后追加并 git 写回）。
    所有被丢弃的脏数据必须记录，不得静默丢弃（v3.0 规格）。"""
    if not dirty_list:
        return
    try:
        if os.path.exists(DIRTY_PATH):
            with open(DIRTY_PATH, encoding='utf-8') as f:
                logs = json.load(f)
        else:
            logs = []
        if not isinstance(logs, list):
            logs = []
    except Exception:
        logs = []
    seen = {(d.get('ts'), d.get('concept'), d.get('from_stock')) for d in logs}
    new = [d for d in dirty_list if (d.get('ts'), d.get('concept'), d.get('from_stock')) not in seen]
    if new:
        logs.extend(new)
        with open(DIRTY_PATH, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=1)
        _git_commit_push(DIRTY_PATH, 'update dirty log')
        print(f'[dirty] 记录脏概念 {len(new)} 条（累计 {len(logs)}）')


# ============ v3.0 批次B：数据源健康 + 生命周期 ============
def _data_health(rows):
    """数据源健康检查：valid_count==0 或 >80 → 异常；连续两次异常 → 保守模式。
    confidence：正常→高；异常但缓存新鲜(<90分钟)→中；完全异常→低。
    计数状态写 data_health_state.json（最近两次，跨 run 保留）。"""
    valid_count = len(rows or [])
    # 东财 clist 常态返回 99~100 只，>80 不算异常；只有空(0)或明显过少(<20)才算数据异常
    abnormal = valid_count == 0 or valid_count < 20
    state = {}
    try:
        if os.path.exists(HEALTH_STATE_PATH):
            with open(HEALTH_STATE_PATH, encoding='utf-8') as f:
                state = json.load(f)
    except Exception:
        state = {}
    recent = state.get('recent') or []
    recent.append({'ts': _bj_now().strftime('%Y-%m-%d %H:%M:%S'),
                   'valid_count': valid_count, 'abnormal': abnormal})
    recent = recent[-2:]
    conservative = len(recent) == 2 and all(r.get('abnormal') for r in recent)
    try:
        with open(HEALTH_STATE_PATH, 'w', encoding='utf-8') as f:
            json.dump({'recent': recent}, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    if not abnormal:
        conf = '高'
    elif _cache_themes_fresh():
        conf = '中'
    else:
        conf = '低'
    return {'valid_count': valid_count, 'abnormal': abnormal,
            'conservative': conservative, 'confidence': conf}


def _cache_themes_fresh():
    """last_valid_themes.json 存在且距离写入 <90 分钟 → True。"""
    try:
        if not os.path.exists(THEMES_PATH):
            return False
        with open(THEMES_PATH, encoding='utf-8') as f:
            d = json.load(f)
        ts = d.get('ts', '')
        if not ts:
            return False
        dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
        return (_bj_now() - dt).total_seconds() < 5400
    except Exception:
        return False


def _save_cache_themes(theme_name, codes):
    """正常数据时写最后有效题材缓存（异常降级用，<90 分钟有效）。"""
    try:
        with open(THEMES_PATH, 'w', encoding='utf-8') as f:
            json.dump({'theme_name': theme_name, 'ts': _bj_now().strftime('%Y-%m-%d %H:%M:%S'),
                       'stocks': codes}, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print('[themes] 缓存写盘失败:', e)


def _theme_lifecycle(theme, stocks):
    """题材生命周期状态机（萌芽→发酵→高潮→退潮）。
    迁移：无历史→萌芽；prev∈{发酵,高潮}且红盘<2→退潮；≥2只涨停或≥4只且成交额≥_AMT_HIGH→高潮；
    否则 prev 存在→发酵。写回 theme_lifecycle.json（跨 run）。返回当前 status。"""
    lc = {}
    try:
        if os.path.exists(LIFECYCLE_PATH):
            with open(LIFECYCLE_PATH, encoding='utf-8') as f:
                lc = json.load(f)
    except Exception:
        lc = {}
    if not isinstance(lc, dict):
        lc = {}
    prev = lc.get(theme) or {}
    now = _bj_now().strftime('%Y-%m-%d %H:%M:%S')
    n = len(stocks)
    lus = sum(1 for s in stocks if _is_lu(s))
    reds = sum(1 for s in stocks if float(s.get('pct') or 0) > 0)
    amt = sum(float(s.get('amount') or 0) for s in stocks)
    prev_status = prev.get('status', '')
    if not prev:
        status = '萌芽'
    elif prev_status in ('发酵', '高潮') and reds < 2:
        status = '退潮'
    elif lus >= 2 or (n >= 4 and amt >= _AMT_HIGH):
        status = '高潮'
    else:
        status = '发酵'
    lc[theme] = {'status': status,
                 'first_seen': prev.get('first_seen', now),
                 'last_seen': now,
                 'push_count': prev.get('push_count', 0),
                 'last_push_type': prev.get('last_push_type', ''),
                 'prev_cnt': prev.get('prev_cnt', n),
                 'seen_count': prev.get('seen_count', 0) + 1}
    try:
        with open(LIFECYCLE_PATH, 'w', encoding='utf-8') as f:
            json.dump(lc, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print('[lifecycle] 写盘失败:', e)
    return status


def _detect_retreat(rows, fired, today):
    """退潮检测：曾推过正面卡(发酵/高潮)的题材，当前涨幅榜中该题材红盘<2 → 退潮题材列表。
    返回 [(theme, prev_status)]，当日已推反向卡(key R|{theme}|{today})的排除。"""
    ret = []
    try:
        if not os.path.exists(LIFECYCLE_PATH):
            return ret
        with open(LIFECYCLE_PATH, encoding='utf-8') as f:
            lc = json.load(f)
    except Exception:
        return ret
    if not isinstance(lc, dict):
        return ret
    for theme, info in lc.items():
        if info.get('push_count', 0) == 0 or info.get('status') not in ('发酵', '高潮'):
            continue
        if f'R|{theme}|{today}' in fired:
            continue
        reds = sum(1 for s in rows if str(s.get('industry') or '').strip() == theme
                   and float(s.get('pct') or 0) > 0)
        if reds < 2:
            ret.append((theme, info.get('status', '')))
    return ret


_REV_SYS = ('你是A股一线游资，写「板块转弱/退潮·退出提醒」。某题材此前给出过正面信号（发酵/高潮），现在该题材红盘家数不足2只，判定为转弱。'
            '用大白话讲清楚：这是不是真退潮、主力在干什么、持仓者具体怎么处理、什么条件才算重新回来。'
            '只基于输入说话，禁止编造盘面数据，禁止模板句，结论先行，坏消息不软化。'
            '只输出 JSON：{"logic":"转弱判断依据与主力在干什么(≥25字)","act":"持仓与观察列表的具体动作(≥15字,给条件)","back":"重新关注的条件(≥12字,给信号)"}，不要其他文字。')


def _board_reverse_ds(theme, prev_status):
    """板块转弱判读（大模型）。失败返回 {}。"""
    try:
        fmt = ('题材「' + theme + '」此前状态「' + prev_status + '」，当前该题材红盘家数不足2只。'
               '只输出 JSON：{"logic":"...","act":"...","back":"..."}，不要其他文字')
        t = ask_deepseek({'task': 'board_reverse', 'theme': theme, 'prev': prev_status, 'format': fmt},
                         purpose='board_reverse', system_text=_REV_SYS)
        if not t:
            return {}
        _j = json.loads(t[t.find('{'):t.rfind('}') + 1])
        return _j if isinstance(_j, dict) else {}
    except Exception:
        return {}


def _board_reverse_card(theme, prev_status):
    """↩️ 反向观察卡：数据事实由代码算，转弱判读交大模型；模型未返回时不给规则版操作建议。"""
    _rv = _board_reverse_ds(theme, prev_status)
    _logic = str(_rv.get('logic') or '').strip()
    _act = str(_rv.get('act') or '').strip()
    _back = str(_rv.get('back') or '').strip()
    if _logic:
        _body = (f'<div style="color:#e9ecef;font-size:13px;margin-top:4px;">🧠 {_logic}</div>'
                 + (f'<div style="margin-top:8px;padding:8px 10px;background:#2a1f22;border-left:4px solid {RED};'
                    f'border-radius:8px;font-size:13px;color:{RED};">💡 {_act}</div>' if _act else '')
                 + (f'<div style="color:{TEAL};font-size:12px;margin-top:6px;">🔙 重新关注条件：{_back}</div>' if _back else ''))
    else:
        _body = ''
    return f"""<div style="background:#1f2635;border:2px solid {RED};border-radius:12px;padding:12px 14px;margin:10px 0;">
<div style="font-size:13px;color:{RED};font-weight:800;">↩️ {theme} 转弱（此前{prev_status}）</div>
<div style="color:#e9ecef;font-size:13px;margin-top:4px;">该题材今天翻红的家数不到 2 只，板块没形成合力，单票再强也带不动</div>
{_body}</div>"""


# ============ v3.0 批次C：统一中间层 payload + 推送快照 ============
def _board_payload(card_type, confidence, theme_name, trigger_reason, lifecycle_status,
                   stocks, volume_emotion, risk_warning, verify_nodes, data_source,
                   raw_dirty, push_content):
    """统一中间层：所有板块卡先产出标准 payload dict，再渲染 HTML/落盘 JSON（供次日反馈）。"""
    sorted_s = sorted(stocks or [], key=lambda x: -float(x.get('pct') or 0))
    leaders = [{'code': s.get('code'), 'name': s.get('name'),
                'pct': round(float(s.get('pct') or 0), 1),
                'amount': round(float(s.get('amount') or 0), 0),
                'is_first': bool(s.get('is_first'))}
               for s in sorted_s[:3]]
    followers = [{'code': s.get('code'), 'name': s.get('name'),
                  'pct': round(float(s.get('pct') or 0), 1)}
                 for s in sorted_s[3:]]
    return {'card_type': card_type, 'confidence': confidence, 'theme_name': theme_name,
            'trigger_reason': trigger_reason, 'lifecycle_status': lifecycle_status,
            'leaders': leaders, 'followers': followers,
            'volume_emotion': volume_emotion, 'risk_warning': risk_warning,
            'verify_nodes': verify_nodes, 'data_source': data_source,
            'raw_dirty_concepts': raw_dirty, 'push_content': push_content}


def _append_push(payload):
    """推送快照追加写 tools/theme_pushes.json（跨 run 保留，供次日 EOD 反馈统计）。"""
    if not payload or payload.get('card_type') in ('静默',):
        return
    rec = {'ts': _bj_now().strftime('%Y-%m-%d %H:%M:%S'),
           'theme_name': payload.get('theme_name', ''),
           'card_type': payload.get('card_type', ''),
           'confidence': payload.get('confidence', ''),
           'lifecycle_status': payload.get('lifecycle_status', ''),
           'board_snapshot': [{'code': s['code'], 'name': s['name'], 'pct': s['pct']}
                              for s in (payload.get('leaders') or []) + (payload.get('followers') or [])][:8]}
    pushes = []
    try:
        if os.path.exists(PUSHES_PATH):
            with open(PUSHES_PATH, encoding='utf-8') as f:
                pushes = json.load(f)
    except Exception:
        pushes = []
    if not isinstance(pushes, list):
        pushes = []
    pushes.append(rec)
    try:
        with open(PUSHES_PATH, 'w', encoding='utf-8') as f:
            json.dump(pushes, f, ensure_ascii=False, indent=1)
        _git_commit_push(PUSHES_PATH, 'update theme pushes')
        print(f'[pushsnap] 记录推送快照（累计 {len(pushes)}）')
    except Exception as e:
        print('[pushsnap] 写盘失败:', e)


_VERIFY_NODES = ['09:45 看龙头是否继续封板/回封', '10:30 看跟风是否扩散', '14:00 看整体是否回落']


def _deep_logic(s, sec, fzn, market_bias='震荡', eod_kind=None):
    """规则层已彻底停用判读结论：本函数只输出数据事实与技术位，判读一律交大模型。
    不再输出"为什么选这只/能不能买/目标位/放弃条件"这类规则结论句。"""
    role = s.get('role', ('低吸候选' if eod_kind == '低吸候选' else '冲高做T') if eod_kind else '跟风')
    cur = float(s.get('price') or 0)
    if cur > 0:
        buy_low = round(cur * 0.995, 2)
        buy_high = round(cur * 1.01, 2)
        stop = round(buy_low * 0.97, 2)
        buy_txt = f'回踩 {buy_low}~{buy_high} 这一带能接，跌破 {stop} 就直接走'
    else:
        buy_low = buy_high = stop = 0.0
        buy_txt = '技术位：现价未取得，买入区间与止损无法计算'
    sec_txt = (f'{sec} 今日 {fzn} 只同步放量（量比≥1.5）' if fzn else f'{sec} 今日放量活跃')
    return (f'① 板块数据：{sec_txt}\n'
            f'② 个股位置：{s.get("name", "")} 角色{role}｜涨幅 {float(s.get("pct") or 0):+.1f}%｜量比 {float(s.get("lb") or 0):.1f}\n'
            f'③ {buy_txt}')


_BOARD_DS_SYS = '''你是一位A股盘中助理，面对炒股小白，禁止专业黑话，术语首次出现必须括号解释。只基于输入数据输出，绝不编造；已涨停的票只能作为「板块热度证据」提及，绝不能作为买入推荐。总长度控制在150字以内。
【强制主力视角】先用一句话说清主力现在在干什么（吸筹/拉升/出货），再翻译成小白能懂的操作建议。
【三层认知结构】信息密度压缩；因果链显影（谁在动→为什么动→动到哪一步）；决策接口（触发条件+动作+失败出口）。
比喻优先，结论先行，坏消息不软化。禁止模板句。'''


def _board_ds(board, mscore):
    """板块启动 DeepSeek 三问总结（预算网关：固定4+warn1+板块启动1=6，≤8 上限；用尽/失败返回 ''）。"""
    payload = {
        'task': 'board_start',
        'sec': board['sec'],
        'stocks': [{'name': s['name'], 'pct': round(float(s.get('pct') or 0), 1),
                    'lb': round(float(s.get('lb') or 0), 1), 'role': s.get('role', '')}
                   for s in board['stocks'][:5]],
        'market_score': mscore,
        'format': ('请用大白话输出三问总结（≤150字，全文用陈述句，禁止任何问号）：\n'
                   '1. 现在最值得跟踪的板块与原因（资金涌入/多只共振/情绪支持）\n'
                   '2. 怎么跟：买谁（只允许提未涨停的）、买在什么区间、仓位几成\n'
                   '3. 风险与降仓条件：风险在哪、什么情况立刻降仓'),
    }
    return ask_deepseek(payload, purpose='board', system_text=_BOARD_DS_SYS)


def _cap_txt(mscore, mlabel='震荡'):
    """仓位一句话（顶部整体行用，与情绪标签对齐；底部仍有 pos_cap_line 精确行）。"""
    if mlabel == '偏多' or mscore >= 70:
        return '建议总仓位 6-8 成'
    if mlabel == '偏空' or mscore < 40:
        return '建议总仓位 0-3 成'
    return '建议总仓位 3-5 成'


def _board_why_deep(sec, stocks, fzn):
    """板块题材逻辑深挖：为什么今天市场资金选这个板块（题材驱动/资金风格/持续性与位置/操作）。
    注入板块内个股 F10 题材交集 + 当日新闻命中。失败 ''（回退量价规则行）。"""
    if not stocks or not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return ''
    try:
        _news_hits = _board_news_hits(sec, stocks)
    except Exception:
        _news_hits = []
    sec_f10 = []
    for sd in stocks[:5]:
        f10 = _stock_f10(sd.get('code', ''))
        if f10:
            for kw in re.findall(r'[^／/]+', f10):
                kw2 = kw.replace('核心题材：', '').strip()
                if len(kw2) >= 2 and '公司简介' not in kw2 and '核心题材' not in kw2:
                    sec_f10.append(kw2)
    sec_f10 = sorted(set(sec_f10))[:6]
    news_txt = ('；相关新闻：' + '；'.join(_news_hits[:3])) if _news_hits else ''
    brief = (f"板块「{sec}」今日{fzn}只放量(涨幅≥2.5%且量比≥1.5)。板块内个股F10题材交集："
             f"{'、'.join(sec_f10) if sec_f10 else '未见'}{news_txt}")
    _g = load_position_gauge()
    _g_txt = (f'（当前仓位仪表盘：{_g.get("suggest", "")}，来自 {_g.get("source", "")}，不得与其矛盾）\n' if _g else '（仓位仪表盘未生成）\n')
    fmt = (_g_txt
           + '你是一线游资，盘中板块共振观察，回答一个核心问题：为什么今天主力资金选这个板块（严格按主力游资五步铁律）：\n'
           + FIVE_BRIEF + '\n'
           + '先判断主力阶段，再写逻辑。已涨停票只当热度证据，不进买点。\n板块数据：' + brief + '\n'
           + '只输出 JSON：{"board":{"logic":"为什么今天主力选这个板块：题材驱动+建仓痕迹/资金风格+和昨日比是刚启动还是接力+持续性判断,至少40字","why":"大白话：这板块今天能不能跟,至少18字","op":"跟/看/别追/轻仓试——必须与logic一致","stage":"启动|接力|分歧|退潮","sustain":"持续性依据(一句话)","min_confirm":"至少几只共振才算真启动","buy":"op≠别追时必须指名1-2只票给可执行买点(哪只+回踩到具体价位→几成仓),op=别追写今日无买点","stop":"op≠别追时给对应个股具体止损,op=别追写无"}}，只输出这一个对象。')
    t = ask_deepseek({'task': 'board_why', 'items': [{'n': sd['name'], 'c': sd.get('code', '')} for sd in stocks[:5]],
                      'format': fmt}, purpose='board_why')
    if not t:
        return ''
    try:
        _j = json.loads(t)
        _b = _j.get('board') or {}
        if not (_b.get('logic') or _b.get('why')):
            return ''
        _opcol = {'别追': RED, '轻仓试': TEAL, '看': GOLD, '观望': GREY}.get(_b.get('op', ''), GOLD)
        _opx = _b.get('op', '')
        try:
            _d0 = get_pools()
            _zbr0 = _d0['zb'] / (_d0['lu'] + _d0['zb']) if (_d0['lu'] + _d0['zb']) else 0.0
        except Exception:
            _zbr0 = 0.0
        if _zbr0 > 0.45 and _opx == '轻仓试':
            _opx = '观察'
        _op_txt = (f'<br>💡 板块操作：<b style="color:{_opcol};">{_opx}</b>'
                   + (f' ｜ 买点/确认：{_b.get("buy","")} ｜ 失效：{_b.get("stop","")}' if (_b.get('buy') or _b.get('stop')) else '')) if (_opx or _b.get('buy')) else ''
        _st_txt = (f'<br>🎚️ 阶段：{_b.get("stage","")} ｜ 持续依据：{_b.get("sustain","")} ｜ 真启动需同步：{_b.get("min_confirm","")}只' if (_b.get('stage') or _b.get('sustain') or _b.get('min_confirm')) else '')
        return (f'<div style="background:#1c2830;border-left:3px solid {GOLD};border-radius:6px;padding:6px 8px;'
                f'margin:4px 0;font-size:12px;color:#ced4da;line-height:1.65;">'
                f'🧠 板块题材逻辑：{_b.get("logic","")}<br>'
                f'👉 大白话：{_b.get("why","")}{_st_txt}{_op_txt}</div>')
    except Exception:
        return ''


def _board_stocks_deep(stocks, sec, fzn):
    """板块卡「已动个股」批量 LLM 深挖：{name: {logic,why,op,buy,stop}}。失败 {}（回退规则行）。
    注入 F10（公司简介+核心题材）让 LLM 挖真实底层逻辑（主业/题材关联/资金本质/催化/暗雷），非量价模板。"""
    if not stocks or not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return {}
    lines = []
    for sd in stocks[:5]:
        f10 = _stock_f10(sd.get('code', ''))
        f10_txt = (' ' + f10) if f10 else ''
        lu_txt = '已涨停' if _is_lu(sd) else '未涨停'
        lines.append(f"- {sd['name']}({sd.get('code','')}) 板块「{sec}」({fzn}只放量) 角色{sd.get('role','跟风')} "
                     f"涨{float(sd.get('pct') or 0):+.1f}% 量比{float(sd.get('lb') or 0):.1f} {lu_txt}{f10_txt}")
    _g = load_position_gauge()
    _g_txt = (f'（当前仓位仪表盘：{_g.get("suggest", "")}，来自 {_g.get("source", "")}，不得与其矛盾）\n' if _g else '（仓位仪表盘未生成）\n')
    fmt = (_g_txt
           + '你是一线游资，盘中板块共振里「已经在动的个股」，对每只深挖（严格按主力游资五步铁律）：\n'
           + FIVE_BRIEF + '\n'
           + '必须判断：真龙头/中军还是跟风炮灰；有没有建仓痕迹；筹码状态。已连板≥3或60日位置>0.85，verdict必须为「不碰」、op必须「别追」。\n已动个股数据（含F10公司简介/核心题材）：\n' + '\n'.join(lines) + '\n'
           + '只输出 JSON：{"per":[{"name":"股票名(照抄)","role":"龙头|中军|跟风|纯蹭","real_benefit":"实受益|沾边|纯蹭","verdict":"终审推荐|观察|不碰","stage":"启动日|中段接力|末段高位|退潮反抽","resonance":0-4,"logic":"底层核心逻辑：主业+题材关联+建仓痕迹/筹码状态+资金本质+催化+暗雷,至少45字","why":"大白话：一句话戳穿真假+该不该追,至少18字","op":"别追/看/轻仓试/观望——必须与logic一致","buy":"op≠别追时给具体买点条件,op=别追写今日无买点","stop":"op≠别追时给具体止损,op=别追写无","exit":"介入/退出出口：已涨停票禁止推荐买入,只写回踩介入条件；未涨停票写现价能否介入+触发条件+止损,至少15字"}]}，必须覆盖每只。')
    t = ask_deepseek({'task': 'board_deep', 'items': [{'n': sd['name'], 'c': sd.get('code', '')} for sd in stocks[:5]],
                      'format': fmt}, purpose='board_deep')
    out = {}
    if t:
        try:
            _j = json.loads(t)
        except Exception:
            _j = None
        if _j:
            for it in _j.get('per') or []:
                nm = str(it.get('name') or '').strip()
                if nm and (it.get('logic') or it.get('why')):
                    out[nm] = {k: str(it.get(k) or '') for k in ('logic', 'why', 'op', 'buy', 'stop', 'exit', 'role', 'real_benefit', 'verdict', 'stage', 'resonance')}
    # 缺失补调：LLM 漏报的个股只喂它自己再调一次（保证每只都有深挖，不让某只退回纯量价模板）
    missing = []
    for sd in stocks[:5]:
        nm = sd['name']
        has = nm in out
        if not has:
            for _k in out:
                if _k[:4] == nm[:4] or nm[:4] in _k:
                    has = True
                    break
        if not has:
            missing.append(sd)
    if missing and t:
        lines2 = []
        for sd in missing:
            f10 = _stock_f10(sd.get('code', ''))
            f10_txt = (' ' + f10) if f10 else ''
            lu_txt = '已涨停' if _is_lu(sd) else '未涨停'
            lines2.append(f"- {sd['name']}({sd.get('code','')}) 板块「{sec}」({fzn}只放量) 角色{sd.get('role','跟风')} "
                          f"涨{float(sd.get('pct') or 0):+.1f}% 量比{float(sd.get('lb') or 0):.1f} {lu_txt}{f10_txt}")
        fmt2 = ('你是10年A股超短线交易员，盘中板块共振里这只「已经在动的个股」，深挖（严格按大白话五步铁律，禁模板句、禁「值得关注/建议留意/一日游」）：\n' + _g_txt
                + FIVE_BRIEF + '\n'
                + '个股数据：\n' + '\n'.join(lines2) + '\n'
                + '只输出 JSON：{"per":[{"name":"股票名(照抄)","role":"龙头|中军|跟风|纯蹭","real_benefit":"实受益|沾边|纯蹭","verdict":"终审推荐|观察|不碰","stage":"启动日|中段接力|末段高位|退潮反抽","resonance":0-4,"logic":"底层核心逻辑：主业(F10依据,人话翻译)+题材关联(实受益/沾边/纯蹭明确判断)+资金本质(龙头/订单/低价/情绪,说清哪种)+催化(新闻无就写未见明确新闻催化)+暗雷(位置/业绩/减持等),至少45字,禁止只讲盘面、禁止万能句","why":"大白话：一句话戳穿真假+该不该追,至少18字,比喻只能收尾一句","op":"别追/看/轻仓试/观望——必须与logic一致","buy":"op≠别追时给具体买点条件(价位/量能),op=别追写今日无买点","stop":"op≠别追时给具体止损,op=别追写无"}]}，只输出缺失的这{len(missing)}只，不许偷懒。')
        t2 = ask_deepseek({'task': 'board_deep_fill', 'items': [{'n': sd['name'], 'c': sd.get('code', '')} for sd in missing],
                           'format': fmt2}, purpose='board_deep_fill')
        if t2:
            try:
                _j2 = json.loads(t2)
                for it in _j2.get('per') or []:
                    nm = str(it.get('name') or '').strip()
                    if nm and (it.get('logic') or it.get('why')):
                        out[nm] = {k: str(it.get(k) or '') for k in ('logic', 'why', 'op', 'buy', 'stop', 'exit', 'role', 'real_benefit', 'verdict', 'stage', 'resonance')}
            except Exception:
                pass
    return out


def _board_news_hits(sec, stocks):
    """板块相关新闻（标题/摘要命中板块名或个股名的前3条）。失败 []。"""
    try:
        news = get_news(30)
    except Exception:
        return []
    kws = [sec] + [sd['name'] for sd in stocks[:4]] + [sd.get('code', '') for sd in stocks[:4]]
    out = []
    for nw in news:
        t = (nw.get('title') or '') + ' ' + (nw.get('summary') or '')
        if any(k and k in t for k in kws):
            out.append((nw.get('title') or '')[:50])
        if len(out) >= 3:
            break
    return out


def _conf_rows_html(stocks, sec, fzn, deep_rows=True):
    """已动个股渲染：量价规则行 + LLM 深挖子行（🧠逻辑/👉大白话/💡操作）+ 板块题材逻辑。返回 (rows, why_html)。
    deep_rows=False 只出角色行（仅热度证据，不深挖），深挖由调用方单独渲染放卡片尾部。"""
    deep = _board_stocks_deep(stocks, sec, fzn) if deep_rows else {}
    why_html = _board_why_deep(sec, stocks, fzn) if deep_rows else ''
    rows = ''
    for sd in stocks[:5]:
        lu = _is_lu(sd)
        ico = '🔥' if sd.get('role') == '龙头' else ('⚡' if sd.get('role') == '中军' else '💤')
        role_txt = (f'{ico} {sd.get("role")}：' if sd.get('role') else f'{ico} ')
        rows += (f'<div style="font-size:13px;color:#e9ecef;margin:2px 0;">{role_txt}'
                 f'{sd["name"]}（{sd.get("code","")}）+{float(sd.get("pct") or 0):.1f}% 量比{float(sd.get("lb") or 0):.1f}'
                 f'<span style="color:{GREY};font-size:12px;">{"（已涨停·仅热度证据，不追）" if lu else ""}</span></div>')
        _d = deep.get(sd['name'])
        if not _d:
            _kk = sd['name'][:4]
            for _k, _v in deep.items():
                if _k[:4] == _kk or _kk in _k:
                    _d = _v
                    break
        if _d and (_d.get('logic') or _d.get('why')):
            _opcol = {'别追': RED, '轻仓试': TEAL, '看': GOLD, '观望': GREY}.get(_d.get('op', ''), GOLD)
            _opx = _d.get('op', '')
            try:
                _d0 = get_pools()
                _zbr0 = _d0['zb'] / (_d0['lu'] + _d0['zb']) if (_d0['lu'] + _d0['zb']) else 0.0
            except Exception:
                _zbr0 = 0.0
            if _zbr0 > 0.45 and _opx == '轻仓试':
                _opx = '观察'
            _op_txt = (f'<br>💡 操作：<b style="color:{_opcol};">{_opx}</b>'
                       + (f' ｜ 买点：{_d.get("buy","")} ｜ 止损：{_d.get("stop","")}' if (_d.get('buy') or _d.get('stop')) else '')) if (_opx or _d.get('buy')) else ''
            _x_txt = (f'<br>🪜 介入/退出：{_d.get("exit","")}' if _d.get('exit') else '')
            _v_txt = (f'<br>🏷️ 角色：{_d.get("role","")} ｜ 受益：{_d.get("real_benefit","")} ｜ 结论：<b style="color:{RED if _d.get("verdict")=="不碰" else (TEAL if _d.get("verdict")=="终审推荐" else GOLD)};">{_d.get("verdict","")}</b> ｜ 阶段：{_d.get("stage","")}' if (_d.get('verdict') or _d.get('stage') or _d.get('resonance')) else '')
            _dr_txt = (f'<br>⚠️ 暗雷：{_d.get("dark_risk","")}' if (_d.get('dark_risk') and _d.get('dark_risk') != '[]') else '')
            rows += (f'<div style="background:#1c2830;border-left:3px solid {TEAL};border-radius:6px;padding:6px 8px;'
                     f'margin:3px 0 6px 0;font-size:12px;color:#ced4da;line-height:1.65;">'
                     f'🧠 个股逻辑：{_d.get("logic","")}<br>'
                     f'👉 大白话：{_d.get("why","")}{_v_txt}{_op_txt}{_x_txt}{_dr_txt}</div>')
    return rows, why_html


def _board_card(board, mscore, mlabel, confidence='高', lifecycle='', data_source='eastmoney'):
    """板块启动提醒卡（小白友好极致版）：今天整体 → 为什么看这个板块 + 共振确认（可含已涨停作热度证据）
    + 可跟个股（严格剔除已涨停，每只完整六段深度逻辑）+ 风控/观察窗口 + DS 大白话总结 + 额度注明。
    v3.0 批C：启动后观察窗口 + 更严格风控 + payload 落盘。"""
    sec, stocks = board['sec'], board['stocks']
    conf_rows, _why_html = _conf_rows_html(stocks, sec, board['fzn'])
    follow = [s for s in stocks if not _is_lu(s)]
    follow_rows = ''
    if follow:
        for i, s in enumerate(follow):
            if i < 2:   # 前 2 只完整六段逻辑；第 3 只起只写名称+涨幅（防卡片过长）
                deep = _deep_logic(s, sec, len(stocks))
                deep_html = deep.replace('\n', '<br>')
                _cyc, _cyc_reason = _cycle_tag(s['code'], sec, 0)
                _cyc_html = (f'<div style="color:#8bd3c7;font-size:12px;margin-top:2px;">⏱ 周期视角：<b>{_cyc}</b> ｜ {_cyc_reason}</div>'
                             if _cyc else '')
                follow_rows += f"""<div style="background:#1f2635;border-left:3px solid {GOLD};border-radius:8px;padding:9px 11px;margin:6px 0;">
<div style="font-size:14px;font-weight:700;color:#fff;">{i + 1}. {s['name']} <span style="color:{GREY};font-size:12px;">{s['code']}</span> <span style="color:{_c(s['pct'])};font-weight:800;float:right;">+{float(s.get('pct') or 0):.1f}%</span></div>
{_cyc_html}
<div style="color:#ced4da;font-size:12px;line-height:1.7;margin-top:4px;">{deep_html}</div></div>"""
            else:
                follow_rows += (f'<div style="font-size:13px;color:#e9ecef;margin:2px 0;">{i + 1}. {s["name"]} '
                                f'<span style="color:{GREY};font-size:12px;">{s["code"]}</span> '
                                f'<span style="color:{_c(s["pct"])};font-weight:700;">+{float(s.get("pct") or 0):.1f}%</span>'
                                f'<span style="color:{GREY};font-size:12px;">（还没涨停）</span></div>')
    else:
        follow_rows = '<div style="color:' + GREY + ';font-size:13px;">这个板块今天放量的票全封了涨停，已经没有还能上车的位置</div>'
    leader = next((s for s in stocks if s.get('role') == '龙头'), None)
    leader_txt = leader['name'] if leader else '未标注'
    watch_risk = (f'<div style="margin-top:10px;padding:9px 11px;background:#1c2830;border-left:4px solid {GOLD};border-radius:8px;font-size:13px;color:#e2e8f0;">'
                  f'<b>盯这几件事：</b>龙头 {leader_txt}｜同步 {board["fzn"]} 只｜止损位由各票技术位给<br>'
                  f'<span style="color:{GREY};">跌破各自技术止损位就直接走，不扛</span></div>')
    ds_html = _board_ds(board, mscore)
    ds_block = (f'<div style="margin-top:10px;padding:10px;background:#232a3a;border-left:4px solid #a78bfa;'
                f'border-radius:8px;font-size:13px;line-height:1.8;color:#e2e8f0;">🤖 DS 大白话总结：{md2html(ds_html)}</div>'
                if ds_html else '')
    exhausted = ''
    _conf_txt = ''
    _html = f"""<div style="background:#1f2635;border:2px solid {GOLD};border-radius:12px;padding:12px 14px;margin:10px 0;">
<div style="font-size:13px;color:#e9ecef;margin-bottom:6px;">🧭 今天整体：情绪{mlabel}（{mscore}分），{_cap_txt(mscore, mlabel)}。</div>
<div style="font-size:13px;color:{RED};font-weight:800;">🚀 为什么现在看这个板块</div>
<div style="color:#e9ecef;font-size:13px;margin-top:4px;">{sec} 今日 <b style="color:{GOLD}">{board['fzn']} 只</b>同时放量上涨。</div>
{_why_html}
<div style="margin-top:10px;font-size:14px;font-weight:800;color:{TEAL};">同步启动确认（{board['fzn']} 只）</div>{conf_rows}
<div style="margin-top:10px;font-size:14px;font-weight:800;color:{TEAL};">可跟（未涨停，按顺序优先级）</div>{follow_rows}
{watch_risk}
{ds_block}{exhausted}
<div style="color:{GREY};font-size:12px;margin-top:6px;">市场{mlabel}（{mscore}分）</div></div>"""
    _payload = _board_payload('启动卡', confidence, sec,
                              f'{sec} 今日 {board["fzn"]} 只同时放量（涨幅≥2.5%且量比≥1.8），同步启动确认（{_conf_txt}）',
                              lifecycle, stocks, '资金集中涌入、板块同步启动确认',
                              f'跟踪口径：龙头 {leader_txt}｜同步 {board["fzn"]} 只｜减仓/止损条件由本卡 AI 段给',
                              _VERIFY_NODES, data_source, board.get('dirty', []), _html)
    _append_push(_payload)     # 推送快照落盘（仅在推送路径调用；测试环境已打桩 git）
    return _html


_BOARD_WATCH_DS_SYS = ('''A股盘中主力意图反推与大白话作战指令 V3.0
一、你的角色
你是一名有丰富A股超短线实战经验的一线游资盘中决策助手。
你的工作不是罗列行情，不是复述新闻，而是根据当日真实行情，反推主力正在做什么（吸筹/洗盘/拉升/出货/对倒），并将研判转化为明确、可执行、可验证的交易条件。
你只解决五个问题：
1. 判断今天能不能做（主力进攻还是出货环境）
2. 判断主力真正围绕什么题材和业务交易
3. 判断谁是龙头、谁可能是有独立强度的龙二龙三、谁只是跟风炮灰
4. 判断哪只票满足条件后可以买、具体什么价格触发、什么情况必须放弃
5. 判断错误时最先出现什么危险信号、应该如何处理
最终输出必须使用自然、直接的大白话。
二、强制执行：先核实数据，再做判断
（保持原数据红线：只用真实数据、区分盘中/收盘、已涨停票不进可买名单、不预测明日涨跌等）
三、第一步：用大白话判断今天的市场环境（主力进攻意愿）
先判断：今天这行情，主力是在进攻，还是在出货。
计算市场情绪分（权重保持原结构），但解读时优先看主力行为。
一票否决规则保持，触发后直接写"不能开新仓"。
四、第二步：反推主力到底在炒什么
必须判断：主力围绕的具体业务、为什么进入前排、哪些股票先动、是龙头带动还是跟风、当前属于启动/加速/分歧/退潮的哪个阶段。
五、第三步：拆解龙头、龙二、龙三与跟风
每只股票核实：谁最先启动、谁成交额更大、谁有建仓痕迹、谁只是跟风。角色定义保持，但增加"有无明显建仓痕迹"判断。
六、第四步：把研判变成具体的交易条件
只有同时满足条件才允许进入可买名单：当日未涨停、情绪/阶段允许、涨幅符合环境限制、量比合理、价格回到支撑、分时结构OK、有建仓痕迹或筹码优势。
七、第五步：风险和仓位必须算清楚
（保持原风险预算与仓位计算逻辑）
八、最终输出：交易员大白话作战简报
严格按照原十一段结构输出，但所有判断必须带「主力意图」视角。已涨停股票只放热度证据，不列入买入候选。没有符合条件的标的时明确写"当前无符合条件的买入标的"。
九、强制自检
（保持原12条自检，并增加：确认每只可买票都检查了建仓痕迹/筹码状态；确认每只候选都先自问了「如果不推这只票，最硬的理由是什么」，理由成立即否决）
最终原则：先判断主力值不值得跟，再研究做哪只票；先反推主力，再验证买点；先确定失效条件，再讨论仓位。宁可明确说没有机会，也不制造虚假的交易机会。没有符合条件的标的时明确写"当前无符合条件的买入标的"，空推送是正确行为，禁止硬凑。
现在根据输入数据开始判断
''')


def _board_watch_ds(board, mscore, mlabel, lifecycle, candidates=None):
    """板块观察卡（可操作候选/操作信号/验证节点/风险）大模型生成。失败返回 {}（调用方回退规则模板）。"""
    if not MODELSCOPE_KEY:
        return {}
    try:
        payload = {
            'task': 'board_watch_next',
            'sec': board['sec'],
            'stocks': [{'name': s.get('name', ''), 'code': s.get('code', ''),
                        'pct': round(float(s.get('pct') or 0), 1),
                        'lb': round(float(s.get('lb') or 0), 1), 'role': s.get('role', ''),
                        'lu': _is_lu(s),
                        'f10': _stock_f10(str(s.get('code') or ''))[:60]}
                       for s in (board.get('stocks') or [])[:6]],
            'candidates': [{'name': s.get('name', ''), 'code': s.get('code', ''),
                            'pct': round(float(s.get('pct') or 0), 1),
                            'lb': round(float(s.get('lb') or 0), 1),
                            'turn': round(float(s.get('turn') or 0), 1),
                            'price': s.get('price'), 'prev': s.get('prev'),
                            'fzn': s.get('fzn', 0), 'sec': s.get('sec_clean', ''),
                            'type': s.get('type', '候选')}
                           for s in (candidates or [])[:5]],
            'fzn': board.get('fzn', 0),
            'market': {'score': mscore, 'label': mlabel},
            'lifecycle': lifecycle,
            'verify_nodes': _VERIFY_NODES,
            'format': ('严格按 system 的十一节结构输出交易员大白话作战简报（【一、当前时间与数据可信度】~【十一、最后给出最简单的执行总结】），所有数字带时点、全大白话、禁止输出JSON报表：'),
        }
        t = ask_deepseek(payload, purpose='board_watch', system_text=_BOARD_WATCH_DS_SYS)
        if not t:
            _diag_append('[board_watch_ds] LLM 返回空，回退规则模板')
            return {}
        t = t.strip()
        if t.startswith('```'):
            t = re.sub(r'^```[a-zA-Z]*\n?|\n?```$', '', t)
        try:
            d = json.loads(t)
        except Exception as _je:
            _diag_append('[board_watch_ds] JSON 解析失败: %s 原文前80=%s' % (str(_je)[:40], t[:80].replace('\n', ' ')))
            return {}
        # v3：优先尝试 JSON（兼容 v2 契约），否则按十一节文本返回
        _t2 = t.strip()
        if _t2.startswith('{'):
            try:
                _dj = json.loads(_t2)
                _keys = ['数据时点', '数据缺口', '市场情绪', '今天能不能做', '板块详细判断', '可以动手的票', '如果还不能买', '已在动的个股', '盘中重点盯', '最怕发生什么']
                if all(_k in _dj for _k in _keys):
                    for _k in _keys:
                        if _k in ('可以动手的票', '盘中重点盯', '已在动的个股', '市场情绪', '板块详细判断'):
                            continue
                        _dj[_k] = str(_dj[_k]).strip()
                    _wh = str(_dj.get('why') or '').strip()
                    for _p in ('为什么现在关注这个方向：', '为什么现在关注：', '为什么现在关注这个方向:', '为什么现在关注:', '为什么盯这个方向：', '为什么盯这个方向:'):
                        if _wh.startswith(_p):
                            _wh = _wh[len(_p):].strip()
                            break
                    _dj['why'] = _wh
                    return _dj
            except Exception:
                pass
        return {'v3': _t2}
    except Exception:
        return {}


def _clamp_pos(_pos, _max_cheng):
    """仓位档位硬约束（reson_b2）：把 半仓/2成/3成 等 clamp 到 ≤_max_cheng 成；空仓保留。"""
    _p = str(_pos or '').strip()
    if not _p:
        return _p
    if '空仓' in _p or '不买' in _p:
        return _p
    _is_half = any(k in _p for k in ('半仓', '五成', '四成', '三成'))
    _num = None
    for _kw, _v in (('半仓', 2), ('五成', 2), ('四成', 2), ('三成', 2), ('两成', 2), ('二成', 2),
                    ('1成', 1), ('一成', 1)):
        if _kw in _p:
            _num = _v
            break
    if _num is None:
        try:
            _m = re.search(r'[0-9一二三四五]+', _p)
            if _m:
                _num = int(_m.group(0))
        except Exception:
            _num = None
    if _num is None:
        return _p
    if _max_cheng <= 1:
        return '1成试探'
    if _is_half or _num > _max_cheng:
        return str(_max_cheng) + '成'
    return _p


def _board_watch_v3_html(text, green=GREEN, red=RED, gold=GOLD, teal=TEAL, grey=GREY):
    # V3 十一节大白话作战简报 -> 深色 HTML 卡片（按【N、标题】拆分成区块渲染）
    if not text:
        return ''
    _sec_color = {
        '一': '#a78bfa', '当前时间': '#a78bfa', '数据可信度': '#a78bfa',
        '二': green, '一句话作战结论': green, '作战结论': green,
        '三': '#8bc8ea', '市场情绪': '#8bc8ea',
        '四': teal, '资金反推': teal, '钱在做什么': teal,
        '五': gold, '龙头': gold, '拆解': gold,
        '六': green, '真正可以动手': green, '可以动手': green,
        '七': '#f4b393', '等待名单': '#f4b393',
        '八': '#f4b393', '已经启动': '#f4b393', '只看热度': '#f4b393',
        '九': '#8bc8ea', '盘中行动计划': '#8bc8ea',
        '十': red, '最危险的失败信号': red, '失败信号': red,
        '十一': gold, '执行总结': gold,
    }
    _parts = re.split(r'(【[一二三四五六七八九十]+、[^】]*】)', text)
    _out = []
    _cur_title = ''
    for _seg in _parts:
        if not _seg.strip():
            continue
        if _seg.startswith('【') and _seg.endswith('】'):
            _cur_title = _seg.strip()
            continue
        if not _cur_title:
            _cur_title = '研判'
        _c = '#e9ecef'
        for _kw, _col in _sec_color.items():
            if _kw in _cur_title:
                _c = _col
                break
        _body = '<br>'.join('　' + _l if _l.strip().startswith(('-', '·')) else _l
                            for _l in _seg.strip().split('\n') if _l.strip())
        _out.append('<div style="margin-top:8px;padding:9px 11px;background:#161e2b;border-left:4px solid ' + _c + ';border-radius:8px;font-size:13px;color:#e2e8f0;line-height:1.75;">'
                    '<b style="color:' + _c + ';">' + _cur_title + '</b><br>' + _body + '</div>')
    return ''.join(_out)


def _board_watch_llm_action(d, green=GREEN, red=RED):
    """严格版 action 段：📌今天能不能做(结论前置) + 🎯可以动手的票(数组渲染买入条件/触发信号/止损/仓位)；无票时显示如果还不能买。"""
    if not d:
        return ''
    # 共振档位硬约束（reson_b2）：C 空票 / B 最高1成 / A 最高2成(删半仓)；失败降级不约束
    _res_grade = ''
    try:
        _rr = _resonance()
        if _rr:
            _res_grade = _rr.get('grade') or ''
    except Exception:
        _res_grade = ''
    _h = ''
    # v2：数据时点 + 数据缺口（小条，置顶）
    _ts = d.get('数据时点', '')
    _gap = d.get('数据缺口', '')
    if _ts or _gap:
        _meta = []
        if _ts:
            _meta.append('🕐 数据时点：' + str(_ts))
        if _gap:
            _meta.append('📋 数据缺口：' + str(_gap))
        _h += ('<div style="margin-top:8px;padding:8px 11px;background:#1a2332;border-left:4px solid #a78bfa;border-radius:8px;font-size:12px;color:#a5b4cb;">'
               + '<br>'.join(_meta) + '</div>')
    # v2：市场情绪卡（分数/状态/总仓位上限/一票否决）
    _mo = d.get('市场情绪')
    if isinstance(_mo, dict) and _mo:
        _mobits = []
        for _mk, _ml in (('分数', '分数'), ('状态', '状态'), ('总仓位上限', '总仓位上限'), ('一票否决触发', '一票否决')):
            _mv = _mo.get(_mk)
            if _mv:
                _mobits.append('%s:%s' % (_ml, _mv))
        _h += ('<div style="margin-top:8px;padding:8px 11px;background:#14202b;border-left:4px solid #8bc8ea;border-radius:8px;font-size:12px;color:#cfe3f0;">'
               '<b>🧭 市场情绪：</b>' + ' ｜ '.join(_mobits) + '</div>')
    _can = d.get('今天能不能做', '')
    if _can:
        _h += ('<div style="margin-top:10px;padding:10px 12px;background:#12261e;border-left:4px solid ' + green + ';border-radius:8px;font-size:14px;color:#e2e8f0;">'
               '<b style="color:' + green + ';">📌 今天能不能做：</b>' + str(_can).replace('\n', '<br>') + '</div>')
    _tks = d.get('可以动手的票') or []
    # 共振档位硬约束（reson_b2）：C 档强制空票（「空仓等」+列瓦解证据由 why/risk 区承担）
    _res_note = ''
    if _res_grade == 'C' and isinstance(_tks, list) and _tks:
        _tks = []
        _res_note = ''
    elif isinstance(_tks, list):
        _cap = 1 if _res_grade == 'B' else 2  # B 档最高1成；A/未知 最高2成(删半仓)
        for _t in _tks:
            if isinstance(_t, dict) and _t.get('仓位'):
                _t['仓位'] = _clamp_pos(_t['仓位'], _cap)
    if isinstance(_tks, list) and _tks:
        _items = []
        for _t in _tks:
            if isinstance(_t, dict):
                _nm = str(_t.get('名字', '') or '').strip()
                if not _nm:
                    continue
                _role = _t.get('角色', '')
                _items.append('<div style="margin-top:8px;padding:8px 10px;background:#1e2a24;border-radius:8px;font-size:13px;color:#e2e8f0;">'
                              '<b style="color:' + green + ';">🔹 ' + _nm + ('</b> <span style="color:#a5b4cb;">[' + str(_role) + ']</span>' if _role else '</b>')
                              + (f'<br>🎖 角色依据：{_t.get("角色依据","")}' if _t.get('角色依据') else '')
                              + (f'<br>💰 买入条件：{_t.get("买入条件","")}' if _t.get('买入条件') else '')
                              + (f'<br>⚡ 触发信号：{_t.get("触发信号","")}' if _t.get('触发信号') else '')
                              + (f'<br>❌ 失效条件：{_t.get("失效条件","")}' if _t.get('失效条件') else '')
                              + (f'<br>🛑 止损：{_t.get("止损","")}' if _t.get('止损') else '')
                              + (f'<br>🧮 仓位：{_t.get("仓位","")}' if _t.get('仓位') else '')
                              + '</div>')
        if _items:
            _h += ('<div style="margin-top:10px;padding:10px 12px;background:#1e2a24;border-left:4px solid ' + green + ';border-radius:8px;font-size:13px;color:#e2e8f0;">'
                   '<b>🎯 可以动手的票：</b>' + ''.join(_items) + '</div>')
    if not _tks:
        _wait = d.get('如果还不能买', '')
        _h += ('<div style="margin-top:10px;padding:10px 12px;background:#1e2a24;border-left:4px solid ' + green + ';border-radius:8px;font-size:13px;color:#e2e8f0;">'
               '<b>🎯 今日无符合严格低吸标准的票</b>' + _res_note + '<br>'
               + (f'⏳ 要等：{str(_wait).replace(chr(10), "<br>")}' if _wait else '空仓等待')
               + '</div>')
    return _h


def _board_watch_llm_rest(d, gold=GOLD, teal=TEAL, red=RED, grey=GREY):
    """严格版剩余段：盘中重点盯(数组) + 最怕发生什么；字段缺失由调用方回退规则段。"""
    if not d:
        return ''
    _h = ''
    _mv = d.get('已在动的个股') or []
    if isinstance(_mv, list) and _mv:
        _rows = '<br>'.join('🔥 ' + str(_p).replace('\n', '<br>') for _p in _mv if str(_p).strip())
        _h += ('<div style="margin-top:8px;padding:9px 11px;background:#232a18;border-left:4px solid #f4b393;border-radius:8px;font-size:13px;color:#e2e8f0;">'
               '<b>已在动的个股（仅热度证据，不追）：</b><br>' + _rows + '</div>')
    _pts = d.get('盘中重点盯') or []
    if isinstance(_pts, list) and _pts:
        _rows = '<br>'.join('👉 ' + str(_p).replace('\n', '<br>') for _p in _pts if str(_p).strip())
        _h += ('<div style="margin-top:8px;padding:9px 11px;background:#1c2830;border-left:4px solid ' + gold + ';border-radius:8px;font-size:13px;color:#e2e8f0;">'
               '<b>盘中重点盯（出现什么 → 做什么动作）：</b><br>' + _rows + '</div>')
    _fear = d.get('最怕发生什么', '')
    if _fear:
        _h += ('<div style="margin-top:8px;padding:8px 10px;background:#2a1f22;border-left:4px solid ' + red + ';border-radius:8px;font-size:13px;color:' + red + ';">'
               '⚠️ 最怕发生什么：' + str(_fear).replace('\n', '<br>') + '</div>')
    return _h


def _board_watch_llm_html(d, gold=GOLD, teal=TEAL, red=RED, grey=GREY):
    """LLM 四段整段（兼容旧调用：action+rest 拼接）。"""
    if not d:
        return ''
    return _board_watch_llm_action(d) + _board_watch_llm_rest(d, gold=gold, teal=teal, red=red, grey=grey)





def _board_watch_card(board, mscore, mlabel, confidence='高', lifecycle='', data_source='eastmoney', candidates=None):
    """👀 板块观察卡：今天整体 → 为什么关注 → 明确题材 → 已动个股（角色，仅热度证据）→
    🎯 可操作候选（大模型从 candidates 挑低吸票：买入条件/触发/止损/仓位）→
    下一步盯什么（操作信号）→ 验证节点 → 风险。观察期不加仓，只做回踩企稳低吸。
    候选池由 _early_watch（启动埋伏/逼近涨停，未涨停）供给；LLM 失败回退规则。"""
    sec, stocks = board['sec'], board['stocks']
    conf_rows, _why_html = _conf_rows_html(stocks, sec, board['fzn'])
    mid = next((s for s in stocks if s.get('role') == '中军'), None)
    mid_txt = (f'优先盯中军 <b>{mid["name"]}</b>（放量最稳、跟龙头最紧）；补涨等龙头站稳再跟。'
               if mid else '先盯涨幅最高的龙头，等它站稳再看补涨。')
    _conf_txt = ''
    _nodes_html = '<br>'.join(f'⏱ {n}' for n in _VERIFY_NODES)
    _ds_watch = _board_watch_ds(board, mscore, mlabel, lifecycle, candidates=candidates)      # LLM 五段+为什么关注（失败返回 {}）
    if not _ds_watch:
        print('[board_watch] LLM 未返回且已禁规则版兜底，不推板块观察卡')
        return ''
    # v3：LLM 输出十一节文本 → 整段渲染；v2 兼容 JSON
    _v3_html = ''
    if isinstance(_ds_watch, dict) and _ds_watch.get('v3'):
        _v3_html = _board_watch_v3_html(_ds_watch['v3'])
    _why_llm = '' if _v3_html else (_ds_watch.get('板块详细判断') or _ds_watch.get('why', ''))
    if isinstance(_why_llm, dict):
        _wparts = []
        for _kk in ('资金在买什么逻辑', '板块阶段', '和昨天比差在哪', '跟风拥挤度', '结论'):
            _vv = _why_llm.get(_kk)
            if _vv:
                _wparts.append('<b>' + _kk + '：</b>' + str(_vv))
        _why_llm = '<br>'.join(_wparts)
    _why_llm_html = (f'<div style="color:#e9ecef;font-size:13px;margin-top:4px;border-left:3px solid {TEAL};padding-left:8px;">{_why_llm}</div>'
                     if _why_llm else '')
    _why_rule_html = (f'<div style="color:#e9ecef;font-size:13px;margin-top:4px;">{sec} 今日 <b style="color:{TEAL};">{board["fzn"]} 只</b>放量达标（涨幅≥2.5% 且 量比≥1.5）进入观察池，大模型暂不可用，详细逻辑盘中再推。</div>')
    _why_html_final = _why_llm_html
    _cand_html = ''
    if candidates:
        _cand_items = []
        for _c in candidates[:5]:
            _tp = _c.get('type', '候选')
            _cand_items.append(f'<b>{_c.get("name", "")}</b>（{_c.get("pct", 0):+.1f}% / 量比{_c.get("lb", 0):.1f} / {_tp}）→ 买：回踩分时均线或开盘价企稳；触发：量比维持、站上昨收；止损：破成本-3%；仓位：1成试探')
        _cand_html = '<br>'.join(_cand_items)
    else:
        _cand_html = '今日无可介入候选：等同题材第 3 只同步启动、或龙头回踩企稳后再动手。'
    _watch_rules_action = ('<div style="margin-top:10px;padding:10px 12px;background:#1e2a24;border-left:4px solid ' + GREEN + ';border-radius:8px;font-size:13px;color:#e2e8f0;">'
                           '<b>🎯 可操作候选（低吸埋伏，不追已涨停）：</b><br>' + _cand_html + '</div>')
    _watch_rules_rest = ('<div style="margin-top:8px;padding:9px 11px;background:#1c2830;border-left:4px solid ' + GOLD + ';border-radius:8px;font-size:13px;color:#e2e8f0;">'
                         '<b>下一步盯什么（出现什么 → 做什么动作）：</b><br>'
                         '👉 ① 第 3 只达标（涨幅≥2.5% 且 量比≥1.8）→ 板块确认，低吸未涨停补涨<br>'
                         '👉 ② 龙头或中军量比放大到 2.5 以上 → 盯同题材未涨停票回踩企稳<br>'
                         '👉 ③ 板块出现消息/事件催化（涨价、政策等）→ 确认信号出现再动手</div>'
                         '<div style="margin-top:8px;padding:9px 11px;background:#232a3a;border-left:4px solid #a78bfa;border-radius:8px;font-size:13px;color:#e2e8f0;">'
                         '<b>⏱ 验证节点（到点回来看一眼）：</b><br>' + _nodes_html + '</div>'
                         '<div style="margin-top:8px;font-size:13px;color:#e2e8f0;">🎯 确认后优先跟谁：' + mid_txt + '</div>'
                         '<div style="margin-top:8px;padding:8px 10px;background:#2a1f22;border-left:4px solid ' + RED + ';border-radius:8px;font-size:13px;color:' + RED + ';">'
                         '⏳ 当前仍是观察期，建议先不加仓，等确认信号再动手。<br>'
                         '⚠️ 风险：量比普遍掉到 1.5 以下，或第 3 只迟迟不出现 → 说明资金没接上，放弃关注。<b>若龙头炸板或板块红盘不足 2 只，则观察失败。</b></div>')
    # bw_card_reorder：新版低吸观察卡——action(低吸候选)前置为核心，已动个股仅作热度证据后移
    if _v3_html:
        _action_final = _v3_html
        _rest_final = ''
    else:
        _action_final = _board_watch_llm_action(_ds_watch)
        _rest_final = _board_watch_llm_rest(_ds_watch)
    conf_rows, _why_html = _conf_rows_html(stocks, sec, board['fzn'], deep_rows=False)
    _deep_block = ''
    try:
        _deep_map = _board_stocks_deep(stocks, sec, board['fzn'])
        _deep_rows = []
        for _sd in stocks[:5]:
            _d = _deep_map.get(_sd['name'])
            if not _d:
                _kk = _sd['name'][:4]
                for _k, _v in _deep_map.items():
                    if _k[:4] == _kk or _kk in _k:
                        _d = _v
                        break
            if _d and (_d.get('logic') or _d.get('why')):
                _opcol = {'别追': RED, '轻仓试': TEAL, '看': GOLD, '观望': GREY}.get(_d.get('op', ''), GOLD)
                _opx = _d.get('op', '')
                _op_txt = (f'<br>💡 操作：<b style="color:{_opcol};">{_opx}</b>'
                           + (f' ｜ 买点：{_d.get("buy","")} ｜ 止损：{_d.get("stop","")}' if (_d.get('buy') or _d.get('stop')) else '')) if (_opx or _d.get('buy')) else ''
                _x_txt = (f'<br>🪜 介入/退出：{_d.get("exit","")}' if _d.get('exit') else '')
                _v_txt = (f'<br>🏷️ 角色：{_d.get("role","")} ｜ 受益：{_d.get("real_benefit","")} ｜ 结论：<b style="color:{RED if _d.get("verdict")=="不碰" else (TEAL if _d.get("verdict")=="终审推荐" else GOLD)};">{_d.get("verdict","")}</b> ｜ 阶段：{_d.get("stage","")}' if (_d.get('verdict') or _d.get('stage') or _d.get('resonance')) else '')
                _dr_txt = (f'<br>⚠️ 暗雷：{_d.get("dark_risk","")}' if (_d.get('dark_risk') and _d.get('dark_risk') != '[]') else '')
                _deep_rows.append(f'<div style="background:#1c2830;border-left:3px solid {TEAL};border-radius:6px;padding:6px 8px;margin:3px 0 6px 0;font-size:12px;color:#ced4da;line-height:1.65;">🧠 个股逻辑：{_d.get("logic","")}<br>👉 大白话：{_d.get("why","")}{_v_txt}{_op_txt}{_x_txt}{_dr_txt}</div>')
        if _deep_rows:
            _deep_block = ('<div style="margin-top:10px;font-size:13px;font-weight:800;color:#e9ecef;">🔍 已动个股深挖（仅参考，非买入建议）</div>' + ''.join(_deep_rows))
    except Exception:
        _deep_block = ''
    _html = f"""<div style="background:#1f2635;border:2px solid {TEAL};border-radius:12px;padding:12px 14px;margin:10px 0;">
<div style="font-size:13px;color:#e9ecef;margin-bottom:6px;">🧭 今天整体：情绪{mlabel}（{mscore}分），{_cap_txt(mscore, mlabel)}。先看板块，别追已涨停。</div>
<div style="font-size:13px;color:{TEAL};font-weight:800;">👀 为什么现在关注这个方向</div>
{_why_html_final}
{_why_html}
{_action_final}
<div style="margin-top:8px;font-size:14px;font-weight:800;color:{GOLD};">📌 关注方向：{sec}</div>
<div style="margin-top:10px;font-size:13px;font-weight:800;color:{TEAL};">已经在动的个股（{board['fzn']} 只 · 仅热度证据，不追）</div>{conf_rows}
{_rest_final}
{_deep_block}
<div style="color:{GREY};font-size:12px;margin-top:6px;">市场{mlabel}（{mscore}分）｜ 已涨停仅作热度证据</div></div>"""
    _payload = _board_payload('观察卡', confidence, sec,
                              f'{sec} 今日 {board["fzn"]} 只同步放量（量比≥1.5），板块同步启动（{_conf_txt}）',
                              lifecycle, stocks, '量能放大、板块同步启动', 
                              '若龙头炸板或板块红盘不足 2 只，则观察失败；量比普遍掉到 1.5 以下放弃关注',
                              _VERIFY_NODES, data_source, board.get('dirty', []), _html)
    _append_push(_payload)     # 推送快照落盘（仅在推送路径调用；测试环境已打桩 git）
    return _html


# ============ 新增C·主线健康度卡（score<50 → 本轮不追高，渲染前降级「轻仓试」） ============
HEALTH_DEDUPE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'health_dedupe.json')


def _health_dedupe(key):
    """健康度卡按 日期小时 去重。"""
    try:
        with open(HEALTH_DEDUPE_PATH, encoding='utf-8') as f:
            d = json.load(f)
    except Exception:
        d = {}
    if d.get(key) == _bj_now().strftime('%Y-%m-%d %H'):
        return True
    d[key] = _bj_now().strftime('%Y-%m-%d %H')
    try:
        os.makedirs(os.path.dirname(HEALTH_DEDUPE_PATH), exist_ok=True)
        with open(HEALTH_DEDUPE_PATH, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        _git_commit_push(HEALTH_DEDUPE_PATH, 'update health dedupe')
    except Exception:
        pass
    return False


def _health_card(lu, zb, zbr, max_lbc, secs, money_flow):
    """🛡️ 主线健康度：综合 涨停/炸板率/最高板/板块涨停家数/资金 → LLM 打分 0-100。
    score<50 → can_chase=false，本轮板块卡一律不追（降「观察」）。失败/预算用尽 → ''（不空推）。"""
    if not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return ''
    key = 'health|' + _bj_now().strftime('%Y-%m-%d')
    if _health_dedupe(key):
        return ''
    _g = load_position_gauge()
    _g_txt = ('仓位仪表盘：' + str(_g.get('suggest', '')) + '（' + str(_g.get('source', '')) + '）' if _g else '仓位仪表盘未生成')
    fmt = ('你是一线游资，评估今日市场主线健康度（综合下面数据），优先看：主力资金是否还在、龙头是否还在控盘、跟风是否失控。只输出 JSON：\n'
           '{"score":0-100,"stage":"启动/发酵/高潮/退潮","can_chase":true或false,"reason":"大白话为什么(≥20字，必须含主力行为)","action":"具体动作(≤2句,含仓位档 空仓/1成/2成/半仓)"}\n'
           '涨停{lu}只 炸板{zb}只(炸板率{zbr:.0f}%) 最高{max_lbc}板；板块涨停家数：{secs}；资金：{money_flow}\n'
           + _g_txt + '\n'
           '打分依据：炸板率>45% 或最高板断板 → 分数≤50；score<50 时 can_chase 必须 false；禁模板句、禁「值得关注」。')
    t = ask_deepseek({'task': 'health_card', 'lu': lu, 'zb': zb, 'zbr': zbr, 'max_lbc': max_lbc,
                      'secs': secs, 'money_flow': money_flow, 'gauge': _g, 'format': fmt}, purpose='health')
    if not t:
        return ''
    try:
        _j = json.loads(t)
    except Exception:
        return ''
    try:
        score = int(float(_j.get('score', 0)))
    except Exception:
        score = 0
    chase = bool(_j.get('can_chase'))
    sc = RED if score < 50 else (GOLD if score < 75 else TEAL)
    mark = '🟥 主线走弱，本轮只观察不追高' if score < 50 else ('🟨 有分歧，挑强的不碰弱的' if score < 75 else '🟩 主线健康，可跟强不追高')
    return (f'<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ffd43b;">🛡️ 主线健康度</div>'
            f'<div style="background:#1c2230;border-left:4px solid {sc};border-radius:8px;padding:9px 11px;margin:5px 0;font-size:13px;">'
            f'<b style="color:#fff;">健康度 {score}/100</b> <span style="color:{sc};">{mark}</span>'
            f'<span style="color:{GREY};font-size:12px;"> ｜ 阶段：{_j.get("stage","")}</span><br>'
            f'<span style="color:#ced4da;font-size:12px;">🧠 {_j.get("reason","")}</span><br>'
            f'<span style="color:{GOLD};font-size:12px;">🎯 {_j.get("action","")}</span></div>')


_LINK_DS_SYS = ('你是一线游资，写「板块联动确认」提示。某题材今日多只个股同时达标（同题材≥3只放量，领涨股已确认），你要用大白话讲清楚：板块共振确认意味着主力开始扩散做板块、资金在干嘛、接下来重点盯什么失败信号。只基于输入数据说话，禁编；禁模板句；结论先行。只输出 JSON：{"logic":"板块同步启动意味着什么(≥25字,大白话,结合家数与领涨股+主力意图)","risk":"接下来要盯的失败信号(≥12字,给具体量价条件)"}，不要其他文字。')


def _link_ds(sec, n, lead):
    """联动确认 LLM 大白话（失败 '' → 调用方回退规则文案）。"""
    if not MODELSCOPE_KEY:
        return ''
    try:
        fmt = ('板块「' + sec + '」今日 ' + str(n) + ' 只达标（同步启动）' + ('，' + lead + ' 领涨' if lead else '')
               + '。只输出 JSON：{"logic":"板块同步启动意味着什么(≥25字,大白话,结合家数与领涨股,禁模板句)","risk":"接下来要盯的失败信号(≥12字,给具体量价条件)"}，不要其他文字')
        t = ask_deepseek({'task': 'link_confirm', 'sec': sec, 'fzn': n, 'lead': lead, 'format': fmt},
                         purpose='link_confirm', system_text=_LINK_DS_SYS)
        if not t:
            return ''
        _j = json.loads(t)
        _l = str(_j.get('logic') or '').strip()
        if not _l:
            return ''
        _r = str(_j.get('risk') or '').strip()
        _h = ('<div style="background:#1c2830;border:2px solid ' + TEAL + ';border-radius:12px;padding:10px 14px;margin:10px 0;">'
              '<div style="font-size:15px;font-weight:900;color:' + TEAL + ';">🔄 联动确认</div>'
              '<div style="color:#e9ecef;font-size:13px;margin-top:6px;">' + _l + '</div>'
              + (('<div style="color:' + RED + ';font-size:12px;margin-top:4px;">⚠️ 盯失败信号：' + _r + '</div>') if _r else '') + '</div>')
        return _h
    except Exception:
        return ''


def build_watch():
    """盘中异动（仅北京盘中 09:30-11:30/13:00-14:50 推送，14:50 硬停；--force 演示时跳过闸门）：
    ①启动埋伏/逼近涨停（资金量能优先，不等涨停）→ ②题材启动（同题材≥3只放量）→
    ③老龙头回流（回踩后重新放量）→ ④新闻发酵。构建超过 30 秒丢弃（防延迟）。全部当日按股去重。"""
    bj = _bj_now()
    if not FORCE_SLOT and not _in_session(bj):
        print(f'[watch] 当前北京时间 {bj.strftime("%H:%M")} 不在异动窗口(09:30-11:30/13:00-14:50)，不推盘中异动')
        return None
    _t0 = time.time()                                   # 150 秒构建超时闸（双层LLM深挖需 60-120s；watch 每10分钟一次，可容忍）
    def _timeout():
        return time.time() - _t0 > 150

    idx = get_indices()
    d = get_pools()
    mscore, mlabel, _ = market_score(idx, d)
    today = bj.strftime('%Y-%m-%d')
    al = load_alerts()
    if al.get('date') != today:
        al = {'date': today, 'fired': []}
    fired = set(al['fired'])
    new_cards = []

    mem = load_memory()
    days = sorted(mem.keys(), reverse=True)
    yest = days[1] if len(days) > 1 else None
    yest_sec = set(mem.get(yest, {}).keys()) if yest else set()

    # 0) 盘中预警（资金量能优先：启动埋伏/逼近涨停，涨停前介入；偏空门槛上调）
    ambush, near = _early_watch(mlabel if mlabel in ('偏空',) else ('偏空' if mscore < 40 else '震荡'))
    fit = ('情绪偏多/中性，可积极' if mscore >= 55 else '情绪偏弱，谨慎、仓位减半')
    # 0+) 板块启动雷达（最高优先级：同题材≥3只共振 → 推「板块启动提醒」卡而非单只涨停票；
    #     一次只推最强 1 个板块；当日该板块去重；已涨停仅作热度证据、可跟区严格剔除）
    try:
        _rows_b = _clist_gainers()
    except Exception:
        _rows_b = []
    print(f'[board] 拉取涨幅榜 {len(_rows_b)} 只（市场{mlabel}/{mscore}分）')
    health = _data_health(_rows_b)
    print(f'[board] 数据源健康: valid={health["valid_count"]} abnormal={health["abnormal"]} '
          f'conservative={health["conservative"]} confidence={health["confidence"]}')
    _bias = mlabel if mlabel in ('偏空',) else ('偏空' if mscore < 40 else '震荡')
    _dsrc = 'eastmoney' if health['confidence'] == '高' else ('cache' if health['confidence'] == '中' else 'eastmoney_abnormal')
    # 退潮反向卡（独立于共振命中：曾推过正面卡且当前红盘<2）
    for _rtheme, _rprev in _detect_retreat(_rows_b, fired, today):
        print(f'[board] 退潮检测: {_rtheme} 红盘<2（此前{_rprev}）→ 推反向观察卡')
        fired.add(f'R|{_rtheme}|{today}')
        al['fired'] = list(fired)[-200:]
        save_alerts(al)
        _append_push(_board_payload('反向观察卡', health['confidence'], _rtheme,
                                    f'{_rtheme} 退潮：龙头炸板/红盘不足 2 只/资金撤离', _rprev,
                                    [], '红盘家数不足2只（代码统计）', '转弱事实已成立，具体动作见本卡 AI 判读',
                                    [], _dsrc, [], _board_reverse_card(_rtheme, _rprev)))
        return _wrap(f'<div style="color:{RED};font-size:14px;font-weight:700;">↩️ {_bj_now().strftime("%H:%M")} 板块退潮 · 退出提醒</div>{_board_reverse_card(_rtheme, _rprev)}',
                     '↩️', '板块退潮提醒')
    if health['confidence'] != '低':
        board = _board_start(_rows_b, _bias, min_cnt=3 + (1 if health['conservative'] else 0),
                             need_streak=True)
        if board:
            print(f'[board] 板块启动命中: {board["sec"]} 共振{board["fzn"]}只')
        else:
            print('[board] 无≥3只共振题材，走原异动/新闻流程')
        if board:
            _append_dirty_log(board.get('dirty'))
            key = f'B|{board["sec"]}|{today}'
            if key not in fired:
                _lc = _theme_lifecycle(board['sec'], board['stocks'])
                _save_cache_themes(board['sec'], [s['code'] for s in board['stocks']])
                try:
                    with open(LIFECYCLE_PATH, encoding='utf-8') as _f:
                        _lcdata = json.load(_f)
                    _seen = (_lcdata.get(board['sec']) or {}).get('seen_count', 1)
                    for _st in board['stocks']:
                        _st['is_first'] = (_seen == 1)
                except Exception:
                    pass
                if _lc == '退潮':
                    print(f'[board] {board["sec"]} 生命周期=退潮，改推反向观察卡')
                    fired.add(f'R|{board["sec"]}|{today}')
                    al['fired'] = list(fired)[-200:]
                    save_alerts(al)
                    _append_push(_board_payload('反向观察卡', health['confidence'], board['sec'],
                                                f'{board["sec"]} 生命周期进入退潮', '退潮',
                                                board['stocks'], '红盘家数不足2只（代码统计）',
                                                '转弱事实已成立，具体动作见本卡 AI 判读',
                                                [], _dsrc, board.get('dirty', []),
                                                _board_reverse_card(board['sec'], '发酵/高潮')))
                    return _wrap(f'<div style="color:{RED};font-size:14px;font-weight:700;">↩️ {_bj_now().strftime("%H:%M")} 板块退潮 · 退出提醒</div>{_board_reverse_card(board["sec"], "发酵/高潮")}',
                                 '↩️', '板块退潮提醒')
                fired.add(key)
                al['fired'] = list(fired)[-200:]
                save_alerts(al)
                _emotion = sentiment(idx, d)[0]
                _card = _board_card(board, mscore, mlabel, confidence=health['confidence'], lifecycle=_lc, data_source=_dsrc)
                return _wrap(f'<div style="color:{GOLD};font-size:14px;font-weight:700;">🚀 {_bj_now().strftime("%H:%M")} 板块启动 · 市场{mlabel}({mscore}分)</div>{_card}{pos_cap_line(_emotion, None, mscore)}',
                             '🚀', '板块启动提醒')
    else:
        print('[board] confidence=低（数据异常且无缓存），禁推板块观察/启动卡')
    # 0++) 早期观察（降门槛版：≥2只 + 量比≥1.5，纯规则零 DS；比板块启动更早一步。
    #      观察推过可再推启动（升级路径，B|/O| key 独立）；启动推过则不倒退推观察。当日 O|{sec} 去重 1 次）
    if health['confidence'] != '低':
        key_o = key_b = None
        early = _board_start(_rows_b, _bias, min_cnt=2 + (1 if health['conservative'] else 0),
                             min_lb=1.5)
        if early:
            key_o = f'O|{early["sec"]}|{today}'
            key_b = f'B|{early["sec"]}|{today}'
            if key_b not in fired and key_o not in fired:
                _lc2 = _theme_lifecycle(early['sec'], early['stocks'])
                if _lc2 == '退潮':
                    print(f'[board] 早期观察 {early["sec"]} 生命周期=退潮，跳过')
                elif _lc2 in ('萌芽', '发酵'):
                    _append_dirty_log(early.get('dirty'))
                    try:
                        with open(LIFECYCLE_PATH, encoding='utf-8') as _f2:
                            _lcdata2 = json.load(_f2)
                        _seen2 = (_lcdata2.get(early['sec']) or {}).get('seen_count', 1)
                        for _st2 in early['stocks']:
                            _st2['is_first'] = (_seen2 == 1)
                    except Exception:
                        pass
                    print(f'[board] 早期观察命中: {early["sec"]} 共振{early["fzn"]}只（≥2只/量比≥1.5，纯规则）')
                    fired.add(key_o)
                    al['fired'] = list(fired)[-200:]
                    save_alerts(al)
                    _emotion = sentiment(idx, d)[0]
                    # watch_cand_filter：新版铁律——已涨停/涨幅≥7%大幅高开只作热度证据，不进入低吸候选
                    def _cand_ok(_s):
                        try:
                            return not _is_lu(_s) and float(_s.get('pct') or 0) < 7.0
                        except Exception:
                            return False
                    _cands = [dict(s, type='启动埋伏') for s in ambush[:3] if _cand_ok(s)] + [dict(s, type='逼近涨停') for s in near[:2] if _cand_ok(s)]
                    _card = _board_watch_card(early, mscore, mlabel, confidence=health['confidence'], lifecycle=_lc2, data_source=_dsrc, candidates=_cands)
                    if not _card:
                        print('[board] LLM 未返回且已禁规则版，不推板块观察卡')
                        return None
                    return _wrap(f'<div style="color:{TEAL};font-size:14px;font-weight:700;">👀 {_bj_now().strftime("%H:%M")} 板块观察 · 市场{mlabel}({mscore}分)</div>{_card}{pos_cap_line(_emotion, None, mscore)}',
                                 '👀', '板块观察')
                else:
                    print(f'[board] 早期观察 {early["sec"]} 生命周期={_lc2}，跳过观察卡')
            if key_o in fired:
                print(f'[board] 早期观察 {early["sec"]} 今日已推过观察卡，跳过')
            elif key_b in fired:
                print(f'[board] {early["sec"]} 已推过启动卡，不倒退推观察')
        if key_o and key_o in fired:
            print(f'[board] 早期观察 {early["sec"]} 今日已推过观察卡，跳过')
        elif key_b in fired:
            print(f'[board] {early["sec"]} 已推过启动卡，不倒退推观察')
    for s in ambush[:4]:
        key = f"{s['name']}|埋伏"
        if key in fired:
            continue
        if not s['sec_clean'] or s['sec_clean'] == '其他':
            _fix = _stock_industry(s.get('code') or '')
            if _fix:
                s['sec_clean'] = _fix
        heat = _theme_heat([s])[0].get(s['sec_clean'], 0)
        sg = {'n': s['name'], 'code': s['code'], 'type': '启动埋伏', 'price': s.get('price'),
              'sec': s['sec_clean'], 'pct': s['pct'], 'lb': s['lb'], 'turn': s['turn'],
              'score': round(min(10.0, (heat / 10.0 if heat else 0.0)), 1),
              'act': '提前埋伏', 'pos': '1-2成',
              'buy': '回踩分时均线/开盘价企稳介入', 'stop': '破成本-3%或启动低点走',
              'why': f"{s['sec_clean']}现涨{s['pct']:+.1f}%刚启动，同题材{s.get('fzn', 0)}只同步放量(共振)，量比{s['lb']:.1f}，分时站上昨收，涨停前可埋伏，破位即走。"}
        _quote_card(sg)
        new_cards.append((key, sg))
    for s in near[:4]:
        key = f"{s['name']}|逼近"
        if key in fired:
            continue
        if not s['sec_clean'] or s['sec_clean'] == '其他':
            _fix = _stock_industry(s.get('code') or '')
            if _fix:
                s['sec_clean'] = _fix
        heat = _theme_heat([s])[0].get(s['sec_clean'], 0)
        strong = s['lb'] >= 1.8
        sg = {'n': s['name'], 'code': s['code'], 'type': '逼近涨停', 'price': s.get('price'),
              'sec': s['sec_clean'], 'pct': s['pct'], 'lb': s['lb'], 'turn': s['turn'],
              'score': round(min(10.0, (heat / 10.0 if heat else 0.0)), 1),
              'act': '可跟进' if strong else '先观察',
              'pos': '1-2成' if strong else '空仓等信号',
              'buy': '回踩分时均线不破介入' if strong else '放量突破再跟',
              'stop': '破成本-3%或当日低点走',
              'why': f"{s['sec_clean']}现涨{s['pct']:+.1f}%未封板，量比{s['lb']:.1f}·换手{s['turn']:.1f}%，"
                     f"{'放量抢筹，可提前介入' if strong else '量能一般，先观察'}(涨停后不追)。"}
        _quote_card(sg)
        new_cards.append((key, sg))
    if _timeout():
        print('[watch] 构建超时(>150s)，丢弃本次异动推送（防止延迟）')
        return None
    # 1) 题材启动：同题材≥3只同时放量上涨（涨幅≥2% 且量比≥1.5，无需涨停；昨日已有板块交老龙头回流）
    grp = defaultdict(list)
    try:
        _rows = _clist_gainers()
    except Exception:
        _rows = []
    for s in _rows:
        ind = re.sub(r'[行业板块概念\s]+', '', s.get('industry') or '') or '其他'
        if s['pct'] >= 2.0 and s['lb'] >= 1.5:
            grp[ind].append(s)
    for name, stocks in grp.items():
        if len(stocks) < 3:
            continue
        if name in d.get('themes', {}):
            continue
        for st in stocks[:1]:
            key = f"{st.get('n')}|启动"
            if key in fired:
                continue
            sg = suggestion(st, name, theme_score(name, stocks, False)[0], '题材启动', mlabel)
            sg['why'] = (f'{name}今天{len(stocks)}只同时放量上涨（涨幅都在5%以内，还没到涨停，属于底部先动）'
                         f'｜市场档位：{mlabel}')
            _quote_card(sg)
            new_cards.append((key, sg))
    # 2) 老龙头回流：昨日涨停/连板票今日回踩后重新放量上攻（量比≥1.5）
    seen = set()
    for pd in days[:3]:
        for sec, info in mem.get(pd, {}).items():
            for nm in (info.get('leaders', []) if isinstance(info, dict) else []):  # 数据异常防御（WATCH_GUARD）
                if nm in seen:
                    continue
                seen.add(nm)
                st = next((x for stocks in d['sectors'].values() for x in stocks if x.get('n') == nm), None)
                if not st:
                    continue
                if not (st.get('lb', 0) >= 1.5):       # 必须重新放量才算回流
                    continue
                key = f'{nm}|回流'
                if key in fired:
                    continue
                sg = suggestion(st, sec, 7, '老龙头回流', mlabel)
                sg['why'] = f'{sec}上次强势股{nm}今天重新放量上攻（量比{st.get("lb", 0):.1f}，是放量上攻）。'
                _quote_card(sg)
                new_cards.append((key, sg))
    if _timeout():
        print('[watch] 构建超时(>150s)，丢弃本次异动推送（防止延迟）')
        return None

    if not new_cards:
        # 价格无异动时，再看新闻发酵（高权重+命中题材才推，避免刷屏）
        news = get_news()
        dr = news_drive(news, d, mem)
        for item in dr:
            key = 'N|' + item['title'][:20]
            if key in fired:
                continue
            fired.add(key)
            tag = '📰 事件驱动' if item['merged'] else '📰 新闻发酵'
            _deep = _news_drive_deep(item, 'watch_news', rows=_rows)
            if _deep:
                _i = _strip_pre(_deep[1], ('影响：', '影响:'))
                _s2 = _strip_pre(_deep[2], ('代表个股：', '代表个股:', '个股：', '个股:'))
                _w = _strip_pre(_deep[3], ('大白话：', '大白话:', '人话：', '解读：'))
                _a = _strip_pre(_deep[4], ('操作：', '操作:'))
                _sec_txt = _i or item['sec']
                _lead_html = ('<div style="color:' + GREEN + ';font-size:12px;margin-top:4px;">📌 历史强势股：' + '、'.join(item['leaders']) + '</div>') if item['leaders'] else ''
                cards = ('<div style="background:#1f2635;border:2px solid ' + GOLD + ';border-radius:12px;padding:12px 14px;margin:10px 0;">'
                         '<div style="font-size:16px;font-weight:900;color:' + GOLD + ';">' + tag + '</div>'
                         '<div style="color:#fff;font-size:13px;margin-top:6px;line-height:1.7;">' + item['title'] + '</div>'
                         '<div style="color:' + GOLD + ';font-size:12px;margin-top:6px;">🎯 影响板块：' + _sec_txt + '</div>'
                         '<div style="color:#b197fc;font-size:12px;margin-top:4px;">🏆 代表个股：' + _s2 + '</div>'
                         '<div style="color:' + TEAL + ';font-size:12px;margin-top:4px;">🧠 大白话：' + _w + '</div>'
                         '<div style="color:' + RED + ';font-size:12px;margin-top:4px;">💡 操作：' + _a + '</div>'
                         + _lead_html + '</div>')
            else:
                _lead_html = ('<div style="color:' + GREEN + ';font-size:12px;margin-top:4px;">📌 历史强势股：' + '、'.join(item['leaders']) + '</div>') if item['leaders'] else ''
                cards = ('<div style="background:#1f2635;border:2px solid ' + GOLD + ';border-radius:12px;padding:12px 14px;margin:10px 0;">'
                         '<div style="font-size:16px;font-weight:900;color:' + GOLD + ';">' + tag + '</div>'
                         '<div style="color:#fff;font-size:13px;margin-top:6px;line-height:1.7;">' + item['title'] + '</div>'
                         '<div style="color:' + TEAL + ';font-size:13px;margin-top:6px;">影响板块：' + item['sec'] + '</div>'
                         + _lead_html
                         + '<div style="color:' + TEAL + ';font-size:12px;margin-top:6px;">👉 ' + ('板块已动，盯龙头，破-3%走' if item['merged'] else '暂未动，先加自选，板块放量再跟') + '</div></div>')

            return _wrap(f'<div style="color:{GOLD};font-size:14px;font-weight:700;">⏰ {_bj_now().strftime("%H:%M")} 新闻风向</div>{cards}',
                         '📰', '新闻发酵')
        return None
    # 记录本次触发价/买入下沿（供回踩确认跨 run 使用）
    sig_ctx = al.setdefault('sig_ctx', {})
    for key, sg in new_cards:
        try:
            sig_ctx[key] = {'trigger': float(sg.get('cur') or 0), 'buy_low': float(sg.get('buy_low') or 0)}
        except (TypeError, ValueError):
            pass
    for key, _ in new_cards:
        fired.add(key)
    al['fired'] = list(fired)[-200:]
    save_alerts(al)

    # 偏空：单次最多 2 张；正常 3 张（当日按股去重已在上方完成）
    bear = (mlabel == '偏空' or mscore < 40)
    max_cards = 2 if bear else 3
    # 最终版硬性筛选（13条，2026-11-02）：盘中异动候选先过筛，不过的不进补涨推演池
    _cards_tmp = []
    for _k, _sg in new_cards[:max_cards]:
        _ok, _rs = _hard_filter_pass(_sg.get('code'), _sg.get('n') or _sg.get('name') or '',
                                     _sg.get('cur') or _sg.get('price'))
        if _ok:
            _cards_tmp.append((_k, _sg))
        else:
            print(f'[spot] 硬性筛选剔除 {_sg.get("n")}({_sg.get("code")}): {_rs}')
    sel = _cards_tmp
    for _, sg in sel:
        sg['life'] = life_badge(sg.get('sec', ''), d, mem, days)  # 模块8 生命周期徽标
        sg['_factor'] = _factor_for_spot(sg, d)  # 因子体检（情绪/量价/资金/题材/动量+硬闸），失败为 None 不影响卡片
    try:
        _sig_rows = []
        for _, sg in sel:
            _f4 = sg.get('_factor')
            if not _f4:
                continue
            _sig_rows.append({'code': sg.get('code'), 'name': sg.get('n') or sg.get('name'),
                              'price': sg.get('cur') or sg.get('price'),
                              'jq': _f4.get('jq'), 'lj': _f4.get('lj'), 'zj': _f4.get('zj'),
                              'tc': _f4.get('tc'), 'dl': _f4.get('dl'),
                              'total': _f4.get('total'), 'combined': _f4.get('combined'),
                              'vetoed': _f4.get('vetoed')})
        _factor_signal_write('watch', _sig_rows)
    except Exception as _sig_e:
        print(f'[sigcsv] watch 接入异常 {_sig_e}')
    ds_plain = _spot_ds([sg for _, sg in sel], mem, days, today_top=_today_top(d)) if sel else {}
    _spot_gl = ''
    if isinstance(ds_plain, dict):
        _g = ds_plain.get('_global')
        if _g:
            _spot_gl = _spot_global_html(_g)
    _mk = (ds_plain or {}).get('_market') if isinstance(ds_plain, dict) else None
    _mk_html = ''
    if _mk and (_mk.get('state') or _mk.get('risk_budget') is not None):
        _rb = _mk.get('risk_budget')
        try:
            _rb_f = float(_rb)
        except (TypeError, ValueError):
            _rb_f = None
        _rb_txt = f'市场风险预算 {_rb_f:.2f}' if _rb_f is not None else ''
        _mk_emoji = ('🟢 可打' if (_rb_f or 0) >= 0.6 else '🟡 谨慎' if (_rb_f or 0) >= 0.35 else '🔴 低预算·最高只到「看」')
        _mk_html = f'<div style="background:#1c2830;border:2px solid {TEAL};border-radius:12px;padding:8px 12px;margin:8px 0;">'
        _mk_html += f'<div style="font-size:13px;font-weight:900;color:{TEAL};">🌐 市场环境 {_mk_emoji}</div>'
        if _mk.get('state'):
            _mk_html += f'<div style="margin-top:4px;font-size:12px;color:#c8d3e1;">状态：{_mk["state"]}</div>'
        if _rb_txt:
            _mk_html += f'<div style="margin-top:2px;font-size:12px;color:#c8d3e1;">{_rb_txt}</div>'
        if _mk.get('yesterday_check') and _mk['yesterday_check'] != '无':
            _mk_html += f'<div style="margin-top:2px;font-size:12px;color:#9aa4b8;">昨日对账：{_mk["yesterday_check"]}</div>'
        _mk_html += '</div>'
    _deep6_spot = _deep6_for_spot(ds_plain, sel) if sel else ''
    cards = _mk_html + _spot_gl + _deep6_spot + ''.join(_watch_card(sg, mscore, ds_plain) for _, sg in sel)
    # 联动确认：同题材当日≥3只达标 → 补一张（同一题材 10 分钟内最多 1 张，link_ts 冷却）
    now_ts = bj.timestamp()
    link_ts = al.setdefault('link_ts', {})
    sec_cnt = defaultdict(int)
    for _, sg in new_cards:
        sec_cnt[sg.get('sec', '')] += 1
    link_cards = ''
    for sec, n in sec_cnt.items():
        if n >= 3 and sec and (now_ts - link_ts.get(sec, 0)) >= 600:
            link_ts[sec] = now_ts
            lead = next((sg['n'] for _, sg in sel if sg.get('sec') == sec), '')
            _lk_llm = _link_ds(sec, n, lead)
            if not _lk_llm:
                # 联动确认的"共振意味着什么"必须由大模型给；未返回则不推规则版确认卡
                print(f'[link] {sec} 模型未返回，不推规则版联动确认卡')
                continue
            link_cards += _lk_llm
    if link_ts:
        save_alerts(al)
    # 回踩确认二次提醒（模块4）+ 持仓风控雷达（模块5）
    pb = pullback_check(al, d, fired)
    _push_secs = [sg.get('sec', '') for _, sg in sel] + list(sec_cnt.keys())
    hr = holdings_radar(al, secs=_push_secs)
    # 龙头分歧转一致（模块9）
    piv = pivot_monitor(d, al)
    # 信号日志（模块7）
    _log_signals('watch', [{'type': sg['type'], 'code': sg['code'], 'name': sg['n']} for _, sg in sel])
    emotion = sentiment(idx, d)[0]
    try:
        build_intraday()
    except Exception as _e:
        print('[intra] 异常:', _e)
    _body = cards + link_cards + pb + hr + piv
    if not _body.strip():
        # 空候选兜底：数据缺源/无达标候选时如实说明，不推空白卡
        _bad = [k for k, v in HEALTH['sources'].items() if not v['ok']]
        _body = (f'<div style="background:#1c2230;border-radius:8px;padding:10px 12px;margin:6px 0;">'
                 f'<div style="color:#e9ecef;font-size:13px;">本轮无异动候选：{mlabel}（{mscore}分），情绪{emotion}</div>'
                 f'<div style="color:{GREY};font-size:12px;margin-top:3px;">数据源：' + ('缺 ' + '、'.join(_bad) if _bad else '正常')
                 + '；有达标候选才出卡，不硬凑，等下一轮</div></div>')
    return _wrap(f'<div style="color:{RED};font-size:14px;font-weight:700;">⏰ {_bj_now().strftime("%H:%M")} 盘中异动 · 市场{mlabel}({mscore}分)</div>{_body}{pos_cap_line(emotion, None, mscore)}',
                 '🚨', '异动提醒')


# ============ 盘中异动监控（intra，涨停池增量六步）============
INTRA_STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'intraday_state.json')


def _intra_state():
    try:
        with open(INTRA_STATE_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_intra_state(st):
    try:
        with open(INTRA_STATE_PATH, 'w', encoding='utf-8') as f:
            json.dump(st, f, ensure_ascii=False)
    except Exception as _e:
        print('[intra] state 写盘失败:', _e)


def _intra_fingerprint(d):
    codes = sorted(x.get('c', '') for sec in d['sectors'].values() for x in sec)
    return f"{d['lu']}|{d['zb']}|{','.join(codes)}"


def _intra_ma5_price(code, price):
    """MA5 与现价相对位置（近5日收盘均线，不含今日未收盘根）。返回 (ma5, 是否贴近)。"""
    try:
        sym = ('sh' if code.startswith('6') else 'sz') + code
        arr = get_klines(sym, 40)
        if arr:
            today_s = _bj_now().strftime('%Y-%m-%d')
            b = arr[:-1] if str(arr[-1][0]) == today_s else arr
            closes = [float(r[2]) for r in b[-5:]]
            if len(closes) == 5 and all(v > 0 for v in closes):
                ma5 = sum(closes) / 5.0
                return ma5, price <= ma5 * 1.05
    except Exception:
        pass
    return None, False


def _intra_pos60(code, price):
    """60日区间位置（0~1），高位>0.85。"""
    try:
        sym = ('sh' if code.startswith('6') else 'sz') + code
        arr = get_klines(sym, 130)
        if arr:
            today_s = _bj_now().strftime('%Y-%m-%d')
            b = arr[:-1] if str(arr[-1][0]) == today_s else arr
            if len(b) >= 60:
                hi = max(float(r[3]) for r in b[-60:])
                lo = min(float(r[4]) for r in b[-60:])
                if hi > lo:
                    return (price - lo) / (hi - lo)
    except Exception:
        pass
    return None


def _INTRA_DS_SYS_text():
    return ('你是一位在A股盘中有10年以上实战经验的一线游资，最擅长用大白话讲盘。你的任务：基于我给的「涨停池实时快照」，把现在谁在动、为什么动、底层逻辑是什么、还能关注谁讲清楚，像跟兄弟连麦盯盘一样。\n'
            '强制规则：1. 只许用我给的数据说话，不许编造新闻。2. 全程大白话。3. 操作只给：别追 / 看 / 轻仓试 / 观望 / 持仓不动。4. 禁止万能句。5. 【底层核心逻辑·硬要求】每只新进票必须按这条逻辑链深挖：公司主业（翻译成人话）→题材关联（实受益/沾边/纯蹭）→建仓痕迹与筹码状态→资金本质→催化验证→暗雷。6. 必须区分驱动类型：消息驱动 / 资金行为 / 情绪扩散 / 业绩预期，并给出判断依据。7. 输出前自问：如果不推这只票，最硬的理由是什么？高位连板直接不碰。8. 只输出 JSON：\n'
            '{"overall":"情绪一句话+能不能追","mainline":"今日最强方向+还能不能跟","risk":"最大风险+什么情况立刻撤","per":[{"name":"股票名称","theme":"真实题材名","logic":"底层核心逻辑：主业+题材关联+建仓痕迹/筹码+资金本质+催化+暗雷，至少55字，用连贯大白话一段写","why":"大白话：一句话戳穿真假，至少18字","op":"别追/看/轻仓试/观望——必须与logic一致","buy":"买点具体条件","stop":"止损具体"}]}，per必须覆盖每只新进票。')


def _kline_ctx(code, price):
    """个股K线近况（供DS深度挖掘异动原因）：5日涨幅/量能放大倍数/60日位置/是否新高/站上MA5/连阳天数。失败返回 {}。"""
    try:
        sym = ('sh' if code.startswith('6') else 'sz') + code
        arr = get_klines(sym, 130)
        if not arr:
            return {}
        today_s = _bj_now().strftime('%Y-%m-%d')
        b = arr[:-1] if str(arr[-1][0]) == today_s else arr
        closes = [float(r[2]) for r in b]
        vols = [float(r[5]) for r in b]
        g5 = vol_r = up_days = None
        if len(closes) >= 8:
            c5 = closes[-5:]
            g5 = (c5[-1] / c5[0] - 1) * 100 if c5[0] else None
            v3 = sum(vols[-3:]) / 3.0
            v5p = sum(vols[-8:-3]) / 5.0
            vol_r = v3 / v5p if v5p > 0 else None
            up_days = 0
            for k in range(1, min(6, len(closes))):
                if closes[-k] >= closes[-k - 1]:
                    up_days += 1
                else:
                    break
        pos60 = new_high = None
        if len(closes) >= 60:
            hi = max(closes[-60:]); lo = min(closes[-60:])
            if hi > lo:
                pos60 = (price - lo) / (hi - lo)
            new_high = price >= hi * 0.99
        ma5 = sum(closes[-5:]) / 5.0 if len(closes) >= 5 else None
        return {'g5': round(g5, 1) if g5 is not None else None,
                'vol_r': round(vol_r, 1) if vol_r else None,
                'pos60': round(pos60, 2) if pos60 is not None else None,
                'new_high': bool(new_high) if new_high is not None else None,
                'above_ma5': (price >= ma5) if ma5 else None,
                'up_days': up_days}
    except Exception:
        return {}


def _board_hist(sec, mem, days):
    """板块近3日历史（供DS判断板块是真持续还是首日启动）：出现天数 + 龙头名单。"""
    if not mem:
        return '无板块历史记录'
    cnt = 0
    ldrs = []
    for pd in (days or [])[:3]:
        info = (mem.get(pd) or {}).get(sec)
        if info:
            cnt += 1
            ldrs.extend((info.get('leaders') or [])[:2])
    seen = []
    for x in ldrs:
        if x not in seen:
            seen.append(x)
    if cnt == 0:
        return '近3日板块无记录，今天可能是首日启动'
    return f'近3日板块出现{cnt}天，龙头：{"、".join(seen[:3])}'


def _zt_price(x):
    """ZTPool 现价：东财 p 字段=价格×1000，fallback 用 price。失败返回 0.0。"""
    try:
        if x.get('p') is not None and x.get('p') not in ('', None):
            return float(x.get('p')) / 1000.0
        return float(x.get('price') or 0)
    except Exception:
        return 0.0


def _intra_ds(now, prev_lu, d, top_new, ma5_map, pos_map, sec_cnt):
    """盘中异动 DeepSeek（每轮最多1次，计入当日≤8预算）。返回解析 dict；失败/用尽返回 None。"""
    import datetime as _dt
    zb_rate = d['zb'] / (d['lu'] + d['zb']) if (d['lu'] + d['zb']) else 0.0
    stk = []
    for x in top_new:
        c = x.get('c', '')
        ma5 = ma5_map.get(c, (None, False))[0]
        pos60 = pos_map.get(c)
        stk.append({'name': x.get('n', ''), 'code': c, 'industry': x.get('hybk') or '其他',
                    'lbc': int(x.get('lbc') or 0), 'fbt': str(x.get('fbt') or ''),
                    'pct': round(float(x.get('zdp') or 0), 2),
                    'turn': round(float(x.get('hs') or 0), 2),
                    'amount_wan': round(float(x.get('amount') or 0) / 1e4, 1),
                    'fund_wan': round(float(x.get('fund') or 0) / 1e4, 1),
                    'price': _zt_price(x),
                    'ma5': (round(ma5, 2) if ma5 else None),
                    'pos60': (round(pos60, 2) if pos60 is not None else None),
                    'news': _stock_news(x.get('n') or '', c),
                    'f10': _stock_f10(c),
                    'sector_lu_cnt': sec_cnt.get(x.get('hybk') or '其他', 0)})
    sec_top = sorted(sec_cnt.items(), key=lambda kv: -kv[1])[:6]
    payload = {
        'task': 'intraday_watch',
        'time': now.strftime('%H:%M'),
        'emotion': {'lu_before': prev_lu, 'lu_now': d['lu'], 'zb': d['zb'],
                    'zb_rate': round(zb_rate, 2), 'dt': d['dt']},
        'new_stocks': stk,
        'sector_top': [{'industry': k, 'lu_cnt': v} for k, v in sec_top],
        'holding': [{'name': h['name'], 'code': h['code']} for h in HOLDINGS],
        'format': ('以下是涨停池实时快照。严格输出 JSON（不要任何其他文字）：\n'
                   '每只票我给了 f10（公司简介+核心题材，公司到底干什么的）和 news（新闻标题，可能空）：'
                   '必须先用 f10 把公司主业翻译成一句接地气大白话（像跟朋友解释这家公司干嘛的，如「做电子元器件『网上超市』的」，禁止照抄书面简介），再用 news 佐证催化；news 为空就老实说「新闻源没抓到，从盘面数据推」，不许编。\n'
                   '【股票深挖铁律·每票强制】每只票完整执行：①本质（一句大白话）②暗线业务（具体产品+阶段+对业绩真实贡献，写不出写「未见明确暗线业务」）③真实关联与弹性（实受益/沾边/纯蹭+弹性大小）④为什么是它⑤破灭点（必写）⑥动作。logic字段必须包含以上全部要点；单票≤90字；逻辑不硬直接写「不碰」。\n'
                   '按【底层核心逻辑链】输出：①公司主业(一句人话)②题材关联(实受益/沾边/纯蹭)③资金本质(龙头/订单/摘帽/低价/情绪，可引用 fund_wan 资金流入)④催化验证(news)⑤暗雷。\n'
                   '{"overall":"情绪一句话+能不能追","mainline":"今日最强方向+还能不能跟","risk":"最大风险+什么情况立刻撤","contagion":"今天涨停/板块爆发会传染到哪个还没启动的题材/个股（点名具体股+传染逻辑与暗线；没有写「暂无明确传染方向」）","per":[{"name":"股票名称","theme":"真实题材名","driver":"涨停驱动：板块爆发/个股利好/资金接力/情绪扩散（写清判断依据：靠消息还是靠板块还是靠资金）","stage":"启动日|中段接力|末段高位|退潮反抽","verdict":"终审推荐|观察|不碰","evidence":["证据1","证据2"],"logic":"公司主业+题材关联+资金本质+催化+暗雷，至少55字，禁止只讲盘面高位、禁止固定比喻充当逻辑","why":"大白话，至少18字，比喻只能收尾一句","op":"别追/看/轻仓试/观望","buy":"买点具体条件","stop":"止损具体"}]}，'
                   '每条 logic 必须先写「我查到了什么」再下判断（真实数据摆在前：现价/涨幅/量比/换手/资金/F10主业一句/news催化），'
                   '禁止「值得关注/建议留意/板块强势带动/具备一定投资价值/XX概念+龙头」这类模板句；证据不足必须降级评级并说明原因；'
                   'lbc>=3 或 pos60>0.85 的票：op 只能「别追」、verdict 只能「不碰」，只解释原因；'
                   '大白话要让完全不懂股票的人听懂、老手觉得说到点子上。'
                   'per 必须覆盖每只新进票，没把握的也如实说。数据看不出的直接说看不出来。'),
    }
    txt = ask_deepseek(payload, purpose='intra', system_text=_INTRA_DS_SYS_text())
    if not txt:
        return None
    return _intra_parse_ds(txt, [x.get('n', '') for x in top_new])


def _intra_parse_ds(txt, names):
    """解析 DS 输出：优先 JSON（overall/mainline/risk/per[logic,why,op,buy,stop]），回退【情绪】/竖线行。"""
    out = {'overall': None, 'per': {}, 'mainline': None, 'risk': None, 'contagion': None}
    names_set = set(names)
    try:
        import json as _json
        _j = _json.loads(txt)
        out['overall'] = str(_j.get('overall') or '') or None
        out['mainline'] = str(_j.get('mainline') or '') or None
        out['risk'] = str(_j.get('risk') or '') or None
        out['contagion'] = str(_j.get('contagion') or '') or None
        for it in _j.get('per') or []:
            nm = str(it.get('name') or '').strip()
            nm = nm.split('（')[0].strip()
            if nm in names_set:
                out['per'][nm] = {'logic': str(it.get('logic') or ''), 'why': str(it.get('why') or ''),
                                  'op': str(it.get('op') or ''), 'buy': str(it.get('buy') or ''),
                                  'stop': str(it.get('stop') or ''), 'theme': str(it.get('theme') or ''),
                                  'stage': str(it.get('stage') or ''), 'verdict': str(it.get('verdict') or ''),
                                  'driver': str(it.get('driver') or ''),
                                  'evidence': it.get('evidence') if isinstance(it.get('evidence'), list) else []}
        return out
    except Exception:
        pass
    for ln in txt.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        if ln.startswith('【情绪】'):
            out['overall'] = ln[len('【情绪】'):].strip()
        elif ln.startswith('【主线】'):
            out['mainline'] = ln[len('【主线】'):].strip()
        elif ln.startswith('【风险】'):
            out['risk'] = ln[len('【风险】'):].strip()
        elif '|' in ln and ln[0] != '【':
            head = ln.split('|')[0].strip()
            nm = head.split('（')[0].strip() if '（' in head else head
            if nm in names_set:
                parts = [p.strip() for p in ln.split('|')]
                if len(parts) >= 5:
                    out['per'][nm] = {'logic': '', 'why': parts[1], 'op': parts[2], 'buy': parts[3], 'stop': parts[4]}
    return out


def build_intraday():
    """盘中异动监控（用户六步规格）：涨停池指纹门→情绪定性→新进涨停七段→主线→高位预警→持仓联动→纪律。
    大白话优先 DeepSeek 动态生成（每轮最多1次，计入当日≤8预算）；不可用/用尽自动回退规则模板并注明额度。
    仅北京盘中 09:30-14:59 生效；指纹未变不推送；lu 异常清零发数据说明不推个股；接口失败如实报故障。"""
    now = _bj_now()
    hm = now.hour * 60 + now.minute
    if not (9 * 60 + 30 <= hm <= 14 * 60 + 59):
        print('[intra] 非盘中时段，跳过')
        return ''
    d = get_pools()
    if not d['pool_ok']['zt']:
        print('[intra] 涨停池接口失败，报故障不推')
        push(_wrap('<div style="color:#e2e8f0;font-size:13px;">🔧 盘中异动监控：涨停池接口异常，本次无法获取涨停名单，先如实报故障（不编造）。' +
                   '<br>👉 大白话：数据源没给到数据，宁可空着也不瞎说。</div>', '🔧', '盘中异动'),
             f'🔧 盘中异动 {now.strftime("%H:%M")} · 数据源故障')
        return 'fault'
    fp = _intra_fingerprint(d)
    st = _intra_state()
    if st and st.get('fp') == fp:
        print(f"[intra] 指纹未变（lu={d['lu']} zb={d['zb']} 涨停代码数={len(st.get('codes', []))}），不推送")
        return ''
    prev_lu = st.get('lu', 0)
    prev_dt = st.get('dt', 0)
    prev_codes = set(st.get('codes') or [])
    all_codes = sorted(x.get('c', '') for sec in d['sectors'].values() for x in sec)
    _save_intra_state({'ts': now.isoformat(), 'fp': fp, 'lu': d['lu'], 'zb': d['zb'], 'dt': d['dt'],
                       'codes': all_codes})
    # —— 兜底：涨停池异常清零（上次>0 本次=0）→ 数据故障，发说明不推个股 ——
    if d['lu'] == 0 and prev_lu > 0:
        print(f"[intra] 涨停池异常清零 {prev_lu}→0，判定数据故障，发说明不推个股")
        push(_wrap(f'<div style="color:#e2e8f0;font-size:13px;">🔧 盘中异动监控：涨停池数据异常（{prev_lu}→0），判定为数据故障，' +
                   '本次不推荐任何个股。' + '<br>👉 大白话：数据突然清零多半是接口抽风，不是市场真没涨停，先别看。</div>',
                   '🔧', '盘中异动'), f'🔧 盘中异动 {now.strftime("%H:%M")} · 数据异常')
        return 'fault'
    # —— 涨停池全部个股（含行业/连板/首封/封单）——
    pool = []
    for sec, lst in d['sectors'].items():
        for x in lst:
            pool.append(x)
    code2x = {x.get('c', ''): x for x in pool}
    # 情绪定性：涨停变化 + 炸板率 + 跌停
    dl = d['lu'] - prev_lu
    zb_rate = d['zb'] / (d['lu'] + d['zb']) if (d['lu'] + d['zb']) else 0.0
    dt_new = (d['dt'] > 0 and prev_dt == 0)
    if dl >= 3:
        mood, mood_emoji = '升温', '🔥'
    elif dl <= -3:
        mood, mood_emoji = '降温', '🌡️'
    elif zb_rate >= 0.40:
        mood, mood_emoji = '热而毛糙', '🌪️'
    elif zb_rate < 0.20:
        mood, mood_emoji = '平稳偏强', '➡️'
    else:
        mood, mood_emoji = '平稳偏燥', '🔄'
    if dt_new:
        mood = '警惕退潮'
    # —— 新进涨停（增量差集，最多 5 只）——
    new_xs = [x for x in pool if x.get('c', '') not in prev_codes]
    sec_cnt = {}
    for x in pool:
        sec_cnt[x.get('hybk') or '其他'] = sec_cnt.get(x.get('hybk') or '其他', 0) + 1
    def _new_key(x):
        sc = sec_cnt.get(x.get('hybk') or '其他', 0)
        fbt = str(x.get('fbt') or '')
        early = 5 if fbt and fbt <= '0945' else 0
        return (sc, int(x.get('lbc') or 0), early, float(x.get('fund') or 0))
    new_xs.sort(key=_new_key, reverse=True)
    top_new = new_xs[:5]
    rest_n = len(new_xs) - len(top_new)
    # —— 每只算 MA5 / pos60（喂 DS 与模板共用）——
    ma5_map, pos_map = {}, {}
    for x in top_new:
        c, p = x.get('c', ''), _zt_price(x)
        if c and p:
            ma5_map[c] = _intra_ma5_price(c, p)
            pos_map[c] = _intra_pos60(c, p)
    # —— DeepSeek 动态大白话（一次调用，计入预算）——
    ds = _intra_ds(now, prev_lu, d, top_new, ma5_map, pos_map, sec_cnt)
    if ds is not None:
        print('[intra] DS 大白话已生成（个股覆盖', sum(1 for x in top_new if x.get('n', '') in ds['per']), '/', len(top_new), '）')
    else:
        print('[intra] DS 不可用/失败，不回退规则模板，只出数据事实', '（额度用尽）' if _DS_EXHAUSTED else '')
    mood_line = (f'<div style="color:#e9ecef;font-size:13px;">{mood_emoji} 情绪定性：{mood}'
                 f'（涨停 {prev_lu}→{d["lu"]}，炸板率 {zb_rate*100:.0f}%'
                 f'{f"，跌停 {d['dt']} 只（新增）" if dt_new else ""}）</div>')
    if ds and ds.get('overall'):
        mood_line += f'<div style="color:{GREY};font-size:12px;">👉 AI 大白话：{ds["overall"]}</div>'
    else:
        mood_line += ''
    rows = []
    for x in top_new:
        code = x.get('c', '')
        name = x.get('n', '')
        sec = x.get('hybk') or '其他'
        lbc = int(x.get('lbc') or 0)
        fbt = str(x.get('fbt') or '')
        price = _zt_price(x)
        lb_txt = f'{lbc}板' if lbc >= 2 else '首板'
        fbt_txt = f'｜首封 {fbt[:2]}:{fbt[2:]}' if fbt else ''
        grp = sec_cnt.get(sec, 0)
        pos60 = pos_map.get(code)
        ma5, near5 = ma5_map.get(code, (None, False))
        dsp = ds.get('per', {}).get(name) if ds else None
        if not dsp and ds:
            _kk = name[:4]
            for _k, _v in (ds.get('per') or {}).items():
                if _k[:4] == _kk or _kk in _k:
                    dsp = _v
                    break
        _logic = (dsp.get('logic') or '') if isinstance(dsp, dict) else ''
        if dsp:
            why, op, buy, stop = (dsp.get('why') or ''), (dsp.get('op') or ''), (dsp.get('buy') or ''), (dsp.get('stop') or '')
            if not (why or op or buy or stop):
                dsp = None
            op_col = TEAL if op in ('轻仓', '轻仓试', '看') else (GOLD if op in ('观望', '持仓不动') else RED)
        else:
            # 无模型判读：不出规则版结论句、不给规则版买点止损，只列已算出的数据
            why = ''
        # 无模型时不给规则版操作/买点/止损
        _oprow = ''
        if dsp:
            _oprow = ('<div style="color:#ced4da;font-size:12px;">操作：<b style="color:' + op_col + ';">' + op
                      + '</b> ｜ 买点：' + buy + ' ｜ 止损：' + stop + '</div>')
        if dsp:
            _whyrow = '<div style="color:' + GREY + ';font-size:12px;">👉 AI 大白话：' + why + '。</div>'
        else:
            _whyrow = ('<div style="color:#9aa4b8;font-size:12px;">'
                       + sec + '板块共 ' + str(grp) + ' 只齐涨｜' + lb_txt + fbt_txt
                       + (f'｜距60日高 {pos60*100:.0f}%' if pos60 is not None else '')
                       + (f'｜5日线 {ma5:.2f}' if ma5 else '')
                       + '</div>')
        rows.append(
            '<div style="background:#1f2635;border-left:3px solid ' + op_col + ';border-radius:8px;padding:8px 10px;margin:6px 0;">'
            + '<div style="font-size:13px;font-weight:700;color:#fff;">' + name + '（' + code + '）｜' + (dsp.get('theme') if isinstance(dsp, dict) and dsp.get('theme') else sec) + '｜<span style="color:' + RED + ';">' + lb_txt + '</span>' + fbt_txt + '</div>'
            + (('<div style="color:' + TEAL + ';font-size:12px;margin-top:2px;">🧠 个股逻辑：' + _logic + '</div>') if _logic else '')
            + (('<div style="color:#94d4d0;font-size:12px;margin-top:2px;">⚡ 涨停驱动：' + dsp.get('driver', '') + '</div>') if isinstance(dsp, dict) and dsp.get('driver') else '')
            + _whyrow
            + _oprow
            + '</div></div>')
    new_block = ('<div style="margin-top:8px;font-size:14px;font-weight:800;color:#ff922b;">🆕 新进涨停 ' + str(len(new_xs)) + ' 只（增量，只讲新的）</div>'
                 + ''.join(rows)
                 + (('<div style="color:#94d4d0;font-size:12px;margin-top:4px;line-height:1.6;">🔄 传染方向：' + str(ds.get('contagion')) + '</div>') if ds and ds.get('contagion') else '')
                 + ('<div style="color:' + GREY + ';font-size:12px;margin-top:4px;">另有 ' + str(rest_n) + ' 只首封（' + '、'.join(x.get('n', '') for x in new_xs[5:8]) + ' 等），不逐一展开。</div>' if rest_n else ''))
    # —— 主线归纳（DS 优先，模板回退）——
    from collections import Counter as _C
    cnt_new = _C(x.get('hybk') or '其他' for x in new_xs)
    top_main = cnt_new.most_common(2)
    if ds and ds.get('mainline'):
        main_line = ('<div style="margin-top:8px;font-size:14px;font-weight:800;color:#ff922b;">🧵 今日主线</div>'
                     f'<div style="color:#e9ecef;font-size:13px;">{ds["mainline"]}</div>') if new_xs else ''
    else:
        # 无模型判读：只列聚类数据，不写"真·板块合力/谨防一日游"这类规则结论
        _mp = []
        for sec, n in top_main:
            tot = sec_cnt.get(sec, 0)
            _mp.append(f'{sec}（新进 {n} 只，板块共 {tot} 只）')
        main_line = ('<div style="margin-top:8px;font-size:14px;font-weight:800;color:#ff922b;">🧵 今日主线</div>'
                     f'<div style="color:#e9ecef;font-size:13px;">新进票集中在 {"；".join(_mp) if _mp else "没形成合力"}。'
                     f'同一个板块里进榜的越多，说明资金是顺着一条线打的，不是各打各的</div>') if new_xs else ''
    # —— 高位预警（连板≥4 或 60日高位区的新高票）——
    hi = [x for x in pool if int(x.get('lbc') or 0) >= 4]
    hi_txt = []
    for x in hi[:3]:
        lbc = int(x.get('lbc') or 0)
        hi_txt.append(f'{x.get("n", "")}（{lbc}板）')
    pos_hi = []
    for x in pool[:12]:
        c, nm = x.get('c', ''), x.get('n', '')
        p = _zt_price(x)
        if p and c:
            pos = _intra_pos60(c, p)
            if pos is not None and pos > 0.85 and int(x.get('lbc') or 0) < 4:
                pos_hi.append(nm)
        if len(pos_hi) >= 3:
            break
    hi_line = ('<div style="margin-top:8px;font-size:14px;font-weight:800;color:#ff922b;">⚠️ 高位预警</div>'
               f'<div style="color:{RED};font-size:13px;">{"、".join(hi_txt + pos_hi)}已经连到高位或贴到60日高点，位置太靠上，这时候进去就是给别人接力</div>') if (hi_txt or pos_hi) else ''
    # —— 持仓联动（冰轮/道恩）——
    hold_hits = []
    for h in HOLDINGS:
        c6 = h['code'].replace('sh', '').replace('sz', '')
        if c6 in code2x:
            x = code2x[c6]
            hold_hits.append(f'{h["name"]} 涨停（{int(x.get("lbc") or 0)}板）！')
        elif h['name'] in d.get('zb_names', set()):
            hold_hits.append(f'{h["name"]} 炸板（注意回落）')
    hold_line = ('<div style="margin-top:8px;padding:8px 10px;background:#3b1d1d;border-left:4px solid #ff922b;border-radius:8px;">'
                 f'<div style="font-size:13px;font-weight:800;color:#ffd43b;">🐉 持仓有动静：{"；".join(hold_hits)}</div></div>') if hold_hits else ''
    # —— 纪律句 + DS 风险 + 额度注 ——
    if ds and ds.get('risk'):
        risk_line = f'<div style="margin-top:8px;color:{RED};font-size:12px;">⚠️ AI 风险：{ds["risk"]}</div>'
    else:
        risk_line = ''
    if mood in ('升温', '平稳偏强'):
        disc = '只看龙头、不碰高位、不追炸板'
    elif mood in ('降温', '警惕退潮'):
        disc = '退潮期别接飞刀，先保住今天的利润'
    else:
        disc = '管住手，等同步启动确认再动'
    quota_line = ('<div style="margin-top:6px;color:' + GREY + ';font-size:11px;">今日 DS 额度已用，以下为纯规则判断</div>'
                  if _DS_EXHAUSTED else '')
    html = _wrap(
        f'<div style="color:{RED};font-size:14px;font-weight:700;">⏰ {now.strftime("%H:%M")} 盘中异动 · 涨停 {d["lu"]} / 炸板 {d["zb"]}</div>'
        + mood_line + new_block + main_line + hi_line + hold_line + risk_line
        + f'<div style="margin-top:8px;color:{TEAL};font-size:12px;">📌 纪律：{disc}</div>'
        + quota_line
        + '<div style="margin-top:4px;color:' + GREY + ';font-size:11px;">不构成投资建议</div>',
        '🚨', '盘中异动')
    ok, msg = push(html, f'🚨 盘中异动 {now.strftime("%H:%M")} · {mood}')
    print(f'[intra] 指纹变化 lu={prev_lu}→{d["lu"]} zb={d["zb"]} 新进 {len(new_xs)} 只 → PUSH', ok, msg)
    return html


# ============ 板块启动预警（warn）============
_WARN_DS_SYS = ('''你是一位有10年以上A股实盘和量化经验的一线游资，专门做板块轮动和主线捕捉。你的核心能力是用真实盘面数据，在板块真正启动前，识别「资金领先、龙头先行、有建仓痕迹、结构改善」的早期信号，然后用最接地气的大白话告诉用户该怎么做。
你必须全程用大模型自己的深度思考来完成判断，禁止机械套用固定模板。
一、你真正要做的事
每天开盘后或盘中，先想清楚三个问题，并用当天真实数据回答：
谁在动：真正有资金在动手的是哪个板块，是主线还是支线，是龙头在动还是跟风在动，有没有建仓痕迹。
为什么动：是因为资金提前进场，还是因为消息刺激，还是因为情绪扩散。
动到哪一步了：是刚启动、中段加速、末段高潮，还是已经开始退潮。
这三个问题想不清楚，就直接输出「今日暂无明确启动预警」，绝不硬写。
二、早期信号的评分因子（用自己的交易经验权衡）
资金层（最重要）、龙头层（是否有建仓痕迹、位置是否还低）、结构层、情绪与位置层。
三、阶段判断硬标准（启动/中段加速/末段高潮/退潮）
四、输出时必须遵守的认知结构：结论先行 → 因果链显影 → 决策接口（触发条件+动作+失败出口）
五、绝对禁止的行为：没有数据支撑就编信号；用无法验证的空话；输出「满仓」「必涨」；同一句话换票名复用。
六、最终输出原则
信号不够强 → 直接回复「今日暂无明确启动预警」
有信号 → 用最接地气的大白话，把结论、原因、操作三件套说清楚
输出前先自问：如果不推这只票/这个板块，最硬的理由是什么？理由成立就写「今日暂无明确启动预警」
全程像一个老游资在跟朋友聊天。
现在开始，用你的交易经验深度思考今天的盘面，给出判断。
''')



_WARN_DS_FMT = ('当前时间：{time} 市场阶段：{market_phase}\n'
                '【资金数据】\n{money_flow_data}\n'
                '【龙头与结构】\n{leader_move}\n'
                '【量价】\n{volume_price}\n'
                '【外部映射】\n{external}\n'
                '【热度】\n{sentiment}\n'
                '请完成以下任务：\n'
                '1. 计算启动评分（0-100），并给出主要得分项。\n'
                '2. 判断是否达到「启动预警」标准（建议阈值60分）。\n'
                '3. 如果达到，按下面格式输出；如果没达到，只回复「今日暂无明确启动预警」。\n'
                '输出格式（严格遵守）：\n'
                '【启动预警】{板块名称}（评分：XX）\n'
                '【大白话总结】一句话说明为什么现在值得盯。\n'
                '【核心信号】\n- 信号1：...\n- 信号2：...\n- 信号3：...\n'
                '【龙头观察】目前最强的1-2只票及原因。\n'
                '【操作建议】观察 / 轻仓试错（具体怎么做）\n'
                '【风险提示】最可能失败的点。\n'
                '【最终结论】继续观察 / 可以开始关注 / 信号较强可小仓试错')


def _warn_score(d, fin, fout):
    """规则层板块启动评分（0-100，全真实数据，无数据不计分）。
    资金≤25 + 龙头≤30 + 量价≤20 + 外部≤15 + 热度≤10。返回 (总分, 板块名, 数据字典)。"""
    if not d.get('tops'):
        return 0, None, {}
    sec, stocks = d['tops'][0]
    zt_n = len(stocks)
    # 资金（个股净流入前5聚合为全局资金判断；接口失败 fin=None 只给中性分）
    net = 0.0
    if fin and fout:
        net = sum(v for _, v in fin) + sum(v for _, v in fout)
    sc_money = 25 if net > 3e9 else 20 if net > 1e9 else 12 if net > 0 else 5
    # 龙头（板块涨停家数 + 是否出≥2板连板）
    sc_leader = min(30, zt_n * 6)
    lb = 0
    for n, _names in d.get('ladder', []):
        if n >= 2:
            lb = max(lb, n)
    if lb >= 2:
        sc_leader = min(30, sc_leader + 10)
    # 量价（涨停家数≥3 视为量能配合；缩量后放量/量价背离暂无历史对比数据，如实不计）
    sc_vol = 15 if zt_n >= 3 else 8
    # 外部映射（仅备注，不虚构得分）
    sc_ext = 0
    # 热度
    sc_heat = 10 if zt_n >= 5 else 6 if zt_n >= 3 else 0
    total = min(100, sc_money + sc_leader + sc_vol + sc_ext + sc_heat)
    return total, sec, {'sec': sec, 'zt_n': zt_n, 'lb': lb,
                        'sc_money': sc_money, 'sc_leader': sc_leader, 'sc_vol': sc_vol,
                        'sc_ext': sc_ext, 'sc_heat': sc_heat}


def _warn_ds(data):
    """启动预警 DeepSeek：传数据字典 + 独立系统提示词（板块轮动交易员）。失败返回 ''。"""
    if not DEEPSEEK_KEY:
        return ''
    payload = {'task': 'sector_startup_warning',
               'data': {'time': data['time'], 'market_phase': data['market_phase'],
                        'money_flow_data': data['money_flow_data'],
                        'leader_move': data['leader_move'], 'volume_price': data['volume_price'],
                        'external': data['external'], 'sentiment': data['sentiment']},
               'format': _WARN_DS_FMT}
    t = ask_deepseek(payload, purpose='warn', system_text=_WARN_DS_SYS)
    return md2html(t) if t else ''


def _warn_news_ds(items, zt_names=None):
    """08:20 消息面点火预判 LLM：新闻→可能被点燃的板块→个股→点火逻辑→实时数据→开盘验证→失败规则→风险。失败返回 ''。"""
    if not items or not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return ''
    # hold：持仓名（data/holdings.json 可选），供 LLM 判断「点火板块与持仓的关系」；无持仓写暂无
    _hs = _load_holdings()
    hold = '、'.join(str(h.get('name') or '') for h in _hs) if _hs else '暂无持仓'
    news_txt = '\n'.join(f"- {x['title']}（摘要：{x['summary'][:60]}）" for x in items[:15])
    _zt = sorted(str(x) for x in (zt_names or set()))[:40]
    zt_line = ('昨日已涨停/连板（禁止选为可操作候选，只可作风险提示）：' + '、'.join(_zt) + '\n') if _zt else ''
    fmt = ('你是一线游资，现在是开盘前08:20，手里只有隔夜和当天的新闻，没有盘中数据。\n'
           '任务：判断哪些板块今天可能被消息面点火启动。严格按主力游资五步铁律：\n'
           + FIVE_BRIEF + '\n'
           + zt_line
           + '先判断主力最可能选哪类票（低位有建仓痕迹的）作为点火点。\n'
           + '【深挖铁律·落到个股必做】fire 里每个方向必须举2-3只例子（stocks 字段），必须完整执行「股票深挖铁律」：本质（一句话大白话）+暗线业务（具体产品+阶段+真实贡献，写不出写「未见明确暗线业务」）+真实关联与弹性（实受益/沾边/纯蹭）+破灭点。禁止把昨日涨停/连板票列为 stocks 候选（涨停票只能写进 risk 提示）。没有明确标的写「该方向暂无明确点火标的」，禁止硬编。总输出≤380字。\n新闻列表：\n' + news_txt + '\n'
           + '只输出 JSON：{"fire":[{"sector":"可能被点燃的板块(≥8字)","stocks":"真实关联候选个股2-3只(必须用新闻和板块逻辑推出具体股票名，优先低位未涨停；禁止一律写无；完全推不出才写无，并写明推不出的原因)","logic":"点火逻辑(≥35字)：板块逻辑(为什么这个板块会动)+题材逻辑(消息对应哪个题材)+主力可能选什么类型的票","data":"实时数据参考：当前竞价/早盘量能、板块涨跌幅、相关个股表现；开盘前无盘中数据则明确写「开盘前暂无盘中数据，待09:25竞价验证量能/高开/板块联动」(禁止硬编数据)","verify":"开盘验证条件：竞价量比/高开幅度/板块多股联动等具体信号(≥15字，禁止空话)","fail_if":"失败则放弃的条件：出现什么信号即证伪(≥12字)","risk":"最大风险：位置/情绪/消息证伪/外围(≥12字)"}]}\n'
           + 'fire 最多3个（只留最有把握的1-3个，宁缺毋滥）。推不出就写"今日消息面无明确点火板块"，不许硬凑。\n'
           + 'JSON 另加 "news_brief":[{"t":"新闻原标题","core":"消息核心内容完整版(≤80字，禁止只写一句话标题)","sec":"板块逻辑：利好/利空哪个板块(≥6字)","theme":"题材逻辑：对应哪个题材(≥6字)","dark":"个股暗线：直接点名可能受益的1-2只具体股(主业真实关联+弹性；无则写「暂无明确个股暗线」)","p":"大白话原因(≤45字)：说清这条消息可能点燃/压制哪个方向、主力会不会借题发挥","act":"操作建议：这条消息带来的具体操作（买/躲/看+条件，≥10字，禁止万能句）","data":"实时数据参考：竞价/量能/板块涨跌/个股表现；开盘前无盘中数据则写「开盘前暂无盘中数据，待竞价验证」"}]，只对会改变交易决策的新闻给 news_brief（最多8条），纯凑数/无交易价值的新闻直接跳过不写。')
    t = ask_deepseek({'task': 'warn_news_ds', 'news': items[:15], 'format': fmt}, purpose='warn_news_ds')
    return t if t else ''


def _warn_render_fire(_j, items=None):
    """渲染点火预判 JSON；items 为新闻列表时先出「今日新闻速览」。"""
    out = []
    # 新闻速览：优先 LLM 大白话研判（news_brief），LLM 没给时降级只显示标题（不拼摘要，防重复两遍）
    _nb = (_j.get('news_brief') or []) if isinstance(_j, dict) else []
    _news_brief = []
    if _nb:
        for _n in _nb[:8]:
            _t = str(_n.get('t') or '').strip()
            _c = str(_n.get('core') or '').strip()
            _sec = str(_n.get('sec') or '').strip()
            _theme = str(_n.get('theme') or '').strip()
            _dark = str(_n.get('dark') or '').strip()
            _p = str(_n.get('p') or '').strip()
            _data = str(_n.get('data') or '').strip()
            if _t:
                _line = f'<div style="color:#e9ecef;font-size:12px;margin:5px 0 0;line-height:1.5;">• {_t[:44]}</div>'
                if _c:
                    _line += f'<div style="color:#c8d0e0;font-size:12px;margin:1px 0 0 10px;line-height:1.5;">📄 {_c[:80]}</div>'
                if _sec:
                    _line += f'<div style="color:#94d4d0;font-size:12px;margin:1px 0 0 10px;line-height:1.5;">🧭 板块逻辑：{_sec}</div>'
                if _theme:
                    _line += f'<div style="color:#94d4d0;font-size:12px;margin:1px 0 0 10px;line-height:1.5;">🎯 题材逻辑：{_theme}</div>'
                if _dark:
                    _line += f'<div style="color:#a78bfa;font-size:12px;margin:1px 0 0 10px;line-height:1.5;">🕳️ 个股暗线：{_dark[:70]}</div>'
                if _p:
                    _line += f'<div style="color:#a78bfa;font-size:12px;margin:1px 0 0 10px;line-height:1.5;">💬 大白话：{_p[:50]}</div>'
                if str(_n.get('act') or '').strip():
                    _line += f'<div style="color:{RED};font-size:12px;margin:1px 0 0 10px;line-height:1.5;">💡 操作：{str(_n.get("act")).strip()[:60]}</div>'
                if _data:
                    _line += f'<div style="color:#6c7a89;font-size:11px;margin:1px 0 4px 10px;line-height:1.5;">📊 实时数据：{_data[:60]}</div>'
                _news_brief.append(_line)
    else:
        for _n in (items or [])[:15]:
            _t = str(_n.get('title') or '').strip()
            if _t:
                _news_brief.append(f'<div style="color:#e9ecef;font-size:12px;margin:3px 0;line-height:1.5;">• {_t[:44]}</div>')
    if _news_brief:
        out.append('<div style="font-size:14px;font-weight:800;color:#ffd43b;margin-top:4px;">📰 今日新闻速览（' + str(len(_news_brief)) + '条 · 大白话研判，开盘前全貌）</div>')
        out.append('<div style="background:#161e2b;border-radius:8px;padding:8px 10px;margin:4px 0;">' + ''.join(_news_brief) + '</div>')
    fire = _j.get('fire') or []
    if fire:
        out.append('<div style="font-size:15px;font-weight:800;color:#ff922b;">🔥 今日可能被消息点燃的板块（开盘前预判，等竞价验证）</div>')
        for i, f_ in enumerate(fire[:3], 1):
            _conf = f_.get('confidence', '')
            _conf_txt = ('★' * int(_conf)) if str(_conf).isdigit() else ''
            _stk = str(f_.get('stocks') or '').strip()
            if not _stk or _stk in ('无', '暂无', '无。'):
                _stk = '待竞价验证候选'
            _data = str(f_.get('data') or '').strip()
            if not _data or _data in ('无', '暂无'):
                _data = '开盘前暂无盘中数据，待09:25竞价验证量能/高开/板块联动'
            _vfy = str(f_.get('verify') or '').strip() or '待竞价验证：板块竞价量比放大+多股联动再确认'
            _fail = str(f_.get('fail_if') or '').strip() or '竞价量能不足/冲高回落即放弃'
            _risk = str(f_.get('risk') or '').strip() or '以竞价验证为准，逻辑未兑现不介入'
            out.append(f"""<div style="background:#1c2830;border-left:3px solid {RED};border-radius:8px;padding:9px 11px;margin:6px 0;">
<div style="font-size:13px;font-weight:700;color:#fff;">{i}. {f_.get('sector','')} <span style="color:{GREY};font-weight:400;">｜相关个股：{_stk}</span> <span style="color:{GOLD};">{_conf_txt}</span></div>
<div style="color:#a78bfa;font-size:12px;margin-top:2px;">🧠 点火逻辑：{f_.get('logic','')}</div>
<div style="color:#6c7a89;font-size:12px;margin-top:2px;">📊 实时数据：{_data}</div>
<div style="color:{TEAL};font-size:12px;margin-top:2px;">🔍 开盘验证：{_vfy}</div>
<div style="color:{GREEN};font-size:12px;margin-top:2px;">⛔ 失败则：{_fail}</div>
<div style="color:{GREEN};font-size:12px;margin-top:2px;">⚠️ 风险：{_risk}</div></div>""")
    avoid = _j.get('avoid') or []
    if avoid:
        out.append('<div style="font-size:14px;font-weight:800;color:' + GREEN + ';margin-top:6px;">🚫 消息面要避开的</div>')
        for a_ in avoid[:3]:
            out.append(f"""<div style="font-size:12px;color:#c8d0e0;margin:3px 0;">• {a_.get('sector','')}：{a_.get('logic','')}</div>""")
    if _j.get('hold'):
        out.append('<div style="font-size:13px;color:' + GOLD + ';margin-top:8px;">📌 持仓联动：' + str(_j['hold']) + '</div>')
    return ''.join(out)


def _zt_pool_names():
    """昨日涨停池股票名+代码集合（供 warn stocks / 盘前 focus / 操作清单 过滤：禁止把昨日涨停/连板票列为可操作）。
    失败返回空 set（调用方不因排除集缺失而阻塞）。"""
    try:
        td = _last_trade_date()
        if not td:
            return set()
        pool = _follow_pool(td.replace('-', ''))
        out = set()
        for x in pool:
            nm = str(x.get('name') or '').strip()
            cd = str(x.get('code') or '').strip()
            if nm:
                out.add(nm)
            if cd:
                out.add(cd)
        return out
    except Exception as e:
        print('[ztpool] 涨停排除集异常:', e)
        return set()


# ============ 雷达扫描（11-05 指令⑪）：倍量 + 实体阳线 + 5日线金叉20日线 ============
RADAR_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'radar_done.json')


def _radar_kctx(code, price):
    """个股K线核验（雷达三条件）：返回 dict 或 None。
    条件①成交量倍量（今日量 ≥ 前5日均量×2，量比口径）；②实体阳线（收>开、涨幅1.5~9.5%）；
    ③五日均线上穿二十日均线（含今日 MA5>MA20 且昨日 MA5≤MA20，允许近2日刚金叉）。"""
    try:
        sym = ('sh' if code.startswith('6') else 'sz') + code
        arr = get_klines(sym, 70)
        if not arr or len(arr) < 26:
            return None
        today_s = _bj_now().strftime('%Y-%m-%d')
        if str(arr[-1][0]) != today_s:
            # 非交易时段跑（FORCE 回放）：用最新已收盘K线视为当日
            pass
        last = arr[-1]
        prev = arr[-2] if len(arr) >= 2 else None
        o, c, h, l, v = float(last[1]), float(last[2]), float(last[3]), float(last[4]), float(last[5])
        if o <= 0 or c <= 0 or v <= 0:
            return None
        pct = (c / o - 1) * 100
        v5 = sum(float(x[5]) for x in arr[-6:-1]) / 5.0
        vol_r = v / v5 if v5 > 0 else 0.0
        closes = [float(x[2]) for x in arr]
        ma5_now = sum(closes[-5:]) / 5.0
        ma20_now = sum(closes[-20:]) / 20.0
        ma5_prev = sum(closes[-6:-1]) / 5.0 if len(closes) >= 6 else 0.0
        ma20_prev = sum(closes[-21:-1]) / 20.0 if len(closes) >= 21 else 0.0
        golden = (ma5_now > ma20_now and ma5_prev <= ma20_prev) or \
                 (len(closes) >= 7 and ma5_now > ma20_now and
                  sum(closes[-6:-1]) / 5.0 <= sum(closes[-21:-1]) / 20.0)
        body_ok = c > o and 1.0 <= pct <= 9.5
        if vol_r < 2.0 or not body_ok or not golden:
            return None
        return {'price': round(c, 2), 'pct': round(pct, 2), 'vol_r': round(vol_r, 1),
                'ma5': round(ma5_now, 2), 'ma20': round(ma20_now, 2), 'golden': bool(golden)}
    except Exception:
        return None


def _radar_candidates(maxn=8):
    """雷达扫描选股：涨幅榜初筛（涨幅2~9.5%、量比≥1.8、换手≥2.5%、未涨停）→ K线核验三条件。"""
    try:
        rows = _clist_gainers()
    except Exception as e:
        print('[radar] 涨幅榜异常:', e)
        return []
    zt_codes = set()
    try:
        for _sec, sts in get_pools()['sectors'].items():
            for st in sts:
                zt_codes.add(str(st.get('c') or ''))
    except Exception:
        pass
    cands = []
    for s in rows:
        try:
            if float(s.get('pct') or 0) < 2.0 or float(s.get('pct') or 0) >= 9.5:
                continue
            if float(s.get('lb') or 0) < 1.8:
                continue
            if float(s.get('turn') or 0) < 2.5:
                continue
        except Exception:
            continue
        if str(s.get('code') or '') in zt_codes:
            continue
        cands.append(s)
        if len(cands) >= 25:
            break
    cands.sort(key=lambda x: -(float(x.get('lb') or 0)))
    out = []
    for s in cands[:15]:
        k = _radar_kctx(s.get('code') or '', float(s.get('price') or 0))
        if k is None:
            continue
        s['_k'] = k
        out.append(s)
        if len(out) >= maxn:
            break
    return out


def _radar_ds(stocks):
    """雷达扫描 LLM 深挖：每只筛出股挖异动归因/逻辑/暗线/买点止损。失败返回 {}。"""
    if not stocks or not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return {}
    stk_txt = '\n'.join(
        f"- {s.get('name')}({s.get('code')}) 现价{s.get('price')} 涨幅{s.get('pct')}% 量比{s.get('lb')} 换手{s.get('turn')}% "
        f"行业{s.get('industry') or '其他'} K线:量比{s['_k']['vol_r']} 实体阳线+{s['_k']['pct']}% "
        f"MA5={s['_k']['ma5']} MA20={s['_k']['ma20']} 金叉={s['_k']['golden']}" for s in stocks)
    fmt = ('你是一线游资，雷达扫描器今日筛出以下「倍量+实体阳线+五日均线上穿二十日均线」的异动股。'
           '对每只完整执行「股票深挖铁律」：①本质（一句话大白话，禁标签糊弄）②异动归因（今天为什么放量上涨：消息/资金/板块/业绩，用数据说话）'
           '③暗线业务（具体产品+阶段+对业绩真实贡献，挖不出写「未见明确暗线业务」，禁「相关/涉及/布局/受益于」糊弄）'
           '④真实关联与弹性（实受益/沾边/纯蹭+弹性大小）⑤破灭点（必写）⑥动作（买点具体价位/条件+止损位+仓位1-2成，逻辑不硬写「不碰」）。'
           '禁止推荐总市值千亿大票（30-800亿口径）；禁止「值得关注/建议留意」万能句；没有把握写「逻辑不硬，不碰」。'
           '只输出 JSON：{"per":[{"name":"股票名称","why":"异动归因(≥30字)","dark":"暗线(≥20字,挖不出如实写)","elastic":"关联弹性(实受益/沾边/纯蹭+大小)","op":"别追/轻仓试/观望","buy":"买点具体","stop":"止损具体","verdict":"值得试/观察/不碰"}]}\n'
           '股票列表：\n' + stk_txt)
    t = ask_deepseek({'task': 'radar_ds', 'stocks': [{'name': s.get('name'), 'code': s.get('code')} for s in stocks],
                      'format': fmt}, purpose='radar_ds')
    if not t:
        return {}
    try:
        _j = json.loads(t)
        out = {}
        for it in (_j.get('per') or []):
            nm = str(it.get('name') or '').strip()
            if nm:
                out[nm] = it
        return out
    except Exception:
        return {}


def build_radar():
    """雷达扫描（11-05 指令⑪）：倍量+实体阳线+5日线金叉20日线筛股 → LLM 挖异动归因/逻辑/暗线。
    仅北京盘中 09:30-14:50 实时推送（--force 演示跳过闸门）。无达标股 → 不推送（如实说明）。"""
    bj = _bj_now()
    if not FORCE_SLOT and not _in_session(bj):
        print(f'[radar] 当前北京时间 {bj.strftime("%H:%M")} 不在盘中窗口(09:30-14:50)，不推雷达扫描')
        return None
    stocks = _radar_candidates()
    if not stocks:
        print('[radar] 今日无达标（倍量+实体阳线+金叉）个股，不推送')
        return None
    ds = _radar_ds(stocks)
    rows = []
    for s in stocks:
        name, code = s.get('name', ''), s.get('code', '')
        _d = ds.get(name) or {}
        _why = str(_d.get('why') or '') or '数据达标（倍量+阳线+金叉），归因见下方'
        _dark = str(_d.get('dark') or '') or '未见明确暗线业务'
        _op = str(_d.get('op') or '看')
        _opc = TEAL if _op in ('轻仓试',) else (GOLD if _op in ('看', '观望') else RED)
        _buy = str(_d.get('buy') or '待盘中确认')
        _stop = str(_d.get('stop') or '-3%')
        _vd = str(_d.get('verdict') or '观察')
        # 多周期视角（雷达标的已备 _k 日K数据，直接复用）
        _cyc, _cyc_reason = _cycle_tag(code, '', 0)
        _cyc_html = (f'<div style="color:#8bd3c7;font-size:12px;margin-top:2px;">⏱ 周期视角：<b>{_cyc}</b> ｜ {_cyc_reason}</div>'
                     if _cyc else '')
        rows.append(f"""<div style="background:#1f2635;border-left:4px solid {_opc};border-radius:10px;padding:9px 12px;margin:6px 0;">
<div style="font-weight:700;color:#fff;">📡 {name}<span style="color:{GREY};font-size:12px;">（{code}）</span>
<span style="color:{_c(s.get('pct'))};">+{s.get('pct')}%</span>
<span style="color:{GREY};font-size:12px;">｜量比{s.get('lb')}·换手{s.get('turn')}%·量能{s['_k']['vol_r']}x</span>
<span style="color:{TEAL};font-size:12px;">｜5日{s['_k']['ma5']}上穿20日{s['_k']['ma20']}</span></div>
{_cyc_html}
<div style="color:#e9ecef;font-size:12px;margin-top:3px;line-height:1.6;">🧠 异动归因：{_why}</div>
<div style="color:#a78bfa;font-size:12px;margin-top:2px;">🕳️ 暗线：{_dark}</div>
<div style="color:#ced4da;font-size:12px;margin-top:2px;">🎯 结论：<b style="color:{_opc};">{_vd}（{_op}）</b>｜买点：{_buy}｜止损：{_stop}</div></div>""")
    if not rows:
        rows = ['<div style="color:' + GREY + ';font-size:13px;">今日无达标（倍量+实体阳线+金叉）个股，等下一轮</div>']
    inner = (f'<div style="color:{RED};font-size:14px;font-weight:700;">📡 {bj.strftime("%H:%M")} 雷达扫描 · 倍量+实体阳线+5日线上穿20日线</div>'
             + ''.join(rows)
             + f'<div style="color:{GREY};font-size:11px;margin-top:6px;">筛股口径：量比≥1.8 + 实体阳线涨幅1~9.5% + MA5上穿MA20（含今日）。LLM 深挖归因/暗线；高位不追，按买点纪律执行。</div>')
    return _wrap(inner, '📡', '雷达扫描')


def _radar_done(d):
    """雷达扫描当日去重：同交易日仅推一次（防 watch 每15分钟重复刷屏）。"""
    try:
        with open(RADAR_PATH, encoding='utf-8') as f:
            m = json.load(f)
    except Exception:
        m = {}
    return m.get(d) is True


def _mark_radar_done(d):
    try:
        with open(RADAR_PATH, 'w', encoding='utf-8') as f:
            json.dump({d: True}, f, ensure_ascii=False)
        _git_commit_push(RADAR_PATH, 'update radar done')
    except Exception:
        pass


# ============ 盘中风险体检（11-05 用户诉求：及时参与/躲避风险，10:35/13:35 每交易日两次）============
def build_risk():
    """盘中风险体检：盘口等级由规则引擎算（红/橙/黄 才推，绿色静默不打扰）；
    判读、风险链、动作、盯盘信号、大白话全部交大模型生成——模型未返回时只出数据事实行，
    绝不落回规则动作句。数据：东财涨停/炸板/跌停池 + 指数 + 昨日情绪账本对比。"""
    bj = _bj_now()
    if not FORCE_SLOT and not _in_session(bj):
        print(f'[risk] 当前北京时间 {bj.strftime("%H:%M")} 不在盘中窗口(09:30-14:50)，不推风险体检')
        return None
    try:
        d = get_pools()
    except Exception as e:
        print('[risk] 池数据异常:', e)
        return None
    try:
        idx = get_indices()
    except Exception:
        idx = None
    r = _risk_engine(d, idx)
    if not r:
        print('[risk] 引擎数据不可得，不推送')
        return None
    if r['level'] == '绿':
        print(f"[risk] 当前无风险（绿，{r['score']:.0f}分），不打扰推送")
        return None
    try:
        _mscore, _mlabel, _ = market_score(idx, d) if idx else (50, '—', '')
    except Exception:
        _mscore, _mlabel = 50, '—'
    col = {'红': RED, '橙': GOLD, '黄': GOLD}.get(r['level'], GREY)
    # —— 大模型判读（硬约束：模型不返回就不给动作句）——
    _verdict = _chain = _act = _watch = _plain = ''
    _rp = {
        'task': 'intraday_risk_read',
        'clock': bj.strftime('%H:%M'),
        'rule_level': r['level'],
        'rule_score': round(float(r['score']), 1),
        'lu': r['lu'], 'zb': r['zb'], 'zbr': round(float(r['zbr']), 1),
        'dt': r['dt'], 'max_lbc': r['max_lbc'],
        'mscore': int(_mscore), 'mlabel': _mlabel,
        'evid': [str(e) for e in (r.get('evid') or [])][:6],
        'format': (
            '你是A股盘中风控交易员。上面盘口数字是程序实算的事实，只许引用、不许改、不许编新数字。'
            '按这些事实写当前风险判读，只输出 JSON，不要任何其他文字：'
            '{"verdict":"一句话判读：现在盘面处在什么状态、危险具体在哪（必须引用数字），至少20字",'
            '"chain":"风险链：把这些盘口数字串成因果链，说清风险怎么一步步形成、现在走到第几步，至少60字",'
            '"act":"具体动作：现在该做什么——仓位降到几成、哪些票必须走、现金留多少、还能不能接新票，必须落到数字，至少30字",'
            '"watch":"接下来30分钟盯什么：具体到哪个数字或信号会升级、哪个会解除，至少25字",'
            '"plain":"一句大白话给散户：说人话不带术语，至少20字"}'
            '禁止万能句（注意风险/控制仓位/谨慎操作这类）、禁止设问句、禁止列表符号、禁止可能/或许/建议关注这类含糊词；'
            '判断要一口咬定，错也错得干脆。'),
    }
    _rt = ask_deepseek(_rp, purpose='risk_card')
    if _rt:
        try:
            _j = json.loads(_rt[_rt.find('{'):_rt.rfind('}') + 1])
            _verdict = str(_j.get('verdict') or '').strip()
            _chain = str(_j.get('chain') or '').strip()
            _act = str(_j.get('act') or '').strip()
            _watch = str(_j.get('watch') or '').strip()
            _plain = str(_j.get('plain') or '').strip()
        except Exception as e:
            print('[risk] LLM JSON 解析失败:', e)
    ev = '<br>'.join(f'<span style="color:#e9ecef;">• {e}</span>' for e in r['evid'])
    head = (f'<div style="color:{RED};font-size:14px;font-weight:700;">🛡️ {bj.strftime("%H:%M")} 盘中风险体检 · '
            f'风险等级：<b style="color:{col};">{r["level"]}</b>（{r["score"]:.0f}/100）</div>'
            f'<div style="color:#e2e8f0;font-size:13px;line-height:1.8;margin-top:6px;">'
            f'盘口实况：涨停{r["lu"]} 炸板{r["zb"]}（{r["zbr"]:.0f}%） 跌停{r["dt"]} 最高{r["max_lbc"]}板 ｜ '
            f'情绪分{int(_mscore)}（{_mlabel}）<br>{ev}</div>')
    if _act:
        body = (head
                + f'<div style="color:#e2e8f0;font-size:13px;line-height:1.8;margin-top:8px;">🧠 判读：{_verdict}</div>'
                + (f'<div style="color:#ced4da;font-size:12px;margin-top:4px;">🔗 风险链：{_chain}</div>' if _chain else '')
                + f'<div style="color:#ffd43b;font-size:13px;margin-top:6px;">👉 动作：{_act}</div>'
                + (f'<div style="color:#91a7ff;font-size:12px;margin-top:4px;">👀 盯：{_watch}</div>' if _watch else '')
                + (f'<div style="color:#a78bfa;font-size:12px;margin-top:4px;">💬 {_plain}</div>' if _plain else '')
                + f'<div style="color:{GREY};font-size:11px;margin-top:4px;">判读与动作由大模型生成；盘口数字由规则引擎实算，不编数。10:35/13:35 每交易日两次。</div>')
    else:
        body = head
    return _wrap(body, '🛡️', '盘中风险体检')


# ============ 新闻发酵（11-05 指令⑧）：盘中 10 条消息汇总一起推 ============
def build_newsfire():
    """盘中新闻发酵（仅北京盘中 09:30-14:50 实时推送）：取最新消息按「事件驱动量化评分」排序精选 5 条，
    LLM 逐条深挖「带来什么信息→影响哪个行业/题材/个股→操作建议」。LLM 失败降级规则 news_tags。"""
    bj = _bj_now()
    if not FORCE_SLOT and not _in_session(bj):
        print(f'[newsfire] 当前北京时间 {bj.strftime("%H:%M")} 不在盘中窗口(09:30-14:50)，不推新闻发酵')
        return None
    try:
        news = get_news(25)
    except Exception as e:
        print('[newsfire] 新闻源异常:', e)
        news = []
    items = []
    for nw in (news or []):
        t = (nw.get('title') or '').strip()
        s = (nw.get('summary') or '').strip()
        if t or s:
            items.append({'title': t[:80], 'summary': s[:90], 'ts': nw.get('ts') or ''})
    # 事件驱动量化评分排序（紧跟时事：重大/产业催化 > 时间新 > 一般消息），取前5
    _scored = []
    for _nw in items:
        _ev = _score_event(_nw, bj)
        if _ev is None:
            continue
        _scored.append((_nw, _ev))
    _scored.sort(key=lambda x: -x[1]['score'])
    items = [_nw for _nw, _ev in _scored[:5]]
    if not items:
        print('[newsfire] 无新闻，不推送')
        return None
    _t = _warn_news_ds(items, _zt_pool_names())
    _j = None
    try:
        _j = json.loads(_t) if _t else None
    except Exception:
        _j = None
    if not (_j or {}).get('news_brief'):
        # LLM 未返回：只列标题与事件强度（代码算出的事实），不给规则版"影响板块/大白话"
        rows = []
        for nw in items:
            _ev2 = _score_event(nw, bj)
            _lvl = (_ev2 or {}).get('level') or 'C'
            _tag = {'S': '重大', 'A': '催化', 'B': '公司', 'C': '一般'}.get(_lvl, '一般')
            _tcol = {'S': RED, 'A': GOLD, 'B': TEAL, 'C': GREY}.get(_lvl, GREY)
            rows.append(f"""<div style="background:#1f2635;border-left:3px solid {GOLD};border-radius:8px;padding:7px 11px;margin:5px 0;">
<div style="color:#fff;font-size:13px;">• {nw.get('title','')} <span style="color:{_tcol};font-size:11px;">⚡{_tag}</span></div>
<div style="color:{GREY};font-size:12px;margin-top:2px;">{nw.get('ts','')}</div></div>""")
        inner = (f'<div style="color:{RED};font-size:14px;font-weight:700;">📰 {bj.strftime("%H:%M")} 新闻发酵</div>'
                 + ''.join(rows))
    else:
        nb = [str(_n.get('t') or '') for _n in _j['news_brief'][:5]]
        _s = 0
        for nw in items:
            if nw.get('title') in nb:
                _s += 1
        inner = (f'<div style="color:{RED};font-size:14px;font-weight:700;">📰 {bj.strftime("%H:%M")} 新闻发酵</div>'
                 + _warn_render_fire({'fire': [], 'news_brief': _j['news_brief'][:5]}))
    return _wrap(inner, '📰', '新闻发酵')


def _warn_zt_items():
    """新闻源不可用时降级：拉最近交易日涨停池按板块聚合，构造与新闻同结构的 items。
    板块字段 hybk → _sec_clean 清洗；按涨停家数降序取前 15 个板块。"""
    try:
        td = _last_trade_date()
        if not td:
            return []
        # 东财涨停池 date 参数要求 YYYYMMDD（_last_trade_date 返回 YYYY-MM-DD，必须去横线）
        pool = _follow_pool(td.replace('-', ''))
        if not pool:
            print(f'[warn] 涨停池降级：{td} 无数据')
            return []
    except Exception as e:
        print('[warn] 涨停池降级拉取异常:', e)
        return []
    by_sec = {}
    for x in pool:
        sec = _sec_clean(x.get('hybk') or '') or '其他'
        nm = str(x.get('name') or x.get('code') or '')
        if nm:
            by_sec.setdefault(sec, []).append(nm)
    out = []
    for sec, names in sorted(by_sec.items(), key=lambda kv: -len(kv[1]))[:15]:
        if len(names) >= 1:
            out.append({'title': f'昨日板块「{sec}」涨停 {len(names)} 家（数据源：涨停池降级）',
                        'summary': '代表个股：' + '、'.join(names[:5])})
    return out


def build_warn():
    """板块启动预警（消息面版）08:20：开盘前没有盘中数据，原来用昨日涨停池/资金流评分预测「今日启动」逻辑不成立。
    改为：抓当日/隔夜新闻 → LLM 判断哪些板块可能被消息点燃（新闻→板块→个股传导）+ 开盘验证条件 + 风险。
    LLM 失败回退规则 news_tags 利好板块清单；新闻源异常/无有效新闻 → 不推送（不空推）。"""
    bj = _bj_now()
    try:
        news = get_news(20)
    except Exception as e:
        print('[warn] 新闻源异常:', e)
        news = []
    _diag_append('[build_warn] 进入；新闻条数=%d' % len(news))
    if not news:
        print('[warn] 新闻源无数据，尝试涨停池降级')
    items = []
    for nw in (news or []):
        t = (nw.get('title') or '').strip()
        s = (nw.get('summary') or '').strip()
        if t or s:
            items.append({'title': t[:80], 'summary': s[:90], 'ts': nw.get('ts') or ''})
    if len(items) >= 6:
        # 事件驱动量化评分排序：重大/产业催化优先（08:20 点火预判紧跟隔夜+今晨重大事件）
        _sc = []
        for _nw in items:
            _ev = _score_event(_nw, bj)
            if _ev is not None:
                _sc.append((_nw, _ev))
        _sc.sort(key=lambda x: -x[1]['score'])
        items = [x[0] for x in _sc][:15]
    else:
        items = items[:15]
    _warn_src = '新闻'
    if not items:
        print('[warn] 新闻为空，走涨停池降级')
        try:
            items = _warn_zt_items()
            _warn_src = '涨停池'
            _diag_append('[build_warn] 涨停池降级 items=%d' % len(items))
        except Exception as e:
            print('[warn] 涨停池降级异常:', e)
            items = []
    if not items:
        print('[warn] 无任何数据源，不推送')
        _warn_diag_wecom('云端数据源全失败 | ' + ('; '.join(_WARN_DIAG_LINES) if _WARN_DIAG_LINES else '新闻空') + ' | 涨停池降级空')
        return None
    _diag_append('[build_warn] LLM key: MODELSCOPE=%s DEEPSEEK=%s' % (bool(MODELSCOPE_KEY), bool(DEEPSEEK_KEY)))
    t = _warn_news_ds(items, _zt_pool_names())
    _diag_append('[build_warn] LLM 返回长度=%d' % len(t))
    if not t:
        print('[warn] LLM 未返回且已禁规则版兜底，不推启动预警')
        return None
    try:
        _j = json.loads(t)
    except Exception as e:
        print('[warn] LLM JSON 解析失败且已禁规则版兜底，不推启动预警:', e)
        return None
    if not (_j.get('fire') or _j.get('avoid')):
        print('[warn] LLM 判定今日消息面无明确点火板块，不推送（不硬凑）')
        _warn_diag_wecom('LLM判定今日消息面无明确点火板块，不硬凑；新闻%d条 来源:%s' % (len(items), _warn_src))
        return None
    inner = (f'<div style="color:{RED};font-size:14px;font-weight:700;">🚨 板块启动预警 · 开盘前（{bj.strftime("%H:%M")}）</div>'
             f'<div style="color:{GREY};font-size:12px;margin-top:3px;">基于{_warn_src} {len(items)} 条数据推演，最终以竞价/开盘验证为准</div>'
             + _warn_render_fire(_j, items)
             + '<div style="color:' + GREY + ';font-size:11px;margin-top:8px;">① 验证：板块竞价量比明显放大+多股联动才算真启动；② 纪律：高位连板不追，低吸为主。</div>')
    return _wrap(inner, '🚨', '启动预警'), '【消息面点火预判】' + bj.strftime('%H:%M')

TITLES = {'pre': '盘前速递', 'auction': '竞价观察', 'tail': '尾盘竞价筛选', 'noon': '午间作战', 'eod': '收盘复盘',
         'news': '事件简报', 'news2h': '两小时市场消息汇总',
          'hourly': '盘中解读', 'warn': '启动预警', 'confirm': '竞价确认', 'ext': '外盘窗口',
          'radar': '雷达扫描', 'newsfire': '新闻发酵', 'risk': '盘中风险体检',
          'cycle': '多周期视角研判'}


BUILDERS['warn'] = build_warn
BUILDERS['ext'] = build_ext
BUILDERS['tail'] = build_tail
BUILDERS['radar'] = build_radar
BUILDERS['newsfire'] = build_newsfire
BUILDERS['risk'] = build_risk



# ============ 模块12：多通道备份 + 静默时段 ============
def _push_channels():
    """data/push_channels.json 多通道备份（可选）：
    {'wecom': '企业微信机器人webhook', 'feishu': '飞书机器人webhook'}。PushPlus 始终为主。"""
    try:
        with open('data/push_channels.json', 'r', encoding='utf-8') as f:
            c = json.load(f)
        return c if isinstance(c, dict) else {}
    except Exception:
        return {}


def _in_silence(bj=None):
    """data/silence.json 静默时段（可选）：{'start':'21:30','end':'08:00'}，支持跨零点。
    关键档（盘前/竞价/午间/收盘/启动预警/外盘窗口）豁免，不受影响。"""
    bj = bj or _bj_now()
    try:
        with open('data/silence.json', 'r', encoding='utf-8') as f:
            s = json.load(f)
        start, end = str(s.get('start', '')), str(s.get('end', ''))
        if not start or not end:
            return False
        hm = bj.strftime('%H:%M')
        if start <= end:
            return start <= hm < end
        return hm >= start or hm < end
    except Exception:
        return False


KEY_TITLES = ('盘前', '竞价', '午间', '收盘', '启动预警', '外盘窗口')


# —— 推送卡主题（2026-11-02 多版可选）——
# A 曜石黑（纯净深黑，柔和可读）| B 蓝黑科技（深蓝黑+科技亮色）
# C 深邃暖黑（深底暖调，护眼） | D 极夜护眼（蓝紫深底低对比） | E 浅色（暖白参照）
PUSH_THEME = 'C'  # 用户选定：C 深邃暖黑（2026-11-02）
_THEMES = {
    'A': {
        '#161b26': '#0f1218', '#17212b': '#151a24', '#1f2635': '#1b212d', '#1c2230': '#1b212d',
        '#232a3a': '#1b212d', '#1c2830': '#1b212d', '#2a1f22': '#291a1c', '#3a1a1a': '#311b1d',
        '#33281a': '#2b2213',
        '#e9ecef': '#e8eaf0', '#e2e8f0': '#e8eaf0', '#ced4da': '#c3c9d4', '#cfd6e4': '#c3c9d4',
        '#adb5bd': '#8b93a3', 'color:#ffffff': 'color:#f2f4f8', 'color:#fff;': 'color:#f2f4f8;',
        '#444': '#333a46', '#3a3a3a': '#333a46',
        '#c2504a': '#e2706a', '#ff6b6b': '#e2706a', '#ff5c5c': '#e2706a', '#ff4d4f': '#e2706a',
        '#b1852e': '#d4a95c', '#ffd43b': '#d4a95c', '#ffd666': '#dcb26a', '#ffc53d': '#d4a95c',
        '#3e9863': '#5ec98f', '#51cf66': '#5ec98f', '#52c41a': '#5ec98f', '#4cd07d': '#5ec98f',
        '#2f8fa1': '#6cc7d8', '#66d9e8': '#6cc7d8', '#6b7280': '#8b93a3',
    },
    'B': {
        '#161b26': '#101828', '#17212b': '#16202f', '#1f2635': '#1a2637', '#1c2230': '#1a2637',
        '#232a3a': '#1a2637', '#1c2830': '#1a2637', '#2a1f22': '#2a1d22', '#3a1a1a': '#311e24',
        '#33281a': '#2b2218',
        '#e9ecef': '#dfe5ef', '#e2e8f0': '#dfe5ef', '#ced4da': '#bcc5d2', '#cfd6e4': '#bcc5d2',
        '#adb5bd': '#8490a3', 'color:#ffffff': 'color:#edf1f8', 'color:#fff;': 'color:#edf1f8;',
        '#444': '#2e3a4c', '#3a3a3a': '#2e3a4c',
        '#c2504a': '#ef7a6e', '#ff6b6b': '#ef7a6e', '#ff5c5c': '#ef7a6e', '#ff4d4f': '#ef7a6e',
        '#b1852e': '#e0b15e', '#ffd43b': '#e0b15e', '#ffd666': '#e8bd6c', '#ffc53d': '#e0b15e',
        '#3e9863': '#5fd09a', '#51cf66': '#5fd09a', '#52c41a': '#5fd09a', '#4cd07d': '#5fd09a',
        '#2f8fa1': '#5fc2d6', '#66d9e8': '#5fc2d6', '#6b7280': '#8490a3',
    },
    'C': {
        '#161b26': '#141210', '#17212b': '#1a1815', '#1f2635': '#211f1b', '#1c2230': '#211f1b',
        '#232a3a': '#211f1b', '#1c2830': '#211f1b', '#2a1f22': '#2a1d1a', '#3a1a1a': '#31201d',
        '#33281a': '#2b2116',
        '#e9ecef': '#eae6df', '#e2e8f0': '#eae6df', '#ced4da': '#c9c4bb', '#cfd6e4': '#c9c4bb',
        '#adb5bd': '#97918a', 'color:#ffffff': 'color:#f4f0ea', 'color:#fff;': 'color:#f4f0ea;',
        '#444': '#3a352f', '#3a3a3a': '#3a352f',
        '#c2504a': '#e2776e', '#ff6b6b': '#e2776e', '#ff5c5c': '#e2776e', '#ff4d4f': '#e2776e',
        '#b1852e': '#d8ad63', '#ffd43b': '#d8ad63', '#ffd666': '#e0b96f', '#ffc53d': '#d8ad63',
        '#3e9863': '#62bf8a', '#51cf66': '#62bf8a', '#52c41a': '#62bf8a', '#4cd07d': '#62bf8a',
        '#2f8fa1': '#63b8c8', '#66d9e8': '#63b8c8', '#6b7280': '#97918a',
    },
    'D': {
        '#161b26': '#131722', '#17212b': '#181d2a', '#1f2635': '#1d2330', '#1c2230': '#1d2330',
        '#232a3a': '#1d2330', '#1c2830': '#1d2330', '#2a1f22': '#2a1e24', '#3a1a1a': '#302028',
        '#33281a': '#2a2218',
        '#e9ecef': '#e2e4ea', '#e2e8f0': '#e2e4ea', '#ced4da': '#b9c0cc', '#cfd6e4': '#b9c0cc',
        '#adb5bd': '#828a99', 'color:#ffffff': 'color:#eef0f5', 'color:#fff;': 'color:#eef0f5;',
        '#444': '#313846', '#3a3a3a': '#313846',
        '#c2504a': '#dd7a72', '#ff6b6b': '#dd7a72', '#ff5c5c': '#dd7a72', '#ff4d4f': '#dd7a72',
        '#b1852e': '#cfa45a', '#ffd43b': '#cfa45a', '#ffd666': '#d8b066', '#ffc53d': '#cfa45a',
        '#3e9863': '#63c08a', '#51cf66': '#63c08a', '#52c41a': '#63c08a', '#4cd07d': '#63c08a',
        '#2f8fa1': '#6bbfcf', '#66d9e8': '#6bbfcf', '#6b7280': '#828a99',
    },
    'E': {  # 浅色参照（二版）
        '#161b26': '#f5f4ef', '#17212b': '#ffffff', '#1f2635': '#eceff4', '#1c2230': '#eceff4',
        '#232a3a': '#eceff4', '#1c2830': '#eceff4', '#2a1f22': '#fce9e7', '#3a1a1a': '#fbe3e1',
        '#33281a': '#fbf1e0',
        '#e9ecef': '#1f2329', '#e2e8f0': '#1f2329', '#ced4da': '#41464e', '#cfd6e4': '#41464e',
        '#adb5bd': '#5c636e', 'color:#ffffff': 'color:#1a1b1c', 'color:#fff;': 'color:#1a1b1c;',
        '#444': '#d8dce2', '#3a3a3a': '#d8dce2',
        '#c2504a': '#c2504a', '#ff6b6b': '#c2504a', '#ff5c5c': '#c2504a', '#ff4d4f': '#c2504a',
        '#b1852e': '#b1852e', '#ffd43b': '#b1852e', '#ffd666': '#c29a45', '#ffc53d': '#b1852e',
        '#3e9863': '#3e9863', '#51cf66': '#3e9863', '#52c41a': '#3e9863', '#4cd07d': '#3e9863',
        '#2f8fa1': '#2f8fa1', '#66d9e8': '#2f8fa1', '#6b7280': '#6b7280',
    },
}


def _style_upgrade(html, theme=None):
    """2026-11-02 视觉改版：正文字号升到 14-15px、行高拉大、卡片间距/内边距放宽。
    主题配色由 _THEMES 提供（A曜石黑/B蓝黑科技/C深邃暖黑/D极夜护眼/E浅色）。
    全部正则为字面子串替换（带边界防误伤），作用于所有推送卡，不改任何构建逻辑。"""
    theme = theme or PUSH_THEME
    html = re.sub(r'font-size:11px', 'font-size:13px', html)
    html = re.sub(r'font-size:12px', 'font-size:14px', html)
    html = re.sub(r'font-size:13px', 'font-size:15px', html)
    html = re.sub(r'font-size:14px', 'font-size:15px', html)
    html = re.sub(r'line-height:1\.6(?![0-9])', 'line-height:1.9', html)
    html = re.sub(r'line-height:1\.65(?![0-9])', 'line-height:1.9', html)
    html = re.sub(r'line-height:1\.7(?![0-9])', 'line-height:2.0', html)
    html = re.sub(r'line-height:1\.75(?![0-9])', 'line-height:2.0', html)
    html = re.sub(r'margin-top:2px', 'margin-top:5px', html)
    html = re.sub(r'margin-top:3px', 'margin-top:6px', html)
    html = re.sub(r'margin-top:4px', 'margin-top:7px', html)
    html = re.sub(r'margin:5px 0', 'margin:8px 0', html)
    html = re.sub(r'margin:6px 0', 'margin:9px 0', html)
    html = re.sub(r'margin:7px 0', 'margin:10px 0', html)
    html = re.sub(r'margin:8px 0', 'margin:11px 0', html)
    html = re.sub(r'margin:10px 0', 'margin:13px 0', html)
    html = re.sub(r'margin:12px 0', 'margin:15px 0', html)
    html = re.sub(r'padding:8px 10px', 'padding:11px 13px', html)
    html = re.sub(r'padding:8px 11px', 'padding:11px 14px', html)
    html = re.sub(r'padding:8px 12px', 'padding:11px 15px', html)
    html = re.sub(r'padding:9px 11px', 'padding:12px 14px', html)
    html = re.sub(r'padding:10px 12px', 'padding:13px 15px', html)
    html = re.sub(r'padding:12px 14px', 'padding:15px 17px', html)
    html = re.sub(r'padding:14px', 'padding:17px', html)
    # 未显式写行高的 div 统一补 line-height:1.9（长文透气；已有行高的不动）
    html = re.sub(r'<div style="([^"]*)"',
                  lambda m: m.group(0) if 'line-height:' in m.group(1) else '<div style="%s;line-height:1.9"' % m.group(1), html)
    # 主题配色
    cmap = _THEMES.get(theme) or _THEMES['A']
    for old, new in sorted(cmap.items(), key=lambda kv: -len(kv[0])):
        if old.startswith('color:'):
            html = re.sub(old, new, html)
        else:
            html = re.sub(old + r'(?![0-9a-f])', new, html)
    return html


def push(html, title):
    if DRY_RUN:
        print(f'[DRY-RUN] 模拟推送 title={title} 内容长={len(html)}B（未发真实请求）')
        return True, 'dry-run'
    if not PUSHPLUS_TOKEN:
        print('[push] 未配置 PUSHPLUS_TOKEN，跳过推送（安全降级，不发送）')
        return False, 'no_token'
    # 静默时段（模块12）：非关键档跳过；关键档不受影响
    if _in_silence() and not any(k in title for k in KEY_TITLES):
        print(f'[push] 静默时段跳过 title={title}')
        return False, 'silence'
    # 多通道备份（模块12）：webhook 失败不阻断 PushPlus 主通道
    for ch, url in _push_channels().items():
        if not url:
            continue
        try:
            plain = re.sub(r'<[^>]+>', '', html)[:2000]
            if ch == 'wecom':
                body = json.dumps({'msgtype': 'text', 'text': {'content': title + '\n' + plain}}).encode()
            elif ch == 'feishu':
                body = json.dumps({'msg_type': 'text', 'content': {'text': title + '\n' + plain}}).encode()
            else:
                continue
            req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=8).read()
            print(f'[push] 备份通道 {ch} 发送成功 title={title}')
        except Exception as e:
            print(f'[push] 备份通道 {ch} 失败（不阻断主通道） err={e}')
    # PushPlus 内容上限 20000 字（实测超限返回 999 服务端验证错误：发送内容过大）
    MAX_PUSH_LEN = 19000
    html = _style_upgrade(html)
    if len(html) > MAX_PUSH_LEN:
        _cut = MAX_PUSH_LEN
        _tag = html.rfind('</div>', 0, MAX_PUSH_LEN)
        if _tag > MAX_PUSH_LEN - 500:
            _cut = _tag
        html = html[:_cut] + '</div></body></html>'
        print(f'[push] 内容超限已截断 {len(html)}->{_cut}+closing chars')
    body = json.dumps({'token': PUSHPLUS_TOKEN, 'title': title, 'content': html, 'template': 'html'}).encode()
    req = urllib.request.Request(PUSHPLUS_API, data=body, headers={'Content-Type': 'application/json'})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=15).read().decode())
        try:
            ip_req = urllib.request.Request('http://ifconfig.me/ip', headers={'User-Agent':'curl'})
            _ip = urllib.request.urlopen(ip_req, timeout=6).read().decode().strip()
        except Exception:
            _ip = 'ip_unavailable'
        print('[push] OUT_IP:', _ip)
        print('[push] FULL_RESP:', json.dumps(r, ensure_ascii=False))
        ok = r.get('code') == 200
        if not ok:
            # 只打印日志，绝不递归再发推送（避免失败循环）
            print(f'[push] FAIL code={r.get("code")} msg={r.get("msg")} title={title}')
        return ok, r.get('msg')
    except Exception as e:
        print(f'[push] EXCEPTION title={title} err={e} （不再重试告警，避免循环）')
        return False, str(e)


# ============ 休市日新闻汇总：去重 + 组装（2026-10-19 新增） ============
NEWS_PUSH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'last_news_push.json')


def load_news_push():
    try:
        with open(NEWS_PUSH_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_news_push(m):
    with open(NEWS_PUSH_PATH, 'w', encoding='utf-8') as f:
        json.dump(m, f, ensure_ascii=False, indent=1)
    _git_commit_push(NEWS_PUSH_PATH, 'update news push')


def news_push_done(date_str):
    """休市日新闻去重查询：key=日期（兼容旧版每日一次）或 日期+2小时窗口（每2小时一次）。"""
    return load_news_push().get(date_str) is True


def mark_news_push_done(date_str):
    m = load_news_push()
    m[date_str] = True
    # 只保留最近 90 天，避免文件无限增长
    m = {k: v for k, v in sorted(m.items())[-90:]}
    save_news_push(m)


def _news_date(ts):
    """从东财 showtime 提取日期（'YYYY-MM-DD ...' 或毫秒时间戳）。严格区分新闻时间与抓取时间。"""
    if not ts:
        return None
    s = str(ts)
    m = re.match(r'(\d{4}-\d{2}-\d{2})', s)
    if m:
        return m.group(1)
    if s.isdigit():
        try:
            return datetime.fromtimestamp(int(s) / 1000).strftime('%Y-%m-%d')
        except Exception:
            return None
    return None


def _holiday_ds(items):
    """休市日新闻 LLM 深挖：只挖「暗线方向」（谁真受益＋产业链环节＋当前阶段＋后续往哪发酵），
    外加板块题材/相关个股/大白话。不出利好、利空、操作（2026-11-07 用户指令）。失败返回 {}。
    分批调用（每批 5 条），尽量让每条新闻都拿到暗线，而不是只挖前几条、其余留空壳。"""
    if not items or not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return {}
    out = {}
    for _off in range(0, len(items), 5):
        _batch = items[_off:_off + 5]
        news_txt = '\n'.join(f"- {x['title']}（摘要：{x['summary'][:50]}）" for x in _batch)
        fmt = ('你是一线游资，休市日新闻汇总。只做情报，不做涨跌判断、不给买卖价、不贴利好利空标签。\n'
               + FIVE_BRIEF + '\n'
               + '【每条只挖暗线方向，不挖情绪】必须讲清三件事：①这条消息里谁是真受益方（点名到公司或产业链环节，不许用「相关/涉及/布局/受益于」糊弄）②它落在哪条产业链的哪个环节，这个环节现在处在什么阶段（缺货/涨价/扩产/刚起步/已兑现/产能爬坡）③后面还可能往哪个方向继续发酵（下一棒会打给谁、什么条件下发酵会断）。\n'
               + '【硬约束】正文里禁止出现「利好」「利空」「操作」「买点」「止损」「仓位」「建议买入」这些词，禁止给涨跌预测；暗线必须落到真实业务，写不出就写「未见明确暗线业务」。\n'
               + '新闻列表：\n' + news_txt + '\n'
               + '只输出 JSON：{"items":[{"t":"标题(照抄)","sector":"板块题材(至少8字，猜不到写「暂看不出直接关联」)","stocks":"相关个股(没有写无)","dark":"暗线方向(至少30字：谁真受益+产业链哪个环节+当前阶段+后续往哪发酵)","why":"大白话(一句话戳穿本质，至少15字，不写涨跌不写买卖)"}]}，必须覆盖每条；纯凑数新闻直接跳过。')
        t = ask_deepseek({'task': 'holiday_ds', 'news': [{'title': x['title'], 'summary': x['summary'][:60]} for x in _batch],
                          'format': fmt}, purpose='holiday_ds')
        if not t:
            print(f'[holiday] 第 {_off // 5 + 1} 批（{len(_batch)} 条）模型未返回')
            continue
        try:
            _j = json.loads(t)
            for it in _j.get('items') or []:
                tt = str(it.get('t') or '').strip()
                if tt and (it.get('dark') or it.get('why') or it.get('sector')):
                    out[tt] = {'sector': str(it.get('sector') or ''), 'stocks': str(it.get('stocks') or ''),
                               'dark': str(it.get('dark') or ''), 'why': str(it.get('why') or '')}
        except Exception as e:
            print(f'[holiday] 第 {_off // 5 + 1} 批解析失败: {e}')
    print(f'[holiday] 深挖覆盖 {len(out)}/{len(items)} 条')
    return out


def build_holiday_news():
    """休市日新闻汇总：仅当天实际获取到的新闻 → 标题/来源/时间/摘要/板块题材个股/暗线方向/大白话。
    （已取消利好、利空、操作三行，改为直接说明这条新闻的暗线方向 —— 2026-11-07 用户指令）

    返回 (html, today) 或 (None, today)：
      - 新闻源异常（网络/解析抛错）→ None，调用方不推送（记录失败原因）；
      - 源正常但当天无有效新闻 → 推送明确标注"今日未获取到有效新闻"的汇总（不伪造内容）。
    不调用 DeepSeek，不生成任何行情/涨跌幅/交易建议。
    """
    today = _bj_now().strftime('%Y-%m-%d')
    t0 = time.time()
    try:
        news = get_news(15)
        _record('holiday_news', True, time.time() - t0, f'{len(news)}条')
    except Exception as e:
        _record('holiday_news', False, time.time() - t0, str(e)[:80])
        print(f'[holiday] 新闻源异常: {e} → 不推送（避免空壳报告）')
        return None, today

    # 只保留"新闻时间日期=今天"的条目（严格区分新闻发布时间与抓取时间）
    today_news = []
    for nw in news:
        d = _news_date(nw.get('ts'))
        if d == today:
            today_news.append(nw)
        else:
            print(f'[holiday] 丢弃非当天新闻: ts={nw.get("ts")!r} title={nw.get("title", "")[:20]}')

    if not today_news:
        print(f'[holiday] {today} 无当天有效新闻（新闻源返回 {len(news)} 条但均非当天/为空）')
        html = ('<div style="color:#e2e8f0;font-size:14px;line-height:1.8;padding:10px;background:#1c2230;'
                'border-radius:8px;">今日未获取到有效新闻<br>'
                '<span style="color:#9aa4b8;font-size:12px;">（新闻源返回 '
                f'{len(news)} 条，均非今日或内容为空；不伪造内容。抓取时间 {_bj_now().strftime("%H:%M")}）</span></div>')
        return _wrap(html, '📰', f'休市日新闻汇总 {today}'), today

    _deep_map = _holiday_ds([{'title': nw.get('title', ''), 'summary': nw.get('summary', '')}
                               for nw in today_news if nw.get('title', '').strip() or nw.get('summary', '').strip()])
    def _nrm(s):
        """标题归一化：只留中英文数字，用于扛住模型改写标点/空格导致的匹配失败。"""
        return re.sub(r'[^\u4e00-\u9fffA-Za-z0-9]', '', str(s or ''))[:40]

    _deep_map_n = {_nrm(k): v for k, v in (_deep_map or {}).items()}

    items = []
    for nw in today_news:
        title = nw.get('title', '').strip()
        summary = nw.get('summary', '').strip()
        ts = str(nw.get('ts') or '')
        src = nw.get('source') or '东财7x24'
        if not title and not summary:
            continue
        _d = (_deep_map or {}).get(title) or _deep_map_n.get(_nrm(title))
        # 2026-11-07 用户指令：取消利好/利空/操作三行，也不再打情绪标签，只讲暗线方向
        color = TEAL
        tag_html = ''
        if _d:
            _sec2 = _d.get('sector') or ''
            _stk2 = _d.get('stocks') or ''
            _dk2 = _d.get('dark') or ''
            _wh2 = _d.get('why') or ''
            if _sec2 or _stk2:
                tag_html = (f'<div style="color:{TEAL};font-size:12px;margin-top:3px;">🏷️ 板块题材：{_sec2}'
                            f'｜相关个股：{_stk2}</div>')
            if _dk2:
                tag_html += (f'<div style="color:{GOLD};font-size:12px;margin-top:2px;">🕳️ 暗线方向：{_dk2}</div>')
            if _wh2:
                tag_html += (f'<div style="color:#e2e8f0;font-size:12px;margin-top:2px;">🗣️ 大白话：{_wh2}</div>')
        else:
            tag_html = ''
        items.append(f"""<div style="background:#1f2635;border-left:3px solid {color};border-radius:8px;padding:9px 11px;margin:7px 0;">
<b style="color:#fff;">{title or '（无标题）'}</b>
<div style="color:{GREY};font-size:12px;margin-top:2px;">🕐 {ts}｜来源：{src}</div>
<div style="color:#c8d0e0;font-size:13px;margin-top:4px;line-height:1.7;">{summary[:200]}</div>{tag_html}</div>""")

    if not items:
        html = ('<div style="color:#e2e8f0;font-size:14px;line-height:1.8;padding:10px;background:#1c2230;'
                'border-radius:8px;">今日未获取到有效新闻<br>'
                '<span style="color:#9aa4b8;font-size:12px;">（当天新闻条目为空，不伪造内容。）</span></div>')
        return _wrap(html, '📰', f'休市日新闻汇总 {today}'), today

    inner = (f'<div style="color:{GREY};font-size:12px;margin-bottom:6px;">A 股休市，不推股票分析；'
             f'以下为当天新闻汇总（共 {len(items)} 条，来源：东财 7x24 快讯，抓取时间 '
             f'{_bj_now().strftime("%H:%M")}）</div>' + ''.join(items))
    return _wrap(inner, '📰', f'休市日新闻汇总 {today}'), today


def health_footer():
    """卡片底部：数据源健康摘要（不把失败记成0）。"""
    bad = [k for k, v in HEALTH['sources'].items() if not v['ok']]
    tot = len(HEALTH['calls'])
    okn = sum(1 for c in HEALTH['calls'] if c['ok'])
    if bad:
        st = f'⚠️ 数据缺源：{"、".join(bad)}（该板块未统计）'
    else:
        st = f'数据源正常 {okn}/{tot}'
    return f'<div style="margin-top:10px;color:{GREY};font-size:11px;">🔧 {st} · {_bj_now().strftime("%H:%M")}</div>'


def holiday_slot(slot):
    """休市日统一处理：每 2 小时推一次当天新闻汇总（去重键=日期+2小时窗口；源失败不推）。返回 True 表示已处理（调用方应退出）。"""
    today = _bj_now().strftime('%Y-%m-%d')
    win = _bj_now().hour // 2 * 2
    win_key = f'{today}-{win:02d}'
    if news_push_done(win_key):
        print(f'SLOT {slot} 休市日新闻汇总 {win_key} 窗口已推送（2小时去重），跳过')
        return True
    html, _ = build_holiday_news()
    if html is None:
        print(f'SLOT {slot} 休市日新闻源失败，不推送空壳')
        return True
    ok, msg = push(html, f'📰 休市日新闻汇总 {_bj_now().strftime("%m/%d %H:%M")}')
    if ok:
        mark_news_push_done(win_key)
        mark_news_push_done(today)  # 兼容旧版每日键（仅记录，不作为 2h 窗口去重依据）
    print(f'SLOT {slot} 休市新闻 PUSH', ok, msg)
    return True


if __name__ == '__main__':
    import sys
    args = sys.argv[1:]
    slot = os.environ.get('SLOT')
    if not slot and '--time' in args:
        slot = args[args.index('--time') + 1]
    elif not slot:
        slot = args[0] if args else None
    force = None
    if '--force' in args:
        force = args[args.index('--force') + 1]
        if force == '':
            force = None
    if force:
        FORCE_SLOT = force
        slot = force
    alias = {'morning': 'pre', 'pre': 'pre', 'auction': 'auction', 'tail': 'tail', 'tail_auction': 'tail', 'hourly': 'hourly',
             'noon': 'noon', 'midday': 'noon', 'eod': 'eod', 'close': 'eod', 'risk': 'risk'}
    slot = alias.get(slot, slot) if slot else None
    if not slot:
        h = datetime.utcnow().hour
        slot = {0: 'pre', 1: 'auction', 2: 'hourly', 3: 'noon',
                5: 'hourly', 6: 'hourly', 7: 'eod'}.get(h, 'eod')
    # —— 演示模式（--demo-all）：跳过休市闸门/去重/静默，轮流构建核心槽位并推送。仅显式参数触发，不影响定时任务 ——
    if '--demo-all' in args or (force and force and force.startswith('demo-')):
        # 演示要看到「全部」卡：必须放行盘中/异动时段闸门，
        # 否则盘后或周末跑时 newsfire/risk/watch 会被 _in_session 全部拦成空。
        FORCE_SLOT = 'demo-all'
        demo_items = [('盘前速递', build_pre), ('启动预警', build_warn), ('竞价观察', build_auction),
                      ('盘中解读', build_hourly), ('新闻发酵', build_newsfire), ('风险体检', build_risk),
                      ('午间作战', build_noon),
                      ('事件简报', lambda: _wrap(build_events('noon' if _bj_now().hour < 14 else 'eod'), '📰', '事件简报')),
                      ('两小时汇总', build_news2h), ('跟涨三步走', lambda: build_followup()[0]),
                      ('尾盘竞价', build_tail), ('多周期视角', build_cycle),
                      ('收盘复盘', build_eod), ('外盘窗口', build_ext), ('晚间汇总', build_evening),
                      ('异动提醒', build_watch), ('休市新闻', lambda: build_holiday_news()[0]),
                      ('因子体检', build_factor_weekly)]
        demo_batch = None
        if force and force.startswith('demo-'):
            try:
                demo_batch = int(force.split('-')[1])
            except Exception:
                demo_batch = None
        if demo_batch is not None:
            demo_items = demo_items[demo_batch * 3:(demo_batch + 1) * 3]
            print(f'[demo] 批次 {demo_batch}，本批模块 {len(demo_items)} 个')
        sent, skipped = [], []
        # 演示结果单独落 /tmp（模块内部有 git 写回，会覆盖仓库内文件，所以不能写 tools/data/）
        _trace = os.path.join(os.environ.get('TMPDIR') or os.environ.get('TEMP') or '/tmp', 'demo_trace.txt')
        _traces = []

        def _tr(line):
            _traces.append(line)
            try:
                with open(_trace, 'a', encoding='utf-8') as f:
                    f.write(line + '\n')
            except Exception:
                pass

        import traceback
        _tr(f'=== demo start {_bj_now().strftime("%Y-%m-%d %H:%M:%S")} items={len(demo_items)} ===')
        for name, fn in demo_items:
            try:
                r = fn()
                if isinstance(r, (tuple, list)):
                    r = r[0] if r else None
                html = r
            except Exception as e:
                _tr(f'{name} SKIP 异常 {e}\n{traceback.format_exc()[:900]}')
                skipped.append(f'{name}(异常:{str(e)[:60]})')
                print(f'[demo] {name} SKIP 异常 {str(e)[:80]}')
                continue
            if not isinstance(html, str) or not html.strip():
                _tr(f'{name} SKIP 无数据 type={type(html).__name__}')
                skipped.append(f'{name}(无数据)')
                print(f'[demo] {name} SKIP 无数据 type={type(html).__name__}')
                continue
            try:
                ok, msg = push(html, f'【演示】{name} · 轮流试跑')
            except Exception as e:
                _tr(f'{name} PUSH 异常 {e}\n{traceback.format_exc()[:900]}')
                skipped.append(f'{name}(推送异常:{str(e)[:40]})')
                print(f'[demo] {name} PUSH 异常 {str(e)[:80]}')
                continue
            _tr(f'{name} PUSH {ok} {msg} html_len={len(html)}')
            (sent if ok else skipped).append(name if ok else f'{name}({str(msg)[:40]})')
            print(f'[demo] {name} PUSH', ok, msg)
        _tr(f'sent={sent} skipped={skipped}')
        print('[demo] sent:', sent, '| skipped:', skipped)
        print('[demo] TRACE_BEGIN')
        for _l in _traces:
            print(_l)
        print('[demo] TRACE_END')
        sys.exit(0)

    # （用户指令 2026-11-04：突破回踩·主力成本锚 anchor/review/evaluate 三档已删除，不再有对应推送分支）

    # 周日「因子体检报告」（第5步）：周日是休市日，必须放在交易日闸门之前，否则会被 holiday_slot 吃掉
    if slot == 'factor_weekly':
        _fwk = _slot_window_key('factor_weekly')
        if not force and _slot_done(_fwk):
            print('SLOT factor_weekly 本期已推送，跳过')
            sys.exit(0)
        try:
            html = build_factor_weekly()
        except Exception as e:
            print('[fw] build exception:', e)
            html = None
        if not html:
            print('SLOT factor_weekly: 构建失败或无数据，不推送')
            sys.exit(0)
        ok, msg = push(html, f'因子体检报告 {_bj_now().strftime("%m/%d")}')
        print('SLOT factor_weekly PUSH', ok, msg)
        if ok:
            _mark_slot_done(_fwk)
        sys.exit(0)

    # 休市日（周末/法定节假日/调休休市）：只发当天新闻汇总（每2小时窗口去重），不推任何股票分析、不调 DeepSeek
    if not is_trading_day():
        holiday_slot(slot)
        sys.exit(0)
    # 每2小时新闻 cron（休市日专用调度）在交易日的兜底触发点：非盘面时段直接跳过，避免多余异动推送
    if slot == 'watch' and not force and is_trading_day():
        _hm = _bj_now().strftime('%H:%M')
        if not ('09:15' <= _hm <= '15:05'):
            print(f'SLOT watch 交易日非盘面时段（{_hm}），每2小时cron兜底跳过，不推送')
            sys.exit(0)
    # watch 异动档不做 slot_done 窗口去重（每次内容随行情变化，重复推送风险由交易日时段闸门
    # 09:15-15:05 + 每2小时 cron 兜底控制；如需更强去重可在 build_watch 内按分钟做增量阈值）
    if slot == 'watch':
        try:
            _factor_signal_settle()  # T+1/T+5 回填（幂等，已回填的记录跳过）
        except Exception as _se:
            print(f'[sigcsv] watch 回填异常 {_se}')
        try:
            html = build_watch()
        except Exception as e:
            print('[watch] build exception:', e)
            try:
                import traceback as _tb
                print('[watch] traceback:', _tb.format_exc()[-1000:])
            except Exception:
                pass
            html = None
        if html is None:
            print('SLOT watch: 无异动或构建失败，不推送')
            sys.exit(0)
        ok, msg = push(html, f'异动提醒 {_bj_now().strftime("%H:%M")}')
        print('SLOT watch PUSH', ok, msg)
        # —— 雷达扫描（11-05 指令⑪）：与盘中 watch 同批触发，当日去重，独立卡推送 ——
        try:
            _dkey = _bj_now().strftime('%Y-%m-%d')
            if not force and _radar_done(_dkey):
                print('[radar] 今日雷达扫描已推过，跳过')
            else:
                _rh = build_radar()
                if _rh:
                    _ok2, _msg2 = push(_rh, f'雷达扫描 {_bj_now().strftime("%H:%M")}')
                    print('SLOT radar PUSH', _ok2, _msg2)
                    if _ok2:
                        _mark_radar_done(_dkey)
                else:
                    print('[radar] 无达标个股或构建失败，不推送雷达扫描')
        except Exception as e:
            print('[radar] build/push exception:', e)
        sys.exit(0)
    # 新闻发酵（11-05 指令⑧）：盘中 10 条消息汇总，窗口去重
    if slot == 'newsfire':
        if not force and _slot_done(_slot_window_key('newsfire')):
            print('SLOT newsfire 本窗口已推（slot_done 去重），跳过')
            sys.exit(0)
        try:
            _nf = build_newsfire()
        except Exception as e:
            print('[newsfire] build exception:', e)
            _nf = None
        if _nf is None:
            print('SLOT newsfire: 构建失败/无新闻，不推送')
            sys.exit(0)
        ok, msg = push(_nf, f'新闻发酵 {_bj_now().strftime("%H:%M")}')
        if ok:
            _mark_slot_done(_slot_window_key('newsfire'))
        print('SLOT newsfire PUSH', ok, msg)
        sys.exit(0)
    if slot == 'confirm':
        if not force and _slot_done(_slot_key('confirm')):
            print('SLOT confirm 今日已推（slot_done 去重），跳过')
            sys.exit(0)
        try:
            _cf = build_confirm()
        except Exception as e:
            print('[confirm] build exception:', e)
            _cf = None
        if _cf is None:
            print('SLOT confirm: 构建失败，不推送')
            sys.exit(0)
        ok, msg = push(_cf, f'竞价确认 {_bj_now().strftime("%H:%M")}')
        if ok:
            _mark_slot_done(_slot_key('confirm'))
        print('SLOT confirm PUSH', ok, msg)
        sys.exit(0)
    if slot == 'ext':
        if not force and _slot_done(_slot_window_key('ext')):
            print('SLOT ext 本窗口已推（slot_done 去重），跳过')
            sys.exit(0)
        try:
            _ex = build_ext()
        except Exception as e:
            print('[ext] build exception:', e)
            _ex = None
        if _ex is None:
            print('SLOT ext: 构建失败，不推送')
            sys.exit(0)
        ok, msg = push(_ex, f'外盘窗口 {_bj_now().strftime("%H:%M")}')
        if ok:
            _mark_slot_done(_slot_window_key('ext'))
        print('SLOT ext PUSH', ok, msg)
        sys.exit(0)
    if slot == 'evening':
        if not force and _slot_done(_slot_key('evening')):
            print('SLOT evening 今日已推（slot_done 去重），跳过')
            sys.exit(0)
        try:
            _ev = build_evening()
        except Exception as e:
            print('[evening] build exception:', e)
            _ev = None
        if _ev is None:
            print('SLOT evening: 构建失败，不推送')
            sys.exit(0)
        ok, msg = push(_ev, f'晚间消息汇总 {_bj_now().strftime("%H:%M")}')
        if ok:
            _mark_slot_done(_slot_key('evening'))
        print('SLOT evening PUSH', ok, msg)
        sys.exit(0)
    if slot == 'follow':
        if not force and _slot_done(_slot_window_key('follow')):
            print('SLOT follow 本窗口已推（slot_done 去重），跳过')
            sys.exit(0)
        try:
            _fl, _why = build_followup()
        except Exception as e:
            print('[follow] build exception:', e)
            _fl, _why = None, f'异常 {e}'
        if _fl is None:
            print('SLOT follow: 不推送（', _why, '）')
            sys.exit(0)
        ok, msg = push(_fl, f'跟涨三步走 {_bj_now().strftime("%H:%M")}')
        if ok:
            _mark_slot_done(_slot_window_key('follow'))
        print('SLOT follow PUSH', ok, msg)
        sys.exit(0)
    if slot == 'warn':
        if not force and _slot_done(_slot_key('warn')):
            print('SLOT warn 今日已推（slot_done.json 去重），跳过')
            sys.exit(0)
        try:
            _wr = build_warn()
        except Exception as e:
            print('[warn] build exception:', e)
            _wr = None
        if _wr is None:
            print('SLOT warn: 今日暂无明确启动预警，不调用不推送')
            sys.exit(0)
        html, wtitle = _wr
        ok, msg = push(html, wtitle)
        if ok:
            # force 也标记（手动演示后同日定时不再重推——双推修复①）
            _mark_slot_done(_slot_key('warn'))
        print('SLOT warn PUSH', ok, msg)
        sys.exit(0)
    if slot == 'news':
        # 旧事件简报独立档（11:40=noon 档 / 15:10·15:35=eod 档），复用 build_events
        # 同日同窗口去重：同一 5 分钟窗口被多个 run 触发时只推一次（防手动/排队 run 双推）
        _nk = _news_window_key()
        if not force and _slot_done(_nk):
            print('SLOT news 本窗口已推（slot_done 去重），跳过')
            sys.exit(0)
        _b = build_events('noon' if _bj_now().hour < 14 else 'eod')
        if not _b:
            print('SLOT news: 无有效事件，不推送')
            sys.exit(0)
        ok, msg = push(_wrap(_b, '📰', '事件简报'), f'事件简报 {_bj_now().strftime("%H:%M")}')
        if ok:
            # force 也标记（手动 dispatch 后同日定时 run 不再二次推送——双推修复①，图二铁证场景）
            _mark_slot_done(_nk)
        print('SLOT news PUSH', ok, msg)
        sys.exit(0)


    if slot == 'zscan':
        if not force and _slot_done(_slot_key('zscan')):
            print('SLOT zscan 今日已推（slot_done 去重），跳过')
            sys.exit(0)
        try:
            _zs = build_zscan(os.environ.get('INPUT_CODE') or None)
        except Exception as e:
            print('[zscan] build exception:', e)
            _zs = ''
        if not _zs:
            print('SLOT zscan: 构建失败，不推送')
            sys.exit(0)
        ok, msg = push(_wrap(_zs, '🛰', '主力雷达'), f'主力雷达 {_bj_now().strftime("%m/%d %H:%M")}')
        if ok:
            _mark_slot_done(_slot_key('zscan'))
        print('SLOT zscan PUSH', ok, msg)
        sys.exit(0)
    if slot == 'deep6':
        if not force and _slot_done(_slot_key('deep6')):
            print('SLOT deep6 今日已推（slot_done 去重），跳过')
            sys.exit(0)
        try:
            _d6 = build_deep6(os.environ.get('INPUT_CODE') or '')
        except Exception as e:
            print('[deep6] build exception:', e)
            _d6 = ''
        if not _d6:
            print('SLOT deep6: 无标的或构建失败，不推送')
            sys.exit(0)
        ok, msg = push(_wrap(_d6, '🔬', '个股深度六层'), f'个股深度六层 {_bj_now().strftime("%m/%d %H:%M")}')
        if ok:
            _mark_slot_done(_slot_key('deep6'))
        print('SLOT deep6 PUSH', ok, msg)
        sys.exit(0)
    if slot == 'news2h':
        if not force and _slot_done(_slot_window_key('news2h')):
            print('SLOT news2h 本窗口已推（slot_done 去重），跳过')
            sys.exit(0)
        try:
            _n2 = build_news2h()
        except Exception as e:
            print('[news2h] build exception:', e)
            _n2 = None
        if _n2 is None:
            print('SLOT news2h: 构建失败，不推送')
            sys.exit(0)
        ok, msg = push(_n2, f'两小时消息汇总 {_bj_now().strftime("%H:%M")}')
        if ok:
            _mark_slot_done(_slot_window_key('news2h'))
        print('SLOT news2h PUSH', ok, msg)
        sys.exit(0)
    if slot == 'eod':
        try:
            _factor_signal_settle()  # 收盘后回填 T+1/T+5（幂等）
        except Exception as _se:
            print(f'[sigcsv] eod 回填异常 {_se}')
        try:
            _sig_settle_monitor()  # 11-09 起 T+1 落笔监控（只读账本+落盘状态）
        except Exception as _me:
            print(f'[sigcsv] monitor 异常 {_me}')
        today = _bj_now().strftime('%Y-%m-%d')
        if eod_push_done(today):
            print(f'SLOT eod 今日已推送（eod_status.json 去重），跳过')
            sys.exit(0)
        try:
            html = build_eod()
        except Exception as e:
            print('[build] exception:', e)
            html = _wrap(f'<div style="color:{RED}">⚠️ 本卡片构建异常：{e}</div>', '⚠️', '构建异常')
            ok, msg = push(html, f'{TITLES["eod"]} {_bj_now().strftime("%m/%d %H:%M")}')
            print('SLOT eod PUSH(异常兜底，不标记去重)', ok, msg)
            sys.exit(0)
        ok, msg = push(html, f'{TITLES["eod"]} {_bj_now().strftime("%m/%d %H:%M")}')
        if ok:
            mark_eod_done(today)
            _git_commit_push('data/eod_status.json', 'update eod status')
        print('SLOT eod PUSH', ok, msg)
        sys.exit(0)
    # 雷达扫描（11-05 指令⑪）独立槽：当日去重 + 无达标股不推
    if slot == 'radar':
        _dkey = _bj_now().strftime('%Y-%m-%d')
        if not force and _radar_done(_dkey):
            print('SLOT radar 今日已推（radar_done.json 去重），跳过')
            sys.exit(0)
        try:
            _rh = build_radar()
        except Exception as e:
            print('[build] radar exception:', e)
            _rh = None
        if _rh is None:
            print('SLOT radar 无达标个股/非盘中/构建失败，不推送')
            sys.exit(0)
        ok, msg = push(_rh, f'{TITLES["radar"]} {_bj_now().strftime("%H:%M")}')
        if ok:
            _mark_radar_done(_dkey)
        print('SLOT radar PUSH', ok, msg)
        sys.exit(0)
    # —— 多点cron 当日去重（仅定时自动run；手动 --force 不受限，用于演示/验证）——
    if not force and slot in ('auction', 'tail', 'pre', 'noon', 'hourly', 'risk', 'cycle'):
        _k = _slot_key(slot)
        if _slot_done(_k):
            print('SLOT %s 今日已推（slot_done.json 去重），跳过' % slot)
            sys.exit(0)
    slot = slot if slot in BUILDERS else 'eod'
    try:
        html = BUILDERS[slot]()
    except Exception as e:
        print('[build] exception:', e)
        html = _wrap(f'<div style="color:{RED}">⚠️ 本卡片构建异常：{e}</div>', '⚠️', '构建异常')
    if html is None:
        print('SLOT', slot, '构建返回 None，不推送')
        sys.exit(0)
    ok, msg = push(html, f'{TITLES[slot]} {_bj_now().strftime("%m/%d %H:%M")}')
    if ok and slot in ('auction', 'tail', 'pre', 'noon', 'hourly', 'risk', 'cycle'):
        # force 也标记（手动演示后同日定时不再重推——双推修复①）
        _mark_slot_done(_slot_key(slot))
    print('SLOT', slot, 'PUSH', ok, msg)

# NO_HOLD_PATCH_V2
