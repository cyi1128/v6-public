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
from collections import defaultdict
from datetime import datetime

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

RED, GREEN, GOLD, TEAL, GREY = '#ff6b6b', '#51cf66', '#ffd43b', '#66d9e8', '#9aa4b8'

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
        try:
            return {'price': float(f[3]), 'pct': float(f[32]), 'open': float(f[5]),
                    'prev': float(f[4]), 'lb': float(f[43] or 0), 'vol': float(f[6] or 0),
                    'avg': avg}
        except ValueError:
            return {'price': float(f[3]), 'pct': float(f[32]), 'open': float(f[5]),
                    'prev': float(f[4]), 'lb': 0.0, 'vol': float(f[6] or 0), 'avg': avg}
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
           '【第零步·先看当日真实盘面与筹码】' + rel_txt + '\n'
           '【第一步·先看筹码后说话】先把事实说清（谁发布/干了什么/涉及谁），并判断这条消息是主力真要拉的借口，还是借消息出货的烟幕。\n'
           '【第二步·问三个主力问题】①主力为什么动它——有没有前期建仓痕迹（横盘吸筹/挖坑洗盘/红肥绿瘦）、上方筹码是否真空；②跟我什么关系——能不能跟、会不会被当接盘；③主力下一步想干什么。\n'
           '【第三步·翻译成人话】用游资黑话，结论先行+动作可执行（具体价位/仓位/止损）。\n'
           '【第四步·套游资纪律】高位连板一律不接；没有建仓痕迹的票只看戏；破点火开盘价无条件走。\n'
           '【第五步·自查】结论和逻辑不许矛盾，说机会必须带主力出货信号。\n'
           '只输出 JSON，不要任何其他文字：\n'
           '{"items":[{"t":"事件标题","i":"影响板块/题材+主力意图判断，至少15字（猜不到写「暂看不出直接关联」，不许编）","s":"代表个股深挖——【有真实相关个股时】必须写：建仓痕迹（有/无+具体表现）、筹码状态（真空/套牢）、为什么资金今天选它、主业一句话。禁止万能句和模板堆砌。【没有直接相关个股时】只写「今日盘面暂无与该事件直接共振的代表个股」+检索结果依据，禁止编造盘面。","w":"大白话：一句话戳穿真假+主力意图，至少25字","a":"操作：买/躲/看，必须绑定具体票+价位+触发条件+止损（破点火开盘价或成本区），代表股为空时写「今日无直接标的」+具体等待条件（点名真实公司名）。禁止万能套话和编造数值。至少20字"}]}\n'
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
            f'border-radius:8px;color:{RED};font-size:13px;">⚠️ 高位炸板分歧：{names}（炸板不追，等回封）</div>')


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


def get_klines(code, n=20):
    url = f'http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,{n},qfq'
    d = json.loads(_get(url))
    node = d.get('data', {}).get(code, {}) or {}
    return node.get('qfqday') or node.get('day') or []


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
    txt, ok_zb = _getm(_pool('ZB'), 'zb_pool')
    zb_names = set()
    if ok_zb and txt:
        zbp = (json.loads(txt).get('data') or {}).get('pool') or []
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
            'zb_names': zb_names,
            'pool_ok': {'zt': ok_zt, 'zb': ok_zb, 'dt': ok_dt}}


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
    """持仓竞价三分法（用户口径）：
    - 开幅≥7%：不追，观察是否炸板回封
    - 2%~7% 且量比≥1.8 且 竞价量/昨量≥10%：可加仓
    - 低开<0 且跌幅<3%：小仓试错
    - 其余：观察（标注位置风险由调用方补）"""
    if open_pct >= 7:
        return '不追', '一字/开幅≥7%，不追，观察是否炸板回封'
    if 2 <= open_pct < 7 and lb >= 1.8 and (vq_ratio is None or vq_ratio >= 10):
        return '可加仓', f'开{open_pct:+.1f}%·量比{lb:.1f}≥1.8' + (f'·竞价量/昨量{vq_ratio:.0f}%≥10' if vq_ratio else '') + '，站稳可加'
    if open_pct < 0 and open_pct > -3:
        return '小仓试错', f'低开{open_pct:+.1f}%未破-3%，小仓试错'
    return '观察', f'开幅{open_pct:+.1f}%不在2~7%、量比{lb:.1f}不到1.8，量价都撑不起，不动'


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
    """判断：主线持续 还是 板块轮动。"""
    mem = load_memory()
    days = sorted(mem.keys(), reverse=True)
    today_top = {n for n, _ in d['tops'][:3]}
    prev_top = set()
    for pd in days[1:3]:  # 昨天+前天
        prev_top |= set(mem.get(pd, {}).keys())
    overlap = today_top & prev_top
    if len(overlap) >= 2:
        return '主线持续', f"今天最强的{len(overlap)}个板块（{'、'.join(list(overlap)[:2])}）昨天也在涨，主线没换。", overlap
    return '板块轮动', f"今天最强方向（{'、'.join(list(today_top)[:2])}）和前一两天完全不重样，资金在到处试，别追高。", overlap


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
                        'action': '只观察，等龙头回封或龙二低吸'})
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
                                    'action': '可轻仓试错，破-3%走'})
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
           '{"items":[{"t":"事件标题（照抄原文）","good":"利好哪个板块/题材/个股+主力可能怎么做，至少12字（无明显利好写「无明显直接利好」）","bad":"利空哪个板块/题材/个股+主力可能怎么跑，至少12字（无明显利空写「无明显直接利空」）","logic":"逻辑原因：主力意图深挖，至少25字","why":"大白话：一句话戳穿真假+怎么应对，至少22字","act":"操作：有明确可操作的具体股票才写（股票名+代码+买点/止损/仓位），没有就写「无明确可操作标的」"}]}，【单边定性铁律】同一条事件 good 与 bad 必须二选一，禁止又✅又⚠️。必须覆盖每条事件。')
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
- 【明牌龙头】：新闻直接点名的板块龙头是谁？已经涨停或大涨的，明确告知「买不到，不追」。
- 【细分暗线与平替】：顺着利好，哪个细分最受益？指出可操作方向（优先有前期建仓痕迹的）。
- 【个股与操作】：推荐1-2只「容量中军」或「低位补涨」特征的个股，必须有建仓痕迹或筹码优势，结合突破回踩体系给操作：等缩量回踩均价线低吸？还是放量突破平台半路扫？防守底线在哪？
2. 利空信息的排雷避险：
- 【危险板块】：新闻打击的具体板块/题材。
- 【个股与操作】：哪些高位票或资金正在出逃的个股必须立刻规避？手里有的怎么处理（竞价核按钮/盘中反抽止损）？
3. 中性信息防忽悠：识别看似利好实则「借消息出货」的新闻，大白话点破。
### 输出格式（直接大白话，直击交易核心）：
【今日核心大方向】：一句话定调
🔥 【利好题材与个股实操】：
- 题材细分：XX
- 明面龙头：（提示不能追）
- 实战标的（中军/补涨）：（代码名称，必须提建仓痕迹）
- 怎么买：（缩量回踩xx元低吸/放量突破前高xx元半路，跌破xx止损）
💣 【利空题材与个股避险】：
- 危险题材：XX
- 危险个股：（提示逃跑）
- 怎么跑：（反抽均线无脑清仓）
💡 【隐形坑与潜伏暗线】：（新闻点名的A其实没戏，同产业链的B才是主力真正想拉的暗线）
要求：必须绑定上面输入新闻的具体内容；禁止空话套话；没有价格数据时写「待盘中确认」，不许硬编价位；禁止把推测当已核实事实。'''
    fmt = ('以下是今日事件清单（每条含标签与影响板块）：\n' + evs + '\n'
           '严格按系统提示词输出：开头【今日核心大方向】一句话定调，然后 🔥利好实操 / 💣利空避险 / 💡隐形坑三段，'
           '每段用「- 题材细分 / - 明面龙头 / - 实战标的 / - 怎么买 / - 危险题材 / - 危险个股 / - 怎么跑」子项格式，'
           '自然段大白话，直接输出，不要JSON、不要任何额外说明。')
    t = ask_deepseek({'task': 'event_summary_v3', 'events': [x['title'] for x in items[:20]],
                      'format': fmt}, purpose='brief_summary_v3', system_text=sys_text)
    if not t or len(t.strip()) < 60:
        return ''
    import html as _h
    parts = []
    for ln in t.strip().split('\n'):
        ln = ln.strip()
        if not ln:
            continue
        e = _h.escape(ln)
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
    n = 30  # 事件汇总：有多少显示多少，最多30条
    out = out[:n]
    if not out:
        return ''
    _sum_html = _brief_summary(out)      # 顶部大白话汇总（做减法+实战映射）
    cards = []
    for x in out:
        cards.append(f"""<div style="background:#1f2635;border-left:4px solid {x['color']};border-radius:10px;padding:8px 12px;margin:5px 0;">
<div style="font-weight:800;color:{x['color']};">【{x['tag']}】</div>
<div style="color:#fff;font-size:13px;margin-top:3px;">{x['title']}</div>
<div style="color:{GREY};font-size:12px;margin-top:2px;">影响：{x['rel']}</div></div>""")
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
    return f'<div style="margin-top:12px;font-size:15px;font-weight:800;color:{GOLD};">{head}</div>{_sum_html}{cards}'


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
_TRADER_RULES = '''你是一线游资操盘手，不是分析师。要求：大白话、直接、狠、带盘口细节，说话像真人游资在微信群里盯盘。禁止官方腔、书面语、堆砌形容词。硬性要求：如果今日没有明确主力建仓或拉升痕迹，必须明确写「今日无强推」，并说明原因；禁止为了凑数而推荐。禁止万能句。仓位必须与主力阶段绑定且全天一致，不能前后矛盾。只允许空仓/1成/2成/半仓。'''
def _pos_advice(emotion):
    """情绪→建议总仓位文案（用户硬规则：全天一致，禁止各时段写死打架）。"""
    return {'偏多': '4~6成（主升加速，只做主线，不追高）',
            '震荡': '2~4成（回暖/分歧，只做分歧低吸）',
            '偏空': '空仓或1成试错（退潮防守，不接飞刀）',
            '冰点': '1~2成（情绪冰点，只看不动）'}.get(emotion or '震荡', '2~4成（震荡对待）')


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
        act, buy, pos = '回踩再买', '回踩5日线附近/开盘±1%内', '20%'
    elif sc >= 5.5:
        act, buy, pos = '轻仓试错', '龙头炸板回封或龙二平开低吸', '10%'
    else:
        act, buy, pos = '观察', '不追，等明确回踩', '0%'
    if mkt_label in ('快速轮动', '情绪退潮'):
        pos = '≤5%'
    reason = f'{sec_n}题材强度{sec_s}分，该股为{stype}。'
    reason += ('当前轮动，仓位减半、止损收紧。' if mkt_label == '快速轮动' else
               ('退潮期不建议新开仓。' if mkt_label == '情绪退潮' else '主线延续，按标准仓位参与。'))
    return {'n': stock.get('n'), 'code': stock.get('c'), 'sec': sec_n,
            'type': stype, 'score': sc, 'act': act, 'buy': buy,
            'stop': '破成本-3%或当日最低价', 'pos': pos, 'why': reason}


_ASK_DS_SYS_AC = '''你是有10年以上实战经验的一线游资，服务竞价、主题点火、尾盘深水星、午间作战、收盘复盘、消息解读场景。
【主力游资运作逻辑·强制】
1. 先看筹码后说话：对每条数据先判断主力阶段（吸筹中/洗盘中/拉升中/出货中/对倒中），再问三个问题——主力为什么动它、跟我什么关系、主力下一步想干什么。
2. 翻译成人话：用游资黑话（挖坑洗盘/红肥绿瘦/上方真空/脉冲试盘/对倒出货），结论先行+动作可执行。
3. 套游资纪律：高位连板一律不接飞刀；没有明显建仓痕迹的票只看戏；加仓只加主力还没出货的；破点火开盘价或成本区无条件走。
4. 自查反推：说机会必须同时说出主力可能出货的信号。
5. 结构化输出：严格按用户指定的格式输出。
【输出规范】语言最接地气，像跟兄弟连麦。推荐标准极严：优先真正有建仓痕迹的龙头/中军；竞价买卖比严重失衡直接降级；高开>4%强制标注「谨慎」；默认半仓起步，严禁满仓。【市值红线】只在30亿-150亿之间写操作标的。【量能红线】禁止编造绝对量能数字，只写相对倍数+价格锚。最终结论只能是：跟主力 / 观察 / 不碰。
【三层认知结构】①信息密度压缩；②因果链显影（谁在动→为什么动→动到哪一步）；③决策接口（触发条件+动作+失败出口）。比喻优先于术语，结论先行，坏消息不软化。'''


_ASK_DS_SYS = '''你是有10年以上实战经验的一线游资，服务竞价、主题点火、尾盘深水星、午间作战、收盘复盘、消息解读场景。
【主力游资运作逻辑·强制】
1. 先看筹码后说话：先判断主力阶段（吸筹/洗盘/拉升/出货/对倒），再问三个主力问题。
2. 翻译成人话：游资黑话优先，结论先行+动作可执行。
3. 套游资纪律：高位连板不接飞刀；无建仓痕迹只看戏；破点火开盘价无条件走。
4. 自查反推：说机会必须带主力出货信号。
5. 结构化输出：严格按用户指定格式。
【输出规范】语言最接地气，像跟兄弟连麦。推荐标准极严：优先真正有建仓痕迹的龙头/中军；竞价买卖比严重失衡直接降级；高开>4%强制标注「谨慎」；默认半仓起步，严禁满仓。【市值红线】只在30亿-150亿之间写操作标的。【量能红线】禁止编造绝对量能数字，只写相对倍数+价格锚。最终结论只能是：跟主力 / 观察 / 不碰。
【确定性层·强制】1. 任何「买/跟」必须同时给出：触发价位或条件 + 量能条件 + 失效/止损条件（破点火开盘价或成本区）。2. 任何「不碰」只写唯一主因（位置过高/无建仓痕迹/题材末段/暗雷/资金出逃）。3. 证据不足只能输出「观察」或「不碰」。4. 仓位只允许：空仓 / 1成试探 / 2成 / 半仓。5. 任何强票必须先判主力阶段。6. 推荐须满足：题材主线 + 有建仓痕迹或筹码优势 + 位置非高位连板 + 有明确买点止损，不足强制观察或不碰。'''

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
                              'max_tokens': (6000 if purpose == 'zforce_radar' else 3000)}).encode('utf-8')
            req = urllib.request.Request(MODELSCOPE_URL, data=body, headers={
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + MODELSCOPE_KEY,
                'User-Agent': 'quantmonitor/1.0'})
            r = json.loads(urllib.request.urlopen(req, timeout=120).read().decode('utf-8'))
            txt = ((r.get('choices') or [{}])[0].get('message') or {}).get('content') or ''
            if txt.strip():
                print(f'[LLM] ModelScope OK model={m} purpose={purpose}')
                return txt.strip()
            print(f'[LLM] ModelScope 空回复 model={m}，试下一个')
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


_ANTI_TEMPLATE_BLOCK = ('''【反模板强化·全局铁律·输出前逐句自查，违反即整段重写】
一、禁止句式（含任何变体）：「值得关注」「建议留意」「板块强势带动」「XX概念+龙头」「资金认可」「结构改善」「情绪回暖」「市场有波动」「建议谨慎」「或将刺激相关板块」「具备投资价值」「风险与机会并存」「当前市场情绪」等空泛套话，一个字都不许写。
二、每条结论必须绑定当天真实数据：谁（具体票/板块）、多少（涨幅/量比/换手/封单/家数/分数/成交额）、何时（几点封板/几点启动/数据采集时间）。禁止无数字的定性结论（"资金进场/情绪回暖/结构改善"必须有数字支撑）。
三、每个操作判断必须给当天唯一主因（位置过高/量能造假/题材末段/暗雷/资金出逃，或当天真实独有主因），禁止列一堆笼统理由凑数。
四、无候选/降级/空仓场景禁止套万能公式（"等待回踩企稳/缩量确认/量能配合/情绪修复再考虑"类），必须写当天独有的等待条件：具体到哪只票、什么价位、什么量能阈值、为什么是这个价位——由当天盘面现算，不许照抄公式。
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
    print('[LLM] ModelScope 两次尝试均失败，回退规则文案')
    _diag_append('[ask_deepseek] ModelScope 两次尝试均失败，purpose=%s' % purpose)
    return ''


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
    """卡片顶部红字/黄字状态条：模型失败 → 规则结论（确定性下降）；额度用尽 → 纯规则判断。"""
    if _DS_FAILED:
        return ('<div style="margin-bottom:8px;padding:7px 10px;background:#3a1a1a;border-left:4px solid #ff6b6b;'
                'border-radius:6px;color:#ff8787;font-size:12px;">⚠️ 模型失败，以下为规则结论，确定性下降（不空推）</div>')
    if _DS_EXHAUSTED:
        return ('<div style="margin-bottom:8px;padding:7px 10px;background:#33281a;border-left:4px solid #ffd43b;'
                'border-radius:6px;color:#ffd43b;font-size:12px;">今日 DS 额度已用，以下为纯规则判断</div>')
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

