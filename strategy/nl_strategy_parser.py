# -*- coding: utf-8 -*-
"""
自然语言策略解析器

双模式解析：
1. LLM模式（优先）：通过Ollama本地大模型理解自然语言，输出标准JSON
2. 关键词模式（回退）：正则表达式关键词匹配

AI只负责理解和输出JSON，不执行选股计算，确保安全可控。
"""
import re

from strategy.strategy_schema import DEFAULT_CONDITIONS


class NLStrategyParser:
    """自然语言策略解析器（双模式）"""

    def __init__(self, use_llm=True):
        """
        初始化解析器

        Args:
            use_llm: 是否使用大模型模式（默认True，不可用时自动回退）
        """
        self.conditions = {}
        self.use_llm = use_llm
        self._llm_engine = None
        self._llm_available = None
        self._last_mode = None  # 记录上次使用的模式

    def _get_llm_engine(self):
        """懒加载LLM引擎"""
        if self._llm_engine is None:
            try:
                from strategy.llm_engine import get_llm_engine
                self._llm_engine = get_llm_engine()
            except Exception as e:
                print(f"[NLParser] LLM引擎加载失败: {e}")
                self._llm_engine = None
        return self._llm_engine

    def is_llm_available(self):
        """检测LLM是否可用"""
        if self._llm_available is not None:
            return self._llm_available
        engine = self._get_llm_engine()
        if engine is None:
            self._llm_available = False
            return False
        self._llm_available = engine.is_available()
        return self._llm_available

    def get_last_mode(self):
        """获取上次解析使用的模式"""
        return self._last_mode

    def parse(self, text):
        """
        解析自然语言策略描述

        优先使用LLM，失败或不可用时回退到关键词匹配。

        Args:
            text: 用户描述，如"主板非ST，价格5-60元，市值30-230亿，年涨停≥3次"

        Returns:
            dict: 解析后的条件字典
        """
        text = text.strip()
        if not text:
            self.conditions = DEFAULT_CONDITIONS.copy()
            self._last_mode = "empty"
            return self.conditions

        # 尝试LLM模式
        if self.use_llm and self.is_llm_available():
            result = self._parse_with_llm(text)
            if result is not None:
                self.conditions = result
                self._last_mode = "llm"
                return self.conditions

        # 回退到关键词匹配模式
        self.conditions = self._parse_with_keywords(text)
        self._last_mode = "keyword"
        return self.conditions

    def _parse_with_llm(self, text):
        """使用大模型解析"""
        try:
            engine = self._get_llm_engine()
            if engine is None:
                return None
            result = engine.parse_strategy(text)
            if result and isinstance(result, dict):
                return result
            return None
        except Exception as e:
            print(f"[NLParser] LLM解析失败，回退关键词模式: {e}")
            return None

    def _parse_with_keywords(self, text):
        """使用关键词匹配解析（原有逻辑）"""
        conditions = DEFAULT_CONDITIONS.copy()

        # 1. 主板过滤
        if re.search(r'主板', text):
            conditions["main_board_only"] = True

        # 2. ST过滤
        if re.search(r'剔除ST|排除ST|非ST|去掉ST|不要ST', text, re.IGNORECASE):
            conditions["exclude_st"] = True

        # 3. 价格范围
        self._parse_price(text, conditions)

        # 4. 市值范围
        self._parse_market_cap(text, conditions)

        # 5. 换手率范围
        self._parse_turnover(text, conditions)

        # 6. 量比
        self._parse_volume_ratio(text, conditions)

        # 7. 涨停次数
        self._parse_limit_up(text, conditions)

        # 8. 振幅
        self._parse_amplitude(text, conditions)

        # 9. 行业排除
        self._parse_industries(text, conditions)

        # 10. 高点比例
        self._parse_high_ratio(text, conditions)

        # 11. 前一天未涨停
        if re.search(r'前一天未涨停|昨日未涨停|前一日未涨停|昨天没涨停', text):
            conditions["no_limit_up_yesterday"] = True

        # 12. 涨跌幅
        self._parse_pct_chg(text, conditions)

        # 13. 技术指标（简单关键词）
        if re.search(r'MACD金叉|macd金叉|MACD金|macd金', text, re.IGNORECASE):
            conditions["macd_golden_cross"] = True
        if re.search(r'MACD死叉|macd死叉', text, re.IGNORECASE):
            conditions["macd_dead_cross"] = True
        if re.search(r'均线多头|多头排列|MA5.*MA9.*MA20', text, re.IGNORECASE):
            conditions["ma_bullish"] = True
        if re.search(r'穿九|MA5上穿MA9|5日线上穿9日线', text, re.IGNORECASE):
            conditions["ma5_cross_ma9"] = True

        return conditions

    def _parse_price(self, text, conditions):
        """解析价格范围"""
        patterns = [
            r'价格\s*(\d+\.?\d*)\s*[-~到至]\s*(\d+\.?\d*)\s*元',
            r'股价\s*(\d+\.?\d*)\s*[-~到至]\s*(\d+\.?\d*)\s*元',
            r'(\d+\.?\d*)\s*元\s*[-~到至]\s*(\d+\.?\d*)\s*元',
            r'价格大于\s*(\d+\.?\d*)\s*元?且?小于\s*(\d+\.?\d*)',
        ]
        for p in patterns:
            m = re.search(p, text)
            if m:
                conditions["price_range"] = [float(m.group(1)), float(m.group(2))]
                return

        m = re.search(r'价格不?低[于过]?\s*(\d+\.?\d*)\s*元', text)
        if m:
            conditions["price_range"][0] = float(m.group(1))

        m = re.search(r'价格不?高[于过]?\s*(\d+\.?\d*)\s*元', text)
        if m:
            conditions["price_range"][1] = float(m.group(1))

        m = re.search(r'剔除\s*(\d+\.?\d*)\s*元以上', text)
        if m:
            conditions["price_range"][1] = float(m.group(1))

        m = re.search(r'剔除\s*(\d+\.?\d*)\s*元以下', text)
        if m:
            conditions["price_range"][0] = float(m.group(1))

    def _parse_market_cap(self, text, conditions):
        """解析市值范围"""
        patterns = [
            r'市值\s*(\d+\.?\d*)\s*[-~到至]\s*(\d+\.?\d*)\s*亿',
            r'总市值\s*(\d+\.?\d*)\s*[-~到至]\s*(\d+\.?\d*)\s*亿',
            r'(\d+\.?\d*)\s*亿\s*[-~到至]\s*(\d+\.?\d*)\s*亿',
            r'市值大于\s*(\d+\.?\d*)\s*亿?且?小于等于?\s*(\d+\.?\d*)\s*亿',
        ]
        for p in patterns:
            m = re.search(p, text)
            if m:
                conditions["market_cap_range"] = [float(m.group(1)), float(m.group(2))]
                return

        m = re.search(r'市值不?低[于过]?\s*(\d+\.?\d*)\s*亿', text)
        if m:
            conditions["market_cap_range"][0] = float(m.group(1))

        m = re.search(r'市值不?高[于过]?\s*(\d+\.?\d*)\s*亿', text)
        if m:
            conditions["market_cap_range"][1] = float(m.group(1))

    def _parse_turnover(self, text, conditions):
        """解析换手率范围"""
        patterns = [
            r'换手率\s*(\d+\.?\d*)\s*[-~到至%]\s*(\d+\.?\d*)\s*%',
            r'换手\s*(\d+\.?\d*)\s*[-~到至%]\s*(\d+\.?\d*)\s*%',
            r'(\d+\.?\d*)%\s*[-~到至]\s*(\d+\.?\d*)\s*%.*换手',
        ]
        for p in patterns:
            m = re.search(p, text)
            if m:
                conditions["turnover_range"] = [float(m.group(1)), float(m.group(2))]
                return

    def _parse_volume_ratio(self, text, conditions):
        """解析量比"""
        m = re.search(r'量比\s*(?:大于|>|≥|>=)\s*(\d+\.?\d*)', text)
        if m:
            conditions["volume_ratio_min"] = float(m.group(1))

    def _parse_limit_up(self, text, conditions):
        """解析涨停次数"""
        m = re.search(r'(?:年|一年内|一年).*?涨停.*?(?:≥|>=|大于|不低于|不少于)\s*(\d+)\s*次', text)
        if m:
            conditions["limit_up_count_min"] = int(m.group(1))
            return

        m = re.search(r'涨停.*?(?:≥|>=|大于|不低于|不少于)\s*(\d+)\s*次', text)
        if m:
            conditions["limit_up_count_min"] = int(m.group(1))

    def _parse_amplitude(self, text, conditions):
        """解析振幅"""
        m = re.search(r'振幅\s*(?:小于|<=|≤|不超过)\s*(\d+\.?\d*)\s*%', text)
        if m:
            conditions["amplitude_max"] = float(m.group(1))

    def _parse_industries(self, text, conditions):
        """解析行业排除"""
        m = re.search(r'(?:排除|剔除|去掉|不要)\s*([^，,。；;\n]+?)(?:行业|板块)?', text)
        if m:
            industry_text = m.group(1)
            industries = re.split(r'[、/，,；;\s]+', industry_text)
            industries = [i.strip() for i in industries if i.strip() and len(i.strip()) <= 4]
            if industries:
                conditions["exclude_industries"] = industries

    def _parse_high_ratio(self, text, conditions):
        """解析高点比例范围"""
        m = re.search(r'(\d+)\s*个月.*?高点\s*(\d+\.?\d*)%\s*[-~到至]\s*(\d+\.?\d*)%', text)
        if m:
            months = int(m.group(1))
            conditions["high_period_days"] = months * 20
            conditions["high_ratio_range"] = [float(m.group(2)) / 100, float(m.group(3)) / 100]
            return

        m = re.search(r'高点\s*(\d+\.?\d*)%\s*[-~到至]\s*(\d+\.?\d*)%', text)
        if m:
            conditions["high_ratio_range"] = [float(m.group(1)) / 100, float(m.group(2)) / 100]

    def _parse_pct_chg(self, text, conditions):
        """解析涨跌幅范围"""
        patterns = [
            r'涨跌幅\s*(-?\d+\.?\d*)%\s*[-~到至]\s*(-?\d+\.?\d*)%',
            r'涨幅\s*(-?\d+\.?\d*)%\s*[-~到至]\s*(-?\d+\.?\d*)%',
            r'涨幅\s*(?:大于|>|≥|>=)\s*(-?\d+\.?\d*)%',
            r'涨幅\s*(?:小于|<|≤|<=)\s*(-?\d+\.?\d*)%',
            r'涨幅\s*(-?\d+\.?\d*)%',
            r'涨\s*(-?\d+\.?\d*)%\s*(?:以上|以上)',
            r'涨\s*(-?\d+\.?\d*)个?点',
            r'收盘价涨幅\s*(-?\d+\.?\d*)%',
        ]
        for p in patterns:
            m = re.search(p, text)
            if m:
                if m.lastindex and m.lastindex >= 2:
                    conditions["pct_chg_range"] = [float(m.group(1)), float(m.group(2))]
                else:
                    val = float(m.group(1))
                    conditions["pct_chg_range"] = [val, 99]
                return

        m = re.search(r'跌幅\s*(?:大于|>|≥|>=)\s*(\d+\.?\d*)%', text)
        if m:
            conditions["pct_chg_range"] = [-99, -float(m.group(1))]
            return

        m = re.search(r'跌幅\s*(\d+\.?\d*)%', text)
        if m:
            conditions["pct_chg_range"] = [-99, -float(m.group(1))]

    def generate_description(self, conditions):
        """根据条件生成可读的策略描述"""
        from strategy.condition_mapper import get_condition_mapper
        mapper = get_condition_mapper()
        return mapper._generate_description(conditions)


def get_nl_parser(use_llm=True):
    """
    获取自然语言解析器

    Args:
        use_llm: 是否使用大模型模式（默认True）
    """
    return NLStrategyParser(use_llm=use_llm)
