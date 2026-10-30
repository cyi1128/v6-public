"""
板块资金地图
显示行业、概念资金流向，热点龙头
"""
from datetime import datetime
import requests


class SectorFundMap:
    """板块资金地图"""

    def __init__(self):
        self.sector_data = {}

    def get_sector_list(self):
        """获取板块列表（东方财富API）"""
        try:
            url = 'https://push2delay.eastmoney.com/api/qt/clist/get'
            params = {
                'pn': 1,
                'pz': 50,
                'po': 1,
                'np': 1,
                'fltt': 2,
                'invt': 2,
                'fid': 'f3',
                'fs': 'm:90+t:2',  # 行业板块
                'fields': 'f2,f3,f4,f12,f14,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87',
            }
            resp = requests.get(url, params=params, timeout=8)
            data = resp.json()

            sectors = []
            if data.get('data') and data['data'].get('diff'):
                for item in data['data']['diff']:
                    sectors.append({
                        'code': item.get('f12', ''),
                        'name': item.get('f14', ''),
                        'change_pct': item.get('f3', 0),
                        'main_fund_flow': item.get('f62', 0) / 100000000 if item.get('f62') else 0,  # 亿
                        'leading_stock': item.get('f128', ''),
                        'leading_change': item.get('f136', 0),
                    })

            return sectors
        except Exception as e:
            print(f"[SectorFundMap] 获取板块列表失败: {e}")
            return []

    def get_concept_list(self):
        """获取概念板块列表"""
        try:
            url = 'https://push2delay.eastmoney.com/api/qt/clist/get'
            params = {
                'pn': 1,
                'pz': 50,
                'po': 1,
                'np': 1,
                'fltt': 2,
                'invt': 2,
                'fid': 'f3',
                'fs': 'm:90+t:3',  # 概念板块
                'fields': 'f2,f3,f4,f12,f14,f62,f184',
            }
            resp = requests.get(url, params=params, timeout=8)
            data = resp.json()

            concepts = []
            if data.get('data') and data['data'].get('diff'):
                for item in data['data']['diff']:
                    concepts.append({
                        'code': item.get('f12', ''),
                        'name': item.get('f14', ''),
                        'change_pct': item.get('f3', 0),
                        'main_fund_flow': item.get('f62', 0) / 100000000 if item.get('f62') else 0,
                    })

            return concepts
        except Exception:
            return []

    def get_hot_sectors(self, limit=10):
        """获取热门板块（按涨幅排序）"""
        sectors = self.get_sector_list()
        sectors.sort(key=lambda x: x.get('change_pct', 0), reverse=True)
        return sectors[:limit]

    def get_fund_inflow_sectors(self, limit=10):
        """获取资金流入板块"""
        sectors = self.get_sector_list()
        sectors.sort(key=lambda x: x.get('main_fund_flow', 0), reverse=True)
        return sectors[:limit]

    def get_sector_stocks(self, sector_code):
        """获取板块成分股"""
        try:
            url = 'https://push2delay.eastmoney.com/api/qt/clist/get'
            params = {
                'pn': 1,
                'pz': 30,
                'po': 1,
                'np': 1,
                'fltt': 2,
                'invt': 2,
                'fid': 'f3',
                'fs': f'b:{sector_code}',
                'fields': 'f2,f3,f4,f12,f14,f62',
            }
            resp = requests.get(url, params=params, timeout=8)
            data = resp.json()

            stocks = []
            if data.get('data') and data['data'].get('diff'):
                for item in data['data']['diff']:
                    stocks.append({
                        'code': item.get('f12', ''),
                        'name': item.get('f14', ''),
                        'price': item.get('f2', 0),
                        'change_pct': item.get('f3', 0),
                        'main_fund_flow': item.get('f62', 0) / 100000000 if item.get('f62') else 0,
                    })

            return stocks
        except Exception:
            return []

    def generate_heatmap_data(self):
        """生成热力图数据"""
        sectors = self.get_sector_list()

        heatmap = []
        for sector in sectors:
            change = sector.get('change_pct', 0)
            fund_flow = sector.get('main_fund_flow', 0)

            # 颜色：涨红跌绿
            if change > 3:
                color = '#ff1744'
            elif change > 1:
                color = '#ff5252'
            elif change > 0:
                color = '#ff8a80'
            elif change > -1:
                color = '#80cbc4'
            elif change > -3:
                color = '#26a69a'
            else:
                color = '#00897b'

            heatmap.append({
                'name': sector['name'],
                'change_pct': change,
                'fund_flow': fund_flow,
                'color': color,
                'size': abs(fund_flow) + 1,  # 用于热力图大小
            })

        return heatmap