def _wrap(inner, emoji, title):
    return f"""<div style="background:#161b26;color:#e9ecef;font-family:-apple-system,'Microsoft YaHei',sans-serif;padding:14px;border-radius:12px;">
<div style="font-size:20px;font-weight:800;color:{GOLD};">{emoji} {title} · {datetime.now().strftime('%m/%d %H:%M')}</div>
{_reson_head()}{_ds_status_banner()}{inner}{health_footer()}
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
    """全市场涨幅榜（仅沪深主板+创业板，剔除科创/北交所）。失败返回 []。https 优先，失败换 http。"""
    rows = []
    for scheme in ('https', 'http'):
        url = (scheme + '://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=600&po=1&np=1&fltt=2&invt=2'
               '&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23'
               '&fields=f2,f3,f5,f6,f8,f10,f12,f14,f15,f16,f18,f20,f26,f127')
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
        if _rows is None:
            continue
        rows = []
        for x in _rows:
            try:
                rows.append({
                    'code': str(x.get('f12', '')).strip(),
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


def _auction_filter(rows, zt_lbc=None):
    """硬过滤：仅沪深主板+创业板；剔除ST/退市、次新(<365天)、高开/换手区间外、跌破MA20弱势、
    竞价量/昨量不足（主板<8%/创业<12%）、近5日累计涨幅>25%（连板龙头除外）。"""
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
        # MA20 硬过滤：跌破 MA20 的弱势股剔除（K线失败放行，避免误杀）
        sym = ('sh' if code.startswith('6') else 'sz') + code
        try:
            arr = get_klines(sym, 25)
            if len(arr) >= 20:
                closes = [float(r[2]) for r in arr[-20:]]
                if s['price'] < (sum(closes) / 20):
                    continue
        except Exception:
            pass
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
你的任务是：用大白话（像跟兄弟连麦盯盘一样），顺着资金外溢的逻辑，从盘中异动池里，给我挖出1-2只现在可以买入的"补涨代表股"，并讲透为什么是它、主力前期是怎么建仓洗盘的、技术面和评分够不够咱们上车。
### 推演逻辑（必须连贯叙述，拒绝死板表格）
**第一步：点明现状与资金外溢逻辑**
开场直接说清楚：今天最强的板块是什么？龙头现在封单多少、有多死？说明大资金极度看好这个方向，但在前排买不到筹码。既然资金要赚钱，必然要外溢，这就构成了咱们去低位埋伏"补涨代表"的底层逻辑。
**第二步：为什么选它当补涨代表？（优势与底层暗线）**
直接说出它的核心优势：
- **辨识度与共振**：是不是拥有跟龙头一样的最正宗题材？或叠加另一个大热概念？
- **资金偏好**：盘子够大能容纳机构的"中军平替"？还是盘子极小、位置极低、游资最喜欢拉的"弹性先锋"？
- **主力建仓与洗盘痕迹**：前期是不是在底部横盘时有主力偷偷建仓（小阳线吸筹、红肥绿瘦）？现在拉起来是不是上方筹码真空，没有套牢盘砸盘？没有明显建仓痕迹的票直接降级或不推。
**第三步：技术评分与定仓**
找锚：今天是不是带量突破了前期的震荡平台？量能是不是温和放量（主升初期），而不是爆量滞涨（主力出逃）？
共振评分：龙头封死（+25分），题材正+双概念（+20分），洗盘缩量彻底（+20分），温和放量突破（+15分）。总分超过80分上标准仓（1-2成）；60分左右只能上底仓（1成）。
**第四步：实战怎么买？**
结合现在的分时图，大白话给策略：现在涨了几个点？能不能直接追？还是等回踩分时均线（给出大概价位）再吸？如果跌破哪个关键位，说明咱们埋伏失败，必须止损？
### 输出格式（自然段大白话，不列生硬标题）
开头先交代今天的盘面情况（龙头几板了，封单多大，为什么咱们要找补涨）。
接着直接推演这只补涨标的的底层逻辑（为什么资金会选它，它有什么别人没有的题材或筹码优势）。
然后算算它的技术面评分（锚在哪，洗盘怎样，主力是不是在偷偷建仓拉主升，分数多少，给多少仓位）。
最后给个实操剧本（大白话讲怎么低吸，怎么半路，怎么止损）。
''')


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
    txt = ask_deepseek(payload, purpose='intra_spot', system_text=_SPOT_DS_SYS_text())
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
【红线5条·违反任一条整段作废】
1. 只用输入中实际存在的数据；没给的写"未取得"。
2. 区分数据时间：盘中/收盘/历史不混用。
3. 每条因果判断必须绑定具体数据。
4. 消息分级：公司公告/交易所>董秘公开表态>财经媒体>传闻。
5. 不给"必涨/稳了"；不建议满仓；操作建议必须可执行。
【第一层·盘面事实】列出：现价/涨跌幅/量比/换手/成交额/日内开高低收；近10-12个交易日逐日K线。禁止在摆数据前下任何结论。
【第二层·阶段判定 + 主力阶段】把近期走势切成段落，判定当前处于：高位崩落/缩量横盘出清/试盘点火/确认反包/加速/高位分歧/退潮。同时判断主力阶段：吸筹中/洗盘中/拉升中/出货中。判定必须引用具体日期和量能。
【第三层·消息核验与预期差】对每个上涨理由排序：硬逻辑（公告级）还是软逻辑（题材沾边）。重点挖预期差。
【第四层·题材拆解 + 建仓痕迹】列业务分层表。必须写：有没有前期建仓痕迹（横盘吸筹/挖坑洗盘/红肥绿瘦）、上方筹码是否真空。
【第五层·关键价位 + 主力成本区】上方压力、下方支撑、证伪线。明确主力大概成本区。
【第六层·操作判定】操作评级：持有/加仓条件/减仓触发/止损，全部绑定具体价位和主力阶段。明日预案分三种情况写全。
【输出格式】按六层顺序输出，每层用小标题；每个关键判断后跟👉大白话一句。结尾总评一段 + "不构成投资建议"。'''

# ============ 六层深度分析器 DEEP6（2026-10-28 用户模型） ============
def _DEEP6_SYS_text():
    """六层深度分析系统提示词。"""
    return DEEP6_SYS


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
【一、输入数据与边界】只依据输入数据和产业链知识，不得虚构。字段缺失标"未取得/未知"。
【二、红线】建仓痕迹是概率证据，不是买入信号。当日涨幅>=7%或涨停的票一律不得进入 radar。禁止编造绝对量能数字。观察条件只能用"价格锚+相对量能"。
【三、硬门槛与过滤】涨幅红线、确认假信号、流动性枯竭直接excluded；现价<5日均线（含未站上5日线）的票不得进入radar，保留judged_all并注明「未站上5日线」（用户铁律：只做站上或回踩5日线企稳的票）；当日涨幅>=7%或涨停直接excluded。
【四、逐只研判·九问】手法归类 + 四模式匹配；突破日验收；回抽洗盘判定；建仓成本区 + 锚质量；板块题材共振；主线归属；二次突破与序列阶段；回踩买点五条；底层逻辑 + 题材催化 + 离场规则。
【五、质量评分表】锚质量、板块共振、利好新鲜度、洗盘质量、二次突破量型。质量分→观察优先级参考（非投资建议）。
【六、输出JSON】完整结构保持原样，radar最多3只，judged_all精简字段，全篇控制在合理字数，必须完整闭合。
【七、输出完整性铁律】输出必须是完整闭合的JSON，禁止截断。
'''


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
               'format': '按系统提示词逐只九问研判命中池，输出 meta/radar/judged_all/excluded 完整 JSON 对象（radar 最多5只）。'}
    t = ask_deepseek(payload, purpose='zforce_radar', system_text=ZSYS)
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
        radar = []
        for h in hits[:5]:
            _rb = h.get('res_bonus', 0)
            _qt = int(h.get('score_w') or h.get('score') or 0)
            radar.append({'code': h['code'], 'name': h['name'], 'method': h['method'],
                          'pattern_match': '不匹配', 'pattern_basis': 'LLM未输出，规则降级',
                          'sequence_stage': '找锚中',
                          'anchor_price': str(h.get('anchor') or ''), 'anchor_type': '未取得', 'anchor_quality_score': 0,
                          'cost_zone': str(h['anchor']), 'cost_basis': '规则降级：箱体' + str(h.get('box_low') or '') + '-' + str(h.get('box_high') or ''),
                          'breakout_check': {'verdict': '数据不足'}, 'washout_check': {'verdict': '数据不足无法判定'},
                          'second_breakout': {'done': False, 'volume_type': '数据不足'},
                          'pullback_check': {'five_conditions_met': [], 'time_window': '', 'verdict': '未到'},
                          'quality_score_detail': {'anchor': 0, 'sector_resonance': _rb, 'news_freshness': 0, 'washout': 0, 'second_breakout': 0},
                          'quality_total': _qt,
                          'observation_priority': '低', 'position_ref': '三分之一档参考（规则降级）', 'observation_priority_note': '仅作观察优先级参考，非投资建议',
                          'credibility': '中(规则降级)',
                          'theme': h.get('industry') or '未判',
                          'resonance': ('强' if _rb >= 15 else '中' if _rb >= 5 else '弱' if _rb else '未判'),
                          'bottom_logic': ('客观数据：现价' + str(h.get('price') or '') + '元，箱体'
                                           + str(h.get('box_low') or '') + '-' + str(h.get('box_high') or '')
                                           + '，评分' + str(h.get('score_w') or h.get('score') or '')
                                           + '，换手' + str(h.get('avg_turn') or '未取得')
                                           + '%。主营与产业链信息不在输入内，待LLM研判恢复。'),
                          'ignite_theme': h['industry'],
                          'exit_rule': '止损=收盘破' + str(h.get('falsify_line') or h.get('box_low') or '') + '元；止盈参考=锚+' + str(h.get('anchor') or '') + '元+8%（观察剧本，非投资建议）',
                          'next_watch': '①' + str(h.get('method') or '建仓痕迹') + '；②观察触发：放量突破' + str(h.get('box_high') or '') + '；③失效：跌破' + str(h.get('falsify_line') or '') + '元移出观察池',
                          'false_alarm_status': '数据不足无法判定', 'false_alarm_risk': '缺模型研判',
                          'rank_score': _qt, 'rank_reason': '规则降级按评分排', 'scan_score': int(h.get('score') or 0)})
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
    缩量回踩后启动+15 / 走势平稳+8。高位>100% 由风险扣分单独计，不重复扣。"""
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
        # 缩量回踩后启动：昨量≤前日量×0.95 且 昨收≥MA20×0.97 且 竞价放量 vr≥2
        closes = [float(r[2]) for r in bars[-21:-1]]
        ma20 = (sum(closes) / len(closes)) if len(closes) >= 20 else 0.0
        if v2 > 0 and v1 <= v2 * 0.95 and ma20 > 0 and c1 >= ma20 * 0.97 and vr >= 2.0:
            return 15.0, '缩量回踩启动'
        # 走势平稳：竞价分时代理「平稳」（高开适中+量比适中）
        sl, sh = (4.0, 6.0) if cyb else (2.0, 3.0)
        if sl <= gap < sh and 2.0 <= vr < 5.0:
            return 8.0, '走势平稳'
    except Exception:
        pass
    return 0.0, ''


def _auction_score_v3(s, heat, cnt, mem_days=None):
    """竞价 v3 综合分 = 量价五因子×0.72 + 题材分×0.28 − 风险扣分 + 反推修正。
    五因子对齐本地 auction_filter_widget._score_volume_price：
    高开幅度20 / 竞价量比(分钟归一)25 / 换手×量比情绪25 / 量能占比(竞价量/昨量)15 / 分时形态代理15。"""
    code = s['code']
    cyb = code.startswith(('300', '301'))
    sym = ('sh' if code.startswith('6') else 'sz') + code
    gap = max(0.0, s['pct'] or 0)
    # —— K线：一次拉 130 根（5日均量/昨量/60日区间/MA20 共用）——
    bars = None
    avg_vol5 = ref_vol = 0.0
    pos60 = None
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
    # —— 题材分（100，云端 heat 体系：热度60+同题材≥5家20+主线持续20）——
    ind = re.sub(r'[行业板块概念\s]+', '', s['industry']) or '其他'
    heat60 = min(60.0, heat.get(ind, 0.0) / 100.0 * 60.0)
    co20 = 20.0 if cnt.get(ind, 0) >= 5 else 0.0
    persist = 0.0
    if mem_days:
        for pd, pv in list(mem_days.items())[:3]:
            if ind in pv:
                persist = 20.0
                break
    theme_score_v = min(100.0, heat60 + co20 + persist)
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
    total = base * 0.72 + theme_score_v * 0.28 - risk + rv
    return round(total, 1)


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


def _auction_ds(tops, heat):
    """竞价深挖：每只 TOP 票题材+市场关联+主线多因素深挖（JSON）。返回 (per_map, overall)；失败 ({}, '') 渲染回退规则行。"""
    if not tops:
        return {}, ''
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
    payload = {
        'task': 'auction_top_deep',
        'stocks': [{'name': s['name'], 'code': s['code'], 'score': round(float(s['score']), 1),
                    'pct': s['pct'], 'industry': s['industry'],
                    'vr': round(float(s.get('_vr') or 0), 1), 'revise': round(float(s.get('_revise') or 0), 1),
                    'rtag': s.get('_rtag', '')} for s in tops],
        'hot_sectors': sorted(heat.items(), key=lambda kv: -kv[1])[:6],
        'holding_diagnosis': '\n'.join(hold_txt) or '无持仓',
        'format': ('你是A股竞价短线交易员。对以下每只竞价强票做「题材+市场关联」多因素深挖（禁止单条件结论）：\n'
                   '1. 题材归属：属于什么题材？是不是今日主线？题材里什么地位（龙头/中军/跟风/补涨）？\n'
                   '2. 板块共振：同题材几只一起动？真合力还是一只独涨？\n'
                   '3. 资金逻辑：量比/竞价量比/反推修正说明谁在抢？抢筹还是出货？\n'
                   '4. 位置与预期差：60日位置高低？有没有市场还没消化的东西（业绩预期/错杀修复/政策外溢/龙头扩散）？\n'
                   '5. 为什么值得看或不值得看，多因素交叉说清依据；数据不足以判断就直说。\n'
                   '6. 禁止编新闻猜消息、禁止万能句（「回踩分时均线可轻仓试」等）及变体、禁止满仓/必涨/稳了。\n'
                   '7. 只输出 JSON，不要其他文字：\n'
                   '{"overall":"竞价情绪一句话+今天能不能追+最强方向","per":[{"name":"股票名称","logic":"题材归属+市场关联深挖：题材是不是主线+地位+板块共振几只+资金逻辑+位置+预期差，为什么值得看/不看，多因素，至少40字，禁止单条件","why":"大白话：一句话戳穿真假+该不该追，至少20字，禁止万能句","op":"别追/看/轻仓试/观望","buy":"具体买点条件","stop":"具体止损条件"}]}，'
                   'per 必须覆盖我给的每只股票。'),
    }
    t = ask_deepseek(payload, purpose='auction', system_text=_ASK_DS_SYS_AC)
    if not t:
        return {}, ''
    overall = ''
    per = {}
    try:
        j = json.loads(t[t.find('{'):t.rfind('}') + 1])
        if isinstance(j, dict):
            overall = str(j.get('overall', '') or '')
            for it in (j.get('per') or []):
                nm = str(it.get('name', '')).split('（')[0].split('(')[0].strip()
                if nm:
                    per[nm] = {'logic': str(it.get('logic', '') or ''),
                               'why': str(it.get('why', '') or ''),
                               'op': str(it.get('op', '') or ''),
                               'buy': str(it.get('buy', '') or ''),
                               'stop': str(it.get('stop', '') or '')}
    except Exception:
        pass
    return per, overall


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


