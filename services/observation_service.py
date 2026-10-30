# -*- coding: utf-8 -*-
"""
AI-520 一周观察服务
完整闭环：AI-520扫描→入选事件→观察任务→每日更新→D1-D5→统计→日报→企业微信
"""
import os
import sys
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from strategy.ai_520_database import AI520Database
from utils.kline_fetcher import fetch_kline


class ObservationCalculator:
    """AI-520观察统一收益计算器
    所有页面/日报/企业微信/图表必须调用同一个计算器，确保数据一致
    """

    @staticmethod
    def calc_current_change(current_price: float, prev_close: float) -> float:
        """当日涨跌幅: (current_price/prev_close - 1) * 100"""
        if prev_close <= 0 or current_price <= 0:
            return 0.0
        return round((current_price / prev_close - 1) * 100, 2)

    @staticmethod
    def calc_cumulative_return(current_price: float, selection_price: float) -> float:
        """累计收益: (current_price/selection_price - 1) * 100"""
        if selection_price <= 0 or current_price <= 0:
            return 0.0
        return round((current_price / selection_price - 1) * 100, 2)

    @staticmethod
    def calc_high_gain(week_high: float, selection_price: float) -> float:
        """最高收益: (week_high/selection_price - 1) * 100"""
        if selection_price <= 0 or week_high <= 0:
            return 0.0
        return round((week_high / selection_price - 1) * 100, 2)

    @staticmethod
    def calc_low_gain(week_low: float, selection_price: float) -> float:
        """最低收益: (week_low/selection_price - 1) * 100"""
        if selection_price <= 0 or week_low <= 0:
            return 0.0
        return round((week_low / selection_price - 1) * 100, 2)

    @staticmethod
    def calc_max_drawdown(prices: List[float]) -> float:
        """最大回撤: 从历史最高点计算最大跌幅，返回负值
        prices: 观察期间的收盘价列表（按时间顺序）
        """
        if not prices or len(prices) < 2:
            return 0.0
        running_high = prices[0]
        max_dd = 0.0
        for p in prices[1:]:
            if p > running_high:
                running_high = p
            if running_high > 0:
                dd = (p / running_high - 1) * 100
                if dd < max_dd:
                    max_dd = dd
        return round(max_dd, 2)

    @staticmethod
    def calc_ma(closes: List[float], period: int) -> float:
        """计算简单移动平均SMA"""
        if not closes or len(closes) < period:
            return 0.0
        return round(sum(closes[-period:]) / period, 2)

    @staticmethod
    def calc_trend_state(current_price: float, ma5: float, ma20: float,
                          prev_ma5: float = 0, prev_ma20: float = 0) -> str:
        """计算趋势状态
        TREND_KEEP: 趋势保持（价格>MA5>MA20，均线向上）
        TREND_WATCH: 震荡观察
        BREAK_MA5: 跌破MA5
        BREAK_MA20: 跌破MA20
        REGAIN_MA5: 重新站回MA5
        AI520_INVALID: AI-520条件消失
        """
        if current_price <= 0:
            return 'DATA_PENDING'
        if ma20 > 0 and current_price < ma20 * 0.97:
            return 'BREAK_MA20'
        if ma5 > 0 and current_price < ma5 * 0.98:
            if prev_ma5 > 0 and current_price >= prev_ma5:
                return 'REGAIN_MA5'
            return 'BREAK_MA5'
        if ma5 > 0 and ma20 > 0 and current_price >= ma5 and ma5 >= ma20:
            if prev_ma5 > 0 and ma5 >= prev_ma5:
                return 'TREND_KEEP'
            return 'TREND_WATCH'
        return 'TREND_WATCH'

    @staticmethod
    def validate_data(open_p: float, high: float, low: float, close: float,
                      selection_price: float) -> Tuple[bool, str]:
        """数据准确性自检
        返回: (是否有效, 错误原因)
        """
        if close <= 0:
            return False, 'CLOSE_ZERO'
        if selection_price <= 0:
            return False, 'SELECTION_PRICE_ZERO'
        if high < low:
            return False, 'HIGH_LOW_INVALID'
        if high < close or high < open_p:
            return False, 'HIGH_INVALID'
        if low > close or low > open_p:
            return False, 'LOW_INVALID'
        return True, 'OK'


