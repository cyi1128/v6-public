"""
AI错误复盘系统
每次错误交易，AI分析错误类型、原因和改进建议
"""
import sqlite3
from datetime import datetime
import os


class ErrorReviewSystem:
    """AI错误复盘系统"""

    DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'quant_monitor.db')

    # 错误类型
    ERROR_TYPES = {
        'chase_high': '追高',
        'cut_loss_late': '止损不及时',
        'too_early': '卖飞',
        'wrong_strategy': '策略不匹配',
        'ignore_risk': '忽视风险',
        'over_position': '仓位过重',
        'frequent_trading': '频繁交易',
        'emotional': '情绪化交易',
    }

    def __init__(self):
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS error_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_code TEXT,
                stock_name TEXT,
                trade_date TEXT,
                error_type TEXT,
                error_reason TEXT,
                improvement TEXT,
                loss_amount REAL,
                market_state TEXT,
                strategy_used TEXT,
                review_time TEXT
            )
        ''')

        conn.commit()
        conn.close()

    def analyze_trade(self, trade_data, market_state=None):
        """
        分析一笔交易的错误

        Args:
            trade_data: 交易数据，包含buy_price, sell_price, profit, holding_days等
            market_state: 交易时的市场状态

        Returns:
            dict: 错误分析结果
        """
        if market_state is None:
            market_state = '未知'

        profit = trade_data.get('profit', 0)
        profit_pct = trade_data.get('profit_pct', 0)
        holding_days = trade_data.get('holding_days', 0)
        buy_price = trade_data.get('buy_price', 0)
        sell_price = trade_data.get('sell_price', 0)

        # 只分析亏损交易
        if profit >= 0:
            return {
                'is_error': False,
                'message': '盈利交易，无需复盘',
            }

        # 分析错误类型
        error_type, error_reason = self._identify_error(
            profit_pct, holding_days, market_state
        )

        # 生成改进建议
        improvement = self._generate_improvement(error_type, market_state)

        result = {
            'is_error': True,
            'error_type': error_type,
            'error_type_name': self.ERROR_TYPES.get(error_type, '未知'),
            'error_reason': error_reason,
            'improvement': improvement,
            'loss_amount': abs(profit),
            'loss_pct': abs(profit_pct),
            'market_state': market_state,
            'holding_days': holding_days,
        }

        # 保存到数据库
        self._save_review(trade_data, result)

        return result

    def _identify_error(self, profit_pct, holding_days, market_state):
        """识别错误类型"""
        # 亏损幅度大且持有时间短 = 追高
        if profit_pct < -5 and holding_days <= 2:
            return 'chase_high', f'亏损{abs(profit_pct):.1f}%且仅持有{holding_days}天，典型的追高被套。市场处于{market_state}阶段时，追高风险极大。'

        # 亏损幅度大且持有时间长 = 止损不及时
        if profit_pct < -8 and holding_days >= 5:
            return 'cut_loss_late', f'亏损{abs(profit_pct):.1f}%且持有{holding_days}天，止损不及时。应该在亏损5%以内果断止损。'

        # 市场弱势时亏损 = 策略不匹配
        if '熊市' in market_state or '偏弱' in market_state:
            return 'wrong_strategy', f'市场处于{market_state}，但仍采用进攻策略，策略与市场环境不匹配。'

        # 小亏但频繁 = 频繁交易
        if abs(profit_pct) < 3 and holding_days <= 1:
            return 'frequent_trading', f'仅持有{holding_days}天就亏损卖出，交易过于频繁，手续费侵蚀利润。'

        # 其他情况
        return 'ignore_risk', f'亏损{abs(profit_pct):.1f}%，交易前未充分评估风险，风险收益比不佳。'

    def _generate_improvement(self, error_type, market_state):
        """生成改进建议"""
        improvements = {
            'chase_high': [
                '等待分歧低吸，不追涨',
                '市场高潮阶段减少操作',
                '设置买入价格上限，超过不买',
                '关注回踩支撑位的机会',
            ],
            'cut_loss_late': [
                '严格执行止损纪律，亏损5%无条件止损',
                '买入前就设定止损位',
                '不要抱有侥幸心理',
                '止损后冷静分析，不急于报复性交易',
            ],
            'too_early': [
                '设定目标位，不到目标不卖出',
                '用移动止损保护利润',
                '趋势完好时坚定持有',
                '减少看盘频率，避免被洗出',
            ],
            'wrong_strategy': [
                '根据市场状态选择策略',
                '熊市防守为主，不轻易抄底',
                '震荡市波段操作，不追涨',
                '牛市才积极做多',
            ],
            'ignore_risk': [
                '买入前计算风险收益比',
                '风险收益比低于2:1不参与',
                '分散持仓，单票不超过30%',
                '关注大盘和板块风险',
            ],
            'over_position': [
                '单票仓位控制在20-30%',
                '总仓位根据市场状态调整',
                '分批建仓，不一次性满仓',
                '保留现金应对突发情况',
            ],
            'frequent_trading': [
                '减少交易次数，提高交易质量',
                '每周交易不超过3次',
                '没有明确信号不操作',
                '耐心等待最佳机会',
            ],
            'emotional': [
                '制定交易计划并严格执行',
                '亏损后冷静30分钟再操作',
                '不报复性交易',
                '记录交易日志，定期复盘',
            ],
        }

        return improvements.get(error_type, ['总结经验教训，避免重复犯错'])

    def _save_review(self, trade_data, result):
        """保存复盘记录"""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO error_reviews (ts_code, stock_name, trade_date, error_type,
                error_reason, improvement, loss_amount, market_state, strategy_used, review_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            trade_data.get('ts_code', ''),
            trade_data.get('stock_name', ''),
            datetime.now().strftime('%Y-%m-%d'),
            result['error_type'],
            result['error_reason'],
            '；'.join(result['improvement']),
            result['loss_amount'],
            result['market_state'],
            trade_data.get('strategy', ''),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        ))

        conn.commit()
        conn.close()

    def get_reviews(self, limit=50):
        """获取复盘记录"""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM error_reviews ORDER BY review_time DESC LIMIT ?
        ''', (limit,))

        rows = cursor.fetchall()
        conn.close()

        reviews = []
        for row in rows:
            reviews.append({
                'id': row[0],
                'ts_code': row[1],
                'stock_name': row[2],
                'trade_date': row[3],
                'error_type': row[4],
                'error_type_name': self.ERROR_TYPES.get(row[4], row[4]),
                'error_reason': row[5],
                'improvement': row[6],
                'loss_amount': row[7],
                'market_state': row[8],
                'strategy_used': row[9],
                'review_time': row[10],
            })

        return reviews

    def get_error_statistics(self):
        """获取错误统计"""
        conn = sqlite3.connect(self.DB_PATH)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT error_type, COUNT(*) as cnt, SUM(loss_amount) as total_loss
            FROM error_reviews GROUP BY error_type ORDER BY cnt DESC
        ''')

        rows = cursor.fetchall()
        conn.close()

        stats = []
        for row in rows:
            stats.append({
                'error_type': row[0],
                'error_type_name': self.ERROR_TYPES.get(row[0], row[0]),
                'count': row[1],
                'total_loss': row[2] or 0,
            })

        return stats

    def get_improvement_summary(self):
        """获取改进建议汇总"""
        reviews = self.get_reviews(limit=100)
        if not reviews:
            return '暂无复盘记录'

        # 统计最常见错误
        error_counts = {}
        for r in reviews:
            et = r['error_type']
            error_counts[et] = error_counts.get(et, 0) + 1

        most_common = max(error_counts, key=error_counts.get) if error_counts else None

        summary = f"共复盘{len(reviews)}笔错误交易。"
        if most_common:
            summary += f"最常见错误是【{self.ERROR_TYPES.get(most_common, most_common)}】，共{error_counts[most_common]}次。"
            summary += "建议重点改进这方面的问题。"

        return summary
