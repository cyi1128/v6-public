# -*- coding: utf-8 -*-
"""
条件映射器

将AI输出的JSON条件映射到程序内部筛选引擎可识别的格式。
负责：条件验证、默认值合并、K线需求判断、可读描述生成。
"""
from strategy.strategy_schema import (
    DEFAULT_CONDITIONS,
    FIELD_LABELS,
    merge_with_default,
    is_valid_conditions,
)


class ConditionMapper:
    """条件映射器"""

    # 需要K线数据才能计算的条件字段
    KLINE_REQUIRED_FIELDS = [
        "high_ratio_range",
        "volume_ratio_min",
        "amplitude_max",
        "no_limit_up_yesterday",
        "ma_bullish",
        "ma5_cross_ma9",
        "macd_golden_cross",
        "macd_dead_cross",
        "kdj_j_range",
        "volume_breakout",
        "consecutive_up_days",
    ]

    # 快速条件（不需要K线，从行情接口直接获取）
    FAST_FIELDS = [
        "main_board_only",
        "exclude_st",
        "price_range",
        "market_cap_range",
        "turnover_range",
        "pct_chg_range",
        "exclude_industries",
        "limit_up_count_min",  # 使用缓存
    ]

    def __init__(self):
        pass

    def map(self, ai_conditions):
        """
        将AI输出的条件映射到内部格式

        Args:
            ai_conditions: AI输出的原始条件字典

        Returns:
            dict: 映射后的条件，包含：
                - conditions: 完整条件（含默认值）
                - need_kline: 是否需要K线数据
                - fast_conditions: 快速条件子集
                - description: 可读描述
        """
        if not is_valid_conditions(ai_conditions):
            return None

        conditions = merge_with_default(ai_conditions)
        need_kline = self._check_need_kline(conditions)
        fast_conditions = self._extract_fast_conditions(conditions)
        description = self._generate_description(conditions)

        return {
            "conditions": conditions,
            "need_kline": need_kline,
            "fast_conditions": fast_conditions,
            "description": description,
        }

    def _check_need_kline(self, conditions):
        """判断是否需要K线数据"""
        for field in self.KLINE_REQUIRED_FIELDS:
            value = conditions.get(field)
            if field in ("ma_bullish", "ma5_cross_ma9", "macd_golden_cross",
                         "macd_dead_cross", "no_limit_up_yesterday"):
                if value:
                    return True
            elif field in ("high_ratio_range",):
                if value and (value[0] > 0 or value[1] < 99):
                    return True
            elif field in ("volume_ratio_min", "amplitude_max", "volume_breakout",
                           "consecutive_up_days"):
                if value and value > 0:
                    return True
            elif field == "kdj_j_range":
                if value and (value[0] > -100 or value[1] < 200):
                    return True
        return False

    def _extract_fast_conditions(self, conditions):
        """提取不需要K线的快速条件"""
        fast = {}
        for field in self.FAST_FIELDS:
            if field in conditions:
                fast[field] = conditions[field]
        return fast

    def _generate_description(self, conditions):
        """生成可读的策略描述"""
        parts = []

        if conditions.get("main_board_only"):
            parts.append("主板")
        if conditions.get("exclude_st"):
            parts.append("非ST")

        pr = conditions.get("price_range", [0, 999])
        if pr[0] > 0 or pr[1] < 999:
            parts.append(f"价格{pr[0]}-{pr[1]}元")

        mc = conditions.get("market_cap_range", [0, 9999])
        if mc[0] > 0 or mc[1] < 9999:
            parts.append(f"市值{mc[0]}-{mc[1]}亿")

        tr = conditions.get("turnover_range", [0, 100])
        if tr[0] > 0 or tr[1] < 100:
            parts.append(f"换手{tr[0]}-{tr[1]}%")

        pct = conditions.get("pct_chg_range", [-99, 99])
        if pct[0] > -99 or pct[1] < 99:
            if pct[0] > -99 and pct[1] < 99:
                parts.append(f"涨幅{pct[0]}%-{pct[1]}%")
            elif pct[0] > -99:
                parts.append(f"涨幅≥{pct[0]}%")
            else:
                parts.append(f"涨幅≤{pct[1]}%")

        luc = conditions.get("limit_up_count_min", 0)
        if luc > 0:
            parts.append(f"年涨停≥{luc}次")

        vr = conditions.get("volume_ratio_min", 0)
        if vr > 0:
            parts.append(f"量比≥{vr}")

        amp = conditions.get("amplitude_max", 100)
        if amp < 100:
            parts.append(f"振幅<{amp}%")

        if conditions.get("ma_bullish"):
            parts.append("均线多头")
        if conditions.get("ma5_cross_ma9"):
            parts.append("穿九")
        if conditions.get("macd_golden_cross"):
            parts.append("MACD金叉")
        if conditions.get("macd_dead_cross"):
            parts.append("MACD死叉")

        kdj = conditions.get("kdj_j_range", [-100, 200])
        if kdj[0] > -100 or kdj[1] < 200:
            parts.append(f"KDJ-J {kdj[0]}-{kdj[1]}")

        vb = conditions.get("volume_breakout", 0)
        if vb > 0:
            parts.append(f"放量{vb}倍")

        cud = conditions.get("consecutive_up_days", 0)
        if cud > 0:
            parts.append(f"连涨{cud}天")

        hr = conditions.get("high_ratio_range", [0, 99])
        if hr[0] > 0 or hr[1] < 99:
            months = conditions.get("high_period_days", 160) // 20
            parts.append(f"{months}月高点{hr[0]*100:.0f}%-{hr[1]*100:.0f}%")

        if conditions.get("no_limit_up_yesterday"):
            parts.append("前日未涨停")

        inds = conditions.get("exclude_industries", [])
        if inds:
            parts.append(f"排除{'/'.join(inds)}")

        return " | ".join(parts) if parts else "无特定条件"

    def get_active_fields(self, conditions):
        """获取用户实际设置了的条件列表（用于确认窗口显示）"""
        active = []
        defaults = DEFAULT_CONDITIONS

        for field, value in conditions.items():
            default = defaults.get(field)
            if field in ("main_board_only", "exclude_st", "no_limit_up_yesterday",
                         "ma_bullish", "ma5_cross_ma9", "macd_golden_cross",
                         "macd_dead_cross"):
                if value and not default:
                    active.append(field)
            elif field in ("price_range", "market_cap_range", "turnover_range",
                           "pct_chg_range", "high_ratio_range", "kdj_j_range"):
                if value != default:
                    active.append(field)
            elif field in ("limit_up_count_min", "volume_ratio_min", "amplitude_max",
                           "high_period_days", "volume_breakout", "consecutive_up_days"):
                if value != default:
                    active.append(field)
            elif field == "exclude_industries":
                if value:
                    active.append(field)

        return active


# 单例
_mapper = None


def get_condition_mapper():
    """获取条件映射器单例"""
    global _mapper
    if _mapper is None:
        _mapper = ConditionMapper()
    return _mapper
