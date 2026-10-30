# -*- coding: utf-8 -*-
"""
V6.0 Pro 全市场扫描结果验收脚本
验证筛选条件是否真实生效
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

print('=' * 70)
print('V6.0 Pro 全市场扫描结果验收')
print(f'验收时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
print('=' * 70)

# ===== 第一步：获取全市场行情 =====
print('\n[1/6] 获取全市场行情...')
from utils.tdx_stock_list import get_full_market_quotes, enrich_finance_info

all_stocks = get_full_market_quotes()
print(f'  全市场股票总数: {len(all_stocks)}')

if not all_stocks:
    print('❌ 获取全市场行情失败')
    sys.exit(1)

# ===== 第二步：价格+主板+ST初步过滤 =====
print('\n[2/6] 价格+主板+ST初步过滤...')
from strategy.pro_stock_pool_filter import ProStockPoolFilter
pool_filter = ProStockPoolFilter()

pre_filtered = []
for s in all_stocks:
    code = s.get('code', '')
    name = s.get('name', '')
    price = s.get('price', 0)

    # ST过滤
    if 'ST' in name or 'st' in name.lower() or '*ST' in name:
        continue
    # 主板过滤
    if not (code.startswith('60') or code.startswith('00')):
        continue
    # 价格过滤
    if price < pool_filter.MIN_PRICE or price > pool_filter.MAX_PRICE:
        continue

    pre_filtered.append(s)

print(f'  初步过滤后数量: {len(pre_filtered)}')
print(f'  过滤掉: {len(all_stocks) - len(pre_filtered)}只')

# ===== 第三步：获取财务信息 =====
print(f'\n[3/6] 获取{len(pre_filtered)}只股票的财务信息（可能需要几分钟）...')
enriched = enrich_finance_info(pre_filtered)
print(f'  财务信息获取完成: {len(enriched)}只')

# ===== 第四步：市值+行业过滤 =====
print('\n[4/6] 市值+行业过滤...')
final_candidates = []
for s in enriched:
    market_cap = s.get('market_cap', 0)
    industry = s.get('industry', '')

    # 市值过滤
    if market_cap <= pool_filter.MIN_MARKET_CAP or market_cap > pool_filter.MAX_MARKET_CAP:
        continue
    # 行业过滤
    skip = False
    for excl in pool_filter.EXCLUDE_INDUSTRIES:
        if excl in industry:
            skip = True
            break
    if skip:
        continue

    final_candidates.append(s)

print(f'  市值+行业过滤后: {len(final_candidates)}只')

# ===== 第五步：验收检查 =====
print('\n' + '=' * 70)
print('验收检查')
print('=' * 70)

# 5.1 主板检查
print('\n【1. 主板检查】')
allowed_prefixes = ('600', '601', '603', '605', '000', '001', '002', '003')
forbidden_prefixes = ('300', '301', '688', '689', '8', '4', '9')
board_pass = True
board_violations = []
for s in final_candidates:
    code = s.get('code', '')
    if not code.startswith(allowed_prefixes):
        board_pass = False
        board_violations.append(f"{code} {s.get('name','')}")

if board_pass:
    print(f'  ✅ 通过 - 全部{len(final_candidates)}只均为主板股票')
else:
    print(f'  ❌ 失败 - 发现{len(board_violations)}只非主板股票:')
    for v in board_violations[:10]:
        print(f'    - {v}')

# 5.2 ST检查
print('\n【2. ST检查】')
st_pass = True
st_violations = []
for s in final_candidates:
    name = s.get('name', '')
    if 'ST' in name or 'st' in name.lower() or '*ST' in name or '退' in name:
        st_pass = False
        st_violations.append(f"{s.get('code','')} {name}")

if st_pass:
    print(f'  ✅ 通过 - 全部{len(final_candidates)}只均无ST/退市')
else:
    print(f'  ❌ 失败 - 发现{len(st_violations)}只ST/退市股票:')
    for v in st_violations[:10]:
        print(f'    - {v}')

# 5.3 价格检查
print('\n【3. 价格检查（全部股票）】')
price_pass = True
price_violations = []
prices = [s.get('price', 0) for s in final_candidates]
for s in final_candidates:
    price = s.get('price', 0)
    if price < pool_filter.MIN_PRICE or price > pool_filter.MAX_PRICE:
        price_pass = False
        price_violations.append(f"{s.get('code','')} {s.get('name','')} 价格={price}")

print(f'  价格范围: {min(prices):.2f} ~ {max(prices):.2f}')
print(f'  要求: {pool_filter.MIN_PRICE}元 < 价格 ≤ {pool_filter.MAX_PRICE}元')
if price_pass:
    print(f'  ✅ 通过 - 全部符合价格区间')
else:
    print(f'  ❌ 失败 - 发现{len(price_violations)}只价格异常:')
    for v in price_violations[:10]:
        print(f'    - {v}')

# 5.4 市值检查
print('\n【4. 市值检查（全部股票）】')
cap_pass = True
cap_violations = []
caps = [s.get('market_cap', 0) for s in final_candidates if s.get('market_cap', 0) > 0]
for s in final_candidates:
    cap = s.get('market_cap', 0)
    if cap <= pool_filter.MIN_MARKET_CAP or cap > pool_filter.MAX_MARKET_CAP:
        cap_pass = False
        cap_violations.append(f"{s.get('code','')} {s.get('name','')} 市值={cap}亿")

print(f'  市值范围: {min(caps):.1f}亿 ~ {max(caps):.1f}亿')
print(f'  要求: {pool_filter.MIN_MARKET_CAP}亿 < 市值 ≤ {pool_filter.MAX_MARKET_CAP}亿')
if cap_pass:
    print(f'  ✅ 通过 - 全部符合市值区间')
else:
    print(f'  ❌ 失败 - 发现{len(cap_violations)}只市值异常:')
    for v in cap_violations[:10]:
        print(f'    - {v}')

# 5.5 行业检查
print('\n【5. 行业检查（全部股票）】')
industry_pass = True
industry_violations = []
industries = set()
for s in final_candidates:
    industry = s.get('industry', '')
    industries.add(industry)
    for excl in pool_filter.EXCLUDE_INDUSTRIES:
        if excl in industry:
            industry_pass = False
            industry_violations.append(f"{s.get('code','')} {s.get('name','')} 行业={industry}")

print(f'  排除行业: {pool_filter.EXCLUDE_INDUSTRIES}')
print(f'  实际行业分布: {len(industries)}个行业')
for ind in sorted(industries):
    count = sum(1 for s in final_candidates if s.get('industry','') == ind)
    print(f'    {ind}: {count}只')
if industry_pass:
    print(f'  ✅ 通过 - 无排除行业')
else:
    print(f'  ❌ 失败 - 发现{len(industry_violations)}只排除行业:')
    for v in industry_violations[:10]:
        print(f'    - {v}')

# ===== 第六步：K线条件抽查 =====
print('\n' + '=' * 70)
print('【6. K线条件抽查（随机10只）】')
print('=' * 70)

from utils.kline_provider import get_daily_kline
import random

sample_size = min(10, len(final_candidates))
samples = random.sample(final_candidates, sample_size)

kline_pass_count = 0
kline_fail_count = 0

for s in samples:
    code = s.get('code', '')
    name = s.get('name', '')
    price = s.get('price', 0)
    print(f'\n  抽查: {code} {name} 现价={price:.2f}')

    kline = get_daily_kline(code)
    if not kline:
        print(f'    ❌ K线获取失败')
        kline_fail_count += 1
        continue

    highs = kline.get('high', [])
    closes = kline.get('close', [])
    if len(highs) < 30:
        print(f'    ❌ K线数据不足({len(highs)}根)')
        kline_fail_count += 1
        continue

    # 8个月高点
    recent_highs = highs[-pool_filter.HIGH_PERIOD_DAYS:] if len(highs) >= pool_filter.HIGH_PERIOD_DAYS else highs
    high_8m = max(recent_highs)
    ratio = price / high_8m if high_8m > 0 else 0

    # 涨停次数（近一年约250交易日）
    limit_up_count = 0
    check_days = min(250, len(closes) - 1)
    for i in range(len(closes) - check_days, len(closes)):
        if i > 0 and closes[i-1] > 0:
            pct = (closes[i] - closes[i-1]) / closes[i-1] * 100
            if pct >= 9.8:  # 涨停阈值
                limit_up_count += 1

    # 前一日是否涨停
    prev_limit_up = False
    if len(closes) >= 2 and closes[-2] > 0:
        prev_pct = (closes[-1] - closes[-2]) / closes[-2] * 100
        prev_limit_up = prev_pct >= 9.8

    print(f'    8个月高点: {high_8m:.2f}, 当前/高点: {ratio:.2%} (要求70%-105%)')
    print(f'    近一年涨停: {limit_up_count}次 (要求≥3次)')
    print(f'    前一日涨停: {"是" if prev_limit_up else "否"} (要求否)')

    cond1 = pool_filter.PRICE_RATIO_LOW <= ratio <= pool_filter.PRICE_RATIO_HIGH
    cond2 = limit_up_count >= pool_filter.MIN_LIMIT_UP_COUNT
    cond3 = not prev_limit_up

    if cond1 and cond2 and cond3:
        print(f'    ✅ K线条件通过')
        kline_pass_count += 1
    else:
        print(f'    ❌ K线条件失败: 高点比={cond1}, 涨停数={cond2}, 前日未涨停={cond3}')
        kline_fail_count += 1

print(f'\n  K线抽查结果: {kline_pass_count}通过 / {kline_fail_count}失败 / 共{sample_size}只')

# ===== 验收总结 =====
print('\n' + '=' * 70)
print('验收总结')
print('=' * 70)
print(f'  全市场总数: {len(all_stocks)}只')
print(f'  初步过滤后: {len(pre_filtered)}只 (价格+主板+ST)')
print(f'  财务获取后: {len(enriched)}只')
print(f'  最终候选: {len(final_candidates)}只 (市值+行业过滤)')
print()
print(f'  主板检查: {"✅ 通过" if board_pass else "❌ 失败"}')
print(f'  ST检查: {"✅ 通过" if st_pass else "❌ 失败"}')
print(f'  价格检查: {"✅ 通过" if price_pass else "❌ 失败"}')
print(f'  市值检查: {"✅ 通过" if cap_pass else "❌ 失败"}')
print(f'  行业检查: {"✅ 通过" if industry_pass else "❌ 失败"}')
print(f'  K线抽查: {kline_pass_count}/{sample_size}通过')

all_pass = board_pass and st_pass and price_pass and cap_pass and industry_pass
print()
if all_pass:
    print('🎉 V6.0 Pro股票池策略验收通过')
else:
    print('⚠️ 部分检查未通过，需要修复')
print('=' * 70)
