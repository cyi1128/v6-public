# -*- coding: utf-8 -*-
"""
统一企业微信推送总线 V3.0
========================
原则：
- 业务模块只调本总线，不直接碰 Webhook。
- 企业微信只推送"真正值得关注"的事件，普通程序状态留在 UI。
- 五类实时推送 + 一类收盘总结：
    🔥 盘中机会  INTRADAY
    🎯 分时做T   T_TIMING
    🔄 题材轮动  THEME_ROTATION
    📰 事件驱动  EVENT_DRIVEN
    📈 日K建仓   DAILY_ENTRY
    📊 收盘总结  DAILY_SUMMARY
- 统一：消息分类 -> 优先级 -> 去重 -> 同股冷却 -> 短时合并 -> WechatPushService -> Webhook
- Webhook 加载优先级与发送能力复用 services.wechat_push.WechatPushService（不改地址/不改优先级）。
- 线程安全：内部锁，发送走后台线程，不阻塞业务/UI。
- 数据缺失一律显示"未取得"，禁止用 0 冒充未知。
"""
import os
import sys
import time
import threading
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ---- 冷却时间（秒）----
COOLDOWN = {
    'intraday': 1800,     # 盘中机会 30 分钟
    't_timing': 1200,     # 分时做T 20 分钟
    'theme_rotation': 1800,  # 题材轮动 30 分钟
    'daily_entry': 86400,  # 日K建仓 24 小时（同一基准日只推一次）
    # event_driven 用 event_id 去重，不固定冷却
}

# 同一股票"盘中机会 + 题材轮动"合并窗口（秒）
MERGE_WINDOW = 90

NA = '未取得'


def _fmt(v, digits=2, suffix=''):
    """安全格式化：None/空 -> 未取得；数字 -> 保留小数。"""
    if v is None or v == '' or v == 'None':
        return NA
    try:
        return f"{float(v):.{digits}f}{suffix}"
    except Exception:
        return str(v) if str(v) != '' else NA


