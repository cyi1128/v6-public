# -*- coding: utf-8 -*-
"""
量化交易作战中控台 V2.8 - AI520精准选股+行业过滤+买点评分+自选股+风控排雷+信号跟踪 完整真实数据链路
删除：尾盘选股/运行日志/持仓监控/实时监控
新增：资金流向/热门题材/板块热点/板块异动雷达
增强：盘前新闻大卡片+股票识别、专业K线+信号标记+买点解释、首页市场态势
"""

import sys
import os
import time
import json
import re as _re_mod
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QGridLayout, QSizePolicy, QApplication,
    QTabWidget, QProgressBar, QComboBox, QListWidget, QListWidgetItem,
    QGroupBox, QSplitter, QTextBrowser, QLineEdit, QGraphicsDropShadowEffect,
    QDialog,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QFont, QColor, QDesktopServices
from PyQt6.QtCore import QUrl

from ui.real_scan_service import get_real_scan_service
from service.unified_data_service import get_news_service, get_fund_flow_service, get_sector_data_service

# V3.0 实时新闻中心全量升级：多源接入+自动刷新+智能去重+投资日历
try:
    from news_center import (
        get_refresh_engine, get_deduplicator, get_multi_source_manager,
        get_calendar_provider, CALENDAR_TYPE_COLORS, CALENDAR_TYPE_ICONS,
        REFRESH_CONFIG, get_enabled_sources, get_source_info,
    )
    NEWS_CENTER_AVAILABLE = True
except Exception as _nc_e:
    print(f"[新闻中心] 模块导入失败，降级使用旧版: {_nc_e}", flush=True)
    NEWS_CENTER_AVAILABLE = False

# 启动性能诊断（只测量不修改业务逻辑）
try:
    from tools.startup_profiler import step_start, step_end
    PROFILER_ENABLED = True
except Exception:
    PROFILER_ENABLED = False

def _lu_pct(code) -> float:
    """[CYB-GATE] 按板性返回判涨停阈值（%）：主板 9.5，创业板/科创板 19.5，北交所 29.5。

    创业板 300/301 与科创板 688/689 是 20cm 板，北交所 8xx/4xx/920 是 30cm 板。
    统一按 9.5% 判会把这两类板的「涨了一半」误当成涨停。
    """
    c = str(code or '')
    if c.startswith(('300', '301', '688', '689')):
        return 19.5
    if c.startswith(('8', '4', '920')):
        return 29.5
    return 9.5


def p_start(name):
    if PROFILER_ENABLED:
        step_start(name)

def p_end(name, extra=''):
    if PROFILER_ENABLED:
        step_end(name, extra)


# ============================================================
# 技术指标参数持久化配置
# ============================================================
_INDICATOR_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'config', 'indicator_params.json'
)


def _load_indicator_config():
    """读取指标参数配置，不存在或解析失败返回空dict"""
    try:
        if os.path.exists(_INDICATOR_CONFIG_PATH):
            with open(_INDICATOR_CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"[指标参数] 读取配置失败: {e}", flush=True)
    return {}


def _save_indicator_config(data):
    """保存指标参数配置"""
    try:
        os.makedirs(os.path.dirname(_INDICATOR_CONFIG_PATH), exist_ok=True)
        with open(_INDICATOR_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[指标参数] 保存配置失败: {e}", flush=True)


# ============================================================
# 颜色常量
# ============================================================
class C:
    # 浅色金融主题（统一配色，类东方财富/同花顺网页版浅色终端）
    BG = '#f0f4f9'; CARD = '#ffffff'; CARD_HOVER = '#f5f7fa'
    TAB = '#f5f7fa'; TAB_ACTIVE = '#2f6bff'; BORDER = '#e0e0e0'; BORDER_L = '#cccccc'
    TEXT = '#333333'; TEXT2 = '#888888'; TEXT3 = '#999999'
    BLUE = '#2f6bff'; PURPLE = '#7b1fa2'; RED = '#e53935'; GREEN = '#43a047'
    YELLOW = '#f9a825'; ORANGE = '#ff6d00'; CYAN = '#00838f'


def L(text, color=C.TEXT, size=12, bold=False, align=None):
    label = QLabel(text)
    label.setStyleSheet(f'color:{color};font-size:{size}px;font-weight:{"bold" if bold else "normal"};background:transparent;')
    if align: label.setAlignment(align)
    return label

def Card():
    card = QFrame()
    card.setStyleSheet(f'QFrame{{background:{C.CARD};border:1px solid {C.BORDER};border-radius:12px;}}')
    shadow = QGraphicsDropShadowEffect(card)
    shadow.setBlurRadius(16); shadow.setColor(QColor(0, 0, 0, 25)); shadow.setOffset(0, 4)
    card.setGraphicsEffect(shadow)
    return card

def add_glass_shadow(widget, blur=16, alpha=15, offset_y=4):
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur); shadow.setColor(QColor(0, 0, 0, alpha)); shadow.setOffset(0, offset_y)
    widget.setGraphicsEffect(shadow)
    return widget

def SignalTag(text, color=C.CYAN):
    tag = QLabel(text)
    tag.setStyleSheet(f'color:{color};background:rgba(0,122,255,0.08);border:1px solid {color};border-radius:6px;padding:2px 8px;font-size:11px;font-weight:600;')
    return tag

def RiskTag(text):
    tag = QLabel(f'⚠ {text}')
    tag.setStyleSheet(f'color:{C.RED};background:rgba(255,59,48,0.08);border:1px solid {C.RED};border-radius:6px;padding:2px 8px;font-size:11px;font-weight:600;')
    return tag


# ============================================================
# 数据源状态指示器
# ============================================================
class DataSourceStatus(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        p_start("DataSourceStatus初始化")
        self.setFixedHeight(32)
        self.setStyleSheet(f'QFrame{{background:rgba(255,255,255,0.9);border-bottom:1px solid #E2E8F0;}}')
        self.indicators = {}
        self._build_ui()
        self._start_timer()
        p_end("DataSourceStatus初始化")

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(12)
        layout.addWidget(L('数据源', C.TEXT3, 10, True))
        sources = ['stock_list', 'realtime_quote', 'kline', 'index', 'limit_up', 'sector', 'news', 'signal']
        names = {'stock_list': '股票', 'realtime_quote': '行情', 'kline': 'K线', 'index': '指数', 'limit_up': '涨停', 'sector': '板块', 'news': '新闻', 'signal': '信号'}
        for src in sources:
            ind = QHBoxLayout()
            dot = L('●', C.TEXT3, 10); name = L(names[src], C.TEXT3, 10)
            ind.addWidget(dot); ind.addWidget(name)
            layout.addLayout(ind)
            self.indicators[src] = (dot, name)
        layout.addStretch()
        self.time_label = L(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), C.TEXT2, 11)
        layout.addWidget(self.time_label)

    def _start_timer(self):
        self.timer = QTimer(self); self.timer.timeout.connect(self._update); self.timer.start(2000); self._update()

    def _update(self):
        self.time_label.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        try:
            service = get_real_scan_service()
            status = service.get_data_source_status()
            for src, (dot, name) in self.indicators.items():
                s = status.get(src, {}); st = s.get('status', 'unknown')
                color = C.GREEN if st == 'ok' else (C.RED if st == 'error' else C.YELLOW)
                dot.setStyleSheet(f'color:{color};font-size:10px;background:transparent;')
                name.setStyleSheet(f'color:{color};font-size:10px;background:transparent;')
        except Exception: pass


# ============================================================
# 实时信号流 V2
# ============================================================
# ============================================================
# 市场概况卡片
# ============================================================
# ============================================================
# 扫描线程
# ============================================================
class ScanThread(QThread):
    finished = pyqtSignal(dict); progress = pyqtSignal(int, int, int, int, int, int)
    def __init__(self, max_stocks=0, min_score=40):
        super().__init__(); self.max_stocks = max_stocks; self.min_score = min_score
    def run(self):
        try:
            service = get_real_scan_service()
            result = service.scan_main_board(max_stocks=self.max_stocks, min_score=self.min_score, progress_callback=self._on_progress, use_cache=True)
            self.finished.emit(result)
        except Exception as e:
            print(f"[扫描线程] 错误: {e}", flush=True)
            self.finished.emit({'stocks': [], 'total_scanned': 0, 'filter_stats': {}})
    def _on_progress(self, current, total, candidates, s, a, b):
        self.progress.emit(current, total, candidates, s, a, b)




class _OllamaQWorker(QThread):
    """本地 Ollama 追问线程：自动检测可用模型，失败时返回友好提示"""
    reply_ready = pyqtSignal(str, bool)  # (text, is_error)

    def __init__(self, prompt, parent=None):
        super().__init__(parent)
        self.prompt = prompt

    def run(self):
        try:
            import requests
            model = 'qwen3:14b'
            # 自动检测可用模型（优先qwen3系列）
            try:
                r = requests.get('http://localhost:11434/api/tags', timeout=3)
                if r.status_code == 200:
                    tags = (r.json() or {}).get('models', [])
                    if tags and isinstance(tags, list):
                        # 优先选qwen3:14b，其次任意qwen3，最后任意模型
                        qwen3_32 = [t for t in tags if 'qwen3:14b' in t.get('name','')]
                        qwen3_any = [t for t in tags if 'qwen3' in t.get('name','')]
                        if qwen3_32:
                            model = qwen3_32[0]['name']
                        elif qwen3_any:
                            model = qwen3_any[0]['name']
                        else:
                            model = tags[0].get('name', model)
            except Exception:
                pass
            # qwen3使用chat接口（自动处理对话模板）
            resp = requests.post(
                'http://localhost:11434/api/chat',
                json={'model': model, 'messages': [{'role': 'user', 'content': self.prompt}], 'stream': False},
                timeout=180,
            )
            if resp.status_code != 200:
                self.reply_ready.emit(f'本地AI服务返回错误: HTTP {resp.status_code}', True)
                return
            data = resp.json() or {}
            text = ((data.get('message') or {}).get('content') or '').strip()
            if not text:
                text = '（本地AI未返回内容，请稍后重试）'
            self.reply_ready.emit(text, False)
        except Exception:
            self.reply_ready.emit('本地AI服务未启动或响应超时，请先启动Ollama', True)



# ============================================================
# 同花顺问财 新闻解读 / 追问 后台线程（V3.1 替代本地模板与本地Ollama）
# ============================================================
def _wc_extract_stock_info(stock_dict):
    """从问财返回的单只股票dict中提取 (名称, 代码, 涨跌幅字符串)，兼容多种字段名"""
    name, code, pct_str = '', '', ''
    if not isinstance(stock_dict, dict):
        return name, code, pct_str
    for k, v in stock_dict.items():
        if v is None or str(v) == 'nan':
            continue
        k_raw = str(k)
        k_lower = k_raw.lower()
        try:
            if ('代码' in k_raw) or (k_lower == 'code') or ('code' in k_lower and 'code_name' not in k_lower):
                code = str(v).split('.')[0].zfill(6)
            elif ('简称' in k_raw) or ('名称' in k_raw) or (k_lower == 'name') or ('股票名' in k_raw):
                name = str(v)
            elif ('涨跌幅' in k_raw) or ('pct_chg' in k_lower) or ('changepercent' in k_lower) or k_lower == '涨幅':
                try:
                    pct_str = f'{float(v):+.2f}%'
                except Exception:
                    pct_str = str(v)
        except Exception:
            continue
    return name, code, pct_str


def _wc_build_query(news):
    """从新闻提取核心概念关键词（传入 WencaiNewsService.query_concept，自动追加'概念股'）"""
    title = str(news.get('title', ''))
    content = str(news.get('content', ''))
    text = title + ' ' + content

    if '降准' in text:
        return '降准'
    if '降息' in text:
        return '降息'
    if '加息' in text:
        return '加息'
    if '减税' in text or '增值税' in text:
        return '减税降费'
    if '2nm' in text or '2纳米' in text:
        return '2nm芯片'
    if '半导体' in text and ('设备' in text or '量产' in text or '晶圆' in text):
        return '半导体设备'
    if '芯片' in text or '集成电路' in text:
        return '芯片'
    if '光刻' in text:
        return '光刻机'
    if '新能源汽车' in text or '电动车' in text:
        return '新能源汽车'
    if '锂电池' in text or '动力电池' in text:
        return '锂电池'
    if '光伏' in text:
        return '光伏'
    if '风电' in text:
        return '风电'
    if '人工智能' in text or 'AI' in text or '大模型' in text:
        return '人工智能'
    if '机器人' in text:
        return '机器人'
    if '医疗旅游' in text or '医疗城' in text:
        return '医疗旅游'
    if '医疗器械' in text:
        return '医疗器械'
    if '创新药' in text or '生物医药' in text:
        return '创新药'
    if '军工' in text or '国防' in text:
        return '军工'
    if '房地产' in text or '楼市' in text:
        return '房地产'
    if '数字货币' in text or '区块链' in text:
        return '数字货币'
    if '算力' in text:
        return '算力'
    if '数据中心' in text or 'IDC' in text:
        return '数据中心'
    if '碳关税' in text:
        return '新能源'
    if '新能源' in text:
        return '新能源'
    if '中东' in text or '沙特' in text or '迪拜' in text:
        return '一带一路'
    kw = title.strip()
    kw = _re_mod.sub(r'[^0-9a-zA-Z一-龥]+', ' ', kw).strip()
    kw = kw[:20]
    return kw if kw else 'A股'


def _wc_run_analysis(news):
    """在后台线程中执行AI新闻深度解读（火山方舟大模型，不依赖问财），返回V6量化投研简报dict。
    直接用新闻原文+板块实时数据+大盘概况调用大模型；失败降级规则模板（绝不摆烂）。"""
    from services.news_ai_interpreter import interpret_news
    from ui.news_v6_interpreter import _v6_build_analysis, _v6_match_sectors

    # 主链路：火山方舟大模型按"量化投研简报系统指令"生成六模块深度解读
    try:
        full_text = str(news.get('title', '')) + ' ' + str(news.get('content', ''))
        sector_map = _deep_get_sector_map()
        matched = _v6_match_sectors(full_text, sector_map)
        # 大盘概况（失败忽略，不影响主链路）
        market_brief = None
        try:
            from market_analysis.market_sentiment import analyze_sentiment
            md = analyze_sentiment()
            if md:
                market_brief = (
                    f"涨跌比{md.get('advance', 0)}:{md.get('decline', 0)} "
                    f"涨停{md.get('limit_up', 0)}家 连板{md.get('max_consecutive', 0)}板 "
                    f"炸板率{md.get('broken_rate', 0):.0f}% 量能{md.get('turnover', 0)}亿"
                )
        except Exception:
            pass
        ai = interpret_news(
            news,
            sector_map=sector_map,
            matched_sectors=matched,
            wencai_stocks=None,
            wencai_voice='',
            market_brief=market_brief,
        )
        if ai:
            return ai
        print('[AI解读] 大模型解读不可用，降级规则模板', flush=True)
    except Exception as e:
        print(f'[AI解读] 大模型深度解读异常，降级规则模板: {e}', flush=True)

    # 降级：规则模板兜底（六模块，绝不摆烂）
    return _v6_build_analysis(news, wencai_stocks=None, wencai_voice='')


def _wc_run_qa(question, news_title=''):
    """后台线程中执行问财追问（HTTP 直连 WencaiNewsService），返回 (回答文本, is_error)。"""
    from services.wencai_news_service import get_wencai_news_service
    service = get_wencai_news_service()

    result = service.query_followup(question)
    if result.get('cookie_expired'):
        return ('问财登录已过期，请重新登录后更新Cookie', True)
    if not result.get('success'):
        return (f'问财查询失败：{result.get("error", "未知错误")}', True)

    voice_txt = str(result.get('voice_txt', '') or '')
    stocks = result.get('stocks') or []

    lines = []
    if voice_txt:
        lines.append(f'<span style="color:#1E293B">{voice_txt}</span><br>')
    if stocks:
        lines.append(f'<b>相关标的（{len(stocks)}只）：</b><br>')
        for s in stocks[:10]:
            pct = float(s.get('pct', 0.0) or 0.0)
            price = float(s.get('price', 0.0) or 0.0)
            color = '#FF3B30' if pct >= 0 else '#34C759'
            lines.append(
                f'{s.get("name", "")}({s.get("code", "")}) '
                f'现价 {price:.2f} '
                f'<span style="color:{color}">{pct:+.2f}%</span><br>'
            )
    else:
        lines.append('<span style="color:#64748B">问财未返回相关股票数据，换个问法或稍后再试。</span>')
    lines.append('<span style="color:#64748B">数据来源：同花顺问财，仅供参考</span>')
    return ''.join(lines), False


class _WencaiAnalysisWorker(QThread):
    """问财新闻解读后台线程"""
    result_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, news, parent=None):
        super().__init__(parent)
        self.news = news

    def run(self):
        try:
            analysis = _wc_run_analysis(self.news)
            self.result_ready.emit(analysis)
        except Exception as e:
            self.error_occurred.emit(str(e))


class _WencaiQAWorker(QThread):
    """AI追问后台线程（火山方舟大模型，不依赖问财）"""
    reply_ready = pyqtSignal(str, bool)  # (text, is_error)

    def __init__(self, question, news, parent=None):
        super().__init__(parent)
        self.question = question
        self.news = news

    def run(self):
        try:
            from services.news_ai_interpreter import ask_question
            text = ask_question(self.news, self.question)
            if text:
                self.reply_ready.emit(text, False)
            else:
                self.reply_ready.emit('AI追问暂不可用，请稍后再试', True)
        except Exception as e:
            self.reply_ready.emit(f'AI追问暂不可用：{str(e)[:60]}', True)


# ============================================================
# 深度逻辑分析（问财无直接概念股时的兜底，按新闻分类做传导链分析）
# 核心原则：问财搜不到不等于不分析，必须基于新闻类型走逻辑传导路径
# ============================================================
_deep_sector_cache = {'map': None, 'time': 0}


def _deep_get_sector_map():
    """模块级获取板块真实涨跌幅

    【2026-09-24 清理 v28 死引用】原数据源 v28.core.sector_radar.SectorRadarEngine
    已下线（v28 包不存在），此处此前每次都抛 ModuleNotFoundError 并被吞掉。
    板块真实涨跌幅当前无来源，统一返回空 dict，调用方会走各自的降级分支。
    """
    return {}


def _deep_dir(text):
    """共享方向判断：根据文本判断涨/跌/平，返回 'up'/'down'/'flat'"""
    down_kw = ['大跌','暴跌','跳水','重挫','下挫','杀跌','下跌','回落','走低','下探','跌','走弱','承压','萎缩','下滑','收缩','降息','降准','宽松']
    up_kw = ['大涨','暴涨','飙升','拉升','冲高','反弹','上涨','走高','走强','涨','回升','扩张','超预期','加息','收紧','增产']
    # 优先精确词，避免单字"涨/跌"误判；统计命中
    down_hits = sum(1 for k in down_kw if k in text)
    up_hits = sum(1 for k in up_kw if k in text)
    if down_hits > up_hits:
        return 'down'
    if up_hits > down_hits:
        return 'up'
    return 'flat'


def _deep_classify_news(news):
    """深度新闻分类（6类），判断优先级：期货/指数异动 > 大宗商品 > 宏观数据 > 国际政治 > 个股公告 > 行业政策(默认)。
    设计原则：价格/指数类信号优先于主题归类，避免把指数期货异动误判成国际政治或商品。"""
    title = str(news.get('title', ''))
    content = str(news.get('content', ''))
    text = title + ' ' + content

    # 0. 大类种子词（用于交叉排除）
    commodity_core = ['原油', '油价', '黄金', '金价', '铜价', '铝价', '铁矿石', '煤炭',
                      '煤价', '天然气', '锂价', '钴', '镍', '稀土', '大豆', '玉米', '棉花',
                      '白糖', 'OPEC', '减产', '大宗商品', '布伦特', 'WTI', 'COMEX', 'LME']

    # 1. 期货/指数异动（最高优先级）
    #    强指数信号：指数名称/期指术语/贴水升水，直接归此类
    idx_strong = ['股指期货', '指数期货', '期指', '中证1000', '中证500', '中证100', '沪深300',
                   '上证50', '上证180', '创业板指', '科创50', 'A股三大指数', '三大指数',
                   '贴水', '升水', '指数大跌', '指数暴涨', '指数大涨', '指数跳水', '指数拉升',
                   '大盘涨', '大盘跌', '上证指数', '深证成指']
    idx_code_re = r'(IF|IC|IM|IH)\s*\d{3,4}'
    has_idx_strong = any(k in text for k in idx_strong)
    has_idx_code = bool(_re_mod.search(idx_code_re, text))
    has_commodity_core = any(k in text for k in commodity_core)
    has_futures_generic = any(k in text for k in ['主力合约', '期货跌', '期货涨', '期指跌', '期指涨', '期指'])
    if has_idx_strong or has_idx_code:
        return '期货指数异动'
    # 泛期货涨跌/主力合约：仅在没有商品核心词时才归指数，避免"原油期货涨"误入
    if has_futures_generic and not has_commodity_core:
        return '期货指数异动'

    # 2. 大宗商品（原油/黄金/有色等价格新闻）
    commodity_kw = commodity_core + ['期货价格', '现货价格', '库存', '开工率', '产能']
    if any(kw in text for kw in commodity_kw):
        return '大宗商品'

    # 3. 宏观数据（CPI/PPI/PMI/GDP/社融/贸易等，从原国际政治宏观中拆出）
    macro_kw = ['CPI', 'PPI', 'PMI', 'GDP', '社融', 'M2', '新增贷款', '进出口', '出口', '进口',
                '贸易顺差', '失业率', '非农', '通胀', '通缩', '经济数据', '统计局', '央行数据',
                '工业增加值', '社零', '社会消费品零售', '外汇储备', '财政收支']
    if any(kw in text for kw in macro_kw):
        return '宏观数据'

    # 4. 国际政治（不含已划归宏观的CPI/PPI/通胀）
    intl_kw = ['美国', '特朗普', '拜登', '民主党', '共和党', '中期选举', '大选', '总统',
               '国会', '美联储', '加息', '降息', '缩表', '关税', '贸易战', '制裁', '地缘', '中东',
               '俄乌', '俄罗斯', '乌克兰', '北约', 'G7', 'G20', '美元', '汇率', '人民币',
               '战争', '冲突', '访华', '峰会', '欧盟', '欧洲', '日本', '韩国', '印度',
               '出口管制', '芯片管制', '半导体出口', '美债', '美元指数']
    if any(kw in text for kw in intl_kw):
        return '国际政治'

    # 5. 个股公告
    announce_kw = ['公告', '复牌', '停牌', '重组', '收购', '并购', '定增', '减持',
                   '增持', '回购', '分红', '配股', '股权激励', '中标', '合同', '签约']
    if any(kw in text for kw in announce_kw):
        return '个股公告'

    # 6. 行业政策（默认类，含政策/规划/意见/方案/部委等）
    return '行业政策'


def _deep_fmt_sector(sector_map, name, label=None):
    """取板块真实涨跌幅并格式化，不存在则返回纯名称"""
    if name in sector_map:
        cp = float(sector_map[name].get('change_pct', 0) or 0)
        color = '#FF3B30' if cp > 0 else ('#34C759' if cp < 0 else '#64748B')
        return f'{label or name} <span style="color:{color}">{cp:+.2f}%</span>'
    return (label or name)


def _deep_intl_subtype(text):
    """国际政治子类型：关税贸易 / 美联储利率 / 大选政治 / 地缘冲突 / 汇率美元 / 通用"""
    if any(k in text for k in ['关税', '贸易战', '贸易', '出口管制', '芯片管制', '制裁', '半导体出口']):
        return '关税贸易'
    if any(k in text for k in ['美联储', '加息', '降息', '缩表', '美债']):
        return '美联储利率'
    if any(k in text for k in ['大选', '中期选举', '总统', '国会', '民主党', '共和党', '特朗普', '拜登']):
        return '大选政治'
    if any(k in text for k in ['战争', '冲突', '地缘', '中东', '俄乌', '俄罗斯', '乌克兰', '北约']):
        return '地缘冲突'
    if any(k in text for k in ['美元', '汇率', '人民币', '美元指数']):
        return '汇率美元'
    return '通用'


def _deep_intl_core(text, t_short, wencai_voice):
    """国际政治核心逻辑：说清新闻本质 + A股传导链条 A→B→C"""
    sub = _deep_intl_subtype(text)
    parts = [f'事件：{t_short}。']
    if sub == '关税贸易':
        parts.append('本质是贸易政策不确定性抬升。传导路径：关税/出口管制加码→出口企业订单与盈利预期下修→人民币汇率承压贬值→北向资金流出→A股出口链与外资重仓成长股估值下杀，同时黄金/军工等避险与自主可控方向相对受益。')
    elif sub == '美联储利率':
        parts.append('本质是全球流动性定价锚变化。传导路径：美联储利率预期调整→美债收益率与美元指数波动→中美利差→人民币汇率与外资流向→A股贴现率变化，成长股(高久期)对利率最敏感，价值/红利相对抗跌。')
    elif sub == '大选政治':
        parts.append('本质是美国政策路线摇摆带来的不确定性溢价。传导路径：大选博弈→贸易/关税/产业政策预期反复→出口链与半导体风险溢价上升→美元阶段性走强、人民币波动→避险情绪升温、风险偏好下降，脉冲式行情居多。')
    elif sub == '地缘冲突':
        parts.append('本质是供应端风险重估。传导路径：地缘冲突→能源/粮食/关键矿产供应受阻预期→原油、黄金、粮食价格上行→全球通胀预期反弹→避险资产受益、航运/航空等依赖进口成本的板块承压。')
    elif sub == '汇率美元':
        parts.append('本质是人民币计价资产的相对吸引力变化。传导路径：美元/人民币汇率波动→出口企业汇兑损益与外债成本→北向资金跨境流向→A股外资重仓板块(消费/医药/新能源)估值与流动性分化。')
    else:
        parts.append('本质是海外宏观事件向A股的情绪与资金传导。传导路径：海外事件→全球风险偏好(VIX)→美元指数与汇率→北向资金流向→A股相关板块情绪与估值，多为情绪面、非基本面冲击。')
    if wencai_voice:
        parts.append(f'问财解读：{wencai_voice[:80]}。')
    return ''.join(parts)


def _deep_intl_beneficiary(text, sector_map):
    """国际政治受益/受损板块：区分直接承压/间接受损/可能受益，用本地SectorRadarEngine真实涨跌幅"""
    sub = _deep_intl_subtype(text)
    parts = ['<b>逻辑关联板块（按传导链映射，附本地真实涨跌幅）：</b><br>']

    if sub in ('关税贸易', '大选政治'):
        parts.append('<b>直接承压：</b>')
        parts.append(_deep_fmt_sector(sector_map, '纺织服饰', '纺织服饰(出口链)') + '　')
        parts.append(_deep_fmt_sector(sector_map, '电子', '电子(消费电子/对美出口)') + '　')
        parts.append(_deep_fmt_sector(sector_map, '电力设备', '电力设备(新能源出口)') + '<br>')
        parts.append('<b>可能受益/避险：</b>')
        parts.append(_deep_fmt_sector(sector_map, '有色金属', '有色金属(黄金)') + '　')
        parts.append(_deep_fmt_sector(sector_map, '国防军工', '国防军工') + '　')
        parts.append(_deep_fmt_sector(sector_map, '计算机', '计算机(自主可控)') + '<br>')
    elif sub == '美联储利率':
        parts.append('<b>降息/宽松受益：</b>')
        parts.append(_deep_fmt_sector(sector_map, '有色金属', '有色金属(黄金)') + '　')
        parts.append(_deep_fmt_sector(sector_map, '电子', '电子(高久期成长)') + '　')
        parts.append(_deep_fmt_sector(sector_map, '电力设备', '电力设备') + '<br>')
        parts.append('<b>加息/收紧承压：</b>')
        parts.append(_deep_fmt_sector(sector_map, '房地产', '房地产') + '　')
        parts.append(_deep_fmt_sector(sector_map, '银行', '银行') + '　')
        parts.append(_deep_fmt_sector(sector_map, '公用事业', '公用事业(高股息)') + '<br>')
    elif sub == '地缘冲突':
        parts.append('<b>直接受益：</b>')
        parts.append(_deep_fmt_sector(sector_map, '石油石化', '石油石化(能源)') + '　')
        parts.append(_deep_fmt_sector(sector_map, '有色金属', '有色金属(黄金)') + '　')
        parts.append(_deep_fmt_sector(sector_map, '国防军工', '国防军工') + '<br>')
        parts.append('<b>直接承压：</b>')
        parts.append(_deep_fmt_sector(sector_map, '交通运输', '交通运输(航运/航油)') + '　')
        parts.append(_deep_fmt_sector(sector_map, '农林牧渔', '农林牧渔(粮食进口)') + '<br>')
    elif sub == '汇率美元':
        parts.append('<b>人民币贬值受益：</b>')
        parts.append(_deep_fmt_sector(sector_map, '纺织服饰', '纺织服饰(出口)') + '　')
        parts.append(_deep_fmt_sector(sector_map, '电子', '电子(出口链)') + '<br>')
        parts.append('<b>承压方向：</b>')
        parts.append(_deep_fmt_sector(sector_map, '交通运输', '交通运输(航空/造纸进口成本)') + '　')
        parts.append(_deep_fmt_sector(sector_map, '银行', '银行(外币负债)') + '<br>')
    else:
        parts.append('<b>避险方向：</b>')
        parts.append(_deep_fmt_sector(sector_map, '有色金属', '有色金属(黄金避险)') + '　')
        parts.append(_deep_fmt_sector(sector_map, '银行', '银行') + '　')
        parts.append(_deep_fmt_sector(sector_map, '公用事业', '公用事业(高股息)') + '<br>')

    parts.append('<span style="color:#64748B">数据来源：本地SectorRadarEngine真实涨跌幅</span>')
    return ''.join(parts)


def _deep_intl_risk(text):
    """国际政治风险与预期差：2-3个"如果A则B"具体场景"""
    sub = _deep_intl_subtype(text)
    if sub in ('关税贸易', '大选政治'):
        return ('风险与预期差：①若政治博弈转向、关税缓和→出口链与半导体可能快速反弹，但当前已price in的是悲观预期，反转弹性大；'
                '②若僵局持续→不确定性压制风险偏好，黄金避险逻辑延续但不追高；'
                '③警惕"口头强硬→市场恐慌→实际落地温和"的脉冲，事件驱动行情不可持续，应以政策落地文本为准而非表态。')
    elif sub == '美联储利率':
        return ('风险与预期差：①若降息幅度不及预期→前期靠流动性抬估值的成长股回调；'
                '②若通胀反复→加息预期重燃、美债收益率上行压制全市场估值；'
                '③点阵图与CPI数据是关键验证点，预期差引发的汇率与北向资金波动往往大于基本面冲击。')
    elif sub == '地缘冲突':
        return ('风险与预期差：①冲突升级→能源价格飙升、全球风险偏好骤降，通胀预期二次抬头；'
                '②若快速缓和→避险资产回落、风险资产反弹，前期抢跑的黄金/原油多头获利了结；'
                '③关注油价与黄金的持续性，单日脉冲不构成趋势，不追高。')
    elif sub == '汇率美元':
        return ('风险与预期差：①汇率单边波动直接影响出口企业汇兑损益与外债成本；'
                '②若央行中间价/逆周期因子出手干预→单边预期可能快速反转；'
                '③警惕跨境资金流动，北向资金连续流出时外资重仓板块承压放大。')
    else:
        return ('风险与预期差：①海外事件对A股多为情绪面冲击，需观察北向资金实际流向验证，而非仅看标题；'
                '②警惕"消息驱动→脉冲上涨→快速回落"的节奏；'
                '③若事件无后续跟进，情绪溢价会在1-2个交易日内消化，不提前下重注。')


def _deep_intl_observation(text):
    """国际政治操作观察：3-4个具体看什么指标"""
    sub = _deep_intl_subtype(text)
    if sub in ('关税贸易', '大选政治'):
        items = ['美元指数走势', '美元/人民币汇率', '美国关税政策落地文本', '中国出口同比数据', '北向资金流向']
    elif sub == '美联储利率':
        items = ['美联储点阵图与议息声明', '美国CPI/PCE数据', '10年期美债收益率', '北向资金流向']
    elif sub == '地缘冲突':
        items = ['布伦特原油价格', 'COMEX黄金价格', '冲突进展与停火谈判', 'VIX恐慌指数']
    elif sub == '汇率美元':
        items = ['美元指数', '人民币中间价与在岸价', '外汇储备变化', '北向资金净流入']
    else:
        items = ['美元指数', '人民币汇率', '北向资金', '两市成交额']
    return '观察信号：' + '、'.join(items[:4]) + '。不直接给买卖建议，仅为交易观察点。'


# ============================================================
# 期货/指数异动（新增类）：股指期货、宽基/行业指数涨跌、贴水升水
# ============================================================
def _deep_index_subtype(text):
    """指数/期指子类型：小盘期指 / 大盘期指 / 成长指数 / 期货基差 / 宽基期指。
    注意：先判指数名称(小盘/大盘/成长)，再判升贴水，避免'中证1000+贴水'被误判成纯基差。"""
    if any(k in text for k in ['中证1000', '中证500', '中证100', '小盘', '微盘', '中证']):
        return '小盘期指'
    if any(k in text for k in ['沪深300', '上证50', '上证180', '大盘', '蓝筹']):
        return '大盘期指'
    if any(k in text for k in ['创业板指', '创业板', '科创50', '成长']):
        return '成长指数'
    if any(k in text for k in ['贴水', '升水', '基差']):
        return '期货基差'
    return '宽基期指'


def _deep_index_core(text, t_short, wencai_voice):
    """期货/指数异动核心逻辑：说清指数代表什么 + 期货领先现货的传导路径"""
    sub = _deep_index_subtype(text)
    d = _deep_dir(text)
    parts = [f'事件：{t_short}。']

    # 指数本质
    essence = {
        '小盘期指': '中证1000/500代表A股中小市值成长股，成分股以题材、微盘、量化重仓标的为主，对流动性与情绪最敏感',
        '大盘期指': '沪深300/上证50代表大盘蓝筹与核心资产，外资与机构定价权高，走势反映宏观与权重股预期',
        '成长指数': '创业板指/科创50代表高成长板块(新能源、医药、科技)，估值高、对风险偏好和利率敏感',
        '期货基差': '期货价格相对现货的升贴水，是套保盘与多空情绪的直接量化信号',
        '宽基期指': '宽基股指期货整体反映A股风险偏好与机构仓位方向',
    }.get(sub, '宽基股指期货整体反映A股风险偏好')

    if sub == '期货基差':
        if d == 'down' or '贴水' in text:
            parts.append(f'{essence}。传导路径：期货贴水走阔→空头套保盘增加→期货领先现货定价悲观预期→若现货跟跌则确认下行，未跟跌则可能是量化集中调仓。')
        else:
            parts.append(f'{essence}。传导路径：期货升水→多头预期升温/套保盘离场→期货领涨现货→若现货放量跟涨则趋势确认。')
    else:
        if d == 'down':
            parts.append(f'{essence}。期货/指数急跌意味着市场对该风格短期预期急剧转弱，期货领跌往往领先现货，反映资金集中减仓或套保对冲；放量急跌通常是风险偏好快速下降与资金避险的信号。')
        elif d == 'up':
            parts.append(f'{essence}。期货/指数急涨意味着市场对该风格短期预期快速转强，期货领涨往往领先现货，反映资金集中加仓或空头回补；放量急涨通常是风险偏好回升与增量入场的信号。')
        else:
            parts.append(f'{essence}。指数异动反映市场对该风格定价的边际变化，期货端通常领先现货，需结合量能与期现联动判断是趋势还是脉冲。')

    if wencai_voice:
        parts.append(f'问财解读：{wencai_voice[:80]}。')
    return ''.join(parts)


def _deep_index_beneficiary(text, sector_map):
    """期货/指数异动受益/受损板块：按指数风格区分直接承压/间接受损/可能受益"""
    sub = _deep_index_subtype(text)
    d = _deep_dir(text)
    parts = ['<b>按指数风格映射板块（附本地真实涨跌幅）：</b><br>']

    if sub == '小盘期指':
        if d == 'down':
            parts.append('<b>直接承压：</b>')
            parts.append(_deep_fmt_sector(sector_map, '电子', '电子(小盘成长/题材)') + '　')
            parts.append(_deep_fmt_sector(sector_map, '计算机', '计算机(小盘题材)') + '　')
            parts.append(_deep_fmt_sector(sector_map, '传媒', '传媒(微盘/题材)') + '<br>')
            parts.append('<b>间接受损：</b>')
            parts.append(_deep_fmt_sector(sector_map, '非银金融', '非银金融(券商两融/成交)') + '<br>')
            parts.append('<b>可能受益(资金避险切换)：</b>')
            parts.append(_deep_fmt_sector(sector_map, '银行', '银行(大盘蓝筹)') + '　')
            parts.append(_deep_fmt_sector(sector_map, '公用事业', '公用事业(红利)') + '　')
            parts.append(_deep_fmt_sector(sector_map, '有色金属', '有色金属(黄金避险)') + '<br>')
        else:
            parts.append('<b>直接受益：</b>')
            parts.append(_deep_fmt_sector(sector_map, '电子', '电子(小盘成长/题材)') + '　')
            parts.append(_deep_fmt_sector(sector_map, '计算机', '计算机(小盘题材)') + '　')
            parts.append(_deep_fmt_sector(sector_map, '传媒', '传媒(微盘/题材)') + '<br>')
            parts.append('<b>可能承压(资金抽离)：</b>')
            parts.append(_deep_fmt_sector(sector_map, '银行', '银行(红利避险资金流出)') + '　')
            parts.append(_deep_fmt_sector(sector_map, '公用事业', '公用事业(红利)') + '<br>')
    elif sub in ('大盘期指', '宽基期指'):
        if d == 'down':
            parts.append('<b>直接承压：</b>')
            parts.append(_deep_fmt_sector(sector_map, '食品饮料', '食品饮料(核心资产)') + '　')
            parts.append(_deep_fmt_sector(sector_map, '银行', '银行(权重)') + '　')
            parts.append(_deep_fmt_sector(sector_map, '非银金融', '非银金融(券商)') + '<br>')
            parts.append('<b>可能受益：</b>')
            parts.append(_deep_fmt_sector(sector_map, '有色金属', '有色金属(黄金避险)') + '<br>')
        else:
            parts.append('<b>直接受益：</b>')
            parts.append(_deep_fmt_sector(sector_map, '食品饮料', '食品饮料(核心资产)') + '　')
            parts.append(_deep_fmt_sector(sector_map, '非银金融', '非银金融(券商弹性)') + '　')
            parts.append(_deep_fmt_sector(sector_map, '银行', '银行(权重)') + '<br>')
    elif sub == '成长指数':
        if d == 'down':
            parts.append('<b>直接承压：</b>')
            parts.append(_deep_fmt_sector(sector_map, '电力设备', '电力设备(新能源)') + '　')
            parts.append(_deep_fmt_sector(sector_map, '医药生物', '医药生物') + '　')
            parts.append(_deep_fmt_sector(sector_map, '电子', '电子(科技成长)') + '<br>')
        else:
            parts.append('<b>直接受益：</b>')
            parts.append(_deep_fmt_sector(sector_map, '电力设备', '电力设备(新能源)') + '　')
            parts.append(_deep_fmt_sector(sector_map, '电子', '电子(科技成长)') + '　')
            parts.append(_deep_fmt_sector(sector_map, '计算机', '计算机') + '<br>')
    else:  # 期货基差
        parts.append('<b>贴水走阔(空头占优)：</b>')
        parts.append(_deep_fmt_sector(sector_map, '非银金融', '非银金融(量化/中性策略)') + '　')
        parts.append(_deep_fmt_sector(sector_map, '电子', '电子(小盘对冲标的)') + '<br>')

    parts.append('<span style="color:#64748B">数据来源：本地SectorRadarEngine真实涨跌幅</span>')
    return ''.join(parts)


def _deep_index_risk(text):
    """期货/指数异动风险与预期差：具体场景"""
    sub = _deep_index_subtype(text)
    d = _deep_dir(text)
    base = ('①若期货贴水继续走阔(期货价低于现货)，说明套保盘增加，后续现货可能补跌；'
            '②若仅期货端异动而现货跟跌有限，可能是量化策略集中调仓/换月，不一定是趋势性下跌；'
            '③需警惕小盘指数连续下跌触发部分雪球产品敲入、量化中性策略止损，形成多杀多负反馈。')
    if sub == '大盘期指':
        base = ('①若沪深300/上证50异动但北向资金未同步流出，多为权重股护盘或被动资金调仓；'
                '②若蓝筹急涨而小票继续走弱，说明是指数行情而非全面牛市，赚指数不赚钱；'
                '③警惕权重股拉抬指数掩护个股出货，关注上涨家数而非仅看指数点位。')
    elif sub == '期货基差':
        base = ('①贴水走阔通常领先现货下跌1-2日，需等待现货确认；'
                '②基差极度收敛/升水时往往是情绪高点，警惕期现回归的反向波动；'
                '③期货移月换仓也会造成基差跳变，需剔除换月因素再判断。')
    elif sub == '成长指数':
        base = ('①成长指数对利率与流动性最敏感，若美债收益率同步上行则下跌延续；'
                '②急跌后若成交额萎缩，说明是杀估值而非逻辑破坏，反弹看量能；'
                '③警惕板块内部分化，龙头抗跌而小票补跌，警惕指数失真。')
    return '风险与预期差：' + base


def _deep_index_observation(text):
    """期货/指数异动操作观察：具体指标"""
    sub = _deep_index_subtype(text)
    if sub == '小盘期指':
        items = ['中证1000现货指数是否同步跟跌(期现联动确认)', '两市成交量是否放大(放量=资金真实出逃)',
                 '北向资金流向', '小盘股跌停家数(跌停潮=情绪冰点或有反弹)']
    elif sub == '大盘期指':
        items = ['沪深300现货指数与期货联动', '上涨家数占比(区分指数行情/普涨)',
                 '北向资金净买入', '两市成交额']
    elif sub == '成长指数':
        items = ['创业板指/科创50现货量能', '美债10年期收益率', '北向资金流向', '龙头股是否抗跌']
    else:
        items = ['期货与现货基差变化', '移月换仓日期', '两市成交量', '涨跌停家数']
    return '观察信号：' + '；'.join(items) + '。不直接给买卖建议，仅为交易观察点。'


def _deep_commodity_core(text, t_short, wencai_voice):
    """大宗商品核心逻辑：说清商品属性 + 上下游产业链利润再分配传导"""
    d = _deep_dir(text)
    parts = [f'事件：{t_short}。']
    # 识别具体商品
    if any(k in text for k in ['原油', '油价', 'OPEC', '石油', '布伦特', 'WTI']):
        essence = '原油是工业血液与通胀之母，价格直接影响炼化、航空、化工成本与全球通胀预期'
    elif any(k in text for k in ['黄金', '金价']):
        essence = '黄金是实际利率与避险情绪的反向定价品，实际利率下行+地缘风险时走强'
    elif any(k in text for k in ['铜', '铝', '铁矿石', '钢铁']):
        essence = '铜/铝/铁矿石是全球工业品景气度晴雨表(铜博士)，定价反映制造业与基建需求'
    elif any(k in text for k in ['煤炭', '煤价', '天然气']):
        essence = '煤炭/天然气是国内能源成本核心，影响火电、化工与CPI电价传导'
    elif any(k in text for k in ['锂', '钴', '镍', '稀土']):
        essence = '锂/稀土是新能源与战略金属上游，价格决定电池/磁材产业链利润分配'
    else:
        essence = '大宗商品价格变化本质是供需与库存周期的再定价'

    if d == 'up':
        parts.append(f'{essence}。传导路径：商品涨价→上游资源品盈利弹性释放→中下游成本抬升承压→替代需求与补库存启动，利润沿产业链向上游集中。')
    elif d == 'down':
        parts.append(f'{essence}。传导路径：商品跌价→上游资源品盈利承压、库存减值→中下游成本下降利好利润→去库存周期延续，利润沿产业链向下游转移。')
    else:
        parts.append(f'{essence}。传导路径：大宗商品供需边际变化→产业链上下游利润重新分配→上游资源品与中下游制造出现分化。')

    if wencai_voice:
        parts.append(f'问财解读：{wencai_voice[:80]}。')
    return ''.join(parts)


def _deep_commodity_beneficiary(text, sector_map):
    """大宗商品受益/受损板块：区分上游受益/下游承压"""
    parts = ['<b>产业链映射板块（附本地真实涨跌幅）：</b><br>']
    d = _deep_dir(text)
    if any(k in text for k in ['原油', '油价', 'OPEC', '石油']):
        parts.append('<b>上游受益：</b>')
        parts.append(_deep_fmt_sector(sector_map, '石油石化') + '　')
        parts.append(_deep_fmt_sector(sector_map, '煤炭', '煤炭(替代能源)') + '<br>')
        parts.append('<b>下游承压：</b>')
        parts.append(_deep_fmt_sector(sector_map, '交通运输', '交通运输(航油成本)') + '　')
        parts.append(_deep_fmt_sector(sector_map, '基础化工', '基础化工(原料成本)') + '<br>')
    elif any(k in text for k in ['黄金', '金价']):
        parts.append('<b>直接受益：</b>')
        parts.append(_deep_fmt_sector(sector_map, '有色金属', '有色金属(黄金)') + '　')
        parts.append(_deep_fmt_sector(sector_map, '银行', '银行') + '<br>')
    elif any(k in text for k in ['铜', '铝', '铁矿石', '钢铁']):
        parts.append('<b>上游受益：</b>')
        parts.append(_deep_fmt_sector(sector_map, '有色金属') + '　')
        parts.append(_deep_fmt_sector(sector_map, '钢铁') + '<br>')
        parts.append('<b>下游承压：</b>')
        parts.append(_deep_fmt_sector(sector_map, '机械设备') + '　')
        parts.append(_deep_fmt_sector(sector_map, '电力设备') + '<br>')
    elif any(k in text for k in ['煤炭', '煤价', '天然气']):
        parts.append('<b>受益：</b>')
        parts.append(_deep_fmt_sector(sector_map, '煤炭') + '　')
        parts.append(_deep_fmt_sector(sector_map, '石油石化') + '<br>')
        parts.append('<b>承压：</b>')
        parts.append(_deep_fmt_sector(sector_map, '公用事业', '公用事业(火电成本)') + '<br>')
    elif any(k in text for k in ['锂', '钴', '镍', '稀土']):
        parts.append('<b>上游受益：</b>')
        parts.append(_deep_fmt_sector(sector_map, '有色金属', '有色金属(锂/稀土)') + '<br>')
        parts.append('<b>下游成本受益/承压：</b>')
        parts.append(_deep_fmt_sector(sector_map, '电力设备', '电力设备(电池成本)') + '<br>')
    else:
        parts.append(_deep_fmt_sector(sector_map, '有色金属') + '　')
        parts.append(_deep_fmt_sector(sector_map, '煤炭') + '　')
        parts.append(_deep_fmt_sector(sector_map, '石油石化') + '<br>')
    parts.append('<span style="color:#64748B">数据来源：本地SectorRadarEngine真实涨跌幅</span>')
    return ''.join(parts)


def _deep_commodity_risk(text):
    """大宗商品风险与预期差：具体场景"""
    return ('风险与预期差：①商品价格受供需、库存、美元指数、地缘多重因素叠加，短期波动可能脱离基本面，'
            '若本次涨价无库存去化与开工率支撑，多为情绪脉冲；'
            '②警惕"涨价→股价脉冲→季报业绩验证不及预期"的节奏，资源股弹性大但反转时回撤也大；'
            '③若价格快速反转，前期涨幅较大的上游资源品回调幅度往往超过商品本身，不追高。')


def _deep_commodity_observation(text):
    """大宗商品操作观察"""
    items = ['相关商品期货价格走势与持仓量', '库存数据(交易所/社会库存)', '上下游开工率与产能利用率', '美元指数与北向资金']
    return '观察信号：' + '、'.join(items[:4]) + '。不直接给买卖建议，仅为交易观察点。'


# ============================================================
# 宏观数据（新增类）：CPI/PPI/PMI/GDP/社融/贸易等经济数据公布
# ============================================================
def _deep_macro_subtype(text):
    """宏观数据子类型：通胀 / 增长 / 货币信用 / 贸易 / 通用"""
    if any(k in text for k in ['CPI', 'PPI', '通胀', '通缩']):
        return '通胀'
    if any(k in text for k in ['GDP', 'PMI', '工业增加值', '社零', '社会消费品零售', '经济数据']):
        return '增长'
    if any(k in text for k in ['社融', 'M2', '新增贷款', '央行数据', '财政收支']):
        return '货币信用'
    if any(k in text for k in ['进出口', '贸易顺差', '出口', '进口', '失业率', '非农', '外汇储备']):
        return '贸易就业'
    return '通用'


def _deep_macro_core(text, t_short, wencai_voice):
    """宏观数据核心逻辑：说清数据含义 + 对A股的传导路径"""
    sub = _deep_macro_subtype(text)
    parts = [f'事件：{t_short}。']
    if sub == '通胀':
        parts.append('本质是物价与企业盈利成本的温度计。传导路径：CPI/PPI走势→判断通胀/通缩方向→制约货币政策空间(CPI高则难宽松)→PPI决定工业企业盈利→周期品与成长股估值分化。')
    elif sub == '增长':
        parts.append('本质是经济景气度的边际变化。传导路径：GDP/PMI/工业增加值→反映企业盈利与需求强弱→PMI站上/回落荣枯线50→顺周期(金融/地产链/中游制造)与大盘风格切换。')
    elif sub == '货币信用':
        parts.append('本质是金融体系放水与实体融资意愿。传导路径：社融/M2/新增贷款→信用扩张或收缩→决定市场流动性水位→成长股估值与风险偏好，宽信用利好顺周期，宽货币利好利率敏感板块。')
    elif sub == '贸易就业':
        parts.append('本质是外需与就业的健康度。传导路径：进出口/贸易顺差→反映全球需求与出口链景气→汇率与外汇储备→外资流向与A股出口链盈利；非农就业影响美联储政策预期。')
    else:
        parts.append('本质是宏观经济景气的边际读数。传导路径：经济数据→政策预期与流动性→行业盈利预期→A股风格与板块轮动。')
    if wencai_voice:
        parts.append(f'问财解读：{wencai_voice[:80]}。')
    return ''.join(parts)


def _deep_macro_beneficiary(text, sector_map):
    """宏观数据受益/受损板块"""
    sub = _deep_macro_subtype(text)
    parts = ['<b>宏观传导映射板块（附本地真实涨跌幅）：</b><br>']
    if sub == '通胀':
        parts.append('<b>通胀上行受益：</b>')
        parts.append(_deep_fmt_sector(sector_map, '有色金属', '有色金属(抗通胀)') + '　')
        parts.append(_deep_fmt_sector(sector_map, '煤炭', '煤炭') + '　')
        parts.append(_deep_fmt_sector(sector_map, '石油石化', '石油石化') + '<br>')
        parts.append('<b>通缩/成本承压：</b>')
        parts.append(_deep_fmt_sector(sector_map, '食品饮料', '食品饮料(提价能力)') + '　')
        parts.append(_deep_fmt_sector(sector_map, '电力设备', '电力设备(成长估值)') + '<br>')
    elif sub == '增长':
        parts.append('<b>经济回升受益(顺周期)：</b>')
        parts.append(_deep_fmt_sector(sector_map, '非银金融', '非银金融(券商)') + '　')
        parts.append(_deep_fmt_sector(sector_map, '房地产', '房地产') + '　')
        parts.append(_deep_fmt_sector(sector_map, '钢铁', '钢铁') + '<br>')
        parts.append('<b>增长乏力承压：</b>')
        parts.append(_deep_fmt_sector(sector_map, '银行', '银行(不良/息差)') + '<br>')
    elif sub == '货币信用':
        parts.append('<b>宽信用/宽货币受益：</b>')
        parts.append(_deep_fmt_sector(sector_map, '电子', '电子(成长)') + '　')
        parts.append(_deep_fmt_sector(sector_map, '电力设备', '电力设备') + '　')
        parts.append(_deep_fmt_sector(sector_map, '房地产', '房地产(信用扩张)') + '<br>')
        parts.append('<b>信用收缩承压：</b>')
        parts.append(_deep_fmt_sector(sector_map, '银行', '银行(信用风险)') + '<br>')
    elif sub == '贸易就业':
        parts.append('<b>出口强劲受益：</b>')
        parts.append(_deep_fmt_sector(sector_map, '纺织服饰', '纺织服饰(出口)') + '　')
        parts.append(_deep_fmt_sector(sector_map, '电子', '电子(出口链)') + '　')
        parts.append(_deep_fmt_sector(sector_map, '交通运输', '交通运输(航运)') + '<br>')
    else:
        parts.append(_deep_fmt_sector(sector_map, '非银金融', '非银金融(券商)') + '　')
        parts.append(_deep_fmt_sector(sector_map, '银行', '银行') + '<br>')
    parts.append('<span style="color:#64748B">数据来源：本地SectorRadarEngine真实涨跌幅</span>')
    return ''.join(parts)


def _deep_macro_risk(text):
    """宏观数据风险与预期差"""
    sub = _deep_macro_subtype(text)
    if sub == '通胀':
        return ('风险与预期差：①若CPI超预期上行→制约货币政策宽松空间，成长股估值承压；'
                '②若PPI持续为负→工业企业盈利仍在收缩，顺周期反弹缺乏业绩支撑；'
                '③警惕"数据公布即兑现"，市场往往提前交易预期，公布后反向波动。')
    elif sub == '增长':
        return ('风险与预期差：①若PMI仍在荣枯线下方→经济弱复苏，顺周期反弹是政策预期而非基本面；'
                '②若数据超预期但股市不涨→说明市场已price in，警惕利好出尽；'
                '③结构比总量重要，需看新动能(高技术制造) vs 旧动能(地产)谁更强。')
    elif sub == '货币信用':
        return ('风险与预期差：①社融放量但结构差(靠票据冲量)→实体融资需求仍弱，利好有限；'
                '②若M2与社融持续背离→资金淤积在金融体系，难转化为企业盈利；'
                '③宽货币预期落空(降准降息推迟)→利率敏感板块回调。')
    elif sub == '贸易就业':
        return ('风险与预期差：①出口高增若由抢出口/价格因素支撑→不可持续，需看数量；'
                '②若贸易顺差收窄→人民币汇率与外资承压；'
                '③非农超预期强劲→美联储降息推迟，压制全球成长股估值。')
    else:
        return ('风险与预期差：①宏观数据对A股多为预期交易，公布后易反向修正；'
                '②单一数据不构成趋势，需连续2-3个月数据验证方向；'
                '③警惕数据与政策预期共振或背离带来的风格剧烈切换。')


def _deep_macro_observation(text):
    """宏观数据操作观察"""
    sub = _deep_macro_subtype(text)
    if sub == '通胀':
        items = ['下月CPI/PPI预期', '大宗商品价格', '工业品出厂价格', '货币政策表态']
    elif sub == '增长':
        items = ['PMI新订单分项', '工业增加值同比', '社零数据', '大盘成交额']
    elif sub == '货币信用':
        items = ['M2与社融同比剪刀差', '新增贷款结构', 'DR007/银行间利率', '北向资金']
    elif sub == '贸易就业':
        items = ['出口同比分项', '人民币汇率', '外汇储备', '北向资金流向']
    else:
        items = ['统计局后续数据', '北向资金', '两市成交额', '政策表态']
    return '观察信号：' + '、'.join(items[:4]) + '。不直接给买卖建议，仅为交易观察点。'


def _deep_announcement_core(news, t_short, wencai_voice):
    """个股公告核心逻辑：公告类型 + 对个股与同板块的传导"""
    title = str(news.get('title', ''))
    content = str(news.get('content', ''))
    text = title + ' ' + content
    if any(k in text for k in ['重组', '收购', '并购']):
        essence = '并购重组本质是资产边界重塑，直接改变公司盈利与估值锚，并可能带动同题材(借壳/并购)炒作。'
    elif any(k in text for k in ['减持', '质押']):
        essence = '大股东减持/质押本质是筹码供给与现金流信号，直接压制个股估值，同板块情绪也会受拖累。'
    elif any(k in text for k in ['增持', '回购']):
        essence = '增持/回购本质是公司认为自身价值被低估，是信心信号，但需看金额占比与执行期限。'
    elif any(k in text for k in ['中标', '合同', '签约', '订单']):
        essence = '中标/大额合同本质是未来收入的确定性，关键看合同金额占年收入比重与毛利水平。'
    elif any(k in text for k in ['复牌', '停牌']):
        essence = '停复牌本质是重大事项(重组/监管)的信息释放窗口，复牌涨跌取决于停牌期间市场与事项方向。'
    elif any(k in text for k in ['分红', '配股', '定增', '股权激励']):
        essence = '分红/再融资/股权激励本质是利益分配与绑定机制，影响EPS、股本与管理层动力。'
    else:
        essence = '公司公告直接影响相关个股估值与流动性，并通过同板块联动扩散至产业链。'
    parts = [f'事件：{t_short}。{essence}']
    if wencai_voice:
        parts.append(f'问财解读：{wencai_voice[:80]}。')
    return ''.join(parts)


def _deep_announcement_risk(news):
    """个股公告风险与预期差"""
    title = str(news.get('title', ''))
    content = str(news.get('content', ''))
    text = title + ' ' + content
    base = ('风险与预期差：①若利好已在公告前放量上涨→"官宣即高点"，警惕利好兑现后获利回吐；'
            '②若事项需监管审批或多方同意→存在不确定性与延期风险，不应按落地线性外推；'
            '③个股异动会带动同板块情绪，但跟风标的无基本面支撑，回落更快。')
    if any(k in text for k in ['减持', '质押']):
        base = ('风险与预期差：①减持计划往往分批执行，压制区间可能持续数月而非单日；'
                '②若大股东高位减持→对中小股东是负面信号，警惕基本面恶化；'
                '③需区分被动减持(质押平仓)与主动减持，前者可能引发连锁抛压。')
    elif any(k in text for k in ['中标', '合同', '签约']):
        base = ('风险与预期差：①合同金额需对比公司年收入，占比小则对业绩影响有限；'
                '②收入确认存在跨期与回款风险，警惕纸面订单；'
                '③若公告前股价已大涨，利好兑现后易高开低走。')
    elif any(k in text for k in ['重组', '收购', '并购']):
        base = ('风险与预期差：①重组方案可能因监管/交易对方/估值分歧而流产或调整；'
                '②高商誉收购形成的商誉减值是未来业绩雷；'
                '③复牌后连续涨停打开时是风险点，不追高。')
    return base


def _deep_announcement_observation(news):
    """个股公告操作观察"""
    title = str(news.get('title', ''))
    content = str(news.get('content', ''))
    text = title + ' ' + content
    items = ['公告个股开盘量价与换手', '同板块龙头是否同步联动', '后续进展公告与监管问询', '大盘成交额与北向资金']
    if any(k in text for k in ['中标', '合同']):
        items[0] = '公告个股是否高开及封单强度'
    return '观察信号：' + '；'.join(items) + '。不直接给买卖建议，仅为交易观察点。'


def _deep_announcement_beneficiary(news, sector_map):
    """个股公告：提取新闻提及个股+同板块"""
    parts = ['<b>关联标的与板块：</b><br>']
    title = str(news.get('title', ''))
    content = str(news.get('content', ''))
    text = title + ' ' + content
    stock_list = news.get('stock_codes', news.get('stocks', []))
    if isinstance(stock_list, list) and stock_list:
        parts.append('<b>新闻提及个股：</b>')
        for st in stock_list[:5]:
            if isinstance(st, dict):
                n = st.get('name', '')
                c = str(st.get('code', '')).zfill(6)
                if n:
                    parts.append(f'{n}({c})　')
        parts.append('<br>')
    parts.append('<b>同板块关注：</b>')
    sector_keywords = {
        '半导体': '电子', '芯片': '电子', '新能源': '电力设备', '光伏': '电力设备',
        '医药': '医药生物', '医疗': '医药生物', '白酒': '食品饮料', '银行': '银行',
        '地产': '房地产', '军工': '国防军工', '机器人': '机械设备', 'AI': '计算机',
        '人工智能': '计算机', '汽车': '汽车', '消费电子': '电子',
    }
    matched = set()
    for kw, sec in sector_keywords.items():
        if kw in text and sec not in matched:
            matched.add(sec)
            parts.append(_deep_fmt_sector(sector_map, sec) + '　')
    if not matched:
        parts.append('需结合公司所属行业判断同板块联动。')
    parts.append('<br><span style="color:#64748B">数据来源：本地SectorRadarEngine真实涨跌幅</span>')
    return ''.join(parts)


def _deep_industry_core(text, t_short, wencai_voice):
    """行业政策/行业动态核心逻辑：政策性质 + 产业链传导"""
    if any(k in text for k in ['补贴', '扶持', '鼓励', '规划', '意见', '方案', '国务院', '发改委', '工信部']):
        essence = '本质是产业政策对供需与盈利预期的再分配。传导路径：政策定向扶持/监管收紧→对应行业产能、需求或准入变化→龙头集中度提升/出清→产业链上下游利润重新分配，政策主题通常先炒预期再验证业绩。'
    elif any(k in text for k in ['监管', '新规', '处罚', '整治', '规范', '行业标准']):
        essence = '本质是监管约束重塑行业竞争格局。传导路径：监管新规→合规成本上升/小厂出清→龙头市占率提升(短期阵痛长期利好)→被规范细分领域情绪承压。'
    else:
        essence = '本质是行业供需格局与景气度的边际变化。传导路径：行业动态→产业链上下游订单与价格→相关板块盈利预期→A股主题轮动。'
    parts = [f'事件：{t_short}。{essence}']
    if wencai_voice:
        parts.append(f'问财解读：{wencai_voice[:80]}。')
    return ''.join(parts)


def _deep_industry_risk(text):
    """行业政策风险与预期差"""
    if any(k in text for k in ['补贴', '扶持', '规划', '意见', '方案']):
        return ('风险与预期差：①政策从顶层文件到地方执行、资金到位存在时滞，短期是情绪炒作；'
                '②若补贴/规划力度低于市场预期→题材回落，警惕"预期打满→落地不及"；'
                '③区分真受益(有业绩弹性的龙头)与蹭概念，主题股退潮时回撤剧烈。')
    elif any(k in text for k in ['监管', '新规', '处罚', '整治']):
        return ('风险与预期差：①短期监管冲击情绪承压，长期看龙头集中度反而提升；'
                '②若监管从严超预期→相关细分领域杀估值；'
                '③需跟踪细则落地与执法力度，口头监管与实际处罚力度差异大。')
    return ('风险与预期差：①行业变化从预期到订单/业绩兑现存在时滞，警惕题材炒作后估值回归；'
            '②需区分短期情绪脉冲与长期产业趋势，后者才能穿越；'
            '③若板块已提前大涨，利好公布即兑现点。')


def _deep_industry_observation(text):
    """行业政策操作观察"""
    items = ['相关板块资金流向与成交持续性', '龙头股是否放量领涨', '后续细则/地方配套政策', '行业高频数据(价格/订单/开工率)']
    return '观察信号：' + '、'.join(items) + '。不直接给买卖建议，仅为交易观察点。'


def _deep_industry_beneficiary(text, sector_map):
    """行业政策：关键词匹配板块，区分直接受益/间接受益"""
    parts = ['<b>政策/行业传导映射板块（附本地真实涨跌幅）：</b><br>']
    keyword_map = {
        '半导体': '电子', '芯片': '电子', '集成电路': '电子', '消费电子': '电子', '苹果': '电子',
        '人工智能': '计算机', 'AI': '计算机', '大模型': '计算机', '算力': '计算机', '数据中心': '计算机',
        '新能源': '电力设备', '光伏': '电力设备', '风电': '电力设备', '储能': '电力设备', '锂电池': '电力设备',
        '新能源车': '汽车', '电动车': '汽车', '比亚迪': '汽车',
        '医药': '医药生物', '创新药': '医药生物', '医疗器械': '医药生物', '医疗': '医药生物',
        '白酒': '食品饮料', '消费': '食品饮料',
        '房地产': '房地产', '楼市': '房地产',
        '军工': '国防军工', '国防': '国防军工',
        '银行': '银行', '券商': '非银金融', '保险': '非银金融',
        '机器人': '机械设备', '工业母机': '机械设备',
        '煤炭': '煤炭', '石油': '石油石化', '原油': '石油石化',
        '黄金': '有色金属', '铜': '有色金属', '稀土': '有色金属',
        '5G': '通信', '光模块': '通信', '华为': '通信',
        '游戏': '传媒', '影视': '传媒',
        '农业': '农林牧渔', '猪肉': '农林牧渔',
        '家电': '家用电器',
        '纺织': '纺织服饰', '服装': '纺织服饰',
        '航运': '交通运输', '物流': '交通运输',
        '环保': '公用事业', '核电': '公用事业',
    }
    matched = []
    for kw, sec in keyword_map.items():
        # 不强制要求 sec 在 sector_map 中：雷达缺该板块时 _deep_fmt_sector 仍会显示纯名称
        if kw in text and sec not in matched:
            matched.append(sec)
    if matched:
        parts.append('<b>直接受益方向：</b>')
        for sec in matched[:4]:
            parts.append(_deep_fmt_sector(sector_map, sec) + '　')
        if len(matched) > 4:
            parts.append('<br><b>间接受益方向：</b>')
            for sec in matched[4:6]:
                parts.append(_deep_fmt_sector(sector_map, sec) + '　')
    else:
        # 即使sector_map暂无该板块，也给出上下游逻辑关联，绝不摆烂
        parts.append('<b>按产业链上下游关注：</b>上游资源/材料端、中游制造端、下游应用端，'
                     '可在板块雷达中按行业景气度进一步筛选龙头。')
    parts.append('<br><span style="color:#64748B">数据来源：本地SectorRadarEngine真实涨跌幅</span>')
    return ''.join(parts)


def _deep_logical_analysis(news, sector_map=None, wencai_voice=''):
    """问财无直接概念股时的深度逻辑分析，按新闻分类走不同传导路径。
    返回4段式dict。绝对禁止出现'问财未找到所以不分析'的摆烂内容。"""
    if sector_map is None:
        sector_map = _deep_get_sector_map()

    title = str(news.get('title', ''))
    content = str(news.get('content', ''))
    text = title + ' ' + content
    category = _deep_classify_news(news)
    sentiment = str(news.get('sentiment', '中性') or '中性')
    if sentiment not in ('利好', '利空', '中性'):
        sentiment = '中性'
    impact = str(news.get('intensity', news.get('impact', '中')) or '中')
    if impact not in ('强', '中', '弱'):
        impact = '中'
    t_short = title[:30]

    # 核心逻辑
    if category == '期货指数异动':
        core_logic = _deep_index_core(text, t_short, wencai_voice)
    elif category == '大宗商品':
        core_logic = _deep_commodity_core(text, t_short, wencai_voice)
    elif category == '宏观数据':
        core_logic = _deep_macro_core(text, t_short, wencai_voice)
    elif category == '国际政治':
        core_logic = _deep_intl_core(text, t_short, wencai_voice)
    elif category == '个股公告':
        core_logic = _deep_announcement_core(news, t_short, wencai_voice)
    else:  # 行业政策
        core_logic = _deep_industry_core(text, t_short, wencai_voice)

    # 受益/受损板块
    if category == '期货指数异动':
        beneficiary = _deep_index_beneficiary(text, sector_map)
    elif category == '大宗商品':
        beneficiary = _deep_commodity_beneficiary(text, sector_map)
    elif category == '宏观数据':
        beneficiary = _deep_macro_beneficiary(text, sector_map)
    elif category == '国际政治':
        beneficiary = _deep_intl_beneficiary(text, sector_map)
    elif category == '个股公告':
        beneficiary = _deep_announcement_beneficiary(news, sector_map)
    else:  # 行业政策
        beneficiary = _deep_industry_beneficiary(text, sector_map)

    # 风险与预期差
    if category == '期货指数异动':
        risk = _deep_index_risk(text)
    elif category == '大宗商品':
        risk = _deep_commodity_risk(text)
    elif category == '宏观数据':
        risk = _deep_macro_risk(text)
    elif category == '国际政治':
        risk = _deep_intl_risk(text)
    elif category == '个股公告':
        risk = _deep_announcement_risk(news)
    else:  # 行业政策
        risk = _deep_industry_risk(text)

    # 操作观察
    if category == '期货指数异动':
        observation = _deep_index_observation(text)
    elif category == '大宗商品':
        observation = _deep_commodity_observation(text)
    elif category == '宏观数据':
        observation = _deep_macro_observation(text)
    elif category == '国际政治':
        observation = _deep_intl_observation(text)
    elif category == '个股公告':
        observation = _deep_announcement_observation(news)
    else:  # 行业政策
        observation = _deep_industry_observation(text)

    return {
        'core_logic': core_logic,
        'beneficiary': beneficiary,
        'risk': risk,
        'observation': observation,
        'sentiment': sentiment,
        'impact': impact,
    }


# ============================================================
# 股票卡片 V2（可点击）
# ============================================================
class StockCardV2(QFrame):
    clicked = pyqtSignal(str, str)
    def __init__(self, stock_data: Dict, parent=None, compact=False):
        super().__init__(parent); self.data = stock_data; self.code = stock_data.get('code', ''); self.name = stock_data.get('name', ''); self.compact = compact
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f'QFrame{{background:{C.CARD};border:1px solid {C.BORDER};border-radius:12px;}}QFrame:hover{{border:1px solid {C.BLUE};background:{C.CARD_HOVER};}}')
        self._build_ui()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.clicked.emit(self.code, self.name)
        super().mousePressEvent(event)

    def _build_ui(self):
        layout = QVBoxLayout(self); layout.setContentsMargins(14, 10, 14, 10); layout.setSpacing(6)
        code = self.code; name = self.name; price = self.data.get('price', self.data.get('current_price', 0))
        # V2.8精简模式：只显示核心信息，减少控件数量（用于分页列表）
        if self.compact:
            # 直接写死compact UI，确保显示
            pct = self.data.get('pct_chg', self.data.get('today_change', 0))
            score = self.data.get('ai520_score', self.data.get('score', 0))
            concept = self.data.get('concept', '')
            if score >= 90: grade_color = C.RED
            elif score >= 80: grade_color = C.ORANGE
            elif score >= 70: grade_color = C.YELLOW
            elif score >= 60: grade_color = C.BLUE
            else: grade_color = C.TEXT3
            # 根据code查真实股票名字（引擎返回的name可能就是code）
            real_name = name
            if not real_name or real_name == code:
                try:
                    # 全局缓存，只加载一次
                    global _stock_code2name
                    if '_stock_code2name' not in globals():
                        from utils.stock_name_manager import get_all_stock_names
                        _name_map = get_all_stock_names()
                        _stock_code2name = {v: k for k, v in _name_map.items()}
                    real_name = _stock_code2name.get(code, concept or '--')
                except Exception as e:
                    print(f'[股票名查询失败] {code}: {e}', flush=True)
                    real_name = concept or '--'
            row = QHBoxLayout(); row.setSpacing(8)
            lbl_code = L(code, C.TEXT, 12, True); lbl_code.setFixedWidth(70); row.addWidget(lbl_code)
            lbl_name = L(real_name, C.TEXT2, 11, True); lbl_name.setFixedWidth(100); row.addWidget(lbl_name)
            # 核心题材标签：优先显示最近一次涨停原因（带日期），超1个月降级显示行业
            try:
                global _stock_theme_cache
                if '_stock_theme_cache' not in globals():
                    _stock_theme_cache = {}
                if code not in _stock_theme_cache:
                    # 查本地涨停原因数据库
                    try:
                        from data.limit_up_reason_db import get_last_limit_up_reason
                        from datetime import datetime, timedelta
                        reason, lu_date, lbc, lu_industry = get_last_limit_up_reason(code)
                        if reason and lu_date:
                            # 全部显示真涨停原因，不降级
                            tags = [t.strip() for t in reason.split('+') if t.strip()]
                            # 过滤掉"首板"、"X天X板"这种无效题材
                            bad_tags = {'首板', '二连板', '三连板', '换手板', '一字板', 'T字板'}
                            tags = [t for t in tags if t not in bad_tags and not t.endswith('板') or len(t) > 3]
                            if not tags:
                                # 过滤完空了，用概念兜底
                                from service.concept_service import get_stock_concepts
                                concepts, src = get_stock_concepts(code)
                                _stock_theme_cache[code] = (concepts if concepts else ([concept] if concept else []), 'concept')
                            else:
                                _stock_theme_cache[code] = (tags, 'limit_up')
                        else:
                            # 无涨停记录：用概念兜底
                            from service.concept_service import get_stock_concepts
                            concepts, src = get_stock_concepts(code)
                            _stock_theme_cache[code] = (concepts if concepts else ([concept] if concept else []), 'concept')
                    except Exception as e:
                        print(f'[题材查询失败] {code}: {e}', flush=True)
                        _stock_theme_cache[code] = ([concept] if concept else [], 'concept')
                themes, theme_type = _stock_theme_cache.get(code, ([], 'concept'))
            except Exception as e:
                print(f'[题材获取失败] {code}: {e}', flush=True)
                themes = [concept] if concept else []
                theme_type = 'concept'
            if themes:
                themes_text = '/'.join(themes)
                # 涨停原因/行业/概念全部用红色
                theme_color = C.RED
                lbl_themes = L(themes_text, theme_color, 10, True)
                lbl_themes.setMinimumWidth(160)
                row.addWidget(lbl_themes)
            price_str = f'{price:.2f}' if price and price > 0 else '--'
            lbl_price = L(price_str, C.TEXT, 12, True); lbl_price.setFixedWidth(60); lbl_price.setAlignment(Qt.AlignmentFlag.AlignRight); row.addWidget(lbl_price)
            pct_color = C.RED if pct >= 0 else C.GREEN
            pct_str = f'{pct:+.2f}%' if pct else '--'
            lbl_pct = L(pct_str, pct_color, 12, True); lbl_pct.setFixedWidth(70); lbl_pct.setAlignment(Qt.AlignmentFlag.AlignRight); row.addWidget(lbl_pct)
            score_str = f'AI520 {score:.0f}' if score > 0 else 'AI520 --'
            # 评分用黑色
            row.addWidget(L(score_str, C.TEXT, 12, True))
            row.addStretch()
            row.addWidget(L('点击K线 →', C.BLUE, 9, True))
            layout.addLayout(row)
            return
        pct = self.data.get('pct_chg', self.data.get('today_change', 0)); score = self.data.get('score', 0)
        signals = self.data.get('signals', []); risk_tags = self.data.get('risk_tags', []); details = self.data.get('details', {})
        if score >= 80: grade, grade_color = 'S', C.RED
        elif score >= 70: grade, grade_color = 'A', C.ORANGE
        elif score >= 60: grade, grade_color = 'B', C.YELLOW
        elif score >= 50: grade, grade_color = 'C', C.BLUE
        else: grade, grade_color = 'D', C.TEXT3
        row1 = QHBoxLayout()
        row1.addWidget(L(f'{grade}级', grade_color, 16, True)); row1.addSpacing(8)
        row1.addWidget(L(f'{code}', C.TEXT, 14, True)); row1.addStretch()
        pct_color = C.RED if pct >= 0 else C.GREEN
        row1.addWidget(L(f'{price:.2f}', C.TEXT, 13, True)); row1.addSpacing(8)
        row1.addWidget(L(f'{pct:+.2f}%', pct_color, 13, True)); row1.addSpacing(16)
        row1.addWidget(L(f'评分 {score:.0f}', C.PURPLE, 13, True))
        # V2.7.1：AI520相似度评分（AI520-1.0核心策略）
        ai520_score = self.data.get('ai520_score', 0)
        ai520_grade = self.data.get('ai520_grade', '')
        if ai520_score > 0:
            if ai520_score >= 90: a520_color = C.RED
            elif ai520_score >= 80: a520_color = C.ORANGE
            elif ai520_score >= 70: a520_color = C.YELLOW
            elif ai520_score >= 60: a520_color = C.BLUE
            else: a520_color = C.TEXT3
            row1.addSpacing(12); row1.addWidget(L(f'AI520 {ai520_score:.0f}', a520_color, 12, True))
            if ai520_grade:
                row1.addSpacing(4); row1.addWidget(L(ai520_grade, a520_color, 11, True))
            # 回踩类型
            pullback = self.data.get('ai520_pullback_type', self.data.get('pullback_type', ''))
            if pullback and pullback != 'NONE':
                row1.addSpacing(8); row1.addWidget(L(f'回踩{pullback}', C.CYAN, 10))
        # V2.7.1：AI520买点评分（与相似度评分分离）
        buy_score = self.data.get('buy_score', 0)
        if buy_score > 0:
            buy_color = C.RED if buy_score >= 80 else C.ORANGE if buy_score >= 70 else C.YELLOW if buy_score >= 60 else C.TEXT2
            row1.addSpacing(12); row1.addWidget(L(f'买点 {buy_score:.0f}', buy_color, 12, True))
        # V2.3：AI买点评分
        ai_score = self.data.get('ai_score', 0)
        ai_grade = self.data.get('ai_grade', '')
        if ai_score > 0:
            ai_color = C.RED if ai_grade in ('S+', 'S') else C.ORANGE if ai_grade == 'A' else C.YELLOW if ai_grade == 'B' else C.TEXT2
            row1.addSpacing(12); row1.addWidget(L(f'AI {ai_grade} {ai_score}', ai_color, 12, True))
        layout.addLayout(row1)
        # V2.3：买卖点信息
        buy_price = self.data.get('buy_price', 0)
        stop_loss = self.data.get('stop_loss', 0)
        tp1 = self.data.get('take_profit1', 0)
        tp2 = self.data.get('take_profit2', 0)
        deviation = self.data.get('deviation', 0)
        if buy_price > 0:
            bs_row = QHBoxLayout(); bs_row.setSpacing(8)
            dev_color = C.GREEN if abs(deviation) < 2 else C.YELLOW if abs(deviation) < 5 else C.RED
            bs_row.addWidget(L(f'买入:{buy_price:.2f}', C.GREEN, 10, True))
            bs_row.addWidget(L(f'止损:{stop_loss:.2f}', C.RED, 10))
            bs_row.addWidget(L(f'止盈1:{tp1:.2f}', C.ORANGE, 10))
            bs_row.addWidget(L(f'止盈2:{tp2:.2f}', C.YELLOW, 10))
            bs_row.addWidget(L(f'偏离:{deviation:+.1f}%', dev_color, 10))
            bs_row.addStretch(); layout.addLayout(bs_row)
        row2 = QHBoxLayout()
        ma5 = details.get('ma5', 0); ma9 = details.get('ma9', 0); ma20 = details.get('ma20', 0)
        kdj_j = details.get('kdj_j', 0); vol_ratio = details.get('vol_ratio', 0); change_25d = details.get('change_25d', 0); bias = details.get('bias_ma5', 0)
        for label, val, color in [('MA5', f'{ma5:.2f}' if ma5 else '--', C.TEXT2), ('MA9', f'{ma9:.2f}' if ma9 else '--', C.TEXT2), ('MA20', f'{ma20:.2f}' if ma20 else '--', C.TEXT2), ('KDJ-J', f'{kdj_j:.1f}' if kdj_j else '--', C.CYAN if kdj_j and kdj_j < 20 else C.TEXT2), ('量比', f'{vol_ratio:.2f}' if vol_ratio else '--', C.ORANGE if vol_ratio and vol_ratio > 1.2 else C.TEXT2), ('25日', f'{change_25d:+.1f}%' if change_25d else '--', C.RED if change_25d and change_25d > 15 else C.TEXT2), ('乖离', f'{bias:+.1f}%' if bias else '--', C.RED if bias and bias > 5 else C.TEXT2)]:
            item = QVBoxLayout(); item.addWidget(L(label, C.TEXT3, 9)); item.addWidget(L(val, color, 10, True)); row2.addLayout(item); row2.addSpacing(10)
        row2.addStretch(); layout.addLayout(row2)
        if signals:
            sig_row = QHBoxLayout(); sig_row.setSpacing(4)
            sig_row.addWidget(L(f'信号({len(signals)})', C.TEXT3, 10, True)); sig_row.addSpacing(4)
            core_colors = {'回调后启动': C.RED, '今日启动': C.RED, '20日涨停记忆': C.PURPLE, '回踩20日线': C.PURPLE, '重新启动': C.ORANGE, '低位启动': C.GREEN, '一阳穿线': C.CYAN, 'KDJ启动': C.CYAN, 'KDJ金叉': C.CYAN, '量价启动': C.ORANGE, '板块共振': C.GREEN, '均线多头': C.BLUE, '涨停回调': C.PURPLE, '横盘筑底': C.YELLOW}
            for sig in signals[:10]:
                color = core_colors.get(sig, C.TEXT2); sig_row.addWidget(SignalTag(sig, color))
            if len(signals) > 10: sig_row.addWidget(L(f'+{len(signals)-10}', C.TEXT3, 10))
            sig_row.addStretch(); layout.addLayout(sig_row)
        # V2.7.1：AI520 8维评分摘要（AI520-1.0）
        if ai520_score > 0:
            dim_row = QHBoxLayout(); dim_row.setSpacing(6)
            t_score = self.data.get('ai520_trend_score', self.data.get('trend_score', 0))
            s_score = self.data.get('ai520_strength_score', self.data.get('strength_memory_score', 0))
            m_score = self.data.get('ai520_moderate_score', self.data.get('moderate_rise_score', 0))
            p_score = self.data.get('ai520_pullback_score', self.data.get('pullback_score', 0))
            r_score = self.data.get('ai520_recovery_score', self.data.get('recovery_score', 0))
            k_score = self.data.get('ai520_kdj_score', self.data.get('kdj_score', 0))
            pos_score = self.data.get('ai520_position_score', self.data.get('position_score', 0))
            vp_score = self.data.get('ai520_volume_price_score', self.data.get('volume_price_score', 0))
            dim_text = f"8维: 趋{t_score}/20 强{s_score}/15 温{m_score}/15 回{p_score}/15 转{r_score}/15 K{k_score}/10 位{pos_score}/5 价{vp_score}/5"
            dim_label = L(dim_text, C.TEXT2, 9); dim_label.setWordWrap(True)
            dim_row.addWidget(dim_label); dim_row.addStretch()
            layout.addLayout(dim_row)
            # 策略版本标识
            ver_row = QHBoxLayout()
            ver_row.addWidget(L('策略: AI520-1.0', C.GREEN, 8))
            ver_row.addStretch()
            layout.addLayout(ver_row)
        if risk_tags:
            risk_row = QHBoxLayout(); risk_row.setSpacing(4)
            for risk in risk_tags[:4]: risk_row.addWidget(RiskTag(risk))
            risk_row.addStretch(); layout.addLayout(risk_row)
        reasons = self._generate_reasons(signals, details)
        if reasons:
            rl = L('入选：' + ' '.join(reasons[:4]), C.TEXT2, 10); rl.setWordWrap(True); layout.addWidget(rl)
        row6 = QHBoxLayout()
        industry = details.get('industry', ''); concepts = details.get('concepts', [])
        if industry: row6.addWidget(L(f'行业：{industry}', C.TEXT3, 9))
        if concepts: row6.addWidget(L(f'概念：{"、".join(concepts[:2])}', C.TEXT3, 9))
        row6.addStretch(); row6.addWidget(L('点击查看K线 →', C.BLUE, 9, True)); layout.addLayout(row6)

    def _build_compact_ui(self, layout, code, name, price):
        """V2.8精简模式：只显示核心信息，大幅减少控件数量"""
        pct = self.data.get('pct_chg', self.data.get('today_change', 0))
        score = self.data.get('ai520_score', self.data.get('score', 0))
        ai520_grade = self.data.get('ai520_grade', '')
        buy_price = self.data.get('buy_price', 0)
        stop_loss = self.data.get('stop_loss', 0)
        industry = self.data.get('details', {}).get('industry', '')
        # 核心题材（concept优先，其次industry）
        core_topic = self.data.get('concept', '')
        if not core_topic:
            core_topic = self.data.get('theme', '')
        if not core_topic:
            core_topic = industry
        # 如果name就是code（引擎返回不对），用concept当名称
        display_name = name if name and name != code else core_topic or ''
        
        # 等级颜色
        if score >= 90: grade_color = C.RED
        elif score >= 80: grade_color = C.ORANGE
        elif score >= 70: grade_color = C.YELLOW
        elif score >= 60: grade_color = C.BLUE
        else: grade_color = C.TEXT3
        
        # 单行核心信息（固定列宽对齐）
        row = QHBoxLayout()
        row.setSpacing(8)
        pct_color = C.RED if pct >= 0 else C.GREEN
        # 第1列：代码（固定宽度70px）
        lbl_code = L(f'{code}', C.TEXT, 12, True)
        lbl_code.setFixedWidth(70)
        row.addWidget(lbl_code)
        # 第2列：名称/题材（固定宽度100px）
        lbl_name = L(display_name or '--', C.TEXT2, 11, True)
        lbl_name.setFixedWidth(100)
        row.addWidget(lbl_name)
        # 第3列：价格（固定宽度60px，右对齐）
        price_str = f'{price:.2f}' if price and price > 0 else '--'
        lbl_price = L(price_str, C.TEXT, 12, True)
        lbl_price.setFixedWidth(60)
        lbl_price.setAlignment(Qt.AlignmentFlag.AlignRight)
        row.addWidget(lbl_price)
        # 第4列：涨幅（固定宽度70px，右对齐）
        pct_str = f'{pct:+.2f}%' if pct else '--'
        lbl_pct = L(pct_str, pct_color, 12, True)
        lbl_pct.setFixedWidth(70)
        lbl_pct.setAlignment(Qt.AlignmentFlag.AlignRight)
        row.addWidget(lbl_pct)
        # 第5列：AI520评分
        score_str = f'AI520 {score:.0f}' if score > 0 else 'AI520 --'
        lbl_score = L(score_str, grade_color, 12, True)
        row.addWidget(lbl_score)
        if ai520_grade:
            lbl_grade = L(ai520_grade, grade_color, 11, True)
            row.addSpacing(4)
            row.addWidget(lbl_grade)
        row.addStretch()
        row.addWidget(L('点击K线 →', C.BLUE, 9, True))
        layout.addLayout(row)

    def _generate_reasons(self, signals, details):
        reasons = []
        if '20日涨停记忆' in signals: reasons.append('①20日涨停记忆')
        if '涨停回调' in signals: reasons.append('②涨停后回调')
        if '回调后启动' in signals or '今日启动' in signals: reasons.append('③重新站上MA5')
        if '低位启动' in signals: reasons.append('④低位启动结构')
        if '回踩20日线' in signals: reasons.append('⑤回踩MA20后重启')
        if '均线多头' in signals: reasons.append('⑥MA5>MA9>MA20')
        if 'KDJ启动' in signals or 'KDJ低位' in signals: reasons.append('⑦KDJ低位启动')
        if '温和放量' in signals or '量价启动' in signals: reasons.append('⑧成交量温和放大')
        if '板块共振' in signals: reasons.append('⑨板块资金流入')
        if '一阳穿线' in signals: reasons.append('⑩一阳突破均线')
        if not reasons and signals: reasons.append(f'触发{len(signals)}个信号')
        return reasons


# ============================================================
# 首页 - 作战中控台
# ============================================================
class BattleConsoleHomeV2(QWidget):
    stock_clicked = pyqtSignal(str, str)
    def __init__(self, parent=None):
        super().__init__(parent); self.scan_thread = None; self.all_results = []
        p_start("BattleConsoleHomeV2初始化")
        print("[作战中台] __init__开始，调用_build_ui...", flush=True)
        self._build_ui()
        print("[作战中台] _build_ui完成，调用_start_timer...", flush=True)
        self._start_timer()
        print("[作战中台] _start_timer完成", flush=True)
        p_end("BattleConsoleHomeV2._build_ui+_start_timer")
        # V2.2 市场态势更新定时器（每30秒）
        # V2.2 定时任务检查定时器（每分钟检查09:30/14:45/15:05）
        print("[作战中台] 开始创建_scheduler_timer...", flush=True)
        self._scheduler_timer = QTimer(self); self._scheduler_timer.timeout.connect(self._check_scheduled_tasks); self._scheduler_timer.start(60000)
        print("[作战中台] _scheduler_timer创建完成", flush=True)
        p_end("BattleConsoleHomeV2初始化")
        print("[作战中台] __init__完成", flush=True)

    def _build_ui(self):
        main = QVBoxLayout(self); main.setContentsMargins(12, 8, 12, 8); main.setSpacing(8)
        # 顶部控制栏
        ctrl = QHBoxLayout()
        ctrl.addWidget(L('🎯 AI520选股雷达', C.TEXT, 15, True)); ctrl.addStretch()
        self.scan_btn_small = QPushButton('🔄 重新扫描'); self.scan_btn_small.setFixedHeight(24); self.scan_btn_small.setStyleSheet(f'QPushButton{{background:#AF52DE;color:white;border:none;border-radius:4px;padding:0 10px;font-size:11px;}}QPushButton:hover{{background:#9333EA;}}')
        self.scan_btn_small.clicked.connect(self._run_ai520_scan); ctrl.addWidget(self.scan_btn_small); ctrl.addSpacing(8)
        self.status_label = L('待机', C.TEXT3, 11); ctrl.addWidget(self.status_label)
        # 筛选栏
        filter_bar = QHBoxLayout()
        self.grade_filter = QComboBox(); self.grade_filter.addItems(['全部等级', 'S级', 'A级', 'B级', 'C级']); self.grade_filter.setFixedHeight(26); self.grade_filter.setStyleSheet(f'QComboBox{{background:rgba(255,255,255,0.7);color:{C.TEXT};border:1px solid rgba(0,0,0,0.1);border-radius:8px;padding:0 8px;font-size:11px;}}')
        self.grade_filter.currentIndexChanged.connect(self._apply_filter); filter_bar.addWidget(self.grade_filter); filter_bar.addSpacing(8)
        self.signal_filter = QComboBox(); self.signal_filter.addItems(['全部信号', '20日涨停记忆', '涨停回调', '回调后启动', '回踩20日线', '低位启动', '站5', '穿九', '站二十', 'KDJ金叉', 'KDJ启动', '温和放量', '量价启动', '横盘筑底', '板块共振', '一阳穿线']); self.signal_filter.setFixedHeight(26); self.signal_filter.setStyleSheet(f'QComboBox{{background:rgba(255,255,255,0.7);color:{C.TEXT};border:1px solid rgba(0,0,0,0.1);border-radius:8px;padding:0 8px;font-size:11px;}}')
        self.signal_filter.currentIndexChanged.connect(self._apply_filter); filter_bar.addWidget(self.signal_filter); filter_bar.addSpacing(8)
        # 搜索股票（替换原「全部风险」+「按评分」筛选，真实全市场搜索）
        self.search_input = QLineEdit(); self.search_input.setPlaceholderText('🔍 搜索代码/名称，如：600519 或 茅台'); self.search_input.setFixedHeight(26); self.search_input.setFixedWidth(180); self.search_input.setClearButtonEnabled(True); self.search_input.setStyleSheet(f'QLineEdit{{background:rgba(255,255,255,0.7);color:{C.TEXT};border:1px solid rgba(0,0,0,0.1);border-radius:8px;padding:0 8px;font-size:11px;}}QLineEdit:focus{{border:1px solid #AF52DE;}}')
        self.search_input.textChanged.connect(self._on_search_text_changed); self.search_input.returnPressed.connect(self._on_search_text_changed); filter_bar.addWidget(self.search_input); filter_bar.addSpacing(8)
        self.search_btn = QPushButton('🔍 搜索'); self.search_btn.setFixedHeight(26); self.search_btn.setStyleSheet(f'QPushButton{{background:#AF52DE;color:white;border:none;border-radius:8px;padding:0 12px;font-size:11px;}}QPushButton:hover{{background:#9333EA;}}')
        self.search_btn.clicked.connect(self._on_search_text_changed); filter_bar.addWidget(self.search_btn); filter_bar.addStretch()
        self.result_count = L('', C.TEXT2, 10); filter_bar.addWidget(self.result_count)
        ctrl.addLayout(filter_bar)
        main.addLayout(ctrl)
        # 真实搜索股票结果浮层（默认隐藏，输入关键词后显示全市场匹配）
        self.search_results = QListWidget()
        self.search_results.setStyleSheet(f'QListWidget{{background:rgba(255,255,255,0.96);color:{C.TEXT};border:1px solid rgba(0,0,0,0.12);border-radius:8px;font-size:12px;}}QListWidget::item{{padding:6px 10px;border-bottom:1px solid rgba(0,0,0,0.05);}}QListWidget::item:hover{{background:rgba(175,82,222,0.12);}}QListWidget::item:selected{{background:rgba(175,82,222,0.22);}}')
        self.search_results.itemClicked.connect(self._on_search_result_clicked)
        self.search_results.hide()
        main.addWidget(self.search_results)
        # 进度条
        self.progress = QProgressBar(); self.progress.setFixedHeight(16); self.progress.setTextVisible(True); self.progress.setStyleSheet(f'QProgressBar{{background:rgba(0,0,0,0.05);border:1px solid rgba(0,0,0,0.06);border-radius:8px;text-align:center;color:{C.TEXT2};font-size:10px;}}QProgressBar::chunk{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #2563EB,stop:1 #0EA5E9);border-radius:7px;}}')
        main.addWidget(self.progress)
        # V3.0：市场全景作战地图（用户要求删除）
        self.market_risk_panel = None
        # 主体：左右分栏 - 左AI520列表，右主力启动雷达
        body = QHBoxLayout(); body.setSpacing(10)
        # 左栏：AI520智能选股列表
        left = QWidget(); left_layout = QVBoxLayout(left); left_layout.setContentsMargins(0, 0, 0, 0); left_layout.setSpacing(6)
        ai520_title_row = QHBoxLayout()
        ai520_title_row.addWidget(L('🎯 AI520智能选股（AI520-1.0）', C.TEXT, 12, True))
        ai520_title_row.addStretch()
        left_layout.addLayout(ai520_title_row)
        # V2.8：信号跟踪面板（用户要求删除）
        self.signal_tracking_panel = None
        # 调试：确保事件循环不被阻塞
        try:
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            print("[作战中台] 信号跟踪面板后事件循环已处理", flush=True)
        except Exception:
            pass
        print("[作战中台] 开始创建股票滚动区域...", flush=True)
        self.stock_scroll = QScrollArea(); self.stock_scroll.setWidgetResizable(True); self.stock_scroll.setStyleSheet(f'QScrollArea{{background:transparent;border:none;}}QScrollBar:vertical{{background:transparent;width:8px;}}QScrollBar::handle:vertical{{background:rgba(0,0,0,0.15);border-radius:4px;}}QScrollBar::handle:vertical:hover{{background:rgba(0,0,0,0.25);}}')
        print("[作战中台] 股票滚动区域创建完成", flush=True)
        self.stock_container = QWidget(); self.stock_layout = QVBoxLayout(self.stock_container); self.stock_layout.setContentsMargins(0, 0, 0, 0); self.stock_layout.setSpacing(6); self.stock_layout.addStretch()
        print("[作战中台] 股票容器创建完成", flush=True)
        self.stock_scroll.setWidget(self.stock_container); left_layout.addWidget(self.stock_scroll, 1)
        print("[作战中台] 股票滚动区域添加到布局完成", flush=True)
        body.addWidget(left, 1)
        # 右栏已删除，只保留AI520占满整行
        main.addLayout(body, 1)
        print("[作战中台] _build_ui完成", flush=True)
        # 启动时自动加载上次AI520结果
        self._load_ai520_cache()

    # ============================================================
    # 真实搜索股票（全市场代码/名称匹配，点击跳转个股分析页）
    # ============================================================
    _STOCK_NAMES_CACHE = None

    def _get_stock_names(self):
        """懒加载全市场股票代码→名称映射（约5200只）"""
        if BattleConsoleHomeV2._STOCK_NAMES_CACHE is None:
            try:
                import json, os
                p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'stock_names_full.json')
                with open(p, 'r', encoding='utf-8') as f:
                    BattleConsoleHomeV2._STOCK_NAMES_CACHE = json.load(f)
                print(f"[搜索] 全市场股票库已加载: {len(BattleConsoleHomeV2._STOCK_NAMES_CACHE)}只", flush=True)
            except Exception as e:
                print(f"[搜索] 股票库加载失败: {e}", flush=True)
                BattleConsoleHomeV2._STOCK_NAMES_CACHE = {}
        return BattleConsoleHomeV2._STOCK_NAMES_CACHE

    def _on_search_text_changed(self):
        """输入变化：全市场真实搜索（浮层）+ 候选区过滤"""
        kw = self.search_input.text().strip().upper().replace(' ', '')
        if kw:
            matches = self._search_all_stocks(kw)
            self._show_search_results(matches)
        else:
            self.search_results.hide()
        self._apply_filter()

    def _search_all_stocks(self, kw):
        """在全市场股票库中按代码/名称模糊匹配，返回 [(code, name), ...]"""
        names = self._get_stock_names()
        if not names:
            return []
        out = []
        for code, name in names.items():
            if len(out) >= 12:
                break
            # 代码前缀/包含匹配
            if code.startswith(kw) or kw in code:
                out.append((code, name))
                continue
            # 名称包含匹配（去空格）
            n = name.replace(' ', '').upper()
            if kw in n:
                out.append((code, name))
        return out

    def _show_search_results(self, matches):
        """显示搜索结果列表"""
        self.search_results.clear()
        if not matches:
            self.search_results.addItem('未找到匹配的股票，换个关键词试试')
            self.search_results.setFixedHeight(34)
        else:
            for code, name in matches:
                item = QListWidgetItem(f'{code}  {name}')
                item.setToolTip('点击查看行情/K线')
                self.search_results.addItem(item)
            h = min(len(matches), 8) * 30 + 6
            self.search_results.setFixedHeight(h)
        self.search_results.show()

    def _on_search_result_clicked(self, item):
        """点击搜索结果 → 跳转个股分析页查看真实行情/K线"""
        text = item.text().strip()
        if not text or text.startswith('未找到'):
            return
        parts = text.split()
        code = parts[0]
        name = parts[1] if len(parts) > 1 else code
        print(f"[搜索] 跳转查看: {name}({code})", flush=True)
        self.stock_clicked.emit(code, name)
        self.search_input.clear()
        self.search_results.hide()

    def _load_ai520_cache(self):
        """启动时自动加载上次AI520扫描结果"""
        try:
            import json, os
            cache_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'ai520_last_result.json')
            if not os.path.exists(cache_path): return
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            signals = data.get('signals', [])
            total = data.get('total', 0)
            t = data.get('time', '')
            if signals:
                self._render_ai520_candidates(signals, total)
                self.status_label.setText(f'上次扫描结果: {len(signals)}只 (扫描时间: {t})')
                print(f"[AI520] 已加载上次缓存: {len(signals)}只", flush=True)
        except Exception as e:
            print(f"[AI520] 加载缓存失败: {e}", flush=True)

    def _toggle_signal_tracking(self):
        """V2.8：切换信号跟踪面板显示/隐藏"""
        try:
            if hasattr(self, 'signal_tracking_panel') and self.signal_tracking_panel:
                visible = self.signal_tracking_panel.isVisible()
                self.signal_tracking_panel.setVisible(not visible)
                self.signal_tracking_btn.setText('📊 信号跟踪' if visible else '📊 隐藏跟踪')
        except Exception as e:
            print(f"[V2.8接入] 信号跟踪切换失败: {e}", flush=True)

    def _start_timer(self):
        pass  # V2.4已删除热门板块定时器

    def _start_scan(self):
        if self.scan_thread and self.scan_thread.isRunning(): return
        # V2.8：设置AI520扫描标志（用于K线增量更新互斥）
        self._ai520_scanning = True
        # 同步到主窗口
        parent = self.parent()
        while parent:
            if hasattr(parent, '_ai520_scanning'):
                parent._ai520_scanning = True
                break
            parent = parent.parent()
        print("[V2.8互斥] AI520扫描开始，K线增量更新将等待", flush=True)
        max_stocks = 0  # 全市场扫描
        self.status_label.setText('扫描中...')
        self.progress.setValue(0)
        self.scan_thread = ScanThread(max_stocks=max_stocks, min_score=40)
        self.scan_thread.progress.connect(self._on_progress); self.scan_thread.finished.connect(self._on_scan_finished)
        self.scan_thread.start()

    def _stop_scan(self):
        if self.scan_thread and self.scan_thread.isRunning():
            service = get_real_scan_service(); service.stop_scan()
            self.status_label.setText('已停止')

    def _on_progress(self, current, total, candidates, s, a, b):
        pct = int(current / total * 100) if total > 0 else 0
        self.progress.setValue(pct); self.status_label.setText(f'扫描中 {current}/{total} 候选{candidates} (S:{s} A:{a} B:{b})')

    def _on_scan_finished(self, result):
        self.status_label.setText('扫描完成')
        stocks = result.get('stocks', []); total = result.get('total_scanned', 0)
        self.all_results = stocks
        # AI二次筛选（V2.3新增）
        try:
            service = get_real_scan_service()
            ai_filtered = service.ai_secondary_filter(stocks, min_ai_score=40)
            self.ai_results = ai_filtered
            s_plus = len([s for s in ai_filtered if s.get('ai_grade') == 'S+'])
            s_cnt = len([s for s in ai_filtered if s.get('ai_grade') == 'S'])
            a_cnt = len([s for s in ai_filtered if s.get('ai_grade') == 'A'])
            b_cnt = len([s for s in ai_filtered if s.get('ai_grade') == 'B'])
            obs_cnt = len([s for s in ai_filtered if s.get('ai_grade') == '观察'])
            print(f"[AI筛选] 初筛{len(stocks)}只 → AI二次筛选{len(ai_filtered)}只 (S+:{s_plus} S:{s_cnt} A:{a_cnt} B:{b_cnt} 观察:{obs_cnt})", flush=True)
            self.status_label.setText(f'完成 扫描{total}只 初筛{len(stocks)}只 AI买点{len(ai_filtered)}只 (S+:{s_plus} S:{s_cnt} A:{a_cnt} B:{b_cnt})')
        except Exception as e:
            print(f"[AI筛选] 失败: {e}", flush=True)
            self.ai_results = stocks
            self.status_label.setText(f'完成 扫描{total}只 候选{len(stocks)}只 (AI筛选失败)')
        self._apply_filter()
        self.progress.setValue(100)
        # 日终缓存（V2.3新增）
        try:
            service = get_real_scan_service()
            service.save_daily_cache(result)
        except Exception as e:
            print(f"[日终缓存] 保存失败: {e}", flush=True)

    def _apply_filter(self):
        """应用筛选+搜索（作用于AI520候选列表，基于原始扫描结果重新过滤）"""
        try:
            if not hasattr(self, '_all_signals_orig') or not self._all_signals_orig:
                return
            filtered = list(self._all_signals_orig)
            grade = self.grade_filter.currentText()
            if grade != '全部等级':
                g_map = {'S级': 80, 'A级': 70, 'B级': 60, 'C级': 50}
                threshold = g_map.get(grade, 0); next_t = {'S级': 200, 'A级': 80, 'B级': 70, 'C级': 60}.get(grade, 200)
                filtered = [s for s in filtered if threshold <= s.get('ai520_score', s.get('score', 0)) < next_t]
            sig = self.signal_filter.currentText()
            if sig != '全部信号': filtered = [s for s in filtered if sig in s.get('signals', [])]
            # 搜索股票：按代码/名称/概念题材模糊匹配
            kw = self.search_input.text().strip().upper()
            if kw:
                filtered = [s for s in filtered if kw in str(s.get('code', '')).upper() or kw in str(s.get('name', '')).upper() or kw in str(s.get('concept', '')).upper()]
            # 默认按评分排序（替代原「按评分」下拉框）
            filtered.sort(key=lambda x: (x.get('ai520_score', x.get('score', 0)), x.get('buy_score', 0)), reverse=True)
            self._all_signals = filtered
            self._current_page = 0
            self._render_current_page()
            total_pages = (len(filtered) + self._page_size - 1) // self._page_size
            self.result_count.setText(f'筛选结果 {len(filtered)}只 第{self._current_page+1}/{total_pages}页')
        except Exception as e:
            print(f"[首页] 筛选错误: {e}", flush=True)
            import traceback; traceback.print_exc()

    # ============================================================
    # V2.2 AI-520作战闭环
    # ============================================================
    def _get_v22_service(self):
        """获取V2.2作战闭环服务（懒加载）"""
        if not hasattr(self, '_v22_service') or self._v22_service is None:
            try:
                from services.v22_combat_service import get_v22_combat_service
                self._v22_service = get_v22_combat_service()
            except Exception as e:
                print(f"[V22] 服务加载失败: {e}", flush=True)
                self._v22_service = None
        return self._v22_service

    def _run_ai520_scan(self):
        """执行AI-520全市场扫描"""
        svc = self._get_v22_service()
        if not svc:
            self.status_label.setText('AI-520服务未加载')
            return
        self.scan_btn_small.setEnabled(False)
        self.status_label.setText('AI-520扫描中...')
        # 后台线程执行
        class AI520Thread(QThread):
            finished = pyqtSignal(dict)
            def run(self):
                try:
                    result = svc.run_ai520_scan(scan_source='manual', push_wechat=True)
                    self.finished.emit(result)
                except Exception as e:
                    self.finished.emit({'success': False, 'error': str(e), 'signals': []})
        self._ai520_thread = AI520Thread()
        self._ai520_thread.finished.connect(self._on_ai520_finished)
        self._ai520_thread.start()

    def _on_ai520_finished(self, result):
        """AI-520扫描完成"""
        # V2.8：清除AI520扫描标志（K线增量更新互斥）
        self._ai520_scanning = False
        parent = self.parent()
        while parent:
            if hasattr(parent, '_ai520_scanning'):
                parent._ai520_scanning = False
                break
            parent = parent.parent()
        print("[V2.8互斥] AI520扫描完成，K线增量更新可继续", flush=True)
        self.scan_btn_small.setEnabled(True)
        if result.get('success'):
            signals = result.get('signals', [])
            total = result.get('total_scanned', 0)
            grades = defaultdict(int)
            for s in signals:
                grades[s.get('grade', 'D')] += 1
            self.status_label.setText(f'AI-520完成: 扫描{total}只 信号{len(signals)}只 已推送企业微信')
            print(f"[V22] AI-520扫描完成: {len(signals)}只信号", flush=True)
            # V2.7.1：将AI520扫描结果渲染到候选区域
            self._render_ai520_candidates(signals, total)
            # 保存到本地，下次启动自动加载
            try:
                import json, os
                cache_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'ai520_last_result.json')
                with open(cache_path, 'w', encoding='utf-8') as f:
                    json.dump({'signals': signals, 'total': total, 'time': str(datetime.now())[:19]}, f, ensure_ascii=False)
            except Exception as e:
                print(f"[AI520] 保存缓存失败: {e}", flush=True)
        else:
            self.status_label.setText(f'AI-520失败: {result.get("error", "未知错误")}')

    def _render_ai520_candidates(self, signals, total_scanned=0):
        """V2.8：将AI520扫描结果渲染到候选区域（分页显示，每页50只，避免UI阻塞）"""
        try:
            # 保存所有信号数据（用于分页）
            self._all_signals = sorted(
                signals,
                key=lambda x: (x.get('ai520_score', x.get('score', 0)), x.get('buy_score', 0)),
                reverse=True
            )
            self._all_signals_orig = list(self._all_signals)  # 保存原始数据，供筛选/搜索每次重新过滤
            self._current_page = 0
            self._page_size = 50
            
            # 统计
            sorted_signals = self._all_signals
            s_cnt = len([s for s in sorted_signals if s.get('ai520_score', s.get('score', 0)) >= 90])
            a_cnt = len([s for s in sorted_signals if 80 <= s.get('ai520_score', s.get('score', 0)) < 90])
            b_cnt = len([s for s in sorted_signals if 70 <= s.get('ai520_score', s.get('score', 0)) < 80])
            c_cnt = len([s for s in sorted_signals if 60 <= s.get('ai520_score', s.get('score', 0)) < 70])
            max_score = max([s.get('ai520_score', s.get('score', 0)) for s in sorted_signals], default=0)
            
            # 渲染当前页
            self._render_current_page()
            
            # 更新结果计数
            total_pages = (len(sorted_signals) + self._page_size - 1) // self._page_size
            self.result_count.setText(f'AI520候选 {len(sorted_signals)}只 (S:{s_cnt} A:{a_cnt} B:{b_cnt} C:{c_cnt} 最高{max_score:.0f}) 第{self._current_page+1}/{total_pages}页')
            # 更新进度条
            self.progress.setValue(100)
            print(f"[AI520渲染] 候选区域已更新: {len(sorted_signals)}只 分页{total_pages}页 (S:{s_cnt} A:{a_cnt} B:{b_cnt} C:{c_cnt} 最高{max_score:.0f})", flush=True)
        except Exception as e:
            print(f"[AI520渲染] 错误: {e}", flush=True)
            import traceback
            traceback.print_exc()

    def _render_current_page(self):
        """V2.8：渲染当前页的股票卡片（精简模式）"""
        try:
            # 清空候选区域（保留stretch）
            while self.stock_layout.count() > 1:
                item = self.stock_layout.takeAt(0)
                w = item.widget()
                w and w.deleteLater()
            
            if not hasattr(self, '_all_signals') or not self._all_signals:
                return
            
            start = self._current_page * self._page_size
            end = min(start + self._page_size, len(self._all_signals))
            page_signals = self._all_signals[start:end]
            
            for s in page_signals:
                card_data = dict(s)
                if 'score' not in card_data or card_data['score'] == 0:
                    card_data['score'] = card_data.get('ai520_score', 0)
                if 'price' not in card_data:
                    card_data['price'] = card_data.get('current_price', 0)
                if 'pct_chg' not in card_data:
                    card_data['pct_chg'] = card_data.get('today_change', 0)
                # V2.8：使用精简模式，大幅减少控件数量
                card = StockCardV2(card_data, compact=True)
                card.clicked.connect(self.stock_clicked.emit)
                self.stock_layout.insertWidget(self.stock_layout.count() - 1, card)
            
            # 添加分页按钮
            total_pages = (len(self._all_signals) + self._page_size - 1) // self._page_size
            if total_pages > 1:
                page_row = QHBoxLayout()
                page_row.addStretch()
                # 上一页
                prev_btn = QPushButton('← 上一页')
                prev_btn.setEnabled(self._current_page > 0)
                prev_btn.setFixedHeight(26)
                prev_btn.setStyleSheet('QPushButton{background:#2563EB;color:white;border:none;border-radius:4px;padding:0 12px;font-size:10px;}QPushButton:disabled{background:#94A3B8;}QPushButton:hover{background:#1D4ED8;}')
                prev_btn.clicked.connect(lambda: self._change_page(-1))
                page_row.addWidget(prev_btn)
                page_row.addSpacing(8)
                # 页码
                page_label = L(f'第 {self._current_page+1} / {total_pages} 页', C.TEXT2, 11, True)
                page_row.addWidget(page_label)
                page_row.addSpacing(8)
                # 下一页
                next_btn = QPushButton('下一页 →')
                next_btn.setEnabled(self._current_page < total_pages - 1)
                next_btn.setFixedHeight(26)
                next_btn.setStyleSheet('QPushButton{background:#2563EB;color:white;border:none;border-radius:4px;padding:0 12px;font-size:10px;}QPushButton:disabled{background:#94A3B8;}QPushButton:hover{background:#1D4ED8;}')
                next_btn.clicked.connect(lambda: self._change_page(1))
                page_row.addWidget(next_btn)
                page_row.addStretch()
                self.stock_layout.insertLayout(self.stock_layout.count() - 1, page_row)
        except Exception as e:
            print(f"[AI520渲染] 分页渲染错误: {e}", flush=True)

    def _change_page(self, delta):
        """V2.8：切换分页"""
        if not hasattr(self, '_all_signals') or not self._all_signals:
            return
        total_pages = (len(self._all_signals) + self._page_size - 1) // self._page_size
        new_page = max(0, min(self._current_page + delta, total_pages - 1))
        if new_page != self._current_page:
            self._current_page = new_page
            self._render_current_page()
            self.result_count.setText(f'AI520候选 {len(self._all_signals)}只 第{self._current_page+1}/{total_pages}页')

    def _test_wechat(self):
        """测试企业微信连接"""
        svc = self._get_v22_service()
        if not svc:
            self.status_label.setText('企业微信服务未加载')
            return
        # self.wechat_btn.setEnabled(False)
        self.status_label.setText('企业微信测试中...')
        class WechatTestThread(QThread):
            finished = pyqtSignal(dict)
            def run(self):
                try:
                    result = svc.test_wechat()
                    self.finished.emit(result)
                except Exception as e:
                    self.finished.emit({'success': False, 'error': str(e)})
        self._wechat_thread = WechatTestThread()
        self._wechat_thread.finished.connect(self._on_wechat_test_finished)
        self._wechat_thread.start()

    def _on_wechat_test_finished(self, result):
        """企业微信测试完成"""
        # self.wechat_btn.setEnabled(True)
        if result.get('success'):
            self.status_label.setText('✅ 企业微信测试消息发送成功')
        else:
            self.status_label.setText(f'❌ 企业微信测试失败: {result.get("error", "未知错误")}')

    def _generate_daily_report(self):
        """生成收盘作战日报"""
        svc = self._get_v22_service()
        if not svc:
            self.status_label.setText('收盘总结服务未加载')
            return
        # self.report_btn.setEnabled(False)
        self.status_label.setText('生成收盘日报中...')
        class ReportThread(QThread):
            finished = pyqtSignal(dict)
            def run(self):
                try:
                    result = svc.generate_daily_report(push_wechat=True)
                    self.finished.emit(result)
                except Exception as e:
                    self.finished.emit({'success': False, 'error': str(e)})
        self._report_thread = ReportThread()
        self._report_thread.finished.connect(self._on_report_finished)
        self._report_thread.start()

    def _on_report_finished(self, result):
        """收盘日报生成完成"""
        # self.report_btn.setEnabled(True)
        if result.get('success'):
            self.status_label.setText('✅ 收盘作战日报已生成并推送企业微信')
        else:
            self.status_label.setText(f'❌ 收盘日报失败: {result.get("error", "未知错误")}')

    def _check_scheduled_tasks(self):
        """V2.2 定时任务检查（每分钟调用）"""
        svc = self._get_v22_service()
        if not svc:
            return
        try:
            result = svc.check_scheduled_tasks()
            if result.get('executed'):
                print(f"[V22] 定时任务执行: {result['executed']}", flush=True)
                self.status_label.setText(f"定时任务: {','.join(result['executed'])}")
        except Exception as e:
            print(f"[V22] 定时任务检查失败: {e}", flush=True)


# ============================================================
# 盘前新闻页面 V2.2 - 大卡片+股票识别+黄色高亮+可点击
# ============================================================
class NewsLoaderWorker(QThread):
    """新闻后台加载Worker（V2.3性能优化：真正QThread异步，不阻塞主线程）"""
    news_loaded = pyqtSignal(list)  # 加载完成信号，返回新闻列表
    load_failed = pyqtSignal(str)   # 加载失败信号

    def __init__(self, source='all', limit=200, parent=None):
        super().__init__(parent)
        self.source = source
        self.limit = limit
        self._cancelled = False

    def run(self):
        try:
            service = get_news_service()
            news = service.get_news(source=self.source, limit=self.limit)
            if self._cancelled:
                return
            self.news_loaded.emit(news or [])
        except Exception as e:
            if not self._cancelled:
                self.load_failed.emit(str(e))

    def cancel(self):
        self._cancelled = True


class NewsPage(QWidget):
    """V3.0 实时新闻中心：多源接入+自动刷新+智能去重+投资日历"""
    stock_clicked = pyqtSignal(str, str)
    # 线程安全信号（刷新引擎在后台线程回调，通过信号回到主线程更新UI）
    _sig_refresh_start = pyqtSignal()
    _sig_refresh_success = pyqtSignal(list, object)
    _sig_refresh_error = pyqtSignal(str, object)
    _sig_initial_loaded = pyqtSignal(list)
    _sig_auto_refresh_result = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.all_news = []
        self._seen_ids = set()
        self._new_card_timers = []
        self._use_new_center = NEWS_CENTER_AVAILABLE
        self._search_active = False
        self._current_category = '全部'
        self._search_results = []
        self._current_search_keyword = ''   # 当前搜索关键词（用于高亮）
        self._sector_first_load = True       # 板块新闻标签首次加载标记
        # AI分析数据缓存（30秒）
        self._analysis_data_cache = {}
        self._analysis_cache_time = 0
        # 单条新闻解读缓存
        self._news_interp_cache = {}
        # 股票名称→代码映射缓存（用于新闻标的提取名称反查）
        self._stock_name_map = None
        self._auto_refresh_timer = None
        self._auto_refresh_running = False
        p_start("NewsPage初始化")
        self._build_ui()
        p_end("NewsPage._build_ui")

        if self._use_new_center:
            self._init_new_center()
        else:
            self.count_label.setText('正在加载新闻...')
            self._news_worker = None
            QTimer.singleShot(300, self._load_news_async)
            self._news_timer = QTimer(self)
            self._news_timer.timeout.connect(self._refresh_news_incremental)
            self._news_timer.start(60000)
        p_end("NewsPage初始化")

    def _build_ui(self):
        """V4.0 统一信息流：同花顺7x24实时消息，单一纵向流"""
        main = QVBoxLayout(self); main.setContentsMargins(0, 0, 0, 0); main.setSpacing(0)

        # ===== 顶部栏 72px =====
        header = QFrame()
        header.setFixedHeight(72)
        header.setStyleSheet(f'QFrame{{background:rgba(255,255,255,0.95);border-bottom:1px solid {C.BORDER};}}')
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 16, 0)
        header_layout.setSpacing(12)

        # 左侧：图标 + 标题 + 红点 + 实时更新
        title_icon = QLabel('\U0001F4CA')
        title_icon.setStyleSheet('font-size:20px;background:transparent;')
        header_layout.addWidget(title_icon)
        title_label = QLabel('同花顺7\u00d724实时消息')
        title_label.setStyleSheet(f'color:{C.TEXT};font-size:16px;font-weight:bold;background:transparent;')
        header_layout.addWidget(title_label)
        header_layout.addSpacing(8)

        # 实时红点 8x8px
        red_dot = QLabel()
        red_dot.setFixedSize(8, 8)
        red_dot.setStyleSheet('background:#FF3B30;border-radius:4px;')
        header_layout.addWidget(red_dot)
        header_layout.addSpacing(4)
        live_label = QLabel('实时更新')
        live_label.setStyleSheet(f'color:#FF3B30;font-size:12px;font-weight:bold;background:transparent;')
        header_layout.addWidget(live_label)
        header_layout.addSpacing(16)

        # 中间：最新消息时间
        self.latest_time_label = QLabel('--:--:--')
        self.latest_time_label.setStyleSheet(f'color:{C.TEXT2};font-size:14px;font-weight:bold;background:transparent;')
        header_layout.addWidget(self.latest_time_label)
        header_layout.addStretch()

        # 右侧：分类下拉 80x36 + 搜索框 320x36 + 开始搜索按钮 80x36
        self.category_combo = QComboBox()
        self.category_combo.addItems(['全部', '股票', '宏观', '行业', '国际', '大宗', '市场', '公告'])
        self.category_combo.setFixedSize(80, 36)
        self.category_combo.setStyleSheet(
            f'QComboBox{{background:{C.TAB};color:{C.TEXT};border:1px solid {C.BORDER};'
            f'border-radius:18px;padding:0 10px;font-size:12px;}}'
            f'QComboBox QAbstractItemView{{background:white;color:{C.TEXT};border:1px solid {C.BORDER};}}'
        )
        self.category_combo.currentTextChanged.connect(self._on_category_changed)
        header_layout.addWidget(self.category_combo)

        self.news_search_input = QLineEdit()
        self.news_search_input.setPlaceholderText('搜索标题、股票、行业')
        self.news_search_input.setFixedSize(320, 36)
        self.news_search_input.setStyleSheet(
            f'QLineEdit{{background:{C.TAB};color:{C.TEXT};border:1px solid {C.BORDER};'
            f'border-radius:18px;padding:0 14px;font-size:13px;}}'
            f'QLineEdit:focus{{border:1px solid #2F6BFF;}}'
        )
        self.news_search_input.returnPressed.connect(self._on_search_triggered)
        header_layout.addWidget(self.news_search_input)

        self.news_search_btn = QPushButton('开始搜索')
        self.news_search_btn.setFixedSize(80, 36)
        self.news_search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.news_search_btn.setStyleSheet(
            f'QPushButton{{background:#2F6BFF;color:white;border:none;border-radius:18px;'
            f'font-size:13px;font-weight:bold;}}'
            f'QPushButton:hover{{background:#1E56E0;}}'
        )
        self.news_search_btn.clicked.connect(self._on_search_triggered)
        header_layout.addWidget(self.news_search_btn)

        main.addWidget(header)

        # ===== 主体：单一纵向信息流 =====
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(
            f'QScrollArea{{background:{C.BG};border:none;}}'
            f'QScrollBar:vertical{{background:{C.TAB};width:6px;}}'
            f'QScrollBar::handle:vertical{{background:{C.BORDER_L};border-radius:3px;}}'
        )
        self.container = QWidget()
        self.container.setStyleSheet(f'background:{C.BG};')
        self.news_layout = QVBoxLayout(self.container)
        self.news_layout.setContentsMargins(12, 8, 12, 8)
        self.news_layout.setSpacing(8)
        self.news_layout.addStretch()
        self.scroll.setWidget(self.container)
        main.addWidget(self.scroll, 1)

        # ===== 底部提示条（橙色） =====
        bottom_bar = QFrame()
        bottom_bar.setFixedHeight(28)
        bottom_bar.setStyleSheet('QFrame{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #FF8A3D,stop:1 #FF6D00);border:none;}')
        bl_layout = QHBoxLayout(bottom_bar)
        bl_layout.setContentsMargins(16, 0, 16, 0)
        tip_label = QLabel('已接入同花顺7\u00d724消息源，数据实时更新')
        tip_label.setStyleSheet('color:white;font-size:12px;font-weight:bold;background:transparent;')
        tip_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bl_layout.addWidget(tip_label)
        main.addWidget(bottom_bar)

        # 保留兼容属性（旧代码引用，避免AttributeError）
        self.count_label = QLabel('')
        self.count_label.setStyleSheet(f'color:{C.TEXT3};font-size:10px;background:transparent;')
        self.count_label.hide()
        self.loading_label = QLabel('')
        self.loading_label.setStyleSheet(f'color:{C.BLUE};font-size:10px;background:transparent;')
        self.loading_label.hide()
        self.last_update_label = QLabel('')
        self.last_update_label.setStyleSheet(f'color:{C.TEXT3};font-size:10px;background:transparent;')
        self.last_update_label.hide()
# [已删除投资日历按钮]         # 投资日历按钮
# [已删除投资日历按钮]         self.calendar_btn = QPushButton('📅 投资日历')
# [已删除投资日历按钮]         self.calendar_btn.setFixedHeight(28)
# [已删除投资日历按钮]         self.calendar_btn.setStyleSheet(f'QPushButton{{background:{C.BLUE};color:white;border:none;border-radius:4px;padding:0 12px;font-size:11px;}}QPushButton:hover{{background:#1D4ED8;}}')
# [已删除投资日历按钮]         self.calendar_btn.clicked.connect(self._show_invest_calendar)
# [已删除投资日历按钮]         # 先加到顶部
# [已删除投资日历按钮]         main.addWidget(self.calendar_btn)
        self.refresh_btn = QPushButton()
        self.refresh_btn.hide()
        self.ai_analysis_panel = QFrame()
        self.ai_analysis_panel.setVisible(False)
        self.ai_analysis_content = QLabel()
        self.ai_analysis_title = QLabel()
        self.ai_analysis_close_btn = QPushButton()
        # 旧子标签相关属性设为None
        self.sub_tabs = None
        self.watchlist_news_panel = None
        self.watchlist_news_layout = None
        self.sector_news_panel = None
        self.sector_news_layout = None
        self.sector_combo = None
        self.source_combo = None
        self.news_search_clear_btn = None
        self.ai_analysis_btn = None

    def _on_sub_tab_changed(self, index: int):
        """V2.8 子标签切换时触发对应数据加载（异步defer避免主线程阻塞）"""
        try:
            tab_text = self.sub_tabs.tabText(index)
            if '自选' in tab_text:
                if self.watchlist_news_layout is not None:
                    QTimer.singleShot(10, self._refresh_watchlist_news)
            elif '板块' in tab_text:
                if self.sector_news_layout is not None:
                    QTimer.singleShot(10, self._do_sector_tab_load)
        except Exception as e:
            print(f'[新闻中心] 子标签切换处理异常: {e}', flush=True)

    def _do_sector_tab_load(self):
        """板块新闻标签加载：刷新下拉框+自动选择涨幅行业+加载新闻"""
        try:
            self._refresh_sector_combo()
            # 首次加载默认"全部行业"，不自动切换到涨幅第一行业
            if not self._sector_first_load:
                self._auto_select_top_sector()
            else:
                self._sector_first_load = False
                print('[新闻中心] 板块新闻首次加载，默认显示全部行业', flush=True)
            self._refresh_sector_news()
        except Exception as e:
            print(f'[新闻中心] 板块标签加载异常: {e}', flush=True)

    def _init_new_center(self):
        try:
            engine = get_refresh_engine()
            engine.set_existing_news(self.all_news)
            self._sig_refresh_start.connect(self._on_refresh_start_ui)
            self._sig_refresh_success.connect(self._on_refresh_success_ui)
            self._sig_refresh_error.connect(self._on_refresh_error_ui)
            self._sig_initial_loaded.connect(self._on_initial_loaded)
            self._sig_auto_refresh_result.connect(self._on_auto_refresh_result)
            engine.on_refresh_start = lambda: self._sig_refresh_start.emit()
            engine.on_refresh_success = lambda news, res: self._sig_refresh_success.emit(news, res)
            engine.on_refresh_error = lambda err, res: self._sig_refresh_error.emit(err, res)
            engine.start()
            self.count_label.setText('正在加载新闻...')
            print("[新闻中心] V3.0刷新引擎已启动", flush=True)
            # 初始数据加载：引擎只做增量刷新，首次启动需主动拉取全量新闻
            QTimer.singleShot(200, self._load_initial_news)
            # 独立60秒自动刷新定时器（不依赖刷新引擎状态）
            self._auto_refresh_timer = QTimer(self)
            self._auto_refresh_timer.timeout.connect(self._do_auto_refresh)
            self._auto_refresh_timer.start(60000)
            # 顶部时间显示当前系统时间（每秒刷新）
            self._clock_timer = QTimer(self)
            self._clock_timer.timeout.connect(self._update_clock)
            self._clock_timer.start(1000)
            self._update_clock()
            print("[新闻中心] 自动刷新定时器已启动(60s)", flush=True)
        except Exception as e:
            print(f"[新闻中心] 初始化失败，降级旧版: {e}", flush=True)
            self._use_new_center = False
            self.count_label.setText('正在加载新闻...')
            self._news_worker = None
            QTimer.singleShot(300, self._load_news_async)
            self._news_timer = QTimer(self)
            self._news_timer.timeout.connect(self._refresh_news_incremental)
            self._news_timer.start(60000)

    def _load_initial_news(self):
        """初始加载全量新闻（新新闻中心模式），后台线程执行不阻塞UI"""
        def _do_load():
            try:
                from news_center import get_multi_source_manager
                mgr = get_multi_source_manager()
                news = mgr.fetch_all(limit=200)
                self._sig_initial_loaded.emit(news or [])
            except Exception as e:
                print(f"[新闻中心] 初始加载失败: {e}", flush=True)
                self._sig_initial_loaded.emit([])
        import threading
        threading.Thread(target=_do_load, daemon=True).start()

    def _on_initial_loaded(self, news_list):
        """初始加载完成回调（主线程）"""
        try:
            if not news_list:
                self.count_label.setText('加载失败，点击重试')
                return
            self.all_news = news_list
            for n in self.all_news:
                nid = n.get('news_id') or n.get('id') or n.get('url') or n.get('title', '')
                self._seen_ids.add(nid)
            try:
                get_refresh_engine().set_existing_news(self.all_news)
            except Exception:
                pass
            self._apply_filter(refresh_v28=True)
            print(f"[新闻中心] 初始加载完成: {len(self.all_news)}条", flush=True)
        except Exception as e:
            print(f"[新闻中心] 初始加载回调异常: {e}", flush=True)

    def _update_clock(self):
        # 顶部时间显示当前系统时间
        try:
            from datetime import datetime as _dt
            self.latest_time_label.setText(_dt.now().strftime('%H:%M:%S'))
        except Exception:
            pass

    def _do_auto_refresh(self):
        """60秒自动刷新：后台线程拉取最新新闻，通过信号回主线程更新UI"""
        if self._auto_refresh_running:
            return
        self._auto_refresh_running = True
        def _fetch():
            try:
                from news_center import get_multi_source_manager
                mgr = get_multi_source_manager()
                # 优先拉取同花顺7x24和新浪7x24等实时源，limit=50足够覆盖60秒增量
                news = mgr.fetch_all(limit=50)
                self._sig_auto_refresh_result.emit(news or [])
            except Exception as e:
                print(f"[新闻中心] 自动刷新失败: {e}", flush=True)
                self._sig_auto_refresh_result.emit([])
        import threading
        threading.Thread(target=_fetch, daemon=True).start()

    def _on_auto_refresh_result(self, news_list):
        """自动刷新结果回调（主线程）：增量添加新新闻"""
        self._auto_refresh_running = False
        try:
            if not news_list:
                return
            added = 0
            for n in news_list:
                nid = n.get('news_id') or n.get('id') or n.get('url') or n.get('title', '')
                if nid and nid not in self._seen_ids:
                    self._seen_ids.add(nid)
                    self.all_news.insert(0, n)
                    added += 1
            if added > 0:
                # 保持按时间倒序
                try:
                    self.all_news.sort(key=lambda x: x.get('publish_time', ''), reverse=True)
                except Exception:
                    pass
                # 限制最大条数
                max_keep = 500
                if len(self.all_news) > max_keep:
                    self.all_news = self.all_news[:max_keep]
                try:
                    get_refresh_engine().set_existing_news(self.all_news)
                except Exception:
                    pass
                # 非搜索状态下才刷新UI（搜索时保持搜索结果）
                if not self._search_active:
                    self._apply_filter(refresh_v28=True)
                # 更新顶部最新时间
                print(f"[新闻中心] 自动刷新: +{added}条新消息，总计{len(self.all_news)}条", flush=True)
        except Exception as e:
            print(f"[新闻中心] 自动刷新回调异常: {e}", flush=True)

    def set_tab_visible(self, visible: bool):
        if self._use_new_center:
            try:
                get_refresh_engine().set_active(visible)
            except Exception as e:
                print(f"[新闻中心] 切换状态失败: {e}", flush=True)
        # 独立自动刷新定时器：可见时启动，不可见时暂停
        if hasattr(self, '_auto_refresh_timer') and self._auto_refresh_timer:
            if visible:
                if not self._auto_refresh_timer.isActive():
                    self._auto_refresh_timer.start(60000)
                    print("[新闻中心] 自动刷新定时器恢复", flush=True)
            else:
                self._auto_refresh_timer.stop()
                print("[新闻中心] 自动刷新定时器暂停(切到其他Tab)", flush=True)

    def _on_refresh_start_ui(self):
        self.loading_label.setText('⏳ 更新中...')
        self.refresh_btn.setEnabled(False)

    def _on_refresh_success_ui(self, new_news: list, result):
        try:
            self.loading_label.setText('')
            self.refresh_btn.setEnabled(True)
            if result and getattr(result, 'timestamp', ''):
                self.last_update_label.setText(f'最后更新: {result.timestamp[11:]}')
            if new_news:
                for n in reversed(new_news):
                    nid = n.get('news_id', '') or n.get('id', '') or n.get('title', '')
                    if nid and nid not in self._seen_ids:
                        self._seen_ids.add(nid)
                        self.all_news.insert(0, n)
                try:
                    get_refresh_engine().set_existing_news(self.all_news)
                except Exception:
                    pass
                print(f"[新闻中心] 增量刷新: +{len(new_news)}条，总计{len(self.all_news)}条", flush=True)
                self._apply_filter(refresh_v28=True)
            if self.all_news:
                latest_pt = str(self.all_news[0].get('publish_time', ''))
                if len(latest_pt) >= 19:
                    self.latest_time_label.setText(latest_pt[11:19])
            else:
                self.count_label.setText(f'共{len(self.all_news)}条')
            max_keep = REFRESH_CONFIG.get('max_cached_news', 500) if self._use_new_center else 500
            if len(self.all_news) > max_keep:
                self.all_news = self.all_news[:max_keep]
        except Exception as e:
            print(f"[新闻中心] 刷新成功回调异常: {e}", flush=True)

    def _on_refresh_error_ui(self, error_msg: str, result):
        self.loading_label.setText('')
        self.refresh_btn.setEnabled(True)
        if result and getattr(result, 'timestamp', ''):
            self.last_update_label.setText(f'最后更新: {result.timestamp[11:]}')
        print(f"[新闻中心] 刷新失败: {error_msg}", flush=True)

    def _on_manual_refresh(self):
        if self._use_new_center:
            try:
                get_refresh_engine().trigger_refresh(immediate=True)
            except Exception as e:
                print(f"[新闻中心] 手动刷新失败: {e}", flush=True)
        else:
            self._load_news_async()

    def _load_news_async(self):
        if self._use_new_center:
            return
        if self._news_worker and self._news_worker.isRunning():
            self._news_worker.cancel(); self._news_worker.wait(1000)
        self.count_label.setText('加载中...')
        self._news_worker = NewsLoaderWorker(source='all', limit=200)
        self._news_worker.news_loaded.connect(self._on_news_loaded)
        self._news_worker.load_failed.connect(self._on_news_failed)
        self._news_worker.start()

    def _on_news_loaded(self, news_list):
        try:
            self.all_news = news_list
            for n in self.all_news:
                nid = n.get('id') or n.get('url') or n.get('title', '')
                self._seen_ids.add(nid)
            self._apply_filter(refresh_v28=True)
            print(f"[新闻] 后台加载完成: {len(self.all_news)}条", flush=True)
        except Exception as e:
            print(f"[新闻] 加载回调异常: {e}", flush=True)

    def _on_news_failed(self, error_msg):
        print(f"[新闻] 后台加载失败: {error_msg}", flush=True)
        self.count_label.setText('加载失败')

    def _refresh_news_incremental(self):
        if self._use_new_center:
            return
        try:
            service = get_news_service()
            new_news = service.get_news(source='all', limit=50)
            added = 0
            for n in new_news:
                nid = n.get('id') or n.get('url') or n.get('title', '')
                if nid and nid not in self._seen_ids:
                    self._seen_ids.add(nid)
                    self.all_news.insert(0, n)
                    added += 1
            if added > 0:
                print(f"[新闻] 增量刷新: 新增{added}条，总计{len(self.all_news)}条", flush=True)
                self._apply_filter(refresh_v28=True)
            if len(self.all_news) > 500:
                self.all_news = self.all_news[:500]
        except Exception as e:
            print(f"[新闻] 增量刷新失败: {e}", flush=True)

    def _apply_filter(self, refresh_v28=False):
        """V4.0 单一信息流渲染：不再分标签，统一展示所有新闻"""
        try:
            # 清空现有卡片
            while self.news_layout.count() > 1:
                item = self.news_layout.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()

            # 确定显示的新闻列表
            if self._search_active and self._search_results:
                filtered = self._search_results
            else:
                filtered = list(self.all_news)

            # 分类筛选
            if hasattr(self, '_current_category') and self._current_category and self._current_category != '全部':
                filtered = [n for n in filtered
                            if self._classify_news_category(n)[0] == self._current_category]

            # 按原始发布时间倒序（最新在最上）
            def _sort_key(item):
                pt = str(item.get('publish_time', '') or item.get('time', ''))
                for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
                    try:
                        return datetime.strptime(pt, fmt)
                    except ValueError:
                        continue
                return datetime(2000, 1, 1)
            filtered = sorted(filtered, key=_sort_key, reverse=True)

            # 顶部时间由_clock_timer显示当前系统时间

            # 渲染卡片
            if not filtered:
                empty = QLabel('加载中...')
                empty.setStyleSheet(f'color:{C.TEXT3};font-size:14px;background:transparent;padding:60px;')
                empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.news_layout.insertWidget(self.news_layout.count() - 1, empty)
                return

            for news in filtered[:50]:
                card = self._create_news_card(news)
                self.news_layout.insertWidget(self.news_layout.count() - 1, card)

            if self.count_label:
                self.count_label.setText(f'共{len(filtered)}条')
        except Exception as e:
            print(f"[新闻] 渲染错误: {e}", flush=True)
            import traceback
            traceback.print_exc()

    def _on_search_triggered(self):
        """搜索触发：先显示加载状态，再异步执行搜索（避免主线程阻塞）"""
        try:
            keyword = self.news_search_input.text().strip()
            if not keyword:
                self._clear_search()
                return
            self.count_label.setText('⏳ 搜索中...')
            QApplication.processEvents()
            QTimer.singleShot(10, self._do_search)
        except Exception as e:
            print(f'[新闻搜索] 触发异常: {e}', flush=True)

    def _do_search(self):
        """新闻搜索：获取关键词，调用后端搜索+个股专属拉取，显示结果（增强版）"""
        try:
            keyword = self.news_search_input.text().strip()
            if not keyword:
                self._clear_search()
                return
            print(f"[新闻搜索] 搜索关键词: {keyword}", flush=True)
            self._current_search_keyword = keyword

            # ===== 判断是否为股票代码/名称 =====
            stock_code = ''
            stock_name = ''
            kw_lower = keyword.lower()
            # 带前缀代码 sz002395
            m_prefix = _re_mod.match(r'^(sz|sh|bj)(\d{6})$', kw_lower)
            if m_prefix:
                stock_code = m_prefix.group(2)
            elif _re_mod.match(r'^\d{6}$', keyword):
                stock_code = keyword
            elif _re_mod.match(r'^[\u4e00-\u9fa5]{2,4}$', keyword):
                # 可能是股票名称，从缓存查找
                try:
                    _cache_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'stock_names_cache.json')
                    if os.path.exists(_cache_path):
                        with open(_cache_path, 'r', encoding='utf-8') as _f:
                            _cache_data = json.load(_f)
                        _stock_names = _cache_data.get('stock_names', {})
                        if keyword in _stock_names:
                            stock_code = str(_stock_names[keyword]).zfill(6)
                            stock_name = keyword
                            print(f"[新闻搜索] 股票名称'{keyword}'匹配到代码{stock_code}", flush=True)
                except Exception as _e:
                    print(f"[新闻搜索] 股票名称查找失败: {_e}", flush=True)

            # 如果识别出股票代码，反查名称
            if stock_code and not stock_name:
                try:
                    _cache_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'stock_names_cache.json')
                    if os.path.exists(_cache_path):
                        with open(_cache_path, 'r', encoding='utf-8') as _f:
                            _cache_data = json.load(_f)
                        _stock_names = _cache_data.get('stock_names', {})
                        for _nm, _cd in _stock_names.items():
                            if str(_cd).zfill(6) == stock_code and len(_nm) >= 2:
                                stock_name = _nm
                                break
                except Exception:
                    pass

            # ===== 个股专属新闻拉取（仅当识别为股票代码/名称时） =====
            stock_specific_news = []
            if stock_code:
                try:
                    from news_engine.news_manager import get_news_manager
                    nm = get_news_manager()
                    # 个股专属新闻
                    try:
                        sn = nm.get_stock_news(stock_code, stock_name, limit=20)
                        stock_specific_news.extend(sn)
                        print(f"[新闻搜索] 个股专属新闻: {len(sn)}条", flush=True)
                    except Exception as e_sn:
                        print(f"[新闻搜索] 个股专属新闻拉取失败: {e_sn}", flush=True)
                    # 个股专属公告
                    try:
                        sa = nm.get_stock_announcements(stock_code, stock_name, limit=20)
                        stock_specific_news.extend(sa)
                        print(f"[新闻搜索] 个股专属公告: {len(sa)}条", flush=True)
                    except Exception as e_sa:
                        print(f"[新闻搜索] 个股专属公告拉取失败: {e_sa}", flush=True)
                except Exception as e_nm:
                    print(f"[新闻搜索] NewsManager获取失败: {e_nm}", flush=True)

            # ===== 新闻池搜索（三级降级） =====
            results = []
            try:
                from news_center import get_multi_source_manager
                mgr = get_multi_source_manager()
                results = mgr.search_news(keyword, limit=50)
            except Exception as e1:
                print(f"[新闻搜索] news_center搜索失败: {e1}", flush=True)
            if not results:
                try:
                    from news_engine.news_manager import get_news_manager
                    nm2 = get_news_manager()
                    results = nm2.search_news(keyword, limit=50)
                except Exception as e2:
                    print(f"[新闻搜索] NewsManager搜索失败: {e2}", flush=True)
            if not results and self.all_news:
                kw = keyword.lower()
                for n in self.all_news:
                    text = ' '.join([
                        str(n.get('title', '')),
                        str(n.get('content', n.get('summary', ''))),
                        str(n.get('source', '')),
                    ]).lower()
                    if kw in text:
                        results.append(n)

            # ===== 合并个股专属新闻 + 新闻池搜索结果，去重 =====
            all_merged = list(stock_specific_news) + list(results)
            seen_keys = set()
            deduped = []
            for item in all_merged:
                # 去重键：优先url，其次title+publish_time
                url = str(item.get('url', '')).strip()
                title = str(item.get('title', '')).strip()
                pub_time = str(item.get('publish_time', ''))[:16]
                if url:
                    key = ('url', url)
                elif title:
                    key = ('title', title, pub_time)
                else:
                    key = ('id', str(item.get('news_id', id(item))))
                if key not in seen_keys:
                    seen_keys.add(key)
                    deduped.append(item)

            # 按发布时间倒序
            def _search_sort_key(item):
                pt = item.get('publish_time', '')
                for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
                    try:
                        return datetime.strptime(pt, fmt)
                    except ValueError:
                        continue
                return datetime(2000, 1, 1)
            deduped.sort(key=_search_sort_key, reverse=True)

            self._search_active = True
            self._search_results = deduped

            # 清空布局
            while self.news_layout.count() > 1:
                item = self.news_layout.takeAt(0); w = item.widget()
                if w: w.deleteLater()

            # ===== 空结果兜底 =====
            if not deduped:
                self._render_search_empty_state(keyword)
                self.count_label.setText('搜索结果: 0条')
                print(f"[新闻搜索] 完成，无结果", flush=True)
                return

            # 渲染结果
            for news in deduped[:40]:
                card = self._create_news_card(news)
                self.news_layout.insertWidget(self.news_layout.count() - 1, card)

            # 计数标签（含个股专属数量）
            stock_count = len(stock_specific_news)
            if stock_code and stock_count > 0:
                self.count_label.setText(f'搜索结果: {len(deduped)}条（含个股专属{stock_count}条）')
            else:
                self.count_label.setText(f'搜索结果: {len(deduped)}条')
            print(f"[新闻搜索] 完成，共 {len(deduped)} 条结果（个股专属{stock_count}条）", flush=True)
        except Exception as e:
            print(f"[新闻搜索] 搜索异常: {e}", flush=True)
            import traceback
            traceback.print_exc()

    def _render_search_empty_state(self, keyword):
        """渲染搜索空结果状态：提示 + 热门搜索词 + 查看全部新闻按钮"""
        try:
            container = QFrame()
            container.setStyleSheet(f'QFrame{{background:{C.CARD};border:1px solid {C.BORDER};border-radius:8px;}}')
            layout = QVBoxLayout(container)
            layout.setContentsMargins(24, 32, 24, 32)
            layout.setSpacing(16)

            # 提示文字
            tip = QLabel(f'未找到与"{keyword}"相关的新闻，建议更换关键词')
            tip.setStyleSheet(f'color:{C.TEXT2};font-size:13px;background:transparent;')
            tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tip.setWordWrap(True)
            layout.addWidget(tip)

            # 热门搜索词
            hot_row = QHBoxLayout()
            hot_row.addStretch()
            hot_label = QLabel('热门搜索：')
            hot_label.setStyleSheet(f'color:{C.TEXT3};font-size:11px;background:transparent;')
            hot_row.addWidget(hot_label)
            for hw in ['银行', 'AI', '新能源', '涨停']:
                btn = QPushButton(hw)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setStyleSheet(f'QPushButton{{background:rgba(37,99,235,0.08);color:#2563EB;border:1px solid rgba(37,99,235,0.3);border-radius:4px;padding:2px 10px;font-size:11px;}}QPushButton:hover{{background:rgba(37,99,235,0.15);}}')
                btn.clicked.connect(lambda checked, kw=hw: self._quick_search(kw))
                hot_row.addWidget(btn)
                hot_row.addSpacing(6)
            hot_row.addStretch()
            layout.addLayout(hot_row)

            # 查看全部新闻按钮
            btn_row = QHBoxLayout()
            btn_row.addStretch()
            all_btn = QPushButton('📋 查看全部新闻')
            all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            all_btn.setStyleSheet(f'QPushButton{{background:{C.BLUE};color:white;border:none;border-radius:4px;padding:6px 20px;font-size:12px;font-weight:bold;}}QPushButton:hover{{background:#1D4ED8;}}')
            all_btn.clicked.connect(self._clear_search)
            btn_row.addWidget(all_btn)
            btn_row.addStretch()
            layout.addLayout(btn_row)

            self.news_layout.insertWidget(self.news_layout.count() - 1, container)
        except Exception as e:
            print(f"[新闻搜索] 空状态渲染失败: {e}", flush=True)

    def _quick_search(self, keyword):
        """快捷搜索：设置搜索框内容并触发搜索"""
        try:
            self.news_search_input.setText(keyword)
            self._do_search()
        except Exception as e:
            print(f"[新闻搜索] 快捷搜索失败: {e}", flush=True)
    def _clear_search(self):
        """清除搜索，恢复显示全部新闻"""
        try:
            self.news_search_input.clear()
            self._search_active = False
            self._search_results = []
            self._current_search_keyword = ''
            self._apply_filter()
            print("[新闻搜索] 已清除搜索，恢复全部新闻", flush=True)
        except Exception as e:
            print(f"[新闻搜索] 清除搜索异常: {e}", flush=True)


    # ============================================================
    # AI分析数据层：统一获取本地数据，带30秒缓存
    # ============================================================
    def _get_local_data_for_analysis(self, force_refresh=False):
        """统一获取板块数据、个股行情、AI520评分、自选股列表，带30秒缓存"""
        now = time.time()
        if not force_refresh and (now - self._analysis_cache_time) < 30 and self._analysis_data_cache:
            return self._analysis_data_cache

        result = {
            'sectors': [],          # 板块列表 [{name, change_pct, net_inflow, score, top_stocks, ...}]
            'sector_map': {},       # name -> sector dict
            'quotes': {},           # {code: {name, price, pct_chg, ...}}
            'ai520_scores': {},     # {code: total_score}
            'watchlist': [],        # [{code, name}]
            'watchlist_codes': set(),
            'sh_pct': 0.0,
        }

        # 1. 板块数据
        # 【2026-09-24 清理 v28 死引用】原数据源 v28.core.sector_radar 已下线。
        # 保持 result 的键结构不变（避免调用方 KeyError），值给空。
        result['sectors'] = []
        result['sector_map'] = {}

        # 2. 自选股
        try:
            wl_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'watchlist.json')
            if os.path.exists(wl_path):
                with open(wl_path, 'r', encoding='utf-8') as f:
                    result['watchlist'] = json.load(f)
                result['watchlist_codes'] = {s.get('code', '') for s in result['watchlist'] if s.get('code')}
        except Exception as e:
            print(f'[AI分析] 自选股获取失败: {e}', flush=True)

        # 3. AI520评分（从duckdb读取最新评分）
        try:
            import duckdb
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'ai520_cache.duckdb')
            if os.path.exists(db_path):
                con = duckdb.connect(db_path, read_only=True)
                rows = con.execute("""
                    SELECT code, total_score FROM signals
                    WHERE id IN (SELECT MAX(id) FROM signals GROUP BY code)
                """).fetchall()
                for code, score in rows:
                    if code and score is not None:
                        result['ai520_scores'][str(code).zfill(6)] = float(score)
                con.close()
        except Exception as e:
            print(f'[AI分析] AI520评分获取失败: {e}', flush=True)

        self._analysis_data_cache = result
        self._analysis_cache_time = now
        return result

    def _batch_get_quotes(self, codes):
        """批量获取个股实时行情，结果合并到缓存"""
        if not codes:
            return {}
        codes = [str(c).zfill(6) for c in codes if c]
        # 去重
        codes = list(set(codes))
        data = self._analysis_data_cache if self._analysis_data_cache else self._get_local_data_for_analysis()
        # 检查哪些已经有行情
        missing = [c for c in codes if c not in data.get('quotes', {})]
        if missing:
            try:
                from utils.http_market_data import get_realtime_quotes_http
                quotes = get_realtime_quotes_http(missing)
                if quotes:
                    data['quotes'].update(quotes)
            except Exception as e:
                print(f'[AI分析] 批量行情获取失败: {e}', flush=True)
        return {c: data['quotes'].get(c, {}) for c in codes}

    def _get_stock_name_map(self):
        """获取股票名称→代码映射（带缓存，避免重复读文件）"""
        if self._stock_name_map is None:
            self._stock_name_map = {}
            try:
                _cache_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'stock_names_cache.json')
                if os.path.exists(_cache_path):
                    with open(_cache_path, 'r', encoding='utf-8') as _f:
                        _data = json.load(_f)
                    self._stock_name_map = _data.get('stock_names', {})
            except Exception:
                pass
        return self._stock_name_map

    def _extract_stock_codes_from_news(self, news):
        """从新闻中提取所有提及的股票代码和名称（增强版：字段+正则+名称反查）"""
        codes = set()
        names = set()
        # 1. 从stock_codes字段提取
        stock_list = news.get('stock_codes', news.get('stocks', []))
        if isinstance(stock_list, list):
            for st in stock_list:
                if isinstance(st, dict):
                    c = st.get('code', '')
                    n = st.get('name', '')
                    if c: codes.add(str(c).zfill(6))
                    if n: names.add(n)
                elif isinstance(st, str):
                    if st.isdigit() and len(st) >= 5:
                        codes.add(str(st).zfill(6))
                    else:
                        names.add(st)
        # 2. 从标题和内容中提取6位数字代码（0/3/6开头）
        text = str(news.get('title', '')) + ' ' + str(news.get('content', ''))
        for m in _re_mod.findall(r'(?<!\d)([036][0-9]{5})(?!\d)', text):
            codes.add(m)
        # 3. 股票名称反查：已提取名称从stock_names_cache.json映射为代码
        if names:
            try:
                name_map = self._get_stock_name_map()
                for nm in names:
                    if nm and nm in name_map:
                        codes.add(str(name_map[nm]).zfill(6))
            except Exception:
                pass
        # 4. 从标题/内容正文中匹配已知股票名称（≥2字，限12只防性能问题）
        try:
            name_map = self._get_stock_name_map()
            if name_map:
                # 按名称长度降序，优先匹配长名称（减少误匹配）
                for nm in sorted(name_map.keys(), key=len, reverse=True):
                    if len(nm) >= 2 and nm in text:
                        codes.add(str(name_map[nm]).zfill(6))
                        if len(codes) >= 12:
                            break
        except Exception:
            pass
        return list(codes), list(names)

    def _match_sector_from_keywords(self, text, sector_map):
        """严格关键词匹配申万一级行业：仅命中板块核心业务词(>=2字)，无匹配返回空"""
        if not text or not sector_map:
            return []
        text_lower = text.lower()
        # 严格关键词映射：每个板块3-5个核心业务词，全部>=2字
        keyword_map = {
            '银行': ['银行', '央行', '降息', '降准', 'LPR'],
            '非银金融': ['证券', '券商', '保险', '印花税', 'IPO', '寿险', '财险'],
            '房地产': ['房地产', '地产', '房企', '楼市', '房价', '保利', '万科', '碧桂园'],
            '建筑装饰': ['基建', '新基建', '铁路', '水利', '装修装饰'],
            '建筑材料': ['建材', '水泥', '玻璃', '瓷砖', '石膏板'],
            '钢铁': ['钢铁', '钢材', '铁矿石', '宝钢', '武钢'],
            '有色金属': ['有色金属', '铜价', '铝价', '黄金', '白银', '锂矿', '稀土', '钴', '镍'],
            '煤炭': ['煤炭', '煤价', '动力煤', '焦煤', '中国神华'],
            '石油石化': ['石油', '原油', '油价', 'OPEC', '中石化', '中石油', '炼化'],
            '基础化工': ['化工', '化纤', '塑料', '橡胶', '化肥', '农药', 'MDI', '钛白粉'],
            '电力设备': ['光伏', '太阳能', '风电', '储能', '锂电池', '动力电池', '新能源车', '充电桩', '逆变器', '硅料', '硅片'],
            '电子': ['半导体', '芯片', '集成电路', '晶圆', '光刻', '封测', 'EDA', 'MCU', '存储芯片', '消费电子', '苹果', 'iPhone'],
            '计算机': ['软件', '信创', '数字经济', '云计算', '大数据', '数据中心', '东数西算', '人工智能', '大模型', '算力', 'AIGC', 'ChatGPT', '深度学习'],
            '通信': ['5G', '6G', '光模块', '光纤', '运营商', '华为', '中兴'],
            '传媒': ['传媒', '影视', '游戏', '出版', '广告', '元宇宙', '短剧'],
            '医药生物': ['医药', '医疗', '创新药', 'CXO', '医疗器械', '医院', '医保', '中药', '疫苗', '基因治疗', '生物科技'],
            '食品饮料': ['白酒', '茅台', '五粮液', '泸州老窖', '汾酒', '洋河', '乳业', '调味品', '啤酒', '休闲食品'],
            '农林牧渔': ['农业', '乡村振兴', '粮食', '种业', '猪肉', '生猪', '猪价', '牧原', '温氏', '养殖'],
            '家用电器': ['家电', '白电', '黑电', '空调', '冰箱', '洗衣机', '美的', '格力'],
            '纺织服饰': ['纺织', '服装', '家纺', '服饰'],
            '轻工制造': ['造纸', '家具', '包装', '印刷'],
            '商贸零售': ['零售', '电商', '免税', '超市', '百货'],
            '社会服务': ['旅游', '酒店', '餐饮', '教育', '医美', '玻尿酸', '肉毒素'],
            '交通运输': ['航运', '集装箱', '海运', '港口', '中远海控', '物流', '快递', '顺丰', '航空', '机场', '高铁'],
            '公用事业': ['火电', '水电', '核电', '电价', '环保', '碳中和', '碳达峰', '污水处理', '燃气'],
            '国防军工': ['军工', '国防', '导弹', '战机', '航母', '航天', '卫星', '火箭', '空间站', '商业航天'],
            '机械设备': ['工程机械', '挖掘机', '三一重工', '中联重科', '徐工', '机器人', '人形机器人', '工业机器人', '减速器', '机床'],
            '汽车': ['整车', '比亚迪', '蔚来', '小鹏', '理想', '轮胎'],
        }
        matched = []
        for sector_name, keywords in keyword_map.items():
            if sector_name not in sector_map:
                continue
            for kw in keywords:
                if len(kw) < 2:
                    continue
                if kw.lower() in text_lower:
                    matched.append(sector_name)
                    break
        return matched

    def _classify_event_type(self, news):
        """判断新闻事件类型"""
        title = str(news.get('title', ''))
        content = str(news.get('content', ''))
        source = str(news.get('source', ''))
        category = str(news.get('category', ''))
        text = title + ' ' + content

        if any(kw in text for kw in ['政策', '国务院', '央行', '证监会', '发改委', '工信部', '财政部', '商务部', '通知', '意见', '规划', '条例', '规定', '监管']):
            return '政策'
        if any(kw in text for kw in ['业绩', '营收', '净利润', '财报', '季报', '年报', '中报', '预增', '预减', '扭亏', '亏损', '增长', '同比']):
            return '业绩'
        if any(kw in text for kw in ['公告', '复牌', '停牌', '重组', '收购', '并购', '定增', '减持', '增持', '回购', '分红', '配股', '股权激励', '中标', '合同']):
            return '公告'
        if any(kw in text for kw in ['行业', '产业链', '供需', '价格', '涨价', '降价', '产能', '出货量', '渗透率']):
            return '行业新闻'
        if any(kw in text for kw in ['GDP', 'CPI', 'PPI', 'PMI', '利率', '汇率', '美联储', '加息', '缩表', '宏观', '经济数据', '社融', 'M2']):
            return '宏观事件'
        if category in ['公司公告', '资金']:
            return '公告'
        return '行业新闻'

    def _calc_impact_level(self, news):
        """计算新闻影响等级（强/中/弱），禁止统一标低"""
        hot = float(news.get('hot_score', 0) or 0)
        sentiment = str(news.get('sentiment', ''))
        intensity = str(news.get('intensity', ''))
        source = str(news.get('source', ''))
        title = str(news.get('title', ''))

        score = 0
        # 热度权重
        if hot >= 80: score += 3
        elif hot >= 60: score += 2
        elif hot >= 40: score += 1

        # 情绪强度
        if intensity == '强': score += 2
        elif intensity == '中': score += 1

        # 来源权重
        high_impact_sources = ['新华社', '央视', '人民日报', '证监会', '央行', '国务院', '财联社', '证券时报', '上海证券报', '巨潮', '同花顺', '7x24', '交易所', '证监会发布']
        if any(s in source for s in high_impact_sources):
            score += 2
        elif source:
            score += 1

        # 标题关键词
        strong_keywords = ['重磅', '突发', '紧急', '重大', '史上', '首次', '突破', '暴涨', '暴跌', '涨停', '跌停', '复牌', '重组', '禁令', '制裁']
        if any(kw in title for kw in strong_keywords):
            score += 2

        if score >= 6: return '强'
        elif score >= 3: return '中'
        else: return '弱'

    def _refine_event_title(self, title):
        """提炼事件核心内容，禁止直接复制新闻标题"""
        # 去除常见前缀和时间表述
        t = title
        patterns_to_remove = [
            r'^【[^】]*】\s*',
            r'^\[[^\]]*\]\s*',
            r'[0-9]{1,2}月[0-9]{1,2}日[，,]?\s*',
            r'[0-9]{4}年[0-9]{1,2}月[0-9]{1,2}日[，,]?\s*',
            r'上午起?',
            r'下午起?',
            r'今日',
            r'刚刚[：:]?\s*',
            r'最新消息[：:]?\s*',
        ]
        for p in patterns_to_remove:
            t = _re_mod.sub(p, '', t)
        # 标题不截断，完整显示
        return t.strip()

    def _on_ai_analysis_clicked(self):
        """AI分析按钮：先显示加载状态，再异步执行分析（避免主线程阻塞）"""
        try:
            self.ai_analysis_content.setText('⏳ AI深度分析中，请稍候...')
            self.ai_analysis_panel.setVisible(True)
            QApplication.processEvents()
            QTimer.singleShot(10, self._do_ai_analysis)
        except Exception as e:
            print(f'[AI分析] 按钮触发异常: {e}', flush=True)

    def _do_ai_analysis(self):
        """AI新闻分析升级：4模块固定输出（事件线/板块图谱/标的池/交易视角）"""
        try:
            # 确定当前显示的新闻列表
            if self._search_active and self._search_results:
                news_list = self._search_results
            else:
                news_list = self.all_news

            if not news_list or len(news_list) < 3:
                self.ai_analysis_content.setText('暂无足够新闻进行分析（至少需要3条）')
                self.ai_analysis_panel.setVisible(True)
                return

            self.ai_analysis_content.setText('⏳ AI深度分析中，请稍候...')
            self.ai_analysis_panel.setVisible(True)
            QApplication.processEvents()

            # 获取本地数据
            data = self._get_local_data_for_analysis()
            sector_map = data.get('sector_map', {})
            sectors = data.get('sectors', [])
            watchlist_codes = data.get('watchlist_codes', set())
            ai520_scores = data.get('ai520_scores', {})

            # 取前30条进行分析
            sample = news_list[:30]

            # ========== 模块1：今日核心事件线 ==========
            # 按重要性排序：hot_score + sentiment强度 + 来源权重
            def _news_importance(n):
                hot = float(n.get('hot_score', 0) or 0)
                intensity = str(n.get('intensity', ''))
                source = str(n.get('source', ''))
                score = hot * 0.5
                if intensity == '强': score += 20
                elif intensity == '中': score += 10
                high_src = ['新华社', '央视', '人民日报', '证监会', '央行', '国务院', '财联社', '证券时报']
                if any(s in source for s in high_src): score += 15
                return score

            sorted_news = sorted(sample, key=_news_importance, reverse=True)
            top_events = sorted_news[:5]

            module1_lines = ['<div style="margin-bottom:8px;"><span style="color:#2563EB;font-size:13px;font-weight:bold;">📌 今日核心事件线</span></div>']
            for i, n in enumerate(top_events):
                title = self._refine_event_title(str(n.get('title', '未命名事件')))
                pub_time = str(n.get('publish_time', n.get('time', '')))
                if len(pub_time) > 16: pub_time = pub_time[:16]
                impact = self._calc_impact_level(n)
                sentiment = str(n.get('sentiment', '中性'))
                if '利好' in sentiment:
                    sent_color = '#FF3B30'  # A股红涨
                    sent_text = '利好'
                elif '利空' in sentiment:
                    sent_color = '#34C759'  # A股绿跌
                    sent_text = '利空'
                else:
                    sent_color = '#64748B'
                    sent_text = '中性'
                impact_color = {'强': '#FF3B30', '中': '#FF9500', '弱': '#64748B'}.get(impact, '#64748B')
                module1_lines.append(
                    f'<div style="margin:3px 0;padding-left:8px;border-left:3px solid {impact_color};">'
                    f'<span style="color:{C.TEXT};font-size:11px;font-weight:bold;">{i+1}. {title}</span>'
                    f' <span style="color:{sent_color};font-size:10px;font-weight:bold;">[{sent_text}]</span>'
                    f' <span style="color:{impact_color};font-size:10px;">影响:{impact}</span>'
                    f' <span style="color:{C.TEXT3};font-size:10px;">{pub_time}</span>'
                    f'</div>'
                )

            # ========== 模块2：板块影响图谱 ==========
            # 从所有新闻中提取板块关键词，统计利好/利空频次
            sector_bullish = defaultdict(int)
            sector_bearish = defaultdict(int)
            sector_news_count = defaultdict(int)

            for n in sample:
                text = str(n.get('title', '')) + ' ' + str(n.get('content', ''))
                sentiment = str(n.get('sentiment', ''))
                matched = self._match_sector_from_keywords(text, sector_map)
                for s in matched:
                    sector_news_count[s] += 1
                    if '利好' in sentiment:
                        sector_bullish[s] += 1
                    elif '利空' in sentiment:
                        sector_bearish[s] += 1

            # 分类：直接受益、间接受益、受损、中性
            direct_benefit = []
            indirect_benefit = []
            damaged = []
            neutral = []

            for sname, count in sector_news_count.items():
                if sname not in sector_map:
                    continue
                b = sector_bullish.get(sname, 0)
                be = sector_bearish.get(sname, 0)
                sec = sector_map[sname]
                change_pct = float(sec.get('change_pct', 0) or 0)
                info = {
                    'name': sname,
                    'change_pct': change_pct,
                    'news_count': count,
                    'bullish': b,
                    'bearish': be,
                }
                if b > be and b >= 1:
                    if change_pct > 1.0 or b >= 2:
                        direct_benefit.append(info)
                    else:
                        indirect_benefit.append(info)
                elif be > b:
                    damaged.append(info)
                else:
                    neutral.append(info)

            # 如果新闻匹配板块太少，补充涨幅前5和跌幅前3的板块
            if len(direct_benefit) + len(indirect_benefit) < 3 and sectors:
                top_sectors = sorted(sectors, key=lambda x: float(x.get('change_pct', 0) or 0), reverse=True)[:3]
                for sec in top_sectors:
                    sname = sec.get('name', '')
                    if sname and sname not in sector_news_count:
                        direct_benefit.append({
                            'name': sname,
                            'change_pct': float(sec.get('change_pct', 0) or 0),
                            'news_count': 0,
                            'bullish': 0,
                            'bearish': 0,
                        })

            module2_lines = ['<div style="margin:10px 0 8px;"><span style="color:#2563EB;font-size:13px;font-weight:bold;">🏭 板块影响图谱</span></div>']

            def _sector_row(info, label, label_color):
                cp = info['change_pct']
                cp_color = '#FF3B30' if cp > 0 else ('#34C759' if cp < 0 else C.TEXT3)
                cp_str = f'+{cp:.2f}%' if cp > 0 else f'{cp:.2f}%'
                logic = ''
                if info['news_count'] > 0:
                    if info['bullish'] > info['bearish']:
                        logic = f"新闻面利好({info['bullish']}条)"
                    elif info['bearish'] > info['bullish']:
                        logic = f"新闻面利空({info['bearish']}条)"
                    else:
                        logic = '新闻面多空交织'
                else:
                    logic = '市场资金主动驱动'
                return (f'<div style="margin:2px 0;padding:3px 8px;background:rgba(0,0,0,0.02);border-radius:4px;">'
                        f'<span style="color:{label_color};font-size:10px;font-weight:bold;">[{label}]</span> '
                        f'<span style="color:{C.TEXT};font-size:11px;font-weight:bold;">{info["name"]}</span> '
                        f'<span style="color:{cp_color};font-size:11px;font-weight:bold;">{cp_str}</span> '
                        f'<span style="color:{C.TEXT3};font-size:10px;">{logic}</span>'
                        f'</div>')

            if direct_benefit:
                module2_lines.append('<div style="color:#FF3B30;font-size:11px;font-weight:bold;margin:2px 0;">▲ 直接受益板块</div>')
                for info in sorted(direct_benefit, key=lambda x: x['change_pct'], reverse=True)[:4]:
                    module2_lines.append(_sector_row(info, '强', '#FF3B30'))
            if indirect_benefit:
                module2_lines.append('<div style="color:#FF9500;font-size:11px;font-weight:bold;margin:4px 0 2px;">△ 间接受益板块</div>')
                for info in sorted(indirect_benefit, key=lambda x: x['change_pct'], reverse=True)[:3]:
                    module2_lines.append(_sector_row(info, '中', '#FF9500'))
            if damaged:
                module2_lines.append('<div style="color:#34C759;font-size:11px;font-weight:bold;margin:4px 0 2px;">▼ 受损板块</div>')
                for info in sorted(damaged, key=lambda x: x['change_pct'])[:3]:
                    module2_lines.append(_sector_row(info, '弱', '#34C759'))
            if neutral:
                module2_lines.append('<div style="color:#64748B;font-size:11px;font-weight:bold;margin:4px 0 2px;">○ 中性板块</div>')
                for info in neutral[:2]:
                    module2_lines.append(_sector_row(info, '中', '#64748B'))

            # ========== 模块3：核心标的池 ==========
            # 从所有新闻中提取提及的股票
            all_mentioned_codes = set()
            code_news_map = defaultdict(list)  # code -> [news]
            for n in sample:
                codes, names = self._extract_stock_codes_from_news(n)
                for c in codes:
                    all_mentioned_codes.add(c)
                    code_news_map[c].append(n)

            # 批量获取行情
            quotes = self._batch_get_quotes(list(all_mentioned_codes))

            # 分类：领涨、弹性、风险
            leading_stocks = []
            elastic_stocks = []
            risk_stocks = []

            for code in all_mentioned_codes:
                q = quotes.get(code, {})
                pct = float(q.get('pct_chg', 0) or 0)
                name = q.get('name', '')
                if not name:
                    # 从新闻中找名称
                    for n in code_news_map.get(code, []):
                        stock_list = n.get('stock_codes', n.get('stocks', []))
                        if isinstance(stock_list, list):
                            for st in stock_list:
                                if isinstance(st, dict) and str(st.get('code', '')).zfill(6) == code:
                                    name = st.get('name', code)
                                    break
                        if name: break
                if not name:
                    name = code
                ai_score = ai520_scores.get(code, '--')
                # 核心逻辑
                news_titles = [self._refine_event_title(str(n.get('title', ''))) for n in code_news_map.get(code, [])[:2]]
                logic = '；'.join(news_titles) if news_titles else '新闻提及'
                sentiment = '利好'
                for n in code_news_map.get(code, []):
                    s = str(n.get('sentiment', ''))
                    if '利空' in s:
                        sentiment = '利空'
                        break
                    elif '中性' in s:
                        sentiment = '中性'

                info = {
                    'code': code, 'name': name, 'pct': pct,
                    'ai_score': ai_score, 'logic': logic, 'sentiment': sentiment,
                }
                if pct >= 3.0 and sentiment != '利空':
                    leading_stocks.append(info)
                elif pct < -2.0 or sentiment == '利空':
                    risk_stocks.append(info)
                else:
                    elastic_stocks.append(info)

            # 如果新闻提及股票太少，从板块top_stocks补充龙头
            if len(all_mentioned_codes) < 3 and sectors:
                top_sec = sorted(sectors, key=lambda x: float(x.get('change_pct', 0) or 0), reverse=True)[:2]
                for sec in top_sec:
                    for st in sec.get('top_stocks', [])[:3]:
                        code = str(st.get('code', '')).zfill(6)
                        if code and code not in all_mentioned_codes:
                            all_mentioned_codes.add(code)
                            q = self._batch_get_quotes([code]).get(code, {})
                            pct = float(q.get('pct_chg', st.get('change_pct', 0)) or 0)
                            name = q.get('name', st.get('name', code))
                            ai_score = ai520_scores.get(code, '--')
                            info = {
                                'code': code, 'name': name, 'pct': pct,
                                'ai_score': ai_score, 'logic': f"{sec.get('name','')}板块龙头",
                                'sentiment': '利好' if pct > 0 else '中性',
                            }
                            if pct >= 3.0:
                                leading_stocks.append(info)
                            elif pct < -2.0:
                                risk_stocks.append(info)
                            else:
                                elastic_stocks.append(info)

            module3_lines = ['<div style="margin:10px 0 8px;"><span style="color:#2563EB;font-size:13px;font-weight:bold;">🎯 核心标的池</span></div>']

            def _stock_row(info, label, label_color):
                pct = info['pct']
                pct_color = '#FF3B30' if pct > 0 else ('#34C759' if pct < 0 else C.TEXT3)
                pct_str = f'+{pct:.2f}%' if pct > 0 else f'{pct:.2f}%'
                ai_s = info['ai_score']
                ai_str = f'AI520:{ai_s:.0f}' if isinstance(ai_s, (int, float)) else f'AI520:{ai_s}'
                wl_tag = ' ⭐自选' if info['code'] in watchlist_codes else ''
                return (f'<div style="margin:2px 0;padding:3px 8px;background:rgba(0,0,0,0.02);border-radius:4px;">'
                        f'<span style="color:{label_color};font-size:10px;font-weight:bold;">[{label}]</span> '
                        f'<span style="color:{C.TEXT};font-size:11px;font-weight:bold;">{info["name"]}({info["code"]})</span>{wl_tag} '
                        f'<span style="color:{pct_color};font-size:11px;font-weight:bold;">{pct_str}</span> '
                        f'<span style="color:#AF52DE;font-size:10px;">{ai_str}</span> '
                        f'<span style="color:{C.TEXT3};font-size:10px;">{info["logic"][:30]}</span>'
                        f'</div>')

            if leading_stocks:
                module3_lines.append('<div style="color:#FF3B30;font-size:11px;font-weight:bold;margin:2px 0;">🚀 领涨标的</div>')
                for info in sorted(leading_stocks, key=lambda x: x['pct'], reverse=True)[:5]:
                    module3_lines.append(_stock_row(info, '领涨', '#FF3B30'))
            if elastic_stocks:
                module3_lines.append('<div style="color:#FF9500;font-size:11px;font-weight:bold;margin:4px 0 2px;">⚡ 弹性标的</div>')
                for info in sorted(elastic_stocks, key=lambda x: x['pct'], reverse=True)[:5]:
                    module3_lines.append(_stock_row(info, '弹性', '#FF9500'))
            if risk_stocks:
                module3_lines.append('<div style="color:#34C759;font-size:11px;font-weight:bold;margin:4px 0 2px;">⚠️ 风险标的</div>')
                for info in sorted(risk_stocks, key=lambda x: x['pct'])[:5]:
                    module3_lines.append(_stock_row(info, '风险', '#34C759'))

            # ========== 模块4：交易视角提示 ==========
            # 市场情绪判断
            bullish_n = sum(1 for n in sample if '利好' in str(n.get('sentiment', '')))
            bearish_n = sum(1 for n in sample if '利空' in str(n.get('sentiment', '')))
            neutral_n = len(sample) - bullish_n - bearish_n
            total_n = len(sample)

            if total_n > 0:
                bull_ratio = bullish_n / total_n
                bear_ratio = bearish_n / total_n
                if bull_ratio > 0.5:
                    mood = '升温'
                    mood_color = '#FF3B30'
                elif bear_ratio > 0.4:
                    mood = '降温'
                    mood_color = '#34C759'
                elif abs(bull_ratio - bear_ratio) < 0.15:
                    mood = '分化'
                    mood_color = '#FF9500'
                else:
                    mood = '偏暖'
                    mood_color = '#FF9500'
            else:
                mood = '中性'
                mood_color = '#64748B'

            # 风格偏向
            if sectors:
                top5 = sorted(sectors, key=lambda x: float(x.get('change_pct', 0) or 0), reverse=True)[:5]
                growth_sectors = ['电子', '计算机', '通信', '传媒', '电力设备', '国防军工', '医药生物']
                value_sectors = ['银行', '非银金融', '煤炭', '石油石化', '钢铁', '房地产', '建筑装饰']
                growth_count = sum(1 for s in top5 if s.get('name', '') in growth_sectors)
                value_count = sum(1 for s in top5 if s.get('name', '') in value_sectors)
                if growth_count > value_count:
                    style = '成长风格占优'
                elif value_count > growth_count:
                    style = '价值风格占优'
                else:
                    style = '风格均衡'
                # 大小盘
                small_sectors = ['电子', '计算机', '通信', '传媒', '机械设备', '纺织服饰']
                large_sectors = ['银行', '非银金融', '食品饮料', '石油石化', '煤炭', '房地产']
                small_count = sum(1 for s in top5 if s.get('name', '') in small_sectors)
                large_count = sum(1 for s in top5 if s.get('name', '') in large_sectors)
                size_style = '小盘活跃' if small_count > large_count else ('大盘稳健' if large_count > small_count else '大小盘均衡')
            else:
                style = '风格均衡'
                size_style = '大小盘均衡'

            # 风险提示
            risk_tips = []
            if bullish_n > bearish_n * 2:
                risk_tips.append('利好集中需防兑现回落')
            high_hot_bearish = [n for n in sample if float(n.get('hot_score', 0) or 0) >= 60 and '利空' in str(n.get('sentiment', ''))]
            if high_hot_bearish:
                risk_tips.append(f'高热度利空新闻{len(high_hot_bearish)}条，关注利空扩散')
            # 不及预期
            for n in sample:
                t = str(n.get('title', ''))
                if any(kw in t for kw in ['不及预期', '低于预期', '下滑', '亏损', '减持']):
                    risk_tips.append('存在业绩/事件不及预期风险')
                    break
            if not risk_tips:
                risk_tips.append('暂无显著系统性风险，关注个股层面波动')

            # 自选股关联
            wl_related = []
            for n in sample:
                codes, _ = self._extract_stock_codes_from_news(n)
                for c in codes:
                    if c in watchlist_codes:
                        wl_name = c
                        for w in data.get('watchlist', []):
                            if w.get('code') == c:
                                wl_name = w.get('name', c)
                                break
                        wl_related.append(f"{wl_name}({c})")
            wl_related = list(set(wl_related))

            module4_lines = ['<div style="margin:10px 0 8px;"><span style="color:#2563EB;font-size:13px;font-weight:bold;">💡 交易视角提示</span></div>']
            module4_lines.append(
                f'<div style="margin:2px 0;padding:3px 8px;background:rgba(0,0,0,0.02);border-radius:4px;">'
                f'<span style="color:{C.TEXT2};font-size:11px;">市场情绪：</span>'
                f'<span style="color:{mood_color};font-size:11px;font-weight:bold;">{mood}</span>'
                f'<span style="color:{C.TEXT3};font-size:10px;">（利好{bullish_n}/利空{bearish_n}/中性{neutral_n}，共{total_n}条）</span>'
                f'</div>'
            )
            module4_lines.append(
                f'<div style="margin:2px 0;padding:3px 8px;background:rgba(0,0,0,0.02);border-radius:4px;">'
                f'<span style="color:{C.TEXT2};font-size:11px;">风格偏向：</span>'
                f'<span style="color:{C.BLUE};font-size:11px;font-weight:bold;">{style} · {size_style}</span>'
                f'</div>'
            )
            module4_lines.append(
                f'<div style="margin:2px 0;padding:3px 8px;background:rgba(0,0,0,0.02);border-radius:4px;">'
                f'<span style="color:{C.TEXT2};font-size:11px;">风险提示：</span>'
                f'<span style="color:#FF9500;font-size:11px;">{"；".join(risk_tips[:2])}</span>'
                f'</div>'
            )
            if wl_related:
                module4_lines.append(
                    f'<div style="margin:2px 0;padding:3px 8px;background:rgba(234,179,8,0.08);border-radius:4px;border:1px solid rgba(234,179,8,0.3);">'
                    f'<span style="color:#FF9500;font-size:11px;font-weight:bold;">⭐ 自选股关联：</span>'
                    f'<span style="color:{C.TEXT};font-size:11px;">{"、".join(wl_related[:5])}</span>'
                    f'<span style="color:{C.TEXT3};font-size:10px;"> 相关新闻需重点关注</span>'
                    f'</div>'
                )

            # ========== 组合最终HTML ==========
            disclaimer = '<div style="text-align:right;margin-top:8px;"><span style="color:#64748B;font-size:9px;font-style:italic;">AI生成，仅供参考，不构成投资建议</span></div>'

            full_html = (
                ''.join(module1_lines) +
                ''.join(module2_lines) +
                ''.join(module3_lines) +
                ''.join(module4_lines) +
                disclaimer
            )

            self.ai_analysis_content.setText(full_html)
            self.ai_analysis_panel.setVisible(True)
            print(f'[AI新闻分析] 完成，分析{len(sample)}条新闻，提及{len(all_mentioned_codes)}只个股', flush=True)

        except Exception as e:
            print(f'[AI新闻分析] 异常: {e}', flush=True)
            import traceback; traceback.print_exc()
            try:
                self.ai_analysis_content.setText(f'AI分析暂不可用：{str(e)[:50]}')
                self.ai_analysis_panel.setVisible(True)
            except Exception:
                pass


    def _generate_single_news_interpretation(self, news):
        """生成单条新闻AI解读，固定5个维度"""
        try:
            data = self._get_local_data_for_analysis()
            sector_map = data.get('sector_map', {})
            watchlist_codes = data.get('watchlist_codes', set())
            ai520_scores = data.get('ai520_scores', {})

            title = str(news.get('title', ''))
            content_text = str(news.get('content', ''))
            source = str(news.get('source', ''))
            pub_time = str(news.get('publish_time', news.get('time', '')))
            if len(pub_time) > 16: pub_time = pub_time[:16]
            full_text = title + ' ' + content_text

            # 使用NewsInterpreter获取基础分析
            interp_result = {}
            try:
                from strategy.news_interpreter import NewsInterpreter
                interpreter = NewsInterpreter()
                interp_result = interpreter.interpret(news) or {}
            except Exception as e:
                print(f'[单条解读] NewsInterpreter失败: {e}', flush=True)

            sentiment = interp_result.get('sentiment', news.get('sentiment', '中性'))
            if not sentiment or sentiment not in ['利好', '利空', '中性']:
                sentiment = '中性'

            # ========== 维度1：事件定性 ==========
            event_type = self._classify_event_type(news)
            impact = self._calc_impact_level(news)
            sent_color = {'利好': '#FF3B30', '利空': '#34C759', '中性': '#64748B'}.get(sentiment, '#64748B')
            impact_color = {'强': '#FF3B30', '中': '#FF9500', '弱': '#64748B'}.get(impact, '#64748B')

            dim1 = (
                f'<div style="margin-bottom:6px;"><span style="color:#2563EB;font-size:12px;font-weight:bold;">① 事件定性</span></div>'
                f'<div style="padding:6px 10px;background:rgba(0,0,0,0.02);border-radius:4px;margin-bottom:8px;">'
                f'<span style="color:{C.TEXT2};font-size:11px;">事件类型：</span>'
                f'<span style="color:{C.BLUE};font-size:11px;font-weight:bold;">{event_type}</span>　'
                f'<span style="color:{C.TEXT2};font-size:11px;">影响等级：</span>'
                f'<span style="color:{impact_color};font-size:11px;font-weight:bold;">{impact}</span>　'
                f'<span style="color:{C.TEXT2};font-size:11px;">多空属性：</span>'
                f'<span style="color:{sent_color};font-size:11px;font-weight:bold;">{sentiment}</span>'
                f'</div>'
            )

            # ========== 维度2：板块传导逻辑 ==========
            matched_sectors = self._match_sector_from_keywords(full_text, sector_map)
            # 上下游传导分析
            upstream_map = {
                '电力设备': ['有色金属', '煤炭', '石油石化'],
                '电子': ['有色金属', '基础化工'],
                '汽车': ['钢铁', '有色金属', '石油石化'],
                '房地产': ['建筑材料', '钢铁', '家用电器'],
                '医药生物': ['基础化工', '农林牧渔'],
                '食品饮料': ['农林牧渔', '基础化工'],
                '计算机': ['电子', '通信', '电力设备'],
                '通信': ['电子', '电力设备'],
                '国防军工': ['钢铁', '有色金属', '电子'],
                '机械设备': ['钢铁', '有色金属', '电力设备'],
                '交通运输': ['石油石化', '煤炭'],
                '公用事业': ['煤炭', '石油石化', '有色金属'],
                '建筑装饰': ['钢铁', '建筑材料', '有色金属'],
            }
            downstream_map = {v: k for k, vals in upstream_map.items() for v in vals}

            sector_lines = []
            for sname in matched_sectors[:4]:
                sec = sector_map.get(sname, {})
                cp = float(sec.get('change_pct', 0) or 0)
                cp_color = '#FF3B30' if cp > 0 else ('#34C759' if cp < 0 else C.TEXT3)
                cp_str = f'+{cp:.2f}%' if cp > 0 else f'{cp:.2f}%'
                reacted = '已提前反应' if abs(cp) > 1.5 else '尚未充分反应'
                # 上下游
                up = upstream_map.get(sname, [])[:2]
                down_keys = [k for k, v in upstream_map.items() if sname in v][:2]
                chain_parts = []
                if up: chain_parts.append('上游:' + '/'.join(up))
                if down_keys: chain_parts.append('下游:' + '/'.join(down_keys))
                chain = '；'.join(chain_parts) if chain_parts else '产业链位置：中游'
                sector_lines.append(
                    f'<div style="margin:2px 0;padding:4px 8px;background:rgba(0,0,0,0.02);border-radius:4px;">'
                    f'<span style="color:{C.TEXT};font-size:11px;font-weight:bold;">{sname}</span> '
                    f'<span style="color:{cp_color};font-size:11px;font-weight:bold;">{cp_str}</span> '
                    f'<span style="color:{C.TEXT3};font-size:10px;">[{reacted}]</span> '
                    f'<span style="color:{C.TEXT3};font-size:10px;">{chain}</span>'
                    f'</div>'
                )

            if not sector_lines:
                sector_lines.append('<div style="color:#64748B;font-size:11px;padding:4px 8px;">未匹配到明确申万一级行业，关注泛主题性机会</div>')

            dim2 = (
                f'<div style="margin:8px 0 6px;"><span style="color:#2563EB;font-size:12px;font-weight:bold;">② 板块传导逻辑</span></div>'
                + ''.join(sector_lines)
            )

            # ========== 维度3：关联标的分析 ==========
            codes, names = self._extract_stock_codes_from_news(news)
            quotes = self._batch_get_quotes(codes)

            stock_lines = []
            for code in codes:
                q = quotes.get(code, {})
                pct = float(q.get('pct_chg', 0) or 0)
                name = q.get('name', '')
                if not name:
                    stock_list = news.get('stock_codes', news.get('stocks', []))
                    if isinstance(stock_list, list):
                        for st in stock_list:
                            if isinstance(st, dict) and str(st.get('code', '')).zfill(6) == code:
                                name = st.get('name', code)
                                break
                if not name:
                    name = code
                pct_color = '#FF3B30' if pct > 0 else ('#34C759' if pct < 0 else C.TEXT3)
                pct_str = f'+{pct:.2f}%' if pct > 0 else f'{pct:.2f}%'
                ai_s = ai520_scores.get(code, '--')
                ai_str = f'AI520:{ai_s:.0f}' if isinstance(ai_s, (int, float)) else f'AI520:{ai_s}'
                # 受益/受损逻辑
                if '利空' in sentiment:
                    logic = '新闻利空承压'
                elif '利好' in sentiment:
                    logic = '新闻利好驱动'
                else:
                    logic = '新闻关联关注'
                wl_tag = ' ⭐自选' if code in watchlist_codes else ''
                stock_lines.append(
                    f'<div style="margin:2px 0;padding:4px 8px;background:rgba(0,0,0,0.02);border-radius:4px;">'
                    f'<span style="color:{C.TEXT};font-size:11px;font-weight:bold;">{name}({code})</span>{wl_tag} '
                    f'<span style="color:{pct_color};font-size:11px;font-weight:bold;">{pct_str}</span> '
                    f'<span style="color:#AF52DE;font-size:10px;">{ai_str}</span> '
                    f'<span style="color:{C.TEXT3};font-size:10px;">{logic}</span>'
                    f'</div>'
                )

            # 补充同板块龙头
            if matched_sectors:
                top_sec_name = matched_sectors[0]
                top_sec = sector_map.get(top_sec_name, {})
                for st in top_sec.get('top_stocks', [])[:2]:
                    code = str(st.get('code', '')).zfill(6)
                    if code and code not in codes:
                        pct = float(st.get('change_pct', 0) or 0)
                        name = st.get('name', code)
                        pct_color = '#FF3B30' if pct > 0 else ('#34C759' if pct < 0 else C.TEXT3)
                        pct_str = f'+{pct:.2f}%' if pct > 0 else f'{pct:.2f}%'
                        ai_s = ai520_scores.get(code, '--')
                        ai_str = f'AI520:{ai_s:.0f}' if isinstance(ai_s, (int, float)) else f'AI520:{ai_s}'
                        stock_lines.append(
                            f'<div style="margin:2px 0;padding:4px 8px;background:rgba(37,99,235,0.04);border-radius:4px;">'
                            f'<span style="color:{C.TEXT};font-size:11px;font-weight:bold;">{name}({code})</span> '
                            f'<span style="color:{pct_color};font-size:11px;font-weight:bold;">{pct_str}</span> '
                            f'<span style="color:#AF52DE;font-size:10px;">{ai_str}</span> '
                            f'<span style="color:{C.TEXT3};font-size:10px;">同板块龙头·{top_sec_name}</span>'
                            f'</div>'
                        )

            if not stock_lines:
                stock_lines.append('<div style="color:#64748B;font-size:11px;padding:4px 8px;">新闻未明确提及个股代码，关注板块整体机会</div>')

            dim3 = (
                f'<div style="margin:8px 0 6px;"><span style="color:#2563EB;font-size:12px;font-weight:bold;">③ 关联标的分析</span></div>'
                + ''.join(stock_lines)
            )

            # ========== 维度4：市场影响与预期 ==========
            # 短期影响
            if impact == '强' and sentiment == '利好':
                short_term = '短期情绪提振明显，相关标的或有脉冲式上涨'
            elif impact == '强' and sentiment == '利空':
                short_term = '短期情绪压制显著，相关标的承压回调风险大'
            elif impact == '中' and sentiment == '利好':
                short_term = '短期有一定情绪支撑，关注量能配合'
            elif impact == '中' and sentiment == '利空':
                short_term = '短期情绪偏负面，注意规避相关标的'
            else:
                short_term = '短期影响有限，市场或已部分消化'

            # 中期影响
            if event_type in ['政策', '宏观事件']:
                mid_term = '中期影响深远，政策导向决定板块中期趋势'
            elif event_type == '业绩':
                mid_term = '中期需观察业绩持续性，单季数据影响有限'
            elif event_type == '公告':
                mid_term = '中期看事件落地进度，关注后续公告跟进'
            else:
                mid_term = '中期影响取决于行业基本面变化，需持续跟踪'

            # 关键验证点
            verify_points = []
            if matched_sectors:
                verify_points.append(f"{matched_sectors[0]}板块成交量与涨幅持续性")
            if codes:
                verify_points.append(f"{'/'.join(codes[:2])}等个股资金流向")
            if event_type == '政策':
                verify_points.append('后续配套细则与执行力度')
            elif event_type == '业绩':
                verify_points.append('下一季度业绩指引与机构评级变化')
            elif event_type == '公告':
                verify_points.append('事件进展公告与监管反馈')
            if not verify_points:
                verify_points.append('市场成交量与情绪指标变化')

            dim4 = (
                f'<div style="margin:8px 0 6px;"><span style="color:#2563EB;font-size:12px;font-weight:bold;">④ 市场影响与预期</span></div>'
                f'<div style="padding:6px 10px;background:rgba(0,0,0,0.02);border-radius:4px;margin-bottom:4px;">'
                f'<div style="margin:2px 0;"><span style="color:{C.TEXT2};font-size:11px;">短期(当日/次日)：</span><span style="color:{C.TEXT};font-size:11px;">{short_term}</span></div>'
                f'<div style="margin:2px 0;"><span style="color:{C.TEXT2};font-size:11px;">中期(3-5日)：</span><span style="color:{C.TEXT};font-size:11px;">{mid_term}</span></div>'
                f'</div>'
                f'<div style="padding:4px 10px;"><span style="color:#FF9500;font-size:11px;font-weight:bold;">关键验证点：</span>'
                f'<span style="color:{C.TEXT};font-size:11px;">{"；".join(verify_points[:3])}</span></div>'
            )

            # ========== 维度5：交易风险提示 ==========
            risk_items = []
            # 利好兑现/利空不及预期
            if sentiment == '利好':
                risk_items.append('利好兑现后获利回吐风险，避免追高')
            elif sentiment == '利空':
                risk_items.append('利空可能持续发酵，注意止损控制')
            else:
                risk_items.append('中性事件方向不明，观望为主')
            # 连板炸板风险
            for code in codes:
                q = quotes.get(code, {})
                pct = float(q.get('pct_chg', 0) or 0)
                if pct >= _lu_pct(code):      # [CYB-GATE] 按板性：创业板 19.5 / 北交所 29.5
                    risk_items.append(f'{code}接近涨停，注意连板炸板风险')
                    break
            # 流动性风险
            if codes:
                low_liq = []
                for code in codes:
                    q = quotes.get(code, {})
                    amt = float(q.get('amount', 0) or 0)
                    if amt > 0 and amt < 50000000:  # 成交额<5000万
                        low_liq.append(code)
                if low_liq:
                    risk_items.append(f'{"、".join(low_liq[:2])}成交额偏低，注意流动性风险')
            # 自选股持仓提示
            wl_in_news = [c for c in codes if c in watchlist_codes]
            if wl_in_news:
                wl_names = []
                for c in wl_in_news:
                    for w in data.get('watchlist', []):
                        if w.get('code') == c:
                            wl_names.append(f"{w.get('name', c)}({c})")
                            break
                risk_items.append(f'⭐涉及自选股：{"、".join(wl_names)}，请结合持仓情况评估')

            dim5 = (
                f'<div style="margin:8px 0 6px;"><span style="color:#2563EB;font-size:12px;font-weight:bold;">⑤ 交易风险提示</span></div>'
                f'<div style="padding:6px 10px;background:rgba(255,59,48,0.04);border-radius:4px;border:1px solid rgba(255,59,48,0.15);">'
            )
            for i, r in enumerate(risk_items[:4]):
                dim5 += f'<div style="margin:2px 0;color:#FF3B30;font-size:11px;">⚠ {r}</div>'
            dim5 += '</div>'

            # 组合
            disclaimer = '<div style="text-align:right;margin-top:6px;"><span style="color:#64748B;font-size:9px;font-style:italic;">AI解读，仅供参考</span></div>'
            full_html = dim1 + dim2 + dim3 + dim4 + dim5 + disclaimer
            return full_html

        except Exception as e:
            print(f'[单条解读] 生成异常: {e}', flush=True)
            import traceback; traceback.print_exc()
            return f'<div style="color:#FF3B30;font-size:11px;">解读生成失败：{str(e)[:40]}</div>'

    def _highlight_keyword(self, text, keyword=None):
        """将文本中的关键词用黄色背景高亮（返回HTML）
        非搜索模式或无关键词时返回纯文本（转义HTML特殊字符）"""
        if not text:
            return ''
        if not self._search_active:
            # 非搜索模式：转义HTML特殊字符，防止注入
            return (str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
        kw = keyword or self._current_search_keyword
        if not kw:
            return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        # 转义文本中的HTML特殊字符
        safe_text = str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        safe_kw = str(kw).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        # 大小写不敏感替换（对中文无效但对英文有效）
        try:
            pattern = _re_mod.escape(safe_kw)
            highlighted = _re_mod.sub(
                pattern,
                lambda m: f'<span style="background:#FEF3C7;color:#92400E;">{m.group(0)}</span>',
                safe_text,
                flags=_re_mod.IGNORECASE
            )
            return highlighted
        except Exception:
            return safe_text

    def _classify_news_category(self, news):
        """新闻分类：股票/宏观/行业/国际/大宗/市场/公告，返回(category, color_hex)"""
        title = str(news.get('title', ''))
        content = str(news.get('content', ''))
        source = str(news.get('source', ''))
        news_type = str(news.get('news_type', ''))
        full_text = title + ' ' + content

        # 优先级0：精准对应具体股票（出现6位股票代码 或 标题含上市公司简称）
        import re as _re
        if _re.search(r'(?<!\d)(000|001|002|003|300|301|600|601|603|605|688|689)\d{3}(?!\d)', full_text) \
                or _re.search(r'[\u4e00-\u9fa5]{2,8}(股份|科技|集团|控股|电气|能源|医药|生物|电子|新材|重工|精密|智能|通信|光电|微电|新能|股份)', title):
            return ('股票', '#FF6B00')

        # 优先级1：数据源自带类型
        if news_type == '公告' or source in ['巨潮资讯', '巨潮']:
            return ('公告', '#757575')

        # 优先级2：关键词匹配（按优先级）
        # 公告类
        if any(k in full_text for k in ['业绩', '公告', '股东会', '质押', '并购', '定增',
                                         '减持', '回购', '分红', '中标', '合同', '年报', '季报',
                                         '半年报', '披露', '重组', '招股', '上市']):
            return ('公告', '#757575')
        # 宏观类
        if any(k in full_text for k in ['央行', '利率', 'CPI', 'GDP', 'PMI', '社融', '财政',
                                         '国务院', '发改委', '货币政策', '降准', '加息', '降息',
                                         '汇率', '进出口', '外汇', '财政部', '人民银行', 'LPR',
                                         '存款准备金', '逆回购', 'MLF', '国债', '社会融资']):
            return ('宏观', '#E53935')
        # 国际类
        if any(k in full_text for k in ['美联储', '美股', '港股', '欧洲', '欧盟', '地缘',
                                         '海外', '全球', '国际', '美元', '特朗普', '白宫',
                                         '北约', '俄罗斯', '乌克兰', '中东', '日本央行', '英国央行',
                                         '纳斯达克', '道琼斯', '标普', '欧央行']):
            return ('国际', '#8E24AA')
        # 大宗类
        if any(k in full_text for k in ['原油', '天然气', '煤炭', '铜', '铝', '黄金', '白银',
                                         '农产品', '化工', '铁矿石', '钢材', '库存', 'OPEC',
                                         '布油', 'WTI', '原油价格', '金价', '铜价', '钢价']):
            return ('大宗', '#FF8A3D')
        # 市场类
        if any(k in full_text for k in ['大盘', '板块', '资金流向', '北向', '龙虎榜',
                                         '涨停', '跌停', '异动', '轮动', '成交额', '两市',
                                         '上证指数', '深证成指', '创业板', '沪深', 'A股',
                                         '三大指数', '成交量', '主力资金', '外资']):
            return ('市场', '#43A047')
        # 行业类（默认）
        if any(k in full_text for k in ['行业', '产业', '规划', '政策', '技术突破',
                                         '供需', '产业链', '产能', '景气', '赛道', '新能源',
                                         '半导体', '人工智能', 'AI', '医药', '军工', '汽车']):
            return ('行业', '#2F6BFF')
        return ('行业', '#2F6BFF')

    def _on_category_changed(self):
        """分类下拉变化时重新筛选"""
        if self.category_combo is None:
            return
        self._current_category = self.category_combo.currentText()
        self._apply_filter()

    def _check_news_mark(self, news):
        """检查新闻标记类型：'watchlist'(蓝) / 'sector'(橙) / None(无)
        同时属于自选和板块时优先自选（蓝色）"""
        try:
            data = self._get_local_data_for_analysis()
            watchlist_codes = data.get('watchlist_codes', set())

            # 提取新闻中的股票代码
            codes, names = self._extract_stock_codes_from_news(news)

            # 1. 自选匹配（优先）
            if watchlist_codes:
                for c in codes:
                    if c in watchlist_codes:
                        return 'watchlist'

            # 2. 板块匹配
            sector_map = data.get('sector_map', {})
            title = str(news.get('title', ''))
            content = str(news.get('content', ''))
            matched = self._match_sector_from_keywords(title + ' ' + content, sector_map)
            if matched:
                return 'sector'

            return None
        except Exception:
            return None

    def _create_news_card(self, news: Dict) -> QFrame:
        """V4.0 新闻卡片：96px最小高度、16px标题、12px时间、蓝色股票标签、橙色AI按钮"""
        card = QFrame()
        card.setMinimumHeight(96)
        card.setStyleSheet(
            f'QFrame{{background:{C.CARD};border:1px solid {C.BORDER};border-radius:8px;}}'
            f'QFrame:hover{{border:1px solid {C.BLUE};}}'
        )

        # 左侧色条 + 内容
        outer_layout = QHBoxLayout(card)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # 左侧色条标记
        mark_type = self._check_news_mark(news)
        color_bar = QFrame()
        color_bar.setFixedWidth(4)
        if mark_type == 'watchlist':
            color_bar.setStyleSheet('background:#2F6BFF;border:none;')
        elif mark_type == 'sector':
            color_bar.setStyleSheet('background:#FF8A3D;border:none;')
        else:
            color_bar.setStyleSheet('background:transparent;border:none;')
        outer_layout.addWidget(color_bar)

        # 右侧内容区
        content_widget = QFrame()
        content_widget.setStyleSheet('background:transparent;border:none;')
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # 第一行：类型标签 + 标题
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        # 分类标签（宏观/行业/国际/大宗/市场/公告）
        cat_name, cat_color = self._classify_news_category(news)
        cat_tag = QLabel(cat_name)
        cat_tag.setStyleSheet(
            f'color:{cat_color};background:{cat_color}14;border:1px solid {cat_color};'
            f'border-radius:4px;padding:1px 6px;font-size:11px;font-weight:bold;'
        )
        top_row.addWidget(cat_tag)

        # 类型标签（自选/板块标记）
        if mark_type == 'watchlist':
            tag = QLabel('自选消息')
            tag.setStyleSheet(
                'color:#2F6BFF;background:rgba(47,107,255,0.08);border:1px solid #2F6BFF;'
                'border-radius:3px;padding:1px 6px;font-size:11px;font-weight:bold;'
            )
            top_row.addWidget(tag)
        elif mark_type == 'sector':
            tag = QLabel('板块消息')
            tag.setStyleSheet(
                'color:#FF8A3D;background:rgba(255,138,61,0.08);border:1px solid #FF8A3D;'
                'border-radius:3px;padding:1px 6px;font-size:11px;font-weight:bold;'
            )
            top_row.addWidget(tag)

        # 标题 16px 加粗黑色
        _raw_title = news.get('title', '')
        if self._search_active and self._current_search_keyword:
            title_label = QLabel(self._highlight_keyword(_raw_title))
            title_label.setStyleSheet(f'color:{C.TEXT};font-size:16px;font-weight:bold;background:transparent;')
        else:
            title_label = QLabel(_raw_title)
            title_label.setStyleSheet(f'color:{C.TEXT};font-size:16px;font-weight:bold;background:transparent;')
        title_label.setWordWrap(True)
        top_row.addWidget(title_label, 1)

        layout.addLayout(top_row)

        # 第二行：来源/时间 12px灰色（精确到秒）
        source = str(news.get('source', ''))
        pub_time = str(news.get('publish_time', news.get('time', '')))
        time_str = pub_time
        if len(time_str) == 16:
            time_str = time_str + ':00'
        meta_label = QLabel(f'{source}  {time_str}')
        meta_label.setStyleSheet(f'color:{C.TEXT3};font-size:12px;background:transparent;')
        layout.addWidget(meta_label)

        # 第三行：关联股票标签 + AI解读按钮
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(6)

        stocks = news.get('stock_codes', news.get('stocks', []))
        if stocks:
            for st in stocks[:5]:
                code = ''
                name = ''
                if isinstance(st, dict):
                    code = str(st.get('code', '')).zfill(6)
                    name = st.get('name', code)
                elif isinstance(st, str):
                    code = st.zfill(6)
                    name = st
                if code:
                    stock_btn = QPushButton(name or code)
                    stock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    stock_btn.setStyleSheet(
                        'QPushButton{color:#2F6BFF;background:rgba(47,107,255,0.06);'
                        'border:1px solid #2F6BFF;border-radius:3px;padding:2px 8px;'
                        'font-size:13px;}QPushButton:hover{background:rgba(47,107,255,0.12);}'
                    )
                    stock_btn.clicked.connect(lambda checked, c=code, n=name: self.stock_clicked.emit(c, n or c))
                    bottom_row.addWidget(stock_btn)

        bottom_row.addStretch()

        # AI解读按钮（DeepSeek网页版免费）
        ai_btn = QPushButton('AI解读')
        ai_btn.setFixedSize(90, 32)
        ai_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ai_btn.setStyleSheet(
            'QPushButton{background:#FF6D00;color:white;border:none;border-radius:4px;'
            'font-size:13px;font-weight:bold;}QPushButton:hover{background:#E65F00;}'
        )
        ai_btn.clicked.connect(lambda checked, n=news: self._show_ai_interp_dialog(n))
        bottom_row.addWidget(ai_btn)

        layout.addLayout(bottom_row)
        outer_layout.addWidget(content_widget, 1)
        return card

    def _show_free_interp_window(self, news):
        """AI新闻解读弹窗（QTextBrowser滚动版）"""
        try:
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QTextBrowser
            dialog = QDialog(self)
            dialog.setWindowTitle('AI新闻解读')
            dialog.setFixedSize(1100, 750)
            dialog.setStyleSheet('QDialog{background:#f5f7fa;}')
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(15, 15, 15, 15)
            layout.setSpacing(10)

            title = QLabel('📰 ' + news.get('title', '')[:60])
            title.setStyleSheet('color:#1f2937;font-size:14px;font-weight:bold;')
            title.setWordWrap(True)
            layout.addWidget(title)

            status = QLabel('🔍 AI正在生成解读，请稍候...')
            status.setStyleSheet('color:#3b82f6;font-size:13px;background:#eff6ff;padding:8px;border-radius:6px;')
            layout.addWidget(status)

            result = QTextBrowser()
            result.setReadOnly(True)
            result.setOpenExternalLinks(True)
            result.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            result.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            result.setStyleSheet('QTextBrowser{background:white;color:#1f2937;border:1px solid #e4e7ed;border-radius:6px;font-size:13px;line-height:1.6;padding:10px;}')
            layout.addWidget(result, 1)

            close_btn = QPushButton('关闭')
            close_btn.setFixedSize(80, 32)
            close_btn.clicked.connect(dialog.close)
            layout.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignRight)

            dialog.show()

            def run_interpret():
                try:
                    from services.deepseek_web_interpreter import DeepSeekWebInterpreter
                    interp = DeepSeekWebInterpreter()
                    res = interp.interpret_news(news.get('title', ''), news.get('content', ''))
                    result.setPlainText(res)
                    status.setText('✅ 解读完成')
                    status.setStyleSheet('color:#16a34a;font-size:13px;background:#f0fdf4;padding:8px;border-radius:6px;')
                    print(f'[AI解读] 文本长度: {len(res)}', flush=True)
                    print(f'[AI解读] 正文高度: {result.height()}', flush=True)
                    print(f'[AI解读] 滚动条最大值: {result.verticalScrollBar().maximum()}', flush=True)
                except Exception as e:
                    status.setText(f'❌ 解读失败: {str(e)[:60]}')

            from PyQt6.QtCore import QTimer
            QTimer.singleShot(100, run_interpret)

        except Exception as e:
            print(f'[AI解读窗口] 异常: {e}', flush=True)

    def _show_ai_interp_dialog(self, news):
        """AI新闻解读（改用DeepSeek网页版，免费）"""
        self._show_free_interp_window(news)


    def _populate_ai_matrix(self, dialog, loading_label, analysis):
        """V6量化投研简报布局：QScrollArea包裹6模块卡片（一句话核心/深度逻辑/机会红榜/风险黑榜/交易共振/量化标签JSON）"""
        try:
            loading_label.setVisible(False)
            try:
                loading_label.deleteLater()
            except Exception:
                pass

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet('QScrollArea{background:transparent;border:none;}')
            container = QWidget()
            container.setStyleSheet('background:transparent;')
            cl = QVBoxLayout(container)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(10)

            # 顶部多空结论条 + 影响等级
            sentiment = analysis.get('sentiment', '中性')
            impact = analysis.get('impact', '中')
            if sentiment in ('利好', '中性偏观察'):
                scolor = '#FF3B30'
            elif sentiment in ('利空', '中性偏谨慎'):
                scolor = '#34C759'
            else:
                scolor = '#64748B'
            impact_color = '#FF3B30' if impact == '强' else ('#FF9500' if impact == '中' else '#64748B')
            banner = QLabel(
                f'<span style="color:{scolor};font-weight:bold;">● {sentiment}</span>'
                f'　影响等级：<span style="color:{impact_color};font-weight:bold;">{impact}</span>'
                f'　<span style="color:#64748B;">量化投研简报 · 6模块</span>'
            )
            banner.setStyleSheet(
                'background:#F5F7FA;border:1px solid #E2E8F0;border-radius:6px;padding:8px 12px;font-size:14px;'
            )
            cl.addWidget(banner)

            # AI大模型模式：六模块markdown全文（剥离内嵌JSON代码块，标签由下方chip卡片展示）
            if analysis.get('mode') == 'ai':
                import re as _re
                _md_text = analysis.get('text', '') or ''
                # 删除 markdown 中自带的 ```json {...} ``` 代码块（已解析为 quant 字段，下方chip卡片展示）
                _md_text = _re.sub(r'```json\s*\{.*?\}\s*```', '', _md_text, flags=_re.DOTALL)
                # 兼容未包围栏的裸JSON段（以 { 开头、含 sentiment_score 的行块）
                _md_text = _re.sub(r'\{[^{}]*"sentiment_score"[^{}]*\}', '', _md_text, flags=_re.DOTALL)
                # 股票名(代码) 红色高亮，方便一眼看出
                _md_text = _re.sub(
                    r'([\u4e00-\u9fa5A-Za-z][\u4e00-\u9fa5A-Za-z0-9]{1,9})\((\d{6})\)',
                    r'<span style="color:#FF3B30;font-weight:bold;">\1(\2)</span>',
                    _md_text,
                )
                # 独立出现的6位股票代码也标红
                _md_text = _re.sub(
                    r'(?<![\w(\d])(\d{6})(?![\d)])',
                    r'<span style="color:#FF3B30;font-weight:bold;">\1</span>',
                    _md_text,
                )
                tb = QTextBrowser()
                tb.setMarkdown(_md_text)
                tb.setOpenExternalLinks(False)
                tb.setStyleSheet(
                    'QTextBrowser{background:#F5F7FA;border:1px solid #E2E8F0;border-radius:8px;'
                    'font-size:13px;line-height:1.7;}'
                )
                cl.addWidget(tb)

                scroll.setWidget(container)
                dialog.layout().addWidget(scroll, 1)
                return

            # 1. ⚡ 一句话核心提炼（高亮卡片）
            core_pick = analysis.get('core_pick', '--')
            core_card = QFrame()
            core_card.setStyleSheet('QFrame{background:#FFF7ED;border:1px solid #FDBA74;border-radius:8px;}')
            cvl = QVBoxLayout(core_card)
            cvl.setContentsMargins(12, 10, 12, 10)
            cvl.setSpacing(6)
            ct = QLabel('<b><span style="color:#EA580C;">⚡ 一句话核心提炼</span></b>')
            ct.setTextFormat(Qt.TextFormat.RichText)
            ct.setStyleSheet('background:transparent;')
            cb = QLabel(core_pick)
            cb.setTextFormat(Qt.TextFormat.RichText)
            cb.setWordWrap(True)
            cb.setStyleSheet('color:#9A3412;font-size:15px;font-weight:bold;background:transparent;')
            cb.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            cvl.addWidget(ct)
            cvl.addWidget(cb)
            cl.addWidget(core_card)

            # 2. 🧠 深度逻辑拆解（事件定性/预期差/传导机制/时效催化 4子项）
            logic_blocks = [
                ('事件定性', analysis.get('logic_event', '--')),
                ('预期差分析', analysis.get('logic_gap', '--')),
                ('传导机制', analysis.get('logic_chain', '--')),
                ('时效与催化', analysis.get('logic_catalyst', '--')),
            ]
            logic_card = QFrame()
            logic_card.setStyleSheet('QFrame{background:#F5F7FA;border:1px solid #E2E8F0;border-radius:8px;}')
            lvl = QVBoxLayout(logic_card)
            lvl.setContentsMargins(12, 10, 12, 10)
            lvl.setSpacing(6)
            lt = QLabel('<b><span style="color:#2563EB;">🧠 深度逻辑拆解</span></b>')
            lt.setTextFormat(Qt.TextFormat.RichText)
            lt.setStyleSheet('background:transparent;')
            lvl.addWidget(lt)
            for sub_title, sub_body in logic_blocks:
                sub_t = QLabel(f'<b><span style="color:#64748B;">{sub_title}：</span></b>')
                sub_t.setTextFormat(Qt.TextFormat.RichText)
                sub_t.setStyleSheet('background:transparent;font-size:13px;')
                sub_t.setWordWrap(True)
                lvl.addWidget(sub_t)
                sub_b = QLabel(sub_body)
                sub_b.setTextFormat(Qt.TextFormat.RichText)
                sub_b.setWordWrap(True)
                sub_b.setStyleSheet('color:#1E293B;font-size:13px;background:transparent;')
                sub_b.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
                lvl.addWidget(sub_b)
                lvl.addSpacing(4)
            cl.addWidget(logic_card)

            # 3/4/5. 📈 机会红榜 / 📉 风险黑榜 / 🌡️ 交易共振
            for title, key, accent in [
                ('📈 机会挖掘（红榜）', 'opportunity', '#DC2626'),
                ('📉 风险预警（黑榜）', 'risk', '#059669'),
                ('🌡️ 交易环境共振', 'resonance', '#2563EB'),
            ]:
                card = QFrame()
                card.setStyleSheet('QFrame{background:#F5F7FA;border:1px solid #E2E8F0;border-radius:8px;}')
                vl = QVBoxLayout(card)
                vl.setContentsMargins(12, 10, 12, 10)
                vl.setSpacing(6)
                t = QLabel(f'<b><span style="color:{accent};">{title}</span></b>')
                t.setTextFormat(Qt.TextFormat.RichText)
                t.setStyleSheet('background:transparent;')
                b = QLabel(analysis.get(key, '--'))
                b.setTextFormat(Qt.TextFormat.RichText)
                b.setWordWrap(True)
                b.setStyleSheet('color:#1E293B;font-size:13px;background:transparent;')
                b.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
                vl.addWidget(t)
                vl.addWidget(b)
                cl.addWidget(card)

            # 6. 🏷️ 量化标签（紧凑 chip 卡片，不显示原始JSON）
            quant = analysis.get('quant') or {}
            from PyQt6.QtWidgets import QGridLayout as _QGrid

            def _chip(text, bg='#EEF2F7', fg='#1E293B'):
                c = QLabel(str(text))
                c.setStyleSheet(
                    f'background:{bg};color:{fg};border-radius:10px;padding:3px 10px;font-size:11px;'
                )
                c.setAlignment(Qt.AlignmentFlag.AlignCenter)
                return c

            tags_card = QFrame()
            tags_card.setStyleSheet('QFrame{background:#F5F7FA;border:1px solid #E2E8F0;border-radius:8px;}')
            tvl = QVBoxLayout(tags_card)
            tvl.setContentsMargins(12, 10, 12, 10)
            tvl.setSpacing(8)
            tvl.addWidget(_chip('🏷️ 量化标签', bg='#DBEAFE', fg='#1D4ED8'))

            # 情绪分（大数字 chip）
            try:
                _score = float(quant.get('sentiment_score', 0) or 0)
            except Exception:
                _score = 0.0
            score_bg = '#FEE2E2' if _score >= 0.2 else ('#DCFCE7' if _score <= -0.2 else '#F3F4F6')
            score_fg = '#DC2626' if _score >= 0.2 else ('#059669' if _score <= -0.2 else '#4B5563')
            score_chip = QLabel(f'情绪分 {_score:+.2f}')
            score_chip.setStyleSheet(f'background:{score_bg};color:{score_fg};border-radius:10px;padding:4px 12px;font-size:12px;font-weight:bold;')
            score_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # 键值对 chips
            def _kv(label, value):
                if value is None or value == '' or value == 'none':
                    value = '--'
                return _chip(f'{label}: {value}')

            grid = _QGrid()
            grid.setSpacing(6)
            grid.addWidget(score_chip, 0, 0)
            grid.addWidget(_kv('相关度', quant.get('relevance_score')), 0, 1)
            grid.addWidget(_kv('风险', quant.get('risk_level')), 0, 2)
            grid.addWidget(_kv('影响时长', quant.get('impact_duration')), 0, 3)
            grid.addWidget(_kv('板块阶段', quant.get('sector_stage')), 1, 0)
            grid.addWidget(_kv('市场风格', quant.get('market_regime')), 1, 1)
            grid.addWidget(_kv('交易风格', quant.get('trade_style')), 1, 2)
            ev = quant.get('evidence_level') or '--'
            ev_color = '#DC2626' if ev == 'A' else ('#FF9500' if ev == 'B' else '#4B5563')
            grid.addWidget(_chip(f'证据等级 {ev}', bg='#FEF3C7', fg=ev_color), 1, 3)
            tvl.addLayout(grid)

            # 板块标签 chips 行
            sec_tags = quant.get('sector_tags') or []
            if isinstance(sec_tags, list) and sec_tags:
                from PyQt6.QtWidgets import QHBoxLayout as _QHBox
                row = _QHBox()
                row.setSpacing(6)
                for t in sec_tags[:5]:
                    row.addWidget(_chip(str(t), bg='#FEF3C7', fg='#92400E'))
                row.addStretch()
                tvl.addLayout(row)
            cl.addWidget(tags_card)
            cl.addStretch(1)

            scroll.setWidget(container)
            dialog.layout().addWidget(scroll, 1)
        except Exception as e:
            print(f'[AI解读] 6模块渲染异常: {e}', flush=True)
            import traceback
            traceback.print_exc()

    def _generate_concise_analysis(self, news):
        """V6量化投研简报（新规范6模块）：核心提炼/深度逻辑/机会红榜/风险黑榜/交易共振/量化标签。
        核心引擎：_v6_build_analysis（复用分类传导链 + 问财/板块数据）。
        增强：本地个股行情提取 + 多空一致性校验。"""
        try:
            from ui.news_v6_interpreter import _v6_build_analysis
            data = self._get_local_data_for_analysis()
            sector_map = data.get('sector_map', {})
            watchlist_codes = data.get('watchlist_codes', set())

            title = str(news.get('title', ''))
            content_text = str(news.get('content', ''))
            full_text = title + ' ' + content_text

            # 1. V6量化投研简报（核心引擎）
            analysis = _v6_build_analysis(news, sector_map=sector_map)

            # 2. 提取新闻提及个股，补充实时行情到红榜
            stock_codes_list, _ = self._extract_stock_codes_from_news(news)
            code_name_map = {}
            stock_list = news.get('stock_codes', news.get('stocks', []))
            if isinstance(stock_list, list):
                for st in stock_list:
                    if isinstance(st, dict):
                        c = str(st.get('code', '')).zfill(6)
                        n = st.get('name', '')
                        if c and n:
                            code_name_map[c] = n

            if stock_codes_list:
                quotes = self._batch_get_quotes(stock_codes_list)
                ben_extra = ['<br><b>新闻提及个股（实时行情）：</b>']
                sentiment = analysis.get('sentiment', '中性')
                for code in stock_codes_list[:6]:
                    q = quotes.get(code, {})
                    pct = float(q.get('pct_chg', 0) or 0)
                    name = q.get('name', '') or code_name_map.get(code, '') or code
                    if pct != 0:
                        color = '#FF3B30' if pct > 0 else '#34C759'
                        pct_str = f'<span style="color:{color}">{pct:+.2f}%</span>'
                    else:
                        pct_str = '--'
                    wl = ' <b style="color:#2563EB">[自选]</b>' if code in watchlist_codes else ''
                    logic = '直接受益' if sentiment == '利好' else ('承压关注' if sentiment == '利空' else '关联关注')
                    ben_extra.append(f'{name}({code}) {pct_str} {logic}{wl}<br>')
                analysis['opportunity'] = analysis.get('opportunity', '') + ''.join(ben_extra)

            # 3. 多空一致性校验：板块实际涨跌与情绪矛盾时修正
            matched_sectors = self._match_sector_from_keywords(full_text, sector_map)
            if matched_sectors:
                sector_cps = []
                for sname in matched_sectors:
                    sec = sector_map.get(sname, {})
                    cp = float(sec.get('change_pct', 0) or 0)
                    sector_cps.append((sname, cp))
                avg_cp = (sum(cp for _, cp in sector_cps) / len(sector_cps)) if sector_cps else 0.0
                sentiment = analysis.get('sentiment', '中性')
                if sentiment == '利好' and avg_cp < -0.5:
                    analysis['sentiment'] = '中性偏谨慎'
                    analysis['logic_gap'] += f'（消息面偏利好但相关板块实际平均下跌{avg_cp:.2f}%，资金未跟进）'
                elif sentiment == '利空' and avg_cp > 0.5:
                    analysis['sentiment'] = '中性偏观察'
                    analysis['logic_gap'] += f'（消息面偏空但板块逆势平均上涨{avg_cp:.2f}%，利空或已提前消化）'

            return analysis
        except Exception as e:
            print(f'[AI解读] V6简报生成异常: {e}', flush=True)
            import traceback
            traceback.print_exc()
            return {
                'core_pick': f'分析生成异常：{str(e)[:60]}',
                'logic_event': '--',
                'logic_gap': '--',
                'logic_chain': '--',
                'logic_catalyst': '--',
                'opportunity': '--',
                'risk': '--',
                'resonance': '--',
                'quant': {},
                'quant_json': '{}',
                'sentiment': '中性',
                'impact': '中',
            }

    def _get_watchlist_codes(self):
        codes = []
        try:
            from core.watchlist import get_watchlist_manager
            mgr = get_watchlist_manager()
            codes = mgr.get_codes()
        except Exception as e:
            print(f'[新闻中心] 获取自选股代码失败: {e}', flush=True)
        return codes

    def _refresh_watchlist_news(self):
        if self.watchlist_news_layout is None:
            return
        try:
            # 加载中状态
            safe_clear_layout(self.watchlist_news_layout)
            self.watchlist_news_layout.addStretch()
            loading = L('正在加载自选新闻...', C.TEXT3, 12, align=Qt.AlignmentFlag.AlignCenter)
            loading.setFixedHeight(80)
            self.watchlist_news_layout.insertWidget(0, loading)
            QApplication.processEvents()

            # 每次重新获取自选股列表（不缓存，确保增删后切换标签能刷新）
            codes = self._get_watchlist_codes()
            # 数据兜底加载：all_news为空或数量不足时从news_center多源管理器加载
            if not self.all_news or len(self.all_news) < 20:
                try:
                    from news_center import get_multi_source_manager
                    fb = get_multi_source_manager().fetch_all(limit=200)
                    if fb:
                        # 合并去重（按news_id）
                        existing_ids = set(n.get('news_id', '') for n in self.all_news if n.get('news_id'))
                        merged = list(self.all_news)
                        for n in fb:
                            nid = n.get('news_id', '')
                            if nid and nid not in existing_ids:
                                merged.append(n)
                                existing_ids.add(nid)
                            elif not nid:
                                merged.append(n)
                        self.all_news = merged
                        print(f'[新闻中心] 自选新闻兜底加载: 新增{len(fb)}条，总计{len(self.all_news)}条', flush=True)
                except Exception as e:
                    print(f'[新闻中心] 自选新闻兜底加载失败: {e}', flush=True)
            # 无自选股空状态
            if not codes:
                safe_clear_layout(self.watchlist_news_layout)
                self.watchlist_news_layout.addStretch()
                empty = L('暂无自选股相关新闻', C.TEXT3, 12, align=Qt.AlignmentFlag.AlignCenter)
                empty.setFixedHeight(80)
                self.watchlist_news_layout.insertWidget(0, empty)
                return
            # 【2026-09-24 清理 v28 死引用】原 v28.integration.get_watchlist_news 已下线，
            # 直接走下方的手动匹配分支（行为与之前一致）。
            wl_news = []
            # 手动兜底匹配：增强版，检查所有可能的股票代码字段和标题内容
            if not wl_news and self.all_news:
                try:
                    code_set = set(str(c) for c in codes)
                    # 获取自选股名称用于标题匹配
                    stock_names = set()
                    try:
                        from core.watchlist import get_watchlist_manager
                        mgr = get_watchlist_manager()
                        for item in mgr.get_all():
                            nm = item.get('name') or item.get('stock_name') or ''
                            if nm and len(nm) >= 2:
                                stock_names.add(nm)
                    except Exception:
                        pass
                    matched = []
                    for news in self.all_news:
                        # 收集新闻中所有可能的股票代码
                        news_codes = set()
                        for field in ['codes', 'related_stocks', 'stock_codes', 'stocks', 'related_codes']:
                            val = news.get(field)
                            if not val:
                                continue
                            if isinstance(val, str):
                                for c in val.replace(',', ' ').replace(';', ' ').split():
                                    if c.strip():
                                        news_codes.add(c.strip())
                            elif isinstance(val, list):
                                for c in val:
                                    if isinstance(c, dict):
                                        v = c.get('code', c.get('stock_code', ''))
                                        if v:
                                            news_codes.add(str(v))
                                    elif c:
                                        news_codes.add(str(c))
                        # 单字段code
                        for field in ['stock_code', 'code']:
                            v = news.get(field)
                            if v:
                                news_codes.add(str(v))
                        # 1. 代码字段交集匹配
                        if code_set & news_codes:
                            matched.append(news)
                            continue
                        # 2. 标题/内容包含股票代码
                        title = str(news.get('title', ''))
                        content = str(news.get('content', ''))[:1000]
                        code_match = False
                        for code in code_set:
                            if code and (code in title or code in content):
                                code_match = True
                                break
                        if code_match:
                            matched.append(news)
                            continue
                        # 3. 标题/内容包含股票名称（至少2个字）
                        if stock_names:
                            name_match = False
                            for nm in stock_names:
                                if nm and len(nm) >= 2 and (nm in title or nm in content[:500]):
                                    name_match = True
                                    break
                            if name_match:
                                matched.append(news)
                                continue
                    wl_news = matched
                    print(f'[新闻中心] 自选新闻手动匹配(增强版): {len(wl_news)}条', flush=True)
                except Exception as e2:
                    print(f'[新闻中心] 自选新闻手动匹配失败: {e2}', flush=True)
                    import traceback
                    traceback.print_exc()
            # 无相关新闻空状态
            if not wl_news:
                safe_clear_layout(self.watchlist_news_layout)
                self.watchlist_news_layout.addStretch()
                empty = L('暂无自选股相关新闻', C.TEXT3, 12, align=Qt.AlignmentFlag.AlignCenter)
                empty.setFixedHeight(80)
                self.watchlist_news_layout.insertWidget(0, empty)
                return
            # 按发布时间倒序
            def _wl_get_time(n):
                return str(n.get('publish_time') or n.get('time') or n.get('pub_time') or '')
            wl_news = sorted(wl_news, key=_wl_get_time, reverse=True)
            # 渲染新闻卡片（最多40条）
            safe_clear_layout(self.watchlist_news_layout)
            self.watchlist_news_layout.addStretch()
            for news in wl_news[:40]:
                card = self._create_news_card(news)
                self.watchlist_news_layout.insertWidget(self.watchlist_news_layout.count() - 1, card)
        except Exception as e:
            print(f'[新闻中心] 自选新闻刷新异常: {e}', flush=True)
            try:
                safe_clear_layout(self.watchlist_news_layout)
                self.watchlist_news_layout.addStretch()
                err = L('暂无自选股相关新闻', C.TEXT3, 12, align=Qt.AlignmentFlag.AlignCenter)
                err.setFixedHeight(80)
                self.watchlist_news_layout.insertWidget(0, err)
            except Exception:
                pass

    # ============================================================
    # V2.8 模块8：板块新闻子标签
    # ============================================================
    def _refresh_sector_combo(self):
        if self.sector_combo is None:
            return
        try:
            # all_news兜底加载（数量不足时也触发）
            if not self.all_news or len(self.all_news) < 20:
                try:
                    from news_center import get_multi_source_manager
                    fb = get_multi_source_manager().fetch_all(limit=200)
                    if fb:
                        existing_ids = set(n.get('news_id', '') for n in self.all_news if n.get('news_id'))
                        merged = list(self.all_news)
                        for n in fb:
                            nid = n.get('news_id', '')
                            if nid and nid not in existing_ids:
                                merged.append(n)
                                existing_ids.add(nid)
                            elif not nid:
                                merged.append(n)
                        self.all_news = merged
                        print(f'[新闻中心] 行业下拉兜底加载: 新增{len(fb)}条，总计{len(self.all_news)}条', flush=True)
                except Exception as e:
                    print(f'[新闻中心] 行业下拉兜底加载失败: {e}', flush=True)
            # 从 industry_full_map.json 提取全部申万一级行业名称（去重排序）
            industry_names = []
            try:
                import json as _json, os as _os
                _map_path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), 'data', 'cache', 'industry_full_map.json')
                if _os.path.exists(_map_path):
                    with open(_map_path, 'r', encoding='utf-8') as _f:
                        _ind_map = _json.load(_f)
                    _raw_names = set()
                    for _v in _ind_map.values():
                        if isinstance(_v, str):
                            if _v:
                                _raw_names.add(_v.strip())
                        elif isinstance(_v, dict):
                            _name = _v.get('industry') or _v.get('industry_name') or _v.get('name') or ''
                            if _name:
                                _raw_names.add(str(_name).strip())
                    industry_names = sorted(_raw_names)
                    print(f'[新闻中心] 行业下拉：从映射文件加载{len(industry_names)}个行业', flush=True)
                else:
                    print(f'[新闻中心] 行业映射文件不存在: {_map_path}', flush=True)
            except Exception as e_map:
                print(f'[新闻中心] 行业映射文件读取失败: {e_map}', flush=True)
            # 兜底：如果映射文件不可用，使用内置31个申万一级行业
            if not industry_names:
                industry_names = [
                    '农林牧渔', '采掘', '化工', '钢铁', '有色金属', '电子', '家用电器',
                    '食品饮料', '纺织服装', '轻工制造', '医药生物', '公用事业', '交通运输',
                    '房地产', '商业贸易', '休闲服务', '综合', '建筑材料', '建筑装饰',
                    '电气设备', '国防军工', '计算机', '传媒', '通信', '银行', '非银金融',
                    '汽车', '机械设备', '煤炭', '石油石化', '环保',
                ]
                print(f'[新闻中心] 行业下拉：使用内置{len(industry_names)}个申万一级行业', flush=True)
            # 行业列表最前面添加"全部行业"选项
            if industry_names and industry_names[0] != '全部行业':
                industry_names.insert(0, '全部行业')
            # 保留当前选中项（blockSignals后恢复）
            current = self.sector_combo.currentText()
            self.sector_combo.blockSignals(True)
            self.sector_combo.clear()
            self.sector_combo.addItems(industry_names)
            # 尝试恢复之前选中；若无则默认选中"全部行业"（第一项）
            if current:
                idx = self.sector_combo.findText(current)
                if idx >= 0:
                    self.sector_combo.setCurrentIndex(idx)
                else:
                    self.sector_combo.setCurrentIndex(0)
            else:
                self.sector_combo.setCurrentIndex(0)
            self.sector_combo.blockSignals(False)
        except Exception as e:
            print(f'[新闻中心] 行业下拉框更新异常: {e}', flush=True)

    def _refresh_sector_news(self):
        if self.sector_news_layout is None:
            return
        try:
            safe_clear_layout(self.sector_news_layout)
            self.sector_news_layout.addStretch()
            if self.sector_combo is None:
                return
            sector = self.sector_combo.currentText()
            # all_news兜底加载（数量不足时也触发）
            if not self.all_news or len(self.all_news) < 20:
                try:
                    from news_center import get_multi_source_manager
                    fb = get_multi_source_manager().fetch_all(limit=200)
                    if fb:
                        existing_ids = set(n.get('news_id', '') for n in self.all_news if n.get('news_id'))
                        merged = list(self.all_news)
                        for n in fb:
                            nid = n.get('news_id', '')
                            if nid and nid not in existing_ids:
                                merged.append(n)
                                existing_ids.add(nid)
                            elif not nid:
                                merged.append(n)
                        self.all_news = merged
                        print(f'[新闻中心] 板块新闻兜底加载: 新增{len(fb)}条，总计{len(self.all_news)}条', flush=True)
                except Exception as e:
                    print(f'[新闻中心] 板块新闻兜底加载失败: {e}', flush=True)
            if not sector:
                self._render_sector_empty_state('暂无该行业相关新闻')
                return

            # ===== "全部行业"：加载全市场最新新闻 =====
            if sector == '全部行业':
                all_sorted = sorted(
                    self.all_news,
                    key=lambda n: str(n.get('publish_time') or n.get('time') or ''),
                    reverse=True
                )
                sec_news = all_sorted[:40]
                print(f'[新闻中心] 全部行业新闻: {len(sec_news)}条', flush=True)
            else:
                # 【2026-09-24 清理 v28 死引用】原 v28.integration.get_sector_news 已下线，
                # 直接走下方的手动匹配分支（行为与之前一致）。
                sec_news = []
                # 手动兜底匹配：新闻的industry字段或tags或content中包含行业名
                if not sec_news and self.all_news:
                    try:
                        matched = []
                        sector_lower = sector.lower()
                        for news in self.all_news:
                            # 检查industry字段
                            ind_val = news.get('industry') or news.get('sector') or news.get('industry_name') or ''
                            if isinstance(ind_val, list):
                                ind_val = ','.join(str(x) for x in ind_val)
                            ind_val = str(ind_val).lower()
                            if sector_lower in ind_val or ind_val in sector_lower:
                                matched.append(news)
                                continue
                            # 检查tags字段
                            tags = news.get('tags') or news.get('categories') or []
                            if isinstance(tags, str):
                                tags = [t.strip() for t in tags.split(',') if t.strip()]
                            tag_match = False
                            for t in tags:
                                tl = str(t).lower()
                                if sector_lower in tl or tl in sector_lower:
                                    tag_match = True
                                    break
                            if tag_match:
                                matched.append(news)
                                continue
                            # 检查content/title中包含行业名
                            title = str(news.get('title', '')).lower()
                            content = str(news.get('content', ''))[:500].lower()
                            if sector_lower in title or sector_lower in content:
                                matched.append(news)
                        sec_news = matched
                        print(f'[新闻中心] 板块新闻手动匹配[{sector}]: {len(sec_news)}条', flush=True)
                    except Exception as e2:
                        print(f'[新闻中心] 板块新闻手动匹配失败: {e2}', flush=True)

            # 空状态
            if not sec_news:
                self._render_sector_empty_state(f'暂无{sector}相关新闻，试试其他行业')
                return

            # 按发布时间倒序
            def _sec_get_time(n):
                return str(n.get('publish_time') or n.get('time') or n.get('pub_time') or '')
            sec_news = sorted(sec_news, key=_sec_get_time, reverse=True)

            # 渲染新闻卡片（最多40条）
            safe_clear_layout(self.sector_news_layout)
            self.sector_news_layout.addStretch()
            for news in sec_news[:40]:
                card = self._create_news_card(news)
                self.sector_news_layout.insertWidget(self.sector_news_layout.count() - 1, card)
        except Exception as e:
            print(f'[新闻中心] 板块新闻刷新异常: {e}', flush=True)
            try:
                safe_clear_layout(self.sector_news_layout)
                self.sector_news_layout.addStretch()
                err = L('暂无该行业相关新闻', C.TEXT3, 12, align=Qt.AlignmentFlag.AlignCenter)
                err.setFixedHeight(80)
                self.sector_news_layout.insertWidget(0, err)
            except Exception:
                pass

    def _render_sector_empty_state(self, message):
        """渲染板块新闻空状态：提示 + 查看全部行业新闻按钮"""
        try:
            safe_clear_layout(self.sector_news_layout)
            self.sector_news_layout.addStretch()
            container = QFrame()
            container.setStyleSheet(f'QFrame{{background:{C.CARD};border:1px solid {C.BORDER};border-radius:8px;}}')
            layout = QVBoxLayout(container)
            layout.setContentsMargins(24, 32, 24, 32)
            layout.setSpacing(16)

            tip = QLabel(message)
            tip.setStyleSheet(f'color:{C.TEXT2};font-size:13px;background:transparent;')
            tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tip.setWordWrap(True)
            layout.addWidget(tip)

            btn_row = QHBoxLayout()
            btn_row.addStretch()
            all_btn = QPushButton('🏭 查看全部行业新闻')
            all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            all_btn.setStyleSheet(f'QPushButton{{background:{C.BLUE};color:white;border:none;border-radius:4px;padding:6px 20px;font-size:12px;font-weight:bold;}}QPushButton:hover{{background:#1D4ED8;}}')
            all_btn.clicked.connect(self._show_all_sector_news)
            btn_row.addWidget(all_btn)
            btn_row.addStretch()
            layout.addLayout(btn_row)

            self.sector_news_layout.insertWidget(0, container)
        except Exception as e:
            print(f"[新闻中心] 板块空状态渲染失败: {e}", flush=True)

    def _show_all_sector_news(self):
        """切换到全部行业新闻"""
        try:
            if self.sector_combo is not None:
                idx = self.sector_combo.findText('全部行业')
                if idx >= 0:
                    self.sector_combo.setCurrentIndex(idx)
                else:
                    self.sector_combo.setCurrentIndex(0)
        except Exception as e:
            print(f"[新闻中心] 切换全部行业失败: {e}", flush=True)
    def _on_sector_changed(self):
        self._refresh_sector_news()

    def _auto_select_top_sector(self):
        """自动选择当前涨幅第一的行业（板块新闻标签切换时调用）
        优先从板块雷达引擎获取，降级到unified_data_service，在下拉框中模糊匹配并选中"""
        if self.sector_combo is None:
            return
        try:
            top_sector = None
            # 【2026-09-24 清理 v28 死引用】原「优先级1：v28.core.sector_radar 板块雷达」已下线，
            # 此前每次都抛 ModuleNotFoundError 并被吞掉，实际一直走的就是优先级2。
            # 现直接从优先级2开始，行为不变。
            # 优先级2：降级到 unified_data_service
            if not top_sector:
                try:
                    from service.unified_data_service import get_sector_data_service
                    svc = get_sector_data_service()
                    # 直接复用选股雷达的题材：从涨停数据库取最近涨停题材
                    from data.limit_up_reason_db import get_db
                    conn = get_db()
                    c = conn.cursor()
                    c.execute("SELECT reason FROM limit_up_reasons WHERE reason LIKE '%+%' ORDER BY date DESC LIMIT 1000")
                    theme_set = []
                    seen = set()
                    for row in c.fetchall():
                        tags = [t.strip() for t in row[0].split('+')]
                        for t in tags:
                            if t and t not in seen and not t.endswith('板') and len(t) > 2:
                                seen.add(t)
                                theme_set.append(t)
                        if len(theme_set) >= 20:
                            break
                    conn.close()
                    hot_sectors = [{'name': t, 'pct': 0} for t in theme_set]
                    if hot_sectors:
                        def _get_pct2(s):
                            return s.get('change_pct', s.get('pct_chg', s.get('change', s.get('pct', 0))))
                        sorted_sectors = sorted(hot_sectors, key=_get_pct2, reverse=True)
                        top = sorted_sectors[0]
                        top_sector = top.get('name', top.get('sector_name', top.get('industry', '')))
                        print(f'[新闻中心] 数据服务涨幅第一: {top_sector}', flush=True)
                except Exception as e_svc:
                    print(f'[新闻中心] 数据服务获取涨幅行业失败: {e_svc}', flush=True)
            # 在下拉框中模糊匹配行业名（包含关系）
            idx = -1
            if top_sector:
                top_sector_str = str(top_sector).strip()
                for i in range(self.sector_combo.count()):
                    item_text = self.sector_combo.itemText(i)
                    if not item_text:
                        continue
                    item_str = str(item_text).strip()
                    if top_sector_str in item_str or item_str in top_sector_str:
                        idx = i
                        break
            # 如果匹配不到，默认选中下拉框第一项
            if idx < 0:
                if self.sector_combo.count() > 0:
                    idx = 0
                    print(f'[新闻中心] 涨幅行业未匹配，默认选中第一项: {self.sector_combo.itemText(0)}', flush=True)
            if idx >= 0 and idx != self.sector_combo.currentIndex():
                self.sector_combo.setCurrentIndex(idx)
                print(f'[新闻中心] 自动选择行业: {self.sector_combo.currentText()}', flush=True)
        except Exception as e:
            print(f'[新闻中心] 自动选择行业异常: {e}', flush=True)


    def _refresh_v28_tabs(self):
        """异步刷新新闻子标签（defer到事件循环，避免阻塞主线程）

        【2026-09-24 清理 v28 死引用】原开关 v28.config.is_enabled('news_sentiment')
        已下线。该 import 此前每次都失败，except 分支直接 return，
        即本方法实际上从未执行过刷新。现保持原有行为（不刷新）不变。
        如需恢复刷新，删掉下面这行 return 即可。
        """
        return
        try:
            if self.watchlist_news_layout is not None:
                QTimer.singleShot(10, self._refresh_watchlist_news)
        except Exception:
            pass
        try:
            if self.sector_combo is not None:
                QTimer.singleShot(10, self._do_sector_tab_load)
        except Exception:
            pass
    def _show_invest_calendar(self):

        """弹出投资日历窗口"""

        try:

            from PyQt6.QtWidgets import QDialog, QVBoxLayout

            dlg = QDialog(self)

            dlg.setWindowTitle('📅 投资日历')

            dlg.resize(900, 700)

            layout = QVBoxLayout(dlg)

            cal = InvestmentCalendarView()

            layout.addWidget(cal)

            dlg.exec()

        except Exception as e:

            print(f'[投资日历] 打开失败: {e}', flush=True)







# ============================================================
# V3.0 投资日历视图（嵌入新闻中心子Tab）
# ============================================================
class InvestmentCalendarView(QWidget):
    """投资日历：新股/解禁/财报/宏观/事件，支持日期切换与类型筛选"""
    stock_clicked = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_date = datetime.now().strftime('%Y-%m-%d')
        self.current_type_filter = '全部'
        self.view_mode = 'month'  # today/week/month
        self._build_ui()
        self._load_calendar()

    def _build_ui(self):
        main = QVBoxLayout(self); main.setContentsMargins(4, 4, 4, 4); main.setSpacing(8)
        # 第一行：日期范围按钮
        range_bar = QHBoxLayout()
        self.today_btn = QPushButton('📅 今日'); self.today_btn.setFixedHeight(28)
        self.today_btn.setStyleSheet(f'QPushButton{{background:{C.TAB};color:{C.TEXT};border:1px solid {C.BORDER};border-radius:4px;padding:0 12px;font-size:11px;}}QPushButton:hover{{background:{C.CARD_HOVER};}}')
        self.today_btn.clicked.connect(self._go_today); range_bar.addWidget(self.today_btn)
        self.week_btn = QPushButton('📆 未来7天'); self.week_btn.setFixedHeight(28)
        self.week_btn.setStyleSheet(f'QPushButton{{background:{C.TAB};color:{C.TEXT};border:1px solid {C.BORDER};border-radius:4px;padding:0 12px;font-size:11px;}}QPushButton:hover{{background:{C.CARD_HOVER};}}')
        self.week_btn.clicked.connect(self._show_week); range_bar.addWidget(self.week_btn)
        self.month_btn = QPushButton('🗓 未来30天'); self.month_btn.setFixedHeight(28)
        self.month_btn.setStyleSheet(f'QPushButton{{background:{C.BLUE};color:white;border:none;border-radius:4px;padding:0 12px;font-size:11px;font-weight:bold;}}QPushButton:hover{{background:#1D4ED8;}}')
        self.month_btn.clicked.connect(self._show_month); range_bar.addWidget(self.month_btn)
        range_bar.addSpacing(16)
        self.date_label = L('', C.TEXT, 12, True); range_bar.addWidget(self.date_label)
        range_bar.addStretch()
        self.range_label = L('', C.TEXT2, 10); range_bar.addWidget(self.range_label)
        main.addLayout(range_bar)
        # 第二行：日期导航 + 类型筛选 + 刷新
        toolbar = QHBoxLayout()
        self.prev_btn = QPushButton('◀ 前一天'); self.prev_btn.setFixedHeight(26)
        self.prev_btn.setStyleSheet(f'QPushButton{{background:{C.TAB};color:{C.TEXT};border:1px solid {C.BORDER};border-radius:4px;padding:0 8px;font-size:10px;}}QPushButton:hover{{background:{C.CARD_HOVER};}}')
        self.prev_btn.clicked.connect(self._prev_day); toolbar.addWidget(self.prev_btn)
        self.next_btn = QPushButton('后一天 ▶'); self.next_btn.setFixedHeight(26)
        self.next_btn.setStyleSheet(f'QPushButton{{background:{C.TAB};color:{C.TEXT};border:1px solid {C.BORDER};border-radius:4px;padding:0 8px;font-size:10px;}}QPushButton:hover{{background:{C.CARD_HOVER};}}')
        self.next_btn.clicked.connect(self._next_day); toolbar.addWidget(self.next_btn)
        toolbar.addSpacing(16)
        toolbar.addWidget(L('类型:', C.TEXT2, 10)); toolbar.addSpacing(4)
        self.type_combo = QComboBox(); self.type_combo.addItems(['全部', '宏观', '行业活动', '公司活动', '政策发布', '新股', '解禁', '财报', '事件'])
        self.type_combo.setFixedHeight(26); self.type_combo.setStyleSheet(f'QComboBox{{background:{C.TAB};color:{C.TEXT};border:1px solid {C.BORDER};border-radius:4px;padding:0 6px;font-size:10px;}}')
        self.type_combo.currentIndexChanged.connect(self._on_type_filter); toolbar.addWidget(self.type_combo)
        toolbar.addStretch()
        self.refresh_cal_btn = QPushButton('🔄 刷新'); self.refresh_cal_btn.setFixedHeight(26)
        self.refresh_cal_btn.setStyleSheet(f'QPushButton{{background:{C.TAB};color:{C.TEXT};border:1px solid {C.BORDER};border-radius:4px;padding:0 10px;font-size:10px;}}QPushButton:hover{{background:{C.CARD_HOVER};}}')
        self.refresh_cal_btn.clicked.connect(self._refresh_calendar); toolbar.addWidget(self.refresh_cal_btn)
        main.addLayout(toolbar)
        self.cal_scroll = QScrollArea(); self.cal_scroll.setWidgetResizable(True)
        self.cal_scroll.setStyleSheet(f'QScrollArea{{background:transparent;border:none;}}QScrollBar:vertical{{background:{C.TAB};width:6px;}}QScrollBar::handle:vertical{{background:{C.BORDER_L};border-radius:3px;}}')
        self.cal_container = QWidget(); self.cal_layout = QVBoxLayout(self.cal_container)
        self.cal_layout.setContentsMargins(0, 0, 0, 0); self.cal_layout.setSpacing(6); self.cal_layout.addStretch()
        self.cal_scroll.setWidget(self.cal_container); main.addWidget(self.cal_scroll, 1)

    def _load_calendar(self):
        try:
            while self.cal_layout.count() > 1:
                item = self.cal_layout.takeAt(0); w = item.widget()
                if w: w.deleteLater()
            # 先显示加载中
            loading = L('📅 正在加载投资日历数据...', C.TEXT2, 12, align=Qt.AlignmentFlag.AlignCenter)
            loading.setFixedHeight(80)
            self.cal_layout.insertWidget(0, loading)

            # 后台线程加载，避免UI卡顿
            def run_load():
                try:
                    provider = get_calendar_provider()
                    if self.view_mode == 'today':
                        events = provider.get_events(self.current_date)
                        d_text = self.current_date
                        r_text = ''
                    else:
                        days = 7 if self.view_mode == 'week' else 30
                        start_date = datetime.now().strftime('%Y-%m-%d')
                        end_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
                        range_events = provider.get_date_range_events(start_date, end_date)
                        events = []
                        for date_str in sorted(range_events.keys()):
                            for ev in range_events[date_str]:
                                events.append(ev)
                        d_text = f'未来{days}天'
                        r_text = f'{start_date} 至 {end_date} | 共{len(events)}条事件'
                    if self.current_type_filter != '全部':
                        events = [e for e in events if e.get('type') == self.current_type_filter]
                    # 主线程更新
                    from PyQt6.QtCore import QMetaObject, Qt
                    from PyQt6.QtWidgets import QApplication
                    QApplication.processEvents()
                    self.date_label.setText(d_text)
                    self.range_label.setText(r_text)
                    while self.cal_layout.count() > 1:
                        item = self.cal_layout.takeAt(0); w = item.widget()
                        if w: w.deleteLater()
                    if not events:
                        empty = L(f'暂无财经事件', C.TEXT3, 12, align=Qt.AlignmentFlag.AlignCenter)
                        empty.setFixedHeight(80)
                        self.cal_layout.insertWidget(0, empty)
                        return
                    # 渲染事件列表
                    for ev in events[:100]:
                        row = QHBoxLayout()
                        time_lbl = L(ev.get('time', ''), C.TEXT2, 10)
                        time_lbl.setFixedWidth(70)
                        row.addWidget(time_lbl)
                        type_lbl = L(ev.get('type', ''), C.BLUE, 10)
                        type_lbl.setFixedWidth(60)
                        row.addWidget(type_lbl)
                        title_lbl = L(ev.get('title', ''), C.TEXT, 11)
                        row.addWidget(title_lbl, 1)
                        wrap = QWidget()
                        wrap.setLayout(row)
                        self.cal_layout.addWidget(wrap)
                except Exception as e:
                    print(f'[投资日历] 加载失败: {e}', flush=True)
            import threading
            threading.Thread(target=run_load, daemon=True).start()
            return
            # 按日期分组显示
            current_date_group = ''
            for ev in events:
                ev_date = ev.get('date', '')
                if ev_date != current_date_group:
                    current_date_group = ev_date
                    # 日期分组标题
                    try:
                        d = datetime.strptime(ev_date, '%Y-%m-%d')
                        weekday_names = ['周一','周二','周三','周四','周五','周六','周日']
                        date_title = f'{ev_date} {weekday_names[d.weekday()]}'
                    except:
                        date_title = ev_date
                    title_label = L(f'📆 {date_title}', C.BLUE, 11, True)
                    title_label.setStyleSheet(f'padding:4px 8px;background:rgba(37,99,235,0.08);border-left:3px solid {C.BLUE};border-radius:2px;')
                    self.cal_layout.insertWidget(self.cal_layout.count() - 1, title_label)
                card = self._create_event_card(ev)
                self.cal_layout.insertWidget(self.cal_layout.count() - 1, card)
        except Exception as e:
            print(f"[投资日历] 加载失败: {e}", flush=True)
            import traceback
            traceback.print_exc()
            err = L(f'日历加载失败: {e}', C.RED, 12, align=Qt.AlignmentFlag.AlignCenter)
            self.cal_layout.insertWidget(0, err)

    def _create_event_card(self, event: Dict) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f'QFrame{{background:{C.CARD};border:1px solid {C.BORDER};border-radius:8px;}}QFrame:hover{{border:1px solid {C.BORDER_L};}}')
        layout = QHBoxLayout(card); layout.setContentsMargins(12, 10, 12, 10); layout.setSpacing(10)
        left = QVBoxLayout(); left.setSpacing(2)
        etype = event.get('type', '事件')
        ecolor = CALENDAR_TYPE_COLORS.get(etype, C.TEXT2)
        eicon = CALENDAR_TYPE_ICONS.get(etype, '📅')
        left.addWidget(L(f'{eicon} {etype}', ecolor, 10, True))
        etime = event.get('time', '')
        if etime:
            left.addWidget(L(etime, C.TEXT3, 9))
        left.addStretch()
        layout.addLayout(left)
        mid = QVBoxLayout(); mid.setSpacing(4)
        mid.addWidget(L(event.get('title', ''), C.TEXT, 12, True))
        detail = event.get('detail', '')
        if detail:
            mid.addWidget(L(detail[:100], C.TEXT2, 10))
        layout.addLayout(mid, 1)
        stock_code = event.get('stock_code', '')
        stock_name = event.get('stock_name', '')
        if stock_code:
            jump_btn = QPushButton(f'📊 {stock_name or stock_code}'); jump_btn.setFixedHeight(26)
            jump_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            jump_btn.setStyleSheet(f'QPushButton{{background:rgba(37,99,235,0.1);color:{C.BLUE};border:1px solid {C.BLUE};border-radius:4px;padding:0 10px;font-size:10px;font-weight:bold;}}QPushButton:hover{{background:rgba(37,99,235,0.2);}}')
            jump_btn.clicked.connect(lambda: self.stock_clicked.emit(stock_code, stock_name or stock_code))
            layout.addWidget(jump_btn)
        return card

    def _prev_day(self):
        try:
            self.view_mode = 'today'
            self._update_button_styles()
            d = datetime.strptime(self.current_date, '%Y-%m-%d') - timedelta(days=1)
            self.current_date = d.strftime('%Y-%m-%d')
            self._load_calendar()
        except Exception: pass

    def _next_day(self):
        try:
            self.view_mode = 'today'
            self._update_button_styles()
            d = datetime.strptime(self.current_date, '%Y-%m-%d') + timedelta(days=1)
            self.current_date = d.strftime('%Y-%m-%d')
            self._load_calendar()
        except Exception: pass

    def _go_today(self):
        self.view_mode = 'today'
        self.current_date = datetime.now().strftime('%Y-%m-%d')
        self._update_button_styles()
        self._load_calendar()

    def _show_week(self):
        self.view_mode = 'week'
        self._update_button_styles()
        self._load_calendar()

    def _show_month(self):
        self.view_mode = 'month'
        self._update_button_styles()
        self._load_calendar()

    def _update_button_styles(self):
        """更新按钮选中样式"""
        normal_style = f'QPushButton{{background:{C.TAB};color:{C.TEXT};border:1px solid {C.BORDER};border-radius:4px;padding:0 12px;font-size:11px;}}QPushButton:hover{{background:{C.CARD_HOVER};}}'
        active_style = f'QPushButton{{background:{C.BLUE};color:white;border:none;border-radius:4px;padding:0 12px;font-size:11px;font-weight:bold;}}QPushButton:hover{{background:#1D4ED8;}}'
        self.today_btn.setStyleSheet(active_style if self.view_mode == 'today' else normal_style)
        self.week_btn.setStyleSheet(active_style if self.view_mode == 'week' else normal_style)
        self.month_btn.setStyleSheet(active_style if self.view_mode == 'month' else normal_style)

    def _on_type_filter(self):
        self.current_type_filter = self.type_combo.currentText()
        self._load_calendar()

    def _refresh_calendar(self):
        try:
            get_calendar_provider().refresh_all()
            self._load_calendar()
        except Exception as e:
            print(f"[投资日历] 刷新失败: {e}", flush=True)


# ============================================================
# 资金流向页面 - 板块资金TOP15横向柱状图
# ============================================================
# V2.3已删除：FundFlowPage/HotConceptPage/SectorHotPage（功能整合到板块异动雷达）

# ============================================================
# 个股分析页面 - 专业K线+信号标记+买点解释
# ============================================================

def _is_layout_valid(layout):
    """检查布局对象是否有效（未被删除）"""
    if layout is None:
        return False
    try:
        # 已删除的布局调用count会抛RuntimeError
        layout.count()
        return True
    except RuntimeError:
        return False
    except Exception:
        return False


def safe_clear_layout(layout):
    """安全清空布局（杜绝悬垂指针崩溃）
    
    修复：while循环+takeAt+deleteLater在布局已删除时抛RuntimeError
    策略：先校验布局有效性 → 一次性取出所有项 → 批量脱离 → 统一调度删除
    """
    if not _is_layout_valid(layout):
        return
    try:
        count = layout.count()
    except RuntimeError:
        return
    except Exception:
        return
    
    if count == 0:
        return
    
    # 第一步：一次性取出所有布局项（避免循环中操作正在变化的布局）
    items = []
    try:
        for i in range(count):
            item = layout.itemAt(i)
            if item is not None:
                items.append(item)
    except RuntimeError:
        return
    except Exception:
        pass
    
    # 第二步：批量脱离布局（从布局中移除，但不立即删除）
    try:
        while layout.count() > 0:
            layout.takeAt(0)
    except RuntimeError:
        pass
    except Exception:
        pass
    
    # 第三步：统一调度删除控件
    for item in items:
        try:
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        except RuntimeError:
            pass
        except Exception:
            pass




# ============================================================
# MACD / KDJ 技术指标Widget（基于本地K线数据计算）
# ============================================================

# ============================================================
# MACD / KDJ 技术指标Widget（基于本地K线数据计算）
# 支持：光标同步、独立缩放、MACD红绿柱
# ============================================================
class _IndicatorPlot(QWidget):
    """指标绘图区：QPainter绘制，支持光标同步+独立滚轮缩放"""
    cursor_changed = pyqtSignal(int)  # 发射当前光标对应的数据索引

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(120)
        self.setStyleSheet('background:#FAFBFC;')
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dragging = False
        self._drag_start_x = 0
        self._drag_start_start = 0
        self._lines = []           # [(values_list, color, width)]
        self._bars = []            # [(values_list,)] MACD柱状图数据
        self._zero_line = True
        self._cursor_x = -1        # 光标x像素位置，-1=隐藏
        self._total_count = 0      # 总数据根数
        self._display_count = 120 # 当前显示根数
        self._display_start = 0    # 显示起始索引
        self._pad_l = 30
        self._pad_r = 10
        self._pad_t = 8
        self._pad_b = 20

    def set_data(self, lines, bars=None, zero_line=True):
        self._lines = lines
        self._bars = bars or []
        self._zero_line = zero_line
        self._total_count = max((len(v[0]) for v in lines), default=0)
        # 默认显示最后120根
        if self._total_count > 0:
            self._display_count = min(self._total_count, 120)
            self._display_start = self._total_count - self._display_count
        self.update()

    def set_cursor_index(self, idx):
        """外部设置光标位置（由其他widget同步）"""
        if self._total_count == 0:
            return
        # 转换为widget内坐标
        plot_w = self.width() - self._pad_l - self._pad_r
        if plot_w <= 0:
            return
        # idx是全局索引，转换为显示范围内的索引
        local_idx = idx - self._display_start
        if 0 <= local_idx < self._display_count:
            self._cursor_x = int(self._pad_l + plot_w * (local_idx / max(self._display_count - 1, 1)))
        else:
            self._cursor_x = -1
        self.update()

    def set_zoom_range(self, start_pct, end_pct):
        """外部设置显示范围（跟随主K线图缩放/平移）"""
        if self._total_count == 0:
            return
        total = self._total_count
        start = int(total * start_pct / 100)
        end = int(total * end_pct / 100)
        self._display_start = max(0, min(start, total - 20))
        self._display_count = max(20, min(end - start, total - self._display_start))
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start_x = event.position().x()
            self._drag_start_start = self._display_start
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseMoveEvent(self, event):
        if self._total_count == 0 or self._display_count <= 1:
            return
        plot_w = self.width() - self._pad_l - self._pad_r
        x = event.position().x()

        # 拖动平移模式
        if self._dragging:
            bar_width = plot_w / max(self._display_count, 1)
            dx_pixels = x - self._drag_start_x
            dx_bars = int(round(-dx_pixels / max(bar_width, 1)))
            new_start = self._drag_start_start + dx_bars
            new_start = max(0, min(new_start, self._total_count - self._display_count))
            self._display_start = new_start
            self.update()
            return

        # 光标同步模式
        local_idx = int((x - self._pad_l) / plot_w * (self._display_count - 1))
        local_idx = max(0, min(local_idx, self._display_count - 1))
        self._cursor_x = int(x)
        global_idx = self._display_start + local_idx
        self.cursor_changed.emit(global_idx)
        self.update()

    def leaveEvent(self, event):
        self._cursor_x = -1
        self.update()

    def wheelEvent(self, event):
        """独立缩放：滚轮调整显示根数"""
        delta = event.angleDelta().y()
        old_count = self._display_count
        if delta > 0:
            # 放大：减少显示根数
            self._display_count = max(20, self._display_count - 10)
        else:
            # 缩小：增加显示根数
            self._display_count = min(self._total_count, self._display_count + 10)
        # 调整start保持最后一根可见
        self._display_start = self._total_count - self._display_count
        self._display_start = max(0, self._display_start)
        self.update()

    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter, QPen, QColor, QFont, QBrush
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        plot_w = w - self._pad_l - self._pad_r
        plot_h = h - self._pad_t - self._pad_b
        if plot_w < 10 or plot_h < 10:
            return

        # 当前显示范围
        start = self._display_start
        count = self._display_count
        end = min(start + count, self._total_count)

        # 找数值范围
        all_vals = []
        for vals, color, width in self._lines:
            for i in range(start, end):
                if i < len(vals) and vals[i] is not None:
                    all_vals.append(vals[i])
        for bar_vals in self._bars:
            for i in range(start, end):
                if i < len(bar_vals) and bar_vals[i] is not None:
                    all_vals.append(bar_vals[i])
        if not all_vals:
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '暂无数据')
            p.end()
            return
        vmin, vmax = min(all_vals), max(all_vals)
        if vmin == vmax:
            vmin -= 1; vmax += 1
        vrange = vmax - vmin
        vmin -= vrange * 0.1
        vmax += vrange * 0.1

        def _to_y(v):
            return self._pad_t + plot_h * (1 - (v - vmin) / (vmax - vmin))
        def _to_x(local_i):
            return self._pad_l + plot_w * (local_i / max(count - 1, 1))

        # 0轴
        if self._zero_line and vmin < 0 < vmax:
            p.setPen(QPen(QColor('#94A3B8'), 1, Qt.PenStyle.DashLine))
            y0 = int(_to_y(0))
            p.drawLine(self._pad_l, y0, self._pad_l + plot_w, y0)

        # MACD柱状图（先画柱子，再画线）
        for bar_vals in self._bars:
            bar_w = max(2, int(plot_w / count * 0.6))
            for local_i, i in enumerate(range(start, end)):
                if i >= len(bar_vals) or bar_vals[i] is None:
                    continue
                val = bar_vals[i]
                x_center = _to_x(local_i)
                y_top = int(_to_y(val if val > 0 else 0))
                y_bot = int(_to_y(val if val < 0 else 0))
                bar_h = abs(y_bot - y_top)
                if bar_h < 1:
                    continue
                color = QColor('#E53935') if val >= 0 else QColor('#000000')
                p.fillRect(int(x_center - bar_w/2), min(y_top, y_bot), bar_w, bar_h, QBrush(color))

        # 画每条线
        for vals, color, width in self._lines:
            p.setPen(QPen(QColor(color), width))
            for local_i in range(end - start - 1):
                i1 = start + local_i
                i2 = start + local_i + 1
                if i1 >= len(vals) or i2 >= len(vals) or vals[i1] is None or vals[i2] is None:
                    continue
                p.drawLine(int(_to_x(local_i)), int(_to_y(vals[i1])),
                          int(_to_x(local_i+1)), int(_to_y(vals[i2])))

        # Y轴刻度
        p.setPen(QPen(QColor('#94A3B8'), 1))
        p.setFont(QFont('Arial', 8))
        for v in [vmin, (vmin+vmax)/2, vmax]:
            y = int(_to_y(v))
            p.drawText(2, y + 4, f'{v:.2f}')

        # 垂直光标线
        if self._cursor_x >= 0:
            p.setPen(QPen(QColor('#CCCCCC'), 1, Qt.PenStyle.DashLine))
            p.drawLine(self._cursor_x, self._pad_t, self._cursor_x, self._pad_t + plot_h)

        p.end()


class _TechIndicatorBase(QWidget):
    """技术指标基类：标题栏+图形区+数值栏（参数可持久化）"""
    params = {}

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self._title = title
        self._data = None
        self._param_inputs = []
        # 复制类变量 params 为实例变量，避免修改类变量影响其他实例
        self.params = dict(self.__class__.params)
        # 配置持久化键（子类通过类变量 _config_key 指定）
        self._config_key = getattr(self.__class__, '_config_key', None)
        # 从配置文件加载已保存参数覆盖默认值（大小写不敏感匹配键名）
        if self._config_key:
            saved = _load_indicator_config().get(self._config_key, {}) or {}
            for k in list(self.params.keys()):
                sk = k.lower()
                if sk in saved:
                    try:
                        self.params[k] = int(saved[sk])
                    except (TypeError, ValueError):
                        print(f"[指标参数] 配置项 {self._config_key}.{k} 无效，忽略", flush=True)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)
        top = QHBoxLayout()
        title = QLabel(self._title)
        title.setStyleSheet('color:#1E293B;font-size:12px;font-weight:bold;background:transparent;')
        top.addWidget(title)
        top.addStretch()
        for key, default in self.params.items():
            lbl = QLabel(f'{key}:')
            lbl.setStyleSheet('color:#64748B;font-size:10px;background:transparent;')
            top.addWidget(lbl)
            inp = QLineEdit(str(default))
            inp.setFixedSize(36, 22)
            inp.setAlignment(Qt.AlignmentFlag.AlignCenter)
            inp.setStyleSheet('QLineEdit{background:#F1F5F9;border:1px solid #CBD5E1;border-radius:3px;font-size:10px;}')
            self._param_inputs.append(inp)
            top.addWidget(inp)
        apply_btn = QPushButton('应用')
        apply_btn.setFixedSize(40, 22)
        apply_btn.setStyleSheet('QPushButton{background:#2F6BFF;color:white;border:none;border-radius:3px;font-size:10px;}'
                                 'QPushButton:hover{background:#1E56E0;}')
        apply_btn.clicked.connect(self._on_params_changed)
        top.addWidget(apply_btn)
        layout.addLayout(top)
        self._value_label = QLabel('加载中...')
        self._value_label.setStyleSheet('color:#334155;font-size:11px;background:transparent;')
        layout.addWidget(self._value_label)
        self._plot_widget = _IndicatorPlot(self)
        layout.addWidget(self._plot_widget, 1)

    def _on_params_changed(self):
        try:
            new_params = {}
            keys = list(self.params.keys())
            for i, key in enumerate(keys):
                if i < len(self._param_inputs):
                    raw = self._param_inputs[i].text().strip()
                    val = int(raw)
                    if val <= 0:
                        raise ValueError(f"参数 {key} 必须为正整数，当前为 {raw!r}")
                    new_params[key] = val
            # 验证全部通过后再更新
            self.params = new_params
            # 持久化保存（键名统一小写）
            if self._config_key:
                cfg = _load_indicator_config()
                cfg[self._config_key] = {k.lower(): v for k, v in new_params.items()}
                _save_indicator_config(cfg)
            if self._data:
                self._calc_and_draw()
        except Exception as e:
            print(f"[指标] 参数修改失败: {e}", flush=True)

    def set_kline_data(self, kline_dict):
        self._data = kline_dict
        self._calc_and_draw()

    def _calc_and_draw(self):
        pass


class MACDIndicatorWidget(_TechIndicatorBase):
    """MACD指标：DIF/DEA线 + 红绿柱状图"""
    _config_key = 'macd'
    params = {'fast': 12, 'slow': 26, 'signal': 9}

    def __init__(self, parent=None):
        super().__init__('MACD', parent)

    def _calc_and_draw(self):
        if not self._data or 'close' not in self._data:
            return
        closes = self._data['close']
        n = len(closes)
        if n < self.params['slow']:
            self._value_label.setText('数据不足')
            return
        fast = self.params['fast']
        slow = self.params['slow']
        signal = self.params['signal']

        def _ema(data, period):
            result = [data[0]]
            k = 2 / (period + 1)
            for i in range(1, len(data)):
                result.append(data[i] * k + result[-1] * (1 - k))
            return result

        ema_fast = _ema(closes, fast)
        ema_slow = _ema(closes, slow)
        dif = [ema_fast[i] - ema_slow[i] for i in range(n)]
        dea = _ema(dif, signal)
        macd_bar = [2 * (dif[i] - dea[i]) for i in range(n)]

        last_dif = dif[-1]
        last_dea = dea[-1]
        last_bar = macd_bar[-1]
        cross = '多头' if last_dif > last_dea else '空头'

        self._value_label.setText(
            f'DIF: {last_dif:.2f}  |  DEA: {last_dea:.2f}  |  MACD: {last_bar:.2f}  |  状态: {cross}'
        )

        # 绘制：DIF蓝线 + DEA黄线 + MACD红绿柱
        self._plot_widget.set_data(
            lines=[
                (dif, '#2563EB', 1.5),   # DIF蓝
                (dea, '#F59E0B', 1.5),   # DEA黄
            ],
            bars=[macd_bar],            # MACD红绿柱
            zero_line=True,
        )


class KDJIndicatorWidget(_TechIndicatorBase):
    """KDJ指标：K/D/J三线"""
    _config_key = 'kdj'
    params = {'N': 9, 'M1': 3, 'M2': 3}

    def __init__(self, parent=None):
        super().__init__('KDJ', parent)

    def _calc_and_draw(self):
        if not self._data:
            return
        highs = self._data.get('high', [])
        lows = self._data.get('low', [])
        closes = self._data.get('close', [])
        n = len(closes)
        if n < self.params['N']:
            self._value_label.setText('数据不足')
            return
        N = self.params['N']
        M1 = self.params['M1']
        M2 = self.params['M2']

        rsv = []
        for i in range(n):
            s = max(0, i - N + 1)
            hh = max(highs[s:i+1]) if i >= s else highs[i]
            ll = min(lows[s:i+1]) if i >= s else lows[i]
            if hh == ll:
                rsv.append(50.0)
            else:
                rsv.append((closes[i] - ll) / (hh - ll) * 100)

        k_vals = [50.0]
        d_vals = [50.0]
        for i in range(1, n):
            k = (M1 - 1) / M1 * k_vals[-1] + 1 / M1 * rsv[i]
            d = (M2 - 1) / M2 * d_vals[-1] + 1 / M2 * k
            k_vals.append(k)
            d_vals.append(d)
        j_vals = [3 * k_vals[i] - 2 * d_vals[i] for i in range(n)]

        last_k = k_vals[-1]
        last_d = d_vals[-1]
        last_j = j_vals[-1]

        if last_k > 80 or last_d > 80:
            status = '超买区'
        elif last_k < 20 or last_d < 20:
            status = '超卖区'
        else:
            status = '中性'

        self._value_label.setText(
            f'K: {last_k:.2f}  |  D: {last_d:.2f}  |  J: {last_j:.2f}  |  状态: {status}'
        )

        self._plot_widget.set_data(
            lines=[
                (k_vals, '#2563EB', 1.5),   # K蓝
                (d_vals, '#F59E0B', 1.5),   # D黄
                (j_vals, '#8B5CF6', 1),     # J紫
            ],
            bars=[],
            zero_line=False,
        )


class StockDetailPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent); self.current_code = ''; self.current_name = ''
        self.kline_period = 'day'   # 当前K线周期：15min/30min/60min/day/week/month
        self.period_buttons = {}
        self._loading = False  # 加载状态锁，防止重入崩溃
        self._kline_worker = None  # K线增量更新后台Worker（自动刷新引擎）
        p_start("StockDetailPage初始化")
        self._build_ui()
        p_end("StockDetailPage初始化")

    def _build_ui(self):
        main = QVBoxLayout(self); main.setContentsMargins(12, 8, 12, 8); main.setSpacing(8)
        # 顶部信息
        self.header = QFrame(); self.header.setStyleSheet(f'QFrame{{background:{C.CARD};border:1px solid {C.BORDER};border-radius:8px;}}')
        hl = QVBoxLayout(self.header); hl.setContentsMargins(14, 10, 14, 10); hl.setSpacing(6)
        self.title_row = QHBoxLayout(); self.title_row.addWidget(L('📈 个股分析', C.TEXT, 15, True)); self.title_row.addStretch()
        # 全市场搜索框
        self.stock_search = QLineEdit()
        self.stock_search.setPlaceholderText('搜索股票代码/名称/拼音...')
        self.stock_search.setFixedSize(320, 32)
        self.stock_search.setStyleSheet(
            f'QLineEdit{{background:{C.TAB};color:{C.TEXT};border:1px solid {C.BORDER};'
            f'border-radius:16px;padding:0 12px;font-size:12px;}}'
            f'QLineEdit:focus{{border:1px solid #2F6BFF;}}'
        )
        self.title_row.addWidget(self.stock_search)
        # 搜索联想
        self._load_stock_identity()
        from PyQt6.QtWidgets import QCompleter
        self._stock_completer = QCompleter(self._stock_list_items, self)
        self._stock_completer.setMaxVisibleItems(10)
        self._stock_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._stock_completer.activated.connect(self._on_stock_selected)
        self.stock_search.setCompleter(self._stock_completer)
        self.stock_search.returnPressed.connect(self._on_search_return)
        self.back_btn = QPushButton('← 返回'); self.back_btn.setFixedHeight(26); self.back_btn.setStyleSheet(f'QPushButton{{background:{C.TAB};color:{C.TEXT2};border:1px solid {C.BORDER};border-radius:4px;padding:0 12px;font-size:10px;}}QPushButton:hover{{background:{C.CARD_HOVER};color:{C.TEXT};}}')
        self.title_row.addWidget(self.back_btn); hl.addLayout(self.title_row)
        self.info_row = QHBoxLayout(); self.info_row.addWidget(L('请从首页或新闻点击股票查看详情', C.TEXT3, 12)); hl.addLayout(self.info_row)
        main.addWidget(self.header)
        # 主体
        splitter = QSplitter(Qt.Orientation.Vertical)
        # K线区域（V2.8模块6：内部水平布局，左侧K线stretch=1，右侧量化诊断侧边栏fixed 320）
        kline_card = QFrame(); kline_card.setStyleSheet(f'QFrame{{background:{C.CARD};border:1px solid {C.BORDER};border-radius:8px;}}')
        kline_outer = QHBoxLayout(kline_card); kline_outer.setContentsMargins(8, 8, 8, 8); kline_outer.setSpacing(8)
        kline_left = QWidget()
        kl = QVBoxLayout(kline_left); kl.setContentsMargins(0, 0, 0, 0); kl.setSpacing(4)
        self.kline_title = L('日K线（前复权） MA5/MA9/MA20/MA60 + 成交量', C.TEXT2, 11); kl.addWidget(self.kline_title)
        try:
            from ui.kline_container import KlineContainer
            self.kline_container_widget = KlineContainer()
            kl.addWidget(self.kline_container_widget, 1)
            # 注意：不再调用QApplication.processEvents()，避免触发异步ECharts创建导致阻塞
        except Exception as e:
            print(f"[个股分析] KlineContainer创建失败: {e}", flush=True)
            self.kline_container_widget = None
            self.kline_placeholder = L('K线组件初始化失败', C.RED, 12, align=Qt.AlignmentFlag.AlignCenter)
            kl.addWidget(self.kline_placeholder, 1)
        kline_outer.addWidget(kline_left, 1)
        self.quant_sidebar = None
        # V2.8模块6：量化诊断侧边栏（用户要求删除）
        self.quant_sidebar = None
        splitter.addWidget(kline_card); splitter.setSizes([450, 360])
        # MACD + KDJ 技术指标卡片
        indicators_card = QFrame(); indicators_card.setStyleSheet(f'QFrame{{background:{C.CARD};border:1px solid {C.BORDER};border-radius:8px;}}')
        indicators_layout = QVBoxLayout(indicators_card); indicators_layout.setContentsMargins(8, 4, 8, 4); indicators_layout.setSpacing(2)
        self.macd_widget = MACDIndicatorWidget()
        self.macd_widget.setFixedHeight(180)
        indicators_layout.addWidget(self.macd_widget)
        self.kdj_widget = KDJIndicatorWidget()
        self.kdj_widget.setFixedHeight(180)
        indicators_layout.addWidget(self.kdj_widget)
        splitter.addWidget(indicators_card)
        # 光标同步：K线 <-> MACD <-> KDJ 三图联动
        try:
            self.macd_widget._plot_widget.cursor_changed.connect(
                lambda idx: self.kdj_widget._plot_widget.set_cursor_index(idx))
            self.kdj_widget._plot_widget.cursor_changed.connect(
                lambda idx: self.macd_widget._plot_widget.set_cursor_index(idx))
            # 主K线图光标 -> MACD/KDJ
            if hasattr(self, 'kline_container_widget') and self.kline_container_widget:
                self.kline_container_widget.cursor_index_changed.connect(
                    lambda idx: self.macd_widget._plot_widget.set_cursor_index(idx))
                self.kline_container_widget.cursor_index_changed.connect(
                    lambda idx: self.kdj_widget._plot_widget.set_cursor_index(idx))
                print("[指标] K线<->MACD<->KDJ 三图光标联动已连接", flush=True)
        except Exception as _ce:
            print(f"[指标] 光标同步连接失败: {_ce}", flush=True)
        # V2.8模块3：个股资金流向卡片
        # 【2026-09-24 清理 v28 死引用】原开关 v28.config.is_enabled('capital_flow') 已下线，
        # 该卡片此前一直不会创建。现保持原有行为（不创建）不变，属性保留为 None。
        # 如日后找回 v28 包，按原实现恢复即可。
        self.fund_card = None
        main.addWidget(splitter, 1)


    def _load_stock_identity(self):
        """加载全市场股票列表用于搜索联想"""
        self._stock_list_items = []
        self._stock_map = {}
        try:
            import json
            path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'data', 'cache', 'stock_identity.json')
            if os.path.exists(path):
                with open(path, encoding='utf-8') as f:
                    d = json.load(f)
                for code, info in d.items():
                    name = info.get('name', '')
                    pinyin = info.get('pinyin', '')
                    self._stock_list_items.append(f'{name}({code})')
                    self._stock_map[f'{name}({code})'] = (code, name)
                    self._stock_map[code] = (code, name)
                    if pinyin:
                        self._stock_map[pinyin] = (code, name)
                print(f"[个股分析] 搜索列表加载: {len(self._stock_list_items)}只", flush=True)
        except Exception as e:
            print(f"[个股分析] 搜索列表加载失败: {e}", flush=True)

    def _on_search_return(self):
        """回车确认搜索"""
        text = self.stock_search.text().strip()
        if not text:
            return
        # 直接匹配
        self._navigate_to_stock(text)

    def _on_stock_selected(self, text):
        """联想列表选择"""
        self._navigate_to_stock(text)

    def _navigate_to_stock(self, text):
        """根据搜索文本切换个股"""
        try:
            text = text.strip()
            code, name = '', ''
            # 直接从映射查
            if text in self._stock_map:
                code, name = self._stock_map[text]
            else:
                # 尝试从"名称(代码)"格式提取
                import re as _re
                m = _re.search(r'\(?([036]\d{5})\)?', text)
                if m:
                    code = m.group(1)
                    # 查名称
                    for k, v in self._stock_map.items():
                        if v[0] == code:
                            name = v[1]
                            break
                    if not name:
                        name = code
                else:
                    # 按名称模糊匹配
                    for item in self._stock_list_items:
                        if text in item:
                            code, name = self._stock_map[item]
                            break
            if code:
                print(f"[个股分析] 搜索切换: {name}({code})", flush=True)
                self.stock_search.clear()
                self.load_stock(code, name)
            else:
                self.stock_search.setPlaceholderText('未找到对应股票')
        except Exception as e:
            print(f"[个股分析] 搜索切换失败: {e}", flush=True)

    def load_stock(self, code: str, name: str):
        """加载股票详情（重入保护+安全清空+异常兜底）"""
        # 重入保护：正在加载时禁止重复进入，快速多次点击只响应最后一次
        if self._loading:
            return
        self._loading = True
        try:
            self.current_code = code; self.current_name = name
            # 更新标题（安全清空，杜绝悬垂指针崩溃）
            safe_clear_layout(self.info_row)
            self.info_row.addWidget(L(f'{name}({code})', C.TEXT, 16, True)); self.info_row.addSpacing(16)
            # 题材概念（后台加载，避免网络请求阻塞UI）
            self.theme_label = L('题材: 加载中...', C.TEXT2, 10)
            self.theme_label.setMaximumWidth(560)
            self.info_row.addWidget(self.theme_label); self.info_row.addSpacing(8)
            self._start_themes_loader(code)
            # 从扫描结果获取数据
            stock_data = None
            try:
                service = get_real_scan_service(); results = service.get_last_results()
                for s in results:
                    if s.get('code') == code: stock_data = s; break
            except Exception: pass
            if stock_data:
                price = stock_data.get('price', stock_data.get('current_price', 0))
                pct = stock_data.get('pct_chg', stock_data.get('today_change', 0))
                score = stock_data.get('score', 0); details = stock_data.get('details', {})
                pct_color = C.RED if pct >= 0 else C.GREEN
                self.info_row.addWidget(L(f'现价 {price:.2f}', C.TEXT, 13, True)); self.info_row.addSpacing(8)
                self.info_row.addWidget(L(f'{pct:+.2f}%', pct_color, 13, True)); self.info_row.addSpacing(16)
                self.info_row.addWidget(L(f'评分 {score:.0f}', C.PURPLE, 13, True)); self.info_row.addSpacing(16)
                ma5 = details.get('ma5', 0); ma9 = details.get('ma9', 0); ma20 = details.get('ma20', 0); kdj_j = details.get('kdj_j', 0)
                for label, val in [('MA5', f'{ma5:.2f}' if ma5 else '--'), ('MA9', f'{ma9:.2f}' if ma9 else '--'), ('MA20', f'{ma20:.2f}' if ma20 else '--'), ('KDJ-J', f'{kdj_j:.1f}' if kdj_j else '--')]:
                    self.info_row.addWidget(L(f'{label}:{val}', C.TEXT2, 10)); self.info_row.addSpacing(8)
                self.info_row.addStretch()
                # detail_card已移除，不再更新信号/理由/风险/板块/AI520
            else:
                self.info_row.addWidget(L('（该股票不在当前扫描结果中）', C.TEXT3, 10)); self.info_row.addStretch()
            # K线周期切换按钮（15分/30分/60分/日K/周K/月K），挂在标题行右侧
            try:
                self.info_row.addWidget(self._make_period_bar())
            except Exception as _pbe:
                print(f'[个股分析] 周期按钮创建失败: {_pbe}', flush=True)
            # 加载K线（先校验最新日期，过期则后台增量更新后再渲染）
            self._check_kline_date_and_update(code, name)
            # V2.8模块6：量化诊断侧边栏数据
            # 【2026-09-24 清理 v28 死引用】原开关 v28.config.is_enabled('quant_diagnosis')
            # 已下线，此前一直不加载数据。现保持原有行为不变。
            # V2.8模块3：个股资金流向
            # 【2026-09-24 清理 v28 死引用】原开关 v28.config.is_enabled('capital_flow')
            # 与 v28.integration.get_stock_fund_info 均已下线，此前一直不加载。
            # 现保持原有行为不变。
            # 历史信号统计已移除
        except RuntimeError as e:
            # 控件已删除异常，记录日志但不崩溃
            print(f"[个股详情] 控件操作异常（已忽略）: {e}", flush=True)
        except Exception as e:
            print(f"[个股详情] load_stock异常: {e}", flush=True)
            import traceback
            traceback.print_exc()
        finally:
            self._loading = False  # 释放加载锁

    def _start_themes_loader(self, code):
        """后台加载个股题材（优先用选股雷达/AI520扫描题材数据，不在候选中回退概念服务）"""
        try:
            class ThemeThread(QThread):
                done = pyqtSignal(str, str, str)  # code, text, source
                def __init__(self, code):
                    super().__init__(); self.code = code
                def run(self):
                    try:
                        theme = ''
                        src_note = ''
                        stock = None
                        # 1) 优先从涨停原因数据库取（和选股雷达一致）
                        try:
                            from data.limit_up_reason_db import get_last_limit_up_reason
                            reason, lu_date, lbc, lu_industry = get_last_limit_up_reason(self.code)
                            if reason:
                                tags = [t.strip() for t in reason.split('+') if t.strip()]
                                bad_tags = {'首板', '二连板', '三连板', '换手板', '一字板', 'T字板'}
                                tags = [t for t in tags if t not in bad_tags and not (t.endswith('板') and len(t) <= 3)]
                                if tags:
                                    theme = ' / '.join(tags)
                                    src_note = '涨停异动题材'
                        except Exception:
                            pass
                        # 2) 选股雷达实时扫描服务
                        if not theme:
                            try:
                                service = get_real_scan_service()
                                for s in service.get_last_results():
                                    if s.get('code') == self.code:
                                        stock = s; break
                            except Exception:
                                pass
                        # 3) 选股雷达上次扫描缓存
                        if not theme and not stock:
                            try:
                                import json, os
                                cache_p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'ai520_last_result.json')
                                with open(cache_p, 'r', encoding='utf-8') as f:
                                    _data = json.load(f)
                                for s in _data.get('signals', []):
                                    if s.get('code') == self.code:
                                        stock = s; break
                            except Exception:
                                pass
                        # 4) 使用选股雷达的题材（concept优先，其次industry）
                        if not theme and stock:
                            theme = stock.get('concept', '') or stock.get('industry', '')
                            src_note = '选股雷达'
                        # 5) 最后回退概念服务
                        if not theme:
                            from service.concept_service import get_stock_concepts
                            concepts, csrc = get_stock_concepts(self.code)
                            if concepts:
                                theme = ' / '.join(str(c) for c in concepts[:8])
                                src_note = '概念服务'
                        if theme:
                            self.done.emit(self.code, theme, src_note)
                    except Exception as e:
                        print(f"[个股分析] 题材获取失败: {e}", flush=True)
            self._theme_thread = ThemeThread(code)
            self._theme_thread.done.connect(self._on_themes_ready)
            self._theme_thread.start()
        except Exception as e:
            print(f"[个股分析] 题材线程启动失败: {e}", flush=True)

    def _on_themes_ready(self, code, text, source):
        """题材加载完成，更新信息行（校验股票未切换+控件未销毁）"""
        try:
            if code != self.current_code:
                return
            if not hasattr(self, 'theme_label') or not self.theme_label:
                return
            from PyQt6 import sip
            if sip.isdeleted(self.theme_label):
                return
            full = f'题材: {text}'
            fm = self.theme_label.fontMetrics()
            elided = fm.elidedText(full, Qt.TextElideMode.ElideRight, 556)
            self.theme_label.setText(elided)
            self.theme_label.setToolTip(f'{full}\n来源: {source}')
        except Exception as e:
            print(f"[个股分析] 题材更新失败: {e}", flush=True)

    def _check_kline_date_and_update(self, code, name):
        """校验K线最新日期，过期则后台增量更新后再渲染（不阻塞UI）"""
        try:
            from services.kline_cache_service import get_last_date
            last_date = get_last_date(code)
            today_str = datetime.now().strftime('%Y-%m-%d')
            weekday = datetime.now().weekday()
            # 非交易日（周六日）预期为最近周五
            if weekday >= 5:
                expected_date = (datetime.now() - timedelta(days=weekday - 4)).strftime('%Y-%m-%d')
            else:
                expected_date = today_str

            if last_date and last_date >= expected_date:
                # K线已是最新，直接渲染
                self._load_kline(code, name)
                return

            # K线过期，启动后台增量更新
            print(f"[个股分析] {code} K线日期{last_date} < 预期{expected_date}，启动增量更新", flush=True)
            try:
                self.kline_title.setText(f'📈 {name}({code}) K线更新中...')
            except Exception:
                pass

            # 停止旧Worker
            if self._kline_worker and self._kline_worker.isRunning():
                try:
                    self._kline_worker.wait(1000)
                except Exception:
                    pass

            self._kline_worker = KlineUpdateWorker([code])
            self._kline_worker.update_done.connect(
                lambda r, c=code, n=name: self._on_single_kline_updated(r, c, n)
            )
            self._kline_worker.start()
        except Exception as e:
            print(f"[个股分析] K线日期校验异常，直接加载: {e}", flush=True)
            self._load_kline(code, name)

    def _on_single_kline_updated(self, result, code, name):
        """单只股票K线增量更新完成回调（UI线程槽函数）"""
        # 关键修复：校验当前股票是否还是请求更新的股票，防止快速切换时旧回调覆盖新股票
        if code != self.current_code:
            print(f"[个股分析] K线更新回调跳过：请求{code}，当前{self.current_code}（用户已切换股票）", flush=True)
            return
        try:
            updated = result.get('updated', 0)
            if updated > 0:
                print(f"[个股分析] {code} K线更新完成，新增{result.get('new_kline_total', 0)}根", flush=True)
            elif result.get('failed', 0) > 0:
                print(f"[个股分析] {code} K线更新失败: {result.get('failed_list', [])}", flush=True)
        except Exception as e:
            print(f"[个股分析] K线更新回调异常: {e}", flush=True)
        finally:
            # 无论成功失败都重新加载K线（使用最新缓存）
            try:
                # 再次校验，防止回调过程中用户又切换了股票
                if code == self.current_code:
                    self._load_kline(code, name)
                else:
                    print(f"[个股分析] K线更新后加载跳过：请求{code}，当前{self.current_code}", flush=True)
            except Exception as e:
                print(f"[个股分析] 更新后重新加载K线失败: {e}", flush=True)

    # ============================================================
    # K线周期切换（15分/30分/60分/日K/周K/月K）—— 与「我的自选·专业K线图」同一套
    # ============================================================
    _PERIOD_LABELS = [('15min', '15分'), ('30min', '30分'), ('60min', '60分'),
                      ('day', '日K'), ('week', '周K'), ('month', '月K')]
    _PERIOD_NAMES = {'15min': '15分', '30min': '30分', '60min': '60分',
                     'day': '日K', 'week': '周K', 'month': '月K'}

    def _make_period_bar(self):
        """创建K线周期切换按钮栏（样式对齐「我的自选-专业K线图」）"""
        bar = QWidget()
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.period_buttons = {}
        for p, n in self._PERIOD_LABELS:
            btn = QPushButton(n)
            btn.setCheckable(True)
            btn.setFixedHeight(22)
            btn.setStyleSheet(
                f'QPushButton{{background:transparent;color:{C.TEXT2};border:none;'
                f'padding:2px 8px;font-size:11px;border-radius:4px;}}'
                f'QPushButton:hover{{background:{C.CARD_HOVER};color:{C.TEXT};}}'
                f'QPushButton:checked{{background:#e8f0ff;color:{C.BLUE};font-weight:700;}}'
            )
            btn.clicked.connect(lambda checked, _p=p: self._on_kline_period_changed(_p))
            lay.addWidget(btn)
            self.period_buttons[p] = btn
        cur = getattr(self, 'kline_period', 'day')
        if cur in self.period_buttons:
            self.period_buttons[cur].setChecked(True)
        return bar

    def _on_kline_period_changed(self, period):
        """切换K线周期并重新加载当前股票"""
        if period == getattr(self, 'kline_period', 'day'):
            return
        self.kline_period = period
        for p, btn in self.period_buttons.items():
            btn.setChecked(p == period)
        print(f'[个股分析] 切换K线周期: {period}', flush=True)
        if self.current_code:
            self._load_kline(self.current_code, self.current_name, period)

    def _load_kline(self, code, name, period=None):
        """加载K线数据（复用KlineContainer，只更新数据，含渲染重试）"""
        period = period or getattr(self, 'kline_period', 'day')
        # 关键修复：校验当前股票是否还是请求加载的股票，防止异步回调覆盖
        if code != self.current_code:
            print(f"[个股分析] _load_kline跳过：请求{code}，当前{self.current_code}", flush=True)
            return
        try:
            if not self.kline_container_widget:
                self.kline_title.setText(f'📈 {name}({code}) K线组件不可用')
                return
            # 获取K线数据：日K沿用原链路（本地缓存最快）；分钟/周/月线与「我的自选·专业K线图」共用同一数据源
            if period == 'day':
                service = get_real_scan_service()
                _raw = service.get_kline(code, days=240, use_cache=True)
                kline_data = self._convert_kline_format(_raw) if _raw else None
                _n = len(_raw) if _raw else 0
                _last = (_raw[-1].get('date', '') if _raw else '')
            else:
                from utils.kline_provider import get_kline_by_period
                _cnt = 500 if period in ('week', 'month') else 300
                _d = get_kline_by_period(code, _cnt, period)
                if _d:
                    # 注意：该接口返回 dict 且日期键名是 dates，需转成 KlineContainer 要的 date
                    _dates = list(_d.get('dates') or _d.get('date') or [])
                    kline_data = {
                        'date': _dates,
                        'open': list(_d.get('open') or []),
                        'close': list(_d.get('close') or []),
                        'high': list(_d.get('high') or []),
                        'low': list(_d.get('low') or []),
                        'volume': list(_d.get('volume') or []),
                    }
                    _n = len(_dates)
                    _last = _dates[-1] if _n else ''
                else:
                    kline_data = None; _n = 0; _last = ''
            if kline_data and _n > 10:
                # K线渲染加固：首次渲染后延迟100ms重试一次，适配页面切换导致的渲染上下文未就绪
                self.kline_container_widget.set_kline_data(kline_data, code)
                # 更新MACD/KDJ指标
                try:
                    self.macd_widget.set_kline_data(kline_data)
                    self.kdj_widget.set_kline_data(kline_data)
                except Exception as _ie:
                    print(f'[指标] 更新失败: {_ie}', flush=True)
                _pname = self._PERIOD_NAMES.get(period, '日K')
                self.kline_title.setText(f'📈 {name}({code}) {_pname}线（前复权） MA5/MA9/MA20/MA60 + 成交量 | 最新：{_last} | {_n}根')
                # 延迟100ms重试渲染，确保页面切换后渲染上下文就绪
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(100, lambda: self._retry_kline_render(code, name, kline_data))
            else:
                self.kline_title.setText(f'📈 {name}({code}) K线数据不足（{_n}根）')
        except Exception as e:
            print(f"[个股分析] K线加载失败: {e}", flush=True)
            import traceback; traceback.print_exc()
            self.kline_title.setText(f'📈 {name}({code}) K线加载失败: {e}')

    def _retry_kline_render(self, code, name, kline_data):
        """K线渲染重试（适配页面切换导致的渲染上下文未就绪）"""
        # 关键修复：校验当前股票，防止延迟重试时用户已切换股票
        if code != self.current_code:
            print(f"[个股分析] K线渲染重试跳过：请求{code}，当前{self.current_code}", flush=True)
            return
        try:
            if self.kline_container_widget and kline_data:
                self.kline_container_widget.set_kline_data(kline_data, code)
        except Exception as e:
            print(f"[个股分析] K线渲染重试失败: {e}", flush=True)

    def _convert_kline_format(self, kline: List[Dict]) -> Dict:
        """转换K线格式为KlineContainer需要的格式"""
        try:
            dates = [k.get('date', '') for k in kline]
            opens = [float(k.get('open', 0)) for k in kline]
            closes = [float(k.get('close', 0)) for k in kline]
            highs = [float(k.get('high', 0)) for k in kline]
            lows = [float(k.get('low', 0)) for k in kline]
            volumes = [float(k.get('volume', 0)) for k in kline]
            return {'date': dates, 'open': opens, 'close': closes, 'high': highs, 'low': lows, 'volume': volumes}
        except Exception as e:
            print(f"[个股分析] K线格式转换失败: {e}", flush=True); return {}


# ============================================================
# V2.3 AI520观察池UI（真正落地，按日期/批次分组）
# ============================================================
class ObservationPoolPage(QWidget):
    """AI520观察池页面：按日期/批次分组，D0价格冻结，D1/D3/D5/D7统计"""
    stock_clicked = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded_batches = set()
        self._build_ui()
        QTimer.singleShot(500, self._load_observations)

    def _build_ui(self):
        main = QVBoxLayout(self); main.setContentsMargins(12, 8, 12, 8); main.setSpacing(8)
        # 顶部控制栏
        ctrl = QHBoxLayout()
        ctrl.addWidget(L('🎯 AI-520观察池', C.TEXT, 15, True)); ctrl.addSpacing(16)
        self.refresh_btn = QPushButton('🔄 刷新'); self.refresh_btn.setFixedHeight(28)
        self.refresh_btn.setStyleSheet(f'QPushButton{{background:#2563EB;color:white;border:none;border-radius:6px;padding:0 12px;font-size:12px;font-weight:600;}}QPushButton:hover{{background:#1D4ED8;}}')
        self.refresh_btn.clicked.connect(self._load_observations); ctrl.addWidget(self.refresh_btn)
        ctrl.addSpacing(8)
        self.expand_all_btn = QPushButton('📂 全部展开'); self.expand_all_btn.setFixedHeight(28)
        self.expand_all_btn.setStyleSheet(f'QPushButton{{background:{C.TAB};color:{C.TEXT};border:1px solid {C.BORDER};border-radius:4px;padding:0 10px;font-size:11px;}}')
        self.expand_all_btn.clicked.connect(self._expand_all); ctrl.addWidget(self.expand_all_btn)
        ctrl.addSpacing(8)
        self.collapse_all_btn = QPushButton('📁 全部折叠'); self.collapse_all_btn.setFixedHeight(28)
        self.collapse_all_btn.setStyleSheet(f'QPushButton{{background:{C.TAB};color:{C.TEXT};border:1px solid {C.BORDER};border-radius:4px;padding:0 10px;font-size:11px;}}')
        self.collapse_all_btn.clicked.connect(self._collapse_all); ctrl.addWidget(self.collapse_all_btn)
        ctrl.addStretch()
        self.summary_label = L('', C.TEXT2, 11); ctrl.addWidget(self.summary_label)
        main.addLayout(ctrl)
        # 统计面板
        self.stats_panel = QFrame(); self.stats_panel.setStyleSheet(f'QFrame{{background:{C.CARD};border:1px solid {C.BORDER};border-radius:8px;}}')
        sp_layout = QHBoxLayout(self.stats_panel); sp_layout.setContentsMargins(12, 8, 12, 8); sp_layout.setSpacing(16)
        self.stat_total = self._make_stat_box('📊 总观察', '0只')
        self.stat_today = self._make_stat_box('📅 今日新增', '0只')
        self.stat_s = self._make_stat_box('🏆 S/A级', '0只', C.GREEN)
        self.stat_d1 = self._make_stat_box('📈 D1平均', '0%')
        self.stat_dd = self._make_stat_box('📉 最大回撤', '0%', C.RED)
        sp_layout.addStretch()
        main.addWidget(self.stats_panel)
        # 批次列表（滚动区域）
        self.batch_scroll = QScrollArea(); self.batch_scroll.setWidgetResizable(True)
        self.batch_scroll.setStyleSheet(f'QScrollArea{{background:transparent;border:none;}}QScrollBar:vertical{{background:{C.TAB};width:6px;}}QScrollBar::handle:vertical{{background:{C.BORDER_L};border-radius:3px;}}')
        self.batch_container = QWidget(); self.batch_layout = QVBoxLayout(self.batch_container)
        self.batch_layout.setContentsMargins(0, 0, 0, 0); self.batch_layout.setSpacing(8); self.batch_layout.addStretch()
        self.batch_scroll.setWidget(self.batch_container); main.addWidget(self.batch_scroll, 1)

    def _make_stat_box(self, title, value, color=None):
        box = QVBoxLayout(); box.setSpacing(2)
        box.addWidget(L(title, C.TEXT3, 9, True))
        val_label = L(value, color or C.TEXT, 14, True)
        box.addWidget(val_label)
        self.stats_panel.layout().addLayout(box)
        return val_label

    def _load_observations(self):
        """从数据库加载观察池数据，按日期/批次分组"""
        try:
            from services.observation_service import get_observation_service
            from strategy.ai_520_database import AI520Database
            obs_svc = get_observation_service()
            db = AI520Database()
            conn = db._get_conn()
            # 获取所有观察任务，按signal_date分组
            rows = conn.execute("""
                SELECT id, batch_id, signal_date, code, name, signal_price, signal_score,
                       signal_grade, pullback_type, current_day, status, trend_state,
                       d1_pct, d3_pct, d5_pct, d7_pct, max_return, max_drawdown,
                       entry_price_source, data_status
                FROM observation_pool
                ORDER BY signal_date DESC, signal_score DESC
            """).fetchall()
            conn.close()

            # 按日期分组
            batches = defaultdict(list)
            for r in rows:
                date_key = r[2] or '未知日期'
                batches[date_key].append({
                    'id': r[0], 'batch_id': r[1], 'signal_date': r[2],
                    'code': r[3], 'name': r[4], 'signal_price': r[5],
                    'signal_score': r[6], 'signal_grade': r[7], 'pullback_type': r[8],
                    'current_day': r[9], 'status': r[10], 'trend_state': r[11],
                    'd1_pct': r[12], 'd3_pct': r[13], 'd5_pct': r[14], 'd7_pct': r[15],
                    'max_return': r[16], 'max_drawdown': r[17],
                    'entry_price_source': r[18], 'data_status': r[19],
                })

            # 清空现有批次UI
            while self.batch_layout.count() > 1:
                item = self.batch_layout.takeAt(0)
                w = item.widget()
                if w: w.deleteLater()

            total = len(rows)
            today = datetime.now().strftime('%Y-%m-%d')
            today_count = sum(1 for r in rows if (r[2] or '').startswith(today))
            sa_count = sum(1 for r in rows if r[7] in ('S+', 'S', 'A'))

            # 统计
            self.stat_total.setText(f'{total}只')
            self.stat_today.setText(f'{today_count}只')
            self.stat_s.setText(f'{sa_count}只')

            # D1平均收益
            d1_pcts = [r[12] for r in rows if r[12] is not None]
            if d1_pcts:
                avg_d1 = sum(d1_pcts) / len(d1_pcts)
                self.stat_d1.setText(f'{avg_d1:+.2f}%')
                self.stat_d1.setStyleSheet(f'color:{"#34C759" if avg_d1 >= 0 else "#FF3B30"};font-size:14px;font-weight:bold;')

            # 最大回撤
            dd_vals = [r[17] for r in rows if r[17] is not None and r[17] < 0]
            if dd_vals:
                max_dd = min(dd_vals)
                self.stat_dd.setText(f'{max_dd:.2f}%')

            self.summary_label.setText(f'共{len(batches)}个批次 / {total}只观察任务')

            # 按日期创建批次UI
            for date_key in sorted(batches.keys(), reverse=True):
                tasks = batches[date_key]
                batch_widget = self._create_batch_widget(date_key, tasks)
                self.batch_layout.insertWidget(self.batch_layout.count() - 1, batch_widget)

            print(f"[观察池] 加载完成: {len(batches)}个批次, {total}只任务", flush=True)
        except Exception as e:
            print(f"[观察池] 加载失败: {e}", flush=True)
            import traceback; traceback.print_exc()

    def _create_batch_widget(self, date_key, tasks):
        """创建单个批次的UI（可展开/折叠）"""
        frame = QFrame(); frame.setStyleSheet(f'QFrame{{background:{C.CARD};border:1px solid {C.BORDER};border-radius:8px;}}')
        layout = QVBoxLayout(frame); layout.setContentsMargins(12, 8, 12, 8); layout.setSpacing(6)

        # 批次标题行
        header = QHBoxLayout()
        is_expanded = date_key in self._expanded_batches
        toggle_icon = '▼' if is_expanded else '▶'
        toggle_btn = QPushButton(f'{toggle_icon} 📅 {date_key}'); toggle_btn.setFixedHeight(24)
        toggle_btn.setStyleSheet(f'QPushButton{{background:transparent;color:{C.TEXT};border:none;font-size:12px;font-weight:bold;text-align:left;}}QPushButton:hover{{color:{C.BLUE};}}')
        toggle_btn.clicked.connect(lambda: self._toggle_batch(date_key))
        header.addWidget(toggle_btn); header.addSpacing(12)

        # 批次统计
        sa = sum(1 for t in tasks if t.get('signal_grade') in ('S+', 'S', 'A'))
        avg_d1 = ''
        d1_list = [t['d1_pct'] for t in tasks if t.get('d1_pct') is not None]
        if d1_list:
            avg_d1 = f'D1均:{sum(d1_list)/len(d1_list):+.2f}%'
        header.addWidget(L(f'{len(tasks)}只 | S/A:{sa}只 | {avg_d1}', C.TEXT2, 10))
        header.addStretch()
        layout.addLayout(header)

        # 展开内容
        if is_expanded:
            # 表格标题
            header_row = QHBoxLayout()
            cols = [('状态', 50), ('代码', 70), ('名称', 80), ('D0价', 60), ('等级', 50),
                    ('评分', 50), ('D天', 40), ('D1', 60), ('D3', 60), ('D5', 60),
                    ('最高', 60), ('回撤', 60), ('趋势', 80), ('信号', 100)]
            for col_name, col_w in cols:
                lbl = L(col_name, C.TEXT3, 9, True); lbl.setFixedWidth(col_w)
                header_row.addWidget(lbl)
            header_row.addStretch()
            layout.addLayout(header_row)

            # 分隔线
            sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine); sep.setStyleSheet(f'color:{C.BORDER};')
            layout.addWidget(sep)

            # 股票行
            for task in tasks[:50]:  # 每批次最多显示50只，避免UI卡顿
                row = self._create_stock_row(task)
                layout.addWidget(row)
            if len(tasks) > 50:
                layout.addWidget(L(f'... 等共{len(tasks)}只（仅显示前50只）', C.TEXT3, 9))

        return frame

    def _create_stock_row(self, task):
        """创建单只股票的观察行"""
        row = QHBoxLayout(); row.setSpacing(4)
        code = task.get('code', '')
        name = task.get('name', '')
        grade = task.get('signal_grade', '')
        grade_color = {'S+': '#FF9500', 'S': '#FF9500', 'A': '#AF52DE', 'B': '#007AFF', 'C': '#8E8E93'}.get(grade, C.TEXT2)

        # 状态
        status = task.get('status', '观察中')
        status_color = C.GREEN if status == '观察中' else C.TEXT3
        row.addWidget(self._fixed_label(status, 50, status_color, 9))

        # 代码（可点击）
        code_btn = QPushButton(code); code_btn.setFixedWidth(70); code_btn.setFixedHeight(20)
        code_btn.setStyleSheet(f'QPushButton{{background:transparent;color:{C.BLUE};border:none;font-size:10px;font-weight:bold;text-align:left;}}QPushButton:hover{{text-decoration:underline;}}')
        code_btn.clicked.connect(lambda: self.stock_clicked.emit(code, name))
        row.addWidget(code_btn)

        # 名称
        row.addWidget(self._fixed_label(name[:8], 80, C.TEXT, 10))
        # D0价（冻结）
        d0_price = task.get('signal_price', 0)
        row.addWidget(self._fixed_label(f'{d0_price:.2f}', 60, C.TEXT2, 10))
        # 等级
        row.addWidget(self._fixed_label(grade, 50, grade_color, 10, True))
        # 评分
        score = task.get('signal_score', 0)
        row.addWidget(self._fixed_label(f'{score:.0f}', 50, C.TEXT2, 10))
        # D天
        day = task.get('current_day', 0)
        row.addWidget(self._fixed_label(f'D{day}', 40, C.CYAN, 10))
        # D1/D3/D5
        for d_key, d_w in [('d1_pct', 60), ('d3_pct', 60), ('d5_pct', 60)]:
            val = task.get(d_key)
            if val is not None:
                color = '#34C759' if val >= 0 else '#FF3B30'
                row.addWidget(self._fixed_label(f'{val:+.2f}%', d_w, color, 9))
            else:
                row.addWidget(self._fixed_label('-', d_w, C.TEXT3, 9))
        # 最高收益
        max_ret = task.get('max_return')
        if max_ret is not None:
            row.addWidget(self._fixed_label(f'{max_ret:+.2f}%', 60, '#34C759', 9))
        else:
            row.addWidget(self._fixed_label('-', 60, C.TEXT3, 9))
        # 最大回撤
        max_dd = task.get('max_drawdown')
        if max_dd is not None:
            row.addWidget(self._fixed_label(f'{max_dd:.2f}%', 60, '#FF3B30', 9))
        else:
            row.addWidget(self._fixed_label('-', 60, C.TEXT3, 9))
        # 趋势状态
        trend = task.get('trend_state', '')
        trend_color = {'TREND_KEEP': C.GREEN, 'BREAK_MA5': C.ORANGE, 'BREAK_MA20': C.RED, 'REGAIN_MA5': C.CYAN}.get(trend, C.TEXT3)
        row.addWidget(self._fixed_label(trend or '-', 80, trend_color, 9))
        # 信号类型
        signal = task.get('pullback_type', '')
        row.addWidget(self._fixed_label(signal or '-', 100, C.TEXT2, 9))

        row.addStretch()
        # 包装为widget
        w = QWidget(); w.setLayout(row); w.setFixedHeight(22)
        return w

    def _fixed_label(self, text, width, color, size, bold=False):
        lbl = L(text, color, size, bold); lbl.setFixedWidth(width)
        lbl.setWordWrap(False)
        return lbl

    def _toggle_batch(self, date_key):
        """展开/折叠批次"""
        if date_key in self._expanded_batches:
            self._expanded_batches.remove(date_key)
        else:
            self._expanded_batches.add(date_key)
        self._load_observations()

    def _expand_all(self):
        """全部展开"""
        try:
            from strategy.ai_520_database import AI520Database
            db = AI520Database()
            conn = db._get_conn()
            dates = conn.execute("SELECT DISTINCT signal_date FROM observation_pool WHERE signal_date IS NOT NULL").fetchall()
            conn.close()
            self._expanded_batches = set(d[0] for d in dates)
            self._load_observations()
        except Exception as e:
            print(f"[观察池] 全部展开失败: {e}", flush=True)

    def _collapse_all(self):
        """全部折叠"""
        self._expanded_batches = set()
        self._load_observations()


# ============================================================
# V2.8 自动刷新引擎：K线增量更新后台Worker（线程安全，pyqtSignal回传）
# ============================================================
class KlineUpdateWorker(QThread):
    """后台K线增量更新Worker：执行incremental_update_kline，通过信号回传结果"""
    update_done = pyqtSignal(dict)  # 增量更新结果dict

    def __init__(self, codes: list):
        super().__init__()
        self.codes = codes

    def run(self):
        try:
            from services.kline_cache_service import incremental_update_kline
            result = incremental_update_kline(self.codes, verbose=False)
            self.update_done.emit(result)
        except Exception as e:
            print(f"[K线更新Worker] 异常: {e}", flush=True)
            self.update_done.emit({
                'total': len(self.codes), 'updated': 0, 'no_new_data': 0,
                'failed': len(self.codes), 'new_kline_total': 0,
                'details': {}, 'failed_list': [{'error': str(e)}],
            })


# ============================================================
# V2.8 自动刷新引擎：全市场行情刷新后台Worker
# ============================================================
class MarketRefreshWorker(QThread):
    """后台全市场行情刷新Worker：触发行情刷新，通过信号回传结果"""
    refresh_done = pyqtSignal(dict)  # {'ok': bool, 'error': str}

    def run(self):
        try:
            result = {'ok': True, 'error': ''}
            try:
                from services.realtime_quote_refresh import RealtimeQuoteRefresher
                refresher = RealtimeQuoteRefresher()
                result['quote_refresher'] = 'ok'
            except Exception as e:
                result['quote_refresher'] = f'skip: {e}'
            self.refresh_done.emit(result)
        except Exception as e:
            print(f"[行情刷新Worker] 异常: {e}", flush=True)
            self.refresh_done.emit({'ok': False, 'error': str(e)})


# ============================================================
# 主窗口 V2.2
# ============================================================
class BattleConsoleWindowV2(QWidget):
    def __init__(self):
        super().__init__(); self.setWindowTitle('清一盘'); self.resize(1400, 900)
        # V2.8模块10：记录程序启动时间（用于运行时长统计）
        self._app_start_time = datetime.now()
        p_start("BattleConsoleWindowV2._build_ui")
        self.setStyleSheet(f'QWidget{{background:{C.BG};color:{C.TEXT};font-family:"Microsoft YaHei","Segoe UI",sans-serif;}}')
        self._build_ui(); self._connect_signals(); self._init_auto_refresh()
        # 收盘复盘推送：15:05后每个交易日自动生成复盘报告并推到企业微信（一次/日）
        self._close_summary_last_date = None
        self._close_summary_timer = QTimer(self)
        self._close_summary_timer.timeout.connect(self._check_close_summary)
        self._close_summary_timer.start(30000)
        QTimer.singleShot(8000, self._check_close_summary)
        # 【2026-09-24】30分钟新闻简报服务已按用户要求停用（不再需要）
        # 服务文件未删除：services/news_30min_digest.py（要恢复就取消下面注释）
        # # 启动30分钟新闻简报服务
        # try:
        #     from services.news_30min_digest import News30MinDigest
        #     self._digest_service = News30MinDigest()
        #     self._digest_service.start()
        #     print('[30分钟简报] 自动服务已启动', flush=True)
        # except Exception as e:
        #     print(f'[30分钟简报] 启动失败: {e}', flush=True)
        p_end("BattleConsoleWindowV2._build_ui")

    def _check_close_summary(self):
        """15:05后生成并自动推送当日复盘报告到企业微信；每个交易日只推一次。"""
        now = datetime.now()
        if now.weekday() >= 5 or (now.hour * 60 + now.minute) < (15 * 60 + 5):
            return
        today = now.strftime('%Y-%m-%d')
        if self._close_summary_last_date == today:
            return
        self._close_summary_last_date = today
        import threading

        def _worker():
            try:
                from services.daily_close_summary_service import get_daily_close_summary_service
                service = get_daily_close_summary_service()
                result = service.generate_and_push(self)
                print(f"[收盘复盘推送] {result.get('status')}: {result.get('message', '')}", flush=True)
            except Exception as e:
                print(f"[收盘复盘推送] 生成/推送失败: {e}", flush=True)
        threading.Thread(target=_worker, daemon=True, name='DailyCloseSummary').start()

    def _build_ui(self):
        # 初始化异步创建相关的属性
        self._pending_stock_code = None
        self._detail_timer = None
        main = QVBoxLayout(self); main.setContentsMargins(0, 0, 0, 0); main.setSpacing(0)
        # 顶部标题栏
        title_bar = QFrame(); title_bar.setFixedHeight(18); title_bar.setStyleSheet(f'QFrame{{background:{C.TAB};border-bottom:1px solid {C.BORDER};}}')
        tl = QHBoxLayout(title_bar); tl.setContentsMargins(16, 0, 16, 0); tl.setSpacing(12)
        # V2.4: 按用户要求隐藏顶部"🤖 AI盯盘 + V2.3 + 行情/K线/板块/新闻"导航行
        #       （仅不渲染，代码保留后续可恢复；右侧异动提醒/设置按钮保留）
        tl.addStretch()
        # V2.8模块9：自定义异动提醒按钮
        # 【2026-09-24 清理 v28 死引用】原开关 v28.config.is_enabled('custom_alert') 已下线，
        # 该按钮此前一直不会显示。现保持原有行为（不显示）不变。
        # V2.8模块10/11/12：设置按钮（运行监控 / 策略复盘 / AI-520参数设置入口）
        # 【2026-09-24 清理 v28 死引用】原开关 v28.config.is_enabled('health_monitor' /
        # 'push_review' / 'strategy_params') 已下线，该按钮此前一直不会显示。
        # 现保持原有行为（不显示）不变。
        self.clock_label = L(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), C.TEXT2, 11); tl.addWidget(self.clock_label)
        self.clock_timer = QTimer(self); self.clock_timer.timeout.connect(lambda: self.clock_label.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))); self.clock_timer.start(1000)
        main.addWidget(title_bar)
        # V2.7.2：已删除顶部数据源状态导航栏（用户要求移除）
        # p_start("DataSourceStatus创建")
        # main.addWidget(DataSourceStatus())
        # p_end("DataSourceStatus创建")
        # Tab导航
        self.tabs = QTabWidget(); self.tabs.setStyleSheet(f'QTabWidget::pane{{border:none;top:-1px;background:{C.BG};}}QTabBar::tab{{background:{C.TAB};color:{C.TEXT2};border:1px solid {C.BORDER};border-bottom:none;border-top-left-radius:8px;border-top-right-radius:8px;padding:10px 20px;font-size:13px;margin-right:2px;}}QTabBar::tab:selected{{background:{C.CARD};color:{C.BLUE};border-color:{C.BORDER};font-weight:600;}}QTabBar::tab:hover{{background:{C.CARD_HOVER};color:{C.TEXT};}}')
        # 创建页面：作战中控台（占位，后续加市场全景）
        # 【V2.9.7】选股雷达（主力启动+AI520）页已按用户要求移除（2026-09-24）
        p_start("Pages创建")
        print("[主窗口] 创建作战中控台（V2.7 四模块基础版）...", flush=True)
        # V2.7：作战中控台基础模块重建 - 我的自选/领涨题材/今日涨停/板块异动
        try:
            from ui.battle_widgets.battle_console_home import BattleConsoleHome
            self.home_page = BattleConsoleHome()
            print("[主窗口] 作战中控台V2.7创建成功", flush=True)
        except Exception as _bc_err:
            print(f"[主窗口] 作战中控台V2.7创建失败，降级占位: {_bc_err}", flush=True)
            self.home_page = QWidget()
            _hp = QVBoxLayout(self.home_page)
            _hp.setContentsMargins(20, 20, 20, 20)
            _hp.addWidget(L('🤖 AI盯盘', C.TEXT, 20, True))
            _hp.addWidget(L(f'模块加载失败: {_bc_err}', C.RED, 12))
            _hp.addStretch()
        # 【今日市场决策页】清一盘首页第一屏升级：四重共振（板块/龙头/资金/情绪）
        # + 市场状态/建议仓位/方向结论/持仓预警（2026-10-17 新增）
        try:
            from ui.battle_widgets.decision_page_widget import DecisionPageWidget
            self.decision_page = DecisionPageWidget()
            self.tabs.addTab(self.decision_page, '🎯 今日决策')
            print("[主窗口] 今日市场决策页已添加", flush=True)
        except Exception as _dp_err:
            print(f"[主窗口] 今日决策页加载失败: {_dp_err}", flush=True)
            import traceback; traceback.print_exc()
            self.decision_page = QWidget()
        self.tabs.addTab(self.home_page, '🤖 清一盘')
        # 【控盘选股页】以控盘标准单独筛全市场的独立页面（2026-10-11 新增）
        # 口径：控盘分 + 洗盘/出货阶段 + 近120日位置，叠加 C4/C6/试盘/出货形态/拉升观察因子
        try:
            from ui.battle_widgets.control_screen_widget import ControlScreenWidget
            self.ctrl_screen_page = ControlScreenWidget()
            self.tabs.addTab(self.ctrl_screen_page, '🎛 控盘选股')
            print("[主窗口] 控盘选股页已添加", flush=True)
        except Exception as _cs_err:
            print(f"[主窗口] 控盘选股页加载失败: {_cs_err}", flush=True)
            import traceback; traceback.print_exc()
            self.ctrl_screen_page = QWidget()
            _cs_lay = QVBoxLayout(self.ctrl_screen_page)
            _cs_lay.addWidget(L(f'控盘选股页加载失败: {_cs_err}', C.RED, 12,
                                align=Qt.AlignmentFlag.AlignCenter))
            self.tabs.addTab(self.ctrl_screen_page, '🎛 控盘选股')

        # 决策页「一键跳转控盘选股」：切到控盘页并自动开启「仅看今日主线」
        try:
            self.decision_page.jump_to_control.connect(self._jump_to_control_filtered)
        except Exception:
            pass

        # 【策略看板页】对标 TickFlow Stock Panel：经典技术指标策略全市场扫描（2026-10-17 新增）
        # v1：MA金叉/多头排列/MACD金叉/RSI超卖/KDJ金叉/放量突破/缩量回踩MA20，吃本地K线
        try:
            from ui.battle_widgets.strategy_panel_widget import StrategyPanelWidget
            self.strategy_panel_page = StrategyPanelWidget()
            self.tabs.addTab(self.strategy_panel_page, '📈 策略看板')
            print("[主窗口] 策略看板页已添加", flush=True)
        except Exception as _sp_err:
            print(f"[主窗口] 策略看板页加载失败: {_sp_err}", flush=True)
            import traceback; traceback.print_exc()
            self.strategy_panel_page = QWidget()
            _sp_lay = QVBoxLayout(self.strategy_panel_page)
            _sp_lay.addWidget(L(f'策略看板页加载失败: {_sp_err}', C.RED, 12,
                                align=Qt.AlignmentFlag.AlignCenter))
            self.tabs.addTab(self.strategy_panel_page, '📈 策略看板')

        # 【V2.9.7】选股雷达页已移除（2026-09-24 用户要求：不再使用，剔除）
        # 移除原因：① 用户明确不再使用该模块 ② BattleConsoleHomeV2 为重量级组件
        #（含 QScrollArea + 大量子控件），在 Qt 6.11 + Python 3.14 下会触发
        #  C++ 层渲染段错误 0xC0000005（见下方原注释），是程序闪退源之一。
        # 恢复方式：取消下面 8 行注释即可（类定义与 AI520 服务均未删除）。
        # print("[主窗口] 创建选股雷达页（主力启动+AI520）...", flush=True)
        # # 【V2.9.6修复】Qt 6.11 + Python 3.14 下，大型 QWidget 子类（BattleConsoleHomeV2，
        # # 含 QScrollArea + 大量子控件）直接作为 QTabWidget 页面时，窗口最大化/缩放
        # # 触发 C++ 层渲染段错误（0xC0000005）。用一层空 QWidget 容器包装隔离渲染。
        # self.radar_page = QWidget()
        # _radar_lay = QVBoxLayout(self.radar_page)
        # _radar_lay.setContentsMargins(0, 0, 0, 0)
        # self._radar_inner = BattleConsoleHomeV2()
        # _radar_lay.addWidget(self._radar_inner)
        # self.tabs.addTab(self.radar_page, '🎯 选股雷达')
        # print("[主窗口] 选股雷达页已添加", flush=True)
        # 确保事件循环不被阻塞
        try:
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            print("[主窗口] 作战中控台后事件循环已处理", flush=True)
        except Exception:
            pass
        p_end("BattleConsoleHomeV2创建")  # 历史探针名保留：该组件已移除，此行现在只用于结束计时
        print("[主窗口] 开始创建个股分析页占位符...", flush=True)
        # V2.8启动优化：StockDetailPage异步创建，避免KlineContainer/QWebEngineView初始化阻塞主线程
        # 先创建占位符，主窗口显示后再异步创建真实的个股分析页
        p_start("StockDetailPage占位符创建")
        self.detail_page = None
        self._detail_placeholder = QWidget()
        _ph_layout = QVBoxLayout(self._detail_placeholder)
        _ph_layout.addWidget(L('📊 个股分析页正在初始化...', C.TEXT2, 14, align=Qt.AlignmentFlag.AlignCenter))
        self.tabs.addTab(self._detail_placeholder, '📊 个股分析')
        p_end("StockDetailPage占位符创建")
        # 延迟300ms异步创建StockDetailPage，确保主窗口先显示
        self._detail_page_retry_count = 0  # P3任务4：个股分析页创建重试计数器
        QTimer.singleShot(300, self._async_create_detail_page)
        p_start("NewsPage创建(含同步新闻加载)")
        self.news_page = NewsPage(); self.tabs.addTab(self.news_page, '📰 实时新闻')
        p_end("NewsPage创建(含同步新闻加载)")
        # 自选评分（复用现有WatchlistWidget）
        try:
            p_start("WatchlistWidget创建")
            from ui.watchlist_panel import WatchlistWidget
            self.watchlist_page = WatchlistWidget(); self.tabs.addTab(self.watchlist_page, '⭐ 自选评分')
            p_end("WatchlistWidget创建")
        except Exception as e:
            print(f"[主窗口] 自选评分加载失败: {e}", flush=True)
            import traceback; traceback.print_exc()
            self.watchlist_page = QWidget(); wl = QVBoxLayout(self.watchlist_page); wl.addWidget(L(f'自选评分模块加载失败: {e}', C.RED, 14, align=Qt.AlignmentFlag.AlignCenter)); self.tabs.addTab(self.watchlist_page, '⭐ 自选评分')
            p_end("WatchlistWidget创建(失败)")
        # V2.9：分时做T回测页 (JoinQuant 风格)
        try:
            p_start("BacktestPage创建")
            from ui.backtest_page import BacktestPage
            self.backtest_page = BacktestPage()
            # self.tabs.addTab(self.backtest_page, '📈 做T回测')  # V2.4: 用户要求删除做T回测Tab(保留页面对象/文件)
            p_end("BacktestPage创建")
        except Exception as e:
            print(f"[主窗口] 做T回测加载失败: {e}", flush=True)
            import traceback; traceback.print_exc()
            self.backtest_page = QWidget()
            _bt = QVBoxLayout(self.backtest_page)
            _bt.addWidget(L(f"做T回测模块加载失败: {e}", C.RED, 14, align=Qt.AlignmentFlag.AlignCenter))
            # self.tabs.addTab(self.backtest_page, '📈 做T回测')  # V2.4: 删除做T回测Tab
            p_end("BacktestPage创建(失败)")
        # V2.7：观察池功能已彻底删除，不再创建Tab
        # V2.8模块2：板块雷达Tab 已按用户要求移除
        main.addWidget(self.tabs, 1)

    def _async_create_detail_page(self):
        """异步创建StockDetailPage，避免阻塞主窗口初始化"""
        try:
            print("[启动优化] 开始异步创建个股分析页...", flush=True)
            p_start("StockDetailPage异步创建")
            self.detail_page = StockDetailPage()
            # 替换占位符
            tab_index = self.tabs.indexOf(self._detail_placeholder)
            if tab_index >= 0:
                self.tabs.removeTab(tab_index)
                self.tabs.insertTab(tab_index, self.detail_page, '📊 个股分析')
            # 连接信号
            self.detail_page.back_btn.clicked.connect(lambda: self.tabs.setCurrentWidget(self.home_page))
            p_end("StockDetailPage异步创建")
            print("[启动优化] 个股分析页异步创建完成", flush=True)
            # 如果有缓存的股票需要加载，在这里处理
            if hasattr(self, '_pending_stock_code') and self._pending_stock_code:
                code, name = self._pending_stock_code
                self._pending_stock_code = None
                self._show_stock_detail(code, name)
        except Exception as e:
            print(f"[启动优化] 个股分析页异步创建失败: {e}", flush=True)
            import traceback; traceback.print_exc()
            # P3任务4：失败后重试机制（最多重试2次，每次间隔2秒，不阻塞UI）
            self._detail_page_retry_count = getattr(self, '_detail_page_retry_count', 0) + 1
            if self._detail_page_retry_count <= 2:
                print(f"[启动优化] 个股分析页第{self._detail_page_retry_count}次重试，2秒后执行...", flush=True)
                QTimer.singleShot(2000, self._async_create_detail_page)
            else:
                print(f"[启动优化] 个股分析页重试{self._detail_page_retry_count}次仍失败，显示错误提示", flush=True)
                try:
                    _ph_layout = self._detail_placeholder.layout()
                    if _ph_layout:
                        while _ph_layout.count() > 0:
                            _item = _ph_layout.takeAt(0)
                            _w = _item.widget()
                            if _w: _w.deleteLater()
                        from PyQt6.QtWidgets import QLabel as _QL
                        _err_label = _QL('个股分析页加载失败，请重启应用')
                        _err_label.setStyleSheet('color: #DC2626; font-size: 14px;')
                        _err_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        _ph_layout.addWidget(_err_label)
                except Exception as _e:
                    print(f"[启动优化] 显示错误提示失败: {_e}", flush=True)

    def _connect_signals(self):
        # 【V2.9.7】选股雷达页已移除（2026-09-24）。改为「存在才连接」，
        # 否则 getattr 返回 None 后会继续取 self.radar_page，触发 AttributeError。
        _radar_src = getattr(self, '_radar_inner', None)
        if _radar_src is not None:
            _radar_src.stock_clicked.connect(self._show_stock_detail)
        self.news_page.stock_clicked.connect(self._show_stock_detail)
        # V3.x：作战中控台（我的自选/今日涨停/机会发现）点击股票名称跳转个股分析
        try:
            if hasattr(self, 'home_page') and self.home_page and hasattr(self.home_page, 'stock_clicked'):
                self.home_page.stock_clicked.connect(self._show_stock_detail)
                print('[信号连接] 作战中控台 stock_clicked 已连接个股分析', flush=True)
        except Exception as _e:
            print(f'[信号连接] 作战中控台 stock_clicked 连接失败: {_e}', flush=True)
        # 【控盘选股页】点击股票名称跳转个股分析
        try:
            if getattr(self, 'ctrl_screen_page', None) and hasattr(self.ctrl_screen_page, 'stock_clicked'):
                self.ctrl_screen_page.stock_clicked.connect(self._show_stock_detail)
                print('[信号连接] 控盘选股页 stock_clicked 已连接个股分析', flush=True)
        except Exception as _e:
            print(f'[信号连接] 控盘选股页 stock_clicked 连接失败: {_e}', flush=True)

        # 【策略看板页】双击股票跳转个股分析
        try:
            if getattr(self, 'strategy_panel_page', None) and hasattr(self.strategy_panel_page, 'stock_clicked'):
                self.strategy_panel_page.stock_clicked.connect(self._show_stock_detail)
                print('[信号连接] 策略看板页 stock_clicked 已连接个股分析', flush=True)
        except Exception as _e:
            print(f'[信号连接] 策略看板页 stock_clicked 连接失败: {_e}', flush=True)
        # P1修复：自选股面板点击跳转个股分析页（用户要求取消自动跳转）
        try:
            if hasattr(self, 'watchlist_page') and self.watchlist_page and hasattr(self.watchlist_page, 'stock_clicked'):
                # self.watchlist_page.stock_clicked.connect(self._show_stock_detail)
                print("[信号连接] 自选股自动跳转已取消", flush=True)
        except Exception as e:
            print(f"[信号连接] 自选股stock_clicked连接失败: {e}", flush=True)
        # V2.8模块5：信号跟踪面板卡片点击跳转个股详情
        try:
            if hasattr(self, 'signal_tracking_panel') and self.signal_tracking_panel:
                self.signal_tracking_panel.stock_clicked.connect(self._show_stock_detail)
        except Exception as e:
            print(f"[V2.8接入] 信号跟踪面板信号连接失败: {e}", flush=True)
        # V2.7：观察池已删除，不再连接signal
        # V2.8启动优化：detail_page可能为None（异步创建），需检查后再连接信号
        # 信号连接已在_async_create_detail_page中完成，这里只在同步创建时连接
        if self.detail_page is not None and hasattr(self.detail_page, 'back_btn'):
            self.detail_page.back_btn.clicked.connect(lambda: self.tabs.setCurrentWidget(self.home_page))
        else:
            print("[启动优化] detail_page未就绪，back_btn信号将在异步创建完成后连接", flush=True)
        # V3.0：新闻中心智能启停 - Tab切换时调整刷新频率
        self.tabs.currentChanged.connect(self._on_tab_changed)
        # V2.8模块9：自定义异动提醒后台检测线程
        # 【2026-09-24 清理 v28 死引用】原开关 v28.config.is_enabled('custom_alert') 已下线，
        # 该后台线程此前一直不会启动。现保持原有行为（不启动）不变。

    # ============================================================
    # V2.8 全局自动刷新引擎（第六优先级核心）
    # ============================================================
    @staticmethod
    def is_trading_time() -> bool:
        """判断当前是否为A股交易时段：9:30-11:30 和 13:00-15:00（周一至周五）"""
        try:
            now = datetime.now()
            weekday = now.weekday()
            if weekday >= 5:  # 周六日
                return False
            t = now.time()
            from datetime import time as dt_time
            morning_start = dt_time(9, 30)
            morning_end = dt_time(11, 30)
            afternoon_start = dt_time(13, 0)
            afternoon_end = dt_time(15, 0)
            return (morning_start <= t <= morning_end) or (afternoon_start <= t <= afternoon_end)
        except Exception:
            return False

    def _init_auto_refresh(self):
        """初始化全局自动刷新引擎：定时器+Worker+锁，交易时段自动启动"""
        try:
            # 定时器
            self._market_refresh_timer = QTimer(self)
            self._market_refresh_timer.timeout.connect(self._on_market_refresh_timeout)
            self._kline_refresh_timer = QTimer(self)
            self._kline_refresh_timer.timeout.connect(self._on_kline_refresh_timeout)
            # 等待开盘定时器（非交易时段每5分钟检查一次）
            self._wait_open_timer = QTimer(self)
            self._wait_open_timer.timeout.connect(self._check_and_start_refresh)

            # Worker引用（防止被GC）
            self._market_refresh_worker = None
            self._kline_refresh_worker = None
            # 任务锁（防止重复触发）
            self._market_refresh_busy = False
            self._kline_refresh_busy = False

            # 立即检查是否在交易时段
            self._check_and_start_refresh()
            print("[自动刷新引擎] 初始化完成", flush=True)
        except Exception as e:
            print(f"[自动刷新引擎] 初始化失败: {e}", flush=True)

    def _check_and_start_refresh(self):
        """检查当前是否在交易时段，是则启动刷新定时器，否则启动等待开盘定时器"""
        try:
            if self.is_trading_time():
                # 停止等待开盘定时器
                if hasattr(self, '_wait_open_timer') and self._wait_open_timer.isActive():
                    self._wait_open_timer.stop()
                # 启动行情刷新定时器（3分钟）
                if not self._market_refresh_timer.isActive():
                    self._market_refresh_timer.start(180000)
                    print("[自动刷新引擎] 行情刷新定时器已启动（3分钟）", flush=True)
                # 启动K线刷新定时器（5分钟）
                if not self._kline_refresh_timer.isActive():
                    self._kline_refresh_timer.start(300000)
                    print("[自动刷新引擎] K线刷新定时器已启动（5分钟）", flush=True)
            else:
                # 非交易时段：停止刷新定时器，启动等待开盘定时器
                if hasattr(self, '_market_refresh_timer') and self._market_refresh_timer.isActive():
                    self._market_refresh_timer.stop()
                    print("[自动刷新引擎] 非交易时段，行情刷新定时器已停止", flush=True)
                if hasattr(self, '_kline_refresh_timer') and self._kline_refresh_timer.isActive():
                    self._kline_refresh_timer.stop()
                    print("[自动刷新引擎] 非交易时段，K线刷新定时器已停止", flush=True)
                if not self._wait_open_timer.isActive():
                    self._wait_open_timer.start(300000)  # 5分钟检查一次
        except Exception as e:
            print(f"[自动刷新引擎] 检查交易时段异常: {e}", flush=True)

    def _on_market_refresh_timeout(self):
        """行情刷新定时器超时（3分钟）：后台Worker执行，禁止直接网络请求"""
        try:
            if not self.is_trading_time():
                self._check_and_start_refresh()
                return
            if self._market_refresh_busy:
                print("[自动刷新引擎] 行情刷新上一次未完成，跳过本次", flush=True)
                return
            self._market_refresh_busy = True
            self._market_refresh_worker = MarketRefreshWorker()
            self._market_refresh_worker.refresh_done.connect(self._on_market_refresh_done)
            self._market_refresh_worker.start()
        except Exception as e:
            print(f"[自动刷新引擎] 行情刷新超时异常: {e}", flush=True)
            self._market_refresh_busy = False

    def _on_market_refresh_done(self, result: dict):
        """行情刷新完成回调（UI线程）：同步更新大盘/板块/选股列表"""
        try:
            self._market_refresh_busy = False
            if not result.get('ok', False):
                print(f"[自动刷新引擎] 行情刷新失败: {result.get('error', '')}", flush=True)
                return
            # 同步更新大盘全景指标（MarketRiskPanel）
            try:
                if hasattr(self, 'home_page') and hasattr(self.home_page, '_market_risk_panel'):
                    panel = self.home_page._market_risk_panel
                    if panel and hasattr(panel, 'refresh_now'):
                        panel.refresh_now()
            except Exception as e:
                print(f"[自动刷新引擎] 大盘面板刷新异常: {e}", flush=True)
            # 同步更新板块雷达数据（板块雷达功能已移除）
            # 同步更新选股结果列表的价格/涨跌幅/量比
            try:
                self._refresh_stock_list_quotes()
            except Exception as e:
                print(f"[自动刷新引擎] 选股列表行情刷新异常: {e}", flush=True)
            print("[自动刷新引擎] 行情刷新完成", flush=True)
        except Exception as e:
            print(f"[自动刷新引擎] 行情刷新回调异常: {e}", flush=True)
            self._market_refresh_busy = False

    def _refresh_stock_list_quotes(self):
        """刷新选股结果列表中个股的实时价格/涨跌幅/量比"""
        try:
            service = get_real_scan_service()
            results = service.get_last_results()
            if not results:
                return
            codes = [s.get('code', '') for s in results if s.get('code')]
            if not codes:
                return
            # 使用行情刷新服务获取最新报价
            try:
                from services.realtime_quote_refresh import RealtimeQuoteRefresher
                refresher = RealtimeQuoteRefresher()
                refreshed, stats = refresher.refresh_signals_quotes(results, force=True)
                if refreshed:
                    # 更新扫描服务缓存的结果
                    service._last_results = refreshed
                    print(f"[自动刷新引擎] 选股列表行情已同步: {stats.get('refreshed', 0)}只更新", flush=True)
            except Exception as e:
                print(f"[自动刷新引擎] 选股列表行情获取异常: {e}", flush=True)
        except Exception as e:
            print(f"[自动刷新引擎] 选股列表刷新异常: {e}", flush=True)

    def _on_kline_refresh_timeout(self):
        """K线刷新定时器超时（5分钟）：更新当前打开个股+自选股K线"""
        try:
            if not self.is_trading_time():
                self._check_and_start_refresh()
                return
            if self._kline_refresh_busy:
                print("[自动刷新引擎] K线刷新上一次未完成，跳过本次", flush=True)
                return
            # 收集需要更新的股票代码
            codes = []
            # 当前打开的个股
            if self.detail_page is not None and self.detail_page.current_code:
                codes.append(self.detail_page.current_code)
            # 自选股列表
            try:
                from core.watchlist import get_watchlist_manager
                mgr = get_watchlist_manager()
                wl_codes = mgr.get_codes()
                for c in wl_codes:
                    if c not in codes:
                        codes.append(c)
            except Exception as e:
                print(f"[自动刷新引擎] 获取自选股代码异常: {e}", flush=True)

            if not codes:
                return

            self._kline_refresh_busy = True
            print(f"[自动刷新引擎] 开始K线增量更新: {len(codes)}只（当前个股+自选股）", flush=True)
            self._kline_refresh_worker = KlineUpdateWorker(codes)
            self._kline_refresh_worker.update_done.connect(self._on_kline_refresh_done)
            self._kline_refresh_worker.start()
        except Exception as e:
            print(f"[自动刷新引擎] K线刷新超时异常: {e}", flush=True)
            self._kline_refresh_busy = False

    def _on_kline_refresh_done(self, result: dict):
        """K线刷新完成回调（UI线程）：如个股分析页打开则自动刷新K线图"""
        try:
            self._kline_refresh_busy = False
            updated = result.get('updated', 0)
            if updated > 0:
                print(f"[自动刷新引擎] K线更新完成: {updated}只更新，新增{result.get('new_kline_total', 0)}根", flush=True)
                # 如果个股分析页当前打开，自动刷新K线图
                try:
                    if hasattr(self, 'tabs') and self.detail_page is not None and self.tabs.currentWidget() is self.detail_page:
                        if self.detail_page.current_code and self.detail_page.current_name:
                            self.detail_page._load_kline(
                                self.detail_page.current_code,
                                self.detail_page.current_name
                            )
                            print("[自动刷新引擎] 个股分析页K线图已自动刷新", flush=True)
                except Exception as e:
                    print(f"[自动刷新引擎] 个股K线图自动刷新异常: {e}", flush=True)
            else:
                print(f"[自动刷新引擎] K线更新完成: 无新数据（{result.get('no_new_data', 0)}只）", flush=True)
        except Exception as e:
            print(f"[自动刷新引擎] K线刷新回调异常: {e}", flush=True)
            self._kline_refresh_busy = False

    def _stop_auto_refresh(self):
        """停止所有自动刷新定时器和后台线程（程序关闭时调用）"""
        try:
            for attr in ['_market_refresh_timer', '_kline_refresh_timer', '_wait_open_timer']:
                if hasattr(self, attr):
                    timer = getattr(self, attr)
                    if timer and timer.isActive():
                        timer.stop()
            for attr in ['_market_refresh_worker', '_kline_refresh_worker']:
                if hasattr(self, attr):
                    worker = getattr(self, attr)
                    if worker and worker.isRunning():
                        try:
                            worker.wait(2000)
                        except Exception:
                            pass
            print("[自动刷新引擎] 已停止所有定时器和线程", flush=True)
        except Exception as e:
            print(f"[自动刷新引擎] 停止异常: {e}", flush=True)

    def closeEvent(self, event):
        """窗口关闭事件：停止自动刷新引擎后再关闭"""
        try:
            self._stop_auto_refresh()
        except Exception:
            pass
        super().closeEvent(event)

    def _on_tab_changed(self, index):
        try:
            current_widget = self.tabs.currentWidget()
            self.news_page.set_tab_visible(current_widget is self.news_page)
        except Exception as e:
            print(f"[主窗口] Tab切换回调异常: {e}", flush=True)

    # ============================================================
    # V2.8 模块9/10/11/12 的四个入口对话框
    # 【2026-09-24 清理 v28 死引用】原来分别调用 v28.integration 的
    # get_custom_alert_config_dialog / get_health_monitor_panel /
    # get_push_review_panel / get_strategy_params_dialog，v28 包已不存在，
    # 这四个对话框此前一直打不开。方法签名保留（避免外部引用报错），
    # 内部改为空操作。如日后找回 v28 包，按原实现恢复即可。
    # ============================================================
    def _show_custom_alert_dialog(self):
        """V2.8模块9：异动提醒设置对话框（v28 已下线，当前为空操作）"""
        return

    def _show_health_monitor_panel(self):
        """V2.8模块10：运行状态监控面板（v28 已下线，当前为空操作）"""
        return

    def _show_push_review_panel(self):
        """V2.8模块11：策略效果复盘面板（v28 已下线，当前为空操作）"""
        return

    def _show_strategy_params_dialog(self):
        """V2.8模块12：AI-520策略参数配置中心（v28 已下线，当前为空操作）"""
        return

    def _on_alert_triggered(self, alert_data: dict):
        """V2.8模块9：后台线程触发异动提醒（UI线程槽函数）"""
        try:
            if hasattr(self, 'alert_popup_mgr') and self.alert_popup_mgr:
                self.alert_popup_mgr.show_alert(alert_data)
        except Exception as e:
            print(f"[V2.8接入] 异动弹窗显示失败: {e}", flush=True)

    def _jump_to_control_filtered(self):
        """决策页跳转：切到控盘选股页并勾选「仅看今日主线」。"""
        try:
            self.tabs.setCurrentWidget(self.ctrl_screen_page)
            if hasattr(self.ctrl_screen_page, 'enable_mainline_filter'):
                self.ctrl_screen_page.enable_mainline_filter()
        except Exception as e:
            print(f"[决策页] 跳转控盘选股失败: {e}", flush=True)

    def _show_stock_detail(self, code, name):
        """显示个股详情（200ms防抖+先切页再加载+页面就绪校验）"""
        # 防抖：取消之前的延迟调用
        if hasattr(self, '_detail_timer') and self._detail_timer is not None:
            self._detail_timer.stop()
        # 延迟200ms执行，快速多次点击只响应最后一次
        self._detail_timer = QTimer(self)
        self._detail_timer.setSingleShot(True)
        def _do_show():
            try:
                # 检查个股分析页是否已异步创建完成
                if self.detail_page is None:
                    # 页面还在创建中，缓存股票代码，等创建完成后自动加载
                    self._pending_stock_code = (code, name)
                    print(f"[启动优化] 个股分析页未就绪，缓存股票: {name}({code})", flush=True)
                    return
                # 修正时序：先切换页面，确保布局容器先渲染就绪
                self.tabs.setCurrentWidget(self.detail_page)
                # 页面就绪校验：等待K线容器创建完成，最多重试3次
                self._wait_and_load_stock(code, name, retry=0)
            except Exception as e:
                print(f"[主窗口] 显示个股详情异常: {e}", flush=True)
        self._detail_timer.timeout.connect(_do_show)
        self._detail_timer.start(200)

    def _wait_and_load_stock(self, code, name, retry=0):
        """等待页面就绪后加载股票数据（最多重试3次，每次延迟50ms）"""
        try:
            # V2.8启动优化：检查detail_page是否已异步创建完成
            if self.detail_page is None:
                if retry < 5:
                    print(f"[主窗口] detail_page未就绪，延迟50ms重试({retry+1}/5)", flush=True)
                    QTimer.singleShot(50, lambda: self._wait_and_load_stock(code, name, retry + 1))
                else:
                    print(f"[主窗口] detail_page创建超时，缓存股票: {name}({code})", flush=True)
                    self._pending_stock_code = (code, name)
                return
            # 检查K线容器是否已创建
            kline_ready = (hasattr(self.detail_page, 'kline_container_widget') 
                          and self.detail_page.kline_container_widget is not None)
            # 检查布局是否已创建
            layout_ready = (hasattr(self.detail_page, 'info_row') 
                           and self.detail_page.info_row is not None
                           and hasattr(self.detail_page, 'signals_row')
                           and self.detail_page.signals_row is not None)
            
            if kline_ready and layout_ready:
                # 页面就绪，加载数据
                self.detail_page.load_stock(code, name)
            elif retry < 3:
                # 页面未就绪，延迟50ms重试
                QTimer.singleShot(50, lambda: self._wait_and_load_stock(code, name, retry + 1))
            else:
                # 重试3次仍未就绪，直接加载（异常会被load_stock内部捕获）
                print(f"[主窗口] 页面就绪超时，直接加载: {code}", flush=True)
                self.detail_page.load_stock(code, name)
        except Exception as e:
            print(f"[主窗口] 等待页面就绪异常: {e}", flush=True)


# ============================================================
# 入口
# ============================================================
if __name__ == '__main__':
    app = QApplication(sys.argv); app.setStyle('Fusion')
    window = BattleConsoleWindowV2(); window.show(); sys.exit(app.exec())

