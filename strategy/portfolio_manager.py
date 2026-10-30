"""
我的持仓AI管理系统
支持手动添加持仓，AI自动分析，每日生成持仓报告
"""
import sqlite3
from datetime import datetime
import os
import requests


class PortfolioManager:
    """我的持仓AI管理系统"""

    DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'quant_monitor.db')

    def __init__(self):
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS portfolio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_code TEXT UNIQUE,
                stock_name TEXT,
                cost_price REAL,
                quantity INTEGER,
                buy_date TEXT,
                notes TEXT,
                add_time TEXT
            )
        ''')

        conn.commit()
        conn.close()

    def add_stock(self, ts_code, stock_name, cost_price, quantity, buy_date='', notes=''):
        """添加持仓股票"""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT OR REPLACE INTO portfolio (ts_code, stock_name, cost_price, quantity, buy_date, notes, add_time)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (ts_code, stock_name, cost_price, quantity, buy_date, notes,
                  datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
            result = {'success': True, 'message': f'已添加 {stock_name} 到持仓'}
        except Exception as e:
            result = {'success': False, 'message': str(e)}

        conn.close()
        return result

    def remove_stock(self, ts_code):
        """删除持仓股票"""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM portfolio WHERE ts_code=?', (ts_code,))
        conn.commit()
        conn.close()
        return {'success': True, 'message': '已从持仓删除'}

    def get_portfolio(self):
        """获取持仓列表"""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM portfolio ORDER BY add_time DESC')
        rows = cursor.fetchall()
        conn.close()

        portfolio = []
        for row in rows:
            portfolio.append({
                'id': row[0],
                'ts_code': row[1],
                'stock_name': row[2],
                'cost_price': row[3],
                'quantity': row[4],
                'buy_date': row[5],
                'notes': row[6],
                'add_time': row[7],
            })

        return portfolio

    def get_realtime_price(self, ts_code):
        """获取实时价格（腾讯财经API）"""
        try:
            # 转换代码格式
            if ts_code.startswith('6'):
                code = 'sh' + ts_code
            else:
                code = 'sz' + ts_code

            url = f'https://qt.gtimg.cn/q={code}'
            resp = requests.get(url, timeout=5)
            text = resp.content.decode('gbk', errors='ignore')
            parts = text.split('"')[1].split('~')

            if len(parts) > 3:
                return {
                    'name': parts[1],
                    'price': float(parts[3]),
                    'change_pct': float(parts[32]) if len(parts) > 32 else 0,
                    'turnover': float(parts[38]) if len(parts) > 38 else 0,
                }
        except Exception:
            pass

        return None

    def analyze_portfolio(self, daily_data_provider=None):
        """分析整个持仓"""
        portfolio = self.get_portfolio()
        results = []

        total_cost = 0
        total_value = 0
        total_profit = 0

        for stock in portfolio:
            ts_code = stock['ts_code']
            realtime = self.get_realtime_price(ts_code)

            if realtime:
                current_price = realtime['price']
                stock_name = realtime['name']
                change_pct = realtime['change_pct']
            else:
                current_price = stock['cost_price']
                stock_name = stock['stock_name']
                change_pct = 0

            cost = stock['cost_price'] * stock['quantity']
            value = current_price * stock['quantity']
            profit = value - cost
            profit_pct = (current_price - stock['cost_price']) / stock['cost_price'] * 100 if stock['cost_price'] > 0 else 0

            total_cost += cost
            total_value += value
            total_profit += profit

            results.append({
                'ts_code': ts_code,
                'stock_name': stock_name,
                'cost_price': stock['cost_price'],
                'current_price': current_price,
                'quantity': stock['quantity'],
                'change_pct': change_pct,
                'profit': round(profit, 2),
                'profit_pct': round(profit_pct, 2),
                'cost': round(cost, 2),
                'value': round(value, 2),
            })

        total_profit_pct = (total_profit / total_cost * 100) if total_cost > 0 else 0

        summary = {
            'total_cost': round(total_cost, 2),
            'total_value': round(total_value, 2),
            'total_profit': round(total_profit, 2),
            'total_profit_pct': round(total_profit_pct, 2),
            'stock_count': len(portfolio),
        }

        return results, summary

    def generate_daily_report(self, stock_data_provider=None):
        """生成每日持仓报告"""
        results, summary = self.analyze_portfolio()

        report_lines = []
        report_lines.append(f"📊 持仓日报 - {datetime.now().strftime('%Y-%m-%d')}")
        report_lines.append(f"持仓数量: {summary['stock_count']}只")
        report_lines.append(f"总市值: {summary['total_value']:.2f}元")
        report_lines.append(f"总盈亏: {summary['total_profit']:+.2f}元 ({summary['total_profit_pct']:+.2f}%)")
        report_lines.append("")

        for stock in results:
            status = '盈利' if stock['profit'] >= 0 else '亏损'
            report_lines.append(f"【{stock['stock_name']}】{stock['ts_code']}")
            report_lines.append(f"  成本: {stock['cost_price']:.2f} | 现价: {stock['current_price']:.2f}")
            report_lines.append(f"  盈亏: {stock['profit']:+.2f}元 ({stock['profit_pct']:+.2f}%) - {status}")
            report_lines.append("")

        return '\n'.join(report_lines), results, summary

    def get_stock_advice(self, ts_code, daily_data=None, stock_info=None):
        """获取单只股票的操作建议"""
        from strategy.main_fund_analyzer import MainFundAnalyzer
        from strategy.six_dimension_scoring import SixDimensionScorer
        from strategy.decision_tree import DecisionTree
        from strategy.risk_reward_model import RiskRewardModel

        if daily_data is None:
            daily_data = []
        if stock_info is None:
            stock_info = {}

        # 主力阶段
        fund_analyzer = MainFundAnalyzer()
        fund_result = fund_analyzer.analyze({}, daily_data, stock_info)

        # 六维评分
        scorer = SixDimensionScorer()
        realtime = self.get_realtime_price(ts_code)
        price = realtime['price'] if realtime else 0
        score_result = scorer.score({'price': price}, daily_data, stock_info)

        # 风险收益比
        rr_model = RiskRewardModel()
        rr_result = rr_model.calculate({'price': price}, daily_data, stock_info)

        # 决策
        tree = DecisionTree()
        decision_result = tree.analyze({'price': price}, score_result, fund_result, rr_result)

        return {
            'stage': fund_result['stage'],
            'stage_color': fund_result['stage_color'],
            'score': score_result['total_score'],
            'rating': score_result['rating'],
            'decision': decision_result['decision'],
            'position': decision_result['position'],
            'stop_loss': rr_result['stop_loss'],
            'target_price': rr_result['target_price'],
            'risk_reward_ratio': rr_result['ratio'],
            'signals': fund_result['signals'],
            'analysis': fund_result['analysis'],
        }
