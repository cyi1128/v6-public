# -*- coding: utf-8 -*-
"""
作战中控台 - 真实数据扫描服务
统一获取真实股票列表、K线、行情、计算全部信号标签。
所有数据来自真实接口，无模拟数据、无写死数据。
"""

import sys
import os
import time
import threading
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class RealScanService:
    """真实数据扫描服务"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._cache = {}
        self._kline_cache = {}  # K线缓存：{code: {days: kline_data}}
        self._scan_running = False
        self._scan_stop_requested = False
        self._data_source_status = {
            'stock_list': {'status': 'unknown', 'count': 0, 'last_update': None, 'error': None},
            'realtime_quote': {'status': 'unknown', 'count': 0, 'last_update': None, 'error': None},
            'kline': {'status': 'unknown', 'count': 0, 'last_update': None, 'error': None},
            'index': {'status': 'unknown', 'count': 0, 'last_update': None, 'error': None},
            'limit_up': {'status': 'unknown', 'count': 0, 'last_update': None, 'error': None},
            'sector': {'status': 'unknown', 'count': 0, 'last_update': None, 'error': None},
            'news': {'status': 'unknown', 'count': 0, 'last_update': None, 'error': None},
            'signal': {'status': 'unknown', 'count': 0, 'last_update': None, 'error': None},
        }
        self._signal_stream = []  # 实时信号流
        self._last_results = []  # 最近一次扫描结果
        self._ai_buy_signals = {}  # AI买入信号：{code: {signal_id, status, buy_price, stop_loss, take_profit1, take_profit2}}
        self._daily_cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'cache', 'daily')

    def get_data_source_status(self) -> Dict:
        """获取数据源状态"""
        return self._data_source_status.copy()

    def get_signal_stream(self) -> List[Dict]:
        """获取实时信号流"""
        return self._signal_stream[-50:].copy()

    def _add_signal_stream(self, code: str, name: str, signals: List[str], score: float = 0):
        """添加信号到实时信号流"""
        if not signals:
            return
        self._signal_stream.append({
            'time': datetime.now().strftime('%H:%M:%S'),
            'code': code,
            'name': name,
            'signals': signals,
            'score': score,
        })
        # 保留最近100条
        if len(self._signal_stream) > 100:
            self._signal_stream = self._signal_stream[-100:]

    # ============================================================
    # 1. 获取主板股票列表（排除创业板/科创板/北交所/ST）
    # ============================================================

    def get_main_board_stocks(self, max_count: int = 3000) -> List[Dict]:
        """
        获取主板股票列表（60/000/001开头），排除ST、创业板、科创板、北交所。
        返回真实股票列表，包含code、name、price、pct_chg等。
        """
        stocks = []
        try:
            from utils.tdx_stock_list import get_full_market_quotes
            all_stocks = get_full_market_quotes(main_board_only=True, exclude_st=True)
            if all_stocks:
                for s in all_stocks:
                    code = s.get('code', '')
                    name = s.get('name', '')
                    # 只保留主板
                    if not (code.startswith('60') or code.startswith('000') or code.startswith('001')):
                        continue
                    # 排除ST
                    if 'ST' in name.upper() or '*ST' in name.upper():
                        continue
                    # 排除价格为0的
                    price = s.get('price', 0)
                    if price <= 0:
                        continue
                    # V2.5全局硬过滤：价格<6.00元直接拒绝（6.00允许，5.99禁止）
                    if price < 6.00:
                        print(f"[REAL_SCAN_FILTER] REJECT PRICE_BELOW_6 code={code} price={price:.2f}", flush=True)
                        continue
                    stocks.append(s)
                    if len(stocks) >= max_count:
                        break
            self._data_source_status['stock_list'] = {
                'status': 'ok', 'count': len(stocks),
                'last_update': datetime.now().strftime('%H:%M:%S'), 'error': None
            }
        except Exception as e:
            self._data_source_status['stock_list'] = {
                'status': 'error', 'count': 0,
                'last_update': datetime.now().strftime('%H:%M:%S'), 'error': str(e)
            }
            print(f"[真实扫描] 获取股票列表失败: {e}", flush=True)
        return stocks

    # ============================================================
    # 2. 获取K线数据
    # ============================================================

    def get_kline(self, code: str, days: int = 60, use_cache: bool = True) -> List[Dict]:
        """获取真实K线数据，优先从DuckDB缓存读取，缓存不足时才在线获取（pytdx）"""
        # 检查内存缓存（V2.8.1：5分钟时效校验）
        if use_cache and code in self._kline_cache:
            cached = self._kline_cache[code]
            if time.time() - cached.get('time', 0) >= 300:
                # 缓存过期，删除后重新获取
                del self._kline_cache[code]
            elif cached.get('days', 0) >= days and cached.get('data'):
                return cached['data'][-days:]

        # 优先从DuckDB缓存读取（V2.7.1优化：避免全市场逐个在线获取导致慢和闪退）
        duckdb_bars = self._get_kline_from_duckdb(code, days)
        if duckdb_bars and len(duckdb_bars) >= min(20, days):
            # [修复] 检查最后一根是不是今天，不是今天就轻量在线拉最近5天（只拉增量，不阻塞UI）
            last_date = duckdb_bars[-1].get('date', '')
            today_str = datetime.now().strftime('%Y-%m-%d')
            if last_date >= today_str:
                self._data_source_status['kline']['status'] = 'ok'
                self._data_source_status['kline']['count'] = len(duckdb_bars)
                self._data_source_status['kline']['last_update'] = datetime.now().strftime('%H:%M:%S')
                self._kline_cache[code] = {'days': days, 'data': duckdb_bars, 'time': time.time()}
                return duckdb_bars
            # 最后一根不是今天：用实时行情拼一根今日K线（盘中日K接口不返回当天数据）
            try:
                from utils.http_market_data import get_realtime_quotes_http
                q = get_realtime_quotes_http([code]) or {}
                qd = q.get(code) or {}
                price = float(qd.get('price') or 0)
                open_px = float(qd.get('open') or 0)
                high = float(qd.get('high') or 0)
                low = float(qd.get('low') or 0)
                vol = float(qd.get('volume') or 0)
                if price > 0 and open_px > 0:
                    today_bar = {
                        'date': today_str,
                        'open': open_px,
                        'high': max(high, price, open_px),
                        'low': min(low, price, open_px),
                        'close': price,
                        'volume': vol * 100,  # 实时行情volume单位是手，DuckDB是股，×100对齐
                    }
                    merged = list(duckdb_bars)
                    # 如果历史里已有今天的（收盘后），替换；否则追加
                    if merged and merged[-1].get('date') == today_str:
                        merged[-1] = today_bar
                    else:
                        merged.append(today_bar)
                    merged = merged[-days:]
                    self._data_source_status['kline']['status'] = 'ok'
                    self._data_source_status['kline']['count'] = len(merged)
                    self._data_source_status['kline']['last_update'] = datetime.now().strftime('%H:%M:%S')
                    self._kline_cache[code] = {'days': days, 'data': merged, 'time': time.time()}
                    return merged
            except Exception as e:
                self._data_source_status['kline']['error'] = str(e)
            # 实时行情也失败，返回DuckDB旧数据（不阻塞）
            self._data_source_status['kline']['status'] = 'stale'
            self._kline_cache[code] = {'days': days, 'data': duckdb_bars, 'time': time.time()}
            return duckdb_bars

    def _get_kline_from_duckdb(self, code: str, days: int = 60) -> List[Dict]:
        """从DuckDB K线缓存读取（V2.8新增，大幅提升扫描速度）"""
        try:
            import duckdb
            import os
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'cache', 'kline_cache.duckdb')
            if not os.path.exists(db_path):
                return []
            con = duckdb.connect(db_path, read_only=False)
            rows = con.execute("""
                SELECT date, open, high, low, close, volume
                FROM kline_cache
                WHERE TRIM(code) = ?
                ORDER BY date DESC
                LIMIT ?
            """, (code, days)).fetchall()
            con.close()
            if not rows:
                return []
            bars = []
            for row in reversed(rows):
                bars.append({
                    'date': str(row[0]), 'open': float(row[1]), 'high': float(row[2]),
                    'low': float(row[3]), 'close': float(row[4]), 'volume': float(row[5]),
                })
            return bars
        except Exception as e:
            print(f"[RealScan] {code} DuckDB缓存读取失败: {e}", flush=True)
            return []

    def batch_load_kline_from_duckdb(self, codes: list, days: int = 60, min_bars: int = 20) -> dict:
        """批量从DuckDB加载K线（V2.8新增，全市场扫描预加载）"""
        if not codes:
            return {}
        try:
            import duckdb
            import os
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'cache', 'kline_cache.duckdb')
            if not os.path.exists(db_path):
                return {}
            print(f"[RealScan] 批量加载K线: {len(codes)}只股票...", flush=True)
            start = time.time()
            con = duckdb.connect(db_path, read_only=False)
            placeholders = ','.join(['?'] * len(codes))
            rows = con.execute(f"""
                SELECT TRIM(code) as code, date, open, high, low, close, volume
                FROM kline_cache
                WHERE TRIM(code) IN ({placeholders})
                ORDER BY code, date
            """, codes).fetchall()
            con.close()
            result = {}
            for row in rows:
                c = str(row[0])
                if c not in result:
                    result[c] = []
                result[c].append({
                    'date': str(row[1]), 'open': float(row[2]), 'high': float(row[3]),
                    'low': float(row[4]), 'close': float(row[5]), 'volume': float(row[6]),
                })
            filtered = {}
            for c, kline in result.items():
                if len(kline) >= min_bars:
                    filtered[c] = kline[-days:] if len(kline) > days else kline
            elapsed = time.time() - start
            print(f"[RealScan] 批量加载完成: {len(filtered)}/{len(codes)}只有效K线, 耗时{elapsed:.2f}秒", flush=True)
            for c, kline in filtered.items():
                self._kline_cache[c] = {'days': days, 'data': kline, 'time': time.time()}
            return filtered
        except Exception as e:
            print(f"[RealScan] 批量加载K线失败: {e}", flush=True)
            return {}

    def _get_kline_from_duckdb(self, code: str, days: int = 60):
        """从DuckDB K线缓存读取（单只）"""
        try:
            import duckdb
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(project_root, 'data', 'cache', 'kline_cache.duckdb')
            if not os.path.exists(db_path):
                return None
            con = duckdb.connect(db_path, read_only=False)
            rows = con.execute("""
                SELECT date, open, high, low, close, volume
                FROM kline_cache
                WHERE TRIM(code) = ?
                ORDER BY date DESC
                LIMIT ?
            """, (code, days)).fetchall()
            con.close()
            if not rows:
                return None
            kline = []
            for row in reversed(rows):
                kline.append({
                    'date': str(row[0]), 'open': float(row[1]), 'high': float(row[2]),
                    'low': float(row[3]), 'close': float(row[4]), 'volume': float(row[5]),
                })
            return kline
        except Exception:
            return None

    def batch_load_kline_from_duckdb(self, codes, days: int = 60, min_bars: int = 20):
        """批量从DuckDB加载K线（一次性查询，大幅提升扫描速度）"""
        if not codes:
            return {}
        try:
            import duckdb
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(project_root, 'data', 'cache', 'kline_cache.duckdb')
            if not os.path.exists(db_path):
                return {}
            print(f"[RealScan] 批量加载K线: {len(codes)}只股票...", flush=True)
            start = time.time()
            con = duckdb.connect(db_path, read_only=False)
            placeholders = ','.join(['?'] * len(codes))
            rows = con.execute(f"""
                SELECT TRIM(code) as code, date, open, high, low, close, volume
                FROM kline_cache
                WHERE TRIM(code) IN ({placeholders})
                ORDER BY code, date
            """, codes).fetchall()
            con.close()
            result = {}
            for row in rows:
                code = str(row[0])
                if code not in result:
                    result[code] = []
                result[code].append({
                    'date': str(row[1]), 'open': float(row[2]), 'high': float(row[3]),
                    'low': float(row[4]), 'close': float(row[5]), 'volume': float(row[6]),
                })
            filtered = {}
            for code, kline in result.items():
                if len(kline) >= min_bars:
                    filtered[code] = kline[-days:] if len(kline) > days else kline
                    self._kline_cache[code] = {'days': days, 'data': filtered[code], 'time': time.time()}
            elapsed = time.time() - start
            print(f"[RealScan] 批量加载完成: {len(filtered)}/{len(codes)}只有效K线, 耗时{elapsed:.2f}秒", flush=True)
            return filtered
        except Exception as e:
            print(f"[RealScan] 批量加载K线失败: {e}", flush=True)
            return {}

    def clear_kline_cache(self):
        """清空K线缓存"""
        self._kline_cache.clear()

    # ============================================================
    # 3. 计算全部信号标签
    # ============================================================

    def calculate_all_signals(self, code: str, name: str, kline: List[Dict],
                               realtime: Dict = None) -> Dict:
        """
        计算单只股票的全部信号标签。
        返回：{signals: [], score: float, signal_count: int, details: {}}
        """
        result = {
            'signals': [],
            'score': 0,
            'signal_count': 0,
            'details': {},
            'risk_tags': [],
        }

        if not kline or len(kline) < 20:
            return result

        try:
            import numpy as np
            import pandas as pd

            # 提取数据
            closes = [k['close'] for k in kline]
            highs = [k['high'] for k in kline]
            lows = [k['low'] for k in kline]
            opens = [k['open'] for k in kline]
            volumes = [k['volume'] for k in kline]

            current_price = closes[-1]
            prev_close = closes[-2] if len(closes) >= 2 else current_price
            today_change = (current_price - prev_close) / prev_close * 100 if prev_close > 0 else 0

            result['details']['today_change'] = today_change
            result['details']['current_price'] = current_price

            # ---- 计算均线 ----
            def ma(data, n):
                if len(data) < n:
                    return None
                return sum(data[-n:]) / n

            ma5 = ma(closes, 5)
            ma9 = ma(closes, 9)
            ma13 = ma(closes, 13)
            ma20 = ma(closes, 20)
            ma60 = ma(closes, 60) if len(closes) >= 60 else None

            result['details']['ma5'] = ma5
            result['details']['ma9'] = ma9
            result['details']['ma13'] = ma13
            result['details']['ma20'] = ma20

            prev_ma5 = ma(closes[:-1], 5) if len(closes) >= 6 else None

            # ---- MA均线信号 ----
            if ma5 and current_price >= ma5:
                result['signals'].append('站5')
                # 今日刚站5
                if prev_ma5 and closes[-2] < prev_ma5 and current_price >= ma5:
                    result['signals'].append('今日刚站5')

            if ma20 and current_price >= ma20:
                result['signals'].append('站二十')

            # MA5上穿MA20
            if ma5 and ma20 and len(closes) >= 21:
                prev_ma5_2 = ma(closes[:-1], 5)
                prev_ma20 = ma(closes[:-1], 20)
                if prev_ma5_2 and prev_ma20 and prev_ma5_2 <= prev_ma20 and ma5 > ma20:
                    result['signals'].append('MA5上穿20')

            # MA5上穿MA9（穿九）
            if ma5 and ma9 and len(closes) >= 10:
                prev_ma5_9 = ma(closes[:-1], 5)
                prev_ma9 = ma(closes[:-1], 9)
                if prev_ma5_9 and prev_ma9 and prev_ma5_9 <= prev_ma9 and ma5 > ma9:
                    result['signals'].append('穿九')

            # 一阳穿线
            if len(closes) >= 11:
                body_low = min(opens[-1], closes[-1])
                body_high = max(opens[-1], closes[-1])
                ma5_prev = ma(closes[:-1], 5)
                ma10_prev = ma(closes[:-1], 10)
                if ma5_prev and ma10_prev and body_low <= min(ma5_prev, ma10_prev) and body_high >= max(ma5_prev, ma10_prev):
                    result['signals'].append('一阳穿线')

            # 均线多头排列
            if ma5 and ma9 and ma20 and ma5 > ma9 > ma20:
                result['signals'].append('均线多头')

            # ---- KDJ信号（参数13,3,3） ----
            try:
                kdj = self._calc_kdj(highs, lows, closes, n=13, m1=3, m2=3)
                if kdj:
                    k_val, d_val, j_val = kdj
                    result['details']['kdj_k'] = k_val
                    result['details']['kdj_d'] = d_val
                    result['details']['kdj_j'] = j_val

                    if j_val < 20:
                        result['signals'].append('KDJ低位')
                    # KDJ金叉
                    if len(closes) >= 2:
                        prev_kdj = self._calc_kdj(highs[:-1], lows[:-1], closes[:-1], n=13, m1=3, m2=3)
                        if prev_kdj:
                            prev_k, prev_d, prev_j = prev_kdj
                            if prev_k <= prev_d and k_val > d_val:
                                result['signals'].append('KDJ金叉')
                            if j_val < 20 and k_val > d_val:
                                result['signals'].append('KDJ启动')
            except Exception:
                pass

            # ---- 成交量信号 ----
            if len(volumes) >= 6:
                vol_ma5 = sum(volumes[-6:-1]) / 5
                if vol_ma5 > 0:
                    vol_ratio = volumes[-1] / vol_ma5
                    result['details']['vol_ratio'] = vol_ratio
                    if 1.2 <= vol_ratio <= 2.5:
                        result['signals'].append('温和放量')
                    # 三红温和放量
                    if len(closes) >= 4:
                        red_count = sum(1 for i in range(-4, -1) if closes[i] > opens[i])
                        if red_count >= 2 and vol_ratio >= 1.2:
                            result['signals'].append('量价启动')

                # 缩量承接
                if len(volumes) >= 6:
                    recent_vol = volumes[-1]
                    prev_vol = sum(volumes[-4:-1]) / 3
                    if prev_vol > 0 and recent_vol < prev_vol * 0.8 and current_price >= ma5 * 0.98 if ma5 else True:
                        result['signals'].append('缩量承接')

            # ---- 横盘筑底信号 ----
            if len(closes) >= 8:
                recent_8 = closes[-8:]
                price_range = (max(recent_8) - min(recent_8)) / min(recent_8) * 100 if min(recent_8) > 0 else 100
                if price_range <= 8 and ma20 and abs(current_price - ma20) / ma20 < 0.05:
                    result['signals'].append('横盘筑底')

            # ---- 20日涨停记忆信号 ----
            try:
                from strategy.limit_up_radar import find_limit_up_in_20d, is_one_word_board
                lu_info = find_limit_up_in_20d(kline)
                if lu_info and lu_info.get('has_limit_up', False):
                    result['signals'].append('20日涨停记忆')
                    result['details']['last_limit_date'] = lu_info.get('last_limit_date', '')
                    result['details']['limit_count_20d'] = lu_info.get('limit_up_count', 0)

                    # 涨停回调
                    days_after = lu_info.get('days_after_limit', 0)
                    post_high = lu_info.get('post_limit_high', 0)
                    if days_after >= 2 and post_high > 0:
                        pullback = (post_high - current_price) / post_high * 100
                        result['details']['pullback_pct'] = pullback
                        if pullback >= 3:
                            result['signals'].append('涨停回调')
                        # 回调后启动
                        if pullback >= 3 and ma5 and current_price >= ma5 and 0.3 <= today_change <= 7:
                            result['signals'].append('回调后启动')
            except Exception:
                pass

            # ---- 回踩20日线信号 ----
            if ma20 and len(closes) >= 8:
                # 近7天内接触MA20
                touched_ma20 = False
                for i in range(-7, 0):
                    if abs(closes[i] - ma20) / ma20 <= 0.02:
                        touched_ma20 = True
                        break
                if touched_ma20 and ma5 and ma9 and ma5 > ma9 > ma20 and current_price >= ma5 * 0.98:
                    result['signals'].append('回踩20日线')
                    result['signals'].append('重新启动')

            # ---- 核心：回踩信号（贴线/穿线/冲高回落） ----
            try:
                high_1 = highs[-1] if len(highs) >= 1 else current_price
                low_1 = lows[-1] if len(lows) >= 1 else current_price
                open_1 = opens[-1] if len(opens) >= 1 else current_price
                # 均线多头排列：MA5 > MA13 > MA20
                ma13 = ma(closes, 13) if len(closes) >= 13 else None
                bullish_alignment = bool(ma5 and ma13 and ma20 and ma5 > ma13 > ma20)
                # 贴近均线（±2%，误差小）
                near_ma5 = bool(ma5) and abs(current_price - ma5) / ma5 <= 0.02
                near_ma13 = bool(ma13) and abs(current_price - ma13) / ma13 <= 0.02
                near_ma20 = bool(ma20) and abs(current_price - ma20) / ma20 <= 0.02
                above_ma5 = bool(ma5) and current_price >= ma5
                above_ma13 = bool(ma13) and current_price >= ma13
                above_ma20 = bool(ma20) and current_price >= ma20
                # 一阳穿MA5+MA20（阳线实体同时穿越昨两条均线）
                one_yang_cross520 = False
                if closes[-1] >= open_1 and len(closes) >= 21:
                    body_low = min(open_1, closes[-1])
                    body_high = max(open_1, closes[-1])
                    p_ma5 = ma(closes[:-1], 5)
                    p_ma20 = ma(closes[:-1], 20)
                    if p_ma5 and p_ma20:
                        if body_low <= min(p_ma5, p_ma20) and body_high >= max(p_ma5, p_ma20):
                            one_yang_cross520 = True
                # 放量冲高回落：上影线占比>=30%，收盘在当日下1/2区域
                high_fall = False
                total_range = high_1 - low_1
                if total_range > 0:
                    upper_shadow = high_1 - max(open_1, closes[-1])
                    upper_ratio = upper_shadow / total_range
                    close_pos = (closes[-1] - low_1) / total_range
                    if upper_ratio >= 0.3 and close_pos <= 0.6:
                        high_fall = True
                vol_ratio = result['details'].get('vol_ratio', 1.0)
                is_pullback = False
                pullback_type = ''
                if ma5 and ma13 and ma20 and bullish_alignment:
                    # A: 多头排列下贴MA5 + 放量冲高回落（缩量回踩企稳）
                    if near_ma5 and high_fall:
                        is_pullback = True; pullback_type = '贴MA5缩量回踩'
                    # B: 一阳穿两线且站上（多头排列下）
                    if one_yang_cross520 and above_ma5 and above_ma20:
                        is_pullback = True; pullback_type = '一阳穿线'
                    # C: 多头排列下贴MA5 + 站MA13/MA20上
                    if near_ma5 and above_ma13 and above_ma20:
                        is_pullback = True; pullback_type = '回踩MA5确认'
                    # D: 贴MA13（多头排列）
                    if near_ma13 and above_ma20:
                        is_pullback = True; pullback_type = '回踩MA13'
                    # E: 贴MA20（多头排列，更安全的回踩）
                    if near_ma20 and above_ma13:
                        is_pullback = True; pullback_type = '回踩MA20'
                if is_pullback:
                    result['signals'].append('回踩')
                    result['details']['pullback_type'] = pullback_type
            except Exception:
                pass

            # ---- 今日涨幅范围 ----
            result['details']['today_change'] = today_change
            if 0.3 <= today_change <= 3:
                result['signals'].append('涨幅适中')
            elif 3 < today_change <= 5:
                result['signals'].append('涨幅正常')
            elif 5 < today_change <= 7:
                result['signals'].append('涨幅偏高')
                result['risk_tags'].append('追高风险')
            elif today_change > 7:
                result['risk_tags'].append('追高风险')

            # ---- 25日涨幅风险 ----
            if len(closes) >= 26:
                change_25d = (closes[-1] - closes[-26]) / closes[-26] * 100 if closes[-26] > 0 else 0
                result['details']['change_25d'] = change_25d
                if change_25d >= 22:
                    result['risk_tags'].append('25日涨幅过高')
                elif change_25d >= 15:
                    result['risk_tags'].append('25日涨幅偏高')

            # ---- 追高拦截器 ----
            # 1. MA5乖离率过大
            if ma5 and ma5 > 0:
                bias_ma5 = (current_price - ma5) / ma5 * 100
                result['details']['bias_ma5'] = bias_ma5
                if bias_ma5 > 8:
                    result['risk_tags'].append('乖离过大')
                elif bias_ma5 > 5:
                    result['risk_tags'].append('乖离偏高')

            # 2. 连续大阳（近3天涨幅累计>15%）
            if len(closes) >= 4:
                recent_3d_change = (closes[-1] - closes[-4]) / closes[-4] * 100 if closes[-4] > 0 else 0
                result['details']['recent_3d_change'] = recent_3d_change
                if recent_3d_change > 15:
                    result['risk_tags'].append('连续大涨')

            # 3. 距离近期高点过近（5日高点）
            if len(highs) >= 5:
                high_5d = max(highs[-5:])
                if high_5d > 0:
                    dist_from_high = (high_5d - current_price) / high_5d * 100
                    result['details']['dist_from_high'] = dist_from_high
                    if dist_from_high < 1:
                        result['risk_tags'].append('接近高点')

            # 4. 低位启动加分（价格在MA20附近，25日涨幅<10%）
            is_low_position = False
            if ma20 and ma20 > 0:
                dist_ma20 = abs(current_price - ma20) / ma20 * 100
                change_25d = result['details'].get('change_25d', 0)
                if dist_ma20 < 8 and change_25d < 10:
                    is_low_position = True
                    result['signals'].append('低位启动')
            result['details']['is_low_position'] = is_low_position

            # ---- 板块/概念 ----
            try:
                from service.concept_service import get_stock_concepts, get_stock_industry_f10
                concepts, _ = get_stock_concepts(code)
                industry = get_stock_industry_f10(code)
                if concepts:
                    result['details']['concepts'] = concepts[:3]
                    result['details']['main_concept'] = concepts[0] if concepts else ''
                if industry:
                    result['details']['industry'] = industry
                # 板块共振（简化：有概念且个股上涨）
                if concepts and today_change > 0:
                    result['signals'].append('板块共振')
            except Exception:
                pass

            # ---- 计算综合评分 ----
            score = self._calculate_score(result['signals'], result['details'], result['risk_tags'])
            result['score'] = score
            result['signal_count'] = len(result['signals'])

            # 添加到实时信号流（只添加有核心信号的）
            core_signals = [s for s in result['signals'] if s in
                             ['回调后启动', '今日启动', '20日涨停记忆', '回踩20日线', '重新启动',
                              '一阳穿线', 'KDJ启动', '量价启动', '板块共振', '均线多头']]
            if core_signals and score >= 50:
                self._add_signal_stream(code, name, core_signals, score)

            self._data_source_status['signal']['status'] = 'ok'
            self._data_source_status['signal']['count'] += 1
            self._data_source_status['signal']['last_update'] = datetime.now().strftime('%H:%M:%S')

        except Exception as e:
            print(f"[真实扫描] 计算信号失败 {code}: {e}", flush=True)

        return result

    def _calc_kdj(self, highs, lows, closes, n=13, m1=3, m2=3):
        """计算KDJ（参数13,3,3）"""
        if len(closes) < n:
            return None
        try:
            import numpy as np
            low_list = [min(lows[max(0, i-n+1):i+1]) for i in range(len(closes))]
            high_list = [max(highs[max(0, i-n+1):i+1]) for i in range(len(closes))]
            rsv = [(closes[i] - low_list[i]) / (high_list[i] - low_list[i]) * 100
                   if high_list[i] > low_list[i] else 50 for i in range(len(closes))]
            k = rsv[0]
            d = rsv[0]
            for i in range(1, len(rsv)):
                k = (m1 - 1) / m1 * k + 1 / m1 * rsv[i]
                d = (m2 - 1) / m2 * d + 1 / m2 * k
            j = 3 * k - 2 * d
            return (k, d, j)
        except Exception:
            return None

    def _calculate_score(self, signals: List[str], details: Dict, risk_tags: List[str]) -> float:
        """计算综合评分（0-100），低位启动优先，追高风险重扣"""
        score = 0
        # 基础分：每个信号2分
        score += len(signals) * 2
        # 核心信号加分（低位启动类权重更高）
        core_signal_scores = {
            '回调后启动': 15, '今日启动': 12, '20日涨停记忆': 12,
            '回踩': 15, '回踩20日线': 12, '重新启动': 10, '低位启动': 10,
            '一阳穿线': 10, 'KDJ启动': 8, 'KDJ金叉': 6,
            '量价启动': 8, '板块共振': 8, '均线多头': 6,
            '站5': 3, '穿九': 5, '站二十': 4, 'MA5上穿20': 8,
            '温和放量': 4, '缩量承接': 4, '横盘筑底': 6,
            '涨停回调': 8, 'KDJ低位': 5,
        }
        for sig in signals:
            score += core_signal_scores.get(sig, 2)

        # 低位启动组合加分（20日涨停记忆+回调+低位+站5）
        if '20日涨停记忆' in signals and '涨停回调' in signals and '低位启动' in signals:
            score += 10
        if '回踩20日线' in signals and '重新启动' in signals and '低位启动' in signals:
            score += 8

        # 今日涨幅适中加分（低涨幅优先）
        today_change = details.get('today_change', 0)
        if 0.3 <= today_change <= 2:
            score += 10  # 最优低涨幅
        elif 2 < today_change <= 3:
            score += 8
        elif 3 < today_change <= 5:
            score += 5

        # 风险扣分（追高重扣）
        risk_penalties = {
            '追高风险': 15, '25日涨幅过高': 20, '25日涨幅偏高': 8,
            '乖离过大': 12, '乖离偏高': 6, '连续大涨': 15,
            '接近高点': 8, '涨幅偏高': 5,
        }
        for risk in risk_tags:
            score -= risk_penalties.get(risk, 5)

        # 25日涨幅>=22直接降到50以下（高位风险）
        if details.get('change_25d', 0) >= 22:
            score = min(score, 45)

        return max(0, min(100, score))

    # ============================================================
    # 4. 批量扫描（获取真实候选股票）
    # ============================================================

    def scan_main_board(self, max_stocks: int = 0, min_score: int = 40,
                         progress_callback=None, use_cache: bool = True) -> Dict:
        """
        批量扫描主板股票，返回真实候选结果。
        max_stocks=0表示全市场扫描。
        progress_callback: 回调函数(current, total, candidates_count, s_count, a_count, b_count)
        """
        result = {
            'stocks': [],
            'total_scanned': 0,
            'filter_stats': {
                'total': 0, 'non_main_board': 0, 'st': 0, 'no_price': 0,
                'no_kline': 0, 'no_signal': 0, 'below_min_score': 0, 'final': 0,
                'kline_failed': 0, 'signal_failed': 0,
            }
        }

        self._scan_running = True
        self._scan_stop_requested = False

        # V2.8.1：扫描前强制全量刷新K线（解决昨日数据选股问题）
        try:
            print(f"[RealScan] 扫描前强制刷新K线数据（最多等待120秒）...", flush=True)
            refresh_start = time.time()
            refresh_result = [None]
            refresh_error = [None]

            def _do_refresh():
                try:
                    from services.kline_cache_service import incremental_update_kline
                    refresh_result[0] = incremental_update_kline(verbose=True)
                except Exception as e:
                    refresh_error[0] = e

            refresh_thread = threading.Thread(target=_do_refresh, daemon=True)
            refresh_thread.start()
            refresh_thread.join(timeout=120)

            if refresh_thread.is_alive():
                print(f"[RealScan] WARNING K线刷新超时（>120秒），降级使用缓存数据继续扫描", flush=True)
            elif refresh_error[0]:
                print(f"[RealScan] WARNING K线刷新失败（非交易时间等），降级使用缓存: {refresh_error[0]}", flush=True)
            elif refresh_result[0]:
                r = refresh_result[0]
                print(f"[RealScan] OK K线刷新完成: 更新{r.get('updated',0)}只, 新增K线{r.get('new_kline_total',0)}根, 失败{r.get('failed',0)}只, 耗时{time.time()-refresh_start:.1f}秒", flush=True)

            # 清空内存缓存，确保后续读取最新DuckDB数据
            self._kline_cache.clear()
            print(f"[RealScan] 内存K线缓存已清空", flush=True)
        except Exception as e:
            print(f"[RealScan] WARNING 扫描前K线刷新异常（不阻断扫描）: {e}", flush=True)

        try:
            # 获取股票列表（全市场或指定数量）
            max_count = max_stocks if max_stocks > 0 else 5000
            stocks = self.get_main_board_stocks(max_count=max_count)
            result['filter_stats']['total'] = len(stocks)
            result['total_scanned'] = len(stocks)

            # V2.7.1优化：批量从DuckDB预加载K线，避免逐个在线获取导致慢和闪退
            if use_cache and stocks:
                codes = [s.get('code', '') for s in stocks if s.get('code')]
                self.batch_load_kline_from_duckdb(codes, days=60, min_bars=20)

            candidates = []
            s_count = a_count = b_count = c_count = 0

            # V2.7.1优化：批量预加载DuckDB K线缓存（避免逐只在线获取导致扫描慢/闪退）
            if use_cache and stocks:
                codes = [s.get('code', '') for s in stocks if s.get('code')]
                self.batch_load_kline_from_duckdb(codes, days=60, min_bars=20)

            for i, stock in enumerate(stocks):
                # 检查停止
                if self._scan_stop_requested:
                    print(f"[真实扫描] 用户停止，已扫描 {i+1}/{len(stocks)}", flush=True)
                    break

                code = stock.get('code', '')
                name = stock.get('name', '')
                if not code:
                    continue

                try:
                    # 获取K线（使用缓存）
                    kline = self.get_kline(code, days=60, use_cache=use_cache)
                    if not kline or len(kline) < 20:
                        result['filter_stats']['no_kline'] += 1
                        result['filter_stats']['kline_failed'] += 1
                        continue

                    # 计算信号
                    signal_result = self.calculate_all_signals(code, name, kline, stock)
                    if not signal_result['signals']:
                        result['filter_stats']['no_signal'] += 1
                        continue

                    if signal_result['score'] < min_score:
                        result['filter_stats']['below_min_score'] += 1
                        continue

                    # 合并数据
                    stock.update(signal_result)
                    stock['signal_count'] = signal_result['signal_count']
                    stock['score'] = signal_result['score']
                    candidates.append(stock)

                    # 统计等级
                    score = signal_result['score']
                    if score >= 80:
                        s_count += 1
                    elif score >= 70:
                        a_count += 1
                    elif score >= 60:
                        b_count += 1
                    else:
                        c_count += 1

                except Exception as e:
                    result['filter_stats']['signal_failed'] += 1
                    print(f"[真实扫描] {code} 处理失败: {e}", flush=True)
                    continue

                # 进度回调
                if progress_callback and (i + 1) % 5 == 0:
                    try:
                        progress_callback(i + 1, len(stocks), len(candidates),
                                        s_count, a_count, b_count)
                    except Exception:
                        pass

                # 每50只输出一次进度
                if (i + 1) % 50 == 0:
                    print(f"[真实扫描] 已扫描 {i+1}/{len(stocks)}，候选 {len(candidates)} "
                          f"(S:{s_count} A:{a_count} B:{b_count})", flush=True)

            # 按评分排序
            candidates.sort(key=lambda x: x.get('score', 0), reverse=True)
            result['stocks'] = candidates
            result['filter_stats']['final'] = len(candidates)
            result['s_count'] = s_count
            result['a_count'] = a_count
            result['b_count'] = b_count
            result['c_count'] = c_count

            print(f"[真实扫描] 完成：扫描{len(stocks)}只，候选{len(candidates)}只 "
                  f"(S:{s_count} A:{a_count} B:{b_count} C:{c_count})", flush=True)

            # 保存最后结果
            self._last_results = candidates.copy()

        finally:
            self._scan_running = False

        return result

    def stop_scan(self):
        """请求停止扫描"""
        self._scan_stop_requested = True

    def is_scan_running(self) -> bool:
        """扫描是否正在运行"""
        return self._scan_running

    # ============================================================
    # 5. 获取市场概况
    # ============================================================

    def get_market_overview(self) -> Dict:
        """获取真实市场概况"""
        result = {
            'sh_index': 0, 'sh_pct': 0, 'sz_index': 0, 'sz_pct': 0,
            'cyb_index': 0, 'cyb_pct': 0, 'total_amount': 0,
            'limit_up_count': 0, 'limit_down_count': 0, 'max_consecutive': 0,
            'market_sentiment': 50,
        }
        try:
            from utils.tdx_stock_list import get_tdx_api
            api = get_tdx_api()
            if api:
                quotes = api.get_security_quotes([
                    (1, '000001'), (0, '399001'), (0, '399006')
                ])
                if quotes:
                    for q in quotes:
                        code = q.get('code', '')
                        price = q.get('price', 0)
                        last_close = q.get('last_close', 0)
                        pct = (price - last_close) / last_close * 100 if last_close > 0 else 0
                        amount = q.get('amount', 0)
                        if code == '000001':
                            result['sh_index'] = price
                            result['sh_pct'] = pct
                        elif code == '399001':
                            result['sz_index'] = price
                            result['sz_pct'] = pct
                        elif code == '399006':
                            result['cyb_index'] = price
                            result['cyb_pct'] = pct
                        result['total_amount'] += amount / 100000000
            self._data_source_status['index']['status'] = 'ok'
            self._data_source_status['index']['last_update'] = datetime.now().strftime('%H:%M:%S')
        except Exception as e:
            self._data_source_status['index']['status'] = 'error'
            self._data_source_status['index']['error'] = str(e)

        try:
            from data.limit_up_data_provider import get_limit_up_data_provider
            provider = get_limit_up_data_provider()
            lu_data = provider.get_limit_up_data()
            if lu_data and isinstance(lu_data, list):
                result['limit_up_count'] = len(lu_data)
                max_consec = 0
                for item in lu_data:
                    consec = item.get('consecutive_count', item.get('lianban', 1))
                    if consec > max_consec:
                        max_consec = consec
                result['max_consecutive'] = max_consec
            self._data_source_status['limit_up']['status'] = 'ok'
            self._data_source_status['limit_up']['count'] = result['limit_up_count']
            self._data_source_status['limit_up']['last_update'] = datetime.now().strftime('%H:%M:%S')
        except Exception as e:
            self._data_source_status['limit_up']['status'] = 'error'
            self._data_source_status['limit_up']['error'] = str(e)

        # 市场情绪
        if result['limit_up_count'] > 0:
            result['market_sentiment'] = min(100, int(40 + result['limit_up_count'] * 0.5 + result['max_consecutive'] * 3))

        return result

    def get_last_results(self) -> List[Dict]:
        """获取最近一次扫描结果"""
        return self._last_results.copy()

    def calculate_ai_entry_score(self, stock: Dict) -> Dict:
        """
        AI二次筛选评分（AIEntryScore 0-100）
        重点寻找主力启动前1-3天低风险买点
        """
        signals = stock.get('signals', [])
        details = stock.get('details', {})
        risk_tags = stock.get('risk_tags', [])
        score = 0
        ai_signals = []

        # 1. 板块指数共振 20分（简化：用板块共振信号代理）
        if '板块共振' in signals:
            score += 20; ai_signals.append('板块共振')
        elif details.get('industry'):
            score += 5

        # 2. 量价结构 20分
        if '量价启动' in signals:
            score += 20; ai_signals.append('量价启动')
        elif '温和放量' in signals:
            score += 12; ai_signals.append('温和放量')
        elif '缩量承接' in signals:
            score += 8; ai_signals.append('缩量承接')

        # 3. 低位启动 15分
        if '低位启动' in signals:
            score += 15; ai_signals.append('低位启动')
        elif details.get('change_25d', 0) < 10 and details.get('bias_ma5', 0) < 3:
            score += 8

        # 4. 回踩20日线 10分
        if '回踩20日线' in signals:
            score += 10; ai_signals.append('回踩20日线')

        # 5. 重新站MA5 10分
        if '今日启动' in signals or '回调后启动' in signals:
            score += 10; ai_signals.append('重新站MA5')
        elif '站5' in signals:
            score += 5

        # 6. 20日涨停记忆 8分
        if '20日涨停记忆' in signals:
            score += 8; ai_signals.append('涨停记忆')

        # 7. KDJ启动 7分
        if 'KDJ启动' in signals or 'KDJ金叉' in signals:
            score += 7; ai_signals.append('KDJ启动')
        elif 'KDJ低位' in signals:
            score += 4

        # 8. 温和放量 5分（已在量价结构中，这里不重复）
        # 9. 市场环境 5分（简化）
        score += 3

        # 追高风险扣分
        if '追高风险' in risk_tags:
            score -= 15
        if '乖离过大' in risk_tags:
            score -= 12
        if '连续大涨' in risk_tags:
            score -= 15
        if any('25日' in r for r in risk_tags):
            score -= 10
            if score > 45: score = 45  # 25日涨幅过高直接降到45以下

        # 剔除连板股（连续涨停风险）
        is_consecutive = False
        if details.get('consecutive_limit_up', 0) >= 2:
            is_consecutive = True
            score -= 20

        score = max(0, min(100, int(score)))

        # 等级
        if score >= 90: grade = 'S+'
        elif score >= 85: grade = 'S'
        elif score >= 80: grade = 'A'
        elif score >= 70: grade = 'B'
        elif score >= 60: grade = '观察'
        else: grade = '淘汰'

        # 买卖点计算
        buy_sell = self.calculate_buy_sell_points(stock)

        return {
            'ai_score': score,
            'ai_grade': grade,
            'ai_signals': ai_signals,
            'is_consecutive': is_consecutive,
            'buy_price': buy_sell['buy_price'],
            'buy_low': buy_sell['buy_low'],
            'buy_high': buy_sell['buy_high'],
            'stop_loss': buy_sell['stop_loss'],
            'take_profit1': buy_sell['take_profit1'],
            'take_profit2': buy_sell['take_profit2'],
            'current_price': buy_sell['current_price'],
            'deviation': buy_sell['deviation'],
        }

    def calculate_buy_sell_points(self, stock: Dict) -> Dict:
        """计算买卖点（基于真实行情和均线）"""
        details = stock.get('details', {})
        price = stock.get('price', stock.get('current_price', 0))
        ma5 = details.get('ma5', 0)
        ma13 = details.get('ma13', 0)
        ma20 = details.get('ma20', 0)
        high_5d = details.get('high_5d', 0)
        low_5d = details.get('low_5d', 0)

        if price <= 0:
            return {'buy_price': 0, 'buy_low': 0, 'buy_high': 0, 'stop_loss': 0,
                    'take_profit1': 0, 'take_profit2': 0, 'current_price': 0, 'deviation': 0}

        # 建议买入价：MA5附近
        buy_price = ma5 if ma5 > 0 else price
        buy_low = min(price, ma5) * 0.99 if ma5 > 0 else price * 0.99
        buy_high = max(price, ma5) * 1.01 if ma5 > 0 else price * 1.01

        # 止损：MA20下方2% 或 买入价-5%
        if ma20 > 0:
            stop_loss = min(ma20 * 0.98, buy_price * 0.95)
        else:
            stop_loss = buy_price * 0.95

        # 止盈1：买入价+5%
        take_profit1 = buy_price * 1.05
        # 止盈2：5日高点 或 买入价+10%
        take_profit2 = max(high_5d, buy_price * 1.10) if high_5d > 0 else buy_price * 1.10

        # 当前偏离买入区
        deviation = ((price - buy_price) / buy_price * 100) if buy_price > 0 else 0

        return {
            'buy_price': round(buy_price, 2),
            'buy_low': round(buy_low, 2),
            'buy_high': round(buy_high, 2),
            'stop_loss': round(stop_loss, 2),
            'take_profit1': round(take_profit1, 2),
            'take_profit2': round(take_profit2, 2),
            'current_price': round(price, 2),
            'deviation': round(deviation, 2),
        }

    def ai_secondary_filter(self, stocks: List[Dict], min_ai_score: int = 60) -> List[Dict]:
        """AI二次筛选：从初筛结果中筛选真正符合买点结构的股票"""
        result = []
        for stock in stocks:
            try:
                ai_result = self.calculate_ai_entry_score(stock)
                if ai_result['ai_score'] >= min_ai_score:
                    stock['ai_score'] = ai_result['ai_score']
                    stock['ai_grade'] = ai_result['ai_grade']
                    stock['ai_signals'] = ai_result['ai_signals']
                    stock['buy_price'] = ai_result['buy_price']
                    stock['buy_low'] = ai_result['buy_low']
                    stock['buy_high'] = ai_result['buy_high']
                    stock['stop_loss'] = ai_result['stop_loss']
                    stock['take_profit1'] = ai_result['take_profit1']
                    stock['take_profit2'] = ai_result['take_profit2']
                    stock['deviation'] = ai_result['deviation']
                    result.append(stock)
            except Exception as e:
                print(f"[AI筛选] {stock.get('code','')} 计算失败: {e}", flush=True)
        # 按AI评分排序
        result.sort(key=lambda x: x.get('ai_score', 0), reverse=True)
        return result

    def save_daily_cache(self, scan_result: Dict = None):
        """日终缓存：保存当天扫描结果"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            cache_dir = os.path.join(self._daily_cache_dir, today)
            os.makedirs(cache_dir, exist_ok=True)

            import json
            # 保存扫描结果
            if scan_result:
                with open(os.path.join(cache_dir, 'stocks.json'), 'w', encoding='utf-8') as f:
                    json.dump(scan_result, f, ensure_ascii=False, default=str)
            # 保存最后结果
            if self._last_results:
                with open(os.path.join(cache_dir, 'ai_results.json'), 'w', encoding='utf-8') as f:
                    json.dump(self._last_results, f, ensure_ascii=False, default=str)
            # 保存信号流
            with open(os.path.join(cache_dir, 'signals.json'), 'w', encoding='utf-8') as f:
                json.dump(self._signal_stream, f, ensure_ascii=False, default=str)
            # 保存元数据
            meta = {'date': today, 'saved_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'total_stocks': len(self._last_results), 'is_live': False}
            with open(os.path.join(cache_dir, 'meta.json'), 'w', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False)
            print(f"[日终缓存] 已保存到 {cache_dir}", flush=True)
            return True
        except Exception as e:
            print(f"[日终缓存] 保存失败: {e}", flush=True)
            return False

    def load_daily_cache(self, date_str: str = None) -> Dict:
        """加载日终缓存"""
        try:
            if not date_str:
                # 找最近的缓存日期
                if not os.path.exists(self._daily_cache_dir):
                    return None
                dates = sorted([d for d in os.listdir(self._daily_cache_dir) if os.path.isdir(os.path.join(self._daily_cache_dir, d))], reverse=True)
                if not dates:
                    return None
                date_str = dates[0]

            cache_dir = os.path.join(self._daily_cache_dir, date_str)
            if not os.path.exists(cache_dir):
                return None

            import json
            result = {'date': date_str, 'stocks': [], 'signals': [], 'meta': {}}

            ai_file = os.path.join(cache_dir, 'ai_results.json')
            if os.path.exists(ai_file):
                with open(ai_file, 'r', encoding='utf-8') as f:
                    result['stocks'] = json.load(f)

            sig_file = os.path.join(cache_dir, 'signals.json')
            if os.path.exists(sig_file):
                with open(sig_file, 'r', encoding='utf-8') as f:
                    result['signals'] = json.load(f)

            meta_file = os.path.join(cache_dir, 'meta.json')
            if os.path.exists(meta_file):
                with open(meta_file, 'r', encoding='utf-8') as f:
                    result['meta'] = json.load(f)

            print(f"[日终缓存] 已加载 {date_str}: {len(result['stocks'])}只股票", flush=True)
            return result
        except Exception as e:
            print(f"[日终缓存] 加载失败: {e}", flush=True)
            return None


def get_real_scan_service() -> RealScanService:
    """获取真实扫描服务单例"""
    return RealScanService()
