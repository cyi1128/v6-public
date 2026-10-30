# -*- coding: utf-8 -*-
"""
V0.4.3.1 自选股AI跟踪数据层测试
不依赖quantbacktest，使用模拟决策数据验证跟踪逻辑。
"""
import sys
import os

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from watchlist import WatchlistTracker, WatchlistCache, TrackSnapshot, ChangeType


def test_basic_tracking():
    """测试基本跟踪功能"""
    print("=" * 50)
    print("测试1: 基本跟踪功能")
    print("=" * 50)

    # 使用临时缓存
    cache = WatchlistCache(cache_file=os.path.join(
        os.path.dirname(__file__), 'test_watchlist_cache.json'
    ))
    cache.clear()

    # 模拟自选股管理器
    class MockWatchlistManager:
        def __init__(self, stocks):
            self._stocks = stocks
        def get_all(self):
            return self._stocks

    stocks = [
        {'code': '000510', 'name': '新金路'},
        {'code': '600410', 'name': '华胜天成'},
        {'code': '000735', 'name': '罗牛山'},
    ]
    mgr = MockWatchlistManager(stocks)

    tracker = WatchlistTracker(watchlist_manager=mgr, cache=cache)

    # 模拟决策提供函数
    mock_decisions = {
        '000510': {'name': '新金路', 'score': 82, 'status': '重点关注',
                   'risk_level': '低风险', 'action': '等待回踩', 'data_date': '2026-08-15'},
        '600410': {'name': '华胜天成', 'score': 91, 'status': '确认买入',
                   'risk_level': '低风险', 'action': '关注买点', 'data_date': '2026-08-15'},
        '000735': {'name': '罗牛山', 'score': 75, 'status': '等待确认',
                   'risk_level': '中风险', 'action': '观察', 'data_date': '2026-08-15'},
    }

    def provider(code):
        return mock_decisions.get(code)

    # 第一次跟踪（全部为新增）
    count = tracker.track(decision_provider=provider)
    print(f"跟踪股票数: {count}")
    changes = tracker.get_changes()
    print(f"变化数量: {len(changes)}")
    for c in changes:
        print(f"  {c.format()}")

    assert count == 3, f"期望3只，实际{count}"
    assert len(changes) == 3, f"期望3个新增变化，实际{len(changes)}"
    assert all(c.change_type == ChangeType.NEW for c in changes), "第一次跟踪应全部为新增"
    print("  ✅ 第一次跟踪通过")

    # 第二次跟踪（模拟状态变化）
    mock_decisions['000510']['status'] = '确认买入'  # 升级
    mock_decisions['000510']['score'] = 93
    mock_decisions['000735']['status'] = '风险提醒'  # 下降
    mock_decisions['000735']['risk_level'] = '高风险'

    count = tracker.track(decision_provider=provider)
    changes = tracker.get_changes()
    print(f"\n第二次跟踪变化: {len(changes)}")
    for c in changes:
        print(f"  {c.format()}")

    upgrades = tracker.get_upgrades()
    downgrades = tracker.get_downgrades()
    print(f"  升级: {len(upgrades)}, 下降: {len(downgrades)}")

    assert len(upgrades) == 1, f"期望1个升级，实际{len(upgrades)}"
    assert upgrades[0].code == '000510', "升级应为000510"
    assert len(downgrades) >= 1, "至少1个下降"
    print("  ✅ 第二次跟踪通过")

    # 测试报告
    report = tracker.format_report()
    print("\n" + report)
    print("  ✅ 报告生成通过")

    # 清理
    cache.clear()
    print("\n测试1全部通过 ✅")


