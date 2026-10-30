"""
AI模拟交易训练系统
增加模拟账户，自动模拟如果昨天买入结果如何
统计胜率、收益、最大亏损，帮助优化策略
"""
import sqlite3
from datetime import datetime, timedelta
import os


class PaperTrading:
    """AI模拟交易训练系统"""

    DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'quant_monitor.db')

    def __init__(self):
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_code TEXT,
                stock_name TEXT,
                buy_price REAL,
                buy_time TEXT,
                sell_price REAL,
                sell_time TEXT,
                quantity INTEGER,
                strategy TEXT,
                reason TEXT,
                status TEXT,
                profit REAL,
                profit_pct REAL,
                holding_days INTEGER
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS paper_account (
                id INTEGER PRIMARY KEY,
                total_capital REAL,
                available_capital REAL,
                total_profit REAL,
                total_trades INTEGER,
                win_trades INTEGER,
                lose_trades INTEGER,
                max_drawdown REAL,
                update_time TEXT
            )
        ''')

        # 初始化账户
        cursor.execute('SELECT COUNT(*) FROM paper_account')
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO paper_account (id, total_capital, available_capital, total_profit,
                    total_trades, win_trades, lose_trades, max_drawdown, update_time)
                VALUES (1, 1000000, 1000000, 0, 0, 0, 0, 0, ?)
            ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),))

        conn.commit()
        conn.close()

    def buy(self, ts_code, stock_name, price, quantity=100, strategy='', reason=''):
        """模拟买入"""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        # 检查资金
        cursor.execute('SELECT available_capital FROM paper_account WHERE id=1')
        available = cursor.fetchone()[0]
        cost = price * quantity

        if cost > available:
            conn.close()
            return {'success': False, 'message': '资金不足'}

        # 扣除资金
        cursor.execute('''
            UPDATE paper_account SET available_capital = available_capital - ?
            WHERE id=1
        ''', (cost,))

        # 记录交易
        cursor.execute('''
            INSERT INTO paper_trades (ts_code, stock_name, buy_price, buy_time,
                quantity, strategy, reason, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, '持有中')
        ''', (ts_code, stock_name, price, datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
              quantity, strategy, reason))

        conn.commit()
        conn.close()

        return {'success': True, 'message': f'买入{stock_name} {quantity}股，价格{price:.2f}'}

    def sell(self, trade_id, price):
        """模拟卖出"""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM paper_trades WHERE id=?', (trade_id,))
        trade = cursor.fetchone()
        if not trade or trade[9] != '持有中':
            conn.close()
            return {'success': False, 'message': '交易不存在或已卖出'}

        buy_price = trade[3]
        quantity = trade[7]
        buy_time = datetime.strptime(trade[4], '%Y-%m-%d %H:%M:%S')
        sell_time = datetime.now()

        profit = (price - buy_price) * quantity
        profit_pct = (price - buy_price) / buy_price * 100
        holding_days = (sell_time - buy_time).days

        # 更新交易
        cursor.execute('''
            UPDATE paper_trades SET sell_price=?, sell_time=?, status='已卖出',
                profit=?, profit_pct=?, holding_days=? WHERE id=?
        ''', (price, sell_time.strftime('%Y-%m-%d %H:%M:%S'), profit, profit_pct, holding_days, trade_id))

        # 更新账户
        revenue = price * quantity
        cursor.execute('''
            UPDATE paper_account SET available_capital = available_capital + ?,
                total_profit = total_profit + ?, total_trades = total_trades + 1,
                win_trades = win_trades + ?, lose_trades = lose_trades + ?,
                update_time = ? WHERE id=1
        ''', (revenue, profit, 1 if profit > 0 else 0, 1 if profit <= 0 else 0,
              sell_time.strftime('%Y-%m-%d %H:%M:%S')))

        conn.commit()
        conn.close()

        return {
            'success': True,
            'message': f'卖出{trade[2]}，盈利{profit:.2f}元({profit_pct:+.2f}%)',
            'profit': profit,
            'profit_pct': profit_pct,
        }

    def get_account(self):
        """获取账户信息"""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM paper_account WHERE id=1')
        row = cursor.fetchone()
        conn.close()

        if not row:
            return {}

        win_rate = row[5] / row[4] * 100 if row[4] > 0 else 0

        return {
            'total_capital': row[1],
            'available_capital': row[2],
            'total_profit': row[3],
            'total_trades': row[4],
            'win_trades': row[5],
            'lose_trades': row[6],
            'max_drawdown': row[7],
            'win_rate': round(win_rate, 2),
            'update_time': row[8],
        }

    def get_trades(self, status=None, limit=50):
        """获取交易记录"""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        if status:
            cursor.execute('''
                SELECT * FROM paper_trades WHERE status=? ORDER BY buy_time DESC LIMIT ?
            ''', (status, limit))
        else:
            cursor.execute('''
                SELECT * FROM paper_trades ORDER BY buy_time DESC LIMIT ?
            ''', (limit,))

        rows = cursor.fetchall()
        conn.close()

        trades = []
        for row in rows:
            trades.append({
                'id': row[0],
                'ts_code': row[1],
                'stock_name': row[2],
                'buy_price': row[3],
                'buy_time': row[4],
                'sell_price': row[5],
                'sell_time': row[6],
                'quantity': row[7],
                'strategy': row[8],
                'reason': row[9],
                'status': row[10],
                'profit': row[11],
                'profit_pct': row[12],
                'holding_days': row[13],
            })

        return trades

    def get_statistics(self):
        """获取统计数据"""
        account = self.get_account()
        trades = self.get_trades(status='已卖出', limit=1000)

        if not trades:
            return {
                'total_trades': 0,
                'win_rate': 0,
                'avg_profit': 0,
                'avg_holding_days': 0,
                'max_profit': 0,
                'max_loss': 0,
                'total_profit': 0,
            }

        profits = [t['profit'] for t in trades if t['profit'] is not None]
        holding_days = [t['holding_days'] for t in trades if t['holding_days'] is not None]

        return {
            'total_trades': len(trades),
            'win_rate': account.get('win_rate', 0),
            'avg_profit': round(sum(profits) / len(profits), 2) if profits else 0,
            'avg_holding_days': round(sum(holding_days) / len(holding_days), 1) if holding_days else 0,
            'max_profit': max(profits) if profits else 0,
            'max_loss': min(profits) if profits else 0,
            'total_profit': sum(profits) if profits else 0,
        }

    def simulate_yesterday(self, ts_code, stock_name, buy_price, current_price, quantity=100):
        """模拟如果昨天买入的结果"""
        profit = (current_price - buy_price) * quantity
        profit_pct = (current_price - buy_price) / buy_price * 100 if buy_price > 0 else 0

        return {
            'ts_code': ts_code,
            'stock_name': stock_name,
            'buy_price': buy_price,
            'current_price': current_price,
            'quantity': quantity,
            'profit': round(profit, 2),
            'profit_pct': round(profit_pct, 2),
            'result': '盈利' if profit > 0 else '亏损',
        }

    def reset_account(self):
        """重置账户"""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        cursor.execute('DELETE FROM paper_trades')
        cursor.execute('''
            UPDATE paper_account SET total_capital=1000000, available_capital=1000000,
                total_profit=0, total_trades=0, win_trades=0, lose_trades=0,
                max_drawdown=0, update_time=? WHERE id=1
        ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),))

        conn.commit()
        conn.close()

        return {'success': True, 'message': '账户已重置'}
