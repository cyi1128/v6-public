"""
strategy/ai520_strategy.py - AI520核心策略模块（唯一可调用的520选股策略）

V2.8：将AI520 520模式正式固化为独立、可测试、可复用的Python策略模块。
以后全市场扫描/自选股评分/个股分析/历史回测全部调用此模块。

AI520核心思想：寻找当前股票与520历史模式的相似度（0~100分），
不是"所有条件全部满足才选股"，而是条件越接近分数越高。

8维度评分模型（总分100分）：
①趋势结构 20分  ②历史强势记忆 15分  ③温和上涨 15分  ④缩量回踩 15分
⑤再次转强 15分  ⑥KDJ 10分  ⑦位置 5分  ⑧价量关系 5分

策略版本：AI520-1.0
"""
import os
import sys
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

AI520_STRATEGY_VERSION = "1.0"
AI520_STRATEGY_TAG = f"AI520-{AI520_STRATEGY_VERSION}"

# 8维度满分配置
DIMENSION_WEIGHTS = {
    'trend': 20,           # 趋势结构
    'strength_memory': 15,  # 历史强势记忆
    'moderate_rise': 15,    # 温和上涨
    'pullback': 15,         # 缩量回踩
    'recovery': 15,         # 再次转强
    'kdj': 10,              # KDJ
    'position': 5,           # 位置
    'volume_price': 5,       # 价量关系
}