def test_score_change():
    """测试评分变化检测"""
    print("\n" + "=" * 50)
    print("测试2: 评分变化检测")
    print("=" * 50)

    cache = WatchlistCache(cache_file=os.path.join(
        os.path.dirname(__file__), 'test_score_cache.json'
    ))
    cache.clear()

    class MockMgr:
        def get_all(self):
            return [{'code': '000001', 'name': '平安银行'}]

    tracker = WatchlistTracker(watchlist_manager=MockMgr(), cache=cache)

    # 第一次
    decisions = {'000001': {'name': '平安银行', 'score': 70, 'status': '重点关注',
                            'risk_level': '低风险', 'action': '观察', 'data_date': '2026-08-15'}}
    tracker.track(decision_provider=lambda c: decisions.get(c))

    # 第二次：评分上升超过阈值
    decisions['000001']['score'] = 78  # +8
    tracker.track(decision_provider=lambda c: decisions.get(c))
    changes = tracker.get_changes()
    score_ups = [c for c in changes if c.change_type == ChangeType.SCORE_UP]
    print(f"评分上升变化: {len(score_ups)}")
    assert len(score_ups) == 1, "应检测到评分上升"
    print("  ✅ 评分上升检测通过")

    # 第三次：评分下降超过阈值
    decisions['000001']['score'] = 70  # -8
    tracker.track(decision_provider=lambda c: decisions.get(c))
    changes = tracker.get_changes()
    score_downs = [c for c in changes if c.change_type == ChangeType.SCORE_DOWN]
    print(f"评分下降变化: {len(score_downs)}")
    assert len(score_downs) == 1, "应检测到评分下降"
    print("  ✅ 评分下降检测通过")

    # 第四次：评分变化在阈值内
    decisions['000001']['score'] = 72  # +2，小于阈值
    tracker.track(decision_provider=lambda c: decisions.get(c))
    changes = tracker.get_changes()
    score_changes = [c for c in changes if c.change_type in (ChangeType.SCORE_UP, ChangeType.SCORE_DOWN)]
    print(f"阈值内评分变化: {len(score_changes)} (应为0)")
    assert len(score_changes) == 0, "阈值内不应检测到评分变化"
    print("  ✅ 阈值过滤通过")

    cache.clear()
    print("\n测试2全部通过 ✅")


def test_removed_stock():
    """测试自选股移除检测"""
    print("\n" + "=" * 50)
    print("测试3: 自选股移除检测")
    print("=" * 50)

    cache = WatchlistCache(cache_file=os.path.join(
        os.path.dirname(__file__), 'test_remove_cache.json'
    ))
    cache.clear()

    class MockMgr:
        def __init__(self):
            self.stocks = [
                {'code': '000001', 'name': '平安银行'},
                {'code': '000002', 'name': '万科A'},
            ]
        def get_all(self):
            return self.stocks

    mgr = MockMgr()
    tracker = WatchlistTracker(watchlist_manager=mgr, cache=cache)

    decisions = {
        '000001': {'name': '平安银行', 'score': 70, 'status': '重点关注',
                   'risk_level': '低风险', 'action': '观察', 'data_date': '2026-08-15'},
        '000002': {'name': '万科A', 'score': 65, 'status': '等待确认',
                   'risk_level': '中风险', 'action': '观察', 'data_date': '2026-08-15'},
    }

    # 第一次
    tracker.track(decision_provider=lambda c: decisions.get(c))
    print(f"初始自选股: {len(tracker.get_snapshots())} 只")

    # 移除一只
    mgr.stocks = [{'code': '000001', 'name': '平安银行'}]
    tracker.track(decision_provider=lambda c: decisions.get(c))
    changes = tracker.get_changes()
    removed = [c for c in changes if c.change_type == ChangeType.REMOVED]
    print(f"移除检测: {len(removed)} 只")
    assert len(removed) == 1, "应检测到1只移除"
    assert removed[0].code == '000002', "移除的应为000002"
    print(f"  {removed[0].format()}")
    print("  ✅ 移除检测通过")

    cache.clear()
    print("\n测试3全部通过 ✅")


if __name__ == '__main__':
    test_basic_tracking()
    test_score_change()
    test_removed_stock()
    print("\n" + "=" * 50)
    print("V0.4.3.1 自选股AI跟踪数据层 全部测试通过 ✅")
    print("=" * 50)
