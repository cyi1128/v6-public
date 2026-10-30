# -*- coding: utf-8 -*-
"""
策略条件Schema定义

定义AI输出的标准JSON格式，以及与程序内部条件格式的映射。
AI必须严格按照此Schema输出，确保安全可控。
"""

# 标准策略条件Schema（AI输出格式）
STRATEGY_SCHEMA = {
    "type": "object",
    "properties": {
        "main_board_only": {
            "type": "boolean",
            "description": "是否只筛选主板股票（600/601/603/605/000/001/002/003开头）"
        },
        "exclude_st": {
            "type": "boolean",
            "description": "是否剔除ST股票"
        },
        "price_range": {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 2,
            "maxItems": 2,
            "description": "股价范围[最低价, 最高价]，单位元"
        },
        "market_cap_range": {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 2,
            "maxItems": 2,
            "description": "总市值范围[最小, 最大]，单位亿"
        },
        "turnover_range": {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 2,
            "maxItems": 2,
            "description": "换手率范围[最小%, 最大%]"
        },
        "volume_ratio_min": {
            "type": "number",
            "description": "量比最小值"
        },
        "limit_up_count_min": {
            "type": "integer",
            "description": "近一年涨停次数最小值"
        },
        "amplitude_max": {
            "type": "number",
            "description": "当日振幅最大值，单位%"
        },
        "pct_chg_range": {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 2,
            "maxItems": 2,
            "description": "当日涨跌幅范围[最小%, 最大%]，如[3, 8]表示涨幅3%-8%"
        },
        "exclude_industries": {
            "type": "array",
            "items": {"type": "string"},
            "description": "排除的行业列表，如['地产', '农业', '酒', '保险']"
        },
        "high_ratio_range": {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 2,
            "maxItems": 2,
            "description": "近N个月最高价比例范围[最小比例, 最大比例]，如[0.7, 1.05]表示70%-105%"
        },
        "high_period_days": {
            "type": "integer",
            "description": "高点统计周期，单位交易日，如160表示约8个月"
        },
        "no_limit_up_yesterday": {
            "type": "boolean",
            "description": "前一天是否未涨停"
        },
        "ma_bullish": {
            "type": "boolean",
            "description": "是否均线多头排列（MA5>MA9>MA20）"
        },
        "ma5_cross_ma9": {
            "type": "boolean",
            "description": "是否MA5上穿MA9（穿九）"
        },
        "macd_golden_cross": {
            "type": "boolean",
            "description": "是否MACD金叉（参数8,21,5）"
        },
        "macd_dead_cross": {
            "type": "boolean",
            "description": "是否MACD死叉"
        },
        "kdj_j_range": {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 2,
            "maxItems": 2,
            "description": "KDJ的J值范围[最小, 最大]，参数13,3,3"
        },
        "volume_breakout": {
            "type": "number",
            "description": "成交量突破倍数，如1.5表示成交量大于5日均量1.5倍"
        },
        "consecutive_up_days": {
            "type": "integer",
            "description": "连续上涨天数，每日涨幅≥1%"
        }
    },
    "additionalProperties": False
}

# 默认条件（AI未提及的字段使用这些默认值，表示不限制）
DEFAULT_CONDITIONS = {
    "main_board_only": False,
    "exclude_st": False,
    "price_range": [0, 999],
    "market_cap_range": [0, 9999],
    "limit_up_count_min": 0,
    "turnover_range": [0, 100],
    "volume_ratio_min": 0,
    "amplitude_max": 100,
    "pct_chg_range": [-99, 99],
    "exclude_industries": [],
    "high_ratio_range": [0, 99],
    "high_period_days": 160,
    "no_limit_up_yesterday": False,
    "ma_bullish": False,
    "ma5_cross_ma9": False,
    "macd_golden_cross": False,
    "macd_dead_cross": False,
    "kdj_j_range": [-100, 200],
    "volume_breakout": 0,
    "consecutive_up_days": 0,
}

# 字段中文说明（用于AI确认窗口显示）
FIELD_LABELS = {
    "main_board_only": "主板过滤",
    "exclude_st": "ST过滤",
    "price_range": "股价范围",
    "market_cap_range": "市值范围",
    "turnover_range": "换手率范围",
    "volume_ratio_min": "量比最小",
    "limit_up_count_min": "年涨停次数≥",
    "amplitude_max": "振幅≤",
    "pct_chg_range": "涨跌幅范围",
    "exclude_industries": "排除行业",
    "high_ratio_range": "高点比例范围",
    "high_period_days": "高点周期(天)",
    "no_limit_up_yesterday": "前日未涨停",
    "ma_bullish": "均线多头排列",
    "ma5_cross_ma9": "MA5上穿MA9",
    "macd_golden_cross": "MACD金叉",
    "macd_dead_cross": "MACD死叉",
    "kdj_j_range": "KDJ-J值范围",
    "volume_breakout": "成交量突破倍数",
    "consecutive_up_days": "连续上涨天数",
}


def get_schema_description():
    """获取Schema的文本描述，用于构建AI提示词"""
    lines = ["你必须输出以下JSON格式的策略条件，只能输出JSON，不要输出其他内容：", ""]
    for field, props in STRATEGY_SCHEMA["properties"].items():
        desc = props.get("description", "")
        dtype = props.get("type", "")
        lines.append(f"- {field} ({dtype}): {desc}")
    lines.append("")
    lines.append("未提及的条件不要输出，使用默认值表示不限制。")
    lines.append("示例：用户说'价格5到60元，市值30到230亿，一年涨停超过3次'")
    lines.append('输出：{"price_range":[5,60],"market_cap_range":[30,230],"limit_up_count_min":3}')
    return "\n".join(lines)


def is_valid_conditions(conditions):
    """验证AI输出的条件是否符合Schema"""
    if not isinstance(conditions, dict):
        return False
    for key in conditions:
        if key not in STRATEGY_SCHEMA["properties"]:
            return False
    return True


def merge_with_default(conditions):
    """将AI输出的条件与默认条件合并"""
    result = DEFAULT_CONDITIONS.copy()
    if isinstance(conditions, dict):
        for key, value in conditions.items():
            if key in result:
                result[key] = value
    return result
