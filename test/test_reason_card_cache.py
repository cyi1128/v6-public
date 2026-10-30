# -*- coding: utf-8 -*-
"""
V1.3-A-5-DEV Step2：原因卡片缓存功能测试
验证缓存的读写、命中、过期、清空等功能。
"""
import os
import sys
import time
import json
from datetime import datetime

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PyQt6.QtCore import Qt, QCoreApplication
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

from PyQt6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.cache.reason_card_cache import get_reason_card_cache, ReasonCardCache, CACHE_FILE
from test.mock_limit_up_data import generate_mock_card_data


def test_cache():
    app = QApplication(sys.argv)

    print('=' * 70)
    print('V1.3-A-5-DEV Step2：原因卡片缓存功能测试')
    print('=' * 70)

    all_passed = True

    # 获取缓存单例
    cache = get_reason_card_cache()

    # 1. 清空缓存，从头测试
    print('\n[1] 清空缓存')
    cache.clear()
    stats = cache.get_stats()
    assert stats['count'] == 0, f"缓存应为空，实际: {stats['count']}"
    print(f'  ✅ 缓存已清空，当前数量: {stats["count"]}')

    # 2. 测试写入缓存
    print('\n[2] 写入缓存测试')
    test_stocks = [
        ('000815', '美利云', '算力', 3),
        ('600666', '奥瑞德', '人工智能', 2),
        ('300615', '欣天科技', 'F5G', 1),
    ]

    for code, name, industry, lbc in test_stocks:
        card_data = generate_mock_card_data(code, name, industry, lbc)
        card_data['code'] = code
        card_data['name'] = name
        cache.set(code, name, card_data)

    stats = cache.get_stats()
    assert stats['count'] == 3, f"缓存数量应为3，实际: {stats['count']}"
    print(f'  ✅ 写入3只股票，当前缓存数量: {stats["count"]}')

    # 3. 测试缓存命中
    print('\n[3] 缓存命中测试')
    for code, name, _, _ in test_stocks:
        cached = cache.get(code)
        assert cached is not None, f"{code} 应命中缓存"
        assert cached.get('code') == code, f"缓存数据code不匹配"
        assert cached.get('name') == name, f"缓存数据name不匹配"
        print(f'  ✅ {name} ({code}) 缓存命中')

    # 4. 测试缓存未命中
    print('\n[4] 缓存未命中测试')
    not_cached = cache.get('999999')
    assert not_cached is None, "不存在的股票应返回None"
    print('  ✅ 不存在的股票返回None')

    # 5. 测试已缓存列表
    print('\n[5] 已缓存列表测试')
    cached_list = cache.get_cached_list()
    assert len(cached_list) == 3, f"缓存列表数量应为3，实际: {len(cached_list)}"
    for item in cached_list:
        print(f'  - {item["name"]} ({item["code"]}) {item["level"]}级 {item["score"]}分 @ {item["time"]}')
    print('  ✅ 已缓存列表正确')

    # 6. 测试磁盘持久化
    print('\n[6] 磁盘持久化测试')
    assert os.path.exists(CACHE_FILE), "缓存文件应存在"
    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        disk_data = json.load(f)
    assert disk_data['date'] == datetime.now().strftime('%Y-%m-%d'), "日期不匹配"
    assert len(disk_data['stocks']) == 3, f"磁盘缓存数量应为3，实际: {len(disk_data['stocks'])}"
    print(f'  ✅ 磁盘缓存文件存在，共 {len(disk_data["stocks"])} 条记录')
    print(f'     文件路径: {CACHE_FILE}')

    # 7. 测试跨日过期（模拟修改日期）
    print('\n[7] 跨日过期测试')
    # 手动修改缓存日期为昨天
    cache._cache_date = '2020-01-01'
    cached = cache.get('000815')
    assert cached is None, "过期缓存应返回None"
    assert cache.get_stats()['count'] == 0, "过期后缓存应被清空"
    print('  ✅ 跨日缓存自动失效并清空')

    # 8. 重新写入并验证
    print('\n[8] 重新写入验证')
    card_data = generate_mock_card_data('000815', '美利云', '算力', 3)
    card_data['code'] = '000815'
    card_data['name'] = '美利云'
    cache.set('000815', '美利云', card_data)
    cached = cache.get('000815')
    assert cached is not None, "重新写入后应命中"
    print(f'  ✅ 重新写入成功，当前缓存数量: {cache.get_stats()["count"]}')

    # 9. 测试单例模式
    print('\n[9] 单例模式测试')
    cache2 = get_reason_card_cache()
    assert cache is cache2, "应返回同一个实例"
    print('  ✅ 单例模式正常')

    # 10. 最终清空
    print('\n[10] 最终清空')
    cache.clear()
    assert cache.get_stats()['count'] == 0
    print('  ✅ 缓存已清空')

    print('\n' + '=' * 70)
    print('测试结果: ✅ 全部通过')
    print('=' * 70)

    return 0


if __name__ == '__main__':
    sys.exit(test_cache())