class AI520Strategy:
    """AI520核心策略类（唯一520选股策略）"""

    def __init__(self):
        self.version = AI520_STRATEGY_VERSION
        self.tag = AI520_STRATEGY_TAG

    # ==================== 核心入口 ====================

    def score_stock(self, kline: List[Dict], stock_info: Optional[Dict] = None) -> Dict:
        """
        核心评分入口：对一只股票计算AI520相似度评分

        Args:
            kline: K线数据列表，每根包含 date/open/high/low/close/volume/amount
            stock_info: 股票基础信息（code/name/price/industry等），可选

        Returns:
            {
                'score': 0~100, 'grade': 'S/A/B/C/D', 'similarity': str,
                'trend_score': int, 'strength_memory_score': int, 'moderate_rise_score': int,
                'pullback_score': int, 'recovery_score': int, 'kdj_score': int,
                'position_score': int, 'volume_price_score': int,
                'pullback_type': 'MA5'/'MA20'/'NONE',
                'pullback_ma5_score': int, 'pullback_ma20_score': int,
                'matched_conditions': List[str], 'missing_conditions': List[str],
                'risk_items': List[str], 'reasons': List[str],
                'ma5': float, 'ma10': float, 'ma20': float,
                'dist_ma5': float, 'dist_ma20': float, 'vol_ratio': float,
                'kdj_k': float, 'kdj_d': float, 'kdj_j': float,
                'limit_up_20d': int, 'limit_up_1y': int,
                'status': 'OK'/'INSUFFICIENT_DATA'/'DATA_ERROR',
                'data_quality': 'GOOD'/'WARNING'/'INSUFFICIENT',
                'strategy_version': str,
            }
        """
        result = self._init_result()
        try:
            # 数据质量检查
            quality = self._check_data_quality(kline)
            result['data_quality'] = quality
            if quality == 'INSUFFICIENT':
                result['status'] = 'INSUFFICIENT_DATA'
                result['risk_items'].append(f'K线数据不足（需要至少30根，实际{len(kline) if kline else 0}根）')
                return result

            # 计算技术特征
            features = self.calculate_features(kline)
            if features.get('status') != 'OK':
                result['status'] = features.get('status', 'DATA_ERROR')
                result['risk_items'].extend(features.get('errors', []))
                return result

            # 8维度评分
            scores = self.calculate_score(kline, features)
            result.update(scores)

            # 总分
            total = (result['trend_score'] + result['strength_memory_score'] +
                     result['moderate_rise_score'] + result['pullback_score'] +
                     result['recovery_score'] + result['kdj_score'] +
                     result['position_score'] + result['volume_price_score'])
            result['score'] = min(round(total, 2), 100)

            # 等级
            result['grade'], result['similarity'] = self._get_grade(result['score'])

            # 回踩类型
            result['pullback_type'] = self._get_pullback_type(result)

            # 评分解释
            result['reasons'] = self.explain_score(result)

            # 技术指标
            result['ma5'] = features.get('ma5', 0)
            result['ma10'] = features.get('ma10', 0)
            result['ma20'] = features.get('ma20', 0)
            result['dist_ma5'] = features.get('dist_ma5', 0)
            result['dist_ma20'] = features.get('dist_ma20', 0)
            result['vol_ratio'] = features.get('vol_ratio', 1)
            result['kdj_k'] = features.get('kdj_k', 50)
            result['kdj_d'] = features.get('kdj_d', 50)
            result['kdj_j'] = features.get('kdj_j', 50)
            result['limit_up_20d'] = features.get('limit_up_20d', 0)
            result['limit_up_1y'] = features.get('limit_up_1y', 0)

            result['status'] = 'OK'
            result['strategy_version'] = self.version

        except Exception as e:
            result['status'] = 'DATA_ERROR'
            result['data_quality'] = 'WARNING'
            result['risk_items'].append(f'评分异常: {str(e)}')
            print(f"[AI520Strategy] 评分异常: {e}", flush=True)

        return result

    def scan_stock(self, kline: List[Dict], stock_info: Optional[Dict] = None) -> Dict:
        """扫描单只股票（score_stock的别名，保持接口兼容）"""
        return self.score_stock(kline, stock_info)

    # ==================== 特征计算 ====================

    def calculate_features(self, kline: List[Dict]) -> Dict:
        """计算技术特征：MA/KDJ/涨停/量比/价格位置"""
        features = {'status': 'OK', 'errors': []}
        try:
            closes = [float(k['close']) for k in kline if k.get('close') is not None]
            highs = [float(k['high']) for k in kline if k.get('high') is not None]
            lows = [float(k['low']) for k in kline if k.get('low') is not None]
            volumes = [float(k['volume']) for k in kline if k.get('volume') is not None]

            if len(closes) < 30:
                features['status'] = 'INSUFFICIENT_DATA'
                features['errors'].append(f'K线不足30根（实际{len(closes)}根）')
                return features

            # MA计算
            ma5 = self.calc_ma(closes, 5)
            ma10 = self.calc_ma(closes, 10)
            ma20 = self.calc_ma(closes, 20)
            ma60 = self.calc_ma(closes, 60) if len(closes) >= 60 else None

            features['ma5'] = round(ma5[-1], 2) if ma5 and ma5[-1] else 0
            features['ma10'] = round(ma10[-1], 2) if ma10 and ma10[-1] else 0
            features['ma20'] = round(ma20[-1], 2) if ma20 and ma20[-1] else 0
            features['ma5_prev'] = round(ma5[-2], 2) if len(ma5) >= 2 and ma5[-2] else features['ma5']
            features['ma20_prev'] = round(ma20[-2], 2) if len(ma20) >= 2 and ma20[-2] else features['ma20']

            current_close = closes[-1]
            features['current_close'] = current_close
            features['current_vol'] = volumes[-1] if volumes else 0

            # 距离MA
            if features['ma5'] > 0:
                features['dist_ma5'] = round(abs(current_close - features['ma5']) / features['ma5'] * 100, 2)
            if features['ma20'] > 0:
                features['dist_ma20'] = round(abs(current_close - features['ma20']) / features['ma20'] * 100, 2)

            # 量比
            if len(volumes) >= 6:
                avg_vol_5 = sum(volumes[-6:-1]) / 5
                features['vol_ratio'] = round(features['current_vol'] / avg_vol_5, 2) if avg_vol_5 > 0 else 1
            else:
                features['vol_ratio'] = 1

            # KDJ 13,3,3
            kdj = self.calc_kdj(kline, n=13, m1=3, m2=3)
            features['kdj_k'] = round(kdj.get('current_k', 50), 1)
            features['kdj_d'] = round(kdj.get('current_d', 50), 1)
            features['kdj_j'] = round(kdj.get('current_j', 50), 1)

            # 涨停计数
            features['limit_up_20d'], _ = self.count_limit_up(kline, days=20)
            features['limit_up_1y'], _ = self.count_limit_up(kline, days=250)

            # KDJ低位记忆
            kdj_mem = self.check_kdj_memory(kline)
            features['kdj_memory'] = kdj_mem.get('has_memory', False)
            features['kdj_lowest_j'] = kdj_mem.get('lowest_j', 100)

            # 近20日/60日高点
            if len(highs) >= 20:
                features['high_20d'] = max(highs[-20:])
            if len(highs) >= 60:
                features['high_60d'] = max(highs[-60:])

            # 保存原始数组供评分使用
            features['closes'] = closes
            features['highs'] = highs
            features['lows'] = lows
            features['volumes'] = volumes

        except Exception as e:
            features['status'] = 'DATA_ERROR'
            features['errors'].append(f'特征计算异常: {str(e)}')

        return features

    # ==================== 8维度评分 ====================

    def calculate_score(self, kline: List[Dict], features: Dict) -> Dict:
        """8维度评分计算"""
        scores = {
            'trend_score': 0, 'strength_memory_score': 0, 'moderate_rise_score': 0,
            'pullback_score': 0, 'recovery_score': 0, 'kdj_score': 0,
            'position_score': 0, 'volume_price_score': 0,
            'pullback_ma5_score': 0, 'pullback_ma20_score': 0,
            'matched_conditions': [], 'missing_conditions': [], 'risk_items': [],
        }

        closes = features.get('closes', [])
        volumes = features.get('volumes', [])
        current_close = features.get('current_close', 0)
        current_vol = features.get('current_vol', 0)
        ma5_val = features.get('ma5', 0)
        ma10_val = features.get('ma10', 0)
        ma20_val = features.get('ma20', 0)
        ma5_prev = features.get('ma5_prev', 0)
        ma20_prev = features.get('ma20_prev', 0)

        # ========== ①趋势结构 20分 ==========
        trend = 0
        if ma5_val > 0 and ma10_val > 0:
            if ma5_val > ma10_val:
                trend += 6
                scores['matched_conditions'].append('MA5>MA10')
            else:
                scores['missing_conditions'].append('MA5未>MA10')
            if ma10_val > ma20_val:
                trend += 6
                scores['matched_conditions'].append('MA10>MA20')
            else:
                scores['missing_conditions'].append('MA10未>MA20')
        if ma5_val > 0 and ma5_prev > 0 and ma5_val >= ma5_prev:
            trend += 4
            scores['matched_conditions'].append('MA5向上')
        else:
            scores['missing_conditions'].append('MA5未向上')
        if ma20_val > 0 and ma20_prev > 0:
            ma20_slope = (ma20_val - ma20_prev) / ma20_prev
            if ma20_slope >= -0.005:
                trend += 4
                scores['matched_conditions'].append('MA20未明显下降')
            elif ma20_slope < -0.02:
                scores['risk_items'].append('MA20严重向下')
            else:
                scores['missing_conditions'].append('MA20轻微下降')
        scores['trend_score'] = min(trend, 20)

        # ========== ②历史强势记忆 15分 ==========
        memory = 0
        lu_20d = features.get('limit_up_20d', 0)
        lu_1y = features.get('limit_up_1y', 0)
        if lu_20d > 0:
            memory += min(lu_20d * 4, 8)
            scores['matched_conditions'].append(f'近20日涨停{lu_20d}次')
        else:
            scores['missing_conditions'].append('近20日无涨停')
        if lu_1y >= 3:
            memory += 4
            scores['matched_conditions'].append(f'近一年涨停{lu_1y}次')
        elif lu_1y >= 1:
            memory += 2
            scores['matched_conditions'].append(f'近一年涨停{lu_1y}次')
        else:
            scores['missing_conditions'].append('近一年涨停不足')
        if len(closes) >= 11 and closes[-11] > 0:
            gain_10d = (closes[-1] / closes[-11] - 1) * 100
            if 5 <= gain_10d <= 30:
                memory += 3
                scores['matched_conditions'].append(f'近10日涨幅{gain_10d:.1f}%')
            elif gain_10d > 30:
                scores['risk_items'].append(f'近10日涨幅过大{gain_10d:.1f}%')
        scores['strength_memory_score'] = min(memory, 15)

        # ========== ③温和上涨 15分 ==========
        gentle = 0
        if len(volumes) >= 20:
            recent_vols = volumes[-20:]
            max_vol_idx = recent_vols.index(max(recent_vols))
            startup_idx = len(volumes) - 20 + max_vol_idx
            if startup_idx < len(closes) - 1:
                startup_close = closes[startup_idx]
                if startup_close > 0:
                    gain_from_startup = (current_close / startup_close - 1) * 100
                    if 3 <= gain_from_startup <= 25:
                        gentle += 8
                        scores['matched_conditions'].append(f'启动后温和上涨{gain_from_startup:.1f}%')
                    elif gain_from_startup > 25:
                        scores['risk_items'].append(f'启动后涨幅过大{gain_from_startup:.1f}%')
                    elif gain_from_startup < 3:
                        scores['missing_conditions'].append('启动后涨幅不足')
                crazy_count = 0
                for i in range(max(0, len(closes)-6), len(closes)-1):
                    if closes[i] > 0 and (closes[i+1]/closes[i]-1)*100 > 7:
                        crazy_count += 1
                if crazy_count == 0:
                    gentle += 7
                    scores['matched_conditions'].append('无连续疯狂拉升')
                else:
                    scores['risk_items'].append(f'近5日{crazy_count}次大涨>7%')
        scores['moderate_rise_score'] = min(gentle, 15)

        # ========== ④缩量回踩 15分（MA5 OR MA20）==========
        pullback = 0
        pullback_ma5 = 0
        pullback_ma20 = 0
        vol_ratio = features.get('vol_ratio', 1)
        # 缩量
        if vol_ratio < 0.8:
            pullback += 5
            scores['matched_conditions'].append(f'缩量回踩(量比{vol_ratio:.2f})')
        elif vol_ratio < 1.0:
            pullback += 3
            scores['matched_conditions'].append(f'轻微缩量(量比{vol_ratio:.2f})')
        elif vol_ratio > 1.8 and len(closes) >= 2 and current_close < closes[-2]:
            scores['risk_items'].append('放量下跌')
        else:
            scores['missing_conditions'].append('未明显缩量')
        # 回踩MA5
        if ma5_val > 0:
            dist_ma5 = abs(current_close - ma5_val) / ma5_val
            if dist_ma5 <= 0.02:
                pullback_ma5 += 5
                pullback += 5
                scores['matched_conditions'].append(f'回踩MA5(距离{dist_ma5*100:.1f}%)')
            elif dist_ma5 <= 0.05:
                pullback_ma5 += 2
                pullback += 2
                scores['matched_conditions'].append(f'接近MA5(距离{dist_ma5*100:.1f}%)')
        # 回踩MA20
        if ma20_val > 0:
            dist_ma20 = abs(current_close - ma20_val) / ma20_val
            if dist_ma20 <= 0.02:
                pullback_ma20 += 5
                pullback += 5
                scores['matched_conditions'].append(f'回踩MA20(距离{dist_ma20*100:.1f}%)')
            elif dist_ma20 <= 0.05:
                pullback_ma20 += 2
                pullback += 2
                scores['matched_conditions'].append(f'接近MA20(距离{dist_ma20*100:.1f}%)')
        scores['pullback_score'] = min(pullback, 15)
        scores['pullback_ma5_score'] = pullback_ma5
        scores['pullback_ma20_score'] = pullback_ma20

        # ========== ⑤再次转强 15分 ==========
        recovery = 0
        if ma5_val > 0 and current_close > ma5_val:
            recovery += 5
            scores['matched_conditions'].append('收盘价>MA5')
        else:
            scores['missing_conditions'].append('未站上MA5')
        if ma10_val > 0 and current_close > ma10_val:
            recovery += 3
            scores['matched_conditions'].append('收盘价>MA10')
        if len(kline) >= 1 and kline[-1].get('close', 0) > kline[-1].get('open', 0):
            recovery += 3
            scores['matched_conditions'].append('今日阳线')
        else:
            scores['missing_conditions'].append('今日非阳线')
        if len(volumes) >= 2 and current_vol > volumes[-2]:
            recovery += 2
            scores['matched_conditions'].append('成交量恢复')
        highs = features.get('highs', [])
        if len(highs) >= 2 and current_close > highs[-2]:
            recovery += 2
            scores['matched_conditions'].append('突破前高')
        scores['recovery_score'] = min(recovery, 15)

        # ========== ⑥KDJ 10分 ==========
        kdj_s = 0
        k_val = features.get('kdj_k', 50)
        d_val = features.get('kdj_d', 50)
        j_val = features.get('kdj_j', 50)
        if 20 <= j_val <= 80:
            kdj_s += 3
            scores['matched_conditions'].append(f'KDJ J={j_val:.1f}合理区间')
        elif j_val < 20:
            kdj_s += 2
            scores['matched_conditions'].append(f'KDJ J={j_val:.1f}低位')
        elif j_val > 90:
            scores['risk_items'].append(f'KDJ J={j_val:.1f}超买')
        if k_val > d_val:
            kdj_s += 3
            scores['matched_conditions'].append(f'K>D金叉(K={k_val:.1f},D={d_val:.1f})')
        if features.get('kdj_memory', False):
            kdj_s += 4
            scores['matched_conditions'].append(f'KDJ低位记忆({features.get("kdj_lowest_j",0):.1f})')
        else:
            scores['missing_conditions'].append('无KDJ低位记忆')
        scores['kdj_score'] = min(kdj_s, 10)

        # ========== ⑦位置 5分 ==========
        position = 0
        high_20d = features.get('high_20d', 0)
        if high_20d > 0:
            dist_high_20 = (high_20d - current_close) / high_20d
            if dist_high_20 <= 0.05:
                position += 3
                scores['matched_conditions'].append(f'接近20日高点(距离{dist_high_20*100:.1f}%)')
            elif dist_high_20 <= 0.15:
                position += 1
        high_60d = features.get('high_60d', 0)
        if high_60d > 0 and current_close > high_60d * 0.7:
            position += 2
            scores['matched_conditions'].append('价格在60日高点70%以上')
        scores['position_score'] = min(position, 5)

        # ========== ⑧价量关系 5分 ==========
        vp = 0
        if len(volumes) >= 6 and len(closes) >= 2:
            avg_vol_5 = sum(volumes[-6:-1]) / 5
            vr = current_vol / avg_vol_5 if avg_vol_5 > 0 else 1
            today_change = (closes[-1] / closes[-2] - 1) * 100 if closes[-2] > 0 else 0
            if today_change > 0 and vr > 1.0:
                vp += 2
                scores['matched_conditions'].append('上涨放量')
            if today_change <= 0 and vr < 0.8:
                vp += 2
                scores['matched_conditions'].append('下跌缩量')
            if 0.5 <= vr <= 2.5:
                vp += 1
                scores['matched_conditions'].append(f'量比合理({vr:.2f})')
        scores['volume_price_score'] = min(vp, 5)

        return scores

    # ==================== 评分解释 ====================

    def explain_score(self, result: Dict) -> List[str]:
        """生成评分解释列表"""
        reasons = []
        score = result.get('score', 0)
        grade = result.get('grade', 'D')
        reasons.append(f"AI520相似度: {score}分 ({grade}级)")
        reasons.append(f"趋势结构: {result.get('trend_score',0)}/20")
        reasons.append(f"历史强势记忆: {result.get('strength_memory_score',0)}/15")
        reasons.append(f"温和上涨: {result.get('moderate_rise_score',0)}/15")
        reasons.append(f"缩量回踩: {result.get('pullback_score',0)}/15 (回踩类型: {result.get('pullback_type','NONE')})")
        reasons.append(f"再次转强: {result.get('recovery_score',0)}/15")
        reasons.append(f"KDJ: {result.get('kdj_score',0)}/10")
        reasons.append(f"位置: {result.get('position_score',0)}/5")
        reasons.append(f"价量关系: {result.get('volume_price_score',0)}/5")
        matched = result.get('matched_conditions', [])
        if matched:
            reasons.append(f"主要符合项: {', '.join(matched[:8])}")
        missing = result.get('missing_conditions', [])
        if missing:
            reasons.append(f"缺失项: {', '.join(missing[:5])}")
        risks = result.get('risk_items', [])
        if risks:
            reasons.append(f"风险项: {', '.join(risks[:5])}")
        return reasons

    # ==================== 技术指标计算 ====================

    def calc_ma(self, closes: List[float], period: int) -> List[Optional[float]]:
        """计算移动平均线"""
        result = []
        for i in range(len(closes)):
            if i < period - 1:
                result.append(None)
            else:
                result.append(sum(closes[i-period+1:i+1]) / period)
        return result

    def calc_kdj(self, kline: List[Dict], n: int = 13, m1: int = 3, m2: int = 3) -> Dict:
        """计算KDJ（固定参数13,3,3）"""
        try:
            closes = [float(k['close']) for k in kline]
            highs = [float(k['high']) for k in kline]
            lows = [float(k['low']) for k in kline]
            if len(closes) < n:
                return {'current_k': 50, 'current_d': 50, 'current_j': 50}

            k_values = []
            d_values = []
            prev_k = 50
            prev_d = 50
            for i in range(len(closes)):
                if i < n - 1:
                    k_values.append(50)
                    d_values.append(50)
                    continue
                high_n = max(highs[i-n+1:i+1])
                low_n = min(lows[i-n+1:i+1])
                if high_n == low_n:
                    rsv = 50
                else:
                    rsv = (closes[i] - low_n) / (high_n - low_n) * 100
                k = (m1 - 1) / m1 * prev_k + 1 / m1 * rsv
                d = (m2 - 1) / m2 * prev_d + 1 / m2 * k
                k_values.append(k)
                d_values.append(d)
                prev_k = k
                prev_d = d

            current_k = k_values[-1]
            current_d = d_values[-1]
            current_j = 3 * current_k - 2 * current_d
            return {
                'current_k': round(current_k, 2),
                'current_d': round(current_d, 2),
                'current_j': round(current_j, 2),
                'k_values': k_values,
                'd_values': d_values,
            }
        except Exception as e:
            print(f"[AI520Strategy] KDJ计算异常: {e}", flush=True)
            return {'current_k': 50, 'current_d': 50, 'current_j': 50}

    def count_limit_up(self, kline: List[Dict], days: int = 250) -> Tuple[int, List[str]]:
        """统计近N日涨停次数"""
        count = 0
        dates = []
        try:
            recent = kline[-days:] if len(kline) > days else kline
            for i, k in enumerate(recent):
                if i == 0:
                    continue
                prev_close = float(recent[i-1].get('close', 0))
                close = float(k.get('close', 0))
                if prev_close > 0:
                    pct = (close / prev_close - 1) * 100
                    if pct >= 9.8:  # 主板涨停约10%
                        count += 1
                        dates.append(k.get('date', ''))
        except Exception as e:
            print(f"[AI520Strategy] 涨停统计异常: {e}", flush=True)
        return count, dates

    def check_kdj_memory(self, kline: List[Dict], lookback_days: int = 10, j_threshold: float = 15.0) -> Dict:
        """检查KDJ低位记忆（近10日是否出现J<=15）"""
        try:
            kdj = self.calc_kdj(kline, n=13, m1=3, m2=3)
            k_values = kdj.get('k_values', [])
            d_values = kdj.get('d_values', [])
            if not k_values or len(k_values) < lookback_days:
                return {'has_memory': False, 'lowest_j': 100, 'memory_date': ''}

            lowest_j = 100
            memory_idx = -1
            recent_k = k_values[-lookback_days:]
            recent_d = d_values[-lookback_days:]
            for i in range(len(recent_k)):
                j_val = 3 * recent_k[i] - 2 * recent_d[i]
                if j_val < lowest_j:
                    lowest_j = j_val
                    memory_idx = i
                if j_val <= j_threshold:
                    actual_idx = len(k_values) - lookback_days + i
                    return {
                        'has_memory': True,
                        'lowest_j': round(lowest_j, 2),
                        'memory_date': kline[actual_idx].get('date', '') if actual_idx < len(kline) else '',
                        'memory_j': round(j_val, 2),
                    }
            return {'has_memory': False, 'lowest_j': round(lowest_j, 2), 'memory_date': ''}
        except Exception as e:
            print(f"[AI520Strategy] KDJ记忆检查异常: {e}", flush=True)
            return {'has_memory': False, 'lowest_j': 100, 'memory_date': ''}

    # ==================== 内部工具 ====================

    def _init_result(self) -> Dict:
        """初始化结果字典"""
        return {
            'score': 0, 'grade': 'D', 'similarity': '不相似',
            'trend_score': 0, 'strength_memory_score': 0, 'moderate_rise_score': 0,
            'pullback_score': 0, 'recovery_score': 0, 'kdj_score': 0,
            'position_score': 0, 'volume_price_score': 0,
            'pullback_type': 'NONE', 'pullback_ma5_score': 0, 'pullback_ma20_score': 0,
            'matched_conditions': [], 'missing_conditions': [], 'risk_items': [],
            'reasons': [], 'ma5': 0, 'ma10': 0, 'ma20': 0,
            'dist_ma5': 0, 'dist_ma20': 0, 'vol_ratio': 1,
            'kdj_k': 50, 'kdj_d': 50, 'kdj_j': 50,
            'limit_up_20d': 0, 'limit_up_1y': 0,
            'status': 'OK', 'data_quality': 'GOOD',
            'strategy_version': self.version,
        }

    def _check_data_quality(self, kline: List[Dict]) -> str:
        """检查数据质量"""
        if not kline or len(kline) < 30:
            return 'INSUFFICIENT'
        # 检查是否有NaN或异常值
        try:
            for k in kline[-5:]:
                close = k.get('close')
                volume = k.get('volume')
                if close is None or volume is None or close <= 0 or volume < 0:
                    return 'WARNING'
        except Exception:
            return 'WARNING'
        return 'GOOD'

    def _get_grade(self, score: float) -> Tuple[str, str]:
        """根据分数获取等级"""
        if score >= 90:
            return 'S', '高度相似'
        elif score >= 80:
            return 'A', '强相似'
        elif score >= 70:
            return 'B', '较强相似'
        elif score >= 60:
            return 'C', '相似'
        else:
            return 'D', '弱相似/不进入候选'

    def _get_pullback_type(self, result: Dict) -> str:
        """获取回踩类型（MA5 OR MA20）"""
        ma5_score = result.get('pullback_ma5_score', 0)
        ma20_score = result.get('pullback_ma20_score', 0)
        if ma5_score >= ma20_score and ma5_score > 0:
            return 'MA5'
        elif ma20_score > 0:
            return 'MA20'
        return 'NONE'


# ==================== 单例 ====================

_ai520_strategy_instance = None


def get_ai520_strategy() -> AI520Strategy:
    """获取AI520策略单例"""
    global _ai520_strategy_instance
    if _ai520_strategy_instance is None:
        _ai520_strategy_instance = AI520Strategy()
    return _ai520_strategy_instance
