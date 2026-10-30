# -*- coding: utf-8 -*-
"""
V7.4 精准买点页面
将V7.4.8冻结交易规则接入UI，6个区域：
1. 今日重点关注池
2. A/B级信号
3. 买卖计划
4. 历史交割单
5. 模拟资金曲线
6. 自动复盘结果

独立页面，不修改任何策略逻辑，只调用已有接口和读取已有数据。
"""
import os
import sys
import csv
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QTabWidget, QProgressBar,
    QMessageBox, QHeaderView, QFrame, QComboBox, QLineEdit,
    QFileDialog, QSplitter, QGroupBox, QGridLayout, QScrollArea
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QBrush, QFont

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ============================================================
# 真实股票名称映射（从stock_names_full.json加载）
# ============================================================
_STOCK_NAME_MAP = None

def get_stock_name_map():
    """获取code→真实名称映射，懒加载"""
    global _STOCK_NAME_MAP
    if _STOCK_NAME_MAP is not None:
        return _STOCK_NAME_MAP
    _STOCK_NAME_MAP = {}
    json_path = os.path.join(PROJECT_ROOT, 'data', 'stock_names_full.json')
    if os.path.exists(json_path):
        try:
            import json
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                _STOCK_NAME_MAP = {str(k).zfill(6): v for k, v in data.items()}
        except Exception:
            pass
    return _STOCK_NAME_MAP

def resolve_stock_name(code):
    """根据代码获取真实股票名称，找不到返回代码"""
    if not code:
        return ''
    code_str = str(code).zfill(6)
    name_map = get_stock_name_map()
    return name_map.get(code_str, code_str)

def normalize_code(code):
    """代码标准化为6位补零字符串"""
    if code is None:
        return ''
    return str(code).zfill(6)

# 卖出原因英文→中文映射
SELL_REASON_CN = {
    'stop_loss': '止损-7%',
    'take_profit': '止盈+8%',
    'timeout': '第10天收盘',
    'time_out': '第10天收盘',
    'expired': '第10天收盘',
    'ma5_break': 'MA5跌破卖出',
    'trailing_stop': '移动止损',
    'partial': '部分止盈',
}

# 信号状态英文→中文映射
SIGNAL_STATUS_CN = {
    'closed': '已完成',
    'pending': '持仓中',
    'open': '持仓中',
    'stop_loss': '已止损',
    'take_profit': '已止盈',
    'timeout': '已到期',
    'expired': '已到期',
    'completed': '已完成',
}

def translate_sell_reason(reason):
    """卖出原因中文化"""
    if not reason:
        return ''
    reason_lower = str(reason).lower().strip()
    if reason_lower in SELL_REASON_CN:
        return SELL_REASON_CN[reason_lower]
    # 包含关键词匹配
    if 'stop' in reason_lower or '损' in reason:
        return '止损'
    if 'profit' in reason_lower or '盈' in reason:
        return '止盈'
    if 'time' in reason_lower or '期' in reason or '天' in reason:
        return '到期卖出'
    return str(reason)

def translate_signal_status(status):
    """信号状态中文化"""
    if not status:
        return ''
    status_lower = str(status).lower().strip()
    return SIGNAL_STATUS_CN.get(status_lower, str(status))


# 等级优先级（数字越小优先级越高）
GRADE_PRIORITY = {'S级': 0, 'S': 0, 'A级': 1, 'A': 1, 'B级': 2, 'B': 2,
                   '重点关注': 3, '观察': 4, '过滤': 5}


# ============================================================
# 信号生命周期管理（V7.5.2）
# ============================================================
from datetime import datetime as _dt

# 信号状态定义
SIGNAL_STATUS = {
    'new': '🟢新出现',
    'buy_window': '🟡买入窗口',
    'watch_valid': '🔵有效观察',
    'watch_level': '🔵观察级',
    'expired': '⚪失效',
}

# 信号状态颜色
SIGNAL_STATUS_COLOR = {
    'new': '#3fb950',
    'buy_window': '#d29922',
    'watch_valid': '#58a6ff',
    'watch_level': '#58a6ff',
    'expired': '#8b949e',
}

# V7.5.3 信号状态排序优先级（数字越小越优先）
STATUS_PRIORITY = {
    'new': 0,         # 🟢新出现 最优先
    'buy_window': 1,  # 🟡买入窗口 次优先
    'watch_valid': 2, # 🔵有效观察 第三
    'watch_level': 3, # 🔵观察级 第四
    'expired': 4,     # ⚪失效 最后
}

# 建议操作
SIGNAL_ACTION = {
    'new': '关注低吸机会',
    'buy_window': '建议买入',
    'watch_valid': '等待回调或升级',
    'watch_level': '等待评分提升',
    'expired': '已过期',
}


def _days_between(date1, date2):
    """计算两个YYYYMMDD日期之间的自然日天数差"""
    try:
        d1 = _dt.strptime(str(date1), '%Y%m%d')
        d2 = _dt.strptime(str(date2), '%Y%m%d')
        return abs((d2 - d1).days)
    except Exception:
        return 0


def determine_signal_status(signal, current_date):
    """
    根据score和持续天数判断信号状态：
    V7.4.2优化：优先使用pool_grade（精准买点评分制池子）
    - new(🟢新出现): 买入池/强买点 且 首次=最新=今日
    - buy_window(🟡买入窗口): 买入池/强买点 且 持续<=3天
    - watch_valid(🔵有效观察): 观察池 且 持续<=3天
    - watch_level(🔵观察级): 观察池 且 持续>3天
    - expired(⚪失效): 过滤池 或 持续>5天
    """
    # V8.1修复：同时支持final_score和enhanced_score（V7.6生产层用final_score）
    score = signal.get('final_score', signal.get('enhanced_score', 0))
    # V7.4.2：精准买点评分（如果有则优先使用）
    precision_score = signal.get('precision_score', None)
    pool_grade = signal.get('pool_grade', None)
    duration = signal.get('signal_duration', 1)
    first_date = str(signal.get('first_signal_date', '') or signal.get('date', ''))
    latest_date = str(signal.get('latest_signal_date', '') or signal.get('date', ''))
    cur = str(current_date) if current_date else ''

    # V7.4.2：基于池子等级判断（优先）
    if pool_grade:
        # 过滤池直接失效
        if pool_grade == '过滤池':
            return 'expired'
        # 持续>5天失效
        if duration > 5:
            return 'expired'
        # 买入池/强买点
        if pool_grade in ('买入池', '强买点'):
            if score >= 0 and first_date and latest_date and cur and first_date == latest_date == cur:
                return 'new'
            if duration <= 3:
                return 'buy_window'
            return 'watch_valid'  # 买入池持续>3天转为有效观察
        # 观察池
        if pool_grade == '观察池':
            if duration <= 3:
                return 'watch_valid'
            return 'watch_level'
        return 'expired'

    # 原有逻辑（兼容无pool_grade的情况）
    # 失效：score<40 或 持续>5天
    if score < 40 or duration > 5:
        return 'expired'

    # 新出现：首次=最新=今日 且 score>=50
    if score >= 50 and first_date and latest_date and cur and first_date == latest_date == cur:
        return 'new'

    # 买入窗口：score>=50且持续<=3天
    if score >= 50 and duration <= 3:
        return 'buy_window'

    # 有效观察：score>=50但持续>3天
    if score >= 50 and duration > 3:
        return 'watch_valid'

    # 观察级：40<=score<50
    return 'watch_level'


def calculate_signal_lifecycle(signals, current_date=None):
    """
    对去重后的信号计算生命周期字段。
    新增字段：signal_duration/current_score/signal_status/signal_status_text/signal_action
    """
    if not signals:
        return []

    # 如果没有指定current_date，用最新信号日期
    if current_date is None:
        dates = [str(r.get('latest_signal_date', '') or r.get('date', '')) for r in signals]
        dates = [d for d in dates if d and d.isdigit()]
        current_date = max(dates) if dates else ''

    for r in signals:
        first_date = str(r.get('first_signal_date', '') or r.get('date', ''))
        latest_date = str(r.get('latest_signal_date', '') or r.get('date', ''))
        # V8.1修复：同时支持final_score和enhanced_score
        current_score = r.get('final_score', r.get('enhanced_score', 0))

        # 计算持续天数（最新信号日 - 首次信号日 + 1）
        if first_date and latest_date and first_date.isdigit() and latest_date.isdigit():
            duration = _days_between(first_date, latest_date) + 1
        else:
            duration = r.get('signal_count', 1)

        r['signal_duration'] = duration
        r['current_score'] = current_score

        # 判断状态
        status = determine_signal_status(r, current_date)
        r['signal_status'] = status
        r['signal_status_text'] = SIGNAL_STATUS.get(status, status)
        r['signal_action'] = SIGNAL_ACTION.get(status, '')

    return signals


