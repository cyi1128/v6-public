# -*- coding: utf-8 -*-
"""
V2.7.2 统一行业过滤服务（含三层强校验）
负责：获取股票行业、行业标准化、排除行业判断、持久化缓存、多层校验
解决：静默扫描行业字段为空导致601155新城控股（房地产）未被过滤的问题
V2.7.2: 新增validate_industry三层校验，调整优先级为 full_map > 实时获取 > override
"""
import os
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(PROJECT_ROOT, 'data', 'cache')
INDUSTRY_CACHE_FILE = os.path.join(CACHE_DIR, 'industry_cache_v2.json')
INDUSTRY_OVERRIDE_FILE = os.path.join(CACHE_DIR, 'industry_override.json')
INDUSTRY_FULL_MAP_FILE = os.path.join(CACHE_DIR, 'industry_full_map.json')  # V2.7.1全量映射表（申万一级行业）

# 排除行业（V2.7.1统一规则）
EXCLUDE_INDUSTRIES = [
    '白酒', '啤酒', '黄酒', '葡萄酒', '酒类', '饮料', '酒水',
    '房地产', '农业', '保险',
]

# 行业关键词映射（用于模糊匹配）
INDUSTRY_KEYWORD_MAP = {
    '白酒': ['白酒', '白酒制造'],
    '啤酒': ['啤酒', '啤酒制造'],
    '黄酒': ['黄酒', '黄酒制造'],
    '葡萄酒': ['葡萄酒', '葡萄酒制造'],
    '酒类': ['酒类', '酒制造', '酿酒'],
    '饮料': ['饮料', '饮料制造', '软饮料'],
    '酒水': ['酒水'],
    '房地产': ['房地产', '地产', '房产'],
    '农业': ['农业', '种植业', '养殖业', '畜牧业', '渔业'],
    '保险': ['保险', '保险业'],
}

# ===== V2.7.2 行业校验常量 =====
# 申万一级行业标准列表（31个）
VALID_SHENWAN_INDUSTRIES = [
    '农林牧渔', '采掘', '化工', '钢铁', '有色金属', '电子', '家用电器',
    '食品饮料', '纺织服装', '轻工制造', '医药生物', '公用事业', '交通运输',
    '房地产', '商业贸易', '休闲服务', '综合', '建筑材料', '建筑装饰',
    '电气设备', '国防军工', '计算机', '传媒', '通信', '银行', '非银金融',
    '汽车', '机械设备', '煤炭', '石油石化', '环保',
]

# 第一层：基础常识校验 - 公用事业类关键词（不得为电子/计算机/传媒/通信）
UTILITY_KEYWORDS = ['燃气', '天然气', '电力', '发电', '水务', '供水', '环保', '热力', '供热']
FORBIDDEN_FOR_UTILITY = ['电子', '计算机', '传媒', '通信']

# 银行类 → 必须为银行
BANK_KEYWORDS = ['银行']
# 保险类 → 必须为非银金融
INSURANCE_KEYWORDS = ['保险', '人寿', '平安']
# 地产类 → 必须为房地产
REALESTATE_KEYWORDS = ['地产', '置业', '城建']
# 证券类 → 必须为非银金融
SECURITIES_KEYWORDS = ['证券', '券商']

# 第三层：历史错配股票清单（code -> 正确行业）
HISTORICAL_MISMATCH = {
    '605169': '公用事业',   # 洪通燃气
    '000811': '机械设备',   # 冰轮环境
}

# 校验日志目录
VALIDATION_LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')


