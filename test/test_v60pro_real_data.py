# -*- coding: utf-8 -*-
"""V6.0 Pro 第三阶段 - 真实数据链路验收测试"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print('=' * 60)
print('V6.0 Pro 真实数据链路验收测试')
print('=' * 60)

# 测试股票
test_stocks = ['600519', '000001', '002579']
stock_names = {'600519': '贵州茅台', '000001': '平安银行', '002579': '中京电子'}

try:
    from utils.kline_provider import get_daily_kline
    from utils.indicators import (
        calc_ma_series, calc_kdj_series, calc_macd_series
    )

    all_pass = True

    for code in test_stocks:
        name = stock_names.get(code, code)
        print(f'\n{"-" * 50}')
        print(f'测试股票: {code} {name}')
        print(f'{"-" * 50}')

        # 1. 获取500根日K
        print(f'\n[1] 获取500根日K...')
        kline = get_daily_kline(code, count=500)
        if not kline:
            print(f'  ❌ K线数据为空')
            all_pass = False
            continue

        closes = kline.get('close', [])
        highs = kline.get('high', [])
        lows = kline.get('low', [])
        volumes = kline.get('volume', [])
        dates = kline.get('dates', [])

        print(f'  K线数量: {len(closes)}根')
        print(f'  日期范围: {dates[0] if dates else "?"} ~ {dates[-1] if dates else "?"}')
        print(f'  最新收盘: {closes[-1] if closes else "?"}')
        print(f'  最新成交量: {volumes[-1] if volumes else "?"}')

        if len(closes) < 200:
            print(f'  ⚠️ K线数量不足200根')
        else:
            print(f'  ✅ K线数据正常')

        # 2. MA均线计算
        print(f'\n[2] MA5/MA9/MA20计算...')
        import pandas as pd
        ma5 = calc_ma_series(closes, 5)
        ma9 = calc_ma_series(closes, 9)
        ma20 = calc_ma_series(closes, 20)

        # 转换为list并处理NaN
        def get_last(series):
            if series is None or len(series) == 0:
                return None
            val = series.iloc[-1] if hasattr(series, 'iloc') else series[-1]
            if pd.isna(val):
                return None
            return float(val)

        ma5_last = get_last(ma5)
        ma9_last = get_last(ma9)
        ma20_last = get_last(ma20)

        if ma5_last:
            print(f'  MA5: {ma5_last:.2f}')
        else:
            print(f'  ⚠️ MA5计算异常')

        if ma9_last:
            print(f'  MA9: {ma9_last:.2f}')
        else:
            print(f'  ⚠️ MA9计算异常')

        if ma20_last:
            print(f'  MA20: {ma20_last:.2f}')
        else:
            print(f'  ⚠️ MA20计算异常')

        # 验证MA逻辑
        if len(closes) >= 5 and ma5_last:
            expected_ma5 = sum(closes[-5:]) / 5
            if abs(expected_ma5 - ma5_last) < 0.01:
                print(f'  ✅ MA5计算正确 (验证: {expected_ma5:.2f} == {ma5_last:.2f})')
            else:
                print(f'  ❌ MA5计算错误 (期望: {expected_ma5:.2f}, 实际: {ma5_last:.2f})')
                all_pass = False

        # 3. KDJ(13,3,3)计算
        print(f'\n[3] KDJ(13,3,3)计算...')
        kdj_result = calc_kdj_series(highs, lows, closes, n=13, m1=3, m2=3)
        if kdj_result and len(kdj_result) >= 3:
            k_series, d_series, j_series = kdj_result
            k_val = get_last(k_series)
            d_val = get_last(d_series)
            j_val = get_last(j_series)
            print(f'  K: {k_val:.2f}')
            print(f'  D: {d_val:.2f}')
            print(f'  J: {j_val:.2f}')

            # KDJ状态判断
            if k_val > d_val:
                status = '金叉/多头'
            else:
                status = '死叉/空头'
            print(f'  状态: {status}')
            print(f'  ✅ KDJ计算正常')
        else:
            print(f'  ❌ KDJ计算失败')
            all_pass = False

        # 4. MACD(8,21,5)计算
        print(f'\n[4] MACD(8,21,5)计算...')
        macd_result = calc_macd_series(closes, fast=8, slow=21, signal=5)
        if macd_result and len(macd_result) >= 3:
            diff_series, dea_series, bar_series = macd_result
            diff_val = get_last(diff_series)
            dea_val = get_last(dea_series)
            bar_val = get_last(bar_series)
            print(f'  DIFF: {diff_val:.4f}')
            print(f'  DEA: {dea_val:.4f}')
            print(f'  MACD柱: {bar_val:.4f}')

            if diff_val > dea_val:
                status = '金叉/红柱'
            else:
                status = '死叉/绿柱'
            print(f'  状态: {status}')
            print(f'  ✅ MACD计算正常')
        else:
            print(f'  ❌ MACD计算失败')
            all_pass = False

        # 5. 成交量验证
        print(f'\n[5] 成交量验证...')
        if volumes and len(volumes) > 0:
            avg_vol = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else sum(volumes) / len(volumes)
            print(f'  最新成交量: {volumes[-1]:.0f}')
            print(f'  20日均量: {avg_vol:.0f}')
            print(f'  量比: {volumes[-1]/avg_vol:.2f}' if avg_vol > 0 else '  量比: N/A')
            print(f'  ✅ 成交量数据正常')
        else:
            print(f'  ❌ 成交量数据为空')
            all_pass = False

        # 6. 价格位置判断
        print(f'\n[6] 价格位置判断...')
        current_price = closes[-1] if closes else 0
        price_pos = []
        if ma5_last and current_price > ma5_last:
            price_pos.append('站上MA5')
        else:
            price_pos.append('跌破MA5')
        if ma9_last and current_price > ma9_last:
            price_pos.append('站上MA9')
        else:
            price_pos.append('跌破MA9')
        if ma20_last and current_price > ma20_last:
            price_pos.append('站上MA20')
        else:
            price_pos.append('跌破MA20')
        print(f'  当前价: {current_price:.2f}')
        print(f'  位置: {" | ".join(price_pos)}')

    print(f'\n{"=" * 60}')
    if all_pass:
        print('✅ 全部测试通过，真实数据链路正常')
    else:
        print('⚠️ 部分测试未通过，需要检查')
    print('=' * 60)

except Exception as e:
    print(f'\n❌ 测试异常: {e}')
    import traceback
    traceback.print_exc()