def deduplicate_signals(signals, window_days=5):
    """
    同一股票5个交易日内多个信号，只保留最高score的一条。
    优先级：S>A>B>重点关注>观察，同级保留最新日期。
    返回去重后的信号列表，每条增加first_signal_date/latest_signal_date/signal_count/highest_score字段。
    """
    if not signals:
        return []

    # V8.0修复：类型检查，过滤非字典元素，防止崩溃
    if not isinstance(signals, list):
        print(f"[去重警告] signals不是列表，类型: {type(signals)}，尝试提取列表字段")
        if isinstance(signals, dict):
            for key in ('signals', 'results', 'data', 'stocks'):
                if key in signals and isinstance(signals[key], list):
                    signals = signals[key]
                    print(f"[去重警告] 从字典字段'{key}'提取列表，长度{len(signals)}")
                    break
            else:
                print("[去重警告] 字典中未找到列表字段，返回空列表")
                return []
        else:
            print("[去重警告] 非列表非字典，返回空列表")
            return []

    # 过滤非字典元素
    valid_signals = []
    for r in signals:
        if isinstance(r, dict):
            valid_signals.append(r)
        else:
            print(f"[去重警告] 跳过非字典元素: type={type(r).__name__}, value={str(r)[:100]}")
    if len(valid_signals) != len(signals):
        print(f"[去重警告] 过滤了{len(signals)-len(valid_signals)}个非字典元素，剩余{len(valid_signals)}个有效信号")
    signals = valid_signals

    if not signals:
        return []

    # 按股票代码分组
    groups = {}
    for r in signals:
        code = r.get('stock_code') or r.get('code') or ''
        if not code:
            continue
        if code not in groups:
            groups[code] = []
        groups[code].append(r)

    deduped = []
    for code, group in groups.items():
        # 按score降序、等级优先级、日期降序排序
        # V7.6: 优先使用final_score，否则回退到enhanced_score
        def sort_key(r):
            score = r.get('final_score', r.get('enhanced_score', 0))
            grade = r.get('grade', '观察')
            grade_pri = GRADE_PRIORITY.get(grade, 4)
            date = r.get('date', '') or r.get('signal_date', '')
            return (-score, grade_pri, -int(date) if str(date).isdigit() else 0)

        sorted_group = sorted(group, key=sort_key)
        best = dict(sorted_group[0])  # 复制，避免修改原始数据

        # 计算统计字段
        dates = [r.get('date', '') or r.get('signal_date', '') for r in group]
        dates = [d for d in dates if d]
        # V7.6: 优先使用final_score
        scores = [r.get('final_score', r.get('enhanced_score', 0)) for r in group]

        best['first_signal_date'] = min(dates) if dates else ''
        best['latest_signal_date'] = max(dates) if dates else ''
        best['signal_count'] = len(group)
        best['highest_score'] = max(scores) if scores else best.get('final_score', best.get('enhanced_score', 0))
        # 代表信号的评分用最高评分（V7.6: final_score和enhanced_score都更新）
        best['enhanced_score'] = best['highest_score']
        best['final_score'] = best['highest_score']

        deduped.append(best)

    # 去重后按评分降序（V7.6: final_score优先）
    deduped.sort(key=lambda x: x.get('final_score', x.get('enhanced_score', 0)), reverse=True)
    return deduped


# ============================================================
# 冻结交易规则常量（从V7.4.8报告读取，不硬编码业务逻辑）
# ============================================================
FROZEN_RULES = {
    'trade_pool': ['S级', 'A级', 'B级', '重点关注'],
    'forbidden_grade': '观察级',
    'min_score': 50,
    'buy_method': '次日低吸（开盘-1%则买入，否则开盘买）',
    'take_profit': 0.08,
    'stop_loss': -0.07,
    'max_hold_days': 10,
    'market_filter': {
        '上涨': '100%仓位（所有信号）',
        '震荡': '50%仓位（仅score>=50）',
        '下跌': '停止新增交易',
    },
    'position_pct': 0.10,
    'max_positions': 10,
}

# 等级颜色
GRADE_COLORS = {
    'S级': '#FF4444',
    'A级': '#FF8C00',
    'B级': '#FFD700',
    '重点关注': '#4A90D9',
    '观察': '#888888',
}

# 深色主题样式
DARK_STYLE = """
QWidget { background: #0d1117; color: #c9d1d9; font-size: 12px; }
QTableWidget { background: #161b22; gridline-color: #30363d; alternate-background-color: #1c2128; }
QTableWidget::item { padding: 4px 8px; border: none; }
QHeaderView::section { background: #21262d; color: #8b949e; padding: 6px 8px; border: 1px solid #30363d; font-weight: 600; }
QPushButton { background: #238636; color: white; border: none; padding: 6px 16px; border-radius: 4px; font-weight: 600; }
QPushButton:hover { background: #2ea043; }
QPushButton:disabled { background: #30363d; color: #8b949e; }
QPushButton#secondary { background: #30363d; }
QPushButton#secondary:hover { background: #484f58; }
QTabWidget::pane { border: 1px solid #30363d; background: #0d1117; }
QTabBar::tab { background: #161b22; color: #8b949e; padding: 8px 16px; border: 1px solid #30363d; border-bottom: none; }
QTabBar::tab:selected { background: #0d1117; color: #58a6ff; border-bottom: 2px solid #58a6ff; }
QProgressBar { background: #21262d; border: 1px solid #30363d; border-radius: 4px; text-align: center; }
QProgressBar::chunk { background: #238636; border-radius: 3px; }
QComboBox, QLineEdit { background: #21262d; border: 1px solid #30363d; padding: 4px 8px; border-radius: 4px; color: #c9d1d9; }
QGroupBox { border: 1px solid #30363d; border-radius: 6px; margin-top: 12px; padding-top: 12px; font-weight: 600; color: #8b949e; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
QLabel#stat_value { font-size: 20px; font-weight: 700; color: #58a6ff; }
QLabel#stat_label { font-size: 11px; color: #8b949e; }
QLabel#market_up { color: #3fb950; font-weight: 700; }
QLabel#market_flat { color: #d29922; font-weight: 700; }
QLabel#market_down { color: #f85149; font-weight: 700; }
"""


