# -*- coding: utf-8 -*-
"""
强势主力行为选股系统 V1.2.4 - 本地K线持久化缓存（DuckDB）

第一次扫描后K线数据存本地，以后每天只拉最近1-2天增量，秒级加载。
"""
import os
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta

try:
    import duckdb
    _HAS_DUCKDB = True
except ImportError:
    _HAS_DUCKDB = False

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(PROJECT_ROOT, "data", "cache")
DB_PATH = os.path.join(CACHE_DIR, "kline_cache.duckdb")

# 表结构
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS kline_cache (
    code TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    amount REAL,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (code, date)
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_kline_code ON kline_cache(code);
CREATE INDEX IF NOT EXISTS idx_kline_date ON kline_cache(date);
"""


class KlineCacheDB:
    """本地K线持久化缓存（DuckDB）"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = None
        self._available = False
        self._lock_failed = False
        # V1.3.10：启动时清理孤立文件
        self._cleanup_old_files()
        # 初始化数据库（失败不崩溃）
        try:
            self._init_db()
        except Exception as e:
            print(f"[KLINE CACHE] 初始化异常（不影响扫描）: {e}", flush=True)
            self._available = False

    def _get_backup_db_path(self) -> str:
        """V1.3.10：生成带时间戳的备用数据库路径"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_dir = os.path.dirname(self.db_path)
        base_name = os.path.splitext(os.path.basename(self.db_path))[0]
        return os.path.join(base_dir, f"{base_name}_{timestamp}.duckdb")

    def _cleanup_old_files(self):
        """V1.3.10：清理孤立的wal文件和旧的备用缓存文件"""
        try:
            cache_dir = os.path.dirname(self.db_path)
            if not os.path.exists(cache_dir):
                return
            # 1. 清理孤立的.wal文件（对应的.duckdb不存在）
            for f in os.listdir(cache_dir):
                if f.endswith('.wal'):
                    duckdb_file = f[:-4]  # 去掉.wal
                    if not os.path.exists(os.path.join(cache_dir, duckdb_file)):
                        try:
                            os.remove(os.path.join(cache_dir, f))
                            print(f"[KLINE CACHE] 清理孤立wal文件: {f}", flush=True)
                        except Exception:
                            pass
            # 2. 清理旧的备用缓存文件（保留最新的2个）
            backup_files = []
            base_name = os.path.splitext(os.path.basename(self.db_path))[0]
            for f in os.listdir(cache_dir):
                if f.startswith(base_name + '_') and f.endswith('.duckdb'):
                    fpath = os.path.join(cache_dir, f)
                    backup_files.append((fpath, os.path.getmtime(fpath)))
            # 按修改时间降序排序，保留最新的2个
            backup_files.sort(key=lambda x: x[1], reverse=True)
            for fpath, _ in backup_files[2:]:
                try:
                    os.remove(fpath)
                    print(f"[KLINE CACHE] 清理旧备用缓存: {os.path.basename(fpath)}", flush=True)
                except Exception:
                    pass
        except Exception as e:
            print(f"[KLINE CACHE] 清理旧文件异常: {e}", flush=True)

    def _get_conn(self):
        """获取数据库连接（懒加载，V1.3.10增加锁定容错）"""
        if self._conn is not None:
            return self._conn
        if not _HAS_DUCKDB:
            print("[KLINE CACHE] duckdb未安装，K线缓存功能不可用", flush=True)
            return None
        # 尝试连接主文件
        try:
            self._conn = duckdb.connect(self.db_path, read_only=False)
            self._available = True
            return self._conn
        except Exception as e:
            err_str = str(e).lower()
            if 'lock' in err_str or 'another program' in err_str or 'cannot open' in err_str:
                # V1.3.10：文件被锁定，使用备用文件
                print(f"[CACHE WARN] {os.path.basename(self.db_path)}被锁定，尝试使用备用文件", flush=True)
                backup_path = self._get_backup_db_path()
                try:
                    self._conn = duckdb.connect(backup_path, read_only=False)
                    self.db_path = backup_path
                    self._available = True
                    self._lock_failed = True
                    print(f"[CACHE WARN] 使用备用缓存文件: {os.path.basename(backup_path)}", flush=True)
                    return self._conn
                except Exception as e2:
                    print(f"[CACHE WARN] 备用文件也连接失败: {e2}，K线缓存不可用", flush=True)
                    self._available = False
                    return None
            else:
                print(f"[KLINE CACHE] 连接失败: {e}，K线缓存不可用", flush=True)
                self._available = False
                return None

    def _init_db(self):
        """初始化数据库表结构"""
        conn = self._get_conn()
        if conn is None:
            return
        try:
            conn.execute(CREATE_TABLE_SQL)
            conn.execute(CREATE_INDEX_SQL)
        except Exception as e:
            print(f"[KLINE CACHE] 初始化数据库失败: {e}", flush=True)

    def get_kline(self, code: str, days: int = 120) -> Optional[List[Dict]]:
        """从本地缓存读取K线数据

        Args:
            code: 股票代码
            days: 需要的K线根数

        Returns:
            List[Dict] 格式的K线数据，缓存不足时返回None
        """
        conn = self._get_conn()
        if conn is None:
            return None
        try:
            sql = f"""
            SELECT date, open, high, low, close, volume, amount
            FROM kline_cache
            WHERE code = ?
            ORDER BY date DESC
            LIMIT {days}
            """
            result = conn.execute(sql, [code]).fetchall()
            if not result:
                return None
            # 转换为List[Dict]，按日期升序
            kline_list = []
            for row in reversed(result):
                kline_list.append({
                    'trade_date': row[0],
                    'open': float(row[1]) if row[1] else 0.0,
                    'high': float(row[2]) if row[2] else 0.0,
                    'low': float(row[3]) if row[3] else 0.0,
                    'close': float(row[4]) if row[4] else 0.0,
                    'volume': float(row[5]) if row[5] else 0.0,
                    'amount': float(row[6]) if row[6] else 0.0,
                })
            return kline_list
        except Exception as e:
            print(f"[KLINE CACHE] 读取{code}失败: {e}", flush=True)
            return None

    def save_kline(self, code: str, kline_data: List[Dict]):
        """批量写入/更新K线缓存

        Args:
            code: 股票代码
            kline_data: List[Dict] 格式的K线数据
        """
        conn = self._get_conn()
        if conn is None or not kline_data:
            return
        try:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            # 批量插入（UPSERT）
            rows = []
            for k in kline_data:
                date = k.get('trade_date') or k.get('date') or ''
                if not date:
                    continue
                rows.append((
                    code,
                    str(date),
                    float(k.get('open', 0)),
                    float(k.get('high', 0)),
                    float(k.get('low', 0)),
                    float(k.get('close', 0)),
                    float(k.get('volume', 0)),
                    float(k.get('amount', 0)),
                    now,
                ))
            if not rows:
                return
            # 使用临时表批量UPSERT
            conn.execute("CREATE TEMP TABLE IF NOT EXISTS tmp_kline AS SELECT * FROM kline_cache WHERE 1=0")
            conn.executemany("INSERT INTO tmp_kline VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
            conn.execute("""
                INSERT INTO kline_cache
                SELECT * FROM tmp_kline
                ON CONFLICT (code, date) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    amount = excluded.amount,
                    update_time = excluded.update_time
            """)
            conn.execute("DROP TABLE tmp_kline")
        except Exception as e:
            print(f"[KLINE CACHE] 保存{code}失败: {e}", flush=True)

    def get_last_date(self, code: str) -> Optional[str]:
        """返回该股票缓存的最新日期"""
        conn = self._get_conn()
        if conn is None:
            return None
        try:
            result = conn.execute(
                "SELECT MAX(date) FROM kline_cache WHERE code = ?", [code]
            ).fetchone()
            return result[0] if result and result[0] else None
        except Exception:
            return None

    def get_cached_codes(self) -> List[str]:
        """返回所有已缓存股票代码"""
        conn = self._get_conn()
        if conn is None:
            return []
        try:
            result = conn.execute("SELECT DISTINCT code FROM kline_cache").fetchall()
            return [r[0] for r in result]
        except Exception:
            return []

    def clean_expired(self, days: int = 30):
        """清理超过指定天数未更新的缓存

        Args:
            days: 保留天数，默认30天
        """
        conn = self._get_conn()
        if conn is None:
            return
        try:
            cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
            result = conn.execute(
                "DELETE FROM kline_cache WHERE update_time < ?", [cutoff]
            )
            deleted = result.rowcount if hasattr(result, 'rowcount') else 0
            if deleted > 0:
                print(f"[KLINE CACHE] 清理过期缓存: 删除{deleted}条记录", flush=True)
        except Exception as e:
            print(f"[KLINE CACHE] 清理过期缓存失败: {e}", flush=True)

    def cache_stats(self) -> Dict:
        """返回缓存统计信息"""
        conn = self._get_conn()
        if conn is None:
            return {'available': False}
        try:
            stock_count = conn.execute("SELECT COUNT(DISTINCT code) FROM kline_cache").fetchone()[0]
            kline_count = conn.execute("SELECT COUNT(*) FROM kline_cache").fetchone()[0]
            # 计算文件大小
            file_size = 0
            if os.path.exists(self.db_path):
                file_size = os.path.getsize(self.db_path)
            return {
                'available': True,
                'stock_count': stock_count,
                'kline_count': kline_count,
                'file_size_bytes': file_size,
                'file_size_mb': round(file_size / 1024 / 1024, 2),
                'db_path': self.db_path,
            }
        except Exception as e:
            return {'available': False, 'error': str(e)}

    def close(self):
        """关闭数据库连接"""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None


# ============================================================
# 全局单例
# ============================================================

_default_kline_db = None


def get_kline_cache_db() -> KlineCacheDB:
    """获取全局K线缓存数据库单例"""
    global _default_kline_db
    if _default_kline_db is None:
        _default_kline_db = KlineCacheDB()
    return _default_kline_db