class WechatBus:
    """统一推送总线（单例）。"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_init'):
            return
        self._init = True
        self._send_lock = threading.Lock()
        self._last_sent = {}   # dedup_key -> ts(秒)
        self._pending_merge = {}  # code -> {'intraday': dict, 'theme': dict, 'ts': ts}
        self._svc = None
        try:
            from services.wechat_push import get_wechat_push_service
            self._svc = get_wechat_push_service()
        except Exception as e:
            print(f"[WechatBus] 推送服务加载失败(将静默): {e}", flush=True)

    # ---------- 内部：实际发送 ----------
    def _post(self, title, md_body):
        if self._svc is None:
            try:
                from services.wechat_push import get_wechat_push_service
                self._svc = get_wechat_push_service()
            except Exception:
                return False
        if not self._svc or not self._svc.is_configured():
            print(f"[WechatBus] webhook 未配置，跳过: {title}", flush=True)
            return False
        content = f"### {title}\n\n{md_body}"
        try:
            ok = self._svc._send_markdown(content)
            print(f"[WechatBus] 发送 {title} -> {ok}", flush=True)
            return bool(ok)
        except Exception as e:
            print(f"[WechatBus] 发送异常 {title}: {e}", flush=True)
            return False

    def _post_async(self, title, md_body):
        """后台线程发送，不阻塞业务。"""
        threading.Thread(target=self._post, args=(title, md_body), daemon=True).start()

    # ---------- 去重/冷却 ----------
    def _dedup_ok(self, key, cooldown):
        now = time.time()
        with self._send_lock:
            last = self._last_sent.get(key, 0)
            if now - last < cooldown:
                return False
            self._last_sent[key] = now
            return True

    # ---------- ① 🔥 盘中机会 ----------
    def send_intraday(self, status, code, name='', price=None, pct=None,
                      theme='', chain_path='', reasons=None, risk='', extra=None):
        """盘中机会：只对"联动确认/早期启动确认"真正发送。
        其余状态（预备/初步联动/冷却/二次异动/ATR等待）由调用方决定是否进入，
        本方法按 status 二次把关：非确认类直接丢弃。
        [PUSH-UPG] extra: 引擎端已构建的全字段 dict，缺失键输出"数据源缺失：xxx"。"""
        confirm_statuses = ('联动确认', '已启动', '二次异动')  # 早期启动确认
        if status not in confirm_statuses:
            return {'sent': False, 'reason': '非确认状态，不推送企业微信'}

        key = f"intraday|{code}|{status}"
        if not self._dedup_ok(key, COOLDOWN['intraday']):
            return {'sent': False, 'reason': '冷却中'}

        tag = '联动确认' if status == '联动确认' else '早期启动确认'
        title = f"🔥【盘中机会｜{tag}】"

        # [PUSH-UPG] 全字段渲染：优先 extra（引擎端已算），缺失键→"数据源缺失：xxx"
        if extra:
            e = extra
            def _missing(label):
                return f"数据源缺失：{label}"
            pct_txt = f"{pct:+.2f}%" if pct is not None else _missing('个股涨幅')
            price_txt = _fmt(price) if price is not None else _missing('现价')
            excess = e.get('excess') or _missing('板块超额涨幅')
            chain_pos = e.get('chain_position') or _missing('产业链位置')
            leaders = e.get('leaders') or _missing('同题材领涨股')
            linked = e.get('linked') or _missing('联动标的清单')
            sector_pct = e.get('sector_pct') or _missing('板块指数涨幅')
            sector_cnt = e.get('sector_cnt') or _missing('板块涨跌家数')
            vol_ratio = e.get('vol_ratio') or _missing('量比')
            amount = e.get('amount') or _missing('成交额')
            turnover = e.get('turnover') or _missing('换手率')
            fund = e.get('fund') or _missing('主力净流入')
            tech = e.get('tech') or _missing('技术指标')
            stop_ref = e.get('stop_ref') or _missing('止损参考位')
            pressure = e.get('pressure') or _missing('压力位')
            chase = e.get('chase') or _missing('追高风险提示')
            timeliness = e.get('timeliness') or _missing('数据时效')
            reason_lines = reasons or []
            r_txt = '\n'.join(f'> {r}' for r in reason_lines[:6]) if reason_lines else f"> {_missing('触发依据')}"
            body = (
                f"**{name or _missing('股票名')}（{code}）**\n"
                f"> 现价：{price_txt} ｜ 涨跌幅：{pct_txt} ｜ 板块超额：{excess}\n\n"
                f"**题材与产业链：**\n"
                f"> 题材：{theme or _missing('题材名')}\n"
                f"> 产业链位置：{chain_pos}\n"
                f"> 轮动路径：{chain_path or _missing('轮动路径')}\n"
                f"> 同题材领涨：{leaders}\n\n"
                f"**触发依据（{status}）：**\n"
                f"> 联动标的：{linked}\n"
                f"> 板块指数：{sector_pct} ｜ {sector_cnt}\n"
                f"> 量能：量比：{vol_ratio} ｜ 成交额：{amount} ｜ 换手率：{turnover}\n"
                f"> 资金：{fund}\n"
                f"> 技术：{tech}\n"
                f"{r_txt}\n\n"
                f"**风险提示：**\n"
                f"> 止损参考位：{stop_ref} ｜ 压力位：{pressure}\n"
                f"> 追高风险：{chase}\n"
                f"> 数据时效：{timeliness}\n\n"
                f"---\n*清一盘·盘中机会 ｜ 数据为真实行情，仅供参考，不构成投资建议*"
            )
        else:
            # 兼容旧调用方（无 extra）：保留原模板
            reason_lines = reasons or []
            r_txt = '\n'.join(f'> {r}' for r in reason_lines[:3]) if reason_lines else f'> {NA}'
            body = (
                f"**{name or NA}（{code}）**\n"
                f"> 现价：{_fmt(price)} ｜ 涨幅：{_fmt(pct, 2, '%')}\n"
                f"> 题材：{theme or NA}\n"
                f"> 产业链位置/轮动路径：{chain_path or NA}\n\n"
                f"**触发依据：**\n{r_txt}\n\n"
                f"> 当前状态：{status}\n"
                f"> 风险提示：{risk or NA}\n\n"
                f"---\n*清一盘·盘中机会 ｜ 数据为真实行情，仅供参考，不构成投资建议*"
            )
        self._post_async(title, body)
        return {'sent': True, 'key': key}

    # ---------- ② 🎯 分时做T ----------
    def send_t_timing(self, event, code, name='', price=None, vwap=None, atr=None,
                     ref_price=None, cur_status='', reason='', risk='', action=''):
        """分时做T：买入观察/卖出观察/重新转强。
        event in {买入观察, 卖出观察, 重新转强}"""
        if event not in ('买入观察', '卖出观察', '重新转强'):
            return {'sent': False, 'reason': '非有效做T信号'}

        # 同股同状态 20 分钟冷却；状态升级（买入->转强->卖出）视为新 key，允许再发
        key = f"t_timing|{code}|{event}"
        if not self._dedup_ok(key, COOLDOWN['t_timing']):
            return {'sent': False, 'reason': '冷却中'}

        title = f"🎯【分时做T｜{event}】"
        ref_label = '做T买入参考' if event != '卖出观察' else '做T卖出参考'

        body = (
            f"**{name or NA}（{code}）**\n"
            f"> 现价：{_fmt(price)}\n"
            f"> VWAP：{_fmt(vwap)} ｜ ATR：{_fmt(atr)}\n"
            f"> {ref_label}：{_fmt(ref_price)}\n"
            f"> 当前分时状态：{cur_status or NA}\n\n"
            f"**触发依据：**\n> {reason or NA}\n\n"
            f"> 风险条件：{risk or NA}\n"
            f"> 操作建议：{action or NA}\n\n"
            f"---\n*清一盘·分时做T（持仓T+0参考）｜ 仅供参考，不构成投资建议*"
        )
        self._post_async(title, body)
        return {'sent': True, 'key': key}

    # ---------- ③ 📈 日K建仓（盘后信号） ----------
    def send_daily_entry(self, code, name='', price=None, pct=None,
                         pattern='', trigger_type='', entry=None,
                         take_profit=None, env_score=None, env_note='',
                         theme='', base_date='', push_date='', note='',
                         dedup_key=''):
        """日K建仓：只在「建仓触发」推送。

        推送内容：建仓价（= 引擎算出的挂单价）/ 止盈价（= 建仓价×1.03）/ 环境分。
        dedup_key 用于同一基准日只推一次；不传则回落到 code+base_date。
        """
        key = 'daily_entry|%s|%s' % (code, dedup_key or base_date or '')
        if not self._dedup_ok(key, COOLDOWN['daily_entry']):
            return {'sent': False, 'reason': '冷却中'}

        title = '📈【日K建仓｜建仓触发】'

        # 环境分档位
        if env_score is None:
            env_txt = NA
            env_lv = ''
        else:
            try:
                _es = int(env_score)
                env_lv = '正常建仓' if _es >= 6 else ('谨慎/半仓' if _es >= 3 else '不建议建仓')
                env_txt = '%d（%s）' % (_es, env_lv)
            except Exception:
                env_txt = str(env_score)

        # 止盈幅度
        tp_txt = _fmt(take_profit)
        if take_profit and entry:
            try:
                _gain = (float(take_profit) / float(entry) - 1) * 100
                tp_txt = '%s（+%.1f%%）' % (_fmt(take_profit), _gain)
            except Exception:
                pass

        body = (
            f"**{name or NA}（{code}）**\n"
            f"> 现价：{_fmt(price)} ｜ 涨跌幅：{_fmt(pct, 2, '%')}\n"
            f"> 建仓价：{_fmt(entry)} ｜ 止盈价：{tp_txt}\n"
            f"> 环境分：{env_txt}\n\n"
            f"**结构信息：**\n"
            f"> 模式：{pattern or NA}\n"
            f"> 触发条件：{trigger_type or NA}\n"
            f"> 基准日：{base_date or NA}\n"
            f"> 题材：{theme or NA}\n\n"
            f"**环境说明：**\n"
            f"> {env_note or NA}\n"
            f"> {note or NA}\n\n"
            f"---\n*清一盘·日K建仓（盘后信号·次日参考）｜ 仅供参考，不构成投资建议*"
        )
        self._post_async(title, body)
        return {'sent': True, 'key': key}

    # ---------- ④ 🔄 题材轮动 ----------
    def send_theme_rotation(self, theme, rotation_path='', first_stocks=None,
                            new_stocks=None, chain_pos='', status='',
                            reason='', risk=''):
        """题材轮动：只在"真实产业链/资金扩散确认"时发。
        first_stocks/new_stocks: list[str] 股票名/代码。"""
        if not theme:
            return {'sent': False, 'reason': '无题材'}

        key = f"theme_rotation|{theme}|{rotation_path}"
        if not self._dedup_ok(key, COOLDOWN['theme_rotation']):
            return {'sent': False, 'reason': '冷却中'}

        title = "🔄【题材轮动｜确认】"
        first_txt = '、'.join(first_stocks[:5]) if first_stocks else NA
        new_txt = '、'.join(new_stocks[:5]) if new_stocks else NA

        body = (
            f"**题材：{theme}**\n"
            f"> 当前轮动路径：{rotation_path or NA}\n"
            f"> 产业链位置：{chain_pos or NA}\n\n"
            f"**已经出现异动：**\n> {first_txt}\n\n"
            f"**新出现异动：**\n> {new_txt}\n\n"
            f"> 当前状态：{status or NA}\n"
            f"**为什么触发：**\n> {reason or NA}\n\n"
            f"> 风险：{risk or NA}\n\n"
            f"---\n*清一盘·题材轮动 ｜ 仅供参考，不构成投资建议*"
        )
        self._post_async(title, body)
        return {'sent': True, 'key': key}

    # ---------- ④ 📰 事件驱动 ----------
    def send_event_driven(self, event, impact='', direction='', chain='',
                           stocks=None, market='', reason='', status='',
                           risk='', event_id=None):
        """事件驱动：新闻+明确方向+真实题材/产业链+盘面关联，才发。
        event_id 用于同一事件去重。"""
        if not event:
            return {'sent': False, 'reason': '无事件'}
        eid = event_id or f"{event}|{direction}|{(stocks or [''])[0]}"
        key = f"event_driven|{eid}"
        # 事件驱动按 event_id 永久去重：同一事件只发一次
        with self._send_lock:
            if key in self._last_sent:
                return {'sent': False, 'reason': '事件已推送过'}
            self._last_sent[key] = time.time()

        stocks_txt = '、'.join(stocks[:8]) if stocks else NA

        body = (
            f"**事件：{event}**\n"
            f"> 核心影响：{impact or NA}\n"
            f"> 影响方向：{direction or NA}\n"
            f"> 产业链：{chain or NA}\n\n"
            f"**关联股票：**\n> {stocks_txt}\n\n"
            f"> 当前盘面：{market or NA}\n"
            f"**程序匹配依据：**\n> {reason or NA}\n\n"
            f"> 当前状态：{status or NA}\n"
            f"> 风险：{risk or NA}\n\n"
            f"---\n*清一盘·事件驱动 ｜ 仅供参考，不构成投资建议*"
        )
        self._post_async("📰【事件驱动】", body)
        return {'sent': True, 'key': key}

    # ---------- 📊 收盘总结 ----------
    def send_daily_summary(self, date_str, md_body):
        title = f"📊【收盘总结｜{date_str}】"
        # 收盘总结不冷却（一天一次），直接发
        self._post_async(title, md_body)
        return {'sent': True}


# 全局单例
_bus = None

def get_wechat_bus() -> WechatBus:
    global _bus
    if _bus is None:
        _bus = WechatBus()
    return _bus
