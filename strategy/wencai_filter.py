"""
同花顺问财选股模块
通过自然语言查询获取股票列表
"""
import subprocess
import os
import requests
import json


class WencaiFilter:
    """问财选股器"""

    def __init__(self):
        self.js_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            '..', '..', '..', 'AppData', 'Local', 'Programs', 'Python',
            'Python314', 'Lib', 'site-packages', 'pywencai', 'hexin-v.bundle.js'
        )
        # 尝试多个可能的路径
        possible_paths = [
            os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'Programs',
                         'Python', 'Python314', 'Lib', 'site-packages', 'pywencai', 'hexin-v.bundle.js'),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         '..', '..', 'AppData', 'Local', 'Programs', 'Python',
                         'Python314', 'Lib', 'site-packages', 'pywencai', 'hexin-v.bundle.js'),
        ]
        for p in possible_paths:
            if os.path.exists(p):
                self.js_file = p
                break

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
        })
        self._init_session()

    def _init_session(self):
        """初始化session，访问首页获取cookie"""
        try:
            self.session.get('https://www.iwencai.com/', timeout=10)
        except Exception:
            pass

    def _get_token(self):
        """生成hexin-v token"""
        try:
            result = subprocess.run(['node', self.js_file], stdout=subprocess.PIPE, timeout=10)
            return result.stdout.decode().strip()
        except Exception:
            return ''

    def query(self, question, perpage=50, page=1):
        """
        问财自然语言查询
        Args:
            question: 查询语句，如"今日涨停"、"市值大于50亿小于200亿"
            perpage: 每页数量
            page: 页码
        Returns:
            list: [{'code':, 'name':, 'price':, 'change':, ...}, ...]
        """
        token = self._get_token()
        if not token:
            return []

        url = 'https://www.iwencai.com/customized/chart/get-robot-data'
        headers = {
            'hexin-v': token,
            'Content-Type': 'application/json',
            'Referer': 'https://www.iwencai.com/',
        }

        data = {
            'add_info': '{"urp":{"scene":1,"company":1,"business":1},"contentType":"json","searchInfo":true}',
            'perpage': str(perpage),
            'page': page,
            'source': 'Ths_iwencai_Xuangu',
            'log_info': '{"input_type":"click"}',
            'version': '2.0',
            'secondary_intent': 'stock',
            'question': question,
        }

        try:
            resp = self.session.post(url, json=data, headers=headers, timeout=20)
            result = resp.json()

            if not isinstance(result, dict) or not result.get('data'):
                return []

            answer = result['data'].get('answer', [])
            if not answer:
                return []

            # 解析表格数据
            stocks = []
            for ans in answer:
                txt = ans.get('txt', [])
                for item in txt:
                    if item.get('type') != 'global-result':
                        continue
                    content = item.get('content', {})
                    components = content.get('components', [])
                    for comp in components:
                        if comp.get('show_type') != 'xuangu_tableV1':
                            continue
                        table_data = comp.get('data', {})
                        datas = table_data.get('datas', [])
                        columns = table_data.get('columns', [])

                        # 提取列名映射
                        col_map = {}
                        for col in columns:
                            key = col.get('key', '')
                            label = col.get('label', '')
                            col_map[key] = label

                        # 解析每行数据
                        for row in datas:
                            stock = self._parse_row(row, col_map)
                            if stock and stock.get('code'):
                                stocks.append(stock)

            return stocks
        except Exception as e:
            print(f"问财查询失败: {e}")
            return []

    def _parse_row(self, row, col_map):
        """解析一行数据"""
        stock = {}
        for key, value in row.items():
            label = col_map.get(key, key)
            # 标准化字段名
            if '股票代码' in label or label == 'code':
                stock['code'] = str(value).split('.')[0]
            elif '股票简称' in label or label == 'name':
                stock['name'] = str(value)
            elif '最新价' in label or label == 'price':
                try:
                    stock['price'] = float(value)
                except (ValueError, TypeError):
                    stock['price'] = 0
            elif '涨跌幅' in label or label == 'ratio':
                try:
                    stock['change'] = float(value)
                except (ValueError, TypeError):
                    stock['change'] = 0
            elif '换手率' in label:
                try:
                    stock['turnover'] = float(value)
                except (ValueError, TypeError):
                    stock['turnover'] = 0
            elif '市值' in label and '流通' not in label:
                try:
                    # 市值单位可能是元，转亿
                    val = float(value)
                    if val > 100000000:
                        stock['market_cap'] = val / 100000000
                    else:
                        stock['market_cap'] = val
                except (ValueError, TypeError):
                    pass
            else:
                # 其他字段保留
                safe_label = label.replace('[', '_').replace(']', '_').replace('(', '_').replace(')', '_')
                stock[safe_label] = value

        return stock


# 单例
_wencai_filter = None


def get_wencai_filter():
    global _wencai_filter
    if _wencai_filter is None:
        _wencai_filter = WencaiFilter()
    return _wencai_filter
