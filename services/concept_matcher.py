# -*- coding: utf-8 -*-
"""
V2.8 概念跟随算法优化模块
三维度综合匹配：
1. 当日分钟级走势相关性（与板块龙头股走势相关性）
2. 板块联动涨幅（所属概念板块当日涨幅排名）
3. 个股所属概念重合度（与热门概念的重合数量）

匹配粒度：优先匹配细分概念板块（如影视院线、基建装饰），禁止直接输出一级大行业
匹配度输出：保留匹配度百分比数值，与实际联动强度正相关
异常兜底：无匹配细分概念时fallback到二级行业，禁止出现空值或错误分类
"""
import os
import sys
import time
import json
import logging
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logger = logging.getLogger(__name__)


def _log(msg: str, level: str = 'INFO'):
    print(f"[概念匹配] {msg}", flush=True)


# 细分概念板块定义（概念名→包含的关键词/股票特征）
# 优先匹配这些细分概念，而非一级大行业
SECTOR_CONCEPTS = {
    # 科技类细分概念
    'AI算力': ['算力', '服务器', 'GPU', '光模块', 'IDC', '数据中心', '液冷'],
    'AI应用': ['AI应用', '大模型', 'AIGC', 'ChatGPT', '人工智能', '智能办公'],
    '半导体设备': ['半导体设备', '刻蚀', '薄膜沉积', '光刻机', '清洗设备'],
    '半导体材料': ['半导体材料', '硅片', '光刻胶', '电子特气', '靶材'],
    '芯片设计': ['芯片设计', 'SoC', 'MCU', '模拟芯片', '射频芯片'],
    '消费电子': ['消费电子', '苹果链', '华为链', '手机', 'TWS', 'VR', 'AR'],
    '影视院线': ['影视', '院线', '电影', '票房', '影院', '传媒娱乐'],
    '游戏': ['游戏', '手游', '端游', '电竞', '版号'],
    '通信设备': ['通信设备', '5G', '6G', '基站', '光通信', '卫星互联网'],
    # 新能源类细分概念
    '光伏设备': ['光伏', '组件', '逆变器', '硅料', '电池片', 'TOPCon', 'HJT'],
    '储能': ['储能', '电化学储能', '抽水蓄能', '压缩空气', '储能变流器'],
    '锂电池': ['锂电池', '动力电池', '正极', '负极', '电解液', '隔膜'],
    '新能源车': ['新能源车', '电动汽车', '智能驾驶', '自动驾驶', '充电桩'],
    '风电设备': ['风电', '风机', '塔筒', '海缆', '海上风电'],
    # 医药类细分概念
    '创新药': ['创新药', 'PD-1', 'ADC', '双抗', '基因治疗', '细胞治疗'],
    '医疗器械': ['医疗器械', '影像设备', 'IVD', '体外诊断', '高值耗材'],
    '中药': ['中药', '中成药', '中药材', '经典名方'],
    'CXO': ['CXO', 'CRO', 'CDMO', '医药外包'],
    # 消费类细分概念
    '白酒': ['白酒', '酱酒', '浓香型', '酱香型'],
    '食品加工': ['食品加工', '休闲食品', '速冻食品', '调味品'],
    '零售百货': ['零售', '百货', '超市', '便利店', '免税'],
    '旅游酒店': ['旅游', '酒店', '景区', '免税', '出境游'],
    '餐饮': ['餐饮', '连锁餐饮', '预制菜'],
    # 金融类细分概念
    '银行': ['银行', '城商行', '股份制银行'],
    '证券': ['证券', '券商', '投行', '经纪业务'],
    '保险': ['保险', '寿险', '财险'],
    # 地产基建类细分概念
    '房地产开发': ['房地产', '地产开发', '住宅开发'],
    '基建装饰': ['基建', '装饰', '装修', '建筑装饰', '工程建设'],
    '水泥建材': ['水泥', '建材', '玻璃', '陶瓷', '石膏板'],
    # 周期类细分概念
    '煤炭开采': ['煤炭', '动力煤', '焦煤', '无烟煤'],
    '油气开采': ['石油', '天然气', '油气', '原油'],
    '钢铁': ['钢铁', '普钢', '特钢'],
    '有色金属': ['有色', '铜', '铝', '黄金', '稀土', '锂矿'],
    '化工新材料': ['化工', '新材料', '高分子', '复合材料'],
    # 高端制造类细分概念
    '工业母机': ['工业母机', '数控机床', '高端机床'],
    '机器人': ['机器人', '工业机器人', '人形机器人', '减速器', '伺服电机'],
    '军工装备': ['军工', '航空发动机', '导弹', '无人机', '舰船'],
    '汽车零部件': ['汽车零部件', '汽配', '汽车电子', '热管理'],
    # 其他细分概念
    '环保': ['环保', '环境治理', '污水处理', '固废处理'],
    '电力公用': ['电力', '公用事业', '火电', '水电', '核电'],
    '农业种植': ['农业', '种植', '种业', '粮食', '乡村振兴'],
    '养殖': ['养殖', '生猪', '肉鸡', '水产'],
}

