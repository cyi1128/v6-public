# -*- coding: utf-8 -*-
"""
强势主力行为选股系统 V1.2.3 - 智能扫描缓存管理

解决每次启动都重新扫描5000+股票导致等待过慢的问题。
第一次扫描约几十秒，以后启动1-3秒进入股票池。

缓存类型和有效期：
- 扫描结果：30分钟（盘中）/ 当天有效（非交易时段）
- 行情数据：30分钟
- 评分数据：当天有效
- 版本不匹配：立即失效
"""
import os
import json
import time
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import asdict

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False


class _CacheJSONEncoder(json.JSONEncoder):
    """处理numpy等非标准JSON类型的编码器"""
    def default(self, o):
        if _HAS_NUMPY:
            if isinstance(o, (np.bool_,)):
                return bool(o)
            if isinstance(o, (np.integer,)):
                return int(o)
            if isinstance(o, (np.floating,)):
                return float(o)
            if isinstance(o, (np.ndarray,)):
                return o.tolist()
        if isinstance(o, datetime):
            return o.strftime('%Y-%m-%d %H:%M:%S')
        return super().default(o)

# 缓存版本号，策略/评分逻辑变更时升级此版本号
CACHE_VERSION = "V1.2.3"

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 缓存目录
CACHE_DIR = os.path.join(PROJECT_ROOT, "data", "cache")
QUOTE_CACHE_DIR = os.path.join(CACHE_DIR, "quote_cache")
SCORE_CACHE_DIR = os.path.join(CACHE_DIR, "score_cache")

# 缓存文件名
CACHE_INFO_FILE = os.path.join(CACHE_DIR, "cache_info.json")
SCAN_RESULT_FILE = os.path.join(CACHE_DIR, "scan_result_cache.json")


