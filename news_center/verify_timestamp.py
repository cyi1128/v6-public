# -*- coding: utf-8 -*-
"""
验证脚本：调用 get_multi_source_manager().fetch_all(limit=50)
打印前20条新闻的 title 和 publish_time
确认：时间格式统一、无统一00:00、无错误日期、按时间倒序
"""
import sys
import os
import re
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from news_center.news_sources import get_multi_source_manager

def main():
    print(f"验证开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    manager = get_multi_source_manager()
    all_news = manager.fetch_all(limit=50)

    print(f"\n共获取 {len(all_news)} 条新闻")
    print("=" * 80)

    # 打印前20条
    print("\n【前20条新闻抽查】")
    print(f"{'序号':<4} {'发布时间':<18} {'来源':<10} {'标题'}")
    print("-" * 100)
    for i, news in enumerate(all_news[:20], 1):
        pt = news.get('publish_time', '')
        src = news.get('source_tag', news.get('source', ''))
        title = news.get('title', '')[:50]
        print(f"{i:<4} {pt:<18} {src:<10} {title}")

    # 验证检查
    print("\n" + "=" * 80)
    print("【验证检查】")

    # 1. 时间格式检查
    time_pattern = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$')
    bad_format = []
    for i, news in enumerate(all_news):
        pt = news.get('publish_time', '')
        if not time_pattern.match(pt):
            bad_format.append((i, pt, news.get('title', '')[:30]))
    if bad_format:
        print(f"[FAIL] 时间格式不统一: {len(bad_format)} 条")
        for idx, pt, title in bad_format[:5]:
            print(f"  #{idx}: {repr(pt)} - {title}")
    else:
        print(f"[PASS] 所有 {len(all_news)} 条新闻时间格式均为 YYYY-MM-DD HH:MM")

    # 2. 统一00:00检查
    zero_count = sum(1 for n in all_news if n.get('publish_time', '').endswith('00:00'))
    if zero_count > 0:
        print(f"[WARN] {zero_count}/{len(all_news)} 条新闻时间为00:00（可能为日期级数据）")
        # 打印这些新闻
        for i, news in enumerate(all_news):
            if news.get('publish_time', '').endswith('00:00'):
                print(f"  #{i+1}: {news['publish_time']} [{news.get('source_tag','')}] {news.get('title','')[:40]}")
                if i >= 9:
                    print(f"  ... 共 {zero_count} 条")
                    break
    else:
        print("[PASS] 无统一00:00的新闻")

    # 3. 错误日期检查（年份不在2020-2030）
    bad_year = []
    for i, news in enumerate(all_news):
        pt = news.get('publish_time', '')
        try:
            dt = datetime.strptime(pt, '%Y-%m-%d %H:%M')
            if dt.year < 2020 or dt.year > 2030:
                bad_year.append((i, pt, news.get('title', '')[:30]))
        except Exception:
            bad_year.append((i, pt, news.get('title', '')[:30]))
    if bad_year:
        print(f"[FAIL] 错误日期: {len(bad_year)} 条")
    else:
        print("[PASS] 所有新闻年份在2020-2030范围内")

    # 4. 倒序排列检查
    sorted_ok = True
    for i in range(len(all_news) - 1):
        pt1 = all_news[i].get('publish_time', '')
        pt2 = all_news[i + 1].get('publish_time', '')
        try:
            dt1 = datetime.strptime(pt1, '%Y-%m-%d %H:%M')
            dt2 = datetime.strptime(pt2, '%Y-%m-%d %H:%M')
            if dt1 < dt2:
                sorted_ok = False
                print(f"[FAIL] 排序错误: #{i+1} {pt1} < #{i+2} {pt2}")
                break
        except Exception:
            pass
    if sorted_ok:
        print("[PASS] 新闻按发布时间倒序排列")

    # 5. 各源统计
    print("\n【各数据源统计】")
    source_stats = {}
    for news in all_news:
        src = news.get('source_tag', news.get('source', 'unknown'))
        source_stats[src] = source_stats.get(src, 0) + 1
    for src, cnt in sorted(source_stats.items(), key=lambda x: -x[1]):
        print(f"  {src}: {cnt} 条")

    print("\n" + "=" * 80)
    print("验证完成")

if __name__ == '__main__':
    main()