# ============================================================
# 后台扫描线程
# ============================================================
class V74ScanThread(QThread):
    """全市场扫描后台线程"""
    progress = pyqtSignal(int, int, int)  # done, total, found
    finished_scan = pyqtSignal(list)       # 扫描结果列表
    failed = pyqtSignal(str)
    market_info = pyqtSignal(str, str)     # V7.5.6: 行情日期, 数据状态(正常/过期/未知)

    def __init__(self, lookback=1, min_grade='观察', limit=None):
        super().__init__()
        self.lookback = lookback
        self.min_grade = min_grade
        self.limit = limit
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _get_latest_market_date(self, engine):
        """V7.5.6: 获取最新行情日期，从上证指数或第一只股票K线"""
        try:
            # 尝试上证指数
            for code in ['000001', 'sh000001', '600000']:
                klines = engine.get_kline(code, days=3)
                if klines and len(klines) > 0:
                    return str(klines[-1]['date'])
        except Exception:
            pass
        return ''

    def run(self):
        try:
            # V7.6-A：使用V7.6优化策略评分（MA20过滤+趋势过滤+8因子评分>=60）
            from strategies.v75_optimized_strategy import (
                calculate_v75_score, generate_buy_conditions, load_stock_data, determine_v75_grade,
            )
            from data.tdx_data_engine import TdxDataEngine
            from utils.tdx_stock_list import get_realtime_quotes_tdx
            from datetime import datetime, timedelta
            import pandas as pd
            import numpy as np

            engine = TdxDataEngine()

            # 获取股票代码
            codes = engine.get_all_main_board_codes()
            if self.limit and codes:
                codes = codes[:self.limit]

            total = len(codes)
            found = 0
            all_signals = []

            # V7.6-A数据源切换：批量获取通达信实时报价（与实时监控大厅同一接口）
            print(f"[V7.6-A] 正在获取{len(codes)}只股票实时报价...")
            realtime_quotes = {}
            try:
                # 分批获取，每批80只
                for batch_start in range(0, len(codes), 80):
                    batch_codes = codes[batch_start:batch_start+80]
                    batch_quotes = get_realtime_quotes_tdx(batch_codes)
                    if batch_quotes:
                        realtime_quotes.update(batch_quotes)
                    if self._cancelled:
                        return
                print(f"[V7.6-A] 实时报价获取完成: {len(realtime_quotes)}只")
            except Exception as e:
                print(f"[V7.6-A] 实时报价获取失败，使用本地K线: {e}")

            def _augment_kline_with_realtime(df, code):
                """用实时报价补充最新K线（数据源切换核心逻辑）"""
                if df is None or len(df) == 0:
                    return df
                quote = realtime_quotes.get(code)
                if not quote:
                    return df
                price = quote.get('price', 0)
                if price <= 0:
                    return df
                # 检查实时报价是否比本地K线新
                last_close = float(df['close'].values[-1])
                last_date = str(df['date'].values[-1])
                # 如果实时价与本地最后收盘价不同，说明有新交易日数据
                if abs(price - last_close) < 0.001 and quote.get('last_close', 0) == last_close:
                    return df  # 数据一致，无需补充
                # 构造新K线：日期=本地最后日期+1（或当前日期），价格用实时报价
                try:
                    last_dt = datetime.strptime(last_date[:8], '%Y%m%d')
                    # 找到下一个交易日（简单+1天，周末也接受，因为K线日期只用于排序）
                    new_date_int = int((last_dt + timedelta(days=1)).strftime('%Y%m%d'))
                except Exception:
                    new_date_int = int(last_date[:8]) + 1
                open_p = quote.get('open', price) or price
                high_p = quote.get('high', max(price, open_p)) or max(price, open_p)
                low_p = quote.get('low', min(price, open_p)) or min(price, open_p)
                vol = quote.get('volume', 0)
                amount = quote.get('amount', 0)
                # 构造新行
                new_row = df.iloc[-1].copy()
                new_row['date'] = new_date_int
                new_row['open'] = open_p
                new_row['high'] = high_p
                new_row['low'] = low_p
                new_row['close'] = price
                new_row['volume'] = vol
                if 'amount' in new_row:
                    new_row['amount'] = amount
                # 追加到DataFrame
                df_augmented = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                return df_augmented

            for i, code in enumerate(codes):
                if self._cancelled:
                    return
                try:
                    df = load_stock_data(engine, code, days=400, trim_tail=False)
                    if df is None or len(df) < 60:
                        continue
                    # V7.6-A数据源切换：用实时报价补充最新K线
                    df = _augment_kline_with_realtime(df, code)
                    conds = generate_buy_conditions(df)
                    n = len(df)
                    # 扫描近lookback天
                    for offset in range(self.lookback):
                        idx = n - 1 - offset
                        if idx < 30:
                            break
                        score, details, core_count = calculate_v75_score(
                            df.iloc[:idx+1], {k: v[:idx+1] for k, v in conds.items()}, idx, '震荡'
                        )
                        if score >= 60 and core_count >= 3:
                            grade_result = determine_v75_grade(score, core_count)
                            grade = grade_result[0] if isinstance(grade_result, tuple) else grade_result
                            date_str = str(df.iloc[idx].get('date', ''))
                            all_signals.append({
                                'code': code,
                                'date': date_str,
                                'price': float(df['close'].values[idx]),
                                'enhanced_score': score,  # 字段转换：v76_score -> enhanced_score
                                'v76_score': score,
                                'core_conditions': core_count,
                                'grade': grade,
                                'model': 'V7.6-A',
                                'signal_count': 1,
                                'first_signal_date': date_str,
                                'latest_signal_date': date_str,
                                'hold_days': 10,
                                'details': details,
                            })
                            found += 1
                except Exception:
                    continue

                if (i + 1) % 50 == 0 or i == total - 1:
                    self.progress.emit(i + 1, total, found)

            if self._cancelled:
                return

            # V7.6-A：发出最新行情日期（用实时报价的日期）
            if realtime_quotes:
                # 用补充后的K线最新日期
                sample_code = codes[0] if codes else None
                if sample_code:
                    df_sample = load_stock_data(engine, sample_code, days=5, trim_tail=False)
                    if df_sample is not None and len(df_sample) > 0:
                        df_sample = _augment_kline_with_realtime(df_sample, sample_code)
                        latest_date = str(df_sample['date'].values[-1])
                    else:
                        latest_date = self._get_latest_market_date(engine)
                else:
                    latest_date = self._get_latest_market_date(engine)
            else:
                latest_date = self._get_latest_market_date(engine)
            market_status = '正常' if latest_date else '未知'
            self.market_info.emit(latest_date, market_status)

            # 字段统一转换 + 真实名称补全 + 代码补零
            name_map = get_stock_name_map()
            normalized = []
            for r in all_signals:
                code = normalize_code(r.get('code') or r.get('stock_code', ''))
                name = name_map.get(code, r.get('name') or code)
                price = r.get('price') or r.get('current_price') or r.get('close') or 0
                r['stock_code'] = code
                r['stock_name'] = name
                r['current_price'] = float(price) if price else 0
                normalized.append(r)

            self.finished_scan.emit(normalized)

        except Exception as e:
            import traceback
            self.failed.emit(f"{str(e)}\n{traceback.format_exc()}")


# ============================================================
# 数据读取工具
# ============================================================
def read_csv_safe(filepath, encoding='utf-8-sig'):
    """安全读取CSV，返回list[dict]"""
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, 'r', encoding=encoding, errors='replace') as f:
            reader = csv.DictReader(f)
            return list(reader)
    except Exception:
        return []


def load_trade_orders():
    """加载历史交割单（合并V7.4.6/V7.4.7/V7.4.8），代码补零+名称映射+原因中文化"""
    all_orders = []
    name_map = get_stock_name_map()
    files = [
        ('V7.4.6', os.path.join(PROJECT_ROOT, 'reports', 'V7.4.6_trade_orders.csv')),
        ('V7.4.7', os.path.join(PROJECT_ROOT, 'reports', 'V7.4.7_trailing_stop_test.csv')),
        ('V7.4.8', os.path.join(PROJECT_ROOT, 'reports', 'V7.4.8_partial_exit_test.csv')),
    ]
    for version, fpath in files:
        rows = read_csv_safe(fpath)
        for r in rows:
            # 代码补零
            code = normalize_code(r.get('code') or r.get('stock_code', ''))
            r['code'] = code
            r['stock_code'] = code
            # 名称映射
            name = r.get('name') or r.get('stock_name', '')
            if not name or name == code or name.isdigit():
                name = name_map.get(code, code)
            r['name'] = name
            r['stock_name'] = name
            # 卖出原因中文化
            for key in ('sell_reason', 'second_sell_reason', 'first_sell_reason'):
                if key in r and r[key]:
                    r[key] = translate_sell_reason(r[key])
            r['_version'] = version
            all_orders.append(r)
    return all_orders


def load_daily_nav():
    """加载资金曲线数据"""
    fpath = os.path.join(PROJECT_ROOT, 'reports', 'V7.4.6_daily_nav.csv')
    return read_csv_safe(fpath)


def load_feedback_signals():
    """加载自动复盘信号数据库（DuckDB），代码补零+名称映射+状态中文化"""
    db_path = os.path.join(PROJECT_ROOT, 'data', 'cache', 'v74_signals.db')
    if not os.path.exists(db_path):
        return []
    try:
        import duckdb
        con = duckdb.connect(db_path, read_only=True)
        df = con.execute("SELECT * FROM signals ORDER BY signal_date DESC LIMIT 500").fetchdf()
        con.close()
        name_map = get_stock_name_map()
        records = df.to_dict('records')
        for r in records:
            # 代码补零
            code = normalize_code(r.get('stock_code') or r.get('code', ''))
            r['stock_code'] = code
            r['code'] = code
            # 名称映射
            name = r.get('stock_name') or r.get('name', '')
            if not name or name == code or (isinstance(name, str) and name.isdigit()):
                name = name_map.get(code, code)
            r['stock_name'] = name
            r['name'] = name
            # 状态中文化
            if 'status' in r and r['status']:
                r['status_cn'] = translate_signal_status(r['status'])
            else:
                r['status_cn'] = ''
            # 统一字段名
            if 'signal_date' in r and 'date' not in r:
                r['date'] = r['signal_date']
            if 'enhanced_score' in r and 'score' not in r:
                r['score'] = r['enhanced_score']
        return records
    except Exception:
        return []


def detect_market_state():
    """检测当前市场状态（简化：用最近交割单数据等权平均近似）"""
    # 简化实现：默认返回震荡，实际可接入上证指数
    return '震荡', 'MA20走平，建议50%仓位（仅score>=50）'


# ============================================================
# 通用表格工具
# ============================================================
def create_table(headers):
    """创建标准深色表格"""
    table = QTableWidget()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setStretchLastSection(True)
    table.verticalHeader().setDefaultSectionSize(28)
    return table


def fill_table(table, rows, col_keys, grade_col=None):
    """填充表格数据"""
    # V7.4.2：确保表格列数与col_keys一致，防止列数不匹配导致显示异常
    if table.columnCount() != len(col_keys):
        table.setColumnCount(len(col_keys))
        table.setHorizontalHeaderLabels(col_keys)

    table.setRowCount(len(rows))
    for i, row in enumerate(rows):
        for j, key in enumerate(col_keys):
            val = row.get(key, '')
            if isinstance(val, float):
                val = f"{val:.2f}"
            item = QTableWidgetItem(str(val))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # 等级颜色
            if grade_col and key == grade_col and val in GRADE_COLORS:
                item.setForeground(QBrush(QColor(GRADE_COLORS[val])))
                font = item.font()
                font.setBold(True)
                item.setFont(font)

            # 收益率颜色
            if key in ('return_pct', '收益率', '实际收益率', '平均收益') and val:
                try:
                    v = float(str(val).replace('%', ''))
                    if v > 0:
                        item.setForeground(QBrush(QColor('#3fb950')))
                    elif v < 0:
                        item.setForeground(QBrush(QColor('#f85149')))
                except Exception:
                    pass

            table.setItem(i, j, item)
    table.resizeColumnsToContents()


