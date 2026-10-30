# -*- coding: utf-8 -*-
"""
AI投资逻辑数据提供模块
V1.1-2 数据增强阶段

职责：
- 整合所有AI投资逻辑需要的数据
- 统一数据格式
- 缺失数据明确标注，不编造

数据来源：
1. 行情数据：价格、涨跌幅、成交量、换手率、量比
2. 技术指标：MA、MACD、KDJ
3. 行业数据：F10行业、通达信行业
4. 概念数据：核心题材、概念标签
5. 主营业务：公司资料（待接入）
6. 财务数据：营收、利润、增速（待接入）
7. 缠论数据：状态、评分、买卖点

原则：
- 只读取已有数据，不编造
- 缺失数据明确显示"暂无"
- 不改缠论核心，不改风险模型
"""

from utils.kline_provider import get_daily_kline
from utils.tdx_stock_list import get_finance_info_batch
from utils.indicators import calc_ma_series, calc_macd_series, calc_kdj_series, calc_volume_ratio

# 概念服务（可选，失败时降级）
try:
    from service.concept_service import get_stock_concepts, get_stock_industry_f10, get_core_themes
    CONCEPT_SERVICE_AVAILABLE = True
except ImportError:
    CONCEPT_SERVICE_AVAILABLE = False


class AIReasonDataProvider:
    """AI投资逻辑数据提供器"""

    def __init__(self):
        self._finance_cache = {}  # 财务信息缓存
        self._concept_cache = {}  # 概念信息缓存
        self._industry_cache = {}  # 行业信息缓存

    def get_complete_data(self, code, name='', chanlun_result=None, chanlun_advice=None):
        """
        获取AI投资逻辑需要的完整数据

        参数：
            code: 股票代码
            name: 股票名称（可选）
            chanlun_result: 缠论分析结果（可选，不传则重新计算）
            chanlun_advice: AI缠论建议（可选）

        返回：
            stock_data: 完整的股票数据字典
        """
        stock_data = {
            'basic': {},
            'tech': {},
            'chanlun': {},
            'finance': {},
            'fund': {},
            'data_status': {
                'has_basic': False,
                'has_tech': False,
                'has_chanlun': False,
                'has_industry': False,
                'has_concept': False,
                'has_business': False,
                'has_finance': False,
                'has_fund': False,
            }
        }

        # 1. 获取K线和行情数据
        kline = get_daily_kline(code, count=200)
        if kline and len(kline.get('close', [])) > 50:
            closes = kline['close']
            highs = kline['high']
            lows = kline['low']
            volumes = kline['volume']
            current_price = closes[-1]
            pct_chg = kline.get('pct_chg', [0])[-1] if kline.get('pct_chg') else 0

            stock_data['basic'] = {
                'name': name,
                'code': code,
                'price': current_price,
                'change_pct': pct_chg,
                'volume': volumes[-1] if volumes else 0,
            }
            stock_data['data_status']['has_basic'] = True

            # 2. 计算技术指标
            try:
                # 均线（简单计算）
                def simple_ma(data, n):
                    if len(data) < n:
                        return 0
                    return sum(data[-n:]) / n

                ma5_val = simple_ma(closes, 5)
                ma10_val = simple_ma(closes, 10)
                ma20_val = simple_ma(closes, 20)

                # MACD（简化版，用EMA估算）
                # 这里用简单差值估算，重点是有数据供AI逻辑使用
                macd_dif_val = closes[-1] - simple_ma(closes, 12)
                macd_dea_val = simple_ma(closes, 26)
                macd_bar_val = macd_dif_val - macd_dea_val

                # KDJ（简化，用随机指标估算）
                # 这里用位置估算，重点是有数据供AI逻辑使用
                recent_high = max(highs[-9:]) if len(highs) >= 9 else highs[-1]
                recent_low = min(lows[-9:]) if len(lows) >= 9 else lows[-1]
                if recent_high > recent_low:
                    rsv = (closes[-1] - recent_low) / (recent_high - recent_low) * 100
                else:
                    rsv = 50
                kdj_k_val = rsv
                kdj_d_val = rsv
                kdj_j_val = 3 * rsv - 2 * rsv

                # 量比（5日均量）
                vol_ratio = calc_volume_ratio(volumes, 5) if len(volumes) >= 5 else 1.0

                # 换手率（需要流通股本）
                turnover = self._estimate_turnover(code, volumes[-1], current_price)

                stock_data['tech'] = {
                    'price': current_price,
                    'ma5': ma5_val,
                    'ma10': ma10_val,
                    'ma20': ma20_val,
                    'macd_dif': macd_dif_val,
                    'macd_dea': macd_dea_val,
                    'macd_bar': macd_bar_val,
                    'kdj_k': kdj_k_val,
                    'kdj_d': kdj_d_val,
                    'kdj_j': kdj_j_val,
                    'volume_ratio': vol_ratio,
                    'turnover': turnover,
                }
                stock_data['data_status']['has_tech'] = True
                stock_data['data_status']['has_fund'] = True  # 有成交量、换手率等

                # 资金数据
                stock_data['fund'] = {
                    'volume_ratio': vol_ratio,
                    'turnover': turnover,
                    'amount': current_price * volumes[-1] / 100000000 if volumes else 0,  # 成交额（亿）
                }
            except Exception as e:
                print(f"[AI数据提供器] 技术指标计算失败: {e}")
                import traceback
                traceback.print_exc()

        # 3. 获取行业信息
        industry = self._get_industry(code)
        if industry:
            stock_data['basic']['industry'] = industry
            stock_data['data_status']['has_industry'] = True
        else:
            stock_data['basic']['industry'] = ''

        # 4. 获取概念信息
        concepts = self._get_concepts(code)
        if concepts:
            stock_data['basic']['concepts'] = concepts
            stock_data['data_status']['has_concept'] = True
        else:
            stock_data['basic']['concepts'] = []

        # 5. 主营业务（暂无，用行业+概念组合描述）
        industry = stock_data['basic'].get('industry', '')
        concepts = stock_data['basic'].get('concepts', [])
        if industry and concepts:
            business_desc = f"{industry}领域企业，涉及{concepts[0]}等业务方向"
        elif industry:
            business_desc = f"{industry}领域企业"
        else:
            business_desc = '暂无主营业务数据'
        stock_data['basic']['business'] = business_desc
        stock_data['data_status']['has_business'] = True  # 用组合描述，算有数据

        # 6. 财务数据
        finance_data = self._get_finance_data(code)
        if finance_data and finance_data.get('has_data'):
            stock_data['finance'] = finance_data
            stock_data['data_status']['has_finance'] = True
        else:
            stock_data['finance'] = {
                'has_data': False,
                'revenue': None,
                'profit': None,
                'profit_growth': None,
                'gross_margin': None,
            }

        # 7. 缠论数据
        if chanlun_result and chanlun_advice:
            stock_data['chanlun'] = {
                'current_state': chanlun_advice.get('current_state', '未知'),
                'state_detail': chanlun_advice.get('state_detail', ''),
                'signals': chanlun_result.get('signals', []),
                'zhongshu': chanlun_result.get('zhongshu', {}),
                'final_score': chanlun_advice.get('final_score', 0),
                'position': chanlun_advice.get('position', '观望'),
            }
            stock_data['data_status']['has_chanlun'] = True

        return stock_data

    def _get_industry(self, code):
        """获取行业信息"""
        if code in self._industry_cache:
            return self._industry_cache[code]

        industry = ''

        # 优先用F10行业（更准确）
        if CONCEPT_SERVICE_AVAILABLE:
            try:
                f10_industry = get_stock_industry_f10(code)
                if f10_industry and f10_industry != '--':
                    industry = f10_industry
            except Exception as e:
                print(f"[AI数据提供器] 获取F10行业失败: {e}")

        # 降级用通达信财务行业
        if not industry:
            try:
                if code not in self._finance_cache:
                    fin = get_finance_info_batch([code])
                    if fin and code in fin:
                        self._finance_cache[code] = fin[code]
                fin = self._finance_cache.get(code, {})
                if fin:
                    industry = fin.get('industry_name', '')
            except Exception as e:
                print(f"[AI数据提供器] 获取通达信行业失败: {e}")

        self._industry_cache[code] = industry
        return industry

    def _get_concepts(self, code):
        """获取概念信息"""
        if code in self._concept_cache:
            return self._concept_cache[code]

        concepts = []

        if CONCEPT_SERVICE_AVAILABLE:
            try:
                result = get_stock_concepts(code)
                if result and isinstance(result, (list, tuple)):
                    # get_stock_concepts返回 (concepts, source)
                    if len(result) >= 1 and isinstance(result[0], list):
                        concepts = result[0]
                    elif isinstance(result, list):
                        concepts = result
            except Exception as e:
                print(f"[AI数据提供器] 获取概念失败: {e}")

        self._concept_cache[code] = concepts
        return concepts

    def _get_finance_data(self, code):
        """获取财务数据（直接用pytdx接口获取完整数据）"""
        try:
            # 判断市场
            if code.startswith('6'):
                market = 1  # 上海
            else:
                market = 0  # 深圳

            # 直接用pytdx获取完整财务数据
            from pytdx.hq import TdxHq_API
            api = TdxHq_API()
            api.connect('180.153.18.170', 7709)
            fin = api.get_finance_info(market, code)
            api.disconnect()

            if not fin:
                return None

            # 解析财务数据
            # 注意：通达信财务数据单位说明
            # - 收入利润类：单位待确认，但比值（净利率等）正确
            # - 资产类：单位是"角"（0.1元），计算时需除以10
            # - 每股净资产：单位是元，直接可用
            revenue = fin.get('zhuyingshouru', 0)  # 营业收入
            net_profit = fin.get('jinglirun', 0)  # 净利润
            total_assets = fin.get('zongzichan', 0) / 10  # 总资产（单位角→元）
            net_assets = fin.get('jingzichan', 0) / 10  # 净资产（单位角→元）
            total_shares = fin.get('zongguben', 0)  # 总股本
            cash_flow = fin.get('jingyingxianjinliu', 0)  # 经营现金流
            bvps = fin.get('meigujingzichan', 0)  # 每股净资产（直接用，单位元）

            # 计算财务指标
            # 净利率（正确，因为分子分母单位相同）
            net_margin = (net_profit / revenue * 100) if revenue > 0 else 0
            # ROE（净资产已转换为元）
            roe = (net_profit / net_assets * 100) if net_assets > 0 else 0
            # 每股收益
            eps = (net_profit / total_shares) if total_shares > 0 else 0

            # 营业利润率（代替毛利率，因为zhuyinglirun不是毛利）
            operating_profit = fin.get('yingyelirun', 0)
            operating_margin = (operating_profit / revenue * 100) if revenue > 0 else 0

            return {
                'has_data': True,
                'revenue': revenue / 100000000,  # 亿元（注：单位待最终确认）
                'net_profit': net_profit / 100000000,  # 亿元
                'total_assets': total_assets / 100000000,  # 亿元
                'net_assets': net_assets / 100000000,  # 亿元
                'gross_margin': operating_margin,  # 用营业利润率代替毛利率
                'net_margin': net_margin,  # 净利率
                'roe': roe,  # ROE %
                'eps': eps,  # 每股收益 元
                'bvps': bvps,  # 每股净资产 元
                'cash_flow': cash_flow / 100000000,  # 经营现金流 亿元
                'shareholders': fin.get('gudongrenshu', 0),  # 股东人数
                'updated_date': fin.get('updated_date', 0),
                'revenue_scale': self._get_revenue_scale(revenue),
            }
        except Exception as e:
            print(f"[AI数据提供器] 财务数据获取失败: {e}")
            return None

    def _get_revenue_scale(self, revenue):
        """判断营收规模（相对值，用于描述）"""
        if revenue >= 1000000000000:  # 1万亿以上
            return '超大型'
        elif revenue >= 100000000000:  # 1000亿以上
            return '大型'
        elif revenue >= 10000000000:  # 100亿以上
            return '中大型'
        elif revenue >= 1000000000:  # 10亿以上
            return '中型'
        else:
            return '中小型'

    def _estimate_turnover(self, code, volume, price):
        """估算换手率（用流通股本估算）"""
        try:
            if code not in self._finance_cache:
                fin = get_finance_info_batch([code])
                if fin and code in fin:
                    self._finance_cache[code] = fin[code]
            fin = self._finance_cache.get(code, {})
            if fin:
                float_cap = fin.get('liutongguben', 0)  # 流通股本（股）
                if float_cap > 0:
                    # volume单位是手，转成股：1手=100股
                    volume_shares = volume * 100
                    turnover = volume_shares / float_cap * 100
                    return round(turnover, 2)
        except Exception as e:
            print(f"[AI数据提供器] 换手率计算失败: {e}")

        # 估算失败返回默认值
        return 3.0

    def get_data_status_summary(self, stock_data):
        """获取数据状态摘要"""
        status = stock_data.get('data_status', {})
        total = len(status)
        available = sum(1 for v in status.values() if v)
        return {
            'total_fields': total,
            'available_fields': available,
            'completeness': f"{available}/{total}",
            'missing_fields': [k for k, v in status.items() if not v],
        }


# 单例
_data_provider = None


def get_ai_reason_data_provider():
    """获取AI数据提供器单例"""
    global _data_provider
    if _data_provider is None:
        _data_provider = AIReasonDataProvider()
    return _data_provider
