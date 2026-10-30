# -*- coding: utf-8 -*-
"""
新闻解读模块
分析财经新闻，判断利好/利空哪些板块和个股
优先使用豆包AI，没有配置则使用关键词匹配
"""
import re
from strategy.wencai_ai import get_wencai_ai


class NewsInterpreter:
    """新闻解读器"""

    def __init__(self):
        # 板块关键词映射
        self.sector_keywords = {
            # 新能源
            '新能源': ['新能源', '光伏', '太阳能', '风电', '储能', '锂电池', '动力电池', '新能源车', '电动车', '充电桩'],
            '光伏板块': ['光伏', '硅料', '硅片', '组件', '逆变器', 'HJT', 'TOPCon'],
            '锂电板块': ['锂电池', '动力电池', '锂矿', '正极', '负极', '电解液', '隔膜'],
            '新能源车板块': ['新能源车', '电动车', '新能源汽车', '智能驾驶', '自动驾驶'],
            '风电板块': ['风电', '海上风电', '风机', '塔筒', '叶片'],
            '储能板块': ['储能', '抽水蓄能', '电化学储能', '钠电池', '钒电池'],

            # 科技
            '半导体板块': ['半导体', '芯片', '集成电路', '晶圆', '光刻', '封测', 'EDA', 'MCU', '存储'],
            'AI板块': ['人工智能', 'AI', '大模型', 'GPT', '算力', 'AIGC', 'ChatGPT', '深度学习', '机器学习'],
            '计算机板块': ['软件', '信创', '数字经济', '云计算', '大数据', '数据中心', '东数西算'],
            '通信板块': ['5G', '6G', '通信', '光模块', '光纤', '运营商', '华为'],
            '消费电子板块': ['消费电子', '苹果', 'iPhone', '手机', 'VR', 'AR', 'MR', '可穿戴'],
            '机器人板块': ['机器人', '人形机器人', '工业机器人', '伺服', '减速器'],

            # 医药
            '医药板块': ['医药', '医疗', '创新药', 'CXO', '医疗器械', '医院', '医保'],
            '中药板块': ['中药', '中医', '中药材', '同仁堂', '云南白药'],
            '生物科技板块': ['生物科技', '疫苗', '基因', '细胞治疗', '抗体'],
            '医美板块': ['医美', '美容', '玻尿酸', '肉毒素', '轻医美'],

            # 消费
            '白酒板块': ['白酒', '茅台', '五粮液', '泸州老窖', '汾酒', '洋河'],
            '食品饮料板块': ['食品', '饮料', '乳业', '调味品', '休闲食品', '啤酒'],
            '消费板块': ['消费', '零售', '电商', '免税', '旅游', '酒店', '餐饮'],
            '家电板块': ['家电', '白电', '黑电', '空调', '冰箱', '洗衣机'],

            # 周期
            '房地产板块': ['房地产', '地产', '房企', '楼市', '房价', '保利', '万科'],
            '银行板块': ['银行', '央行', '降息', '降准', 'LPR', '房贷'],
            '证券板块': ['证券', '券商', '牛市', '成交额', '印花税', 'IPO'],
            '保险板块': ['保险', '寿险', '财险', '平安', '中国人寿'],
            '煤炭板块': ['煤炭', '煤价', '动力煤', '焦煤', '中国神华'],
            '石油板块': ['石油', '原油', '油价', 'OPEC', '中石化', '中石油'],
            '有色板块': ['有色金属', '铜', '铝', '黄金', '白银', '锂', '稀土'],
            '钢铁板块': ['钢铁', '钢材', '铁矿石', '宝钢', '武钢'],
            '化工板块': ['化工', '化纤', '塑料', '橡胶', '化肥', '农药'],

            # 基建
            '基建板块': ['基建', '基础设施', '新基建', '铁路', '公路', '水利'],
            '建材板块': ['建材', '水泥', '玻璃', '瓷砖', '石膏板'],
            '工程机械板块': ['工程机械', '挖掘机', '三一重工', '中联重科', '徐工'],

            # 军工
            '军工板块': ['军工', '国防', '军队', '导弹', '战机', '航母', '航天'],
            '航天板块': ['航天', '卫星', '火箭', '空间站', '商业航天'],

            # 农业
            '农业板块': ['农业', '农村', '农民', '乡村振兴', '粮食', '种业'],
            '猪肉板块': ['猪肉', '生猪', '猪价', '牧原', '温氏'],

            # 其他
            '航运板块': ['航运', '集装箱', '海运', '港口', '中远海控'],
            '物流板块': ['物流', '快递', '供应链', '顺丰', '圆通'],
            '环保板块': ['环保', '碳中和', '碳达峰', '绿色', '污水处理'],
            '电力板块': ['电力', '火电', '水电', '核电', '电价'],
            '传媒板块': ['传媒', '影视', '游戏', '出版', '广告', '元宇宙'],
            '纺织服装板块': ['纺织', '服装', '家纺', '服饰'],
        }

        # 个股关键词映射（部分热门股）
        self.stock_keywords = {
            # 白酒
            '贵州茅台': ['茅台', '贵州茅台'],
            '五粮液': ['五粮液'],
            '泸州老窖': ['泸州老窖', '老窖'],
            '山西汾酒': ['汾酒', '山西汾酒'],
            '洋河股份': ['洋河', '洋河股份'],

            # 新能源
            '宁德时代': ['宁德时代', '宁王'],
            '比亚迪': ['比亚迪', 'BYD'],
            '隆基绿能': ['隆基', '隆基绿能'],
            '阳光电源': ['阳光电源'],
            '通威股份': ['通威', '通威股份'],
            '天齐锂业': ['天齐锂业', '天齐'],
            '赣锋锂业': ['赣锋锂业', '赣锋'],

            # 科技
            '中芯国际': ['中芯国际', '中芯'],
            '北方华创': ['北方华创', '华创'],
            '韦尔股份': ['韦尔股份', '韦尔'],
            '海康威视': ['海康威视', '海康'],
            '大华股份': ['大华股份', '大华'],
            '科大讯飞': ['科大讯飞', '讯飞'],
            '三六零': ['三六零', '360'],
            '昆仑万维': ['昆仑万维', '昆仑'],
            '工业富联': ['工业富联', '富士康'],

            # 医药
            '恒瑞医药': ['恒瑞医药', '恒瑞'],
            '药明康德': ['药明康德', '药明'],
            '迈瑞医疗': ['迈瑞医疗', '迈瑞'],
            '片仔癀': ['片仔癀'],
            '云南白药': ['云南白药'],

            # 金融
            '招商银行': ['招商银行', '招行'],
            '平安银行': ['平安银行'],
            '中信证券': ['中信证券', '中信'],
            '东方财富': ['东方财富', '东财'],
            '中国平安': ['中国平安', '平安'],

            # 消费
            '美的集团': ['美的集团', '美的'],
            '格力电器': ['格力电器', '格力'],
            '海尔智家': ['海尔智家', '海尔'],
            '伊利股份': ['伊利股份', '伊利'],
            '海天味业': ['海天味业', '海天'],

            # 其他
            '中国中免': ['中国中免', '中免'],
            '顺丰控股': ['顺丰控股', '顺丰'],
            '三一重工': ['三一重工', '三一'],
            '紫金矿业': ['紫金矿业', '紫金'],
            '中国神华': ['中国神华', '神华'],
        }

        # 利好关键词
        self.bullish_words = [
            '上涨', '增长', '突破', '利好', '盈利', '大增', '超预期',
            '创新高', '翻倍', '爆发', '飙升', '走强', '受益',
            '订单', '中标', '签约', '合作', '扩产', '产能释放',
            '政策支持', '降息', '降准', '宽松', '刺激', '复苏',
            '回暖', '改善', '向好', '乐观', '看多', '买入',
            '推荐', '上调', '资金流入', '主力净流入', '抄底',
            '反弹', '反转', '拐点', '启动', '拉升', '封板',
            '连板', '龙头', '风口', '景气', '高景气', '增持',
            '回购', '业绩预增', '大幅增长',
        ]

        # 利空关键词
        self.bearish_words = [
            '下跌', '下滑', '下降', '减少', '利空', '亏损', '大跌',
            '暴跌', '创新低', '不及预期', '腰斩', '崩盘', '走弱',
            '受损', '违约', '逾期', '债务', '诉讼', '处罚',
            '立案', '调查', '减持', '抛售', '出逃', '资金流出',
            '主力净流出', '跳水', '崩', '低迷', '疲软', '衰退',
            '下行', '承压', '看空', '卖出', '下调', '降级',
            '业绩预减', '大幅下滑', '爆雷', '退市', '风险',
        ]

    def interpret(self, news):
        """
        解读单条新闻
        优先使用豆包AI，没有配置则使用关键词匹配

        Args:
            news: dict或NewsItem对象，包含title, content等字段
        Returns:
            dict: {
                'title': str,
                'time': str,
                'source': str,
                'content': str,
                'sentiment': str,  # 利好/利空/中性
                'sentiment_score': float,  # -1到1
                'bullish_sectors': list,  # 利好的板块列表
                'bearish_sectors': list,  # 利空的板块列表
                'bullish_stocks': list,  # 利好的个股列表
                'bearish_stocks': list,  # 利空的个股列表
                'reasons': list,  # 分析原因
                'summary': str,  # AI摘要（AI模式才有）
                'analysis': str,  # AI详细分析（AI模式才有）
                'suggestion': str,  # AI投资建议（AI模式才有）
                'use_ai': bool,  # 是否使用了AI
            }
        """
        # 兼容dict和对象两种格式
        if isinstance(news, dict):
            title = news.get('title', '') or ''
            content = news.get('content', '') or ''
            time_str = news.get('time', '') or news.get('time_str', '') or ''
            source = news.get('source', '') or ''
        else:
            title = getattr(news, 'title', '') or ''
            content = getattr(news, 'content', '') or ''
            time_str = getattr(news, 'time_str', '') or getattr(news, 'time', '') or ''
            source = getattr(news, 'source', '') or ''

        text = title + ' ' + content

        if not text.strip():
            return self._empty_result(news)

        # 使用同花顺问财AI解读新闻
        wencai_ai = get_wencai_ai()
        if wencai_ai.is_available():
            wencai_result = self._interpret_with_wencai(title, content)
            if wencai_result:
                result = {
                    'title': title,
                    'time': time_str,
                    'source': source,
                    'content': content,
                    'sentiment': wencai_result.get('sentiment', '中性'),
                    'sentiment_score': wencai_result.get('sentiment_score', 0),
                    'bullish_sectors': wencai_result.get('bullish_sectors', []),
                    'bearish_sectors': wencai_result.get('bearish_sectors', []),
                    'bullish_stocks': wencai_result.get('bullish_stocks', []),
                    'bearish_stocks': wencai_result.get('bearish_stocks', []),
                    'reasons': wencai_result.get('reasons', []),
                    'summary': wencai_result.get('summary', ''),
                    'analysis': wencai_result.get('analysis', ''),
                    'suggestion': wencai_result.get('suggestion', ''),
                    'use_ai': True,
                    'ai_source': 'wencai',
                }
                return result

        # 降级使用关键词匹配
        return self._keyword_interpret(title, content, time_str, source)

    def _interpret_with_wencai(self, title, content):
        """
        用同花顺问财AI解读新闻

        Args:
            title: 新闻标题
            content: 新闻内容

        Returns:
            dict: 解读结果
        """
        try:
            wencai_ai = get_wencai_ai()
            text = title + ' ' + content

            # 1. 先用关键词匹配判断情绪和板块
            keyword_result = self._keyword_interpret(title, content, '', '')

            # 2. 用问财查询相关概念股
            bullish_stocks = []
            bearish_stocks = []
            bullish_sectors = keyword_result.get('bullish_sectors', [])
            bearish_sectors = keyword_result.get('bearish_sectors', [])
            sentiment = keyword_result.get('sentiment', '中性')
            sentiment_score = keyword_result.get('sentiment_score', 0)

            # 3. 如果有利好板块，用问财查询相关概念股
            if bullish_sectors and sentiment == '利好':
                for sector in bullish_sectors[:2]:  # 最多查2个板块
                    try:
                        query = f"{sector}概念股 龙头股 按市值从大到小排序"
                        stocks = wencai_ai.query_stocks(query)
                        if stocks:
                            for stock in stocks[:5]:
                                name = ''
                                for key, value in stock.items():
                                    if '名称' in str(key) or 'name' in str(key).lower():
                                        name = str(value)
                                        break
                                if name and name not in bullish_stocks:
                                    bullish_stocks.append(name)
                    except Exception:
                        continue

            # 4. 如果有利空板块，用问财查询相关概念股
            if bearish_sectors and sentiment == '利空':
                for sector in bearish_sectors[:2]:
                    try:
                        query = f"{sector}概念股 龙头股 按市值从大到小排序"
                        stocks = wencai_ai.query_stocks(query)
                        if stocks:
                            for stock in stocks[:5]:
                                name = ''
                                for key, value in stock.items():
                                    if '名称' in str(key) or 'name' in str(key).lower():
                                        name = str(value)
                                        break
                                if name and name not in bearish_stocks:
                                    bearish_stocks.append(name)
                    except Exception:
                        continue

            # 5. 直接匹配新闻中提到的个股
            for stock_name, keywords in self.stock_keywords.items():
                for kw in keywords:
                    if kw in text:
                        if sentiment_score > 0 and stock_name not in bullish_stocks:
                            bullish_stocks.append(stock_name)
                        elif sentiment_score < 0 and stock_name not in bearish_stocks:
                            bearish_stocks.append(stock_name)
                        break

            # 6. 生成分析原因
            reasons = []
            if bullish_sectors:
                reasons.append(f"利好板块：{'、'.join(bullish_sectors[:5])}")
            if bearish_sectors:
                reasons.append(f"利空板块：{'、'.join(bearish_sectors[:5])}")
            if bullish_stocks:
                reasons.append(f"利好个股：{'、'.join(bullish_stocks[:5])}")
            if bearish_stocks:
                reasons.append(f"利空个股：{'、'.join(bearish_stocks[:5])}")

            # 提取关键利好/利空词
            bullish_matched = [w for w in self.bullish_words if w in text]
            bearish_matched = [w for w in self.bearish_words if w in text]
            if bullish_matched:
                reasons.append(f"利好信号：{'、'.join(bullish_matched[:5])}")
            if bearish_matched:
                reasons.append(f"利空信号：{'、'.join(bearish_matched[:5])}")

            # 7. 生成摘要和分析
            summary = f"问财AI解读：{title[:30]}..."
            analysis_parts = []
            if sentiment == '利好':
                analysis_parts.append(f"整体情绪偏利好，情绪分数 {sentiment_score:.2f}")
            elif sentiment == '利空':
                analysis_parts.append(f"整体情绪偏利空，情绪分数 {sentiment_score:.2f}")
            else:
                analysis_parts.append(f"整体情绪中性，情绪分数 {sentiment_score:.2f}")

            if bullish_sectors:
                analysis_parts.append(f"涉及利好板块 {len(bullish_sectors)} 个")
            if bearish_sectors:
                analysis_parts.append(f"涉及利空板块 {len(bearish_sectors)} 个")
            if bullish_stocks:
                analysis_parts.append(f"利好相关个股 {len(bullish_stocks)} 只")
            if bearish_stocks:
                analysis_parts.append(f"利空相关个股 {len(bearish_stocks)} 只")

            analysis = '\n'.join(analysis_parts)

            # 8. 投资建议
            if sentiment == '利好':
                suggestion = "可关注相关板块和个股的交易性机会，注意控制仓位"
            elif sentiment == '利空':
                suggestion = "注意规避相关板块和个股的短期风险，保持谨慎"
            else:
                suggestion = "消息中性，对市场影响有限，继续观察"

            return {
                'sentiment': sentiment,
                'sentiment_score': sentiment_score,
                'bullish_sectors': bullish_sectors,
                'bearish_sectors': bearish_sectors,
                'bullish_stocks': bullish_stocks[:10],
                'bearish_stocks': bearish_stocks[:10],
                'reasons': reasons,
                'summary': summary,
                'analysis': analysis,
                'suggestion': suggestion,
            }

        except Exception as e:
            print(f"问财新闻解读失败: {e}")
            return None

    def _keyword_interpret(self, title, content, time_str, source):
        """基于关键词匹配的新闻解读（降级方案）"""
        text = title + ' ' + content

        # 1. 判断整体情绪
        sentiment_score = self._calc_sentiment(text)
        if sentiment_score > 0.2:
            sentiment = '利好'
        elif sentiment_score < -0.2:
            sentiment = '利空'
        else:
            sentiment = '中性'

        # 2. 提取相关板块
        bullish_sectors = []
        bearish_sectors = []
        matched_sectors = set()

        for sector, keywords in self.sector_keywords.items():
            for kw in keywords:
                if kw in text:
                    matched_sectors.add(sector)
                    break

        # 根据情绪判断是利好还是利空板块
        if sentiment_score > 0:
            bullish_sectors = list(matched_sectors)
        elif sentiment_score < 0:
            bearish_sectors = list(matched_sectors)
        else:
            # 中性时，根据上下文判断
            bullish_sectors = list(matched_sectors)

        # 3. 提取相关个股
        bullish_stocks = []
        bearish_stocks = []
        matched_stocks = set()

        for stock, keywords in self.stock_keywords.items():
            for kw in keywords:
                if kw in text:
                    matched_stocks.add(stock)
                    break

        if sentiment_score > 0:
            bullish_stocks = list(matched_stocks)
        elif sentiment_score < 0:
            bearish_stocks = list(matched_stocks)
        else:
            bullish_stocks = list(matched_stocks)

        # 4. 生成分析原因
        reasons = []
        if bullish_sectors:
            reasons.append(f"涉及板块：{'、'.join(bullish_sectors[:5])}")
        if bearish_sectors:
            reasons.append(f"利空板块：{'、'.join(bearish_sectors[:5])}")
        if bullish_stocks:
            reasons.append(f"涉及个股：{'、'.join(bullish_stocks[:5])}")
        if bearish_stocks:
            reasons.append(f"利空个股：{'、'.join(bearish_stocks[:5])}")

        # 提取关键利好/利空词
        bullish_matched = [w for w in self.bullish_words if w in text]
        bearish_matched = [w for w in self.bearish_words if w in text]
        if bullish_matched:
            reasons.append(f"利好信号：{'、'.join(bullish_matched[:5])}")
        if bearish_matched:
            reasons.append(f"利空信号：{'、'.join(bearish_matched[:5])}")

        return {
            'title': title,
            'time': time_str,
            'source': source,
            'content': content,
            'sentiment': sentiment,
            'sentiment_score': sentiment_score,
            'bullish_sectors': bullish_sectors,
            'bearish_sectors': bearish_sectors,
            'bullish_stocks': bullish_stocks,
            'bearish_stocks': bearish_stocks,
            'reasons': reasons,
            'summary': '',
            'analysis': '',
            'suggestion': '',
            'use_ai': False,
        }

    def interpret_news_list(self, news_list):
        """
        解读新闻列表
        Args:
            news_list: 新闻列表
        Returns:
            dict: {
                'overall_sentiment': str,
                'overall_score': float,
                'top_bullish_sectors': list,  # 利好最多的板块
                'top_bearish_sectors': list,  # 利空最多的板块
                'top_bullish_stocks': list,  # 利好最多的个股
                'top_bearish_stocks': list,  # 利空最多的个股
                'interpreted_news': list,  # 解读后的新闻列表
            }
        """
        if not news_list:
            return {
                'overall_sentiment': '中性',
                'overall_score': 0,
                'top_bullish_sectors': [],
                'top_bearish_sectors': [],
                'top_bullish_stocks': [],
                'top_bearish_stocks': [],
                'interpreted_news': [],
            }

        interpreted = []
        total_score = 0
        sector_bullish_count = {}
        sector_bearish_count = {}
        stock_bullish_count = {}
        stock_bearish_count = {}

        for news in news_list:
            result = self.interpret(news)
            interpreted.append(result)

            total_score += result['sentiment_score']

            # 统计板块
            for s in result['bullish_sectors']:
                sector_bullish_count[s] = sector_bullish_count.get(s, 0) + 1
            for s in result['bearish_sectors']:
                sector_bearish_count[s] = sector_bearish_count.get(s, 0) + 1

            # 统计个股
            for s in result['bullish_stocks']:
                stock_bullish_count[s] = stock_bullish_count.get(s, 0) + 1
            for s in result['bearish_stocks']:
                stock_bearish_count[s] = stock_bearish_count.get(s, 0) + 1

        # 计算整体情绪
        n = len(news_list)
        overall_score = total_score / n if n > 0 else 0
        overall_score = max(-1, min(1, overall_score))

        if overall_score > 0.15:
            overall_sentiment = '偏多'
        elif overall_score > 0.05:
            overall_sentiment = '中性偏多'
        elif overall_score < -0.15:
            overall_sentiment = '偏空'
        elif overall_score < -0.05:
            overall_sentiment = '中性偏空'
        else:
            overall_sentiment = '中性'

        # 排序
        top_bullish_sectors = sorted(sector_bullish_count.items(), key=lambda x: x[1], reverse=True)[:10]
        top_bearish_sectors = sorted(sector_bearish_count.items(), key=lambda x: x[1], reverse=True)[:10]
        top_bullish_stocks = sorted(stock_bullish_count.items(), key=lambda x: x[1], reverse=True)[:10]
        top_bearish_stocks = sorted(stock_bearish_count.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            'overall_sentiment': overall_sentiment,
            'overall_score': round(overall_score, 3),
            'top_bullish_sectors': top_bullish_sectors,
            'top_bearish_sectors': top_bearish_sectors,
            'top_bullish_stocks': top_bullish_stocks,
            'top_bearish_stocks': top_bearish_stocks,
            'interpreted_news': interpreted,
        }

    def _calc_sentiment(self, text):
        """计算情绪分数"""
        if not text:
            return 0

        bullish_count = 0
        bearish_count = 0

        # 匹配利好词
        for word in self.bullish_words:
            count = text.count(word)
            if count > 0:
                # 检查前面是否有否定词
                negated = self._is_negated(text, word)
                if negated:
                    bearish_count += count
                else:
                    bullish_count += count

        # 匹配利空词
        for word in self.bearish_words:
            count = text.count(word)
            if count > 0:
                # 检查前面是否有否定词
                negated = self._is_negated(text, word)
                if negated:
                    bullish_count += count
                else:
                    bearish_count += count

        total = bullish_count + bearish_count
        if total == 0:
            return 0

        score = (bullish_count - bearish_count) / total
        return score

    def _is_negated(self, text, keyword):
        """检查关键词前面是否有否定词"""
        negation_words = ['不', '未', '无', '没', '非', '难', '避免', '防止', '减少']
        try:
            idx = text.index(keyword)
            prefix = text[max(0, idx - 10):idx]
            for neg in negation_words:
                if neg in prefix:
                    return True
            return False
        except ValueError:
            return False

    def _empty_result(self, news):
        """空结果"""
        # 兼容dict和对象
        if isinstance(news, dict):
            title = news.get('title', '')
            time_str = news.get('time', '') or news.get('time_str', '')
            source = news.get('source', '')
        else:
            title = getattr(news, 'title', '')
            time_str = getattr(news, 'time_str', '') or getattr(news, 'time', '')
            source = getattr(news, 'source', '')

        return {
            'title': title,
            'time': time_str,
            'source': source,
            'content': '',
            'sentiment': '中性',
            'sentiment_score': 0,
            'bullish_sectors': [],
            'bearish_sectors': [],
            'bullish_stocks': [],
            'bearish_stocks': [],
            'reasons': [],
            'summary': '',
            'analysis': '',
            'suggestion': '',
            'use_ai': False,
        }


# 单例
_interpreter = None


def get_news_interpreter():
    global _interpreter
    if _interpreter is None:
        _interpreter = NewsInterpreter()
    return _interpreter
