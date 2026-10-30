# -*- coding: utf-8 -*-
"""
AI-520数据库模块
DuckDB存储：信号、观察池、推送记录、扫描运行
"""
import os
import sys
import json
import duckdb
from typing import Dict, List, Optional
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'ai520_cache.duckdb')


class AI520Database:
    """AI-520数据库"""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_tables()

    def _get_conn(self):
        return duckdb.connect(self.db_path)

    def _init_tables(self):
        """初始化数据表"""
        conn = self._get_conn()
        try:
            # 信号表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY,
                    signal_date VARCHAR,
                    signal_time VARCHAR,
                    signal_source VARCHAR,
                    code VARCHAR,
                    name VARCHAR,
                    price DOUBLE,
                    pct_chg DOUBLE,
                    industry VARCHAR,
                    market_cap DOUBLE,
                    total_score DOUBLE,
                    grade VARCHAR,
                    grade_name VARCHAR,
                    ma5 DOUBLE,
                    ma10 DOUBLE,
                    ma20 DOUBLE,
                    ma20_trend VARCHAR,
                    cross_days_ago INTEGER,
                    today_cross BOOLEAN,
                    vol_ratio DOUBLE,
                    vol_status VARCHAR,
                    limit_count_1y INTEGER,
                    limit_count_20d INTEGER,
                    dist_from_8m_high DOUBLE,
                    break_10d_high BOOLEAN,
                    sector_name VARCHAR,
                    sector_pct DOUBLE,
                    sector_rank INTEGER,
                    sector_limit_up INTEGER,
                    sector_fund_flow DOUBLE,
                    news_status VARCHAR,
                    reasons VARCHAR,
                    risks VARCHAR,
                    score_details VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 观察池表（7交易日观察）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS observation_pool (
                    id INTEGER PRIMARY KEY,
                    signal_id INTEGER,
                    signal_date VARCHAR,
                    signal_time VARCHAR,
                    signal_source VARCHAR,
                    code VARCHAR,
                    name VARCHAR,
                    signal_price DOUBLE,
                    signal_score DOUBLE,
                    signal_grade VARCHAR,
                    industry VARCHAR,
                    d0_date VARCHAR,
                    d0_price DOUBLE,
                    d1_date VARCHAR,
                    d1_price DOUBLE,
                    d1_pct DOUBLE,
                    d2_date VARCHAR,
                    d2_price DOUBLE,
                    d2_pct DOUBLE,
                    d3_date VARCHAR,
                    d3_price DOUBLE,
                    d3_pct DOUBLE,
                    d4_date VARCHAR,
                    d4_price DOUBLE,
                    d4_pct DOUBLE,
                    d5_date VARCHAR,
                    d5_price DOUBLE,
                    d5_pct DOUBLE,
                    d6_date VARCHAR,
                    d6_price DOUBLE,
                    d6_pct DOUBLE,
                    d7_date VARCHAR,
                    d7_price DOUBLE,
                    d7_pct DOUBLE,
                    max_return DOUBLE,
                    min_return DOUBLE,
                    max_drawdown DOUBLE,
                    current_day INTEGER DEFAULT 0,
                    status VARCHAR DEFAULT '观察中',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 推送记录表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS push_records (
                    id INTEGER PRIMARY KEY,
                    push_date VARCHAR,
                    push_time VARCHAR,
                    signal_source VARCHAR,
                    code VARCHAR,
                    name VARCHAR,
                    grade VARCHAR,
                    total_score DOUBLE,
                    push_type VARCHAR,
                    push_status VARCHAR,
                    error_msg VARCHAR,
                    message_id VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 扫描运行表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scan_runs (
                    id INTEGER PRIMARY KEY,
                    scan_date VARCHAR,
                    scan_time VARCHAR,
                    scan_source VARCHAR,
                    total_stocks INTEGER,
                    filtered_stocks INTEGER,
                    signal_count INTEGER,
                    s_count INTEGER,
                    a_count INTEGER,
                    b_count INTEGER,
                    c_count INTEGER,
                    duration_seconds DOUBLE,
                    status VARCHAR,
                    error_msg VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 观察每日明细表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS observation_daily (
                    id INTEGER PRIMARY KEY,
                    observation_id INTEGER,
                    code VARCHAR,
                    trade_date VARCHAR,
                    day_number INTEGER,
                    open_price DOUBLE,
                    close_price DOUBLE,
                    high_price DOUBLE,
                    low_price DOUBLE,
                    volume DOUBLE,
                    pct_from_signal DOUBLE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 观察批次表（V2.3新增：多批次同时观察）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS observation_batch (
                    id INTEGER PRIMARY KEY,
                    batch_id VARCHAR UNIQUE,
                    strategy VARCHAR DEFAULT 'AI520',
                    selection_date VARCHAR,
                    selection_time VARCHAR,
                    scan_id INTEGER,
                    candidate_count INTEGER DEFAULT 0,
                    status VARCHAR DEFAULT 'ACTIVE',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 推送日志表（V2.3新增：防重复推送）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS report_push_log (
                    id INTEGER PRIMARY KEY,
                    report_date VARCHAR,
                    report_type VARCHAR,
                    batch_id VARCHAR,
                    page_no INTEGER DEFAULT 1,
                    total_pages INTEGER DEFAULT 1,
                    content_hash VARCHAR,
                    send_status VARCHAR,
                    sent_at TIMESTAMP,
                    http_status INTEGER,
                    response TEXT,
                    retry_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 字段迁移：observation_pool扩展字段（V2.3）
            self._add_column_if_not_exists(conn, 'observation_pool', 'batch_id', 'VARCHAR')
            self._add_column_if_not_exists(conn, 'observation_pool', 'pullback_type', 'VARCHAR')
            self._add_column_if_not_exists(conn, 'observation_pool', 'entry_price_source', 'VARCHAR')
            self._add_column_if_not_exists(conn, 'observation_pool', 'entry_price_timestamp', 'VARCHAR')
            self._add_column_if_not_exists(conn, 'observation_pool', 'data_source', 'VARCHAR')
            self._add_column_if_not_exists(conn, 'observation_pool', 'trend_state', 'VARCHAR')
            self._add_column_if_not_exists(conn, 'observation_pool', 'data_status', 'VARCHAR')

            # 字段迁移：observation_daily扩展字段（V2.3）
            self._add_column_if_not_exists(conn, 'observation_daily', 'current_change', 'DOUBLE')
            self._add_column_if_not_exists(conn, 'observation_daily', 'cumulative_return', 'DOUBLE')
            self._add_column_if_not_exists(conn, 'observation_daily', 'high_gain', 'DOUBLE')
            self._add_column_if_not_exists(conn, 'observation_daily', 'low_gain', 'DOUBLE')
            self._add_column_if_not_exists(conn, 'observation_daily', 'max_drawdown', 'DOUBLE')
            self._add_column_if_not_exists(conn, 'observation_daily', 'ma5', 'DOUBLE')
            self._add_column_if_not_exists(conn, 'observation_daily', 'ma20', 'DOUBLE')
            self._add_column_if_not_exists(conn, 'observation_daily', 'trend_state', 'VARCHAR')
            self._add_column_if_not_exists(conn, 'observation_daily', 'source', 'VARCHAR')
            self._add_column_if_not_exists(conn, 'observation_daily', 'source_time', 'VARCHAR')
            self._add_column_if_not_exists(conn, 'observation_daily', 'data_status', 'VARCHAR')

            conn.commit()
        finally:
            conn.close()

    def _add_column_if_not_exists(self, conn, table: str, column: str, col_type: str):
        """安全添加字段（如果不存在）"""
        try:
            # DuckDB: 检查列是否存在
            cols = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
            col_names = [c[1] for c in cols]
            if column not in col_names:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                print(f"[DB] {table} 新增字段: {column}", flush=True)
        except Exception as e:
            print(f"[DB] {table}.{column} 字段迁移跳过: {e}", flush=True)

    # ==================== 信号操作 ====================

    def save_signal(self, signal: Dict) -> int:
        """保存信号，返回信号ID"""
        conn = self._get_conn()
        try:
            # 获取下一个ID
            row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM signals").fetchone()
            signal_id = row[0]

            conn.execute("""
                INSERT INTO signals (
                    id, signal_date, signal_time, signal_source, code, name, price, pct_chg,
                    industry, market_cap, total_score, grade, grade_name,
                    ma5, ma10, ma20, ma20_trend, cross_days_ago, today_cross,
                    vol_ratio, vol_status, limit_count_1y, limit_count_20d,
                    dist_from_8m_high, break_10d_high,
                    sector_name, sector_pct, sector_rank, sector_limit_up, sector_fund_flow,
                    news_status, reasons, risks, score_details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal_id,
                signal.get('signal_date', ''),
                signal.get('signal_time', ''),
                signal.get('signal_source', ''),
                signal.get('code', ''),
                signal.get('name', ''),
                signal.get('price', 0),
                signal.get('pct_chg', 0),
                signal.get('industry', ''),
                signal.get('market_cap', 0),
                signal.get('total_score', 0),
                signal.get('grade', ''),
                signal.get('grade_name', ''),
                signal.get('cross_info', {}).get('ma5', 0),
                signal.get('cross_info', {}).get('ma10', 0),
                signal.get('cross_info', {}).get('ma20', 0),
                signal.get('cross_info', {}).get('ma20_trend', ''),
                signal.get('cross_info', {}).get('cross_days_ago', -1),
                signal.get('cross_info', {}).get('today_cross', False),
                signal.get('volume_info', {}).get('vol_ratio', 0),
                signal.get('volume_info', {}).get('vol_status', ''),
                signal.get('limit_count_1y', 0),
                signal.get('limit_count_20d', 0),
                signal.get('position_info', {}).get('dist_from_8m_high', 0),
                signal.get('position_info', {}).get('break_10d_high', False),
                signal.get('sector_name', ''),
                signal.get('sector_pct', 0),
                signal.get('sector_rank', 0),
                signal.get('sector_limit_up', 0),
                signal.get('sector_fund_flow', 0),
                signal.get('news_status', ''),
                json.dumps(signal.get('reasons', []), ensure_ascii=False),
                json.dumps(signal.get('risks', []), ensure_ascii=False),
                json.dumps(signal.get('score_details', []), ensure_ascii=False),
            ))
            conn.commit()
            return signal_id
        finally:
            conn.close()

    def get_today_signals(self, signal_date: str, signal_source: str = '') -> List[Dict]:
        """获取某日信号"""
        conn = self._get_conn()
        try:
            if signal_source:
                rows = conn.execute(
                    "SELECT * FROM signals WHERE signal_date=? AND signal_source=? ORDER BY total_score DESC",
                    (signal_date, signal_source)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM signals WHERE signal_date=? ORDER BY total_score DESC",
                    (signal_date,)
                ).fetchall()
            columns = [desc[0] for desc in conn.execute("SELECT * FROM signals LIMIT 1").description]
            return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()

    # ==================== 观察池操作 ====================

    def add_to_observation(self, signal: Dict, signal_id: int) -> int:
        """将信号加入7日观察池（V2.6防重复：同一signal_date+code只允许一条）"""
        conn = self._get_conn()
        try:
            signal_date = signal.get('signal_date', '')
            code = signal.get('code', '')

            # V2.6防重复：检查同一交易日+同一股票是否已存在
            existing = conn.execute(
                "SELECT id FROM observation_pool WHERE signal_date=? AND code=?",
                (signal_date, code)
            ).fetchone()
            if existing:
                print(f"[OBSERVATION] 重复跳过: {code} {signal_date} 已存在obs_id={existing[0]}", flush=True)
                return existing[0]

            row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM observation_pool").fetchone()
            obs_id = row[0]

            signal_price = signal.get('price', 0)

            conn.execute("""
                INSERT INTO observation_pool (
                    id, signal_id, signal_date, signal_time, signal_source,
                    code, name, signal_price, signal_score, signal_grade, industry,
                    d0_date, d0_price, current_day, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                obs_id, signal_id, signal_date,
                signal.get('signal_time', ''),
                signal.get('signal_source', ''),
                code,
                signal.get('name', ''),
                signal_price,
                signal.get('total_score', 0),
                signal.get('grade', ''),
                signal.get('industry', ''),
                signal_date, signal_price,
                0, '观察中'
            ))
            conn.commit()
            return obs_id
        finally:
            conn.close()

    def update_observation_daily(self, obs_id: int, day_number: int,
                                  trade_date: str, kline_data: Dict):
        """更新观察池某日数据"""
        conn = self._get_conn()
        try:
            # 获取信号基准价
            obs = conn.execute("SELECT signal_price FROM observation_pool WHERE id=?", (obs_id,)).fetchone()
            if not obs:
                return
            signal_price = obs[0]
            close_price = kline_data.get('close', 0)
            pct = (close_price - signal_price) / signal_price * 100 if signal_price > 0 else 0

            # 更新对应日期字段
            day_field = f'd{day_number}'
            conn.execute(f"""
                UPDATE observation_pool SET
                    {day_field}_date=?, {day_field}_price=?, {day_field}_pct=?,
                    current_day=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (trade_date, close_price, pct, day_number, obs_id))

            # 更新最高/最低收益
            if day_number >= 1:
                conn.execute("""
                    UPDATE observation_pool SET
                        max_return = COALESCE(
                            (SELECT MAX(v) FROM (
                                SELECT d1_pct as v UNION ALL SELECT d2_pct UNION ALL SELECT d3_pct
                                UNION ALL SELECT d4_pct UNION ALL SELECT d5_pct UNION ALL SELECT d6_pct
                                UNION ALL SELECT d7_pct
                            ) WHERE v IS NOT NULL), max_return),
                        min_return = COALESCE(
                            (SELECT MIN(v) FROM (
                                SELECT d1_pct as v UNION ALL SELECT d2_pct UNION ALL SELECT d3_pct
                                UNION ALL SELECT d4_pct UNION ALL SELECT d5_pct UNION ALL SELECT d6_pct
                                UNION ALL SELECT d7_pct
                            ) WHERE v IS NOT NULL), min_return)
                    WHERE id=?
                """, (obs_id,))

            # 第7天完成
            if day_number >= 7:
                conn.execute("UPDATE observation_pool SET status='已完成' WHERE id=?", (obs_id,))

            conn.commit()
        finally:
            conn.close()

    def get_observation_stats(self) -> Dict:
        """获取观察池统计"""
        conn = self._get_conn()
        try:
            total = conn.execute("SELECT COUNT(*) FROM observation_pool").fetchone()[0]
            completed = conn.execute("SELECT COUNT(*) FROM observation_pool WHERE status='已完成'").fetchone()[0]
            observing = conn.execute("SELECT COUNT(*) FROM observation_pool WHERE status='观察中'").fetchone()[0]

            # D7收益统计
            d7_stats = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN d7_pct > 0 THEN 1 ELSE 0 END) as profit_count,
                    AVG(d7_pct) as avg_return,
                    MAX(d7_pct) as max_return,
                    MIN(d7_pct) as min_return
                FROM observation_pool WHERE d7_pct IS NOT NULL
            """).fetchone()

            return {
                'total': total,
                'completed': completed,
                'observing': observing,
                'd7_total': d7_stats[0] or 0,
                'd7_profit_count': d7_stats[1] or 0,
                'd7_win_rate': round(d7_stats[1] / d7_stats[0] * 100, 2) if d7_stats[0] > 0 else 0,
                'd7_avg_return': round(d7_stats[2] or 0, 2),
                'd7_max_return': round(d7_stats[3] or 0, 2),
                'd7_min_return': round(d7_stats[4] or 0, 2),
            }
        finally:
            conn.close()

    # ==================== 观察批次操作（V2.3新增） ====================

    def create_batch(self, batch_id: str, strategy: str = 'AI520',
                     selection_date: str = '', selection_time: str = '',
                     scan_id: int = 0, candidate_count: int = 0) -> int:
        """创建观察批次，返回批次ID（自增主键）"""
        conn = self._get_conn()
        try:
            # 检查是否已存在
            existing = conn.execute("SELECT id FROM observation_batch WHERE batch_id=?", (batch_id,)).fetchone()
            if existing:
                return existing[0]
            row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM observation_batch").fetchone()
            batch_pk = row[0]
            conn.execute("""
                INSERT INTO observation_batch (id, batch_id, strategy, selection_date, selection_time, scan_id, candidate_count, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVE')
            """, (batch_pk, batch_id, strategy, selection_date, selection_time, scan_id, candidate_count))
            conn.commit()
            print(f"[DB] 创建观察批次: {batch_id} 候选{candidate_count}只", flush=True)
            return batch_pk
        finally:
            conn.close()

    def get_batch(self, batch_id: str) -> Optional[Dict]:
        """获取批次信息"""
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT * FROM observation_batch WHERE batch_id=?", (batch_id,)).fetchone()
            if not row:
                return None
            cols = [d[0] for d in conn.description]
            return dict(zip(cols, row))
        finally:
            conn.close()

    def get_active_batches(self) -> List[Dict]:
        """获取所有活跃批次"""
        conn = self._get_conn()
        try:
            rows = conn.execute("""
                SELECT b.id, b.batch_id, b.strategy, b.selection_date, b.selection_time,
                       b.scan_id, b.candidate_count, b.status, b.created_at,
                       COUNT(p.id) as task_count
                FROM observation_batch b
                LEFT JOIN observation_pool p ON p.batch_id = b.batch_id
                WHERE b.status = 'ACTIVE'
                GROUP BY b.id, b.batch_id, b.strategy, b.selection_date, b.selection_time,
                         b.scan_id, b.candidate_count, b.status, b.created_at
                ORDER BY b.selection_date DESC
            """).fetchall()
            cols = [d[0] for d in conn.description]
            return [dict(zip(cols, r)) for r in rows]
        finally:
            conn.close()

    def update_batch_status(self, batch_id: str, status: str):
        """更新批次状态"""
        conn = self._get_conn()
        try:
            conn.execute("UPDATE observation_batch SET status=? WHERE batch_id=?", (status, batch_id))
            conn.commit()
        finally:
            conn.close()

    def get_tasks_by_batch(self, batch_id: str) -> List[Dict]:
        """获取批次下的所有观察任务"""
        conn = self._get_conn()
        try:
            rows = conn.execute("""
                SELECT id, batch_id, signal_date, code, name, signal_price, signal_score,
                       signal_grade, pullback_type, current_day, status, entry_price_source,
                       trend_state, data_status
                FROM observation_pool
                WHERE batch_id=?
                ORDER BY signal_score DESC
            """, (batch_id,)).fetchall()
            cols = [d[0] for d in conn.description]
            return [dict(zip(cols, r)) for r in rows]
        finally:
            conn.close()

    # ==================== 推送日志操作（V2.3新增） ====================

    def save_report_push_log(self, log: Dict) -> int:
        """保存推送日志，返回ID"""
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM report_push_log").fetchone()
            log_id = row[0]
            conn.execute("""
                INSERT INTO report_push_log (
                    id, report_date, report_type, batch_id, page_no, total_pages,
                    content_hash, send_status, sent_at, http_status, response, retry_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                log_id,
                log.get('report_date', ''),
                log.get('report_type', ''),
                log.get('batch_id', ''),
                log.get('page_no', 1),
                log.get('total_pages', 1),
                log.get('content_hash', ''),
                log.get('send_status', ''),
                log.get('sent_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                log.get('http_status', 0),
                log.get('response', ''),
                log.get('retry_count', 0),
            ))
            conn.commit()
            return log_id
        finally:
            conn.close()

    def check_report_push_exists(self, report_date: str, report_type: str,
                                  batch_id: str = '', page_no: int = 1) -> bool:
        """检查推送是否已存在（防重复）"""
        conn = self._get_conn()
        try:
            if batch_id:
                row = conn.execute("""
                    SELECT COUNT(*) FROM report_push_log
                    WHERE report_date=? AND report_type=? AND batch_id=? AND page_no=? AND send_status='SUCCESS'
                """, (report_date, report_type, batch_id, page_no)).fetchone()
            else:
                row = conn.execute("""
                    SELECT COUNT(*) FROM report_push_log
                    WHERE report_date=? AND report_type=? AND page_no=? AND send_status='SUCCESS'
                """, (report_date, report_type, page_no)).fetchone()
            return row[0] > 0
        finally:
            conn.close()

    # ==================== 推送记录操作 ====================

    def save_push_record(self, record: Dict):
        """保存推送记录"""
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM push_records").fetchone()
            push_id = row[0]
            conn.execute("""
                INSERT INTO push_records (
                    id, push_date, push_time, signal_source, code, name, grade,
                    total_score, push_type, push_status, error_msg, message_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                push_id,
                record.get('push_date', ''),
                record.get('push_time', ''),
                record.get('signal_source', ''),
                record.get('code', ''),
                record.get('name', ''),
                record.get('grade', ''),
                record.get('total_score', 0),
                record.get('push_type', ''),
                record.get('push_status', ''),
                record.get('error_msg', ''),
                record.get('message_id', ''),
            ))
            conn.commit()
            return push_id
        finally:
            conn.close()

    def is_duplicate_push(self, push_date: str, code: str, signal_source: str) -> bool:
        """检查是否重复推送（同日同股同源）"""
        conn = self._get_conn()
        try:
            count = conn.execute("""
                SELECT COUNT(*) FROM push_records
                WHERE push_date=? AND code=? AND signal_source=? AND push_status='success'
            """, (push_date, code, signal_source)).fetchone()[0]
            return count > 0
        finally:
            conn.close()

    # ==================== 扫描运行记录 ====================

    def save_scan_run(self, run: Dict) -> int:
        """保存扫描运行记录"""
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM scan_runs").fetchone()
            run_id = row[0]
            conn.execute("""
                INSERT INTO scan_runs (
                    id, scan_date, scan_time, scan_source, total_stocks,
                    filtered_stocks, signal_count, s_count, a_count, b_count,
                    c_count, duration_seconds, status, error_msg
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id,
                run.get('scan_date', ''),
                run.get('scan_time', ''),
                run.get('scan_source', ''),
                run.get('total_stocks', 0),
                run.get('filtered_stocks', 0),
                run.get('signal_count', 0),
                run.get('s_count', 0),
                run.get('a_count', 0),
                run.get('b_count', 0),
                run.get('c_count', 0),
                run.get('duration_seconds', 0),
                run.get('status', ''),
                run.get('error_msg', ''),
            ))
            conn.commit()
            return run_id
        finally:
            conn.close()


def get_ai520_db() -> AI520Database:
    return AI520Database()


if __name__ == '__main__':
    print("AI-520数据库模块自测")
    db = AI520Database()
    print(f"数据库路径: {DB_PATH}")

    # 测试保存信号
    test_signal = {
        'signal_date': '2026-09-02',
        'signal_time': '09:30:00',
        'signal_source': '09:30',
        'code': '000001',
        'name': '平安银行',
        'price': 11.91,
        'pct_chg': 1.5,
        'industry': '银行',
        'market_cap': 2000,
        'total_score': 85.5,
        'grade': 'S',
        'grade_name': '重点启动',
        'cross_info': {'ma5': 11.8, 'ma10': 11.7, 'ma20': 11.5, 'ma20_trend': '向上', 'cross_days_ago': 0, 'today_cross': True},
        'volume_info': {'vol_ratio': 1.5, 'vol_status': '健康放量'},
        'limit_count_1y': 5,
        'limit_count_20d': 1,
        'position_info': {'dist_from_8m_high': -5.2, 'break_10d_high': True},
        'reasons': ['520今日金叉', 'MA20向上', '健康放量'],
        'risks': [],
        'score_details': ['520金叉:20', '趋势:15'],
    }
    sig_id = db.save_signal(test_signal)
    print(f"保存信号ID: {sig_id}")

    # 测试观察池
    obs_id = db.add_to_observation(test_signal, sig_id)
    print(f"观察池ID: {obs_id}")

    # 测试统计
    stats = db.get_observation_stats()
    print(f"观察池统计: {stats}")

    print("\n数据库自测完成")