# ============================================================
# V7.4 精准买点主页面
# ============================================================
class V74PrecisionBuyPage(QWidget):
    """V7.4 精准买点页面 - 6个区域"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('⭐ V7.6-A 精准买点 - 优化交易规则')
        self.resize(1400, 900)
        self.setStyleSheet(DARK_STYLE)

        self.scan_thread = None
        self.current_results = []
        self.current_deduped_results = []

        self._init_ui()
        self._load_historical_data()

    def _init_ui(self):
        """初始化UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # ===== 顶部标题栏 =====
        title_bar = QHBoxLayout()
        title = QLabel('⭐ V7.6-A 精准买点')
        title.setStyleSheet('font-size: 18px; font-weight: 700; color: #58a6ff;')
        title_bar.addWidget(title)

        subtitle = QLabel('V7.6-A优化：胜率53.2% | 平均+1.42% | 回撤-4.00% | 评分≥60 | 第5天清仓')
        subtitle.setStyleSheet('font-size: 11px; color: #8b949e;')
        title_bar.addWidget(subtitle)
        title_bar.addStretch()

        # 市场状态指示器
        self.market_label = QLabel('市场状态：检测中...')
        self.market_label.setObjectName('market_flat')
        title_bar.addWidget(self.market_label)

        # V7.5.6: 行情日期显示
        self.market_date_label = QLabel('📅 行情日期：--')
        self.market_date_label.setStyleSheet('font-size: 11px; color: #8b949e; background: #1c2128; padding: 4px 8px; border-radius: 4px;')
        title_bar.addWidget(self.market_date_label)

        main_layout.addLayout(title_bar)

        # ===== 工具栏 =====
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.scan_btn = QPushButton('🔍 全市场扫描')
        self.scan_btn.clicked.connect(self._start_scan)
        toolbar.addWidget(self.scan_btn)

        self.cancel_btn = QPushButton('⏹ 取消')
        self.cancel_btn.setObjectName('secondary')
        self.cancel_btn.clicked.connect(self._cancel_scan)
        self.cancel_btn.setEnabled(False)
        toolbar.addWidget(self.cancel_btn)

        self.lookback_combo = QComboBox()
        self.lookback_combo.addItems(['今日(1天)', '近3天', '近5天', '近10天'])
        self.lookback_combo.setCurrentText('近3天')  # V7.5.3默认近3天，匹配主力启动前1-3天买点模型
        toolbar.addWidget(self.lookback_combo)

        # V7.5.3 扫描窗口提示
        self.window_hint_label = QLabel('💡 当前窗口：近3天 | 匹配主力启动前1-3天买点模型')
        self.window_hint_label.setStyleSheet('color: #d29922; font-size: 11px; background: #1c2128; padding: 4px 8px; border-radius: 4px;')
        toolbar.addWidget(self.window_hint_label)
        # 切换窗口时更新提示
        self.lookback_combo.currentTextChanged.connect(self._update_window_hint)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(300)
        self.progress_bar.setVisible(False)
        toolbar.addWidget(self.progress_bar)

        self.status_label = QLabel('就绪')
        self.status_label.setStyleSheet('color: #8b949e; font-size: 11px;')
        toolbar.addWidget(self.status_label)

        toolbar.addStretch()

        self.export_btn = QPushButton('📥 导出买卖计划')
        self.export_btn.setObjectName('secondary')
        self.export_btn.clicked.connect(self._export_trade_plan)
        toolbar.addWidget(self.export_btn)

        main_layout.addLayout(toolbar)

        # ===== 6个区域 Tab =====
        self.tabs = QTabWidget()

        # Tab1: 今日重点关注池
        self.tab1 = self._create_focus_pool_tab()
        self.tabs.addTab(self.tab1, '🎯 今日重点关注池')

        # Tab2: A/B级信号
        self.tab2 = self._create_ab_signals_tab()
        self.tabs.addTab(self.tab2, '⭐ A/B级信号')

        # Tab3: 买卖计划
        self.tab3 = self._create_trade_plan_tab()
        self.tabs.addTab(self.tab3, '📋 买卖计划')

        # Tab4: 历史交割单
        self.tab4 = self._create_history_orders_tab()
        self.tabs.addTab(self.tab4, '📊 历史交割单')

        # Tab5: 模拟资金曲线
        self.tab5 = self._create_nav_curve_tab()
        self.tabs.addTab(self.tab5, '📈 模拟资金曲线')

        # Tab6: 自动复盘结果
        self.tab6 = self._create_feedback_tab()
        self.tabs.addTab(self.tab6, '🔄 自动复盘结果')

        main_layout.addWidget(self.tabs, stretch=1)

        # ===== 底部状态栏 =====
        bottom = QHBoxLayout()
        self.bottom_label = QLabel(
            'V7.6-A规则：MA20过滤+趋势过滤 | 评分≥60 | 次日低吸 | 破5日线止盈 | '
            '-5%减半/-7%全清 | 第5天收益<0清仓 | 最长10天 | 单笔10%仓位'
        )
        self.bottom_label.setStyleSheet('font-size: 10px; color: #6e7681;')
        bottom.addWidget(self.bottom_label)
        main_layout.addLayout(bottom)

        # 检测市场状态
        QTimer.singleShot(100, self._update_market_state)

    # ============================================================
    # Tab1: 今日重点关注池
    # ============================================================
    def _create_focus_pool_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        # 统计栏
        stat_bar = QHBoxLayout()
        self.focus_count_label = QLabel('0')
        self.focus_count_label.setObjectName('stat_value')
        self.focus_avg_score_label = QLabel('0')
        self.focus_avg_score_label.setObjectName('stat_value')
        self.focus_s_label = QLabel('0')
        self.focus_s_label.setObjectName('stat_value')
        self.focus_a_label = QLabel('0')
        self.focus_a_label.setObjectName('stat_value')
        # V7.4.2 新增：买入池/观察池数量统计
        self.buy_pool_label = QLabel('0')
        self.buy_pool_label.setObjectName('stat_value')
        self.buy_pool_label.setStyleSheet('color: #f85149; font-size: 20px; font-weight: 700;')
        self.watch_pool_label = QLabel('0')
        self.watch_pool_label.setObjectName('stat_value')
        self.watch_pool_label.setStyleSheet('color: #58a6ff; font-size: 20px; font-weight: 700;')

        for label, text in [
            (self.buy_pool_label, '买入池'),
            (self.watch_pool_label, '观察池'),
            (self.focus_count_label, '当前显示'),
            (self.focus_avg_score_label, '平均评分'),
            (self.focus_s_label, '强买点'),
            (self.focus_a_label, 'S/A级'),
        ]:
            box = QVBoxLayout()
            box.addWidget(label)
            l = QLabel(text)
            l.setObjectName('stat_label')
            box.addWidget(l)
            stat_bar.addLayout(box)
        stat_bar.addStretch()

        # V7.4回退：显示范围筛选
        view_bar = QHBoxLayout()
        view_label = QLabel('显示范围：')
        view_label.setStyleSheet('color: #8b949e; font-size: 11px;')
        view_bar.addWidget(view_label)
        self.focus_view_combo = QComboBox()
        self.focus_view_combo.addItems(['重点关注池(score>=60)', '观察池(50<=score<60)', '全部信号'])
        self.focus_view_combo.setCurrentIndex(0)
        self.focus_view_combo.currentIndexChanged.connect(self._refresh_focus_pool)
        view_bar.addWidget(self.focus_view_combo)
        view_bar.addStretch()
        layout.addLayout(view_bar)

        layout.addLayout(stat_bar)

        # V7.4回退：原16列表格
        headers = ['代码', '名称', '最高评分', '等级', '模型', '信号状态', '距离信号', '建议操作',
                   '当前价', '建议买入价', '止盈价', '止损价', '首次信号日', '最新信号日', '信号次数', '持仓天数']
        self.focus_table = create_table(headers)
        self.focus_table.cellDoubleClicked.connect(self._open_stock_detail)
        layout.addWidget(self.focus_table, stretch=1)

        return widget

    # ============================================================
    # Tab2: A/B级信号
    # ============================================================
    def _create_ab_signals_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        # A/B级Tab切换
        self.ab_tabs = QTabWidget()

        # A级
        a_widget = QWidget()
        a_layout = QVBoxLayout(a_widget)
        a_headers = ['代码', '名称', '等级', '模型', '评分', '买入条件', '止盈', '止损', '当前价']
        self.a_table = create_table(a_headers)
        self.a_table.cellDoubleClicked.connect(self._open_stock_detail)
        a_layout.addWidget(self.a_table)
        self.ab_tabs.addTab(a_widget, '⭐ A级（TOP1突破确认）')

        # B级
        b_widget = QWidget()
        b_layout = QVBoxLayout(b_widget)
        b_headers = ['代码', '名称', '等级', '模型', '评分', '买入条件', '止盈', '止损', '当前价']
        self.b_table = create_table(b_headers)
        self.b_table.cellDoubleClicked.connect(self._open_stock_detail)
        b_layout.addWidget(self.b_table)
        self.ab_tabs.addTab(b_widget, '⭐ B级（TOP3提前埋伏）')

        layout.addWidget(self.ab_tabs, stretch=1)
        return widget

    # ============================================================
    # Tab3: 买卖计划
    # ============================================================
    def _create_trade_plan_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        # 市场状态+仓位建议
        plan_bar = QHBoxLayout()
        self.plan_market_label = QLabel('市场状态：检测中...')
        self.plan_market_label.setObjectName('market_flat')
        plan_bar.addWidget(self.plan_market_label)

        self.plan_position_label = QLabel('仓位建议：--')
        plan_bar.addWidget(self.plan_position_label)
        plan_bar.addStretch()

        refresh_btn = QPushButton('🔄 刷新市场状态')
        refresh_btn.setObjectName('secondary')
        refresh_btn.clicked.connect(self._update_market_state)
        plan_bar.addWidget(refresh_btn)

        layout.addLayout(plan_bar)

        # 表格
        headers = ['代码', '名称', '评分', '等级', '建议买入价', '止盈价(+8%)', '止损价(-7%)', '建议持仓', '仓位建议', '模型']
        self.plan_table = create_table(headers)
        self.plan_table.cellDoubleClicked.connect(self._open_stock_detail)
        layout.addWidget(self.plan_table, stretch=1)

        return widget

    # ============================================================
    # Tab4: 历史交割单
    # ============================================================
    def _create_history_orders_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        # 筛选栏
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel('版本：'))
        self.order_version_combo = QComboBox()
        self.order_version_combo.addItems(['全部', 'V7.4.6', 'V7.4.7', 'V7.4.8'])
        self.order_version_combo.currentTextChanged.connect(self._filter_orders)
        filter_bar.addWidget(self.order_version_combo)

        filter_bar.addWidget(QLabel('等级：'))
        self.order_grade_combo = QComboBox()
        self.order_grade_combo.addItems(['全部', 'S级', 'A级', 'B级', '重点关注', '观察'])
        self.order_grade_combo.currentTextChanged.connect(self._filter_orders)
        filter_bar.addWidget(self.order_grade_combo)

        filter_bar.addWidget(QLabel('收益率：'))
        self.order_return_combo = QComboBox()
        self.order_return_combo.addItems(['全部', '盈利', '亏损'])
        self.order_return_combo.currentTextChanged.connect(self._filter_orders)
        filter_bar.addWidget(self.order_return_combo)

        filter_bar.addStretch()

        export_orders_btn = QPushButton('📥 导出CSV')
        export_orders_btn.setObjectName('secondary')
        export_orders_btn.clicked.connect(self._export_orders)
        filter_bar.addWidget(export_orders_btn)

        layout.addLayout(filter_bar)

        # 统计
        self.order_stat_label = QLabel('共0笔 | 胜率-- | 平均收益-- | 盈亏比--')
        self.order_stat_label.setStyleSheet('color: #8b949e; font-size: 11px; padding: 4px 0;')
        layout.addWidget(self.order_stat_label)

        # 表格
        headers = ['版本', '交易编号', '代码', '名称', '信号日', '买入日', '买入价', '卖出日', '卖出价', '卖出原因', '持仓天数', '收益率(%)', '收益金额']
        self.orders_table = create_table(headers)
        layout.addWidget(self.orders_table, stretch=1)

        return widget

    # ============================================================
    # Tab5: 模拟资金曲线
    # ============================================================
    def _create_nav_curve_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        # 统计卡片
        stat_grid = QGridLayout()
        self.nav_initial_label = QLabel('100,000')
        self.nav_current_label = QLabel('--')
        self.nav_total_return_label = QLabel('--')
        self.nav_annual_label = QLabel('--')
        self.nav_max_dd_label = QLabel('--')
        self.nav_win_rate_label = QLabel('--')

        cards = [
            (self.nav_initial_label, '初始资金(元)'),
            (self.nav_current_label, '当前资金(元)'),
            (self.nav_total_return_label, '总收益率'),
            (self.nav_annual_label, '年化收益率'),
            (self.nav_max_dd_label, '最大回撤'),
            (self.nav_win_rate_label, '胜率'),
        ]
        for i, (label, text) in enumerate(cards):
            box = QGroupBox()
            box_layout = QVBoxLayout(box)
            label.setObjectName('stat_value')
            box_layout.addWidget(label)
            l = QLabel(text)
            l.setObjectName('stat_label')
            box_layout.addWidget(l)
            stat_grid.addWidget(box, 0, i)

        layout.addLayout(stat_grid)

        # 时间范围选择
        range_bar = QHBoxLayout()
        range_bar.addWidget(QLabel('时间范围：'))
        self.nav_range_combo = QComboBox()
        self.nav_range_combo.addItems(['近3月', '近6月', '近1年', '近3年', '全部'])
        self.nav_range_combo.setCurrentText('全部')
        self.nav_range_combo.currentTextChanged.connect(self._update_nav_curve)
        range_bar.addWidget(self.nav_range_combo)
        range_bar.addStretch()
        layout.addLayout(range_bar)

        # 资金曲线（用文字/表格展示，避免matplotlib依赖问题）
        self.nav_text = QLabel('加载中...')
        self.nav_text.setWordWrap(True)
        self.nav_text.setStyleSheet('background: #161b22; padding: 12px; border-radius: 6px; font-family: monospace; font-size: 11px;')
        self.nav_text.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.nav_text)
        layout.addWidget(scroll, stretch=1)

        return widget

    # ============================================================
    # Tab6: 自动复盘结果
    # ============================================================
    def _create_feedback_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        # 统计栏
        fb_bar = QHBoxLayout()
        self.fb_total_label = QLabel('0')
        self.fb_total_label.setObjectName('stat_value')
        self.fb_win_rate_label = QLabel('--')
        self.fb_win_rate_label.setObjectName('stat_value')
        self.fb_avg_return_label = QLabel('--')
        self.fb_avg_return_label.setObjectName('stat_value')
        self.fb_max_dd_label = QLabel('--')
        self.fb_max_dd_label.setObjectName('stat_value')

        for label, text in [
            (self.fb_total_label, '近30天信号数'),
            (self.fb_win_rate_label, '胜率'),
            (self.fb_avg_return_label, '平均收益'),
            (self.fb_max_dd_label, '最大回撤'),
        ]:
            box = QVBoxLayout()
            box.addWidget(label)
            l = QLabel(text)
            l.setObjectName('stat_label')
            box.addWidget(l)
            fb_bar.addLayout(box)
        fb_bar.addStretch()

        update_btn = QPushButton('🔄 手动触发5日复盘')
        update_btn.clicked.connect(self._run_feedback_update)
        fb_bar.addWidget(update_btn)

        layout.addLayout(fb_bar)

        # 表格
        headers = ['信号日', '代码', '名称', '等级', '评分', '模型', '状态', '实际收益率(%)', '最大盈利(%)', '最大回撤(%)']
        self.feedback_table = create_table(headers)
        layout.addWidget(self.feedback_table, stretch=1)

        return widget

    # ============================================================
    # 数据加载
    # ============================================================
    def _load_historical_data(self):
        """加载历史数据（交割单、资金曲线、复盘）"""
        # 历史交割单
        self.all_orders = load_trade_orders()
        self._filter_orders()

        # 资金曲线
        self.nav_data = load_daily_nav()
        self._update_nav_curve()

        # 自动复盘
        self.feedback_data = load_feedback_signals()
        self._update_feedback_table()

    def _update_market_state(self):
        """更新市场状态"""
        state, desc = detect_market_state()
        color_map = {'上涨': 'market_up', '震荡': 'market_flat', '下跌': 'market_down'}
        obj_name = color_map.get(state, 'market_flat')

        self.market_label.setText(f'市场状态：{state}市')
        self.market_label.setObjectName(obj_name)
        self.market_label.setStyleSheet(self.styleSheet())

        self.plan_market_label.setText(f'市场状态：{state}市 - {desc}')
        self.plan_market_label.setObjectName(obj_name)

        position_map = {
            '上涨': '100%仓位（所有score≥50信号）',
            '震荡': '50%仓位（仅score≥50，优先A级/B级）',
            '下跌': '0%仓位（停止新增交易）',
        }
        self.plan_position_label.setText(f'仓位建议：{position_map.get(state, "--")}')

    # ============================================================
    # 扫描功能
    # ============================================================
    def _start_scan(self):
        """开始全市场扫描"""
        if self.scan_thread and self.scan_thread.isRunning():
            QMessageBox.information(self, '提示', '扫描正在进行中，请稍候...')
            return

        lookback_map = {'今日(1天)': 1, '近3天': 3, '近5天': 5, '近10天': 10}
        lookback = lookback_map.get(self.lookback_combo.currentText(), 1)

        self.scan_thread = V74ScanThread(lookback=lookback, min_grade='观察')
        self.scan_thread.progress.connect(self._on_scan_progress)
        self.scan_thread.finished_scan.connect(self._on_scan_finished)
        self.scan_thread.failed.connect(self._on_scan_failed)
        self.scan_thread.market_info.connect(self._on_market_info)  # V7.5.6

        self.scan_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText('扫描中...')

        self.scan_thread.start()

    def _cancel_scan(self):
        """取消扫描"""
        if self.scan_thread:
            self.scan_thread.cancel()
            self.status_label.setText('已取消')
        self.scan_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(False)

    def _on_scan_progress(self, done, total, found):
        """扫描进度更新"""
        if total > 0:
            pct = int(done / total * 100)
            self.progress_bar.setValue(pct)
        self.status_label.setText(f'扫描中... {done}/{total} 只，已发现 {found} 个信号')

    def _on_scan_finished(self, result):
        """扫描完成（V7.4回退：result为信号列表）"""
        # V7.4回退：result直接是信号列表
        if isinstance(result, list):
            results = result
        elif isinstance(result, dict):
            results = result.get('signals', [])
        else:
            results = []

        # 过滤非字典元素
        if not isinstance(results, list):
            results = []
        else:
            results = [r for r in results if isinstance(r, dict)]

        self.current_results = results
        self.scan_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(False)

        print(f"[V7.6-A] 扫描完成，原始信号数: {len(results)}")
        if results:
            sample = results[0]
            print(f"[V7.6-A] 第一个信号: code={sample.get('stock_code', sample.get('code'))}, "
                  f"enhanced_score={sample.get('enhanced_score')}, grade={sample.get('grade')}")
            score_ge50 = sum(1 for r in results if r.get('enhanced_score', 0) >= 50)
            score_ge60 = sum(1 for r in results if r.get('enhanced_score', 0) >= 60)
            print(f"[V7.6-A] score>=50: {score_ge50}只, score>=60: {score_ge60}只")

        # V7.4回退：简单去重（同一股票保留enhanced_score最高的一条）
        try:
            deduped = []
            seen = {}
            for r in results:
                code = r.get('stock_code') or r.get('code') or ''
                if not code:
                    continue
                if code not in seen:
                    seen[code] = len(deduped)
                    deduped.append(dict(r))
                else:
                    # 保留评分更高的
                    idx = seen[code]
                    if r.get('enhanced_score', 0) > deduped[idx].get('enhanced_score', 0):
                        deduped[idx] = dict(r)
            print(f"[V7.6-A] 去重后: {len(deduped)}只")
        except Exception as e:
            print(f"[V7.6-A] 去重失败，使用原始数据: {e}")
            deduped = results

        self.current_deduped_results = deduped

        # V7.6-A：统计（评分>=60重点关注，50-60观察）
        try:
            focus_count = sum(1 for r in deduped if r.get('enhanced_score', 0) >= 60)
            observe_count = sum(1 for r in deduped if 50 <= r.get('enhanced_score', 0) < 60)
            s_count = sum(1 for r in deduped if r.get('grade') == 'S级')
            a_count = sum(1 for r in deduped if r.get('grade') == 'A级')
            b_count = sum(1 for r in deduped if r.get('grade') == 'B级')
        except Exception:
            focus_count = observe_count = s_count = a_count = b_count = 0

        current_window = self.lookback_combo.currentText() if hasattr(self, 'lookback_combo') else '近3天'
        self.status_label.setText(
            f'[{current_window}] V7.6-A扫描完成 | 原始{len(results)}信号→去重{len(deduped)}只 '
            f'| 重点关注{focus_count}只 | 观察{observe_count}只 | S{s_count}/A{a_count}/B{b_count}'
        )

        # V8.0修复：更新UI增加异常保护
        try:
            self._update_focus_pool(deduped)
        except Exception as e:
            print(f"[V7.4回退] 更新重点关注池失败: {e}")
            import traceback
            traceback.print_exc()
        try:
            self._update_ab_signals(deduped)
        except Exception as e:
            print(f"[V7.4回退] 更新A/B级信号失败: {e}")
        try:
            self._update_trade_plan(deduped)
        except Exception as e:
            print(f"[V7.4回退] 更新买卖计划失败: {e}")

        # 切换到第一个Tab
        try:
            self.tabs.setCurrentIndex(0)
        except Exception:
            pass

    def _on_scan_failed(self, error):
        """扫描失败"""
        self.scan_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText('扫描失败')
        QMessageBox.critical(self, '扫描失败', f'扫描过程中发生错误：\n{error}')

    def _on_market_info(self, latest_date, status):
        """V7.5.6: 显示行情日期和数据状态"""
        if not latest_date:
            self.market_date_label.setText('📅 行情日期：未知')
            self.market_date_label.setStyleSheet('font-size: 11px; color: #f85149; background: #1c2128; padding: 4px 8px; border-radius: 4px;')
            return

        # 格式化日期 YYYYMMDD -> YYYY-MM-DD
        fmt_date = f'{latest_date[:4]}-{latest_date[4:6]}-{latest_date[6:8]}' if len(latest_date) == 8 else latest_date

        color_map = {
            '正常': '#3fb950',
            '轻微延迟': '#d29922',
            '过期': '#f85149',
            '未知': '#8b949e',
        }
        color = color_map.get(status, '#8b949e')
        self.market_date_label.setText(f'📅 行情日期：{fmt_date}（{status}）')
        self.market_date_label.setStyleSheet(f'font-size: 11px; color: {color}; background: #1c2128; padding: 4px 8px; border-radius: 4px;')

    # ============================================================
    # 表格更新
    # ============================================================
    def _refresh_focus_pool(self):
        """V7.5.2 显示范围筛选变化时刷新重点关注池"""
        if self.current_deduped_results:
            self._update_focus_pool(self.current_deduped_results)

    def _update_window_hint(self, text):
        """V7.5.3 切换扫描窗口时更新提示"""
        hints = {
            '今日(1天)': '💡 当前窗口：今日 | 仅显示当日新信号（强信号较少）',
            '近3天': '💡 当前窗口：近3天 | 匹配主力启动前1-3天买点模型（推荐）',
            '近5天': '💡 当前窗口：近5天 | 扩大候选范围（含有效观察信号）',
            '近10天': '💡 当前窗口：近10天 | 历史回测验证用（信号较多）',
        }
        self.window_hint_label.setText(hints.get(text, f'💡 当前窗口：{text}'))

    def _update_focus_pool(self, results):
        """更新今日重点关注池（V7.6-A：评分>=60重点关注，50-60观察）"""
        # V7.6-A：显示范围筛选
        view_mode = self.focus_view_combo.currentIndex() if hasattr(self, 'focus_view_combo') else 0
        if view_mode == 0:  # 重点关注池：score>=60
            filtered = [r for r in results if r.get('enhanced_score', 0) >= 60]
        elif view_mode == 1:  # 观察池：50<=score<60
            filtered = [r for r in results if 50 <= r.get('enhanced_score', 0) < 60]
        else:  # 全部信号
            filtered = list(results)

        # V7.6-A：按enhanced_score降序排序
        sorted_results = sorted(filtered, key=lambda x: x.get('enhanced_score', 0), reverse=True)

        rows = []
        for r in sorted_results:
            score = r.get('enhanced_score', 0)
            grade = r.get('grade', '观察')
            model = self._get_model_name(r)
            price = r.get('current_price', 0)
            buy_price = self._calc_buy_price(price)
            tp_price = round(buy_price * 1.08, 2) if buy_price else 0
            sl_price = round(buy_price * 0.93, 2) if buy_price else 0

            # V7.6-A：信号状态
            if score >= 60:
                status_text = '🟢重点关注'
            elif score >= 50:
                status_text = '🔵观察'
            else:
                status_text = '⚪过滤'

            rows.append({
                '代码': r.get('stock_code', r.get('code', '')),
                '名称': r.get('stock_name', r.get('name', '')),
                '最高评分': round(score, 1),
                '等级': grade,
                '模型': model,
                '信号状态': status_text,
                '距离信号': f"{r.get('signal_count', 1)}次",
                '建议操作': r.get('signal_action', '关注'),
                '当前价': price,
                '建议买入价': buy_price,
                '止盈价': tp_price,
                '止损价': sl_price,
                '首次信号日': r.get('first_signal_date', r.get('date', '')),
                '最新信号日': r.get('latest_signal_date', r.get('date', '')),
                '信号次数': r.get('signal_count', 1),
                '持仓天数': r.get('hold_days', 10),
            })

        # V7.4回退：原16列
        col_keys = ['代码', '名称', '最高评分', '等级', '模型', '信号状态', '距离信号', '建议操作',
                    '当前价', '建议买入价', '止盈价', '止损价', '首次信号日', '最新信号日', '信号次数', '持仓天数']
        fill_table(self.focus_table, rows, col_keys, grade_col='等级')

        # V7.4回退：更新统计
        self.focus_count_label.setText(str(len(rows)))
        if rows:
            avg_score = sum(r['最高评分'] for r in rows) / len(rows)
            self.focus_avg_score_label.setText(f'{avg_score:.1f}')
        else:
            self.focus_avg_score_label.setText('0')
        self.focus_s_label.setText(str(sum(1 for r in rows if r['等级'] == 'S级')))
        self.focus_a_label.setText(str(sum(1 for r in rows if r['等级'] == 'A级')))
        # V7.6-A：买入池/观察池统计
        self.buy_pool_label.setText(str(sum(1 for r in rows if r.get('最高评分', 0) >= 60)))
        self.watch_pool_label.setText(str(sum(1 for r in rows if 50 <= r.get('最高评分', 0) < 60)))

    def _update_ab_signals(self, results):
        """更新A/B级信号"""
        a_rows = []
        b_rows = []

        for r in results:
            grade = r.get('grade', '')
            top1 = r.get('top1_raw_trigger', False)
            top3 = r.get('top3_raw_trigger', False)
            model = self._get_model_name(r)
            score = r.get('enhanced_score', 0)
            price = r.get('current_price', 0)
            buy_price = self._calc_buy_price(price)
            buy_cond = self._get_buy_conditions(r)

            # A级：TOP1触发（突破确认型）
            is_a = (grade == 'A级') or (top1 and not top3)
            # B级：TOP3触发（提前埋伏型）
            is_b = (grade == 'B级') or (top3 and not top1)
            # S级：共振，归入A级展示
            is_s = (grade == 'S级') or (top1 and top3)

            row = {
                '代码': r.get('stock_code', ''),
                '名称': r.get('stock_name', ''),
                '等级': 'S级' if is_s else ('A级' if is_a else 'B级'),
                '模型': model,
                '评分': round(score, 1),
                '买入条件': buy_cond,
                '止盈': f'+8% ({buy_price*1.08:.2f})' if buy_price else '+8%',
                '止损': f'-7% ({buy_price*0.93:.2f})' if buy_price else '-7%',
                '当前价': price,
            }

            if is_s or is_a:
                a_rows.append(row)
            elif is_b:
                b_rows.append(row)

        # 按评分降序
        a_rows.sort(key=lambda x: x['评分'], reverse=True)
        b_rows.sort(key=lambda x: x['评分'], reverse=True)

        col_keys = ['代码', '名称', '等级', '模型', '评分', '买入条件', '止盈', '止损', '当前价']
        fill_table(self.a_table, a_rows, col_keys, grade_col='等级')
        fill_table(self.b_table, b_rows, col_keys, grade_col='等级')

        # 空状态提示（在表格第一行显示提示）
        if not a_rows:
            self.a_table.setRowCount(1)
            item = QTableWidgetItem('暂无A级/S级信号（TOP1突破确认型）')
            item.setForeground(QBrush(QColor('#8b949e')))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.a_table.setItem(0, 0, item)
            self.a_table.setSpan(0, 0, 1, 9)
        if not b_rows:
            self.b_table.setRowCount(1)
            item = QTableWidgetItem('暂无B级信号（TOP3提前埋伏型）')
            item.setForeground(QBrush(QColor('#8b949e')))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.b_table.setItem(0, 0, item)
            self.b_table.setSpan(0, 0, 1, 9)

    def _update_trade_plan(self, results):
        """更新买卖计划"""
        sorted_results = sorted(results, key=lambda x: x.get('enhanced_score', 0), reverse=True)

        state, _ = detect_market_state()
        position_map = {'上涨': '10%', '震荡': '5%（优先A/B级）', '下跌': '0%（停止）'}

        rows = []
        for r in sorted_results:
            score = r.get('enhanced_score', 0)
            grade = r.get('grade', '重点关注')
            price = r.get('current_price', 0)
            buy_price = self._calc_buy_price(price)
            # 止盈止损基于建议买入价计算
            tp_price = round(buy_price * 1.08, 2) if buy_price else 0
            sl_price = round(buy_price * 0.93, 2) if buy_price else 0

            # 仓位建议
            if state == '下跌':
                pos = '0%（停止）'
            elif grade in ('A级', 'B级', 'S级'):
                pos = position_map.get(state, '10%')
            else:
                pos = position_map.get(state, '5%')

            rows.append({
                '代码': r.get('stock_code', ''),
                '名称': r.get('stock_name', ''),
                '评分': round(score, 1),
                '等级': grade,
                '建议买入价': buy_price,
                '止盈价(+8%)': tp_price,
                '止损价(-7%)': sl_price,
                '建议持仓': '10天',
                '仓位建议': pos,
                '模型': self._get_model_name(r),
            })

        col_keys = ['代码', '名称', '评分', '等级', '建议买入价', '止盈价(+8%)', '止损价(-7%)', '建议持仓', '仓位建议', '模型']
        fill_table(self.plan_table, rows, col_keys, grade_col='等级')

    # ============================================================
    # 历史交割单
    # ============================================================
    def _filter_orders(self):
        """筛选交割单"""
        version = self.order_version_combo.currentText()
        grade = self.order_grade_combo.currentText()
        ret_filter = self.order_return_combo.currentText()

        filtered = self.all_orders[:]
        if version != '全部':
            filtered = [r for r in filtered if r.get('_version', '') == version]
        if grade != '全部':
            filtered = [r for r in filtered if r.get('grade', '') == grade]
        if ret_filter != '全部':
            def get_ret(r):
                for k in ('return_pct', '收益率', '实际收益率'):
                    if k in r and r[k]:
                        try:
                            return float(str(r[k]).replace('%', ''))
                        except Exception:
                            pass
                return 0
            if ret_filter == '盈利':
                filtered = [r for r in filtered if get_ret(r) > 0]
            elif ret_filter == '亏损':
                filtered = [r for r in filtered if get_ret(r) <= 0]

        # 填充表格
        rows = []
        for r in filtered:
            rows.append({
                '版本': r.get('_version', ''),
                '交易编号': r.get('trade_id', r.get('id', '')),
                '代码': r.get('code', r.get('stock_code', '')),
                '名称': r.get('name', r.get('stock_name', '')),
                '信号日': r.get('signal_date', r.get('signal_day', '')),
                '买入日': r.get('buy_date', ''),
                '买入价': r.get('buy_price', ''),
                '卖出日': r.get('sell_date', r.get('second_sell_date', '')),
                '卖出价': r.get('sell_price', r.get('second_sell_price', '')),
                '卖出原因': r.get('sell_reason', r.get('second_sell_reason', '')),
                '持仓天数': r.get('hold_days', ''),
                '收益率(%)': r.get('return_pct', r.get('收益率', '')),
                '收益金额': r.get('return_amount', ''),
            })

        col_keys = ['版本', '交易编号', '代码', '名称', '信号日', '买入日', '买入价', '卖出日', '卖出价', '卖出原因', '持仓天数', '收益率(%)', '收益金额']
        fill_table(self.orders_table, rows, col_keys)

        # 统计
        total = len(rows)
        if total > 0:
            wins = sum(1 for r in rows if self._get_order_return(r) > 0)
            win_rate = wins / total * 100
            avg_ret = sum(self._get_order_return(r) for r in rows) / total

            win_rets = [self._get_order_return(r) for r in rows if self._get_order_return(r) > 0]
            loss_rets = [abs(self._get_order_return(r)) for r in rows if self._get_order_return(r) <= 0]
            avg_win = sum(win_rets) / len(win_rets) if win_rets else 0
            avg_loss = sum(loss_rets) / len(loss_rets) if loss_rets else 1
            pl_ratio = avg_win / avg_loss if avg_loss > 0 else 0

            self.order_stat_label.setText(
                f'共{total}笔 | 胜率{win_rate:.1f}% | 平均收益{avg_ret:+.2f}% | 盈亏比{pl_ratio:.2f}'
            )
        else:
            self.order_stat_label.setText('共0笔 | 无数据')

    def _get_order_return(self, row):
        """获取交割单收益率"""
        for k in ('return_pct', '收益率', '收益率(%)', '实际收益率', 'return_pct(%)'):
            if k in row and row[k]:
                try:
                    return float(str(row[k]).replace('%', ''))
                except Exception:
                    pass
        return 0

    def _export_orders(self):
        """导出交割单CSV"""
        if not self.all_orders:
            QMessageBox.information(self, '提示', '没有可导出的交割单数据')
            return
        fpath, _ = QFileDialog.getSaveFileName(self, '导出交割单', 'v74_trade_orders.csv', 'CSV (*.csv)')
        if fpath:
            try:
                import csv as csv_mod
                with open(fpath, 'w', newline='', encoding='utf-8-sig') as f:
                    if self.all_orders:
                        writer = csv_mod.DictWriter(f, fieldnames=list(self.all_orders[0].keys()))
                        writer.writeheader()
                        writer.writerows(self.all_orders)
                QMessageBox.information(self, '成功', f'已导出 {len(self.all_orders)} 笔交割单到\n{fpath}')
            except Exception as e:
                QMessageBox.critical(self, '失败', f'导出失败：{e}')

    # ============================================================
    # 资金曲线
    # ============================================================
    def _update_nav_curve(self):
        """更新资金曲线展示"""
        if not self.nav_data:
            self.nav_text.setText('暂无资金曲线数据（V7.4.6_daily_nav.csv）')
            self.nav_current_label.setText('--')
            self.nav_total_return_label.setText('--')
            self.nav_annual_label.setText('--')
            self.nav_max_dd_label.setText('--')
            self.nav_win_rate_label.setText('--')
            return

        # 时间范围过滤
        range_text = self.nav_range_combo.currentText()
        days_map = {'近3月': 60, '近6月': 120, '近1年': 250, '近3年': 750, '全部': 9999}
        max_days = days_map.get(range_text, 9999)
        data = self.nav_data[-max_days:] if len(self.nav_data) > max_days else self.nav_data

        # 提取净值
        navs = []
        dates = []
        for r in data:
            for k in ('nav', 'total_nav', '净值', 'equity', '资金', 'total_value', 'account_value'):
                if k in r and r[k]:
                    try:
                        navs.append(float(r[k]))
                        dates.append(r.get('date', r.get('日期', '')))
                        break
                    except Exception:
                        pass

        if not navs:
            self.nav_text.setText('资金曲线数据格式无法识别')
            return

        initial = navs[0]
        current = navs[-1]
        total_return = (current - initial) / initial * 100

        # 年化
        days = len(navs)
        annual = ((current / initial) ** (250 / days) - 1) * 100 if days > 0 else 0

        # 最大回撤
        peak = initial
        max_dd = 0
        for n in navs:
            if n > peak:
                peak = n
            dd = (n - peak) / peak * 100
            if dd < max_dd:
                max_dd = dd

        # 更新统计卡片
        self.nav_current_label.setText(f'{current:,.0f}')
        self.nav_total_return_label.setText(f'{total_return:+.2f}%')
        self.nav_total_return_label.setStyleSheet(
            'color: #3fb950;' if total_return >= 0 else 'color: #f85149;'
        )
        self.nav_annual_label.setText(f'{annual:+.2f}%')
        self.nav_max_dd_label.setText(f'{max_dd:.2f}%')

        # 胜率（从交割单计算）
        if self.all_orders:
            wins = sum(1 for r in self.all_orders if self._get_order_return(r) > 0)
            wr = wins / len(self.all_orders) * 100
            self.nav_win_rate_label.setText(f'{wr:.1f}%')

        # 文字曲线（ASCII风格）
        text_lines = [
            f'资金曲线（{dates[0]} ~ {dates[-1]}，共{days}个交易日）',
            f'初始: {initial:,.0f}  当前: {current:,.0f}  总收益: {total_return:+.2f}%  年化: {annual:+.2f}%',
            f'最大回撤: {max_dd:.2f}%',
            '',
        ]

        # 简化曲线：每10个交易日取一个点
        step = max(1, len(navs) // 50)
        min_nav = min(navs)
        max_nav = max(navs)
        nav_range = max_nav - min_nav if max_nav > min_nav else 1

        for i in range(0, len(navs), step):
            n = navs[i]
            d = dates[i] if i < len(dates) else ''
            bar_len = int((n - min_nav) / nav_range * 40)
            bar = '█' * bar_len
            pct = (n - initial) / initial * 100
            color_mark = '📈' if pct >= 0 else '📉'
            text_lines.append(f'{d}  {n:>10,.0f}  {pct:+6.2f}%  {color_mark} {bar}')

        self.nav_text.setText('\n'.join(text_lines))

    # ============================================================
    # 自动复盘
    # ============================================================
    def _update_feedback_table(self):
        """更新自动复盘表格"""
        if not self.feedback_data:
            self.feedback_table.setRowCount(0)
            self.fb_total_label.setText('0')
            self.fb_win_rate_label.setText('--')
            self.fb_avg_return_label.setText('--')
            self.fb_max_dd_label.setText('--')
            return

        rows = []
        for r in self.feedback_data:
            rows.append({
                '信号日': str(r.get('date', r.get('signal_date', ''))),
                '代码': str(r.get('stock_code', r.get('code', ''))),
                '名称': str(r.get('stock_name', r.get('name', ''))),
                '等级': str(r.get('grade', '')),
                '评分': r.get('score', r.get('enhanced_score', '')),
                '模型': str(r.get('model_type', '')),
                '状态': r.get('status_cn', str(r.get('status', ''))),
                '实际收益率(%)': r.get('actual_return_5d', r.get('actual_return_3d', '')),
                '最大盈利(%)': r.get('max_profit', ''),
                '最大回撤(%)': r.get('max_drawdown', ''),
            })

        col_keys = ['信号日', '代码', '名称', '等级', '评分', '模型', '状态', '实际收益率(%)', '最大盈利(%)', '最大回撤(%)']
        fill_table(self.feedback_table, rows, col_keys, grade_col='等级')

        # 统计
        completed = [r for r in self.feedback_data if r.get('status') in ('已止盈', '已止损', '已到期', 'completed', 'closed')]
        self.fb_total_label.setText(str(len(self.feedback_data)))
        if completed:
            wins = sum(1 for r in completed if float(r.get('actual_return_5d', 0) or 0) > 0)
            self.fb_win_rate_label.setText(f'{wins/len(completed)*100:.1f}%')
            avg = sum(float(r.get('actual_return_5d', 0) or 0) for r in completed) / len(completed)
            self.fb_avg_return_label.setText(f'{avg:+.2f}%')
            dd_vals = [float(r.get('max_drawdown', 0) or 0) for r in completed]
            dd = min(dd_vals) if dd_vals else 0
            self.fb_max_dd_label.setText(f'{dd:.2f}%')

    def _run_feedback_update(self):
        """手动触发5日复盘"""
        self.status_label.setText('正在触发5日复盘...')
        try:
            from strategies.v74_auto_feedback import V74AutoFeedback
            fb = V74AutoFeedback()
            count = fb.update_feedback()
            self.status_label.setText(f'复盘完成，更新了 {count} 个信号')
            self.feedback_data = load_feedback_signals()
            self._update_feedback_table()
        except Exception as e:
            self.status_label.setText(f'复盘失败：{e}')
            QMessageBox.warning(self, '复盘失败', f'自动复盘触发失败：\n{e}\n\n请检查v74_auto_feedback.py和数据库。')

    # ============================================================
    # 导出买卖计划
    # ============================================================
    def _export_trade_plan(self):
        """导出买卖计划CSV"""
        if not self.current_results:
            QMessageBox.information(self, '提示', '请先运行全市场扫描，生成买卖计划后再导出')
            return

        fpath, _ = QFileDialog.getSaveFileName(self, '导出买卖计划', 'v74_trade_plan.csv', 'CSV (*.csv)')
        if not fpath:
            return

        try:
            import csv as csv_mod
            state, _ = detect_market_state()
            position_map = {'上涨': '10%', '震荡': '5%', '下跌': '0%'}

            with open(fpath, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv_mod.writer(f)
                writer.writerow(['代码', '名称', '评分', '等级', '模型', '当前价', '建议买入价', '止盈价(+8%)', '止损价(-7%)', '建议持仓', '仓位建议', '市场状态'])
                for r in sorted(self.current_results, key=lambda x: x.get('enhanced_score', 0), reverse=True):
                    price = r.get('current_price', 0)
                    writer.writerow([
                        r.get('stock_code', ''),
                        r.get('stock_name', ''),
                        round(r.get('enhanced_score', 0), 1),
                        r.get('grade', ''),
                        self._get_model_name(r),
                        price,
                        self._calc_buy_price(price),
                        round(price * 1.08, 2),
                        round(price * 0.93, 2),
                        '10天',
                        position_map.get(state, '10%'),
                        state,
                    ])
            QMessageBox.information(self, '成功', f'已导出 {len(self.current_results)} 只股票买卖计划到\n{fpath}')
        except Exception as e:
            QMessageBox.critical(self, '失败', f'导出失败：{e}')

    # ============================================================
    # 工具方法
    # ============================================================
    def _get_model_name(self, result):
        """获取模型名称（V7.6-A优先使用model字段）"""
        model = result.get('model', '')
        if model:
            return model
        top1 = result.get('top1_raw_trigger', False)
        top3 = result.get('top3_raw_trigger', False)
        if top1 and top3:
            return 'TOP1+TOP3共振'
        elif top1:
            return 'TOP1'
        elif top3:
            return 'TOP3'
        return 'V7.2综合'

    def _get_buy_conditions(self, result):
        """获取买入条件描述"""
        conds = []
        if result.get('top1_raw_trigger'):
            conds.append('多头排列+一阳穿均线')
        if result.get('top3_raw_trigger'):
            conds.append('KDJ低位+MACD修复')
        score = result.get('enhanced_score', 0)
        if score >= 80:
            conds.append('高评分启动预备')
        elif score >= 65:
            conds.append('重点关注')
        return ' + '.join(conds) if conds else '综合评分达标'

    def _calc_buy_price(self, current_price):
        """计算建议买入价（次日低吸：开盘-1%）"""
        if not current_price or current_price <= 0:
            return 0
        return round(current_price * 0.99, 2)

    def _open_stock_detail(self, row, col):
        """双击行打开专业K线图（V7.5.7复用原程序KlineContainer）"""
        table = self.sender()
        if not table:
            return
        code_item = table.item(row, 0)
        name_item = table.item(row, 1)
        if not code_item:
            return
        code = code_item.text().strip()
        name = name_item.text().strip() if name_item else code
        if not code or not code.isdigit():
            return

        try:
            from ui.professional_kline_dialog import ProfessionalKlineDialog
            dlg = ProfessionalKlineDialog(code, name, parent=self)
            dlg.exec()
        except Exception as e:
            # 降级到简易K线
            try:
                from ui.kline_viewer_dialog import KlineViewerDialog
                dlg = KlineViewerDialog(code, name, parent=self)
                dlg.exec()
            except Exception as e2:
                QMessageBox.information(
                    self, '股票详情',
                    f'代码：{code}\n名称：{name}\n\nK线组件加载失败：{e}\n{e2}'
                )


# ============================================================
# 独立运行测试
# ============================================================
if __name__ == '__main__':
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    page = V74PrecisionBuyPage()
    page.show()
    sys.exit(app.exec())