class ObservationService:
    """AI-520 一周观察服务"""

    def __init__(self, db: Optional[AI520Database] = None):
        self.db = db or AI520Database()
        self._daily_update_lock_table = {}

    # ==================== 交易日历判断 ====================

    def get_latest_trade_date(self) -> Optional[str]:
        """获取最近一个交易日（通过检查K线数据）"""
        try:
            # 用一只活跃股票检查最近交易日
            kline = fetch_kline('000001', days=10)
            if kline and len(kline) > 0:
                latest = kline[-1]
                date_str = latest.get('date', '') or latest.get('trade_date', '')
                if date_str:
                    return date_str.replace('-', '')
        except Exception as e:
            print(f"[OBS] 获取最近交易日失败: {e}", flush=True)
        return None

    def is_trade_day(self, date_str: str) -> bool:
        """判断是否为交易日（简单判断：周一到周五，节假日通过K线验证）"""
        try:
            dt = datetime.strptime(date_str, '%Y%m%d')
            if dt.weekday() >= 5:  # 周六周日
                return False
            # 验证：获取该日K线，如果有数据则是交易日
            kline = fetch_kline('000001', days=30)
            if kline:
                for k in kline:
                    k_date = (k.get('date', '') or k.get('trade_date', '')).replace('-', '')
                    if k_date == date_str:
                        return True
                # 如果最近K线日期小于目标日期，可能是节假日
                latest_date = (kline[-1].get('date', '') or '').replace('-', '')
                if latest_date < date_str:
                    return False
            return True
        except Exception:
            return False

    def get_trade_days_between(self, start_date: str, end_date: str) -> int:
        """计算两个日期之间的交易日数量（包含end_date，不包含start_date）"""
        try:
            start_dt = datetime.strptime(start_date, '%Y%m%d')
            end_dt = datetime.strptime(end_date, '%Y%m%d')
            count = 0
            current = start_dt + timedelta(days=1)
            while current <= end_dt:
                date_str = current.strftime('%Y%m%d')
                if self.is_trade_day(date_str):
                    count += 1
                current += timedelta(days=1)
            return count
        except Exception:
            return 0

    # ==================== 观察任务管理 ====================

    def get_observing_tasks(self) -> List[Dict]:
        """获取所有观察中的任务"""
        conn = self.db._get_conn()
        try:
            rows = conn.execute("""
                SELECT id, signal_id, signal_date, signal_time, signal_source,
                       code, name, signal_price, signal_score, signal_grade, industry,
                       d0_date, d0_price, current_day, status
                FROM observation_pool
                WHERE status = '观察中'
                ORDER BY signal_date DESC, id
            """).fetchall()
            tasks = []
            for row in rows:
                tasks.append({
                    'id': row[0], 'signal_id': row[1], 'signal_date': row[2],
                    'signal_time': row[3], 'signal_source': row[4],
                    'code': row[5], 'name': row[6], 'signal_price': row[7],
                    'signal_score': row[8], 'signal_grade': row[9], 'industry': row[10],
                    'd0_date': row[11], 'd0_price': row[12],
                    'current_day': row[13], 'status': row[14]
                })
            return tasks
        finally:
            conn.close()

    def create_from_ai520_selection(self, signal: Dict, signal_id: int) -> Optional[int]:
        """
        从AI-520入选事件创建观察任务
        防重复：同一天同一股票只创建一次
        """
        code = signal.get('code', '')
        signal_date = signal.get('signal_date', '')

        # 防重复检查
        conn = self.db._get_conn()
        try:
            existing = conn.execute(
                "SELECT id FROM observation_pool WHERE code=? AND signal_date=?",
                (code, signal_date)
            ).fetchone()
            if existing:
                print(f"[OBS] {code} {signal_date} 已存在观察任务，跳过创建", flush=True)
                return existing[0]
        finally:
            conn.close()

        # 创建观察任务
        obs_id = self.db.add_to_observation(signal, signal_id)
        print(f"[OBS] 创建观察任务: {code} {signal.get('name', '')} obs_id={obs_id} 入选价={signal.get('price', 0)}", flush=True)
        return obs_id

    def create_batch_from_scan(self, signals: List[Dict], scan_id: int = 0,
                                 selection_date: str = '', selection_time: str = '') -> Dict:
        """
        从AI-520扫描结果创建观察批次+观察任务
        完整链路: AI520扫描结果 → Selection Event → ObservationBatch → ObservationTask
        Args:
            signals: AI-520扫描结果列表，每个包含code/name/price/score/grade/signal_type等
            scan_id: 扫描运行ID
            selection_date: 选股日期（YYYYMMDD）
            selection_time: 选股时间（HH:MM:SS）
        Returns: 批次创建结果
        """
        if not selection_date:
            selection_date = self.get_latest_trade_date() or datetime.now().strftime('%Y%m%d')
        if not selection_time:
            selection_time = datetime.now().strftime('%H:%M:%S')

        batch_id = f"AI520_{selection_date}"
        print(f"[OBS] ===== 创建观察批次 {batch_id} =====", flush=True)
        print(f"[OBS] AI-520扫描结果: {len(signals)}只信号", flush=True)

        # 创建批次
        batch_pk = self.db.create_batch(
            batch_id=batch_id,
            strategy='AI520',
            selection_date=selection_date,
            selection_time=selection_time,
            scan_id=scan_id,
            candidate_count=len(signals)
        )

        # 为每个信号创建观察任务
        created = 0
        skipped = 0
        errors = []

        for signal in signals:
            try:
                code = signal.get('code', '')
                name = signal.get('name', '')
                price = signal.get('price', signal.get('signal_price', 0))
                score = signal.get('total_score', signal.get('score', signal.get('signal_score', 0)))
                grade = signal.get('grade', signal.get('signal_grade', ''))
                pullback_type = signal.get('signal_type', signal.get('pullback_type', ''))

                if not code or price <= 0:
                    skipped += 1
                    continue

                # 防重复：同一天同一股票只创建一次
                conn = self.db._get_conn()
                try:
                    existing = conn.execute(
                        "SELECT id FROM observation_pool WHERE code=? AND signal_date=?",
                        (code, selection_date)
                    ).fetchone()
                    if existing:
                        skipped += 1
                        continue
                finally:
                    conn.close()

                # 构建signal字典兼容add_to_observation
                obs_signal = {
                    'code': code,
                    'name': name,
                    'signal_date': selection_date,
                    'signal_time': selection_time,
                    'signal_source': 'AI520_SCAN',
                    'price': price,
                    'signal_price': price,
                    'total_score': score,
                    'signal_score': score,
                    'grade': grade,
                    'signal_grade': grade,
                    'industry': signal.get('industry', signal.get('sector_name', '')),
                    'pullback_type': pullback_type,
                    'entry_price_source': 'CLOSE' if selection_time >= '15:00' else 'REALTIME',
                    'entry_price_timestamp': f"{selection_date} {selection_time}",
                    'data_source': 'TDX',
                    'batch_id': batch_id,
                }

                # 创建观察任务
                obs_id = self.db.add_to_observation(obs_signal, scan_id)

                # 更新batch_id到observation_pool
                conn = self.db._get_conn()
                try:
                    conn.execute(
                        "UPDATE observation_pool SET batch_id=?, pullback_type=?, entry_price_source=?, entry_price_timestamp=?, data_source=? WHERE id=?",
                        (batch_id, pullback_type, obs_signal['entry_price_source'],
                         obs_signal['entry_price_timestamp'], 'TDX', obs_id)
                    )
                    conn.commit()
                finally:
                    conn.close()

                created += 1
                print(f"[OBS]   创建任务: {code} {name} 入选价={price:.2f} 评分={score} 等级={grade} 回踩={pullback_type}", flush=True)

            except Exception as e:
                errors.append(f"{signal.get('code', '?')}: {e}")
                print(f"[OBS]   创建任务失败: {signal.get('code', '?')} {e}", flush=True)

        result = {
            'batch_id': batch_id,
            'batch_pk': batch_pk,
            'selection_date': selection_date,
            'total_signals': len(signals),
            'created': created,
            'skipped': skipped,
            'errors': errors,
        }
        print(f"[OBS] ===== 批次创建完成: {batch_id} 创建{created}只 跳过{skipped}只 错误{len(errors)} =====", flush=True)
        return result

    def get_batch_summary(self) -> List[Dict]:
        """获取所有批次汇总（多批次同时观察）"""
        return self.db.get_active_batches()

    # ==================== 每日更新 ====================

    def daily_update(self, trade_date: Optional[str] = None) -> Dict:
        """
        每日收盘更新所有观察任务
        防重复：同一天只执行一次
        Returns: 更新统计
        """
        if trade_date is None:
            trade_date = self.get_latest_trade_date()

        if not trade_date:
            return {'success': False, 'error': '无法获取交易日', 'updated': 0}

        # 防重复锁
        if trade_date in self._daily_update_lock_table:
            print(f"[OBS] {trade_date} 已执行过每日更新，跳过", flush=True)
            return {'success': True, 'skipped': True, 'trade_date': trade_date, 'updated': 0}

        # 数据库级防重复检查
        conn = self.db._get_conn()
        try:
            # 检查observation_daily表中是否已有该日期记录
            existing = conn.execute(
                "SELECT COUNT(*) FROM observation_daily WHERE trade_date=?",
                (trade_date,)
            ).fetchone()[0]
            if existing > 0:
                print(f"[OBS] {trade_date} 已有{existing}条每日记录，跳过重复更新", flush=True)
                self._daily_update_lock_table[trade_date] = True
                return {'success': True, 'skipped': True, 'trade_date': trade_date, 'updated': 0}
        finally:
            conn.close()

        print(f"[OBS] ===== 开始每日更新 {trade_date} =====", flush=True)

        tasks = self.get_observing_tasks()
        print(f"[OBS] 观察中任务: {len(tasks)}只", flush=True)

        stats = {
            'trade_date': trade_date,
            'total_tasks': len(tasks),
            'updated': 0,
            'd1': 0, 'd2': 0, 'd3': 0, 'd4': 0, 'd5': 0, 'd6': 0, 'd7': 0,
            'completed': 0,
            'data_pending': 0,
            'errors': []
        }

        for task in tasks:
            try:
                result = self._update_single_task(task, trade_date)
                if result.get('updated'):
                    stats['updated'] += 1
                    day = result.get('day_number', 0)
                    if day == 1: stats['d1'] += 1
                    elif day == 2: stats['d2'] += 1
                    elif day == 3: stats['d3'] += 1
                    elif day == 4: stats['d4'] += 1
                    elif day == 5: stats['d5'] += 1
                    elif day == 6: stats['d6'] += 1
                    elif day == 7: stats['d7'] += 1
                    if result.get('completed'):
                        stats['completed'] += 1
                elif result.get('data_pending'):
                    stats['data_pending'] += 1
            except Exception as e:
                stats['errors'].append(f"{task.get('code')}: {e}")
                print(f"[OBS] {task.get('code')} 更新异常: {e}", flush=True)

        self._daily_update_lock_table[trade_date] = True
        print(f"[OBS] ===== 每日更新完成: 更新{stats['updated']}只 D1={stats['d1']} D2={stats['d2']} D3={stats['d3']} D4={stats['d4']} D5={stats['d5']} D6={stats['d6']} D7={stats['d7']} 完成={stats['completed']} =====", flush=True)
        return stats

    def _update_single_task(self, task: Dict, trade_date: str) -> Dict:
        """更新单只观察任务（V2.3增强：D0-D7+最大回撤+趋势状态+MA5/MA20+数据血缘）"""
        code = task['code']
        signal_date = task['signal_date'].replace('-', '')
        signal_price = task['signal_price']
        current_day = task.get('current_day', 0)

        # 计算当前是第几个交易日
        day_number = self.get_trade_days_between(signal_date, trade_date)

        # 如果day_number <= current_day，说明已经更新过
        if day_number <= current_day:
            return {'updated': False, 'skipped': True}

        # 如果day_number > 7，标记为完成
        if day_number > 7:
            conn = self.db._get_conn()
            try:
                conn.execute("UPDATE observation_pool SET status='已完成', updated_at=CURRENT_TIMESTAMP WHERE id=?", (task['id'],))
                conn.commit()
            finally:
                conn.close()
            return {'updated': True, 'day_number': day_number, 'completed': True}

        # 获取K线数据（获取足够历史计算MA和最大回撤）
        kline = fetch_kline(code, days=60)
        if not kline or len(kline) == 0:
            print(f"[OBS] {code} 无法获取K线数据", flush=True)
            return {'updated': False, 'data_pending': True}

        # 找到trade_date对应的K线
        target_kline = None
        target_idx = -1
        for i, k in enumerate(reversed(kline)):
            k_date = (k.get('date', '') or k.get('trade_date', '')).replace('-', '')
            if k_date == trade_date:
                target_kline = k
                target_idx = len(kline) - 1 - i
                break

        if not target_kline:
            print(f"[OBS] {code} 未找到{trade_date}的K线", flush=True)
            return {'updated': False, 'data_pending': True}

        close_price = target_kline.get('close', 0)
        open_price = target_kline.get('open', 0)
        high_price = target_kline.get('high', 0)
        low_price = target_kline.get('low', 0)
        volume = target_kline.get('volume', 0)

        # 数据准确性自检
        valid, err_reason = ObservationCalculator.validate_data(open_price, high_price, low_price, close_price, signal_price)
        if not valid:
            print(f"[OBS] {code} 数据异常: {err_reason}", flush=True)
            return {'updated': False, 'data_error': err_reason}

        # 获取前一天收盘价计算当日涨跌幅
        prev_close = 0
        if target_idx > 0:
            prev_close = kline[target_idx - 1].get('close', 0)

        # 统一计算器计算
        current_change = ObservationCalculator.calc_current_change(close_price, prev_close)
        cumulative_return = ObservationCalculator.calc_cumulative_return(close_price, signal_price)

        # 计算观察期间最高/最低/最大回撤
        # 从signal_date之后到trade_date的所有收盘价
        obs_closes = []
        for k in kline:
            k_date = (k.get('date', '') or k.get('trade_date', '')).replace('-', '')
            if signal_date <= k_date <= trade_date:
                c = k.get('close', 0)
                if c > 0:
                    obs_closes.append(c)
        week_high = max(obs_closes) if obs_closes else high_price
        week_low = min(obs_closes) if obs_closes else low_price
        high_gain = ObservationCalculator.calc_high_gain(week_high, signal_price)
        low_gain = ObservationCalculator.calc_low_gain(week_low, signal_price)
        max_drawdown = ObservationCalculator.calc_max_drawdown(obs_closes)

        # 计算MA5/MA20
        closes_up_to = [k.get('close', 0) for k in kline[:target_idx + 1] if k.get('close', 0) > 0]
        ma5 = ObservationCalculator.calc_ma(closes_up_to, 5)
        ma20 = ObservationCalculator.calc_ma(closes_up_to, 20)

        # 前一天MA5用于趋势判断
        prev_ma5 = 0
        if len(closes_up_to) >= 6:
            prev_ma5 = ObservationCalculator.calc_ma(closes_up_to[:-1], 5)

        # 趋势状态
        trend_state = ObservationCalculator.calc_trend_state(close_price, ma5, ma20, prev_ma5)

        # 更新观察池主表（d1-d7字段）
        self.db.update_observation_daily(task['id'], day_number, trade_date, target_kline)

        # 写入observation_daily明细表（扩展字段）
        conn = self.db._get_conn()
        try:
            # 防重复：检查是否已存在
            existing = conn.execute(
                "SELECT id FROM observation_daily WHERE observation_id=? AND trade_date=?",
                (task['id'], trade_date)
            ).fetchone()
            if existing:
                print(f"[OBS] {code} {trade_date} 每日记录已存在，跳过", flush=True)
                return {'updated': False, 'skipped': True}

            row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM observation_daily").fetchone()
            daily_id = row[0]
            source_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            conn.execute("""
                INSERT INTO observation_daily (
                    id, observation_id, code, trade_date, day_number,
                    open_price, close_price, high_price, low_price, volume, pct_from_signal,
                    current_change, cumulative_return, high_gain, low_gain, max_drawdown,
                    ma5, ma20, trend_state, source, source_time, data_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                daily_id, task['id'], code, trade_date, day_number,
                open_price, close_price, high_price, low_price, volume, cumulative_return,
                current_change, cumulative_return, high_gain, low_gain, max_drawdown,
                ma5, ma20, trend_state, 'TDX_CLOSE', source_time, 'OK'
            ))

            # 更新observation_pool的趋势状态和最大回撤
            conn.execute("""
                UPDATE observation_pool SET
                    trend_state=?, max_drawdown=?, current_day=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (trend_state, max_drawdown, day_number, task['id']))

            conn.commit()
        finally:
            conn.close()

        print(f"[OBS] {code} D{day_number} 更新: 收盘={close_price:.2f} 当日={current_change:+.2f}% 累计={cumulative_return:+.2f}% 最高={high_gain:+.2f}% 回撤={max_drawdown:.2f}% 趋势={trend_state}", flush=True)
        return {
            'updated': True, 'day_number': day_number,
            'current_change': current_change,
            'cumulative_return': cumulative_return,
            'high_gain': high_gain,
            'max_drawdown': max_drawdown,
            'trend_state': trend_state,
            'ma5': ma5, 'ma20': ma20
        }

    # ==================== 统计 ====================

    def get_observation_stats(self) -> Dict:
        """获取观察池统计"""
        return self.db.get_observation_stats()

    def get_daily_performance(self, day_number: int) -> Dict:
        """获取第N天的表现统计"""
        conn = self.db._get_conn()
        try:
            day_field = f'd{day_number}_pct'
            rows = conn.execute(f"""
                SELECT code, name, signal_date, {day_field} as pct
                FROM observation_pool
                WHERE {day_field} IS NOT NULL
                ORDER BY {day_field} DESC
            """).fetchall()

            if not rows:
                return {'count': 0, 'avg_return': 0, 'win_rate': 0, 'details': []}

            pcts = [r[3] for r in rows if r[3] is not None]
            win_count = sum(1 for p in pcts if p > 0)
            avg_return = sum(pcts) / len(pcts) if pcts else 0
            win_rate = win_count / len(pcts) * 100 if pcts else 0

            details = []
            for r in rows[:20]:
                details.append({
                    'code': r[0], 'name': r[1],
                    'signal_date': r[2], 'pct': r[3]
                })

            return {
                'count': len(pcts),
                'avg_return': round(avg_return, 2),
                'win_rate': round(win_rate, 2),
                'max_return': round(max(pcts), 2) if pcts else 0,
                'min_return': round(min(pcts), 2) if pcts else 0,
                'details': details
            }
        finally:
            conn.close()

    # ==================== 日报生成 ====================

    def generate_daily_report(self, trade_date: Optional[str] = None) -> str:
        """生成AI-520一周观察日报（V2.3增强：多批次+D1-D7+趋势状态）"""
        if trade_date is None:
            trade_date = self.get_latest_trade_date() or datetime.now().strftime('%Y%m%d')

        stats = self.get_observation_stats()
        observing = stats.get('observing', 0)
        completed = stats.get('completed', 0)
        total = stats.get('total', 0)

        # 获取活跃批次（多批次同时观察）
        batches = self.get_batch_summary()

        lines = []
        lines.append(f"📊【AI-520｜一周观察日报】")
        lines.append(f"日期: {trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}")
        lines.append(f"━━━━━━━━━━━━━━━━━━")
        lines.append(f"📈 观察概况")
        lines.append(f"当前观察中: {observing}只  已完成: {completed}只  累计: {total}只")

        # 多批次汇总
        if batches:
            lines.append(f"")
            lines.append(f"📦 活跃批次 ({len(batches)}个)")
            for b in batches[:5]:
                bdate = b.get('selection_date', '')
                bdate_fmt = f"{bdate[:4]}-{bdate[4:6]}-{bdate[6:8]}" if len(bdate) >= 8 else bdate
                lines.append(f"  {b.get('batch_id', '')} 选股日:{bdate_fmt} 候选:{b.get('candidate_count', 0)}只 任务:{b.get('task_count', 0)}只 状态:{b.get('status', '')}")
            if len(batches) > 5:
                lines.append(f"  ...等共{len(batches)}个批次")

        lines.append(f"")

        # D1-D7表现
        for day in [1, 2, 3, 4, 5, 6, 7]:
            perf = self.get_daily_performance(day)
            if perf['count'] > 0:
                lines.append(f"📊 D{day}表现 (样本{perf['count']}只)")
                lines.append(f"  平均收益: {perf['avg_return']:+.2f}%  胜率: {perf['win_rate']:.1f}%")
                lines.append(f"  最大收益: {perf['max_return']:+.2f}%  最大亏损: {perf['min_return']:+.2f}%")
                lines.append(f"")

        # 趋势状态统计
        conn = self.db._get_conn()
        try:
            trend_rows = conn.execute("""
                SELECT trend_state, COUNT(*) as cnt
                FROM observation_pool
                WHERE status='观察中' AND trend_state IS NOT NULL
                GROUP BY trend_state
                ORDER BY cnt DESC
            """).fetchall()
            if trend_rows:
                lines.append(f"📊 趋势状态分布")
                for tr in trend_rows:
                    lines.append(f"  {tr[0]}: {tr[1]}只")
                lines.append(f"")
        finally:
            conn.close()

        # 当前观察中股票（TOP15）
        tasks = self.get_observing_tasks()
        if tasks:
            lines.append(f"🔍 当前观察中股票 ({len(tasks)}只，显示前15)")
            for t in tasks[:15]:
                code = t['code']
                name = t['name']
                price = t.get('signal_price', 0)
                day = t.get('current_day', 0)
                score = t.get('signal_score', 0)
                grade = t.get('signal_grade', '')
                trend = t.get('trend_state', '') if 'trend_state' in t else ''
                lines.append(f"  {code} {name} 入选价:{price:.2f} D{day} 评分:{score} {grade} {trend}")
            if len(tasks) > 15:
                lines.append(f"  ...等共{len(tasks)}只")
            lines.append(f"")

        lines.append(f"📊 数据来源: AI-520战法模型真实扫描+每日真实行情跟踪")
        lines.append(f"🕒 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return '\n'.join(lines)


# 单例
_observation_service = None

def get_observation_service() -> ObservationService:
    global _observation_service
    if _observation_service is None:
        _observation_service = ObservationService()
    return _observation_service
