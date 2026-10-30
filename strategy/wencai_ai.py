# -*- coding: utf-8 -*-
"""
同花顺问财AI服务模块
基于pywencai库，提供选股、股票分析、新闻解读等功能
"""
import json
import os


class WencaiAIService:
    """同花顺问财AI服务"""

    def __init__(self):
        self._wencai = None
        self._available = False
        self._init_wencai()

    def _init_wencai(self):
        """初始化问财"""
        try:
            import pywencai
            self._wencai = pywencai
            self._available = True
            print("[WencaiAI] 同花顺问财AI初始化成功")
        except ImportError:
            print("[WencaiAI] pywencai未安装，问财功能不可用")
            self._available = False
        except Exception as e:
            print(f"[WencaiAI] 初始化失败: {e}")
            self._available = False

    def is_available(self):
        """检查问财服务是否可用"""
        return self._available

    def query_stocks(self, query_str, query_type='stock'):
        """
        问财选股查询

        Args:
            query_str: 查询语句（自然语言）
            query_type: 查询类型，stock=股票，fund=基金，等

        Returns:
            list: 股票列表
        """
        if not self._available:
            return []

        try:
            result = self._wencai.get(query=query_str, query_type=query_type)
            if result is not None and len(result) > 0:
                # 转换为标准格式
                stocks = []
                for _, row in result.iterrows():
                    stock = {}
                    for col in result.columns:
                        # 处理多级列名
                        if isinstance(col, tuple):
                            key = col[0] if len(col) > 0 else col
                        else:
                            key = col
                        stock[key] = row[col]
                    stocks.append(stock)
                return stocks
            return []
        except Exception as e:
            print(f"[WencaiAI] 选股查询失败: {e}")
            return []

    def analyze_stock(self, code, name=''):
        """
        用问财分析单只股票

        Args:
            code: 股票代码
            name: 股票名称

        Returns:
            dict: 分析结果
        """
        if not self._available:
            return None

        try:
            # 查询股票的技术面和基本面信息
            query = f"{code} 技术分析 基本面 资金流向"
            result = self._wencai.get(query=query, query_type='stock')

            if result is not None and len(result) > 0:
                # 提取关键信息
                info = {}
                row = result.iloc[0]
                for col in result.columns:
                    if isinstance(col, tuple):
                        key = col[0] if len(col) > 0 else col
                    else:
                        key = col
                    info[key] = row[col]

                return {
                    'code': code,
                    'name': name,
                    'info': info,
                    'raw_data': result.to_dict('records')[0] if len(result) > 0 else {}
                }
            return None
        except Exception as e:
            print(f"[WencaiAI] 股票分析失败: {e}")
            return None

    def interpret_news(self, news_title, news_content=''):
        """
        用问财解读新闻（通过选股方式间接实现）

        Args:
            news_title: 新闻标题
            news_content: 新闻内容

        Returns:
            dict: 解读结果
        """
        if not self._available:
            return None

        try:
            # 从新闻中提取关键词，然后用问财查询相关股票
            # 这是一个简化的实现，实际效果可能有限

            # 提取新闻中的关键信息
            text = news_title + ' ' + news_content

            # 尝试用问财查询相关概念/板块
            # 比如："利好哪些板块"、"哪些股票受益"
            # 由于问财主要是选股，我们可以查询相关的概念股

            # 简化处理：返回空结果，由上层降级处理
            return None

        except Exception as e:
            print(f"[WencaiAI] 新闻解读失败: {e}")
            return None

    def get_trend_breakout_stocks(self):
        """
        问财版趋势突破池选股

        Returns:
            list: 股票列表
        """
        if not self._available:
            return []

        try:
            query = """
            非ST 非创业板 非科创板
            市值大于30亿 市值小于等于230亿
            现价大于近8个月最高价的85%
            现价小于近8个月最高价的130%
            前一天非涨停
            近一年涨停次数大于等于3次
            非地产行业 非农业行业 非酒行业 非保险行业
            """
            # 清理换行和空格
            query = ' '.join(query.split())
            return self.query_stocks(query)
        except Exception as e:
            print(f"[WencaiAI] 趋势突破选股失败: {e}")
            return []

    def get_strong_breakout_stocks(self):
        """
        问财版强势突破池选股

        Returns:
            list: 股票列表
        """
        if not self._available:
            return []

        try:
            query = """
            非ST 非创业板 非科创板
            15个交易日内出现连续4天收盘价站稳20日均线
            突破期间成交量大于120日均量
            突破期间换手率大于7%
            近7日涨停 或 近7日涨幅大于7%
            """
            query = ' '.join(query.split())
            return self.query_stocks(query)
        except Exception as e:
            print(f"[WencaiAI] 强势突破选股失败: {e}")
            return []

    def get_steady_low_stocks(self):
        """
        问财版稳健低吸池选股

        Returns:
            list: 股票列表
        """
        if not self._available:
            return []

        try:
            query = """
            非ST 主板
            近2日累计涨幅小于7%
            当日涨幅小于3%
            振幅小于5%
            换手率大于1%
            换手率小于7%
            RSI14大于30
            RSI14小于70
            按5日量比从高到低排序
            """
            query = ' '.join(query.split())
            return self.query_stocks(query)
        except Exception as e:
            print(f"[WencaiAI] 稳健低吸选股失败: {e}")
            return []

    def get_today_limit_up(self):
        """
        问财版今日涨停股

        Returns:
            list: 股票列表
        """
        if not self._available:
            return []

        try:
            query = "今日涨停 非ST 非新股"
            return self.query_stocks(query)
        except Exception as e:
            print(f"[WencaiAI] 涨停股查询失败: {e}")
            return []

    def get_stock_ai_analysis(self, code, name=''):
        """
        获取股票的AI分析（通过问财多维度查询综合）

        Args:
            code: 股票代码
            name: 股票名称

        Returns:
            dict: AI分析结果
        """
        if not self._available:
            return None

        try:
            result = {
                'code': code,
                'name': name,
                'score': 0,
                'trend': '中性',
                'summary': '',
                'analysis': '',
                'buy_conditions': [],
                'risks': [],
                'suggestion': '观察',
            }

            # 1. 查询技术面
            tech_query = f"{code} 技术面 MA5 MA10 MA20 KDJ MACD 成交量"
            tech_result = self.query_stocks(tech_query)

            # 2. 查询基本面
            fund_query = f"{code} 基本面 市盈率 市净率 净利润 营收"
            fund_result = self.query_stocks(fund_query)

            # 3. 查询资金面
            money_query = f"{code} 资金流向 主力资金 北向资金"
            money_result = self.query_stocks(money_query)

            # 综合分析（简化版）
            analysis_parts = []

            if tech_result and len(tech_result) > 0:
                tech = tech_result[0]
                analysis_parts.append(f"技术面：{self._summarize_tech(tech)}")

            if fund_result and len(fund_result) > 0:
                fund = fund_result[0]
                analysis_parts.append(f"基本面：{self._summarize_fund(fund)}")

            if money_result and len(money_result) > 0:
                money = money_result[0]
                analysis_parts.append(f"资金面：{self._summarize_money(money)}")

            result['analysis'] = '\n'.join(analysis_parts)
            result['summary'] = f"{name}({code})综合分析"

            # 简单评分（基于查询结果数量）
            score = 50
            if tech_result:
                score += 10
            if fund_result:
                score += 10
            if money_result:
                score += 10
            result['score'] = min(score, 95)

            return result

        except Exception as e:
            print(f"[WencaiAI] AI分析失败: {e}")
            return None

    def _summarize_tech(self, tech_data):
        """简化技术面总结"""
        parts = []
        for key, value in tech_data.items():
            if value and str(value) != 'nan':
                key_str = str(key)
                if 'MA' in key_str or '均线' in key_str:
                    parts.append(f"{key_str}={value}")
                elif 'KDJ' in key_str or 'MACD' in key_str:
                    parts.append(f"{key_str}={value}")
        return '；'.join(parts[:5]) if parts else '暂无数据'

    def _summarize_fund(self, fund_data):
        """简化基本面总结"""
        parts = []
        for key, value in fund_data.items():
            if value and str(value) != 'nan':
                key_str = str(key)
                if '市盈率' in key_str or '市净率' in key_str:
                    parts.append(f"{key_str}={value}")
                elif '净利润' in key_str or '营收' in key_str:
                    parts.append(f"{key_str}={value}")
        return '；'.join(parts[:5]) if parts else '暂无数据'

    def _summarize_money(self, money_data):
        """简化资金面总结"""
        parts = []
        for key, value in money_data.items():
            if value and str(value) != 'nan':
                key_str = str(key)
                if '主力' in key_str or '资金' in key_str:
                    parts.append(f"{key_str}={value}")
        return '；'.join(parts[:5]) if parts else '暂无数据'


# 单例
_wencai_ai = None


def get_wencai_ai():
    global _wencai_ai
    if _wencai_ai is None:
        _wencai_ai = WencaiAIService()
    return _wencai_ai