class IndustryFilterService:
    """统一行业过滤服务"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._cache: Dict[str, str] = {}
        self._override: Dict[str, str] = {}
        self._full_map: Dict[str, str] = {}  # V2.7.1全量行业映射表（申万一级）
        self._unknown_count = 0
        self._validation_log_count = 0
        self._load_override()
        self._load_cache()
        self._load_full_map()  # V2.7.1加载全量映射表

    def _load_cache(self):
        """加载持久化缓存"""
        try:
            if os.path.exists(INDUSTRY_CACHE_FILE):
                with open(INDUSTRY_CACHE_FILE, 'r', encoding='utf-8') as f:
                    self._cache = json.load(f)
                print(f"[IndustryFilter] 加载行业缓存: {len(self._cache)}只", flush=True)
        except Exception as e:
            print(f"[IndustryFilter] 加载缓存失败: {e}", flush=True)
            self._cache = {}

    def _load_override(self):
        """加载行业修正映射表（V2.7.2降为最低优先级，仅作兜底）"""
        try:
            if os.path.exists(INDUSTRY_OVERRIDE_FILE):
                with open(INDUSTRY_OVERRIDE_FILE, 'r', encoding='utf-8') as f:
                    self._override = json.load(f)
                print(f"[IndustryFilter] 加载行业修正映射: {len(self._override)}只 (兜底优先级)", flush=True)
        except Exception as e:
            print(f"[IndustryFilter] 加载修正映射失败: {e}", flush=True)
            self._override = {}

    def _load_full_map(self):
        """V2.7.1加载全量行业映射表（申万一级行业，最高优先级数据源）"""
        try:
            if os.path.exists(INDUSTRY_FULL_MAP_FILE):
                with open(INDUSTRY_FULL_MAP_FILE, 'r', encoding='utf-8') as f:
                    self._full_map = json.load(f)
                print(f"[IndustryFilter] 加载全量行业映射表: {len(self._full_map)}只 (申万一级)", flush=True)
            else:
                print(f"[IndustryFilter] 全量行业映射表不存在: {INDUSTRY_FULL_MAP_FILE}", flush=True)
        except Exception as e:
            print(f"[IndustryFilter] 加载全量映射表失败: {e}", flush=True)
            self._full_map = {}

    def _save_cache(self):
        """保存持久化缓存"""
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(INDUSTRY_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[IndustryFilter] 保存缓存失败: {e}", flush=True)

    def _log_validation(self, level: str, code: str, name: str, industry: str, reason: str):
        """记录校验日志"""
        try:
            os.makedirs(VALIDATION_LOG_DIR, exist_ok=True)
            log_file = os.path.join(VALIDATION_LOG_DIR, f'industry_validation_{datetime.now().strftime("%Y%m%d")}.log')
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            line = f'[{timestamp}] [{level}] {code} {name} industry="{industry}" reason={reason}\n'
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(line)
            self._validation_log_count += 1
        except Exception:
            pass

    def validate_industry(self, code: str, name: str = '', industry: str = '') -> Tuple[bool, str, str]:
        """
        V2.7.2 三层强校验
        Returns: (is_valid, reason, corrected_industry)
        """
        if not industry:
            return False, '行业为空', ''

        corrected = industry

        # ===== 第一层：基础常识校验 =====
        # 公用事业类股票不得为电子/计算机/传媒/通信
        is_utility = any(kw in name for kw in UTILITY_KEYWORDS)
        if is_utility and industry in FORBIDDEN_FOR_UTILITY:
            corrected = '公用事业'
            reason = f'第一层: 公用事业类股票({name})不得为{industry}，修正为公用事业'
            self._log_validation('L1_FIX', code, name, industry, reason)
            return False, reason, corrected

        # 银行类必须为银行
        if any(kw in name for kw in BANK_KEYWORDS) and industry != '银行':
            corrected = '银行'
            reason = f'第一层: 银行类股票({name})必须为银行，当前为{industry}'
            self._log_validation('L1_FIX', code, name, industry, reason)
            return False, reason, corrected

        # 保险类必须为非银金融
        if any(kw in name for kw in INSURANCE_KEYWORDS) and industry != '非银金融':
            corrected = '非银金融'
            reason = f'第一层: 保险类股票({name})必须为非银金融，当前为{industry}'
            self._log_validation('L1_FIX', code, name, industry, reason)
            return False, reason, corrected

        # 地产类必须为房地产
        if any(kw in name for kw in REALESTATE_KEYWORDS) and industry != '房地产':
            corrected = '房地产'
            reason = f'第一层: 地产类股票({name})必须为房地产，当前为{industry}'
            self._log_validation('L1_FIX', code, name, industry, reason)
            return False, reason, corrected

        # 证券类必须为非银金融
        if any(kw in name for kw in SECURITIES_KEYWORDS) and industry != '非银金融':
            corrected = '非银金融'
            reason = f'第一层: 证券类股票({name})必须为非银金融，当前为{industry}'
            self._log_validation('L1_FIX', code, name, industry, reason)
            return False, reason, corrected

        # ===== 第二层：代码前缀校验（记录日志） =====
        market = '未知'
        if code.startswith('60') or code.startswith('68'):
            market = '沪市'
        elif code.startswith('00') or code.startswith('30'):
            market = '深市'
        # 行业合理性：银行/非银金融多在60开头，记录审计日志
        if industry in ['银行', '非银金融'] and code.startswith('00'):
            self._log_validation('L2_AUDIT', code, name, industry, f'第二层: 深市金融股审计 market={market}')
        elif industry in ['公用事业'] and code.startswith('60'):
            self._log_validation('L2_AUDIT', code, name, industry, f'第二层: 沪市公用事业审计 market={market}')
        else:
            self._log_validation('L2_OK', code, name, industry, f'第二层: 代码前缀校验通过 market={market}')

        # ===== 第三层：历史错配清单校验 =====
        if code in HISTORICAL_MISMATCH:
            expected = HISTORICAL_MISMATCH[code]
            if industry != expected:
                corrected = expected
                reason = f'第三层: 历史错配清单 {code}({name}) 应为{expected}，当前为{industry}'
                self._log_validation('L3_FIX', code, name, industry, reason)
                return False, reason, corrected
            else:
                self._log_validation('L3_OK', code, name, industry, f'第三层: 历史错配清单校验通过')

        # 校验行业名称是否在标准列表中
        if industry not in VALID_SHENWAN_INDUSTRIES:
            reason = f'行业名称"{industry}"不在申万一级标准列表中'
            self._log_validation('WARN', code, name, industry, reason)
            # 不强制拦截，仅告警（可能是子行业名称）
            return True, reason, industry

        return True, '校验通过', industry

    def _fetch_industry_realtime(self, code: str) -> str:
        """V2.7.2 实时从pytdx/akshare获取行业（次优先级，仅当full_map缺失时）"""
        # 尝试pytdx财务信息
        try:
            from utils.tdx_stock_list import get_finance_info_batch
            result = get_finance_info_batch([code])
            if code in result:
                industry = result[code].get('industry_name', '')
                if industry and industry != '未知':
                    return industry
        except Exception as e:
            print(f"[IndustryFilter] pytdx获取{code}行业失败: {e}", flush=True)

        # 尝试akshare个股信息
        try:
            import akshare as ak
            df = ak.stock_individual_info_em(symbol=code)
            for _, row in df.iterrows():
                if str(row.iloc[0]).strip() == '行业':
                    return str(row.iloc[1]).strip()
        except Exception as e:
            print(f"[IndustryFilter] akshare获取{code}行业失败: {e}", flush=True)

        return ''

    def get_industry(self, code: str, name: str = '') -> Tuple[str, str]:
        """
        获取股票行业（V2.7.2: full_map > 实时获取 > override，返回前强制校验）
        Returns: (industry, status) status: OK/UNKNOWN/FETCHING
        """
        # 0. 最高优先级：全量行业映射表（申万一级，权威数据源）
        if code in self._full_map:
            industry = self._full_map[code]
            if industry and industry != '未知':
                # 强制三层校验
                is_valid, reason, corrected = self.validate_industry(code, name, industry)
                if not is_valid and corrected:
                    print(f"[IndustryFilter] 校验修正: {code}({name}) {industry}→{corrected} ({reason})", flush=True)
                    self._full_map[code] = corrected
                    return corrected, 'OK'
                return industry, 'OK'

        # 1. 次优先级：实时从pytdx/akshare获取（仅当full_map缺失时）
        industry = self._fetch_industry_realtime(code)
        if industry and industry != '未知':
            # 强制三层校验
            is_valid, reason, corrected = self.validate_industry(code, name, industry)
            if not is_valid and corrected:
                print(f"[IndustryFilter] 实时获取校验修正: {code}({name}) {industry}→{corrected}", flush=True)
                industry = corrected
            # 同步到full_map和缓存
            self._full_map[code] = industry
            if self._cache.get(code) != industry:
                self._cache[code] = industry
                self._save_cache()
            return industry, 'OK'

        # 2. 最低优先级：override（仅作兜底，不再覆盖full_map）
        if code in self._override:
            industry = self._override[code]
            if industry and industry != '未知':
                is_valid, reason, corrected = self.validate_industry(code, name, industry)
                if not is_valid and corrected:
                    industry = corrected
                self._full_map[code] = industry
                if self._cache.get(code) != industry:
                    self._cache[code] = industry
                    self._save_cache()
                return industry, 'OK'

        # 3. 从缓存取（兜底）
        if code in self._cache:
            industry = self._cache[code]
            if industry and industry != '未知':
                is_valid, reason, corrected = self.validate_industry(code, name, industry)
                if not is_valid and corrected:
                    industry = corrected
                    self._cache[code] = industry
                    self._save_cache()
                return industry, 'OK'
            return '', 'UNKNOWN'

        # 4. 标记为未知
        self._cache[code] = '未知'
        self._unknown_count += 1
        return '', 'UNKNOWN'

    def batch_get_industry(self, codes: List[str]) -> Dict[str, Tuple[str, str]]:
        """
        批量获取行业（V2.7.2: full_map > 实时获取 > override，返回前强制校验）
        """
        result = {}
        need_fetch = []

        # 0. 最高优先级：全量行业映射表（申万一级，权威数据源）
        full_map_applied = 0
        full_map_fixed = 0
        for code in codes:
            if code in self._full_map:
                industry = self._full_map[code]
                if industry and industry != '未知':
                    # 强制三层校验
                    is_valid, reason, corrected = self.validate_industry(code, '', industry)
                    if not is_valid and corrected:
                        self._full_map[code] = corrected
                        industry = corrected
                        full_map_fixed += 1
                    result[code] = (industry, 'OK')
                    full_map_applied += 1
        if full_map_applied > 0:
            print(f"[IndustryFilter] 全量映射表命中: {full_map_applied}/{len(codes)}只 (校验修正{full_map_fixed}只)", flush=True)

        # 1. 次优先级：实时批量获取缺失的
        missing = [c for c in codes if c not in result]
        if missing:
            try:
                from utils.tdx_stock_list import get_finance_info_batch
                finance = get_finance_info_batch(missing)
                realtime_added = 0
                for code in missing:
                    if code in finance:
                        industry = finance[code].get('industry_name', '')
                        if industry and industry != '未知':
                            is_valid, reason, corrected = self.validate_industry(code, '', industry)
                            if not is_valid and corrected:
                                industry = corrected
                            self._full_map[code] = industry
                            if self._cache.get(code) != industry:
                                self._cache[code] = industry
                            result[code] = (industry, 'OK')
                            realtime_added += 1
                        else:
                            need_fetch.append(code)
                    else:
                        need_fetch.append(code)
                if realtime_added > 0:
                    self._save_cache()
                    print(f"[IndustryFilter] 实时获取补充: {realtime_added}只", flush=True)
            except Exception as e:
                print(f"[IndustryFilter] 批量实时获取失败: {e}", flush=True)
                need_fetch = missing

        # 2. 最低优先级：override兜底
        override_applied = 0
        for code in need_fetch[:]:
            if code in self._override:
                industry = self._override[code]
                if industry and industry != '未知':
                    is_valid, reason, corrected = self.validate_industry(code, '', industry)
                    if not is_valid and corrected:
                        industry = corrected
                    self._full_map[code] = industry
                    if self._cache.get(code) != industry:
                        self._cache[code] = industry
                    result[code] = (industry, 'OK')
                    need_fetch.remove(code)
                    override_applied += 1
        if override_applied > 0:
            self._save_cache()
            print(f"[IndustryFilter] override兜底补充: {override_applied}只", flush=True)

        # 3. 从缓存取剩余的
        for code in need_fetch[:]:
            if code in self._cache:
                industry = self._cache[code]
                if industry and industry != '未知':
                    is_valid, reason, corrected = self.validate_industry(code, '', industry)
                    if not is_valid and corrected:
                        industry = corrected
                        self._cache[code] = industry
                        self._save_cache()
                    result[code] = (industry, 'OK')
                else:
                    result[code] = ('', 'UNKNOWN')
                need_fetch.remove(code)

        # 4. 剩余标记为未知
        for code in need_fetch:
            self._cache[code] = '未知'
            result[code] = ('', 'UNKNOWN')
        if need_fetch:
            self._save_cache()

        return result

    def normalize_industry(self, industry: str) -> str:
        """行业标准化"""
        if not industry:
            return ''
        industry = industry.strip()
        # 去除常见后缀
        for suffix in ['制造', '业', '行业']:
            if industry.endswith(suffix) and len(industry) > len(suffix) + 1:
                industry = industry[:-len(suffix)]
        return industry

    def is_excluded_industry(self, industry: str, name: str = '') -> Tuple[bool, str]:
        """
        判断是否为排除行业（多数据源交叉验证：行业名称+股票名称）
        Returns: (is_excluded, matched_keyword)
        """
        # 1. 根据行业名称判断
        if industry:
            normalized = self.normalize_industry(industry)
            # 精确匹配
            if normalized in EXCLUDE_INDUSTRIES:
                return True, normalized
            # 关键词模糊匹配
            for exclude_kw, keywords in INDUSTRY_KEYWORD_MAP.items():
                for kw in keywords:
                    if kw in normalized or kw in industry:
                        return True, exclude_kw

        # 2. 根据股票名称辅助判断（解决通达信API行业代码不正确问题）
        if name:
            # 酒水行业股票名称关键词
            alcohol_names = ['茅台', '五粮液', '泸州老窖', '古井贡酒', '山西汾酒', '洋河股份',
                            '今世缘', '水井坊', '舍得', '酒鬼酒', '口子窖', '迎驾贡酒', '金徽酒',
                            '老白干', '青青稞酒', '皇台', '金种子', '顺鑫农业', '青岛啤酒',
                            '燕京啤酒', '重庆啤酒', '珠江啤酒', '惠泉啤酒', '兰州黄河', '西藏发展',
                            '张裕', '长城葡萄酒', '威龙', '通葡', '莫高', '银鸽投资',
                            '古越龙山', '会稽山', '金枫酒业', '塔牌', '沙洲', '丹阳',
                            '伊利', '蒙牛', '光明乳业', '三元股份', '新乳业', '燕塘乳业',
                            '天润乳业', '西部牧业', '贝因美', '维维股份', '养元饮品',
                            '承德露露', '海南椰岛', '深深宝', '国投中鲁', '保龄宝',
                            '量子高科', '龙力生物', '双塔食品', '汤臣倍健', '西王食品',
                            '金达威', '花园生物', '新诺威', '圣达生物', '兄弟科技',
                            '浙江医药', '新和成', '安迪苏', '梅花生物', '星湖科技',
                            '佳隆股份', '安记食品', '日辰股份', '天味食品', '千禾味业',
                            '恒顺醋业', '中炬高新', '海天味业', '加加食品', '涪陵榨菜',
                            '绝味食品', '煌上煌', '紫燕食品', '有友食品', '盐津铺子',
                            '劲仔食品', '甘源食品', '洽洽食品', '三只松鼠', '良品铺子',
                            '来伊份', '盐津铺子', '亲亲食品', '蜡笔小新', '喜之郎',
                            '盼盼食品', '达利食品', '旺旺', '统一', '康师傅', '日清',
                            '克明面业', '想念食品', '三全食品', '安井食品', '海欣食品',
                            '惠发食品', '千味央厨', '味知香', '福成股份', '新希望',
                            '牧原股份', '温氏股份', '正邦科技', '天邦股份', '大北农',
                            '唐人神', '傲农生物', '金新农', '正虹科技', '新五丰',
                            '罗牛山', '民和股份', '益生股份', '仙坛股份', '圣农发展',
                            '湘佳股份', '立华股份', '禾丰牧业', '海大集团', '大北农',
                            '正邦科技', '天康生物', '天邦股份', '唐人神', '傲农生物',
                            '金新农', '正虹科技', '新五丰', '罗牛山', '民和股份',
                            '益生股份', '仙坛股份', '圣农发展', '湘佳股份', '立华股份',
                            '禾丰牧业', '海大集团']
            for kw in alcohol_names:
                if kw in name:
                    return True, f'酒水(名称匹配:{kw})'

            # 房地产股票名称关键词
            real_estate_names = ['万科', '保利', '招商蛇口', '金地', '新城控股', '华侨城',
                                 '绿地控股', '金科股份', '阳光城', '中南建设', '荣盛发展',
                                 '泰禾集团', '华夏幸福', '蓝光发展', '富力', '雅居乐',
                                 '碧桂园', '恒大', '融创', '世茂', '华润置地', '龙湖',
                                 '远洋', '绿城', '金茂', '旭辉', '正荣', '中骏', '禹洲',
                                 '祥生', '领地', '大发', '港龙', '上坤', '三巽', '德信',
                                 '银城', '美的置业', '建业', '时代中国', '合景泰富',
                                 '佳兆业', '奥园', '龙光', '宝龙', '瑞安', '嘉里',
                                 '恒隆', '新世界', '新鸿基', '长江实业', '恒基', '信和',
                                 '太古', '九龙仓', '鹰君', '希慎', '华人置业',
                                 '中国海外', '首开股份', '北京城建', '金融街', '阳光股份',
                                 '深振业', '深物业', '沙河股份', '深深房', '粤宏远',
                                 '渝开发', '中交地产', '信达地产', '格力地产', '华发股份',
                                 '栖霞建设', '苏州高新', '张江高科', '陆家嘴', '浦东金桥',
                                 '外高桥', '中华企业', '上实发展', '新黄浦', '世茂股份',
                                 '嘉凯城', '苏宁环球', '新华联', '万通发展', '天房发展',
                                 '海泰发展', '津滨发展', '铁岭新城', '荣安地产',
                                 '广宇集团', '滨江集团', '卧龙地产', '京投发展',
                                 '城建发展', '电子城', '空港股份', '天保基建',
                                 '海泰发展', '津滨发展', '铁岭新城', '荣安地产',
                                 '广宇集团', '滨江集团', '卧龙地产', '京投发展']
            for kw in real_estate_names:
                if kw in name:
                    return True, f'房地产(名称匹配:{kw})'

            # 农业股票名称关键词
            agriculture_names = ['隆平高科', '北大荒', '苏垦农发', '亚盛集团', '海南橡胶',
                                '农发种业', '荃银高科', '登海种业', '丰乐种业', '敦煌种业',
                                '万向德农', '神农科技', '大北农', '新希望', '牧原股份',
                                '温氏股份', '正邦科技', '天邦股份', '唐人神', '傲农生物',
                                '金新农', '正虹科技', '新五丰', '罗牛山', '民和股份',
                                '益生股份', '仙坛股份', '圣农发展', '湘佳股份', '立华股份',
                                '禾丰牧业', '海大集团', '天康生物', '天邦股份', '唐人神',
                                '傲农生物', '金新农', '正虹科技', '新五丰', '罗牛山',
                                '民和股份', '益生股份', '仙坛股份', '圣农发展', '湘佳股份',
                                '立华股份', '禾丰牧业', '海大集团', '天康生物']
            for kw in agriculture_names:
                if kw in name:
                    return True, f'农业(名称匹配:{kw})'

            # 保险股票名称关键词
            insurance_names = ['中国平安', '中国人寿', '中国太保', '新华保险', '中国人保',
                              '天茂集团', '西水股份', '爱建集团', '五矿资本', '中航资本',
                              '国投资本', '越秀金控', '海德股份', '陕国投', '安信信托',
                              '江苏国信', '浙江东方', '五矿资本', '中航资本', '国投资本',
                              '越秀金控', '海德股份', '陕国投', '安信信托', '江苏国信',
                              '浙江东方']
            for kw in insurance_names:
                if kw in name:
                    return True, f'保险(名称匹配:{kw})'

        return False, ''

    def filter_stocks(self, stocks: List[Dict]) -> Tuple[List[Dict], Dict]:
        """
        批量过滤股票
        Returns: (filtered_stocks, stats)
        stats: {total, excluded, excluded_by_industry, unknown_industry, unknown_excluded}
        """
        codes = [s.get('code', '') for s in stocks if s.get('code')]
        industry_map = self.batch_get_industry(codes)

        filtered = []
        excluded_by_industry = []
        unknown_industry = []

        for stock in stocks:
            code = stock.get('code', '')
            name = stock.get('name', '')
            industry, status = industry_map.get(code, ('', 'UNKNOWN'))

            # 更新股票的行业字段
            stock['industry'] = industry
            stock['industry_status'] = status

            # 行业未知的不进入最终候选
            if status == 'UNKNOWN':
                unknown_industry.append(stock)
                continue

            # 排除行业（多数据源交叉验证：行业名称+股票名称）
            is_excluded, matched = self.is_excluded_industry(industry, name)
            if is_excluded:
                stock['exclude_reason'] = f'排除行业:{matched}'
                excluded_by_industry.append(stock)
                continue

            filtered.append(stock)

        stats = {
            'total': len(stocks),
            'filtered': len(filtered),
            'excluded_by_industry': len(excluded_by_industry),
            'unknown_industry': len(unknown_industry),
            'excluded_details': [(s.get('code'), s.get('name'), s.get('industry')) for s in excluded_by_industry],
        }

        return filtered, stats

    def get_cache_stats(self) -> Dict:
        """获取缓存统计"""
        known = sum(1 for v in self._cache.values() if v and v != '未知')
        unknown = sum(1 for v in self._cache.values() if not v or v == '未知')
        return {
            'total': len(self._cache),
            'known': known,
            'unknown': unknown,
            'override': len(self._override),
            'full_map': len(self._full_map),
        }

    def fix_cache_from_override(self) -> int:
        """用修正映射表批量修复缓存中的错误行业，返回修复数量"""
        fixed = 0
        for code, correct_industry in self._override.items():
            if code in self._cache and self._cache[code] != correct_industry:
                self._cache[code] = correct_industry
                fixed += 1
        if fixed > 0:
            self._save_cache()
            print(f"[IndustryFilter] 批量修复行业缓存: {fixed}只", flush=True)
        return fixed

    def reload_full_map(self):
        """V2.7.2 重新加载全量映射表（重建后调用）"""
        self._load_full_map()
        print(f"[IndustryFilter] 全量映射表已重新加载: {len(self._full_map)}只", flush=True)


# 单例
def get_industry_filter_service() -> IndustryFilterService:
    return IndustryFilterService()