# 概念→龙头股代码映射（用于走势相关性计算）
CONCEPT_LEADER_STOCKS = {
    'AI算力': ['000977', '300308', '603019'],
    'AI应用': ['300418', '002230', '300059'],
    '半导体设备': ['002371', '688012', '688082'],
    '芯片设计': ['603501', '002049', '300782'],
    '消费电子': ['002475', '002241', '300433'],
    '光伏设备': ['601012', '002129', '300274'],
    '储能': ['300750', '002594', '600905'],
    '锂电池': ['300750', '002460', '300014'],
    '新能源车': ['002594', '600104', '601633'],
    '创新药': ['600276', '300760', '688235'],
    '医疗器械': ['300760', '002223', '688271'],
    '白酒': ['600519', '000858', '000568'],
    '银行': ['601398', '601288', '000001'],
    '证券': ['600030', '601688', '600999'],
    '房地产开发': ['000002', '600048', '001979'],
    '煤炭开采': ['601088', '600188', '601225'],
    '机器人': ['300024', '002747', '688017'],
    '军工装备': ['600760', '000768', '600893'],
}


class ConceptMatcher:
    """概念跟随匹配器（三维度综合匹配）"""

    def __init__(self):
        self._kline_cache: Dict[str, List[Dict]] = {}
        self._concept_cache: Dict[str, Dict] = {}  # code -> {concept, match_score, details}

    def match_concept(self, code: str, name: str = '',
                      industry: str = '', kline: List[Dict] = None) -> Dict:
        """
        三维度综合匹配概念
        Args:
            code: 股票代码
            name: 股票名称
            industry: 申万一级行业
            kline: K线数据（用于走势相关性计算）
        Returns:
            {concept, match_score, dimension_scores, is_fallback, concept_type}
        """
        start_time = time.time()

        # 1. 维度一：个股所属概念重合度（基于名称/行业/关键词匹配）
        concept_keyword_scores = self._calc_keyword_match(code, name, industry)

        # 2. 维度二：板块联动涨幅（概念板块当日涨幅排名）
        concept_sector_scores = self._calc_sector_momentum(concept_keyword_scores)

        # 3. 维度三：当日走势相关性（与概念龙头股走势相关性）
        concept_correlation_scores = self._calc_trend_correlation(code, kline, concept_keyword_scores)

        # 4. 三维度加权综合
        final_scores = {}
        for concept in concept_keyword_scores:
            kw_score = concept_keyword_scores.get(concept, 0)
            sector_score = concept_sector_scores.get(concept, 50)  # 默认中性
            corr_score = concept_correlation_scores.get(concept, 50)  # 默认中性
            # 权重：关键词重合40% + 板块联动30% + 走势相关性30%
            final = kw_score * 0.4 + sector_score * 0.3 + corr_score * 0.3
            final_scores[concept] = round(final, 1)

        # 5. 选择匹配度最高的概念
        if final_scores:
            best_concept = max(final_scores, key=final_scores.get)
            best_score = final_scores[best_concept]
            is_fallback = False
            concept_type = '细分概念'
        else:
            # 兜底：使用二级行业
            best_concept = industry if industry else '综合'
            best_score = 40.0
            is_fallback = True
            concept_type = '行业兜底'

        result = {
            'concept': best_concept,
            'match_score': best_score,
            'dimension_scores': {
                'keyword': concept_keyword_scores.get(best_concept, 0),
                'sector_momentum': concept_sector_scores.get(best_concept, 50),
                'trend_correlation': concept_correlation_scores.get(best_concept, 50),
            },
            'is_fallback': is_fallback,
            'concept_type': concept_type,
            'all_candidates': sorted(final_scores.items(), key=lambda x: -x[1])[:5],
        }

        elapsed = time.time() - start_time
        if elapsed > 0.5:
            _log(f"{code} {name} 概念匹配耗时{elapsed:.2f}s → {best_concept}({best_score}%)")

        return result

    def _calc_keyword_match(self, code: str, name: str, industry: str) -> Dict[str, float]:
        """维度一：个股所属概念重合度（关键词匹配）"""
        scores = {}
        text = f"{name} {industry}"

        for concept, keywords in SECTOR_CONCEPTS.items():
            match_count = 0
            for kw in keywords:
                if kw in text:
                    match_count += 1
            if match_count > 0:
                # 匹配关键词越多，得分越高（最高100）
                score = min(100, match_count / len(keywords) * 100 + 30)
                scores[concept] = round(score, 1)

        # 如果没有匹配到任何细分概念，基于行业推荐相关概念
        if not scores and industry:
            industry_concept_map = {
                '电子': ['芯片设计', '消费电子', '半导体设备'],
                '计算机': ['AI应用', 'AI算力'],
                '通信': ['通信设备'],
                '传媒': ['影视院线', '游戏'],
                '医药生物': ['创新药', '医疗器械', 'CXO'],
                '食品饮料': ['白酒', '食品加工'],
                '电力设备': ['光伏设备', '储能', '锂电池'],
                '汽车': ['新能源车', '汽车零部件'],
                '银行': ['银行'],
                '非银金融': ['证券', '保险'],
                '房地产': ['房地产开发'],
                '建筑装饰': ['基建装饰'],
                '建筑材料': ['水泥建材'],
                '煤炭': ['煤炭开采'],
                '石油石化': ['油气开采'],
                '有色金属': ['有色金属'],
                '基础化工': ['化工新材料'],
                '机械设备': ['工业母机', '机器人'],
                '国防军工': ['军工装备'],
                '商贸零售': ['零售百货'],
                '社会服务': ['旅游酒店', '餐饮'],
                '家用电器': ['消费电子'],
                '环保': ['环保'],
                '公用事业': ['电力公用'],
                '农林牧渔': ['农业种植', '养殖'],
            }
            if industry in industry_concept_map:
                for concept in industry_concept_map[industry]:
                    base_score = 45.0
                    # 食品饮料行业：名称含酒/窖/酿才推荐白酒，否则优先食品加工
                    if industry == '食品饮料' and concept == '白酒':
                        if not any(kw in name for kw in ['酒', '窖', '酿', '茅台', '五粮液', '汾酒', '泸州']):
                            base_score = 20.0
                    # 电力设备：名称含电池/锂/储能优先锂电池/储能
                    if industry == '电力设备' and concept == '电力公用':
                        if any(kw in name for kw in ['电池', '锂', '储能', '宁德', '阳光', '光伏']):
                            base_score = 20.0
                    scores[concept] = base_score

        return scores

    # 板块涨幅数据缓存（模块级，避免重复调用SectorRadarEngine）
    _sector_momentum_cache = None
    _sector_momentum_cache_time = 0.0
    _sector_momentum_degraded_logged = False

    def _get_sector_change_map(self) -> Dict[str, float]:
        """获取板块名称→当日涨幅映射（带30秒缓存）
        优先从 SectorRadarEngine.get_all_sector_data() 获取真实板块涨幅，
        失败返回空dict（调用方使用降级固定分数）。
        """
        import time as _time
        now = _time.time()
        if ConceptMatcher._sector_momentum_cache is not None and (now - ConceptMatcher._sector_momentum_cache_time) < 30:
            return ConceptMatcher._sector_momentum_cache

        # 【2026-09-24 清理 v28 死引用】原数据源 v28.core.sector_radar 已下线，
        # 板块动量拿不到真实涨幅，统一给空 map，调用方走原有的降级分数逻辑。
        change_map = {}

        ConceptMatcher._sector_momentum_cache = change_map
        ConceptMatcher._sector_momentum_cache_time = now
        return change_map

    def _calc_sector_momentum(self, concept_scores: Dict[str, float]) -> Dict[str, float]:
        """维度二：板块联动涨幅（概念板块当日涨幅排名）
        优先使用 SectorRadarEngine 真实板块涨幅计算动量分：
          涨幅>3%→90分，1-3%→75分，0-1%→60分，<0%→40分
        板块数据获取失败时回退到固定分数（热门概念75，其他55）。
        """
        scores = {}
        change_map = self._get_sector_change_map()

        # 概念名→板块名的模糊匹配关键词
        concept_to_sector_kw = {
            'AI算力': ['计算机', '电子', '通信'],
            'AI应用': ['计算机', '传媒'],
            '半导体设备': ['电子'],
            '半导体材料': ['电子'],
            '芯片设计': ['电子'],
            '消费电子': ['电子'],
            '影视院线': ['传媒'],
            '游戏': ['传媒'],
            '通信设备': ['通信'],
            '光伏设备': ['电力设备'],
            '储能': ['电力设备'],
            '锂电池': ['电力设备', '有色金属'],
            '新能源车': ['汽车', '电力设备'],
            '风电设备': ['电力设备'],
            '创新药': ['医药生物'],
            '医疗器械': ['医药生物'],
            '中药': ['医药生物'],
            'CXO': ['医药生物'],
            '白酒': ['食品饮料'],
            '食品加工': ['食品饮料'],
            '零售百货': ['商业贸易', '商贸零售'],
            '旅游酒店': ['休闲服务', '社会服务'],
            '餐饮': ['休闲服务', '社会服务'],
            '银行': ['银行'],
            '证券': ['非银金融'],
            '保险': ['非银金融'],
            '房地产开发': ['房地产'],
            '基建装饰': ['建筑装饰'],
            '水泥建材': ['建筑材料'],
            '煤炭开采': ['煤炭'],
            '油气开采': ['石油石化'],
            '钢铁': ['钢铁'],
            '有色金属': ['有色金属'],
            '化工新材料': ['基础化工', '化工'],
            '工业母机': ['机械设备'],
            '机器人': ['机械设备'],
            '军工装备': ['国防军工'],
            '汽车零部件': ['汽车'],
            '环保': ['环保'],
            '电力公用': ['公用事业'],
            '农业种植': ['农林牧渔'],
            '养殖': ['农林牧渔'],
        }

        for concept in concept_scores:
            if change_map:
                # 尝试精确匹配概念名
                pct = change_map.get(concept)
                # 精确匹配失败时，用关键词模糊匹配
                if pct is None:
                    kws = concept_to_sector_kw.get(concept, [])
                    matched_pcts = [change_map[kw] for kw in kws if kw in change_map]
                    if matched_pcts:
                        pct = sum(matched_pcts) / len(matched_pcts)
                if pct is not None:
                    if pct > 3:
                        scores[concept] = 90.0
                    elif pct >= 1:
                        scores[concept] = 75.0
                    elif pct >= 0:
                        scores[concept] = 60.0
                    else:
                        scores[concept] = 40.0
                    continue

            # 降级：固定分数
            if not ConceptMatcher._sector_momentum_degraded_logged:
                print("[概念匹配] 板块动量使用降级固定分数（热门75/其他55）", flush=True)
                ConceptMatcher._sector_momentum_degraded_logged = True
            hot_concepts = ['AI算力', 'AI应用', '储能', '创新药', '机器人', '半导体设备']
            if concept in hot_concepts:
                scores[concept] = 75.0
            else:
                scores[concept] = 55.0
        return scores

    def _calc_trend_correlation(self, code: str, kline: List[Dict],
                                  concept_scores: Dict[str, float]) -> Dict[str, float]:
        """维度三：当日走势相关性（与概念龙头股走势相关性）"""
        scores = {}
        if not kline or len(kline) < 2:
            return scores

        # 计算个股当日涨跌幅
        stock_pct = 0
        if len(kline) >= 2 and kline[-2].get('close', 0) > 0:
            stock_pct = (kline[-1]['close'] - kline[-2]['close']) / kline[-2]['close'] * 100

        for concept in concept_scores:
            leaders = CONCEPT_LEADER_STOCKS.get(concept, [])
            if not leaders:
                scores[concept] = 50.0
                continue

            # 简化：如果个股涨幅与龙头股平均涨幅方向一致，相关性高
            # 实际应计算分钟级走势相关系数
            avg_leader_pct = self._get_avg_leader_pct(leaders)
            if avg_leader_pct == 0:
                scores[concept] = 50.0
            elif (stock_pct > 0 and avg_leader_pct > 0) or (stock_pct < 0 and avg_leader_pct < 0):
                # 同向，根据幅度接近度计算
                diff = abs(stock_pct - avg_leader_pct)
                corr = max(30, 80 - diff * 5)
                scores[concept] = round(corr, 1)
            else:
                # 反向
                scores[concept] = 30.0

        return scores

    def _get_avg_leader_pct(self, leader_codes: List[str]) -> float:
        """获取龙头股平均涨跌幅（从DuckDB缓存）"""
        try:
            import duckdb
            db_path = os.path.join(PROJECT_ROOT, 'data', 'cache', 'kline_cache.duckdb')
            if not os.path.exists(db_path):
                return 0
            con = duckdb.connect(db_path, read_only=False)
            pcts = []
            for code in leader_codes:
                row = con.execute(
                    "SELECT close FROM kline_cache WHERE code = ? ORDER BY date DESC LIMIT 2",
                    [code]
                ).fetchall()
                if len(row) >= 2 and row[1][0] > 0:
                    pct = (row[0][0] - row[1][0]) / row[1][0] * 100
                    pcts.append(pct)
            con.close()
            return sum(pcts) / len(pcts) if pcts else 0
        except Exception:
            return 0

    def batch_match_concepts(self, signals: List[Dict]) -> List[Dict]:
        """批量匹配概念（在扫描线程内完成）"""
        start_time = time.time()
        matched = 0
        fallback_count = 0

        for sig in signals:
            code = sig.get('code', '')
            name = sig.get('name', '')
            industry = sig.get('industry', '')
            kline = sig.get('_kline_data')  # 扫描时传入的K线数据

            try:
                result = self.match_concept(code, name, industry, kline)
                sig['concept'] = result['concept']
                sig['concept_match_score'] = result['match_score']
                sig['concept_type'] = result['concept_type']
                sig['concept_is_fallback'] = result['is_fallback']
                if result['is_fallback']:
                    fallback_count += 1
                else:
                    matched += 1
            except Exception as e:
                _log(f"{code} 概念匹配异常: {e}", 'WARN')
                sig['concept'] = industry if industry else '综合'
                sig['concept_match_score'] = 0
                sig['concept_type'] = '异常兜底'
                sig['concept_is_fallback'] = True

        elapsed = time.time() - start_time
        _log(f"批量概念匹配完成: {len(signals)}只, 细分概念{matched}只, 兜底{fallback_count}只, 耗时{elapsed:.2f}s")

        return signals


# 全局单例
_matcher: Optional[ConceptMatcher] = None


def get_concept_matcher() -> ConceptMatcher:
    global _matcher
    if _matcher is None:
        _matcher = ConceptMatcher()
    return _matcher


def match_stock_concept(code: str, name: str = '', industry: str = '',
                         kline: List[Dict] = None) -> Dict:
    """便捷函数：匹配单只股票概念"""
    return get_concept_matcher().match_concept(code, name, industry, kline)


def batch_match_concepts(signals: List[Dict]) -> List[Dict]:
    """便捷函数：批量匹配概念"""
    return get_concept_matcher().batch_match_concepts(signals)


if __name__ == '__main__':
    # 测试
    tests = [
        ('002820', '桂发祥', '食品饮料'),
        ('601116', '三江购物', '商贸零售'),
        ('300750', '宁德时代', '电力设备'),
        ('600519', '贵州茅台', '食品饮料'),
        ('000001', '平安银行', '银行'),
    ]
    for code, name, industry in tests:
        result = match_stock_concept(code, name, industry)
        print(f"{code} {name}({industry}): {result['concept']} "
              f"匹配度{result['match_score']}% {result['concept_type']} "
              f"{'(兜底)' if result['is_fallback'] else ''}")
