# -*- coding: utf-8 -*-
"""
AI-520动态选股雷达扫描服务
09:30/14:45自动扫描 + 企业微信推送 + 7日观察池
"""
import os
import sys
import time
import json
import threading
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from strategy.ai_520_engine import AI520Engine
from strategy.ai_520_database import AI520Database
from strategy.ai520_pullback_mode import AI520PullbackMode
from strategy.ai520_strategy import AI520Strategy
from services.realtime_quote_refresh import refresh_signal_quotes
from services.concept_matcher import batch_match_concepts  # V2.7.2：概念匹配


class AI520ScanService:
    """AI-520扫描服务"""

    def __init__(self):
        self.engine = AI520Engine()
        self.pullback_mode = AI520PullbackMode()
        self.db = AI520Database()
        self.ai520_strategy = AI520Strategy()  # V2.7.2：唯一AI520核心策略实例
        self._kline_cache = {}  # 内存缓存：code -> kline list
        self._lock = threading.Lock()

    def load_env_webhook(self) -> Optional[str]:
        """从.env加载企业微信Webhook"""
        env_path = os.path.join(PROJECT_ROOT, '.env')
        if not os.path.exists(env_path):
            return None
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('WECHAT_WORK_WEBHOOK=') or line.startswith('WECHAT_WEBHOOK_URL='):
                        return line.split('=', 1)[1].strip()
        except Exception:
            pass
        return None

    def send_wechat_message(self, content: str) -> Tuple[bool, str]:
        """发送企业微信消息"""
        webhook = self.load_env_webhook()
        if not webhook:
            return False, 'Webhook未配置'

        try:
            import requests
            payload = {
                "msgtype": "markdown",
                "markdown": {"content": content}
            }
            resp = requests.post(webhook, json=payload, timeout=10)
            result = resp.json()
            if result.get('errcode') == 0:
                return True, '发送成功'
            else:
                return False, f"企业微信返回错误: {result.get('errmsg', '未知错误')}"
        except Exception as e:
            return False, f"发送异常: {str(e)}"

    def get_kline(self, code: str, days: int = 200) -> Optional[List[Dict]]:
        """获取K线（带缓存，5分钟时效校验）"""
        cache_key = f"{code}_{days}"
        now = time.time()
        with self._lock:
            if cache_key in self._kline_cache:
                cached = self._kline_cache[cache_key]
                # V2.8.1：缓存时效校验，超过5分钟自动重取DuckDB
                if isinstance(cached, dict) and 'data' in cached:
                    if now - cached.get('time', 0) < 300:
                        return cached['data']
                    # 缓存过期，删除后重新获取
                    del self._kline_cache[cache_key]
                else:
                    # 兼容旧格式（直接存kline list），直接返回
                    return cached

        # 先尝试DuckDB缓存
        kline = self._get_kline_from_duckdb(code, days)
        if kline and len(kline) >= 30:
            with self._lock:
                self._kline_cache[cache_key] = {'data': kline, 'time': time.time()}
            return kline

        # 再尝试多源在线获取（pytdx→腾讯→新浪→东财，与real_scan_service一致）
        try:
            from utils.kline_fetcher import fetch_kline
            kline = fetch_kline(code, days=days)
            if kline and len(kline) >= 30:
                with self._lock:
                    self._kline_cache[cache_key] = {'data': kline, 'time': time.time()}
                return kline
        except Exception as e:
            print(f"[AI520] {code} 多源K线获取失败: {e}", flush=True)

        return None

    def _get_kline_from_duckdb(self, code: str, days: int = 200) -> Optional[List[Dict]]:
        """从DuckDB K线缓存获取（单只）"""
        try:
            import duckdb
            db_path = os.path.join(PROJECT_ROOT, 'data', 'cache', 'kline_cache.duckdb')
            if not os.path.exists(db_path):
                return None
            con = duckdb.connect(db_path, read_only=False)
            rows = con.execute("""
                SELECT date, open, high, low, close, volume
                FROM kline_cache
                WHERE code = ?
                ORDER BY date DESC
                LIMIT ?
            """, (code, days)).fetchall()
            con.close()
            if not rows:
                return None
            # 反转成正序
            kline = []
            for row in reversed(rows):
                kline.append({
                    'date': str(row[0]),
                    'open': float(row[1]),
                    'high': float(row[2]),
                    'low': float(row[3]),
                    'close': float(row[4]),
                    'volume': float(row[5]),
                })
            return kline
        except Exception as e:
            print(f"[AI520] {code} DuckDB缓存读取失败: {e}", flush=True)
            return None

    def batch_load_kline_from_duckdb(self, codes: List[str], days: int = 200,
                                       min_bars: int = 60) -> Dict[str, List[Dict]]:
        """
        批量从DuckDB加载K线（一次性查询，大幅提升速度）
        Args:
            codes: 股票代码列表
            days: 每只股票最多获取多少根
            min_bars: 最少K线数，少于此数的股票不返回
        Returns:
            {code: kline_list}
        """
        if not codes:
            return {}

        try:
            import duckdb
            db_path = os.path.join(PROJECT_ROOT, 'data', 'cache', 'kline_cache.duckdb')
            if not os.path.exists(db_path):
                return {}

            print(f"[AI520] 批量加载K线: {len(codes)}只股票...", flush=True)
            start = time.time()

            con = duckdb.connect(db_path, read_only=False)
            # 使用TRIM(code)避免DuckDB索引异常导致精确匹配失败
            placeholders = ','.join(['?'] * len(codes))
            rows = con.execute(f"""
                SELECT TRIM(code) as code, date, open, high, low, close, volume
                FROM kline_cache
                WHERE TRIM(code) IN ({placeholders})
                ORDER BY code, date
            """, codes).fetchall()
            con.close()

            # 按股票分组
            result = {}
            for row in rows:
                code = str(row[0])
                if code not in result:
                    result[code] = []
                result[code].append({
                    'date': str(row[1]),
                    'open': float(row[2]),
                    'high': float(row[3]),
                    'low': float(row[4]),
                    'close': float(row[5]),
                    'volume': float(row[6]),
                })

            # 过滤K线不足的股票，并限制每只股票的K线数量
            filtered = {}
            for code, kline in result.items():
                if len(kline) >= min_bars:
                    # 只保留最近days根
                    filtered[code] = kline[-days:] if len(kline) > days else kline

            elapsed = time.time() - start
            print(f"[AI520] 批量加载完成: {len(filtered)}/{len(codes)}只有效K线, 耗时{elapsed:.2f}秒", flush=True)

            # 存入内存缓存（V2.8.1：带时间戳，支持5分钟时效校验）
            with self._lock:
                now_ts = time.time()
                for code, kline in filtered.items():
                    self._kline_cache[f"{code}_{days}"] = {'data': kline, 'time': now_ts}

            return filtered
        except Exception as e:
            print(f"[AI520] 批量加载K线失败: {e}", flush=True)
            return {}

    def get_stock_list(self, main_board_only: bool = True, exclude_st: bool = True) -> List[Dict]:
        """获取股票列表"""
        try:
            from utils.tdx_stock_list import get_full_market_quotes
            stocks = get_full_market_quotes(main_board_only=main_board_only, exclude_st=exclude_st)
            return stocks or []
        except Exception as e:
            print(f"[AI520] 股票列表获取失败: {e}", flush=True)
            return []

    def get_stock_list_from_duckdb(self) -> List[Dict]:
        """从DuckDB缓存获取有K线的股票列表（用于回测/非交易时间测试）
        V2.7.1修复：使用IndustryFilterService统一获取行业，解决静默扫描行业为空问题
        """
        try:
            import duckdb
            db_path = os.path.join(PROJECT_ROOT, 'data', 'cache', 'kline_cache.duckdb')
            if not os.path.exists(db_path):
                return []
            con = duckdb.connect(db_path, read_only=False)
            rows = con.execute("""
                SELECT DISTINCT code FROM kline_cache
                WHERE code LIKE '60%' OR code LIKE '00%'
                ORDER BY code
            """).fetchall()
            con.close()

            # 从通达信获取真实股票名称（get_stock_list_tdx返回name但不返回industry）
            name_map = {}
            try:
                from utils.tdx_stock_list import get_stock_list_tdx
                tdx_stocks = get_stock_list_tdx() or []
                for s in tdx_stocks:
                    code = s.get('code', '')
                    if code:
                        name_map[code] = s.get('name', code)
                print(f"[AI520] 通达信股票名称映射加载: {len(name_map)}只", flush=True)
            except Exception as e:
                print(f"[AI520] 通达信股票列表获取失败: {e}", flush=True)

            # V2.7.1：使用IndustryFilterService统一获取行业（带持久化缓存）
            codes = [row[0] for row in rows]
            industry_map = {}
            try:
                from services.industry_filter_service import get_industry_filter_service
                ifs = get_industry_filter_service()
                industry_result = ifs.batch_get_industry(codes)
                for code, (industry, status) in industry_result.items():
                    industry_map[code] = industry
                cache_stats = ifs.get_cache_stats()
                print(f"[AI520] IndustryFilterService行业缓存: 已知{cache_stats['known']}/未知{cache_stats['unknown']}", flush=True)
            except Exception as e:
                print(f"[AI520] IndustryFilterService获取行业失败: {e}", flush=True)

            stocks = []
            for row in rows:
                code = row[0]
                # 排除ST（简单判断名称）
                name = name_map.get(code, code)
                if 'ST' in name.upper() or '*ST' in name.upper():
                    continue
                industry = industry_map.get(code, '')
                stocks.append({
                    'code': code,
                    'name': name,
                    'price': 0,
                    'pct_chg': 0,
                    'industry': industry,
                    'industry_status': 'OK' if industry else 'UNKNOWN',
                    'market_cap': 0,
                })

            # V2.7.1：使用IndustryFilterService统一过滤排除行业（酒水/房地产/农业/保险）
            try:
                from services.industry_filter_service import get_industry_filter_service
                ifs = get_industry_filter_service()
                stocks, filter_stats = ifs.filter_stocks(stocks)
                print(f"[AI520] 行业过滤: 排除{filter_stats['excluded_by_industry']}只, 未知{filter_stats['unknown_industry']}只, 通过{filter_stats['filtered']}只", flush=True)
            except Exception as e:
                print(f"[AI520] 行业过滤失败: {e}", flush=True)

            # 统计行业未知数量
            unknown_count = sum(1 for s in stocks if not s.get('industry'))
            print(f"[AI520] DuckDB股票列表: 共{len(stocks)}只, 行业未知{unknown_count}只", flush=True)
            return stocks
        except Exception as e:
            print(f"[AI520] DuckDB股票列表获取失败: {e}", flush=True)
            return []

    def scan_market(self, scan_source: str = '09:30',
                    max_stocks: int = 0, use_cache: bool = True) -> Dict:
        """
        全市场扫描
        Args:
            scan_source: 扫描来源（09:30/14:45/manual）
            max_stocks: 最大扫描股票数（0=全部）
            use_cache: 是否使用K线缓存
        Returns:
            扫描结果统计
        """
        start_time = time.time()
        scan_date = datetime.now().strftime('%Y-%m-%d')
        scan_time = datetime.now().strftime('%H:%M:%S')

        print(f"[AI520] ===== {scan_source} 扫描开始 {scan_date} {scan_time} =====", flush=True)

        # V2.8：K线日期校验（扫描前检查是否为最新交易日）
        try:
            from services.kline_cache_service import get_last_date
            sample_codes = ['000001', '600000', '000002']
            kline_dates = []
            for code in sample_codes:
                last_date = get_last_date(code)
                if last_date:
                    kline_dates.append(last_date)
            if kline_dates:
                latest_kline_date = max(kline_dates)
                today_str = datetime.now().strftime('%Y-%m-%d')
                # 判断是否为交易日（简单判断：如果今天是周末，用最近的交易日）
                weekday = datetime.now().weekday()
                if weekday >= 5:  # 周六周日
                    # 上周五
                    from datetime import timedelta
                    expected_date = (datetime.now() - timedelta(days=weekday-4)).strftime('%Y-%m-%d')
                else:
                    expected_date = today_str
                
                if latest_kline_date < expected_date:
                    print(f"[AI520] ⚠️ K线数据陈旧: 最新={latest_kline_date}, 预期={expected_date}, 扫描结果可能不准确", flush=True)
                    print(f"[AI520] 建议: 程序启动时已触发后台K线更新，请等待更新完成后重新扫描", flush=True)
                else:
                    print(f"[AI520] ✅ K线日期校验通过: 最新={latest_kline_date}", flush=True)
        except Exception as e:
            print(f"[AI520] K线日期校验失败（不影响扫描）: {e}", flush=True)

        # V2.8.1：扫描前强制全量刷新K线（解决昨日数据选股问题）
        try:
            print(f"[AI520] 扫描前强制刷新K线数据（最多等待120秒）...", flush=True)
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
                print(f"[AI520] WARNING K线刷新超时（>120秒），降级使用缓存数据继续扫描", flush=True)
            elif refresh_error[0]:
                print(f"[AI520] WARNING K线刷新失败（非交易时间等），降级使用缓存: {refresh_error[0]}", flush=True)
            elif refresh_result[0]:
                r = refresh_result[0]
                print(f"[AI520] OK K线刷新完成: 更新{r.get('updated',0)}只, 新增K线{r.get('new_kline_total',0)}根, 失败{r.get('failed',0)}只, 耗时{time.time()-refresh_start:.1f}秒", flush=True)

            # 清空内存缓存，确保后续读取最新DuckDB数据
            with self._lock:
                self._kline_cache.clear()
            print(f"[AI520] 内存K线缓存已清空", flush=True)
        except Exception as e:
            print(f"[AI520] WARNING 扫描前K线刷新异常（不阻断扫描）: {e}", flush=True)

        # 获取股票列表
        if use_cache:
            stocks = self.get_stock_list_from_duckdb()
            print(f"[AI520] 从DuckDB缓存获取股票列表: {len(stocks)}只", flush=True)
        else:
            stocks = self.get_stock_list(main_board_only=True, exclude_st=True)
            print(f"[AI520] 从通达信获取股票列表: {len(stocks)}只", flush=True)

        if max_stocks > 0 and len(stocks) > max_stocks:
            stocks = stocks[:max_stocks]
            print(f"[AI520] 限制扫描数量: {max_stocks}只", flush=True)

        total_stocks = len(stocks)
        signals = []
        s_count = a_count = b_count = c_count = 0
        filter_pass = 0
        kline_fail = 0
        # V2.6评分分布统计
        stat_price_below_6 = 0
        stat_score_90 = 0
        stat_score_80 = 0
        stat_score_70 = 0
        stat_score_60 = 0
        stat_score_below_60 = 0

        # 批量预加载K线（大幅提升速度）
        if use_cache and stocks:
            codes = [s['code'] for s in stocks if s.get('code')]
            batch_kline = self.batch_load_kline_from_duckdb(codes, days=200, min_bars=60)
            # 用批量加载的K线更新股票列表（只保留有足够K线的股票）
            valid_stocks = []
            for stock in stocks:
                code = stock.get('code', '')
                if code in batch_kline:
                    valid_stocks.append(stock)
            stocks = valid_stocks
            total_stocks = len(stocks)
            print(f"[AI520] 批量K线预加载后有效股票: {total_stocks}只", flush=True)

        for idx, stock in enumerate(stocks):
            code = stock.get('code', '')
            if not code:
                continue

            # 获取K线（从内存缓存读取，批量加载后已在缓存中）
            kline = self.get_kline(code, days=200)
            if not kline or len(kline) < 30:
                kline_fail += 1
                continue

            # 用K线最后一根收盘价填充价格（DuckDB股票列表price=0时）
            if stock.get('price', 0) <= 0:
                stock['price'] = kline[-1]['close']
                # 计算涨跌幅
                if len(kline) >= 2 and kline[-2]['close'] > 0:
                    stock['pct_chg'] = (kline[-1]['close'] - kline[-2]['close']) / kline[-2]['close'] * 100

            # V2.3全局硬过滤：价格<6.00元直接拒绝（6.00允许，5.99禁止）
            current_price = stock.get('price', 0)
            if current_price > 0 and current_price < 6.00:
                print(f"[AI520_FILTER] REJECT PRICE_BELOW_6 code={code} price={current_price:.2f}", flush=True)
                stat_price_below_6 += 1
                continue

            # 补充实时价格（如果有）
            if stock.get('price', 0) > 0:
                # 用实时价格替换最后一根K线的收盘价（模拟实时状态）
                kline[-1]['close'] = stock['price']
                if stock.get('pct_chg', 0) != 0:
                    kline[-1]['pct_change'] = stock['pct_chg'] / 100

            # 分析（V2.7.1：统一调用AI520Strategy唯一核心策略）
            try:
                ai520_result = self.ai520_strategy.score_stock(kline, stock)
                if ai520_result and ai520_result.get('status') == 'OK':
                    # V2.7.1：使用AI520Strategy相似度评分
                    ai520_score = ai520_result.get('score', 0)
                    ai520_grade = ai520_result.get('grade', 'D')
                    ai520_similarity = ai520_result.get('similarity', '')
                    # 合并AI520Strategy结果到result
                    result = dict(stock)
                    result.update(ai520_result)
                    result['ai520_score'] = ai520_score
                    result['ai520_grade'] = ai520_grade
                    result['ai520_similarity'] = ai520_similarity
                    result['ai520_matched_conditions'] = ai520_result.get('matched_conditions', [])

                    # 评分分布统计
                    if ai520_score >= 90:
                        stat_score_90 += 1
                    elif ai520_score >= 80:
                        stat_score_80 += 1
                    elif ai520_score >= 70:
                        stat_score_70 += 1
                    elif ai520_score >= 60:
                        stat_score_60 += 1
                    else:
                        stat_score_below_60 += 1

                    # V2.6准入：>=60分进入作战中控台候选池
                    if ai520_score < 60:
                        if idx < 10:
                            print(f"[AI520_V26] {code} 评分{ai520_score}低于60，不进入候选池", flush=True)
                        continue

                    # 打印高分股票
                    if ai520_score >= 70:
                        matched = result.get('ai520_matched_conditions', [])
                        print(f"[AI520_V26] {code} {result.get('name','')} 评分={ai520_score} 等级={ai520_grade} 相似度={ai520_similarity} 符合={len(matched)}项", flush=True)

                    # 使用V2.6相似度评分作为主评分
                    result['grade'] = ai520_grade
                    result['total_score'] = ai520_score
                    result['score'] = ai520_score
                    result['signal_type'] = f'AI520-{ai520_similarity}'

                    # V2.7.1修复：补充企业微信推送需要的旧版字段（从K线实时计算）
                    try:
                        import numpy as np
                        closes = [k['close'] for k in kline]
                        highs = [k['high'] for k in kline]
                        lows = [k['low'] for k in kline]
                        volumes = [k['volume'] for k in kline]
                        # MA5/MA20
                        ma5 = float(np.mean(closes[-5:])) if len(closes) >= 5 else closes[-1]
                        ma20 = float(np.mean(closes[-20:])) if len(closes) >= 20 else closes[-1]
                        # MA20趋势
                        if len(closes) >= 25:
                            ma20_prev = float(np.mean(closes[-25:-5]))
                            ma20_trend = '上行' if ma20 > ma20_prev * 1.001 else ('下行' if ma20 < ma20_prev * 0.999 else '走平')
                        else:
                            ma20_trend = '走平'
                        # 金叉天数（MA5上穿MA20）
                        cross_days_ago = -1
                        for i in range(len(closes) - 5, 4, -1):
                            ma5_now = float(np.mean(closes[i-4:i+1]))
                            ma20_now = float(np.mean(closes[i-19:i+1])) if i >= 19 else closes[i]
                            ma5_prev = float(np.mean(closes[i-5:i]))
                            ma20_prev = float(np.mean(closes[i-20:i])) if i >= 20 else closes[i-1]
                            if ma5_prev <= ma20_prev and ma5_now > ma20_now:
                                cross_days_ago = len(closes) - 1 - i
                                break
                        result['cross_info'] = {
                            'ma5': ma5, 'ma20': ma20,
                            'ma20_trend': ma20_trend,
                            'cross_days_ago': cross_days_ago,
                        }
                        # 量比（今日成交量 / 过去5日均量）
                        if len(volumes) >= 6 and volumes[-6] > 0:
                            vol_ratio = float(volumes[-1]) / (float(np.mean(volumes[-6:-1])) + 1e-9)
                        else:
                            vol_ratio = 1.0
                        result['volume_info'] = {'vol_ratio': min(vol_ratio, 99.9)}
                        # 年涨停次数（近250个交易日涨幅>=9.8%）
                        limit_count = 0
                        for i in range(1, min(len(closes), 250)):
                            if closes[i-1] > 0:
                                pct = (closes[i] - closes[i-1]) / closes[i-1] * 100
                                if pct >= 9.8:
                                    limit_count += 1
                        result['limit_count_1y'] = limit_count
                        # 距8月高点（近60个交易日最高价的距离）
                        if len(highs) >= 5:
                            high_60 = max(highs[-60:]) if len(highs) >= 60 else max(highs)
                            dist_8m = (closes[-1] - high_60) / high_60 * 100 if high_60 > 0 else 0
                        else:
                            dist_8m = 0
                        result['position_info'] = {'dist_from_8m_high': dist_8m}
                    except Exception as e:
                        print(f"[AI520] {code} 推送字段计算异常: {e}", flush=True)
                        result['cross_info'] = {'ma5': 0, 'ma20': 0, 'ma20_trend': '', 'cross_days_ago': -1}
                        result['volume_info'] = {'vol_ratio': 0}
                        result['limit_count_1y'] = 0
                        result['position_info'] = {'dist_from_8m_high': 0}

                    filter_pass += 1
                    result['signal_date'] = scan_date
                    result['signal_time'] = scan_time
                    result['signal_source'] = scan_source

                    # 保存信号
                    sig_id = self.db.save_signal(result)
                    result['signal_id'] = sig_id

                    # V2.7.1：观察池已删除，不再写入
                    signals.append(result)
                    grade = result.get('grade', '')
                    if grade == 'S':
                        s_count += 1
                    elif grade == 'A':
                        a_count += 1
                    elif grade == 'B':
                        b_count += 1
                    elif grade == 'C':
                        c_count += 1

                    if idx % 50 == 0:
                        print(f"[AI520] 进度 {idx}/{total_stocks}, 已发现信号 {len(signals)}只 (V2.3回踩:{sum(1 for s in signals if s.get('is_ai520_v23'))}只)", flush=True)
            except Exception as e:
                print(f"[AI520] {code} 分析异常: {e}", flush=True)
                continue

        duration = time.time() - start_time

        # 保存扫描记录
        self.db.save_scan_run({
            'scan_date': scan_date,
            'scan_time': scan_time,
            'scan_source': scan_source,
            'total_stocks': total_stocks,
            'filtered_stocks': filter_pass,
            'signal_count': len(signals),
            's_count': s_count,
            'a_count': a_count,
            'b_count': b_count,
            'c_count': c_count,
            'duration_seconds': round(duration, 2),
            'status': 'completed',
            'error_msg': '',
        })

        print(f"[AI520] ===== 扫描完成 =====", flush=True)
        print(f"[AI520] 总股票: {total_stocks}, K线失败: {kline_fail}, 通过过滤: {filter_pass}", flush=True)
        print(f"[AI520] 信号: S={s_count}, A={a_count}, B={b_count}, C={c_count}, 总计={len(signals)}", flush=True)
        print(f"[AI520] 耗时: {duration:.2f}秒", flush=True)

        # V2.6相似度评分分布诊断日志
        print(f"[AI520_SCAN] ===== V2.8相似度评分分布 =====", flush=True)
        print(f"[AI520_SCAN] 全市场扫描: {total_stocks}", flush=True)
        print(f"[AI520_SCAN] K线不足淘汰: {kline_fail}", flush=True)
        print(f"[AI520_SCAN] 价格<6淘汰: {stat_price_below_6}", flush=True)
        print(f"[AI520_SCAN] 评分>=90(高度相似): {stat_score_90}", flush=True)
        print(f"[AI520_SCAN] 评分80-89(强相似): {stat_score_80}", flush=True)
        print(f"[AI520_SCAN] 评分70-79(较强相似): {stat_score_70}", flush=True)
        print(f"[AI520_SCAN] 评分60-69(相似): {stat_score_60}", flush=True)
        print(f"[AI520_SCAN] 评分<60(不进入候选): {stat_score_below_60}", flush=True)
        print(f"[AI520_SCAN] 最终AI520信号(>=60): {len(signals)} (S:{s_count} A:{a_count} B:{b_count} C:{c_count})", flush=True)

        return {
            'scan_date': scan_date,
            'scan_time': scan_time,
            'scan_source': scan_source,
            'total_stocks': total_stocks,
            'kline_fail': kline_fail,
            'filter_pass': filter_pass,
            'signals': signals,
            's_count': s_count,
            'a_count': a_count,
            'b_count': b_count,
            'c_count': c_count,
            'duration': round(duration, 2),
        }

    def scan_today_pullback_520(self, max_results: int = 30, use_cache: bool = True) -> Dict:
        """今天模式：520金叉后的MA5/MA20回踩再启动。
        使用真实行情+真实K线；不把“回踩”做成模拟数据。
        """
        started = time.time()
        stocks = self.get_stock_list(main_board_only=True, exclude_st=True)
        if not stocks:
            return {'signals': [], 'error': '通达信股票列表为空'}
        codes = [s.get('code') for s in stocks if s.get('code')]
        batch = self.batch_load_kline_from_duckdb(codes, days=120, min_bars=40) if use_cache else {}
        signals = []
        for stock in stocks:
            code = stock.get('code', '')
            kline = batch.get(code) if use_cache else self.get_kline(code, days=120)
            if not kline or len(kline) < 40:
                continue
            # 实时价格/涨跌幅优先，回测或非交易时段则使用K线收盘
            if stock.get('price', 0) <= 0:
                stock['price'] = kline[-1].get('close', 0)
            if stock.get('pct_chg', 0) == 0 and len(kline) >= 2:
                prev = kline[-2].get('close', 0)
                if prev:
                    stock['pct_chg'] = (stock['price'] - prev) / prev * 100
            # 仅替换最后一根的收盘价，避免篡改历史K线
            live_kline = list(kline)
            live_kline[-1] = dict(live_kline[-1])
            live_kline[-1]['close'] = float(stock.get('price') or live_kline[-1]['close'])
            result = self.pullback_mode.analyze(stock, live_kline)
            if result:
                signals.append(result)
        signals.sort(key=lambda x: (x.get('score', 0), -abs(x.get('dist_ma5', 99))), reverse=True)
        signals = signals[:max_results]
        return {
            'scan_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'mode': 'AI-520回踩MA5/MA20今天启动',
            'scanned': len(stocks), 'signal_count': len(signals),
            'signals': signals, 'duration': round(time.time() - started, 2),
            'data_source': '通达信/pytdx + 本地真实K线缓存',
        }

    def push_today_pullback_520(self, result: Dict, max_push: int = 10) -> Dict:
        """只推送S/A级回踩启动信号，并等待企业微信真实返回。"""
        signals = [x for x in result.get('signals', []) if x.get('grade') in ('S', 'A')][:max_push]
        if not signals:
            return {'success': True, 'pushed': 0, 'message': '没有S/A级回踩启动信号'}
        lines = [f"### 【AI-520回踩启动】{result.get('scan_time','')}",
                 f"扫描{result.get('scanned',0)}只｜入选{result.get('signal_count',0)}只｜推送S/A {len(signals)}只", ""]
        for i, x in enumerate(signals, 1):
            lines.append(f"**{i}. {x['grade']} {x['name']}({x['code']}) {x['score']:.0f}分**")
            lines.append(f"> {x['mode']}｜价格{x['price']:.2f}｜今日{x['today_pct']:+.2f}%")
            lines.append(f"> MA5 {x['ma5']:.2f}({x['dist_ma5']:+.2f}%)｜MA20 {x['ma20']:.2f}({x['dist_ma20']:+.2f}%)")
            lines.append(f"> 520金叉{x['cross_age']}日｜回踩{x['touch_days']}日｜量比{x['vol_ratio']:.2f}｜MA20斜率{x['ma20_slope']:+.2f}%")
            lines.append(f"> {'、'.join(x.get('reasons',[])[:5])}")
            if x.get('risks'): lines.append(f"> 风险：{'、'.join(x['risks'][:3])}")
        lines.append("\n> 数据：通达信/pytdx真实行情与K线；T+1，仅作研究参考")
        # V3.0 推送重构：AI520 回踩启动不再主动推送企业微信（信号仍在UI展示）
        return {'success': True, 'pushed': 0,
                'message': 'AI520企业微信推送已按V3.0关闭，信号仅在程序UI展示'}

    def _calc_buy_sell_points(self, code: str, name: str = '') -> Dict:
        """
        计算买点/卖点价格和逻辑（复用BuyPointEngine V7.1）
        Returns: {best_buy_range, stop_loss, target_range, buy_logic, sell_logic, atr, support, resistance}
        """
        result = {
            'best_buy_range': [0, 0],
            'stop_loss': 0,
            'target_range': [0, 0],
            'buy_logic': '',
            'sell_logic': '',
            'atr': 0,
            'support': 0,
            'resistance': 0,
        }
        try:
            from strategy.buy_point_engine import BuyPointEngine
            engine = BuyPointEngine()
            # 获取K线数据（至少60根用于计算均线和ATR）
            kline = self.get_kline(code, days=120)
            if not kline or len(kline) < 30:
                return result

            bp_result = engine.analyze(kline, code=code, name=name)
            pl = bp_result.price_levels

            result['best_buy_range'] = [round(pl.best_buy_low, 2), round(pl.best_buy_high, 2)]
            result['stop_loss'] = round(pl.stop_loss, 2)
            result['target_range'] = [round(pl.target_low, 2), round(pl.target_high, 2)]
            result['atr'] = round(pl.atr, 2)
            result['support'] = round(pl.support, 2)
            result['resistance'] = round(pl.resistance, 2)

            # 构建买点逻辑
            buy_logics = []
            if bp_result.buy_type and bp_result.buy_type != '无明显买点':
                buy_logics.append(bp_result.buy_type)
            if bp_result.reasons:
                buy_logics.extend(bp_result.reasons[:2])
            if pl.support > 0:
                buy_logics.append(f"支撑位{pl.support:.2f}")
            result['buy_logic'] = ' + '.join(buy_logics[:3]) if buy_logics else '技术面支撑'

            # 构建卖点逻辑
            sell_logics = []
            if pl.resistance > 0:
                sell_logics.append(f"前高压力位{pl.resistance:.2f}")
            if bp_result.risks:
                sell_logics.extend(bp_result.risks[:1])
            if pl.stop_loss > 0:
                sell_logics.append(f"跌破止损位{pl.stop_loss:.2f}")
            result['sell_logic'] = ' + '.join(sell_logics[:2]) if sell_logics else '跌破支撑位'

        except Exception as e:
            print(f"[AI520] {code} 买点计算异常: {e}", flush=True)

        return result

    def push_signals_to_wechat(self, signals: List[Dict], scan_source: str = '09:30') -> Dict:
        """
        将信号推送到企业微信
        只推送S级和A级（评分>=75）
        """
        if not signals:
            return {'pushed': 0, 'failed': 0, 'skipped': 0}

        scan_date = datetime.now().strftime('%Y-%m-%d')
        push_count = 0
        fail_count = 0
        skip_count = 0

        # V2.7.1：批量获取主力净流入、板块异动、异动原因
        try:
            import requests
            # 获取热门板块（带重试和headers）
            hot_sectors = []
            sector_headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            for retry in range(3):
                try:
                    sector_url = 'https://push2delay.eastmoney.com/api/qt/clist/get'
                    sector_params = {
                        'pn': 1, 'pz': 10, 'po': 1, 'np': 1, 'fltt': 2, 'invt': 2,
                        'fid': 'f3', 'fs': 'm:90+t:2',
                        'fields': 'f2,f3,f12,f14,f62',
                    }
                    sector_resp = requests.get(sector_url, params=sector_params, headers=sector_headers, timeout=10)
                    sector_data = sector_resp.json()
                    if sector_data.get('data') and sector_data['data'].get('diff'):
                        for item in sector_data['data']['diff']:
                            sname = item.get('f14', '')
                            schange = item.get('f3', 0)
                            if sname and schange > 1:
                                hot_sectors.append(f"{sname}(+{schange:.1f}%)")
                    if hot_sectors:
                        break
                except Exception as e:
                    if retry < 2:
                        import time
                        time.sleep(1)
                        continue
                    print(f"[AI520] 获取热门板块失败(重试{retry+1}次): {e}", flush=True)
            
            # 为每只S/A级股票获取主力净流入和异动原因
            sa_codes = [s.get('code', '') for s in signals if s.get('grade') in ('S', 'A')]
            for sig in signals:
                if sig.get('grade') not in ('S', 'A'):
                    continue
                code = sig.get('code', '')
                name = sig.get('name', '')
                industry = sig.get('industry', '')
                
                # 获取主力净流入（带headers和重试）
                for fund_retry in range(2):
                    try:
                        secid = f'1.{code}' if code.startswith('6') else f'0.{code}'
                        fund_url = f'https://push2delay.eastmoney.com/api/qt/stock/fflow/daykline/get?secid={secid}&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57'
                        fund_resp = requests.get(fund_url, headers=sector_headers, timeout=8)
                        fund_data = fund_resp.json()
                        if fund_data and fund_data.get('data') and fund_data['data'].get('klines'):
                            klines = fund_data['data']['klines']
                            if klines:
                                latest = klines[-1].split(',')
                                if len(latest) >= 2:
                                    main_net = float(latest[1]) / 10000  # 万元
                                    sig['fund_flow'] = {'main_net': main_net}
                        break
                    except Exception:
                        if fund_retry < 1:
                            import time
                            time.sleep(0.5)
                            continue
                
                # 匹配热门板块
                if industry and hot_sectors:
                    for hs in hot_sectors:
                        if industry[:2] in hs or hs[:2] in industry:
                            sig['hot_sector'] = hs
                            break
                
                # 生成异动原因
                reasons = []
                score_detail = sig.get('score_detail', {})
                ai520_score = sig.get('ai520_score', sig.get('total_score', 0))
                
                # 基于AI520维度生成原因
                if ai520_score >= 80:
                    reasons.append("AI520高度相似")
                elif ai520_score >= 70:
                    reasons.append("AI520较强相似")
                
                # 趋势结构
                trend_score = 0
                if '趋势结构' in score_detail:
                    trend_score = score_detail['趋势结构'].get('score', 0)
                elif 'trend_structure' in sig:
                    trend_score = sig.get('trend_structure', 0)
                if trend_score >= 18:
                    reasons.append("完美多头排列")
                elif trend_score >= 15:
                    reasons.append("趋势结构良好")
                
                # 历史强势
                strong_score = 0
                if '历史强势记忆' in score_detail:
                    strong_score = score_detail['历史强势记忆'].get('score', 0)
                if strong_score >= 12:
                    reasons.append("有强势启动记忆")
                
                # 回踩类型
                pullback = sig.get('pullback_type', '')
                if pullback == 'MA5':
                    reasons.append("MA5缩量回踩")
                elif pullback == 'MA20':
                    reasons.append("MA20缩量回踩")
                
                # 资金流入
                main_net = sig.get('fund_flow', {}).get('main_net', 0)
                if main_net > 5000:
                    reasons.append("主力大幅净流入")
                elif main_net > 1000:
                    reasons.append("主力净流入")
                
                # 板块异动
                if sig.get('hot_sector'):
                    reasons.append("所属板块异动")
                
                if reasons:
                    sig['anomaly_reason'] = '、'.join(reasons[:4])
        except Exception as e:
            print(f"[AI520] 批量获取资金/板块/异动原因失败: {e}", flush=True)

        # 按评分排序，只推S/A级
        high_grade = [s for s in signals if s.get('grade') in ('S', 'A')]
        high_grade.sort(key=lambda x: x.get('total_score', 0), reverse=True)

        if not high_grade:
            print(f"[AI520] 无S/A级信号，不推送企业微信（正常跳过）", flush=True)
            return {'success': True, 'pushed': 0, 'failed': 0, 'skipped': len(signals), 'reason': 'no_high_grade'}

        # V2.7.1：取消推送次数限制，所有S/A级都推送（超过30只时提示）
        push_list = high_grade
        if len(push_list) > 30:
            print(f"[AI520] S/A级信号{len(push_list)}只，超过30只，推送前30只", flush=True)
            push_list = push_list[:30]

        # 构建消息
        title = f"【AI-520 {scan_source}启动雷达】"
        subtitle = f"{scan_date} {scan_source}扫描 | 共{len(signals)}只信号 | S/A级{len(high_grade)}只 | 本次推送{len(push_list)}只"

        content = f"### {title}\n**{subtitle}**\n\n"

        for i, sig in enumerate(push_list, 1):
            code = sig.get('code', '')
            name = sig.get('name', '')
            price = sig.get('price', 0)
            pct = sig.get('pct_chg', 0)
            score = sig.get('total_score', 0)
            grade = sig.get('grade', '')
            grade_name = sig.get('grade_name', '')
            industry = sig.get('industry', '')
            ma5 = sig.get('cross_info', {}).get('ma5', 0)
            ma20 = sig.get('cross_info', {}).get('ma20', 0)
            ma20_trend = sig.get('cross_info', {}).get('ma20_trend', '')
            cross_days = sig.get('cross_info', {}).get('cross_days_ago', -1)
            vol_ratio = sig.get('volume_info', {}).get('vol_ratio', 0)
            limit_1y = sig.get('limit_count_1y', 0)
            dist_8m = sig.get('position_info', {}).get('dist_from_8m_high', 0)
            reasons = sig.get('reasons', [])[:4]

            grade_icon = '🔥' if grade == 'S' else '🟢' if grade == 'A' else '🟡'

            content += f"**{i}. {grade_icon} {name}({code}) {score}分 {grade}级**\n"
            content += f"> 价格: {price:.2f} ({pct:+.2f}%) | 行业: {industry}\n"
            content += f"> MA5: {ma5:.2f} | MA20: {ma20:.2f}({ma20_trend}) | 金叉: {cross_days}天前\n"
            content += f"> 量比: {vol_ratio:.2f} | 年涨停: {limit_1y}次 | 距8月高点: {dist_8m:+.1f}%\n"
            if reasons:
                content += f"> 入选: {'、'.join(reasons)}\n"
            
            # V2.7.1：添加主力净流入、板块异动、异动原因
            fund_flow = sig.get('fund_flow', {})
            main_net = fund_flow.get('main_net', 0)
            if main_net != 0:
                net_text = f"主力净流入: {main_net:+.0f}万" if abs(main_net) < 10000 else f"主力净流入: {main_net/10000:+.2f}亿"
                content += f"> 💰 {net_text}\n"
            
            # 板块异动
            hot_sector = sig.get('hot_sector', '')
            if hot_sector:
                content += f"> 🔥 板块异动: {hot_sector}\n"
            
            # 异动原因
            anomaly_reason = sig.get('anomaly_reason', '')
            if anomaly_reason:
                content += f"> 📌 异动原因: {anomaly_reason}\n"

            # V2.7.1：买点/卖点（基于真实K线计算，复用BuyPointEngine V7.1）
            try:
                bp = sig.get('buy_sell_points')
                if not bp:
                    bp = self._calc_buy_sell_points(code, name)
                    sig['buy_sell_points'] = bp
                best_buy = bp.get('best_buy_range', [0, 0])
                stop_loss = bp.get('stop_loss', 0)
                target = bp.get('target_range', [0, 0])
                buy_logic = bp.get('buy_logic', '')
                sell_logic = bp.get('sell_logic', '')
                if best_buy and best_buy[0] > 0 and best_buy[1] > 0:
                    content += f"> 🎯 买点: {best_buy[0]:.2f}~{best_buy[1]:.2f}元"
                    if buy_logic:
                        content += f"（{buy_logic}）"
                    content += "\n"
                if stop_loss > 0:
                    content += f"> 🛑 止损: {stop_loss:.2f}元"
                    if sell_logic:
                        content += f"（{sell_logic}）"
                    content += "\n"
                if target and target[1] > 0:
                    content += f"> 🎯 目标: {target[0]:.2f}~{target[1]:.2f}元\n"
            except Exception as e:
                print(f"[AI520] {code} 买点卖点推送异常: {e}", flush=True)

            content += "\n"

        if len(high_grade) > 10:
            content += f"*另有{len(high_grade) - 10}只S/A级信号未列出*\n"

        content += f"\n---\n*AI-520动态选股雷达 | 数据来源: 通达信/pytdx | 仅供参考，不构成投资建议*"

        # 检查重复推送
        first_code = push_list[0].get('code', '') if push_list else ''
        if self.db.is_duplicate_push(scan_date, first_code, scan_source):
            print(f"[AI520] {scan_source} 今日已推送过，跳过", flush=True)
            return {'pushed': 0, 'failed': 0, 'skipped': len(push_list), 'duplicate': True}

        # 发送
        # V3.0 推送重构：AI520 信号不再主动推送企业微信（信号仍在UI/记录中保留）
        success, msg = (False, 'V3.0 AI520企业微信推送已关闭，仅保留UI与本地记录')

        # 保存推送记录
        for sig in push_list:
            self.db.save_push_record({
                'push_date': scan_date,
                'push_time': datetime.now().strftime('%H:%M:%S'),
                'signal_source': scan_source,
                'code': sig.get('code', ''),
                'name': sig.get('name', ''),
                'grade': sig.get('grade', ''),
                'total_score': sig.get('total_score', 0),
                'push_type': 'auto',
                'push_status': 'success' if success else 'failed',
                'error_msg': '' if success else msg,
                'message_id': '',
            })

        if success:
            push_count = len(push_list)
            print(f"[AI520] 企业微信推送成功: {push_count}只股票", flush=True)
        else:
            fail_count = len(push_list)
            print(f"[AI520] 企业微信推送失败: {msg}", flush=True)

        return {
            'pushed': push_count,
            'failed': fail_count,
            'skipped': skip_count,
            'push_list_size': len(push_list),
            'success': success,
            'message': msg,
        }

    def run_scan_and_push(self, scan_source: str = '09:30',
                          max_stocks: int = 0, use_cache: bool = True,
                          push_wechat: bool = True) -> Dict:
        """执行扫描并推送
        Args:
            scan_source: 扫描来源（09:30/14:45/manual/premarket）
            max_stocks: 最大扫描股票数，0表示全部
            use_cache: 是否使用缓存
            push_wechat: 是否推送企业微信（True=扫描后自动推送，False=只扫描不推送）
        """
        print(f"[AI520] 开始扫描 (来源:{scan_source}, 推送:{push_wechat})")
        # 扫描
        scan_result = self.scan_market(scan_source=scan_source, max_stocks=max_stocks, use_cache=use_cache)
        signals = scan_result.get('signals', [])
        print(f"[AI520] 全市场扫描: {scan_result.get('total_scanned', 0)} 有效候选: {len(signals)}")

        # V2.7.1全量修复：扫描完成后强制刷新实时行情（禁止复用历史缓存价格）
        if signals:
            print(f"[行情刷新] 开始强制刷新{len(signals)}只信号股实时行情...", flush=True)
            signals, quote_stats = refresh_signal_quotes(signals, force=True)
            scan_result['signals'] = signals
            scan_result['quote_refresh_stats'] = quote_stats
            print(f"[行情刷新] 完成: 成功{quote_stats['refreshed']}/{quote_stats['total']}只 "
                  f"一致性偏差{quote_stats['consistency_issues']}处 耗时{quote_stats['duration']}秒", flush=True)

            # V2.7.1全量修复：批量匹配概念跟随（三维度综合匹配+细分概念优先）
            if signals:
                print(f"[概念匹配] 开始批量匹配{len(signals)}只信号股概念...", flush=True)
                signals = batch_match_concepts(signals)
                scan_result['signals'] = signals
                concept_count = sum(1 for s in signals if not s.get('concept_is_fallback', True))
                print(f"[概念匹配] 完成: 细分概念{concept_count}/{len(signals)}只", flush=True)

        # 按等级统计
        grades = {}
        for s in signals:
            g = s.get('grade', 'D')
            grades[g] = grades.get(g, 0) + 1
        print(f"[AI520] S+:{grades.get('S+',0)} S:{grades.get('S',0)} A:{grades.get('A',0)} B:{grades.get('B',0)} C:{grades.get('C',0)} D:{grades.get('D',0)}")

        # 推送
        push_result = None
        if push_wechat and signals:
            print(f"[WECHAT] 开始生成正式消息 (类型:{scan_source}, 股票数量:{len(signals)})")
            push_result = self.push_signals_to_wechat(signals, scan_source)
            if push_result and push_result.get('success'):
                if push_result.get('skipped', 0) > 0 and push_result.get('pushed', 0) == 0:
                    print(f"[WECHAT] 企业微信推送正常跳过（无S/A级信号，共{push_result['skipped']}只低等级）")
                else:
                    print(f"[WECHAT] 企业微信发送成功, push_records写入成功")
            else:
                error_msg = push_result.get('error', '未知错误') if push_result else '无结果'
                print(f"[WECHAT] 企业微信发送失败: {error_msg}", flush=True)
                if push_result:
                    print(f"[WECHAT] 详细返回: {push_result}", flush=True)
        elif push_wechat and not signals:
            print(f"[AI520] 无信号股票，跳过企业微信推送")

        return {
            'scan': scan_result,
            'push': push_result,
            'signals': signals,
            'grades': grades,
        }


def get_ai520_scan_service() -> AI520ScanService:
    return AI520ScanService()


if __name__ == '__main__':
    print("AI-520扫描服务自测")
    print("=" * 60)

    service = AI520ScanService()

    # 测试Webhook加载
    webhook = service.load_env_webhook()
    print(f"Webhook配置: {'已配置' if webhook else '未配置'}")

    # 测试DuckDB股票列表
    stocks = service.get_stock_list_from_duckdb()
    print(f"DuckDB股票列表: {len(stocks)}只")

    # 测试单只股票K线获取
    if stocks:
        test_code = stocks[0]['code']
        kline = service.get_kline(test_code, days=200)
        print(f"测试股票 {test_code}: K线{len(kline) if kline else 0}根")
        if kline:
            print(f"  最新日期: {kline[-1]['date']}, 收盘: {kline[-1]['close']}")

    print("\n扫描服务自测完成")
