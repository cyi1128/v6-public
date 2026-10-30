"""
自选股管理系统
支持：三倍量阳线池、回踩池、突破池、集合竞价池、AI高评分池、自选股
"""
import sqlite3
from datetime import datetime
from core.database import DatabaseManager


class WatchlistManager:
    """自选股管理器"""

    # 股票池类型
    POOL_WATCHLIST = '自选股'
    POOL_TRIPLE_VOLUME = '三倍量阳线池'
    POOL_PULLBACK = '回踩池'
    POOL_BREAKOUT = '突破池'
    POOL_AUCTION = '集合竞价池'
    POOL_AI_HIGH = 'AI高评分池'

    ALL_POOLS = [
        POOL_WATCHLIST,
        POOL_TRIPLE_VOLUME,
        POOL_PULLBACK,
        POOL_BREAKOUT,
        POOL_AUCTION,
        POOL_AI_HIGH,
    ]

    def __init__(self, db_manager=None):
        self.db = db_manager or DatabaseManager()

    def add_to_watchlist(self, ts_code, name, pool_type=POOL_WATCHLIST,
                         stage='观察', ai_score=0, add_price=0, remark=''):
        """添加股票到自选/股票池"""
        conn = self.db._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO watchlist
                (ts_code, name, pool_type, stage, ai_score, add_price, add_time, remark)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (ts_code, name, pool_type, stage, ai_score, add_price,
                  datetime.now().strftime('%Y-%m-%d %H:%M:%S'), remark))
            conn.commit()
            return True
        except Exception as e:
            print(f"添加自选股失败: {e}")
            return False
        finally:
            conn.close()

    def remove_from_watchlist(self, ts_code, pool_type=None):
        """从自选/股票池移除"""
        conn = self.db._get_conn()
        cursor = conn.cursor()
        try:
            if pool_type:
                cursor.execute('DELETE FROM watchlist WHERE ts_code=? AND pool_type=?',
                               (ts_code, pool_type))
            else:
                cursor.execute('DELETE FROM watchlist WHERE ts_code=?', (ts_code,))
            conn.commit()
            return True
        except Exception as e:
            print(f"移除自选股失败: {e}")
            return False
        finally:
            conn.close()

    def get_watchlist(self, pool_type=None):
        """获取自选/股票池列表"""
        conn = self.db._get_conn()
        cursor = conn.cursor()
        try:
            if pool_type:
                cursor.execute('''
                    SELECT * FROM watchlist WHERE pool_type=? ORDER BY ai_score DESC
                ''', (pool_type,))
            else:
                cursor.execute('''
                    SELECT * FROM watchlist ORDER BY pool_type, ai_score DESC
                ''')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"获取自选股失败: {e}")
            return []
        finally:
            conn.close()

    def is_in_watchlist(self, ts_code, pool_type=POOL_WATCHLIST):
        """检查是否在自选/股票池中"""
        conn = self.db._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT COUNT(*) as cnt FROM watchlist WHERE ts_code=? AND pool_type=?
            ''', (ts_code, pool_type))
            row = cursor.fetchone()
            return row['cnt'] > 0
        except Exception as e:
            return False
        finally:
            conn.close()

    def update_stage(self, ts_code, stage, pool_type=None):
        """更新股票阶段"""
        conn = self.db._get_conn()
        cursor = conn.cursor()
        try:
            if pool_type:
                cursor.execute('''
                    UPDATE watchlist SET stage=? WHERE ts_code=? AND pool_type=?
                ''', (stage, ts_code, pool_type))
            else:
                cursor.execute('''
                    UPDATE watchlist SET stage=? WHERE ts_code=?
                ''', (stage, ts_code))
            conn.commit()
            return True
        except Exception as e:
            return False
        finally:
            conn.close()

    def update_ai_score(self, ts_code, ai_score, pool_type=None):
        """更新AI评分"""
        conn = self.db._get_conn()
        cursor = conn.cursor()
        try:
            if pool_type:
                cursor.execute('''
                    UPDATE watchlist SET ai_score=? WHERE ts_code=? AND pool_type=?
                ''', (ai_score, ts_code, pool_type))
            else:
                cursor.execute('''
                    UPDATE watchlist SET ai_score=? WHERE ts_code=?
                ''', (ai_score, ts_code))
            conn.commit()
            return True
        except Exception as e:
            return False
        finally:
            conn.close()

    def get_pool_stats(self):
        """获取各股票池统计"""
        conn = self.db._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT pool_type, COUNT(*) as cnt, AVG(ai_score) as avg_score
                FROM watchlist GROUP BY pool_type
            ''')
            rows = cursor.fetchall()
            stats = {pool: {'count': 0, 'avg_score': 0} for pool in self.ALL_POOLS}
            for row in rows:
                stats[row['pool_type']] = {
                    'count': row['cnt'],
                    'avg_score': row['avg_score'] or 0
                }
            return stats
        except Exception as e:
            return {}
        finally:
            conn.close()

    def clear_pool(self, pool_type):
        """清空指定股票池"""
        conn = self.db._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM watchlist WHERE pool_type=?', (pool_type,))
            conn.commit()
            return True
        except Exception as e:
            return False
        finally:
            conn.close()

    # ========== 三倍量股票池 ==========
    def save_triple_volume(self, ts_code, name, tv_date, vol_ratio, tv_high,
                           tv_close, turnover_rate, stage='观察', lifeline=0):
        """保存三倍量股票"""
        conn = self.db._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO triple_volume_pool
                (ts_code, name, tv_date, vol_ratio, tv_high, tv_close,
                 turnover_rate, stage, lifeline, update_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (ts_code, name, tv_date, vol_ratio, tv_high, tv_close,
                  turnover_rate, stage, lifeline,
                  datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
            return True
        except Exception as e:
            print(f"保存三倍量股票失败: {e}")
            return False
        finally:
            conn.close()

    def get_triple_volume_pool(self, stage=None):
        """获取三倍量股票池"""
        conn = self.db._get_conn()
        cursor = conn.cursor()
        try:
            if stage:
                cursor.execute('''
                    SELECT * FROM triple_volume_pool WHERE stage=?
                    ORDER BY vol_ratio DESC
                ''', (stage,))
            else:
                cursor.execute('''
                    SELECT * FROM triple_volume_pool ORDER BY vol_ratio DESC
                ''')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            return []
        finally:
            conn.close()

    def update_tv_stage(self, ts_code, stage):
        """更新三倍量股票阶段"""
        conn = self.db._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                UPDATE triple_volume_pool SET stage=?, update_time=?
                WHERE ts_code=?
            ''', (stage, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), ts_code))
            conn.commit()
            return True
        except Exception as e:
            return False
        finally:
            conn.close()


# 全局单例
_watchlist_manager = None


def get_watchlist_manager():
    global _watchlist_manager
    if _watchlist_manager is None:
        _watchlist_manager = WatchlistManager()
    return _watchlist_manager
