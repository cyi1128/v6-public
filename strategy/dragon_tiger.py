"""
龙虎榜分析
机构、游资买卖席位，资金方向
"""
from datetime import datetime, timedelta
import requests


class DragonTigerAnalyzer:
    """龙虎榜分析器"""

    # 知名游资席位
    FAMOUS_HOT_MONEY = {
        '东方财富证券拉萨团结路': '拉萨天团',
        '东方财富证券拉萨东环路': '拉萨天团',
        '国泰君安证券上海江苏路': '章盟主',
        '中信证券上海溧阳路': '孙哥',
        '华泰证券深圳益田路': '益田路',
        '银河证券绍兴营业部': '赵老哥',
        '方正证券上海保定路': '保定路',
        '中国国际金融上海分公司': '量化资金',
        '华鑫证券上海分公司': '量化资金',
    }

    # 机构专用
    INSTITUTION_KEYWORDS = ['机构专用', '机构席位']

    def __init__(self):
        pass

    def get_daily_list(self, date=None):
        """获取某日龙虎榜列表"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        try:
            url = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
            params = {
                'sortColumns': 'SECURITY_CODE',
                'sortTypes': 1,
                'pageSize': 50,
                'pageNumber': 1,
                'reportName': 'RPT_DAILYBILLBOARD_DETAILSNEW',
                'columns': 'ALL',
                'filter': f"(TRADE_DATE='{date}')",
            }
            resp = requests.get(url, params=params, timeout=8)
            data = resp.json()

            stocks = []
            if data.get('result') and data['result'].get('data'):
                for item in data['result']['data']:
                    stocks.append({
                        'code': item.get('SECURITY_CODE', ''),
                        'name': item.get('SECURITY_NAME_ABBR', ''),
                        'change_pct': item.get('CHANGE_RATE', 0),
                        'reason': item.get('EXPLANATION', ''),
                        'buy_amount': item.get('BUY_AMT', 0) / 10000 if item.get('BUY_AMT') else 0,
                        'sell_amount': item.get('SELL_AMT', 0) / 10000 if item.get('SELL_AMT') else 0,
                        'net_amount': item.get('NET_AMT', 0) / 10000 if item.get('NET_AMT') else 0,
                    })

            return stocks
        except Exception as e:
            return []

    def get_stock_detail(self, ts_code, date=None):
        """获取个股龙虎榜详情"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        try:
            url = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
            params = {
                'sortColumns': 'BUY',
                'sortTypes': -1,
                'pageSize': 10,
                'pageNumber': 1,
                'reportName': 'RPT_DAILYBILLBOARD_DETAILS',
                'columns': 'ALL',
                'filter': f"(SECURITY_CODE='{ts_code}')(TRADE_DATE='{date}')",
            }
            resp = requests.get(url, params=params, timeout=8)
            data = resp.json()

            details = {
                'buy_seats': [],
                'sell_seats': [],
                'summary': {},
            }

            if data.get('result') and data['result'].get('data'):
                for item in data['result']['data']:
                    seat = {
                        'name': item.get('OPERATEDEPT_NAME', ''),
                        'buy_amount': item.get('BUY_AMT', 0) / 10000 if item.get('BUY_AMT') else 0,
                        'sell_amount': item.get('SELL_AMT', 0) / 10000 if item.get('SELL_AMT') else 0,
                        'net_amount': item.get('NET_AMT', 0) / 10000 if item.get('NET_AMT') else 0,
                        'type': self._classify_seat(item.get('OPERATEDEPT_NAME', '')),
                    }

                    if seat['buy_amount'] > seat['sell_amount']:
                        details['buy_seats'].append(seat)
                    else:
                        details['sell_seats'].append(seat)

            # 汇总
            total_buy = sum(s['buy_amount'] for s in details['buy_seats'])
            total_sell = sum(s['sell_amount'] for s in details['sell_seats'])
            institution_buy = sum(s['buy_amount'] for s in details['buy_seats'] if s['type'] == '机构')
            institution_sell = sum(s['sell_amount'] for s in details['sell_seats'] if s['type'] == '机构')
            hotmoney_buy = sum(s['buy_amount'] for s in details['buy_seats'] if s['type'] == '游资')
            hotmoney_sell = sum(s['sell_amount'] for s in details['sell_seats'] if s['type'] == '游资')

            details['summary'] = {
                'total_buy': round(total_buy, 2),
                'total_sell': round(total_sell, 2),
                'net_amount': round(total_buy - total_sell, 2),
                'institution_net': round(institution_buy - institution_sell, 2),
                'hotmoney_net': round(hotmoney_buy - hotmoney_sell, 2),
                'institution_count': sum(1 for s in details['buy_seats'] + details['sell_seats'] if s['type'] == '机构'),
                'hotmoney_count': sum(1 for s in details['buy_seats'] + details['sell_seats'] if s['type'] == '游资'),
            }

            return details
        except Exception as e:
            return {'buy_seats': [], 'sell_seats': [], 'summary': {}, 'error': str(e)}

    def _classify_seat(self, seat_name):
        """分类席位"""
        # 机构
        for kw in self.INSTITUTION_KEYWORDS:
            if kw in seat_name:
                return '机构'

        # 知名游资
        for key in self.FAMOUS_HOT_MONEY:
            if key in seat_name:
                return '游资'

        # 量化资金
        if '中金' in seat_name or '华鑫' in seat_name:
            return '量化'

        return '营业部'

    def analyze_stock(self, ts_code, date=None):
        """分析个股龙虎榜"""
        details = self.get_stock_detail(ts_code, date)
        summary = details.get('summary', {})

        if not summary:
            return {
                'has_data': False,
                'message': '暂无龙虎榜数据',
            }

        # 判断资金方向
        net = summary.get('net_amount', 0)
        inst_net = summary.get('institution_net', 0)
        hot_net = summary.get('hotmoney_net', 0)

        if net > 0 and inst_net > 0:
            direction = '机构净买入，看好'
            level = '强烈关注'
            color = '#ff1744'
        elif net > 0 and hot_net > 0:
            direction = '游资净买入，短线活跃'
            level = '关注'
            color = '#ff9100'
        elif net < 0 and inst_net < 0:
            direction = '机构净卖出，注意风险'
            level = '风险'
            color = '#00e676'
        elif net < 0:
            direction = '净卖出，资金流出'
            level = '谨慎'
            color = '#757575'
        else:
            direction = '资金博弈'
            level = '观察'
            color = '#ffea00'

        return {
            'has_data': True,
            'direction': direction,
            'level': level,
            'color': color,
            'summary': summary,
            'buy_seats': details.get('buy_seats', [])[:5],
            'sell_seats': details.get('sell_seats', [])[:5],
        }

    def get_recent_dates(self, days=5):
        """获取最近交易日"""
        dates = []
        today = datetime.now()
        for i in range(days):
            d = today - timedelta(days=i)
            if d.weekday() < 5:  # 工作日
                dates.append(d.strftime('%Y-%m-%d'))
        return dates