def _pre_ds(news):
    """盘前 DeepSeek 大白话总结：新闻→AI看多/看空板块 + 点名关注股（催化+新闻匹配）；失败返回 ''。"""
    if not news:
        return ''
    brief = [{'t': nw['title'], 's': (nw.get('summary') or '')[:60]} for nw in news[:12]]
    jc = judgment_context()
    t = ask_deepseek({'task': 'pre_news_summary', 'news': brief, 'judgment': jc,
                      'format': (_TRADER_RULES + '\n'
                                + (('昨日判断（开盘前先对照它，别重复昨天的错）：\n{judgment}\n' if jc else '昨日判断：无（今日首卡）\n')
                                   + '今日新闻（12条）：\n{news}\n'
                                   + '请严格按以下格式输出，不许加其他板块、不许打乱：\n'
                                   + '① 一句话总判断（今日情绪：强势/震荡/偏空/冰点 + 建议总仓位：空仓/1-2成/半仓 + 主基调：进攻/防守/观望/做分歧）\n'
                                   + '② 今日真正有价值的3-5个点（每个点=现象(数据)/含义/对比(与昨日或上周)/操作启示；只挑重要的）\n'
                                   + '③ 重点标的（最多3只；没有就写「今日无强推」并说明缺哪项共振）\n'
                                   + '每只格式：名称 代码 | 阶段(启动/中段/高位) | 共振x/4 | 为什么现在值得看(禁万能句) | 关键位置：支撑X/阻力X | 买入条件 | 放弃条件 | 仓位(仅1成试探/2成/半仓) | 唯一主风险\n'
                                   + '④ 今日最大风险（一句话）\n'
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
               + '先判断主力阶段（刚启动吸筹 / 拉升中 / 出货中 / 对倒中），再给操作。高位连板板块直接写「不接飞刀」。\n板块数据：\n' + lines + '\n'
               + '只输出 JSON：{"per":[{"name":"板块名(照抄)","logic":"主力阶段+为什么现在强/弱：驱动+资金+持续性判断(≥25字)","why":"大白话(≥20字，游资黑话优先)","act":"操作：追/低吸/看戏+条件(≥15字)"}]}，必须覆盖每个板块，推不出的如实说看不出来，不许硬编。')
    else:
        lines = '\n'.join(
            f"- {x['name']}({x['code']}) 板块「{x['sec']}」({x['sec_count']}家涨停) {x['lbc']}连板 涨{x['pct']:+.1f}% 量比{x['lb']:.1f} {'已封板' if x['sealed'] else '未封'}" + (f' 60日位置{x["pos"]*100:.0f}%' if x.get('pos') is not None else '')
            for x in items)
        fmt = ('你是一线游资，盘中看盘，对下面每只票点评（严格按主力游资五步铁律）：\n'
               + FIVE_BRIEF + '\n'
               + '每只票必须写：主力建仓痕迹有没有、上方筹码真空不真空、今天盘口托单还是砸盘、处于什么阶段。高位连板(lbc≥3)或60日位置>0.85强制「不碰」。\n涨停/强势股数据：\n' + lines + '\n'
               + '只输出 JSON：{"per":[{"name":"股票名(照抄)","logic":"建仓痕迹+筹码状态+驱动+暗雷(≥25字)","why":"大白话(≥20字)","op":"别追/轻仓试/看/观望(只能一个)","buy":"买入条件(≥12字)","stop":"止损条件(≥10字)","stage":"启动日|中段接力|末段高位|退潮反抽","verdict":"终审推荐|观察|不碰","evidence":["证据1","证据2"],"dark_risk":["解禁/减持/担保/业绩亏损等暗雷，无则写空数组"]}]}，dark_risk非空时verdict必须为「不碰」或「观察」；必须覆盖每只。')
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
               + '先判断：主力会不会借此点火，还是借机出货。act必须写「开盘后看哪些票的竞价和盘口托单」而不是直接给买入价。\n新闻：\n' + lines + '\n'
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
           + '只推有明显前期建仓痕迹、位置不高的票。共振不足3项或高位直接写「今日无买点」。\n个股：\n' + lines + '\n'
           + '只输出 JSON：{"per":[{"nm":"股票名(照抄)","stage":"启动/中段/高位","resonance":"满足共振几项(题材/资金/位置/买点, x/4)","plain":"为什么值得看/为什么别碰：建仓痕迹+逻辑深挖(≥30字)","tip":"操作建议：买点+止损+仓位档(仅1成试探/2成/半仓)(≥20字)；不满足3项共振或无建仓痕迹则写「今日无买点」"}]}，必须覆盖每只。')
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
                plain = f'{st.get("n")}已是{lbc}连板且处60日高位（{pos*100:.0f}%分位），情绪票顶格，别追，等放量分歧再看。'
            elif lbc >= 2:
                plain = f'{st.get("n")}已是{lbc}连板，{_hhmm(fbt_min) if fbt_min else "盘中"}封板，短线情绪核心；要接力等分时分歧低吸，不追板。'
            elif sec_count >= 3 and code == leader_code:
                plain = f'{sec}今天{sec_count}家涨停，{st.get("n")}最早封板（{_hhmm(fbt_min)}）是龙头；明天看板块续不续，回踩不破均线可跟。'
            elif sec_count >= 3:
                plain = f'{sec}今天{sec_count}家涨停，{st.get("n")}是跟风涨停；跟风只看龙头脸色，它别追。'
            elif sec_count == 1 and lb >= 2:
                plain = f'{sec}只有{st.get("n")}一只涨停+放量{lb:.1f}倍，疑似新方向点火；要等板块跟风出现才成立，先看别追。'
            elif lb >= 1.5:
                plain = f'{st.get("n")}放量{lb:.1f}倍上攻{pct:+.1f}%，资金真进场了；盯分时均线，回踩不破再动手，破了直接放弃。'
            elif lb < 0.5:
                plain = f'{st.get("n")}涨停但量比仅{lb:.1f}，缩量封板纯情绪，别碰。'
            else:
                plain = f'{st.get("n")}首板量能一般（量比{lb:.1f}），没量就没持续性，不碰。'
            seal_txt = ('已封板' if sealed
                        else ('放量上攻，回踩不破可看' if lb >= 1.5 else '量能一般，先观察'))
            rows += f"""<div style="background:#1f2635;border-left:3px solid {RED if sealed else TEAL};border-radius:8px;padding:8px 10px;margin:6px 0;">
<div style="font-size:14px;font-weight:700;color:#fff;">{n}. {st.get('n')} <span style="color:{GREY};font-size:12px;">{code}</span> <span style="color:{_c(pct)};font-weight:800;float:right;">{pct:+.1f}%</span></div>
<div style="color:{GREY};font-size:12px;">题材：{sec} ｜ 量比 {lb:.1f} ｜ {seal_txt}{f' ｜ {lbc}连板' if lbc >= 2 else ''}</div>
<div style="color:#ced4da;font-size:12px;margin-top:3px;">🧠 大白话：{plain}</div>{_llm_html}</div>"""
        if n > 10:
            break
    return rows or '<div style="color:' + GREY + ';font-size:13px;">今日无强势方向（多看少动）</div>'

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
        mark = (f' <span style="color:{RED};font-weight:700;">🆕 正在启动（{n_res}只共振）</span>'
                if n_res >= 3 else f'（已高位·最高{lbc_max}板，不追）')
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
    try:
        idx_txt = '、'.join(f"{x['name']}{x['pct']:+.2f}%" for x in idx) or '未取得'
        tops = '、'.join(f"{sec}({len(sts)}只)" for sec, sts in sorted(d['sectors'].items(), key=lambda kv: -len(kv[1]))[:5]) or '无'
        _g = load_position_gauge()
        _g_txt = (f'（当前仓位仪表盘：{_g.get("suggest", "")}，来自 {_g.get("source", "")}，不得与其矛盾）' if _g else '（仓位仪表盘未生成）')
        fmt = ('【主力游资五步铁律】先看筹码后说话，问三个主力问题，翻译成人话，套游资纪律，自查。\n'
               + '你是一线游资，基于以下盘中数据做整点解读，先判断市场是主力进攻还是主力出货环境，再给仓位。炸板率>45%时，op不得出现「轻仓试」，只能观察或防守。\n只输出 JSON：\n'
               + '{"overall":"现在盘面真正什么情况(用数据)+主力阶段，一句大白话+能不能做","emotion_score":0-100,"op":"该干什么：具体动作+仓位档(空仓/1成/2成/半仓)","risk":"最大风险+什么情况必须撤","next_watch":"下一小时最该盯的1个点"}\n'
               + '数据：指数 ' + idx_txt + '；涨停{d["lu"]}家 炸板{d["zb"]}家(炸板率{zbr*100:.0f}%) 跌停{d["dt"]}家 最高{d["max_lbc"]}板；情绪=' + b + '；最强板块 ' + tops + _g_txt + '\n炸板率>45% 时，op 不得出现「轻仓试」，只能观察或防守。')
        t = ask_deepseek({'task': 'hourly_ds', 'idx': idx_txt, 'tops': tops, 'b': b,
                          'lu': d['lu'], 'zb': d['zb'], 'dt': d['dt'], 'max_lbc': d['max_lbc'],
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
    # 操作建议（规则模板，用户口径）
    if b == '偏多':
        advice, ac = f'偏多进攻：总仓 {_pos_advice("偏多")}，只做主线前三题材，回踩不破均线可加。', TEAL
    elif b == '偏空':
        advice, ac = f'偏空防守：总仓 {_pos_advice("偏空")}，优先兑现高位股，不接飞刀。', GREEN
    else:
        advice, ac = f'震荡对待：总仓 {_pos_advice("震荡")}，严格不追高、不接力，只低吸主线。', GOLD
    # 当前最该注意的风险点（一句话）
    if b == '偏空':
        risk_line = f'风险点：炸板率{zbr*100:.0f}%/跌停{d["dt"]}家偏多，情绪走弱，警惕继续恶化。'
        rc = GREEN
    elif b == '偏多':
        risk_line = f'风险点：情绪偏暖但涨停{d["lu"]}家已多，谨防午后冲高回落、炸板扩散。'
        rc = GOLD
    else:
        risk_line = '风险点：轮动偏快，避免追高接力，炸板率升高时收手。'
        rc = GOLD
    _overall = (f'<div style="margin-top:4px;padding:8px 10px;background:#1c2830;border-left:4px solid {ac};'
                f'border-radius:8px;font-size:13px;color:#e9ecef;">🧭 今天整体：{b}，涨停{d["lu"]}家炸板{d["zb"]}家'
                f'（炸板率 {zbr*100:.0f}%），最高{d["max_lbc"]}板。→ 操作：{"偏多可进攻" if b=="偏多" else "偏空先防守" if b=="偏空" else "震荡控仓"}。</div>')
    _ds_block = _hourly_ds(idx, d, b, zbr)
    inner = f"""{_overall}
<div style="font-size:14px;">{bits}</div>
<div style="margin-top:6px;font-size:14px;">🔴涨停<b style="color:{RED}">{d['lu']}</b> 🟢炸板<b style="color:{GREEN}">{d['zb']}</b> 🟢跌停<b style="color:{GREEN}">{d['dt']}</b> 最高<b style="color:{GOLD}">{d['max_lbc']}板</b> ｜ 情绪 <b style="color:{_c(avg)}">{b}</b>（炸板率 {zbr*100:.0f}%）</div>
<div style="margin-top:4px;font-size:13px;">{breadth_sample()}</div>
<div style="margin-top:4px;font-size:13px;">{money_flow_note()}</div>
{_ds_block or '<div style="margin-top:8px;padding:10px;background:#1c2230;border-left:4px solid ' + ac + ';border-radius:8px;font-size:13px;font-weight:700;color:' + ac + ';">📌 操作建议：' + advice + '</div>'}
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
            out.append('美股均值%+.1f%%%s' % (avg, '（利空，防低开）' if avg <= -1 else ('（利好，可积极）' if avg >= 1 else '（中性）')))
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
    """② 今日主线方向 3 句（规则）：走势/驱动/最该盯的主线。"""
    if gl_avg <= -1:
        w1 = '今天大概率低开，防守优先：不追高、等情绪企稳再动手。'
    elif gl_avg >= 1:
        w1 = '隔夜外盘回暖，今天有望震荡向上，可积极找机会。'
    else:
        w1 = '外盘中性，今天以震荡为主，低吸不追高。'
    cats, _ = _cat_news(news)
    npol, nind, ncom, nint = (len(cats[k]) for k in ('政策/监管', '产业/行业', '公司大事', '国际/外围'))
    if npol + nind + ncom + nint == 0:
        w2 = '暂无增量驱动，跟随资金与情绪。'
    else:
        top = max(('政策面', npol), ('产业面', nind), ('公司业绩', ncom), ('外围因素', nint), key=lambda x: x[1])
        w2 = '核心驱动看' + top[0] + '（今日相关消息' + str(top[1]) + '条）。'
    tops = d.get('tops') or []
    if tops:
        sec, sts = tops[0]
        if sts:
            w3 = '今天最该盯：' + sec + '（昨日' + str(len(sts)) + '家涨停，看龙头' + sts[0]['n'] + '能不能续板）。'
        else:
            w3 = '今天最该盯：' + sec + '（昨日' + str(len(sts)) + '家涨停）。'
    else:
        w3 = '今天最该盯：昨日强势题材能否延续，多看少动。'
    return w1, w2, w3


def _sector_wind(d, news):
    """③ 板块风向标：强势2-3（为什么强+持续性）、弱势2-3（为什么弱+今天别碰）。"""
    strong = []
    for sec, sts in (d.get('tops') or [])[:3]:
        lu = len(sts)
        lead = sorted(sts, key=lambda x: -(int(x.get('lbc') or 0)))[0] if sts else None
        lbc = int(lead.get('lbc') or 0) if lead else 0
        if lu >= 8:
            cont = '家数多，大概率延续'
        elif lbc >= 2:
            cont = '龙头' + str(lbc) + '连板，有接力'
        else:
            cont = '首日点火，持续性待观察'
        strong.append((sec, ('昨日%d家涨停、龙头%s（%s）' % (lu, lead['n'], cont)) if lead else ('昨日%d家涨停' % lu)))
    weak = []
    for sec, sts in (d.get('worst') or [])[:2]:
        weak.append((sec, '跌停/炸板集中，今天别碰'))
    for nw in news[:12]:
        text = nw['title'] + ' ' + (nw.get('summary') or '')
        tag, _ = classify_news(text)
        if tag == '利空':
            for kws, sec, stocks, plain in NEWS_THEME_MAP:
                if any(k in text for k in kws) and sec not in [w[0] for w in weak]:
                    weak.append((sec, '利空消息（' + plain + '）'))
                    break
    return strong[:3], weak[:3]


def _goodbad_action(news):
    """⑤ 利好利空精选（行动版）：利好≤3、利空≤3，每条带板块/个股影响判断。"""
    good, bad = [], []
    for nw in news[:20]:
        text = nw['title'] + ' ' + (nw.get('summary') or '')
        tag, _ = classify_news(text)
        if tag not in ('利好', '利空'):
            continue
        if tag == '利好' and len(good) >= 3:
            continue
        if tag == '利空' and len(bad) >= 3:
            continue
        plain, sec = _plain_for(nw, '产业/行业')
        hit_stk = _stock_hits(text)
        impact = sec if sec else (hit_stk if hit_stk else '宏观/全市场')
        item = '<b>' + nw['title'][:38] + '</b> <span style="color:' + GREY + '">→ 影响：' + impact + '</span> ' + plain
        (good if tag == '利好' else bad).append(item)
    return good, bad


def _action_list(news, d, gl_avg):
    """⑥ 今日操作清单（核心）：可关注3-5（理由+仓位）、坚决回避3-5、持仓提示。"""
    watch = []
    for sec, sts in (d.get('tops') or [])[:5]:
        lead = sorted(sts, key=lambda x: -(int(x.get('lbc') or 0)))[0] if sts else None
        if lead:
            lbc = int(lead.get('lbc') or 0)
            if lbc >= 2:
                watch.append((lead['n'] + '（' + sec + '）', '昨日龙头' + str(lbc) + '板，题材' + sec + '共振', '轻仓试错 1~2 成'))
            else:
                watch.append((lead['n'] + '（' + sec + '）', '昨日' + sec + '领涨（' + str(len(sts)) + '家涨停），题材共振', '可关注 1~2 成试仓'))
    good, _ = _goodbad_action(news)
    for g in good[:3]:
        hit = _stock_hits(re.sub(r'<[^>]+>', '', g))
        if hit and not any(hit.split('、')[0] in w[0] for w in watch):
            watch.append((hit.split('、')[0], '新闻利好催化', '可关注 1~2 成试仓'))
    avoid = []
    bad_secs = _sector_wind(d, news)[1]
    for sec, why in bad_secs[:2]:
        avoid.append((sec, why))
    _, bad = _goodbad_action(news)
    for b in bad[:2]:
        hit = _stock_hits(re.sub(r'<[^>]+>', '', b))
        if hit:
            avoid.append((hit.split('、')[0], '利空消息回避'))
    hold_rows = [h['name'] + '（成本%.2f）' % h['cost'] for h in HOLDINGS]
    return watch[:5], avoid[:5], hold_rows


# ============ 盘前重点个股参考（小白友好版：昨收/题材/操作提示） ============
def _focus_stocks(d, news):
    """重点个股参考（FOCUS_N 只）：昨日主线龙头 + 新闻命中个股。只选真实数据，不编造。
    返回 [(name, code, prev_close, sector, plain, tip, role)]。"""
    out, seen = [], set()
    # ① 昨日涨停/连板池中主线龙头（有昨收价，角色=龙头）
    tops5 = {x[0] for x in d['tops'][:5]}
    for n, stocks in d['sectors'].items():
        if n not in tops5:
            continue
        for st in stocks[:1]:
            nm = st.get('n', '')
            if nm in seen or not nm:
                continue
            seen.add(nm)
            out.append((nm, st.get('c'), st.get('pc') or '—', n,
                        f'{n}昨天领涨，资金已验证。',
                        '今天看竞价是否高开3~5%且量比>2，可轻仓；低开超过2%先观望',
                        '龙头'))
            if len(out) >= FOCUS_N:
                return out[:FOCUS_N]
    # ② 新闻命中个股（NEWS_THEME_MAP 规则提取，角色=关注）
    for nw in news[:12]:
        text = nw['title'] + ' ' + (nw.get('summary') or '')
        for _kws, sec, stocks, plain in NEWS_THEME_MAP:
            for stk in (stocks or '').split('、'):
                stk = stk.strip()
                if not stk or len(stk) < 2 or stk in seen:
                    continue
                if stk in text:
                    seen.add(stk)
                    out.append((stk, '—', '—', sec, plain or '新闻催化', '看竞价强度，放量再跟', '关注'))
        if len(out) >= FOCUS_N:
            break
    return out[:FOCUS_N]


def build_pre():
    """盘前速递 08:30：今日操盘地图（外盘一句话→主线方向→板块风向→新闻四类→利好利空精选→操作清单）。"""
    gl = get_global()
    gl_avg = sum(p for _, _, p in gl) / max(len(gl), 1) if gl else 0.0
    news = get_news(20)
    d = get_pools()
    one = _global_one_line()
    w1, w2, w3 = _mainline_3(gl_avg, news, d)
    strong, weak = _sector_wind(d, news)
    cats, _ = _cat_news(news)
    _pre_news_map = _pre_news_deep(news)
    good, bad = _goodbad_action(news)
    watch, avoid, hold_rows = _action_list(news, d, gl_avg)
    ds_html = _pre_ds(news)
    # —— 渲染 ——
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
            else:
                plain, sec = _plain_for(nw, cat)
                _sec2 = sec
            tag, _tc = classify_news(nw['title'] + ' ' + (nw.get('summary') or ''))
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
<div style="color:#ced4da;font-size:12px;margin-top:3px;">🧠 {(_foc_map.get(nm) or {}).get("plain", "") or plain}</div>
<div style="color:{TEAL};font-size:12px;margin-top:3px;">👉 {(_foc_map.get(nm) or {}).get("tip", "") or tip}</div></div>"""
        )(nm, code, prev, sec, plain, tip, role)
        for nm, code, prev, sec, plain, tip, role in focus)
    focus_block = f'<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">⑤ 重点个股参考（{len(focus)}只）</div>{focus_rows}' if focus_rows else ''
    g_rows = ''.join('<div style="margin:5px 0;font-size:13px;">🟢 ' + g + '</div>' for g in good)
    b_rows = ''.join('<div style="margin:5px 0;font-size:13px;">🔴 ' + b + '</div>' for b in bad)
    w_rows = ''.join('<div style="margin:5px 0;font-size:13px;">✅ <b>' + nm + '</b> — ' + why + '｜<span style="color:' + GOLD + ';">仓位 ' + pos + '</span></div>' for nm, why, pos in watch)
    a_rows = ''.join('<div style="margin:5px 0;font-size:13px;">⛔ <b>' + nm + '</b> — ' + why + '</div>' for nm, why in avoid)
    h_rows = ''
    if hold_rows:
        h_rows = ('<div style="margin-top:8px;font-size:14px;font-weight:800;color:#ff922b;">▍已持仓提示</div>'
                  + ''.join('<div style="margin:4px 0;font-size:13px;">🏦 ' + h + ' — 持有观察，破位-3%再减</div>' for h in hold_rows))
    ds_block = ('<div style="margin-top:10px;padding:10px;background:#1c2230;border-left:4px solid ' + GOLD + ';border-radius:8px;">'
                '<div style="font-size:15px;font-weight:800;color:' + GOLD + ';">🤖 DeepSeek 大白话研判</div>' + ds_html + '</div>') if ds_html else ''
    inner = ("""<div style="margin-top:8px;font-size:15px;font-weight:800;color:#ff922b;">🧭 今日操盘地图｜方向 + 买什么 + 避开什么</div>
<div style="margin-top:8px;font-size:13px;color:#e9ecef;">🌏 隔夜外盘一句话：""" + one + """</div>
<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">② 今日主线方向（最重要）</div>
<div style="font-size:13px;color:#e9ecef;line-height:1.9;">1️⃣ """ + w1 + '<br>2️⃣ ' + w2 + '<br>3️⃣ ' + w3 + """</div>
<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">③ 板块风向标</div>
<div style="font-size:13px;color:""" + RED + ';">强势风向（可关注）</div>' + s_strong + """
<div style="margin-top:6px;font-size:13px;color:""" + GREEN + ';">弱势/回避（今天别碰）</div>' + s_weak + """
""" + focus_block + """
<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">⑥ 新闻汇总（四类打包，≤12条，每条带利好/利空）</div>""" + news_rows + """
<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">⑦ 利好利空精选（行动版）</div>
<div style="font-size:13px;color:""" + RED + ';">利好（≤3条）</div>' + (g_rows if g_rows else '<div style="font-size:13px;color:' + GREY + ';">今日暂无明确利好</div>') + """
<div style="margin-top:6px;font-size:13px;color:""" + GREEN + ';">利空（≤3条）</div>' + (b_rows if b_rows else '<div style="font-size:13px;color:' + GREY + ';">今日暂无明确利空</div>') + """
<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">⑧ 今日操作清单</div>
<div style="font-size:13px;color:""" + RED + ';">可关注/可低吸（3-5只）</div>' + (w_rows if w_rows else '<div style="font-size:13px;color:' + GREY + ';">今日无合适标的，多看少动</div>') + """
<div style="margin-top:6px;font-size:13px;color:""" + GREEN + ';">坚决回避（3-5只/板块）</div>' + (a_rows if a_rows else '<div style="font-size:13px;color:' + GREY + ';">今日暂无明确回避标的</div>') + h_rows + ds_block + """
<div style="margin-top:8px;color:""" + TEAL + """;font-size:13px;">👉 9:20 看竞价：高开 2~7%（创业 4~14%）+ 量比放量再买；低开直接小仓跟；破-3%走。</div>""" + build_events('pre') + pos_cap_line(_emotion_from_pools(d), None) + '"""')
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


def build_auction():
    """竞价观察 09:25（集合竞价最后阶段数据更可靠；数据延迟最多重试到 09:27，超时跳过不推空卡）：
    持仓竞价诊断 + 全市场涨幅榜→硬过滤→双重打分→TOP8 + 行业风向 + DeepSeek 大白话总结。"""
    # FIX18: 早触发等待——09:20-24 触发时等齐集合竞价(09:25)再取数，避免推数据不全的早卡
    _bj0 = _bj_now()
    if _bj0.hour == 9 and 0 <= _bj0.minute < 25:
        _wait = (_bj0.replace(hour=9, minute=25, second=0, microsecond=0) - _bj0).total_seconds()
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
            op = (q['open'] / q['prev'] - 1) * 100 if q['prev'] else 0
            vq_ratio = None
            try:
                arr = get_klines(h['code'], 2)
                if len(arr) >= 2 and float(arr[-2][5]) > 0 and q.get('vol'):
                    vq_ratio = (q['vol'] * 100) / float(arr[-2][5]) * 100
            except Exception:
                pass
            act, why = three_way(op, q.get('lb', 0), vq_ratio)
            _, ptag = _pos_risk(h['code'], q['price'])
            own.append(f"""<div style="background:#1f2635;border-left:3px solid {TEAL};border-radius:8px;padding:9px 11px;margin:6px 0;">
<b style="color:#fff;">🐉 {h['name']}</b> <span style="color:{_c(op)};font-weight:800;float:right;">开{op:+.1f}%</span>
<div style="color:{GREY};font-size:12px;">量比{q.get('lb',0):.1f}｜{act}{f'｜位置 {ptag}' if ptag else ''}<br>{why}</div></div>""")
        except Exception:
            continue
    own_block = (''.join(own) if own else '<div style="color:' + GREY + ';font-size:13px;">持仓行情未取得（腾讯快照失败），稍后看盘中解读</div>')
    own_section = (f'<div style="margin-top:8px;font-size:14px;font-weight:800;color:#ff922b;">🛡 持仓竞价诊断</div>{own_block}')
    # —— 数据拉取（09:29 硬截止，最多重试 6 次×20s；https/http 双通道）——
    bj = _bj_now()
    deadline = bj.replace(hour=9, minute=29, second=0, microsecond=0)
    rows_all = None
    for attempt in range(6):
        try:
            rows_all = _clist_gainers()
            if rows_all:
                break
        except Exception as e:
            print(f'[auction] 第{attempt+1}次拉竞价数据失败: {e}')
        if _bj_now() >= deadline:
            print('[auction] 09:29 已过且数据未就绪，本次跳过选股（保留持仓诊断）')
            return _wrap(own_section + '<div style="color:#e2e8f0;font-size:13px;margin-top:8px;">⚠️ 全市场竞价数据未按时就绪（09:29 超时），本次不筛选股票；持仓诊断照常。下一时段：10:00 盘中解读。</div>',
                         '🔔', '竞价观察')
        time.sleep(20)
    if not rows_all:
        return _wrap(own_section + '<div style="color:#e2e8f0;font-size:13px;margin-top:8px;">⚠️ 全市场竞价数据未取得，本次不筛选股票；持仓诊断照常。下一时段：10:00 盘中解读。</div>', '🔔', '竞价观察')
    # —— 全市场涨幅榜 → 硬过滤 → 双重打分 → TOP8 ——
    d = get_pools()
    zt_lbc = {}
    for sec, sts in d['sectors'].items():
        for st in sts:
            zt_lbc[st.get('c')] = int(st.get('lbc') or 0)
    cands = _auction_filter(rows_all, zt_lbc)
    heat, cnt = _theme_heat(cands)
    mem = load_memory()
    for s in cands:
        s['score'] = _auction_score_v3(s, heat, cnt, mem)
    cands.sort(key=lambda x: -x['score'])
    tops = cands[:AUCTION_TOP_N]
    ds_map, ds_overall = _auction_ds(tops, heat)
    try:
        _auction_pool_record(tops)
    except Exception:
        pass
    ds_block = (f"""<div style="margin-top:10px;padding:10px;background:#1c2230;border-left:4px solid {GOLD};border-radius:8px;">"""
                f"""<div style="font-size:15px;font-weight:800;color:{GOLD};">🤖 竞价深挖总结（大白话）</div><div style="color:#e9ecef;font-size:13px;">{ds_overall}</div></div>""") if ds_overall else ''
    emotion = _emotion_from_pools(d)
    pos_txt = _pos_advice(emotion)
    overall = (f'<div style="margin-top:4px;padding:8px 10px;background:#1c2830;border-left:4px solid {GOLD};'
               f'border-radius:8px;font-size:13px;color:#e9ecef;">🧭 今天整体：竞价情绪偏'
               f'{"多" if emotion=="偏多" else "空" if emotion=="偏空" else "震荡"}，建议仓位 {pos_txt}。'
               f'只看竞价，不追已经涨停的。</div>')
    rows = ''
    for i, s in enumerate(tops, 1):
        buy_low = round(max(0.0, s['price'] * 0.995), 2)
        buy_high = round(min(10.0, s['price'] * 1.01), 2)
        stop = round(buy_low * 0.97, 2)
        brk_txt = '站上昨收' if s['price'] > (s.get('prev') or 0) else '未站上昨收'
        _qiang = ('量价配合到位，资金抢得凶' if s['score'] >= 75 else '量价一般，能上别贪' if s['score'] >= 60 else '量价偏弱，随时可能砸')
        _deep = (ds_map or {}).get(s['name'])
        if _deep and _deep.get('logic'):
            _opcol = {'别追': RED, '轻仓试': TEAL, '看': GOLD, '观望': GREY}.get(_deep.get('op', ''), GOLD)
            _deep_html = (f"""<div style="color:#a78bfa;font-size:12px;margin-top:3px;">🧠 题材深挖：{_deep.get('logic','')}</div>
<div style="color:#e9ecef;font-size:12px;margin-top:2px;">👉 大白话：{_deep.get('why','')}</div>
<div style="color:#ced4da;font-size:12px;margin-top:2px;">🎯 操作：<b style="color:{_opcol};">{_deep.get('op','')}</b> ｜ 买点：{_deep.get('buy','')} ｜ 止损：{_deep.get('stop','')}</div>""")
        else:
            _deep_html = ''
        rows += f"""<div style="background:#1f2635;border-left:3px solid {GOLD if s['score'] >= 70 else TEAL};border-radius:8px;padding:9px 11px;margin:6px 0;">
<div style="font-size:14px;font-weight:700;color:#fff;">{i}. {s['name']} <span style="color:{GREY};font-size:12px;">{s['code']}</span> <span style="color:{GOLD};font-weight:800;float:right;">{s['score']:.0f}分</span></div>
<div style="color:{GREY};font-size:12px;">竞价高开 <b style="color:{_c(s['pct'])}">{s['pct']:+.2f}%</b> ｜ 量比 {s['lb']:.1f} ｜ 竞价量比(归一) {s.get('_vr', 0):.2f} ｜ 题材：{s['industry']}{f' ｜ <b style="color:{RED if s.get('_revise',0)<0 else TEAL}">{s.get('_rtag','')}{s.get('_revise',0):+.0f}</b>' if s.get('_rtag') else ''}</div>
{_deep_html or f"""<div style="color:#ced4da;font-size:12px;margin-top:3px;">🧠 大白话：{s['industry']}竞价高开{s['pct']:+.1f}%、量比{s['lb']:.1f}、{brk_txt}，{_qiang}。</div>
<div style="color:{TEAL};font-size:12px;margin-top:3px;">👉 建议：开盘30分钟站稳不破均线再动手（1成试探），买入区间 {buy_low}~{buy_high}，破 {buy_low} 的 -3% 止损</div>
<div style="color:#ced4da;font-size:12px;margin-top:2px;">🚫 放弃：跌破分时均线且量能萎缩，或低开超过2%先观望</div>"""}</div>"""
    # —— Top3 重点点评（v3）——
    top3_txt = ''
    if tops:
        def _quick_act(s_):
            bad = (s_.get('_rtag') or '') in ('暴力反抽', '无量反弹')
            if bad or s_['score'] < 60:
                return '不追', RED
            if s_['score'] >= 75:
                return '可轻仓试', TEAL
            return '观察', GOLD
        _t3 = []
        for i, s_ in enumerate(tops[:3], 1):
            _a, _col = _quick_act(s_)
            _t3.append(f'<b style="color:{_col}">{i}.{s_["name"]} {_a}</b>')
        top3_txt = (f'<div style="margin-top:10px;padding:9px 11px;background:#1c2830;border-left:4px solid #a78bfa;'
                    f'border-radius:8px;font-size:13px;color:#e9ecef;"><b>🎯 Top3 速判（小白版）：</b>{("　".join(_t3))}'
                    f'<br><span style="color:{GREY};font-size:12px;">≥75分可轻仓试 / 60~74观察 / &lt;60或暴力反抽、无量反弹不追</span></div>')
    try:
        _pool_prev = _auction_pool_stats()
    except Exception:
        _pool_prev = ''
    pick = f"""{top3_txt}<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">🎯 今日可关注 TOP{AUCTION_TOP_N}（量价×0.72+题材×0.28−风险+反推修正）</div>
{rows or '<div style="color:' + GREY + ';font-size:13px;">今日无符合硬过滤条件的竞价票（涨幅榜未取得或全被过滤）</div>'}{ds_block}{_pool_prev}"""
    # —— 行业/题材风向 ——
    hot = sorted(heat.items(), key=lambda kv: -kv[1])[:3]
    hot_txt = '、'.join(k for k, _ in hot) or '暂无'
    weak_lst = sorted(heat.items(), key=lambda kv: kv[1])
    weak_txt = (weak_lst[0][0] if weak_lst else '暂无')
    wind = (f"""<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">🌬️ 行业/题材风向</div>
<div style="font-size:13px;color:{RED};">• 最强（竞价涨幅前3题材）：{hot_txt}</div>
<div style="font-size:13px;color:{GREEN};">• 最弱：{weak_txt}（今天别碰）</div>""")
    # —— 竞价实盘确认（合并原 09:28：同一推送里直接复核高开/量能，数据同时点更可靠）——
    _confirm_block = ''
    try:
        _cinfos, _crows = [], []
        for s in tops[:5]:
            sym2 = ('sh' if s['code'].startswith('6') else 'sz') + s['code']
            q2 = _qt(sym2)
            if not q2 or not q2['prev']:
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
            if ok2:
                _crows.append(f'<div style="margin:4px 0;font-size:13px;background:#1c2830;border-left:3px solid {RED};border-radius:8px;padding:6px 10px;">✅ <b style="color:#fff;">{s["name"]}({s["code"]})</b> 高开{op2:+.1f}% 量比{lb2:.1f} → <span style="color:{RED};font-weight:800;">可跟 1成试探，止损-3%</span></div>')
            else:
                _crows.append(f'<div style="margin:4px 0;font-size:13px;background:#1f2635;border-left:3px solid {GREY};border-radius:8px;padding:6px 10px;">❌ {s["name"]}({s["code"]}) 高开{op2:+.1f}% 量比{lb2:.1f} → <span style="color:{GREY};">放弃（{why2}）</span></div>')
        _dmap2 = _confirm_ds(_cinfos)
        if _dmap2:
            _crows.append('<div style="margin-top:6px;padding:8px 10px;background:#1c2230;border-left:4px solid ' + TEAL + ';border-radius:8px;">'
                          + ''.join('<div style="color:#e9ecef;font-size:12px;margin:3px 0;">🧠 ' + nm + '：' + rz + '</div>' for nm, rz in _dmap2.items()) + '</div>')
        if _crows:
            _confirm_block = ('<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">🔔 竞价实盘确认（高开+量能复核，AI逐票深挖）</div>'
                              + ''.join(_crows))
    except Exception as e:
        print('[auction] 确认段失败:', e)
        _confirm_block = ''
    inner = (overall + f'<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">🔔 持仓竞价诊断（先看自己的）</div>'
             + (''.join(own) or '<div style="color:' + GREY + ';font-size:13px;">无持仓</div>')
             + pick + wind + pos_cap_line(emotion, None) + _confirm_block)
    return _wrap(inner, '🔔', '竞价观察')


def _confirm_ds(infos):
    """竞价确认 LLM 深挖：对 TOP5 每只输出 为什么能跟/为什么放弃（大白话五步）。失败返回 {}（保留原规则文案）。"""
    if not infos or not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return {}
    lines = '\n'.join(f"- {x['name']}({x['code']}) 高开{x['op']:+.1f}% 量比{'未取得' if not x.get('lb') or float(x.get('lb') or 0) <= 0 else ('%.1f' % x['lb'])} 题材{x['sec']} 判定={'可跟' if x['ok'] else '放弃'}（规则原因：{x['why']}）" for x in infos)
    fmt = ('你是10年A股超短线交易员，竞价确认阶段，对下面每只票逐一解释判定，不许只说"不在区间"：\n'
           + _FIVE_BRIEF_OLD + '\n'
           + '竞价名单：\n' + lines + '\n'
           + '【量比红线】量比标注"未取得"的票说明数据源没取到该字段，绝不得把"未取得"当作量比0来解读，更不得以量比不足为由否决它——只凭高开幅度/题材热度/位置判定；\n'

           + '只输出 JSON：{"per":[{"name":"股票名称","reason":"为什么能跟/为什么放弃(大白话深挖: 高开是否透支/量比真假/题材是不是当日主线/有没有暗雷)，至少25字"}]}，'
           + '必须覆盖每只，不许偷懒。')
    t = ask_deepseek({'task': 'confirm_ds', 'stocks': [{'name': x['name'], 'code': x['code'], 'op': x['op'],
                                                        'lb': x['lb'], 'sec': x['sec'], 'ok': x['ok']} for x in infos],
                      'format': fmt}, purpose='confirm_ds', system_text=_ASK_DS_SYS_AC)
    out = {}
    if not t:
        return out
    try:
        _j = json.loads(t)
        for it in _j.get('per') or []:
            nm = str(it.get('name') or '').strip()
            if nm and it.get('reason'):
                out[nm] = str(it['reason'])
    except Exception:
        pass
    return out


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
        return _wrap('<div style="color:#e2e8f0;font-size:13px;">今日竞价无符合硬过滤条件的票，多看少动</div>', '🔔', '竞价确认')
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
        return _wrap('<div style="color:#e2e8f0;font-size:13px;">今日竞价无确认标的，多看少动</div>', '🔔', '竞价确认')
    _dmap = _confirm_ds(infos)
    rows2 = list(rows)
    if _dmap:
        rows2.append('<div style="margin-top:6px;padding:8px 10px;background:#1c2230;border-left:4px solid ' + TEAL + ';border-radius:8px;">'
                     + ''.join('<div style="color:#e9ecef;font-size:12px;margin:3px 0;">🧠 ' + nm + '：' + rz + '</div>'
                               for nm, rz in _dmap.items()) + '</div>')
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
{''.join(f'<div style="margin:3px 0;font-size:12px;color:{GREY};">{life_badge(sec, d, mem, days)} {sec}（今日{len(st)}家·{life_cycle(sec, d, mem, days)[1]}）</div>' for sec, st in d['tops'][:3] if len(st) >= 1)}
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
            mf_note = f'主力净流入前5：{fin_r}；净流出前5：{fout_r}；' + ('净流入>净流出，真强概率大。' if net_total > 0 else '净流出占优，警惕诱多。')
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
           '2. 绝对禁止推荐千亿大票，流通市值必须严格控制在30亿到150亿之间（点名推荐前先自问这票流通盘够不够小）。\n'
           '3. 全文大白话，极简风格。单只票推演必须用一段话顺到底，字数控制在150字以内。\n'
           '4. 必须详细拆解「题材叠加共振」底牌，并自然揉入以下微观手法：\n'
           '庄家建仓手法：前期挖坑洗盘、缩量横盘熬底、打压吸筹痕迹、股东户数锐减。\n'
           '量化操作手法：盘口频繁拆单托单、脉冲式试盘、锯齿状织布机走势、直线90度点火。\n'
           '联动与情绪因子：上方筹码真空、老妖股记忆、龙虎榜游资接力、大盘跳水逆势抗跌。\n'
           '【执行流程】\n'
           '【盘面定调】用一两句话点明今天最强主线的龙头是否被通道党顶死，大资金现在在哪个新方向或细分领域做局。\n'
           '【核心埋伏标的】每只票严格按照一段大白话叙述，把底牌逻辑、微观盘口手法、龙头触发信号和买卖点无缝揉在一起。没有明显建仓痕迹的票不推。\n'
           '【观察池】列出2到3只备用观察标的（同样限制30到150亿流通盘）。用一句话说明它的题材逻辑以及在等什么信号才动手。\n'
           '【避风港与仓位】连贯陈述今天必须规避的高位断板风险和大资金流出的诱多板块。给出下午总仓位建议并说明理由。\n'
           '【自检】检查全文是否无问号无列表；流通盘是否在30到150亿之间；是否自然融入了庄家建仓与量化操作手法；买卖点止损是否明确。自检通过才输出。\n'
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
    """去重键：auction/pre/noon/warn 按天；hourly 按天+小时（10/11/13/14 各一次）。"""
    today = _bj_now().strftime('%Y-%m-%d')
    if slot == 'hourly':
        return 'hourly|%s|%02d' % (today, _bj_now().hour)
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
           + '只输出 JSON：{"per":[{"name":"板块名(照抄)","logic":"今天为什么强/弱：主力阶段+驱动+资金+持续性(≥25字)","why":"大白话(≥20字)","stage":"启动|接力|分歧|退潮","verdict":"明天能不能跟：跟/看/别追","tomorrow_act":"明天怎么跟：低吸/接力/看戏+条件(≥15字)"}]}，必须覆盖每个板块。')
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
                out[nm] = {k: str(it.get(k) or '') for k in ('logic', 'why', 'act', 'stage', 'verdict', 'tomorrow_act')}
                if not out[nm].get('act') and out[nm].get('tomorrow_act'):
                    out[nm]['act'] = out[nm]['tomorrow_act']
    except Exception:
        pass
    return out


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
    for n, s in d['tops'][:8]:
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
    _sec2_map = _sec2_deep(scored)
    sec2_rows = ''
    for n, s, sc, lv, old_leaders in scored:
        leader = sorted(s, key=lambda x: x.get('fbt') or 0)[0]
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
        fg_txt = '、'.join(fg) if fg else '暂无（量能未达标）'
        _dp2 = _sec2_map.get(n)
        _llm2 = ''
        if _dp2 and _dp2.get('why'):
            _llm2 = (f'<div style="color:#a78bfa;font-size:12px;margin-top:3px;">🧠 逻辑：{_dp2.get("logic", "")}</div>'
                     f'<div style="color:#e9ecef;font-size:12px;margin-top:2px;">👉 大白话：{_dp2.get("why", "")}</div>'
                     + (f'<div style="color:{GOLD};font-size:12px;margin-top:2px;">🎚️ 阶段：{_dp2.get("stage", "")} ｜ 结论：{_dp2.get("verdict", "")}</div>' if _dp2.get('stage') or _dp2.get('verdict') else '')
                     + (f'<div style="color:{TEAL};font-size:12px;margin-top:2px;">🎯 明天：{_dp2.get("act", "")}</div>' if _dp2.get('act') else ''))
        plain = ('资金还在往里涌，明天低开别慌，回踩可轻仓。' if lv == '强'
                 else '今天有资金但不算最强，明天只跟龙头，别追跟风。')
        sec2_rows += f"""<div style="background:#1f2635;border-left:4px solid {GOLD if lv=='强' else GREY};border-radius:10px;padding:10px 12px;margin:7px 0;">
<div style="font-weight:700;color:{GOLD};">{n} <span style="color:{RED};">{len(s)}涨停</span> <span style="color:{TEAL};">{sc}/10·{lv}</span></div>
<div style="color:#ced4da;font-size:13px;margin-top:4px;">👑 龙头：{leader.get('n')} {_hhmm(leader.get('fbt'))}封（封板最早，明天看回封或溢价）</div>
{f'<div style="color:{TEAL};font-size:12px;margin-top:3px;">📌 历史强势股：{"、".join(old_leaders)}</div>' if old_leaders else ''}
<div style="color:{TEAL};font-size:12px;margin-top:3px;">🔎 可跟踪跟风（未涨停量能放大）：{fg_txt}</div>
<div style="color:#ced4da;font-size:12px;margin-top:3px;">🧠 大白话：{plain}</div>{_llm2}</div>"""
    sec2 = f'<div style="margin-top:12px;font-size:15px;font-weight:800;color:#ff922b;">【今日主线 & 强势题材】（最多8条）</div>{sec2_rows}'
    sec2 += ''.join(f'<div style="margin:3px 0;font-size:12px;color:{GREY};">{life_badge(n, d, mem, days)} {n}（{life_cycle(n, d, mem, days)[1]}）</div>'
                    for n, s in d['tops'][:3] if len(s) >= 1)

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
        sec4_rows = '<div style="color:' + GREY + ';font-size:13px;">今日无合适跟踪票（全市场涨停或无量），明天多看少动</div>'
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
                   '【明日板块优先级】一句话（哪个 + 为什么 + 怎么跟）\n'
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
            _reson_sec = ('<div style="margin-top:10px;padding:10px 12px;background:#1a2029;border-left:4px solid #51cf66;border-radius:8px;font-size:13px;color:#e9ecef;">'
                          '<b style="color:#51cf66;">🎚 共振账本</b><br>' + _rb + _vd_txt + _acc_html + _al_html + '</div>')
    except Exception:
        _reson_sec = ''

    inner = (_overall + health_bar(idx, d, fin, fout) + sec1 + sec2 + sec4 + sec45 + sec5 + sec_ds + sec_sell + sec7
             + build_events('eod') + sec6 + _pool_today
             + pos_cap_line(sentiment(idx, d)[0], hl)
             + (f'<div style="margin-top:6px;font-size:12px;color:{GREY};">{_st_line}</div>' if _st_line else '')
             + _reson_sec + _miss_block)
    return _wrap(inner, '🌆', '收盘复盘')


BUILDERS = {'pre': build_pre, 'auction': build_auction, 'noon': build_noon,
            'eod': build_eod, 'hourly': build_hourly}
WATCH_SLOT = 'watch'
BUILDERS['confirm'] = build_confirm


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
            cards.append(_pb_llm or f"""<div style="background:#1c2830;border:2px solid {TEAL};border-radius:12px;padding:10px 14px;margin:10px 0;">
<div style="font-size:15px;font-weight:900;color:{TEAL};">🔁 回踩确认可加仓 · {nm}（{code}）</div>
<div style="color:#e9ecef;font-size:13px;margin-top:5px;">现价 {price:.2f} ≤ 均价×1.002，量比 {lb:.1f}≤1.2，回踩 {((price / trigger - 1) * 100):+.2f}% 不破买入区间下沿 {buy_low:.2f}</div>
<div style="color:{TEAL};font-size:12px;margin-top:4px;">操作：原仓位 +1成，止损不变（买入价-3%）</div></div>""")
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


_PIVOT_DS_SYS = ('你是一线游资，写「龙头情绪拐点·分歧转一致」分析。某龙头连板≥3、今日盘中炸板后回封（同时现身涨停池与炸板池），你要用大白话讲清楚：这是主力故意制造分歧洗盘，还是真出货？资金在干嘛、接下来怎么走、什么情况必须撤。只基于输入数据说话，禁编盘面；禁模板句；结论先行；坏消息不软化。只输出 JSON：{"logic":"分歧转一致意味着什么(≥25字,大白话,结合连板高度与炸板回封背景+主力意图判断)","risk":"后续风险与撤出条件(≥15字,给具体破位/炸板信号)"}，不要其他文字。')


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
            txt = (f'{nm} 连板{lbc}，【分歧转一致】同时现身涨停+炸板池，炸板后回封'
                   '（回封≤30min过滤：当天数据未提供该字段，如实标注），龙头情绪拐点')
            _pv_llm = _pivot_ds(nm, lbc)
            cards.append(_pv_llm or f"""<div style="background:#3a1c1c;border:2px solid {RED};border-radius:12px;padding:10px 14px;margin:10px 0;">
<div style="font-size:15px;font-weight:900;color:{RED};">👑 龙头情绪拐点 · {nm}</div>
<div style="color:#e9ecef;font-size:13px;margin-top:5px;">{txt}</div></div>""")
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
               + '【全球盘面】一句话（美股/商品/恒生，哪里强哪里弱）\n'
               + '【今晚大事】3-5条（从消息里挑真正重要的，每条=事实+对A股哪个板块有影响；消息里没有的直说）\n'
               + '【明天A股怎么看】拆成三行：\n'
               + '- 利好方向：最多1个板块 + 怎么应对\n'
               + '- 利空方向：最多1个板块 + 怎么应对\n'
               + '- 中性可忽略：…\n'
               + '【最大风险】一句话（若美股/商品反向，对应板块怎么处理）\n'
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
2. 【共振传导链】：why必须写完整三段——"龙头XX涨停封板 → 资金沿产业链/同题材外溢 → 它是下一个被盯上的，因为(位置低/贴5日线/有建仓痕迹/筹码真空，至少两条实证)"
3. 【低位优先 + 建仓痕迹优先】：龙头≥4板高位时，picks必须全是未涨停的低位有建仓痕迹的补涨票；无建仓痕迹的降为第二优先级或否决
4. 【禁止偷懒】：哪怕分数不高，也要挑出相对最值得埋伏的1-2只写全方案
每只候选输出字段(全必填)：name/code/rel/d5_read/why/confirm/buy/stop/grade/pos_score
picks最多3只；veto非空的候选不进picks。
━━━ 输出 JSON(不要其他文字) ━━━
{"board_health":{"leader":"...","seal":"...","sector":"...","window":"...","missed":"..."},"picks":[...],"risk":"..."}
━━━ 自检(输出前逐条过) ━━━
1. picks里是否混入了当日已涨停的票？有=作废重写
2. 龙头≥4板时picks是否全是低位未涨停且有建仓痕迹的票？
3. 每只候选的why是否有完整传导链？
4. confirm/buy/stop是否可观察、有具体价格？
5. 是否有万能句？有=改写
6. 是否与仓位仪表盘矛盾？
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



# ============ 突破回踩·主力成本锚（第3步：扫描→评分→过滤→渲染→推送） ============
ANCHOR_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


def _last_trade_date():
    """最近交易日（含今天；从今天往回找最多12天）：扫描器数据基准日。"""
    from datetime import timedelta
    d = _bj_now()
    for _ in range(12):
        if is_trading_day(d.strftime('%Y-%m-%d')):
            return d.strftime('%Y-%m-%d')
        d = d - timedelta(days=1)
    return _bj_now().strftime('%Y-%m-%d')


def _anchor_candidates(trade_date):
    """读当日扫描缓存（anchor_candidates_YYYYMMDD.json）；没有则现场跑扫描器。
    候选池=当日涨停池∪涨幅榜前400 → 六步验收（点火/突破/洗盘/二次突破/回踩/硬过滤）。"""
    cache = os.path.join(ANCHOR_CACHE_DIR, 'anchor_candidates_%s.json' % trade_date.replace('-', ''))
    if os.path.exists(cache):
        try:
            with open(cache, encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f'[anchor] 缓存读取失败，重新扫描: {e}')
    try:
        import anchor_break_retest_scanner as ABR
    except Exception as e:
        print(f'[anchor] 扫描器导入失败（不推送）: {e}')
        return []
    try:
        os.makedirs(ANCHOR_CACHE_DIR, exist_ok=True)
        cands = ABR.run_scanner(end_date=trade_date, limit=None, out=cache)
    except Exception as e:
        print(f'[anchor] 扫描异常（不推送）: {e}')
        return []
    return cands or []


def _anchor_plan(item):
    """由锚位自动派生可执行计划：买点/止损（大白话，仅供参考，不替代实盘判断）。"""
    ap = item.get('anchor_price')
    try:
        ap = float(ap)
    except (TypeError, ValueError):
        return '数据不足：锚价缺失，无法给出可靠价位'
    retest = item.get('retest_date')
    lo, hi = round(ap * 0.98, 2), round(ap * 1.02, 2)
    stop = round(ap * 0.97, 2)
    if retest and str(retest) not in ('', 'None', '未触发', 'null'):
        return (f"已回踩到锚位 {ap} 附近企稳（{lo}~{hi}）可轻仓介入；"
                f"放量跌破 {stop}（锚位下3%）即认错离场，不补仓。")
    return (f"尚未回踩：等股价回踩到锚位 {ap} 附近（{lo}~{hi}）缩量企稳再介入，不追高；"
            f"放量跌破 {stop}（锚位下3%）即放弃。")


def _anchor_risk(item, detail):
    """从评分理由里提炼真实风险点（洗盘偏多/天数偏久/板块弱/无消息等），不套模板。"""
    risks = []
    detail_txt = '；'.join(str(v) for v in (detail or {}).values())
    for kw, txt in (('次偏多', '洗盘段偏多/偏长'), ('偏久', '距突破天数偏久，动能可能已散'),
                    ('板块共振弱', '板块共振弱（跟风不足）'), ('板块共振缺失', '板块共振缺失'),
                    ('纯资金/概念', '无实质消息，纯资金/概念驱动'), ('无有效新闻', '无有效公告/新闻'),
                    ('二次突破缩量', '二次突破缩量'), ('巨量', '二次突破放量过猛')):
        if kw in detail_txt:
            risks.append(txt)
    if not risks:
        risks.append('评分各维度通过，仍需以回踩企稳/放量突破为执行前提')
    return '；'.join(risks[:3])


def _render_anchor(scored, trade_date=None):
    """深色 HTML 卡：总分+action+仓位+五维分数条+买点/止损+风险（手机端一行不换行过长）。"""
    if not scored:
        return None
    ac = {'执行': '#52c41a', '降仓': '#ffd43b', '轻仓试': '#66d9e8', '放弃': '#ff6b6b'}
    lines = [f'<div style="font-size:15px;font-weight:800;color:{GOLD};">🎯 突破回踩·主力成本锚（{len(scored)} 只达标）</div>',
             f'<div style="margin-top:2px;font-size:12px;color:{GREY};">数据日 {trade_date or "-"}：六步验收（点火→突破→洗盘→二次突破→回踩）→ 五维评分，只推 ≥50 分可操作票</div>']
    for it in scored:
        total = it.get('score_total', 0)
        action = it.get('action', '')
        acl = ac.get(action, '#9aa4b8')
        det = it.get('score_detail') or {}
        lines.append(f'<div style="margin-top:10px;padding:10px;background:#1c2230;border-left:4px solid {acl};border-radius:8px;">'
                     f'<div style="font-size:14px;color:#fff;font-weight:700;">{it.get("name","")}（{it.get("code","")}） '
                     f'<span style="color:{acl};font-size:15px;font-weight:800;">{total}分</span> '
                     f'<span style="color:{acl};font-size:12px;">{action}</span> '
                     f'<span style="color:{GREY};font-size:12px;">{it.get("position_suggest","")}</span></div>')
        stage = f'点火{it.get("ignition_date","")} → 突破{it.get("break_date","")}'
        if it.get('retest_date'):
            stage += f' → 回踩{it.get("retest_date","")}'
        else:
            stage += ' → 等待回踩'
        lines.append(f'<div style="margin:3px 0 0 2px;font-size:12px;color:{GREY};">🧭 锚位：{it.get("anchor_type","")} {it.get("anchor_price","")}（{stage}）｜板块共振 {it.get("sector_count","")} 只</div>')
        fiv = f'锚{it.get("score_anchor",0)} 板块{it.get("score_sector",0)} 利好{it.get("score_news",0)} 洗盘{it.get("score_wash",0)} 量型{it.get("score_volume",0)}'
        lines.append(f'<div style="margin:3px 0 0 2px;font-size:12px;color:{TEAL};">📊 评分：{fiv}</div>')
        ns = str(it.get('news_summary', '') or '').strip()
        if ns and '无' not in ns[:2]:
            lines.append(f'<div style="margin:2px 0 0 2px;font-size:12px;color:{GREY};">📰 消息：{ns[:60]}</div>')
        lines.append(f'<div style="margin:3px 0 0 2px;font-size:12px;color:#52c41a;">💰 计划：{_anchor_plan(it)}</div>')
        lines.append(f'<div style="margin:2px 0 0 2px;font-size:12px;color:{RED};">⚠️ 风险：{_anchor_risk(it, det)}</div>')
        lines.append('</div>')
    return _wrap(''.join(lines), '🎯', '突破回踩·主力成本锚')


def build_evaluate():
    """突破回踩·策略评估：先回填最近记录表现 → 评估/敏感性/建议 → 生成评估深色卡。返回 html 或 None。"""
    print('[evaluate] 策略评估开始')
    try:
        import strategy_evaluator as SE
    except Exception as e:
        print(f'[evaluate] 评估模块导入失败（不推送）: {e}')
        return None
    # 先回填最近记录表现（K线拉取失败自动跳过，不中断）
    try:
        import anchor_tracker as TR
        for doc in TR.load_history(days=20):
            d = doc.get('trade_date')
            if d:
                try:
                    TR.update_performance(d)
                except Exception as e:
                    print(f'[evaluate] 回填 {d} 异常（跳过）: {e}')
    except Exception as e:
        print(f'[evaluate] 回填环节异常（跳过）: {e}')
    try:
        html = SE.generate_eval_card(days=20)
    except Exception as e:
        print(f'[evaluate] 评估卡生成异常（不推送）: {e}')
        return None
    if not html:
        print('[evaluate] 无历史记录，不推送')
        return None
    return html


def build_review():
    """突破回踩·复盘：读最近记录 → K线回填后续表现 → 生成复盘深色卡。返回 html 或 None。"""
    print('[review] 复盘生成开始')
    try:
        import anchor_tracker as TR
    except Exception as e:
        print(f'[review] tracker 导入失败（不推送）: {e}')
        return None
    # 先给最近有记录的交易日回填表现（K线拉取失败自动跳过，不中断）
    for doc in TR.load_history(days=5):
        d = doc.get('trade_date')
        if not d:
            continue
        try:
            n = TR.update_performance(d)
            print(f'[review] 回填 {d}: {n} 只')
        except Exception as e:
            print(f'[review] 回填 {d} 异常（跳过）: {e}')
    try:
        html = TR.generate_review_card(days=5)
    except Exception as e:
        print(f'[review] 复盘卡生成异常（不推送）: {e}')
        return None
    if not html:
        print('[review] 无历史记录，不推送')
        return None
    return html


def build_anchor():
    """突破回踩全链路：扫描（读缓存）→ 评分 → 过滤≥50 → 渲染。返回 html 或 None。"""
    trade_date = _last_trade_date()
    print(f'[anchor] 数据基准日 {trade_date}')
    try:
        import quality_scorer as QS
    except Exception as e:
        print(f'[anchor] 评分模块导入失败（不推送）: {e}')
        return None
    raw = _anchor_candidates(trade_date)
    if not raw:
        print('[anchor] 扫描无候选，不推送')
        return None
    scored = QS.score_batch(raw)
    final = [c for c in scored if c.get('score_total', 0) >= 50]
    if not final:
        print(f'[anchor] 评分后无 ≥50 分票（{len(scored)} 只全部低于门槛），不推送')
        return None
    for c in final:
        print(f'[anchor] 达标 {c.get("code")} {c.get("name","")} {c.get("score_total")}分 {c.get("action","")}')
    # 第4步：推送内容落盘到跟踪档案（≥50分票），供后续复盘回填表现
    try:
        import anchor_tracker as TR
        _n = TR.record_candidates(final, trade_date)
        print(f'[anchor] 已记录 {_n} 只到跟踪档案')
    except Exception as e:
        print(f'[anchor] 记录跟踪档案失败（不阻断推送）: {e}')
    return _render_anchor(final, trade_date)




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
    news_brief = [{'t': nw['title'], 's': (nw.get('summary') or '')[:50]} for nw in news[:18]]
    # —— DS 大白话汇总 ——
    ds_html = ''
    if DEEPSEEK_KEY and news:
        fmt = (_TRADER_RULES + '\n'
               + '今日A股：{a_sec}\n'
               + '全球晚间行情：{markets}\n'
               + '今日+晚间消息（东财7x24）：\n{news}\n'
               + '把下面的今日A股、全球行情、今日+晚间消息消化后，用「朋友复盘聊天」式大白话总结，给用户今晚睡前能看懂、明天能用上的东西。\n'
               + '输出三段（全部说人话，禁模板句、禁「利好/利空XX板块」空话、禁条目式清单「1.2.3.」、禁照抄新闻标题）：\n'
               + '【今日大事】挑真正重要的3-5件事，每件说两层：今天到底发生了什么（一句话事实）+这句话翻译成人话意味着什么（讲清谁受益谁受伤、资金会往哪跑、为什么重要）；\n'
               + '【明日关注】2-3条，说人话：明天最可能发生什么、盯什么盘面信号、什么情况别碰；尽量与 eod「明日板块优先级」对齐，推翻要说明原因；\n'
               + '【最大风险】一句话大白话点破。\n'
               + '输出风格：短段落、短句，像微信群里交易员朋友聊天，一段最多两三行；没有值得说的就写「今日无大事，平稳过渡」并说原因。')
        t = ask_deepseek({'task': 'evening_summary', 'a_sec': a_sec, 'markets': markets_txt,
                          'news': news_brief, 'format': fmt}, purpose='evening')
        ds_html = md2html(t) if t else ''
    if not ds_html:
        print('[evening] LLM 未返回且已禁规则版兜底，不推晚间汇总')
        return None
    news_rows, _used_ds = _news_html_lines(news, n=12, purpose_key='eve_news', max_show=15)
    inner = (f'<div style="font-size:15px;font-weight:800;color:#ff922b;">🇨🇳 今日A股全景</div>' + a_sec
             + f'<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">🌐 全球晚间行情</div>'
             + _global_markets_html(gl)
             + (f'<div style="margin-top:10px;padding:10px;background:#1c2230;border-left:4px solid {GOLD};border-radius:8px;font-size:13px;line-height:1.8;color:#e2e8f0;">🤖 今日大事 & 明日关注：{ds_html}</div>' if ds_html else '')
             + f'<div style="margin-top:10px;font-size:15px;font-weight:800;color:#ff922b;">📰 今日消息汇总（按时间）</div>'
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
    good_pairs = _news_ds_lines(good, 6, 'news2h_good') or [(g.get('title',''), '', '', '') for g in good[:6]]
    bad_pairs = _news_ds_lines(bad, 6, 'news2h_bad') or [(b.get('title',''), '', '', '') for b in bad[:6]]

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
               + '【预期差】市场还没消化的1-2条（区分「已定价」与「未定价」；已定价禁止写成机会；没有写「今日无明显预期差，都是明牌」）\n'
               + '【怎么跟/怎么避】具体动作1-2条（结合利好利空说买什么、躲什么）\n'
               + '【明日操作建议】给明确仓位档位（用1-2成/2-4成/半仓/空仓这类明确数字）\n'
               + '【大白话总结】一句话（今天消息面对A股整体偏暖还是偏冷、最该记的一个点）')
        t = ask_deepseek({'task': 'news2h_summary',
                          'good': [g.get('title','')[:40] for g in good[:6]],
                          'bad': [b.get('title','')[:40] for b in bad[:6]],
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
           '只输出 JSON，不要任何其他文字，格式：\n'
           '{"items":[{"t":"消息标题","i":"影响：写清板块/题材，至少15字（猜不到写「暂看不出直接关联」，不许编）","s":"代表个股深挖：点名1-2只能代表这条消息的股票代码+名称，深挖它自己的逻辑（业绩/催化/位置/为什么它能代表），至少30字，不许泛泛而谈","w":"大白话：一句话戳穿真假+为什么+怎么传导，至少25字","a":"操作：买/躲/看，写具体怎么应对（价位/条件/仓位），至少20字"}]}\n'
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
    """信号强度等级：得分≥9 且触发∈{启动埋伏,老龙头回流}→S；得分≥7→A；其余→B。"""
    t = sg.get('type', '')
    if sg.get('score', 0) >= 9 and t in ('启动埋伏', '老龙头回流'):
        return 'S', '极强，可立刻小仓试'
    if sg.get('score', 0) >= 7:
        return 'A', '强，等回踩再上'
    return 'B', '观察为主'


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


def _watch_card(sg, mscore, ds_plain=None):
    """可操作信号卡（小白友好版）：强度等级 + 大白话理由 + 当前价/买入区间/止损 + 仓位 + 做T思路 + 风险提示。
    大白话优先 DS 动态生成（ds_plain），回退 sg['why'] 规则模板。"""
    st_lv, st_txt = _strength(sg)
    st_color = {'S': RED, 'A': GOLD, 'B': GREY}[st_lv]
    fit = ('情绪偏多/中性，可积极' if mscore >= 55 else '情绪偏弱，谨慎、仓位减半')
    t_tgt = sg.get('t_target', '冲高+3%~+5%')          # 做T目标（可配置常量 WATCH_T_TARGET）
    risk = sg.get('risk', '破位-3%无条件止损，不补仓。')
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
            _head_txt, _pos_txt, _buy_txt, _stop_txt, _act_txt, _t_tgt2 = (
                st_txt, sg.get('pos', '1-2成'),
                f"{sg.get('buy_low', '—')} ~ {sg.get('buy_high', '—')}",
                sg.get('stop', '破位-3%走'), sg.get('act', '观察'), t_tgt)
        _logic_html = ('<div style="color:' + TEAL + ';font-size:12px;margin-top:4px;">🧠 个股逻辑：' + _logic + '</div>') if _logic else ''
        _why_html = ('<div style="color:#e9ecef;font-size:12px;margin-top:2px;">👉 大白话：' + _why + '</div>') if _why else ''
        _ai_block = _logic_html + _why_html
    else:
        _head_txt, _pos_txt, _buy_txt, _stop_txt, _act_txt, _t_tgt2 = (
            st_txt, sg.get('pos', '1-2成'),
            f"{sg.get('buy_low', '—')} ~ {sg.get('buy_high', '—')}",
            sg.get('stop', '破位-3%走'), sg.get('act', '观察'), t_tgt)
        _why = _dsp if _dsp else sg.get('why', '')
        _ai_block = ('<div style="color:#e9ecef;font-size:12px;margin-top:2px;">👉 大白话：' + _why + '</div>') if _why else ''
    _t_line = (f'🎯 做T思路：{_t_tgt2} 附近可先出一半，留一半看能否冲击涨停。<br>🚫 若直接冲涨停：不追，等回封或明天。<br>'
               if _t_tgt2 else '')
    return f"""<div style="background:#2a1518;border:2px solid {RED};border-radius:12px;padding:12px 14px;margin:10px 0;">
<div style="font-size:17px;font-weight:900;color:{RED};">⚡ {sg['n']}（{sg['code']}）· {sg['type']} <span style="background:{st_color};color:#161b26;border-radius:6px;padding:1px 8px;font-size:12px;font-weight:700;">{_head_txt}</span></div>
<div style="color:#fff;font-size:13px;margin-top:6px;">所属题材：{(_dsp.get('theme') if _llm_ok and _dsp.get('theme') else sg['sec'])}｜得分 <b style="color:{GOLD}">{sg['score']}/10</b>{sg.get('life', '')}</div>
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


def _board_reverse_card(theme, prev_status):
    """↩️ 反向观察卡（退潮退出提醒，纯规则零 DS）。"""
    return f"""<div style="background:#1f2635;border:2px solid {RED};border-radius:12px;padding:12px 14px;margin:10px 0;">
<div style="font-size:13px;color:{RED};font-weight:800;">↩️ {theme} 已进入退潮期（此前为{prev_status}）</div>
<div style="color:#e9ecef;font-size:13px;margin-top:4px;">退潮信号：龙头炸板 / 板块红盘不足 2 只 / 资金明显撤离。</div>
<div style="margin-top:8px;padding:8px 10px;background:#2a1f22;border-left:4px solid {RED};border-radius:8px;font-size:13px;color:{RED};">
建议操作：持仓者先减仓观望；观察列表里暂时移出，等重新出现 ≥3 只共振再回来。<br>
别在退潮期抄底（容易接飞刀）。</div>
<div style="color:{GREY};font-size:12px;margin-top:6px;">纯规则判断（零 DS）｜ 之前推过该题材正面卡，信号已反转</div></div>"""


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
    """统一极致深度逻辑模板（小白友好，六段不可再细）：
    ①为什么看这个板块 ②为什么选这只 ③现在/明天能不能买 ④买入区间+仓位+止损 ⑤目标与做T ⑥放弃条件。
    s 为涨幅榜行（含 role 可选）；eod_kind='低吸候选'/'冲高做T' 时走「明天低吸/做T」口径。"""
    role = s.get('role', ('低吸候选' if eod_kind == '低吸候选' else '冲高做T') if eod_kind else '跟风')
    cur = float(s.get('price') or 0)
    if cur > 0:
        buy_low = round(cur * 0.995, 2)
        buy_high = round(cur * 1.01, 2)
        stop = round(buy_low * 0.97, 2)
        buy_txt = f'买入区间：回踩分时均线 {buy_low}~{buy_high} 可轻仓 1-2 成，止损 {stop}（-3%）'
    else:
        buy_low = buy_high = stop = 0.0
        buy_txt = '买入区间：回踩分时均线附近可轻仓 1-2 成，止损 -3%'
    why_sec = (f'{sec}今天{fzn}只同步放量（量比≥1.5）、板块共振，资金集中进场。'
               if fzn and fzn >= 2 else f'{sec}今日放量活跃。')
    why_stock = {'龙头': '板块涨幅最高且超次高3pp，资金主攻对象、弹性最大',
                 '中军': '板块第二强，放量最稳、跟龙头最紧',
                 '跟风': '补涨角色，位置低，龙头继续走它就补涨',
                 '并列领涨': '板块多只并列走强，它属于领涨梯队',
                 '低吸候选': '没涨停但量能明显放大+题材在今日主线里，明天可低吸埋伏',
                 '冲高做T': '今天大涨但没封住，分时强势，明天可冲高做T'}.get(role, '')
    if eod_kind:
        # 明天口径：③ 明天能不能买；⑤ 目标按 低吸/做T 区分
        canbuy = '✅ 明天可以买：低开 -1%~-2% 可轻仓低吸；高开>3% 放弃（做T空间被透支）'
        tgt = ('🎯 目标：回封或冲高 +3% 做T（低吸候选，吃到反弹就跑）' if eod_kind == '低吸候选'
               else '🎯 目标：冲高 +3%~+5% 做T（大涨未封板，冲高先出一半）')
        abandon = '🚫 放弃：高开超过 3% 不追，板块整体转弱立刻放弃、不补仓'
    else:
        canbuy = ('✅ 可以轻仓试（现价在买入区间内 + 板块共振≥3只）'
                  if (fzn or 0) >= 3 and cur > 0 and cur <= buy_high
                  else '⏳ 先观察，别急（现价还没回踩到买入区间，或共振不足 3 只）')
        tgt = '🎯 目标：冲高 +3%~+5% 先出一半做T，留一半看能否冲击涨停'
        abandon = '🚫 放弃：跌破分时均线且量比掉到 1.5 以下，或同题材共振掉到 2 只以下，立刻走、不补仓'
    return (f'① 为什么看板块：{why_sec}\n'
            f'② 为什么选这只：{role}——{why_stock}\n'
            f'③ {"现在" if not eod_kind else "明天"}能不能买：{canbuy}\n'
            f'④ {buy_txt}\n'
            f'⑤ {tgt}\n'
            f'⑥ {abandon}')


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
        _st_txt = (f'<br>🎚️ 阶段：{_b.get("stage","")} ｜ 持续依据：{_b.get("sustain","")} ｜ 真启动需共振：{_b.get("min_confirm","")}只' if (_b.get('stage') or _b.get('sustain') or _b.get('min_confirm')) else '')
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
            _v_txt = (f'<br>🏷️ 角色：{_d.get("role","")} ｜ 受益：{_d.get("real_benefit","")} ｜ 结论：<b style="color:{RED if _d.get("verdict")=="不碰" else (TEAL if _d.get("verdict")=="终审推荐" else GOLD)};">{_d.get("verdict","")}</b> ｜ 阶段：{_d.get("stage","")} ｜ 共振：{_d.get("resonance","")}/4' if (_d.get('verdict') or _d.get('stage') or _d.get('resonance')) else '')
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
                follow_rows += f"""<div style="background:#1f2635;border-left:3px solid {GOLD};border-radius:8px;padding:9px 11px;margin:6px 0;">
<div style="font-size:14px;font-weight:700;color:#fff;">{i + 1}. {s['name']} <span style="color:{GREY};font-size:12px;">{s['code']}</span> <span style="color:{_c(s['pct'])};font-weight:800;float:right;">+{float(s.get('pct') or 0):.1f}%</span></div>
<div style="color:#ced4da;font-size:12px;line-height:1.7;margin-top:4px;">{deep_html}</div></div>"""
            else:
                follow_rows += (f'<div style="font-size:13px;color:#e9ecef;margin:2px 0;">{i + 1}. {s["name"]} '
                                f'<span style="color:{GREY};font-size:12px;">{s["code"]}</span> '
                                f'<span style="color:{_c(s["pct"])};font-weight:700;">+{float(s.get("pct") or 0):.1f}%</span>'
                                f'<span style="color:{GREY};font-size:12px;">（未涨停·等回踩，别急）</span></div>')
    else:
        follow_rows = '<div style="color:' + GREY + ';font-size:13px;">板块在动但都接近涨停，暂无未涨停可跟票——等回踩或明天，别追高。</div>'
    leader = next((s for s in stocks if s.get('role') == '龙头'), None)
    leader_txt = leader['name'] if leader else '板块龙头'
    watch_risk = (f'<div style="margin-top:10px;padding:9px 11px;background:#1c2830;border-left:4px solid {GOLD};border-radius:8px;font-size:13px;color:#e2e8f0;">'
                  f'<b>下一步盯什么（风控信号）：</b>👉 {leader_txt} 炸板 或 共振掉到 3 只以下 → 整个板块先减仓观望；量比保持放大则可拿。<br>'
                  f'🚀 启动后观察窗口：30 分钟内看龙头封单与共振数，失守即减仓。</div>')
    ds_html = _board_ds(board, mscore)
    ds_block = (f'<div style="margin-top:10px;padding:10px;background:#232a3a;border-left:4px solid #a78bfa;'
                f'border-radius:8px;font-size:13px;line-height:1.8;color:#e2e8f0;">🤖 DS 大白话总结：{md2html(ds_html)}</div>'
                if ds_html else '')
    exhausted = ('<div style="color:' + GREY + ';font-size:12px;margin-top:4px;">📴 今日 DS 额度已用，以上为规则判断（数据真实、不伪造）。</div>'
                 if _DS_EXHAUSTED else '')
    _conf_txt = {'高': '置信度高（数据源正常）', '中': '置信度中（缓存数据）', '低': '置信度低（数据异常）'}.get(confidence, '')
    _html = f"""<div style="background:#1f2635;border:2px solid {GOLD};border-radius:12px;padding:12px 14px;margin:10px 0;">
<div style="font-size:13px;color:#e9ecef;margin-bottom:6px;">🧭 今天整体：情绪{mlabel}（{mscore}分），{_cap_txt(mscore, mlabel)}。先看板块，别追已涨停。</div>
<div style="font-size:13px;color:{RED};font-weight:800;">🚀 为什么现在看这个板块</div>
<div style="color:#e9ecef;font-size:13px;margin-top:4px;">{sec} 今日 <b style="color:{GOLD}">{board['fzn']} 只</b>同时放量上涨（涨幅≥2.5% 且 量比≥1.8），资金开始集中涌入、板块共振确认。<span style="color:{GREY};font-size:12px;">（{_conf_txt}）</span></div>
{_why_html}
<div style="margin-top:10px;font-size:14px;font-weight:800;color:{TEAL};">共振确认（已启动的 {board['fzn']} 只）</div>{conf_rows}
<div style="margin-top:10px;font-size:14px;font-weight:800;color:{TEAL};">可跟（未涨停，按顺序优先级）</div>{follow_rows}
{watch_risk}
{ds_block}{exhausted}
<div style="color:{GREY};font-size:12px;margin-top:6px;">市场{mlabel}（{mscore}分）｜ 只跟未涨停、严格止损</div></div>"""
    _payload = _board_payload('启动卡', confidence, sec,
                              f'{sec} 今日 {board["fzn"]} 只同时放量（涨幅≥2.5%且量比≥1.8），共振确认（{_conf_txt}）',
                              lifecycle, stocks, '资金集中涌入、板块共振确认',
                              f'龙头 {leader_txt} 炸板或共振<3只 → 先减仓观望；止损固定 -3%，只跟未涨停',
                              _VERIFY_NODES, data_source, board.get('dirty', []), _html)
    _append_push(_payload)     # 推送快照落盘（仅在推送路径调用；测试环境已打桩 git）
    return _html


_BOARD_WATCH_DS_SYS = ('''A股盘中主力意图反推与大白话作战指令 V3.0
一、你的角色
你是一名有丰富A股超短线实战经验的一线游资盘中决策助手。
你的工作不是罗列行情，不是复述新闻，而是根据当日真实行情，反推主力正在做什么（吸筹/洗盘/拉升/出货/对倒），并将研判转化为明确、可执行、可验证的交易条件。
你只解决五个问题：
1. 今天能不能做？（主力进攻还是出货环境）
2. 主力真正围绕什么题材和业务交易？
3. 谁是龙头，谁可能是有独立强度的龙二、龙三，谁只是跟风炮灰？
4. 哪只票满足条件后可以买，具体什么价格触发，什么情况必须放弃？
5. 如果判断错误，最先出现什么危险信号，应该如何处理？
最终输出必须使用自然、直接的大白话。
二、强制执行：先核实数据，再做判断
（保持原数据红线：只用真实数据、区分盘中/收盘、已涨停票不进可买名单、不预测明日涨跌等）
三、第一步：用大白话判断今天的市场环境（主力进攻意愿）
先回答："今天这行情，主力是在进攻，还是在出货？"
计算市场情绪分（权重保持原结构），但解读时优先看主力行为。
一票否决规则保持，触发后直接写"不能开新仓"。
四、第二步：反推主力到底在炒什么
必须回答：主力围绕的具体业务是什么？为什么进入前排？哪些股票先动？是龙头带动还是跟风？当前属于启动/加速/分歧/退潮？
五、第三步：拆解龙头、龙二、龙三与跟风
每只股票核实：谁最先启动、谁成交额更大、谁有建仓痕迹、谁只是跟风。角色定义保持，但增加"有无明显建仓痕迹"判断。
六、第四步：把研判变成具体的交易条件
只有同时满足条件才允许进入可买名单：当日未涨停、情绪/阶段允许、涨幅符合环境限制、量比合理、价格回到支撑、分时结构OK、有建仓痕迹或筹码优势。
七、第五步：风险和仓位必须算清楚
（保持原风险预算与仓位计算逻辑）
八、最终输出：交易员大白话作战简报
严格按照原十一段结构输出，但所有判断必须带「主力意图」视角。已涨停股票只放热度证据，不列入买入候选。没有符合条件的标的时明确写"当前无符合条件的买入标的"。
九、强制自检
（保持原12条自检，并增加：是否每只可买票都检查了建仓痕迹/筹码状态？）
最终原则：先判断主力值不值得跟，再研究做哪只票；先反推主力，再验证买点；先确定失效条件，再讨论仓位。宁可明确说没有机会，也不制造虚假的交易机会。
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
        _res_note = '（共振C档：空仓等，不新开仓）'
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
    _conf_txt = {'高': '置信度高（数据源正常）', '中': '置信度中（缓存数据）', '低': '置信度低（数据异常）'}.get(confidence, '')
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
    _why_rule_html = (f'<div style="color:#e9ecef;font-size:13px;margin-top:4px;">{sec} 今日 <b style="color:{TEAL};">{board["fzn"]} 只</b>放量达标（涨幅≥2.5% 且 量比≥1.5）进入观察池，大模型暂不可用，详细逻辑盘中再推。<span style="color:{GREY};font-size:12px;">（{_conf_txt}）</span></div>')
    _why_html_final = _why_llm_html
    _cand_html = ''
    if candidates:
        _cand_items = []
        for _c in candidates[:5]:
            _tp = _c.get('type', '候选')
            _cand_items.append(f'<b>{_c.get("name", "")}</b>（{_c.get("pct", 0):+.1f}% / 量比{_c.get("lb", 0):.1f} / {_tp}）→ 买：回踩分时均线或开盘价企稳；触发：量比维持、站上昨收；止损：破成本-3%；仓位：1成试探')
        _cand_html = '<br>'.join(_cand_items)
    else:
        _cand_html = '今日无可介入候选：等第 3 只共振出现、或龙头回踩企稳后再动手。'
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
                _v_txt = (f'<br>🏷️ 角色：{_d.get("role","")} ｜ 受益：{_d.get("real_benefit","")} ｜ 结论：<b style="color:{RED if _d.get("verdict")=="不碰" else (TEAL if _d.get("verdict")=="终审推荐" else GOLD)};">{_d.get("verdict","")}</b> ｜ 阶段：{_d.get("stage","")} ｜ 共振：{_d.get("resonance","")}/4' if (_d.get('verdict') or _d.get('stage') or _d.get('resonance')) else '')
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
                              f'{sec} 今日 {board["fzn"]} 只同步放量（量比≥1.5），板块初步共振（{_conf_txt}）',
                              lifecycle, stocks, '量能放大、板块初步共振', 
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


_LINK_DS_SYS = ('你是一线游资，写「板块联动确认」提示。某题材今日多只个股同时达标共振（同题材≥3只放量，领涨股已确认），你要用大白话讲清楚：板块共振确认意味着主力开始扩散做板块、资金在干嘛、接下来重点盯什么失败信号。只基于输入数据说话，禁编；禁模板句；结论先行。只输出 JSON：{"logic":"板块共振确认意味着什么(≥25字,大白话,结合家数与领涨股+主力意图)","risk":"接下来要盯的失败信号(≥12字,给具体量价条件)"}，不要其他文字。')


def _link_ds(sec, n, lead):
    """联动确认 LLM 大白话（失败 '' → 调用方回退规则文案）。"""
    if not MODELSCOPE_KEY:
        return ''
    try:
        fmt = ('板块「' + sec + '」今日 ' + str(n) + ' 只达标（共振确认）' + ('，' + lead + ' 领涨' if lead else '')
               + '。只输出 JSON：{"logic":"板块共振确认意味着什么(≥25字,大白话,结合家数与领涨股,禁模板句)","risk":"接下来要盯的失败信号(≥12字,给具体量价条件)"}，不要其他文字')
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
                                    [], '资金明显撤离', '持仓者减仓观望；别在退潮期抄底',
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
                                                board['stocks'], '资金明显撤离',
                                                '持仓者先减仓观望；别在退潮期抄底',
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
            sg['why'] = (f'{name}今天{len(stocks)}只同时放量上涨（涨幅都还不到5%），'
                         f'资金提前进场、板块共振，属启动早期信号。'
                         + ('轮动期只观察别追。' if mlabel == '快速轮动' else '可轻仓跟最强者。'))
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
                sg['why'] = f'{sec}上次强势股{nm}今天重新放量上攻（量比{st.get("lb", 0):.1f}），老题材资金回流，历史已验证。'
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
    sel = new_cards[:max_cards]
    for _, sg in sel:
        sg['life'] = life_badge(sg.get('sec', ''), d, mem, days)  # 模块8 生命周期徽标
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
            link_cards += (_lk_llm or f"""<div style="background:#1c2830;border:2px solid {TEAL};border-radius:12px;padding:10px 14px;margin:10px 0;">
<div style="font-size:15px;font-weight:900;color:{TEAL};">🔄 联动确认</div>
<div style="color:#e9ecef;font-size:13px;margin-top:6px;">{sec} 今日已 {n} 只达标{f'（{lead} 领涨）' if lead else ''}，板块共振确认，重点跟踪龙头</div></div>""")
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
    return _wrap(f'<div style="color:{RED};font-size:14px;font-weight:700;">⏰ {_bj_now().strftime("%H:%M")} 盘中异动 · 市场{mlabel}({mscore}分)</div>{cards}{link_cards}{pb}{hr}{piv}{pos_cap_line(emotion, None, mscore)}',
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
    return ('你是一位在A股盘中有10年以上实战经验的一线游资，最擅长用大白话讲盘。你的任务：基于我给的「涨停池实时快照」，严格按主力游资五步铁律输出——先看筹码后说话，问三个主力问题，翻译成人话，套游资纪律，自查。\n'
            '强制规则：1. 只许用我给的数据说话，不许编造新闻。2. 全程大白话。3. 操作只给：别追 / 看 / 轻仓试 / 观望 / 持仓不动。4. 禁止万能句。5. 【底层核心逻辑·硬要求】每只新进票必须按这条逻辑链深挖：公司主业（翻译成人话）→题材关联（实受益/沾边/纯蹭）→建仓痕迹与筹码状态→资金本质→催化验证→暗雷。高位连板直接不碰。6. 只输出 JSON：\n'
            '{"overall":"情绪一句话+能不能追","mainline":"今日最强方向+还能不能跟","risk":"最大风险+什么情况立刻撤","per":[{"name":"股票名称","theme":"真实题材名","logic":"底层核心逻辑：主业+题材关联+建仓痕迹/筹码+资金本质+催化+暗雷，至少55字","why":"大白话：一句话戳穿真假，至少18字","op":"别追/看/轻仓试/观望——必须与logic一致","buy":"买点具体条件","stop":"止损具体"}]}，per必须覆盖每只新进票。')


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
                   '按【底层核心逻辑链】输出：①公司主业(一句人话)②题材关联(实受益/沾边/纯蹭)③资金本质(龙头/订单/摘帽/低价/情绪，可引用 fund_wan 资金流入)④催化验证(news)⑤暗雷。\n'
                   '{"overall":"情绪一句话+能不能追","mainline":"今日最强方向+还能不能跟","risk":"最大风险+什么情况立刻撤","per":[{"name":"股票名称","theme":"真实题材名","stage":"启动日|中段接力|末段高位|退潮反抽","verdict":"终审推荐|观察|不碰","evidence":["证据1","证据2"],"logic":"公司主业+题材关联+资金本质+催化+暗雷，至少55字，禁止只讲盘面高位、禁止固定比喻充当逻辑","why":"大白话，至少18字，比喻只能收尾一句","op":"别追/看/轻仓试/观望","buy":"买点具体条件","stop":"止损具体"}]}，'
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
    out = {'overall': None, 'per': {}, 'mainline': None, 'risk': None}
    names_set = set(names)
    try:
        import json as _json
        _j = _json.loads(txt)
        out['overall'] = str(_j.get('overall') or '') or None
        out['mainline'] = str(_j.get('mainline') or '') or None
        out['risk'] = str(_j.get('risk') or '') or None
        for it in _j.get('per') or []:
            nm = str(it.get('name') or '').strip()
            nm = nm.split('（')[0].strip()
            if nm in names_set:
                out['per'][nm] = {'logic': str(it.get('logic') or ''), 'why': str(it.get('why') or ''),
                                  'op': str(it.get('op') or ''), 'buy': str(it.get('buy') or ''),
                                  'stop': str(it.get('stop') or ''), 'theme': str(it.get('theme') or ''),
                                  'stage': str(it.get('stage') or ''), 'verdict': str(it.get('verdict') or ''),
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
    can_chase = ('可以看但别追高' if mood in ('升温', '平稳偏强') else
                 '先管住手' if mood in ('降温', '警惕退潮') else '等确认再动')
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
        print('[intra] DS 不可用/失败，回退规则模板', '（额度用尽）' if _DS_EXHAUSTED else '')
    mood_line = (f'<div style="color:#e9ecef;font-size:13px;">{mood_emoji} 情绪定性：{mood}'
                 f'（涨停 {prev_lu}→{d["lu"]}，炸板率 {zb_rate*100:.0f}%'
                 f'{f"，跌停 {d['dt']} 只（新增）" if dt_new else ""}）</div>')
    if ds and ds.get('overall'):
        mood_line += f'<div style="color:{GREY};font-size:12px;">👉 AI 大白话：{ds["overall"]}</div>'
    else:
        mood_line += f'<div style="color:{GREY};font-size:12px;">👉 大白话：涨停{("变多" if dl>=0 else "变少")}、炸板率{("高=有人亏钱，热而乱" if zb_rate>=0.4 else "低=大家齐心")}，{can_chase}。</div>'
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
            if grp >= 3:
                why = f'{sec}板块 {grp} 只齐动，资金合力（板块行情，不是它一只的事）'
            elif lbc >= 4:
                why = '连板资金博弈，情绪票，涨的是人气不是业绩'
            else:
                why = '就它一只在涨（独立炒作，可能是消息驱动也可能是游资一日游）'
            if lbc >= 4:
                op, op_col = '别追', RED
            elif pos60 is not None and pos60 > 0.85:
                op, op_col = '观望', GOLD
            elif grp >= 3 and fbt and fbt <= '0945':
                op, op_col = '轻仓', TEAL
            elif grp >= 3:
                op, op_col = '看', TEAL
            else:
                op, op_col = '看（不主动荐）', GOLD
            if lbc >= 4 or (pos60 is not None and pos60 > 0.85):
                buy, stop = '无（高位不接）', '不参与'
            elif ma5 and near5:
                buy, stop = f'回踩5日线（{ma5:.2f}）附近可轻仓试', f'跌破5日线（{ma5:.2f}）'
            elif ma5:
                buy, stop = '等板块分歧，不追高', '-5%'
            else:
                buy, stop = '等板块分歧', '-5%'
        rows.append(
            '<div style="background:#1f2635;border-left:3px solid ' + op_col + ';border-radius:8px;padding:8px 10px;margin:6px 0;">'
            + '<div style="font-size:13px;font-weight:700;color:#fff;">' + name + '（' + code + '）｜' + (dsp.get('theme') if isinstance(dsp, dict) and dsp.get('theme') else sec) + '｜<span style="color:' + RED + ';">' + lb_txt + '</span>' + fbt_txt + '</div>'
            + (('<div style="color:' + TEAL + ';font-size:12px;margin-top:2px;">🧠 个股逻辑：' + _logic + '</div>') if _logic else '')
            + '<div style="color:' + GREY + ';font-size:12px;">👉 ' + ('AI 大白话' if dsp else '大白话') + '：' + why + '。</div>'
            + '<div style="color:#ced4da;font-size:12px;">操作：<b style="color:' + op_col + ';">' + op + '</b> ｜ 买点：' + buy + ' ｜ 止损：' + stop + '</div></div>')
    new_block = ('<div style="margin-top:8px;font-size:14px;font-weight:800;color:#ff922b;">🆕 新进涨停 ' + str(len(new_xs)) + ' 只（增量，只讲新的）</div>'
                 + ''.join(rows)
                 + ('<div style="color:' + GREY + ';font-size:12px;margin-top:4px;">另有 ' + str(rest_n) + ' 只首封（' + '、'.join(x.get('n', '') for x in new_xs[5:8]) + ' 等），不逐一展开。</div>' if rest_n else ''))
    # —— 主线归纳（DS 优先，模板回退）——
    from collections import Counter as _C
    cnt_new = _C(x.get('hybk') or '其他' for x in new_xs)
    top_main = cnt_new.most_common(2)
    if ds and ds.get('mainline'):
        main_line = ('<div style="margin-top:8px;font-size:14px;font-weight:800;color:#ff922b;">🧵 今日主线</div>'
                     f'<div style="color:#e9ecef;font-size:13px;">{ds["mainline"]}</div>') if new_xs else ''
    else:
        main_parts = []
        for sec, n in top_main:
            tot = sec_cnt.get(sec, 0)
            if tot >= 3:
                main_parts.append(f'{sec}（新进 {n} 只，板块共 {tot} 只齐涨，真·板块合力）')
            else:
                main_parts.append(f'{sec}（新进 {n} 只，板块仅 {tot} 只，合力不足谨防一日游）')
        main_line = ('<div style="margin-top:8px;font-size:14px;font-weight:800;color:#ff922b;">🧵 今日主线</div>'
                     f'<div style="color:#e9ecef;font-size:13px;">{"；".join(main_parts) if main_parts else "暂无聚类（新进票题材零散）"}</div>') if new_xs else ''
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
               f'<div style="color:{RED};font-size:13px;">{"、".join(hi_txt + pos_hi)} 高位，随时可能闷杀，看戏（保护你不接最后一棒）。</div>') if (hi_txt or pos_hi) else ''
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
        disc = '管住手，等共振确认再动'
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
每天开盘后或盘中，先问自己三个问题，并用当天真实数据回答：
谁在动？真正有资金在动手的是哪个板块？是主线还是支线？是龙头在动还是跟风在动？有没有建仓痕迹？
为什么动？是因为资金提前进场，还是因为消息刺激，还是因为情绪扩散？
动到哪一步了？是刚启动、中段加速、末段高潮，还是已经开始退潮？
这三个问题回答不清楚，就直接输出「今日暂无明确启动预警」，绝不硬写。
二、早期信号的评分因子（用自己的交易经验权衡）
资金层（最重要）、龙头层（是否有建仓痕迹、位置是否还低）、结构层、情绪与位置层。
三、阶段判断硬标准（启动/中段加速/末段高潮/退潮）
四、输出时必须遵守的认知结构：结论先行 → 因果链显影 → 决策接口（触发条件+动作+失败出口）
五、绝对禁止的行为：没有数据支撑就编信号；用无法验证的空话；输出「满仓」「必涨」；同一句话换票名复用。
六、最终输出原则
信号不够强 → 直接回复「今日暂无明确启动预警」
有信号 → 用最接地气的大白话，把结论、原因、操作三件套说清楚
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


def _warn_news_ds(items):
    """08:20 消息面点火预判 LLM：新闻→可能被点燃的板块→个股→点火逻辑→开盘验证→风险。失败返回 ''。"""
    if not items or not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return ''
    # hold：持仓名（data/holdings.json 可选），供 LLM 判断「点火板块与持仓的关系」；无持仓写暂无
    _hs = _load_holdings()
    hold = '、'.join(str(h.get('name') or '') for h in _hs) if _hs else '暂无持仓'
    news_txt = '\n'.join(f"- {x['title']}（摘要：{x['summary'][:60]}）" for x in items[:15])
    fmt = ('你是一线游资，现在是开盘前08:20，手里只有隔夜和当天的新闻，没有盘中数据。\n'
           '任务：判断哪些板块今天可能被消息面点火启动。严格按主力游资五步铁律：\n'
           + FIVE_BRIEF + '\n'
           + '先判断主力最可能选哪类票（低位有建仓痕迹的）作为点火点。\n新闻列表：\n' + news_txt + '\n'
           + '只输出 JSON：{"fire":[{"sector":"可能被点燃的板块(≥8字)","stocks":"相关个股(没有写无，别硬编)","logic":"为什么会被点燃：消息→板块→资金传导逻辑+主力可能选什么类型的票(≥30字)"}]}\n'
           + 'fire 最多5个。推不出就写"今日消息面无明确点火板块"，不许硬凑。\n'
           + 'JSON 另加 "news_brief":[{"t":"新闻原标题","p":"一句话大白话研判(≤40字)：说清这条消息可能利好/利空哪个方向、主力会不会借题发挥"}]，对新闻列表逐条给。')
    t = ask_deepseek({'task': 'warn_news_ds', 'news': items[:15], 'format': fmt}, purpose='warn_news_ds')
    return t if t else ''


def _warn_render_fire(_j, items=None):
    """渲染点火预判 JSON；items 为新闻列表时先出「今日新闻速览」。"""
    out = []
    # 新闻速览：优先 LLM 大白话研判（news_brief），LLM 没给时降级只显示标题（不拼摘要，防重复两遍）
    _nb = (_j.get('news_brief') or []) if isinstance(_j, dict) else []
    _news_brief = []
    if _nb:
        for _n in _nb[:15]:
            _t = str(_n.get('t') or '').strip()
            _p = str(_n.get('p') or '').strip()
            if _t:
                _line = f'<div style="color:#e9ecef;font-size:12px;margin:4px 0;line-height:1.5;">• {_t[:44]}</div>'
                if _p:
                    _line += f'<div style="color:#a78bfa;font-size:12px;margin:1px 0 4px 10px;line-height:1.5;">💬 {_p[:60]}</div>'
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
        for i, f_ in enumerate(fire[:5], 1):
            _conf = f_.get('confidence', '')
            _conf_txt = ('★' * int(_conf)) if str(_conf).isdigit() else ''
            out.append(f"""<div style="background:#1c2830;border-left:3px solid {RED};border-radius:8px;padding:9px 11px;margin:6px 0;">
<div style="font-size:13px;font-weight:700;color:#fff;">{i}. {f_.get('sector','')} <span style="color:{GREY};font-weight:400;">｜相关个股：{f_.get('stocks','无')}</span> <span style="color:{GOLD};">{_conf_txt}</span></div>
<div style="color:#a78bfa;font-size:12px;margin-top:2px;">🧠 点火逻辑：{f_.get('logic','')}</div>
<div style="color:{TEAL};font-size:12px;margin-top:2px;">🔍 开盘验证：{f_.get('verify','')}</div>
<div style="color:{GREEN};font-size:12px;margin-top:2px;">⛔ 失败则：{f_.get('fail_if','')}</div>
<div style="color:{GREEN};font-size:12px;margin-top:2px;">⚠️ 风险：{f_.get('risk','')}</div></div>""")
    avoid = _j.get('avoid') or []
    if avoid:
        out.append('<div style="font-size:14px;font-weight:800;color:' + GREEN + ';margin-top:6px;">🚫 消息面要避开的</div>')
        for a_ in avoid[:3]:
            out.append(f"""<div style="font-size:12px;color:#c8d0e0;margin:3px 0;">• {a_.get('sector','')}：{a_.get('logic','')}</div>""")
    if _j.get('hold'):
        out.append('<div style="font-size:13px;color:' + GOLD + ';margin-top:8px;">📌 持仓联动：' + str(_j['hold']) + '</div>')
    return ''.join(out)


def _warn_rule_fallback(items):
    """LLM 失败回退：规则 news_tags 汇总利好板块（不空推）。"""
    hot = {}
    for nw in items:
        sector, stocks, plain = news_tags(nw.get('title', ''), nw.get('summary', ''))
        if sector and sector != '宏观/全市场':
            hot[sector] = hot.get(sector, 0) + 1
    if not hot:
        print('[warn] 规则兜底也无明确板块，不推送')
        return None
    hot_sorted = sorted(hot.items(), key=lambda kv: -kv[1])[:3]
    rows = ''.join(f'<div style="font-size:13px;color:#e9ecef;margin:4px 0;">🔥 {k}（{v}条相关新闻）</div>' for k, v in hot_sorted)
    inner = ('<div style="color:' + RED + ';font-size:14px;font-weight:700;">🚨 今日消息面板块预警（规则版，AI未返回）</div>'
             + '<div style="color:' + GREY + ';font-size:12px;">开盘前按当日新闻归集的热点板块，仅供开盘参考：</div>' + rows)
    return _wrap(inner, '🚨', '启动预警'), '【消息面预警】' + _bj_now().strftime('%H:%M')


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
            items.append({'title': t[:80], 'summary': s[:90]})
        if len(items) >= 15:
            break
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
    t = _warn_news_ds(items)
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

TITLES = {'pre': '盘前速递', 'auction': '竞价观察', 'noon': '午间作战', 'eod': '收盘复盘',
         'news': '事件简报', 'news2h': '两小时市场消息汇总',
          'hourly': '盘中解读', 'warn': '启动预警', 'confirm': '竞价确认', 'ext': '外盘窗口', 'anchor': '突破回踩', 'review': '突破回踩·复盘', 'evaluate': '突破回踩·策略评估'}


BUILDERS['warn'] = build_warn
BUILDERS['ext'] = build_ext
BUILDERS['anchor'] = build_anchor
BUILDERS['review'] = build_review
BUILDERS['evaluate'] = build_evaluate



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
    """同一休市日只推送一份汇总（去重键=日期）。"""
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
    """休市日新闻 LLM 五步深挖：批量生成 板块题材/利好利空/大白话/操作。失败返回 {}（回退规则 news_tags）。"""
    if not items or not (MODELSCOPE_KEY or DEEPSEEK_KEY):
        return {}
    news_txt = '\n'.join(f"- {x['title']}（摘要：{x['summary'][:50]}）" for x in items[:10])
    fmt = ('你是一线游资，休市日新闻汇总，对每条新闻严格按主力游资五步铁律深度挖掘，不许偷懒：\n'
           + FIVE_BRIEF + '\n'
           + '休市日只做情报收集，操作统一写「开盘后验证主力是否借消息动手」，禁止直接给买入价。\n新闻列表：\n' + news_txt + '\n'
           + '只输出 JSON：{"items":[{"t":"标题(照抄)","sector":"板块题材(至少8字，猜不到写「暂看不出直接关联」)","stocks":"相关个股(没有写无)","good":"✅利好什么(至少8字，无则写无明显直接利好)","bad":"⚠️利空什么(至少8字，无则写无明显直接利空)","why":"大白话(一句话戳穿+怎么应对，至少20字)","act":"操作(休市日统一写「开盘后验证条件」，禁止直接给买入价)"}]}，必须覆盖每条新闻。')
    t = ask_deepseek({'task': 'holiday_ds', 'news': [{'title': x['title'], 'summary': x['summary'][:60]} for x in items[:10]],
                      'format': fmt}, purpose='holiday_ds')
    out = {}
    if not t:
        return out
    try:
        _j = json.loads(t)
        for it in _j.get('items') or []:
            tt = str(it.get('t') or '').strip()
            if tt and (it.get('why') or it.get('sector')):
                out[tt] = {'sector': str(it.get('sector') or ''), 'stocks': str(it.get('stocks') or ''),
                           'good': str(it.get('good') or ''), 'bad': str(it.get('bad') or ''),
                           'why': str(it.get('why') or ''), 'act': str(it.get('act') or '')}
    except Exception:
        pass
    return out


def build_holiday_news():
    """休市日新闻汇总：仅当天实际获取到的新闻 → 标题/来源/时间/摘要/利好利空/板块题材个股/大白话。

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
    items = []
    for nw in today_news:
        title = nw.get('title', '').strip()
        summary = nw.get('summary', '').strip()
        ts = str(nw.get('ts') or '')
        src = nw.get('source') or '东财7x24'
        if not title and not summary:
            continue
        sentiment, color = classify_news(title + ' ' + summary)
        sector, stocks, plain = news_tags(title, summary)
        tag_html = ''
        _d = _deep_map.get(title) if _deep_map else None
        if _d:
            _sec2 = _d.get('sector') or sector
            _stk2 = _d.get('stocks') or stocks
            _gd = _d.get('good') or ''
            _bd = _d.get('bad') or ''
            _wh2 = _d.get('why') or plain
            _ac2 = _d.get('act') or ''
            tag_html = (f'<div style="color:{TEAL};font-size:12px;margin-top:3px;">🏷️ 板块题材：{_sec2}'
                        f'｜相关个股：{_stk2}</div>')
            if _gd:
                tag_html += (f'<div style="color:{RED};font-size:12px;margin-top:2px;">✅ 利好：{_gd}</div>')
            if _bd:
                tag_html += (f'<div style="color:{GREEN};font-size:12px;margin-top:2px;">⚠️ 利空：{_bd}</div>')
            if _wh2:
                tag_html += (f'<div style="color:#e2e8f0;font-size:12px;margin-top:2px;">🗣️ 大白话：{_wh2}</div>')
            if _ac2:
                tag_html += (f'<div style="color:{GOLD};font-size:12px;margin-top:2px;">💡 操作：{_ac2}</div>')
        else:
            if sector:
                tag_html = (f'<div style="color:{TEAL};font-size:12px;margin-top:3px;">🏷️ 板块题材：{sector}'
                            f'｜相关个股：{stocks}</div>')
            if plain:
                tag_html += (f'<div style="color:#e2e8f0;font-size:12px;margin-top:3px;">'
                             f'🗣️ 大白话：{plain}</div>')
        items.append(f"""<div style="background:#1f2635;border-left:3px solid {color};border-radius:8px;padding:9px 11px;margin:7px 0;">
<b style="color:#fff;">【{sentiment}】{title or '（无标题）'}</b>
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
    """休市日统一处理：只发当天新闻汇总（去重/源失败不推）。返回 True 表示已处理（调用方应退出）。"""
    today = _bj_now().strftime('%Y-%m-%d')
    if news_push_done(today):
        print(f'SLOT {slot} 休市日新闻汇总今日已推送（去重），跳过')
        return True
    html, _ = build_holiday_news()
    if html is None:
        print(f'SLOT {slot} 休市日新闻源失败，不推送空壳')
        return True
    ok, msg = push(html, f'📰 休市日新闻汇总 {today}')
    if ok:
        mark_news_push_done(today)
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
    alias = {'morning': 'pre', 'pre': 'pre', 'auction': 'auction', 'hourly': 'hourly',
             'noon': 'noon', 'midday': 'noon', 'eod': 'eod', 'close': 'eod'}
    slot = alias.get(slot, slot) if slot else None
    if not slot:
        h = datetime.utcnow().hour
        slot = {0: 'pre', 1: 'auction', 2: 'hourly', 3: 'noon',
                5: 'hourly', 6: 'hourly', 7: 'eod'}.get(h, 'eod')
    # —— 演示模式（--demo-all）：跳过休市闸门/去重/静默，轮流构建核心槽位并推送。仅显式参数触发，不影响定时任务 ——
    if '--demo-all' in args or (force and force and force.startswith('demo-')):
        demo_items = [('盘前速递', build_pre), ('竞价观察', build_auction), ('盘中解读', build_hourly),
                      ('午间作战', build_noon), ('收盘复盘', build_eod), ('两小时汇总', build_news2h),
                      ('晚间汇总', build_evening), ('跟涨三步走', lambda: build_followup()[0]),
                      ('事件汇总', lambda: _wrap(build_events('noon' if _bj_now().hour < 14 else 'eod'), '📰', '事件汇总')),
                      ('异动提醒', build_watch), ('突破回踩·主力成本锚', build_anchor), ('突破回踩·复盘', build_review), ('突破回踩·策略评估', build_evaluate)]
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
        for name, fn in demo_items:
            try:
                html = fn()
            except Exception as e:
                skipped.append(f'{name}(异常:{str(e)[:60]})')
                continue
            if not html:
                skipped.append(f'{name}(无数据)')
                continue
            ok, msg = push(html, f'【演示】{name} · 轮流试跑')
            (sent if ok else skipped).append(name if ok else f'{name}({str(msg)[:40]})')
            print(f'[demo] {name} PUSH', ok, msg)
        print('[demo] sent:', sent, '| skipped:', skipped)
        sys.exit(0)

    if slot == 'anchor':
        try:
            _ah = build_anchor()
        except Exception as e:
            print('[anchor] build exception:', e)
            _ah = None
        if _ah is None:
            print('SLOT anchor: 无可推候选或构建失败，不推送')
            sys.exit(0)
        ok, msg = push(_ah, f'突破回踩·主力成本锚 {_bj_now().strftime("%H:%M")}')
        print('SLOT anchor PUSH', ok, msg)
        sys.exit(0)


    if slot == 'review':
        try:
            _rv = build_review()
        except Exception as e:
            print('[review] build exception:', e)
            _rv = None
        if _rv is None:
            print('SLOT review: 无历史记录或构建失败，不推送')
            sys.exit(0)
        ok, msg = push(_rv, f'突破回踩·复盘 {_bj_now().strftime("%H:%M")}')
        print('SLOT review PUSH', ok, msg)
        sys.exit(0)


    if slot == 'evaluate':
        try:
            _ev = build_evaluate()
        except Exception as e:
            print('[evaluate] build exception:', e)
            _ev = None
        if _ev is None:
            print('SLOT evaluate: 无历史记录或构建失败，不推送')
            sys.exit(0)
        ok, msg = push(_ev, f'突破回踩·策略评估 {_bj_now().strftime("%H:%M")}')
        print('SLOT evaluate PUSH', ok, msg)
        sys.exit(0)


    # 休市日（周末/法定节假日/调休休市）：只发当天新闻汇总，不推任何股票分析、不调 DeepSeek
    if not is_trading_day():
        holiday_slot(slot)
        sys.exit(0)
    if slot == 'watch':
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
        sys.exit(0)
    if slot == 'confirm':
        try:
            _cf = build_confirm()
        except Exception as e:
            print('[confirm] build exception:', e)
            _cf = None
        if _cf is None:
            print('SLOT confirm: 构建失败，不推送')
            sys.exit(0)
        ok, msg = push(_cf, f'竞价确认 {_bj_now().strftime("%H:%M")}')
        print('SLOT confirm PUSH', ok, msg)
        sys.exit(0)
    if slot == 'ext':
        try:
            _ex = build_ext()
        except Exception as e:
            print('[ext] build exception:', e)
            _ex = None
        if _ex is None:
            print('SLOT ext: 构建失败，不推送')
            sys.exit(0)
        ok, msg = push(_ex, f'外盘窗口 {_bj_now().strftime("%H:%M")}')
        print('SLOT ext PUSH', ok, msg)
        sys.exit(0)
    if slot == 'evening':
        try:
            _ev = build_evening()
        except Exception as e:
            print('[evening] build exception:', e)
            _ev = None
        if _ev is None:
            print('SLOT evening: 构建失败，不推送')
            sys.exit(0)
        ok, msg = push(_ev, f'晚间消息汇总 {_bj_now().strftime("%H:%M")}')
        print('SLOT evening PUSH', ok, msg)
        sys.exit(0)
    if slot == 'follow':
        try:
            _fl, _why = build_followup()
        except Exception as e:
            print('[follow] build exception:', e)
            _fl, _why = None, f'异常 {e}'
        if _fl is None:
            print('SLOT follow: 不推送（', _why, '）')
            sys.exit(0)
        ok, msg = push(_fl, f'跟涨三步走 {_bj_now().strftime("%H:%M")}')
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
        if ok and not force:
            _mark_slot_done(_slot_key('warn'))
        print('SLOT warn PUSH', ok, msg)
        sys.exit(0)
    if slot == 'news':
        # 旧事件简报独立档（11:40=noon 档 / 15:10·15:35=eod 档），复用 build_events
        _b = build_events('noon' if _bj_now().hour < 14 else 'eod')
        if not _b:
            print('SLOT news: 无有效事件，不推送')
            sys.exit(0)
        ok, msg = push(_wrap(_b, '📰', '事件简报'), f'事件简报 {_bj_now().strftime("%H:%M")}')
        print('SLOT news PUSH', ok, msg)
        sys.exit(0)


    if slot == 'zscan':
        try:
            _zs = build_zscan(os.environ.get('INPUT_CODE') or None)
        except Exception as e:
            print('[zscan] build exception:', e)
            _zs = ''
        if not _zs:
            print('SLOT zscan: 构建失败，不推送')
            sys.exit(0)
        ok, msg = push(_wrap(_zs, '🛰', '主力雷达'), f'主力雷达 {_bj_now().strftime("%m/%d %H:%M")}')
        print('SLOT zscan PUSH', ok, msg)
        sys.exit(0)
    if slot == 'deep6':
        try:
            _d6 = build_deep6(os.environ.get('INPUT_CODE') or '')
        except Exception as e:
            print('[deep6] build exception:', e)
            _d6 = ''
        if not _d6:
            print('SLOT deep6: 无标的或构建失败，不推送')
            sys.exit(0)
        ok, msg = push(_wrap(_d6, '🔬', '个股深度六层'), f'个股深度六层 {_bj_now().strftime("%m/%d %H:%M")}')
        print('SLOT deep6 PUSH', ok, msg)
        sys.exit(0)
    if slot == 'news2h':
        try:
            _n2 = build_news2h()
        except Exception as e:
            print('[news2h] build exception:', e)
            _n2 = None
        if _n2 is None:
            print('SLOT news2h: 构建失败，不推送')
            sys.exit(0)
        ok, msg = push(_n2, f'两小时消息汇总 {_bj_now().strftime("%H:%M")}')
        print('SLOT news2h PUSH', ok, msg)
        sys.exit(0)
    if slot == 'eod':
        today = _bj_now().strftime('%Y-%m-%d')
        if eod_push_done(today):
            print(f'SLOT eod 今日已推送（eod_status.json 去重），跳过')
            sys.exit(0)
        try:
            html = build_eod()
        except Exception as e:
            print('[build] exception:', e)
            html = _wrap(f'<div style="color:{RED}">⚠️ 本卡片构建异常：{e}</div>', '⚠️', '构建异常')
            ok, msg = push(html, f'{TITLES["eod"]} {datetime.now().strftime("%m/%d %H:%M")}')
            print('SLOT eod PUSH(异常兜底，不标记去重)', ok, msg)
            sys.exit(0)
        ok, msg = push(html, f'{TITLES["eod"]} {datetime.now().strftime("%m/%d %H:%M")}')
        if ok:
            mark_eod_done(today)
            _git_commit_push('data/eod_status.json', 'update eod status')
        print('SLOT eod PUSH', ok, msg)
        sys.exit(0)
    # —— 多点cron 当日去重（仅定时自动run；手动 --force 不受限，用于演示/验证）——
    if not force and slot in ('auction', 'pre', 'noon', 'hourly'):
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
    ok, msg = push(html, f'{TITLES[slot]} {datetime.now().strftime("%m/%d %H:%M")}')
    if ok and not force and slot in ('auction', 'pre', 'noon', 'hourly'):
        _mark_slot_done(_slot_key(slot))
    print('SLOT', slot, 'PUSH', ok, msg)

# NO_HOLD_PATCH_V2