class ScanCacheManager:
    """智能扫描缓存管理器"""

    def __init__(self):
        self.cache_dir = CACHE_DIR
        self.quote_cache_dir = QUOTE_CACHE_DIR
        self.score_cache_dir = SCORE_CACHE_DIR
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.quote_cache_dir, exist_ok=True)
        os.makedirs(self.score_cache_dir, exist_ok=True)

    # ============================================================
    # 交易时段判断
    # ============================================================

    @staticmethod
    def is_trading_time(now: datetime = None) -> bool:
        """判断当前是否为交易时段（周一至周五 09:30-11:30 / 13:00-15:00）"""
        if now is None:
            now = datetime.now()
        # 周末
        if now.weekday() >= 5:
            return False
        t = now.time()
        morning = t >= datetime.strptime("09:30", "%H:%M").time() and t <= datetime.strptime("11:30", "%H:%M").time()
        afternoon = t >= datetime.strptime("13:00", "%H:%M").time() and t <= datetime.strptime("15:00", "%H:%M").time()
        return morning or afternoon

    @staticmethod
    def is_pre_market(now: datetime = None) -> bool:
        """判断是否为开盘前（09:00-09:30）"""
        if now is None:
            now = datetime.now()
        if now.weekday() >= 5:
            return False
        t = now.time()
        return t >= datetime.strptime("09:00", "%H:%M").time() and t < datetime.strptime("09:30", "%H:%M").time()

    def _get_max_age_seconds(self) -> int:
        """根据当前时段获取缓存最大有效期（秒）"""
        now = datetime.now()
        if self.is_trading_time(now):
            return 30 * 60  # 盘中30分钟
        elif self.is_pre_market(now):
            return 0  # 开盘前缓存立即失效
        else:
            # 非交易时段：当天有效（到次日0点）
            tomorrow = datetime(now.year, now.month, now.day) + timedelta(days=1)
            return int((tomorrow - now).total_seconds())

    # ============================================================
    # 扫描结果缓存
    # ============================================================

    def save_scan_result(self, results: List, funnel, scan_mode: str = "quick"):
        """保存完整扫描结果

        Args:
            results: StockScanResult列表
            funnel: FunnelStats对象
            scan_mode: 扫描模式
        """
        try:
            now = datetime.now()
            # 序列化结果
            result_list = []
            for r in results:
                if hasattr(r, 'to_dict'):
                    d = r.to_dict()
                elif hasattr(r, '__dict__'):
                    d = dict(r.__dict__)
                else:
                    d = dict(r)
                # kline_data可能很大，不缓存
                d.pop('kline_data', None)
                result_list.append(d)

            # 保存完整结果
            with open(SCAN_RESULT_FILE, 'w', encoding='utf-8') as f:
                json.dump(result_list, f, ensure_ascii=False, indent=2, cls=_CacheJSONEncoder)

            # 保存缓存信息
            funnel_dict = funnel.to_dict() if hasattr(funnel, 'to_dict') else dict(funnel)
            cache_info = {
                "version": CACHE_VERSION,
                "scan_time": now.strftime("%Y-%m-%d %H:%M:%S"),
                "scan_timestamp": now.timestamp(),
                "market_count": funnel_dict.get('全市场股票', 0),
                "result_count": len(results),
                "scan_mode": scan_mode,
                "funnel_summary": {
                    "main_board": funnel_dict.get('主板股票', 0),
                    "layer1_pass": funnel_dict.get('第一层基础筛选', 0),
                    "layer2_pass": funnel_dict.get('第二层行为预筛', 0),
                    "layer3_pass": funnel_dict.get('第三层深度分析', 0),
                    "score_60_plus": funnel_dict.get('评分60以上', 0),
                    "b1_count": funnel_dict.get('B1观察买点', 0),
                    "b2_count": funnel_dict.get('B2确认买点', 0),
                    "b3_count": funnel_dict.get('B3强势买点', 0),
                }
            }
            with open(CACHE_INFO_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache_info, f, ensure_ascii=False, indent=2)

            print(f"[CACHE] 扫描结果已保存: {len(results)}只股票, 模式={scan_mode}", flush=True)
            return True
        except Exception as e:
            print(f"[CACHE ERROR] 保存扫描结果失败: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return False

    def load_scan_result(self) -> Tuple[Optional[List], Optional[Dict], bool]:
        """加载缓存的扫描结果

        Returns:
            (results, cache_info, is_valid)
            - results: StockScanResult列表（反序列化），无效时为None
            - cache_info: 缓存信息字典，无效时为None
            - is_valid: 缓存是否有效（版本匹配且未过期）
        """
        try:
            # 读取缓存信息
            if not os.path.exists(CACHE_INFO_FILE) or not os.path.exists(SCAN_RESULT_FILE):
                return None, None, False

            with open(CACHE_INFO_FILE, 'r', encoding='utf-8') as f:
                cache_info = json.load(f)

            # 版本检查
            if cache_info.get('version') != CACHE_VERSION:
                print(f"[CACHE] 缓存版本不匹配: {cache_info.get('version')} != {CACHE_VERSION}", flush=True)
                return None, cache_info, False

            # 有效期检查
            scan_ts = cache_info.get('scan_timestamp', 0)
            max_age = self._get_max_age_seconds()
            if max_age == 0:
                print("[CACHE] 开盘前缓存已失效", flush=True)
                return None, cache_info, False

            age = time.time() - scan_ts
            if age > max_age:
                print(f"[CACHE] 缓存已过期: {age/60:.0f}分钟 > {max_age/60:.0f}分钟", flush=True)
                return None, cache_info, False

            # 读取结果
            with open(SCAN_RESULT_FILE, 'r', encoding='utf-8') as f:
                result_list = json.load(f)

            # 反序列化为StockScanResult
            from strategy.base import (StockScanResult, ModelMatch, AIScore,
                                       BuySellSignal, KlineAnnotation)
            results = []
            for d in result_list:
                try:
                    # 重建matched_models
                    matched_models = []
                    for mm in d.get('matched_models', []):
                        matched_models.append(ModelMatch(
                            model_name=mm.get('model_name', ''),
                            matched=mm.get('matched', False),
                            stage=mm.get('stage', ''),
                            score=mm.get('score', 0.0),
                            signals=mm.get('signals', []),
                            risks=mm.get('risks', []),
                            tags=mm.get('tags', []),
                            support=mm.get('support', 0.0),
                            pressure=mm.get('pressure', 0.0),
                            detail=mm.get('detail', {}),
                        ))
                    # 重建buy_signal
                    bs = d.get('buy_signal', {})
                    buy_signal = BuySellSignal(
                        buy_level=bs.get('buy_level', ''),
                        sell_level=bs.get('sell_level', ''),
                        buy_reasons=bs.get('buy_reasons', []),
                        sell_reasons=bs.get('sell_reasons', []),
                        risk_level=bs.get('risk_level', '低'),
                    )
                    # 重建score
                    sc = d.get('score', {})
                    score = AIScore(
                        total=sc.get('total', 0.0),
                        main_force_structure=sc.get('main_force_structure', 0.0),
                        volume_price=sc.get('volume_price', 0.0),
                        trend_ma=sc.get('trend_ma', 0.0),
                        limit_up_gene=sc.get('limit_up_gene', 0.0),
                        tech_indicator=sc.get('tech_indicator', 0.0),
                        market_env=sc.get('market_env', 0.0),
                        level=sc.get('level', ''),
                        breakdown=sc.get('breakdown', {}),
                        reason=sc.get('reason', ''),
                    )
                    # 重建annotation
                    ann = d.get('annotation', {})
                    annotation = KlineAnnotation(
                        regions=ann.get('regions', []),
                        markers=ann.get('markers', []),
                        model_labels=ann.get('model_labels', []),
                    )
                    result = StockScanResult(
                        code=d.get('code', ''),
                        name=d.get('name', ''),
                        price=d.get('price', 0.0),
                        pct_chg=d.get('pct_chg', 0.0),
                        industry=d.get('industry', ''),
                        matched_models=matched_models,
                        best_model=d.get('best_model', ''),
                        best_model_score=d.get('best_model_score', 0.0),
                        current_stage=d.get('current_stage', ''),
                        buy_signal=buy_signal,
                        risk_warnings=d.get('risk_warnings', []),
                        support=d.get('support', 0.0),
                        pressure=d.get('pressure', 0.0),
                        score=score,
                        annotation=annotation,
                        kline_data={},
                        scan_time=d.get('scan_time', ''),
                        funnel_stage=d.get('funnel_stage', ''),
                    )
                    results.append(result)
                except Exception as e:
                    print(f"[CACHE WARN] 反序列化股票{d.get('code', '?')}失败: {e}", flush=True)
                    continue

            print(f"[CACHE] 缓存加载成功: {len(results)}只股票, "
                  f"扫描时间={cache_info.get('scan_time')}, "
                  f"剩余有效期={int((max_age-age)/60)}分钟", flush=True)
            return results, cache_info, True
        except Exception as e:
            print(f"[CACHE ERROR] 加载缓存失败: {e}", flush=True)
            return None, None, False

    def is_cache_valid(self, max_age_minutes: int = 30) -> bool:
        """缓存是否有效"""
        _, _, is_valid = self.load_scan_result()
        return is_valid

    def get_cache_info(self) -> Dict:
        """返回缓存信息"""
        try:
            if not os.path.exists(CACHE_INFO_FILE):
                return {
                    "exists": False,
                    "status": "无缓存",
                    "version": CACHE_VERSION,
                }
            with open(CACHE_INFO_FILE, 'r', encoding='utf-8') as f:
                info = json.load(f)

            scan_ts = info.get('scan_timestamp', 0)
            max_age = self._get_max_age_seconds()
            age = time.time() - scan_ts

            if info.get('version') != CACHE_VERSION:
                status = "版本不匹配"
            elif max_age == 0:
                status = "开盘前缓存失效"
            elif age > max_age:
                status = f"已过期({int(age/60)}分钟)"
            else:
                remaining = int((max_age - age) / 60)
                if self.is_trading_time():
                    status = f"缓存有效({remaining}分钟后过期)"
                else:
                    status = f"缓存有效(非交易时段,{remaining}分钟后过期)"

            return {
                "exists": True,
                "status": status,
                "version": info.get('version', ''),
                "scan_time": info.get('scan_time', ''),
                "scan_timestamp": scan_ts,
                "market_count": info.get('market_count', 0),
                "result_count": info.get('result_count', 0),
                "scan_mode": info.get('scan_mode', ''),
                "funnel_summary": info.get('funnel_summary', {}),
                "age_minutes": int(age / 60),
                "is_trading_time": self.is_trading_time(),
            }
        except Exception as e:
            return {"exists": False, "status": f"缓存读取失败: {e}", "version": CACHE_VERSION}

    def clear_cache(self) -> bool:
        """清除扫描结果缓存"""
        try:
            for f in [CACHE_INFO_FILE, SCAN_RESULT_FILE]:
                if os.path.exists(f):
                    os.remove(f)
            print("[CACHE] 扫描结果缓存已清除", flush=True)
            return True
        except Exception as e:
            print(f"[CACHE ERROR] 清除缓存失败: {e}", flush=True)
            return False

    # ============================================================
    # 行情缓存（单只股票，30分钟有效）
    # ============================================================

    def _quote_cache_file(self, code: str) -> str:
        safe_code = code.replace('.', '_').replace('/', '_')
        return os.path.join(self.quote_cache_dir, f"{safe_code}.json")

    def save_quote_cache(self, code: str, quote_data: Dict):
        """保存单只股票行情缓存（30分钟有效）"""
        try:
            data = {
                "code": code,
                "data": quote_data,
                "timestamp": time.time(),
            }
            with open(self._quote_cache_file(code), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass

    def load_quote_cache(self, code: str) -> Optional[Dict]:
        """加载行情缓存（30分钟内有效）"""
        try:
            fpath = self._quote_cache_file(code)
            if not os.path.exists(fpath):
                return None
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if time.time() - data.get('timestamp', 0) > 30 * 60:
                return None
            return data.get('data')
        except Exception:
            return None

    # ============================================================
    # 评分缓存（当天有效）
    # ============================================================

    def _score_cache_file(self, code: str) -> str:
        safe_code = code.replace('.', '_').replace('/', '_')
        today = datetime.now().strftime('%Y%m%d')
        return os.path.join(self.score_cache_dir, f"{safe_code}_{today}.json")

    def save_score_cache(self, code: str, score_data: Dict):
        """保存评分缓存（当天有效）"""
        try:
            data = {
                "code": code,
                "data": score_data,
                "timestamp": time.time(),
                "date": datetime.now().strftime('%Y-%m-%d'),
            }
            with open(self._score_cache_file(code), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass

    def load_score_cache(self, code: str) -> Optional[Dict]:
        """加载评分缓存（当天有效）"""
        try:
            fpath = self._score_cache_file(code)
            if not os.path.exists(fpath):
                return None
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # 检查是否是今天的缓存
            if data.get('date') != datetime.now().strftime('%Y-%m-%d'):
                return None
            return data.get('data')
        except Exception:
            return None

    def clear_expired_score_cache(self):
        """清理过期的评分缓存（非今天的文件）"""
        try:
            today = datetime.now().strftime('%Y%m%d')
            cleared = 0
            for fname in os.listdir(self.score_cache_dir):
                if fname.endswith('.json') and today not in fname:
                    os.remove(os.path.join(self.score_cache_dir, fname))
                    cleared += 1
            if cleared > 0:
                print(f"[CACHE] 清理过期评分缓存: {cleared}个文件", flush=True)
        except Exception:
            pass


# ============================================================
# 全局单例
# ============================================================

_default_cache_mgr = None


def get_scan_cache_manager() -> ScanCacheManager:
    """获取全局扫描缓存管理器单例"""
    global _default_cache_mgr
    if _default_cache_mgr is None:
        _default_cache_mgr = ScanCacheManager()
    return _default_cache_mgr
