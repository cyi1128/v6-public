"""
盘中AI助手提醒模块
实时提醒买卖信号、风险提示、策略触发
"""
from datetime import datetime
from collections import deque


class AIAssistant:
    """盘中AI助手"""

    def __init__(self):
        self.alerts = deque(maxlen=100)  # 提醒记录
        self.alerted_stocks = set()  # 已提醒过的股票（避免重复）

    def check_stock(self, stock_data, score_result, risk_result=None, auction_data=None):
        """
        检查单只股票，生成提醒
        stock_data: 股票基本信息 {ts_code, name, price, ...}
        score_result: AI评分结果
        risk_result: 风险监控结果
        auction_data: 集合竞价数据
        返回: 提醒列表
        """
        new_alerts = []
        ts_code = stock_data.get('ts_code', '')
        name = stock_data.get('name', '')
        price = stock_data.get('price', 0)

        # 1. 高评分买入提醒
        if score_result.get('total_score', 0) >= 85:
            alert_key = f'{ts_code}_buy_{score_result["total_score"]}'
            if alert_key not in self.alerted_stocks:
                alert = self._create_buy_alert(stock_data, score_result)
                new_alerts.append(alert)
                self.alerted_stocks.add(alert_key)

        # 2. 五星信号提醒
        signals = score_result.get('signals', [])
        for sig in signals:
            if isinstance(sig, dict) and sig.get('star') == 5:
                alert_key = f'{ts_code}_fivestar_{sig["type"]}'
                if alert_key not in self.alerted_stocks:
                    alert = self._create_fivestar_alert(stock_data, sig, score_result)
                    new_alerts.append(alert)
                    self.alerted_stocks.add(alert_key)

        # 3. 缠论信号提醒
        for sig in signals:
            if isinstance(sig, dict) and 'chan' in sig.get('type', ''):
                alert_key = f'{ts_code}_chan_{sig["type"]}'
                if alert_key not in self.alerted_stocks:
                    alert = self._create_chan_alert(stock_data, sig)
                    new_alerts.append(alert)
                    self.alerted_stocks.add(alert_key)

        # 4. 三倍量信号提醒（5类中的3类）
        for sig in signals:
            if isinstance(sig, dict) and 'triple_volume' in sig.get('type', ''):
                alert_key = f'{ts_code}_tv_{sig["type"]}'
                if alert_key not in self.alerted_stocks:
                    if sig['type'] == 'triple_volume_start':
                        alert = self._create_tv_start_alert(stock_data, sig)
                    elif sig['type'] == 'triple_volume_pullback':
                        alert = self._create_tv_pullback_alert(stock_data, sig)
                    elif sig['type'] == 'triple_volume_second_start':
                        alert = self._create_tv_breakout_alert(stock_data, sig)
                    else:
                        alert = self._create_triple_volume_alert(stock_data, sig)
                    new_alerts.append(alert)
                    self.alerted_stocks.add(alert_key)

        # 5. 集合竞价高开3%以上提醒
        if auction_data:
            auction_pct = auction_data.get('pct_chg', 0)
            if auction_pct >= 3:
                alert_key = f'{ts_code}_auction_{auction_pct}'
                if alert_key not in self.alerted_stocks:
                    alert = self._create_auction_alert(stock_data, auction_data)
                    new_alerts.append(alert)
                    self.alerted_stocks.add(alert_key)

        # 6. 风险提醒（跌破关键支撑）
        if risk_result:
            risk_signals = risk_result.get('signals', [])
            for risk in risk_signals:
                if risk.get('score', 0) >= 7:
                    alert_key = f'{ts_code}_risk_{risk["type"]}'
                    if alert_key not in self.alerted_stocks:
                        alert = self._create_risk_alert(stock_data, risk)
                        new_alerts.append(alert)
                        self.alerted_stocks.add(alert_key)

        # 添加到记录
        for alert in new_alerts:
            self.alerts.append(alert)

        return new_alerts

    def _create_buy_alert(self, stock_data, score_result):
        """创建买入提醒"""
        name = stock_data.get('name', '')
        ts_code = stock_data.get('ts_code', '')
        price = stock_data.get('price', 0)
        score = score_result.get('total_score', 0)

        catalysts = score_result.get('catalysts', [])
        catalyst_str = '、'.join(catalysts[:3]) if catalysts else '多重利好'

        return {
            'type': 'buy',
            'level': 'high',
            'title': f'【{name}】买入机会',
            'content': (
                f'发现买入机会\n'
                f'当前价格: {price:.2f}元\n'
                f'综合评分: {score}分\n'
                f'催化因素: {catalyst_str}\n'
                f'建议: {score_result.get("suggestion", "")}'
            ),
            'stock': name,
            'ts_code': ts_code,
            'price': price,
            'score': score,
            'time': datetime.now().strftime('%H:%M:%S'),
            'sound': True,
        }

    def _create_fivestar_alert(self, stock_data, signal, score_result):
        """创建五星信号提醒"""
        name = stock_data.get('name', '')
        ts_code = stock_data.get('ts_code', '')
        price = stock_data.get('price', 0)

        reasons = signal.get('trigger_reason', [])
        reason_str = '\n'.join([f'  ✓ {r}' for r in reasons])

        return {
            'type': 'fivestar',
            'level': 'critical',
            'title': f'⭐⭐⭐⭐⭐ 【{name}】五星买点！',
            'content': (
                f'{signal.get("name", "")}\n'
                f'当前价格: {price:.2f}元\n'
                f'触发条件:\n{reason_str}\n'
                f'建议: {signal.get("suggestion", "")}'
            ),
            'stock': name,
            'ts_code': ts_code,
            'price': price,
            'signal': signal.get('name', ''),
            'time': datetime.now().strftime('%H:%M:%S'),
            'sound': True,
            'popup': True,
        }

    def _create_chan_alert(self, stock_data, signal):
        """创建缠论信号提醒"""
        name = stock_data.get('name', '')
        ts_code = stock_data.get('ts_code', '')
        price = stock_data.get('price', 0)

        return {
            'type': 'chan',
            'level': 'medium',
            'title': f'【{name}】{signal.get("name", "")}',
            'content': (
                f'{signal.get("description", "")}\n'
                f'当前价格: {price:.2f}元\n'
                f'评分: {signal.get("score", 0)}/10\n'
                f'建议: {signal.get("suggestion", "")}'
            ),
            'stock': name,
            'ts_code': ts_code,
            'price': price,
            'signal': signal.get('name', ''),
            'time': datetime.now().strftime('%H:%M:%S'),
            'sound': False,
        }

    def _create_triple_volume_alert(self, stock_data, signal):
        """创建三倍量信号提醒（通用）"""
        name = stock_data.get('name', '')
        ts_code = stock_data.get('ts_code', '')
        price = stock_data.get('price', 0)
        lifeline = signal.get('lifeline', 0)

        return {
            'type': 'triple_volume',
            'level': 'high',
            'title': f'【{name}】{signal.get("name", "")}',
            'content': (
                f'{signal.get("description", "")}\n'
                f'当前价格: {price:.2f}元\n'
                f'生命线: {lifeline:.2f}元\n'
                f'建议: {signal.get("suggestion", "")}'
            ),
            'stock': name,
            'ts_code': ts_code,
            'price': price,
            'signal': signal.get('name', ''),
            'lifeline': lifeline,
            'time': datetime.now().strftime('%H:%M:%S'),
            'sound': True,
        }

    def _create_tv_start_alert(self, stock_data, signal):
        """三倍量启动提醒：发现放量启动机会"""
        name = stock_data.get('name', '')
        ts_code = stock_data.get('ts_code', '')
        price = stock_data.get('price', 0)
        vol_ratio = signal.get('vol_ratio', 0)

        return {
            'type': 'tv_start',
            'level': 'high',
            'title': f'🚀 【{name}】发现放量启动机会',
            'content': (
                f'三倍量阳线启动！\n'
                f'当前价格: {price:.2f}元\n'
                f'成交量倍数: {vol_ratio:.1f}倍\n'
                f'生命线: {signal.get("lifeline", 0):.2f}元\n'
                f'建议: 关注后续回踩机会'
            ),
            'stock': name,
            'ts_code': ts_code,
            'price': price,
            'signal': '三倍量启动',
            'time': datetime.now().strftime('%H:%M:%S'),
            'sound': True,
            'popup': True,
        }

    def _create_tv_pullback_alert(self, stock_data, signal):
        """回踩确认提醒：强势洗盘完成"""
        name = stock_data.get('name', '')
        ts_code = stock_data.get('ts_code', '')
        price = stock_data.get('price', 0)
        lifeline = signal.get('lifeline', 0)

        return {
            'type': 'tv_pullback',
            'level': 'medium',
            'title': f'💪 【{name}】强势洗盘完成',
            'content': (
                f'回踩不破关键价格，缩量调整确认\n'
                f'当前价格: {price:.2f}元\n'
                f'生命线支撑: {lifeline:.2f}元\n'
                f'建议: 等待二次启动信号'
            ),
            'stock': name,
            'ts_code': ts_code,
            'price': price,
            'signal': '回踩确认',
            'lifeline': lifeline,
            'time': datetime.now().strftime('%H:%M:%S'),
            'sound': True,
        }

    def _create_tv_breakout_alert(self, stock_data, signal):
        """突破提醒：二次启动买点形成"""
        name = stock_data.get('name', '')
        ts_code = stock_data.get('ts_code', '')
        price = stock_data.get('price', 0)
        lifeline = signal.get('lifeline', 0)

        return {
            'type': 'tv_breakout',
            'level': 'critical',
            'title': f'⭐ 【{name}】二次启动买点形成',
            'content': (
                f'突破三倍量阳线收盘价！\n'
                f'当前价格: {price:.2f}元\n'
                f'突破生命线: {lifeline:.2f}元\n'
                f'买入价: {signal.get("buy_price", price):.2f}元\n'
                f'止损价: {signal.get("stop_loss", 0):.2f}元\n'
                f'目标价: {signal.get("target_price", 0):.2f}元\n'
                f'建议: 五星买点，可重点关注'
            ),
            'stock': name,
            'ts_code': ts_code,
            'price': price,
            'signal': '二次启动买点',
            'lifeline': lifeline,
            'time': datetime.now().strftime('%H:%M:%S'),
            'sound': True,
            'popup': True,
        }

    def _create_auction_alert(self, stock_data, auction_data):
        """集合竞价强势提醒"""
        name = stock_data.get('name', '')
        ts_code = stock_data.get('ts_code', '')
        auction_price = auction_data.get('price', 0)
        auction_pct = auction_data.get('pct_chg', 0)
        auction_volume = auction_data.get('volume', 0)

        return {
            'type': 'auction',
            'level': 'high',
            'title': f'📈 【{name}】竞价强势股票',
            'content': (
                f'集合竞价高开{auction_pct:.1f}%\n'
                f'竞价价格: {auction_price:.2f}元\n'
                f'竞价成交量: {auction_volume/10000:.1f}万手\n'
                f'建议: 关注开盘后量能持续性'
            ),
            'stock': name,
            'ts_code': ts_code,
            'price': auction_price,
            'auction_pct': auction_pct,
            'signal': '集合竞价强势',
            'time': datetime.now().strftime('%H:%M:%S'),
            'sound': True,
            'popup': True,
        }

    def _create_risk_alert(self, stock_data, risk):
        """创建风险提醒"""
        name = stock_data.get('name', '')
        ts_code = stock_data.get('ts_code', '')
        price = stock_data.get('price', 0)

        return {
            'type': 'risk',
            'level': 'high',
            'title': f'⚠️ 【{name}】{risk.get("name", "")}',
            'content': (
                f'{risk.get("description", "")}\n'
                f'当前价格: {price:.2f}元\n'
                f'风险等级: {risk.get("level", "")}\n'
                f'操作: {risk.get("action", "")}'
            ),
            'stock': name,
            'ts_code': ts_code,
            'price': price,
            'risk': risk.get('name', ''),
            'time': datetime.now().strftime('%H:%M:%S'),
            'sound': True,
        }

    def get_recent_alerts(self, count=20, alert_type=None):
        """获取最近的提醒"""
        alerts = list(self.alerts)

        if alert_type:
            alerts = [a for a in alerts if a.get('type') == alert_type]

        return alerts[-count:]

    def clear_alerted_stocks(self):
        """清空已提醒记录（每日重置）"""
        self.alerted_stocks.clear()

    def generate_daily_summary(self):
        """生成每日提醒总结"""
        alerts = list(self.alerts)

        summary = {
            'total': len(alerts),
            'buy_count': len([a for a in alerts if a['type'] == 'buy']),
            'fivestar_count': len([a for a in alerts if a['type'] == 'fivestar']),
            'chan_count': len([a for a in alerts if a['type'] == 'chan']),
            'triple_volume_count': len([a for a in alerts if a['type'] == 'triple_volume']),
            'risk_count': len([a for a in alerts if a['type'] == 'risk']),
            'stocks_alerted': len(self.alerted_stocks),
        }

        return summary
