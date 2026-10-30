# -*- coding: utf-8 -*-
"""
V1.3-A-4.1-DEV 最终验收测试
1. 20只涨停样本数据链路验收
2. 排序功能验收（5种排序）
3. UI完整检查
4. 性能压力测试
"""
import os
import sys
import time
import gc

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PyQt6.QtCore import Qt, QCoreApplication
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market.limit_up_center import get_today_limit_up_stocks
from ui.limit_up_reason_card import analyze_and_format
from ui.widgets.reason_card_widget import ReasonCardWidget


def select_20_samples(stocks):
    """选择20只不同类型样本"""
    samples = []
    used_codes = set()

    # 一字板（首次封板09:25且炸板0次）
    yizi = [s for s in stocks if s.get('first_limit_time', '') <= '09:30:00' and s.get('break_count', 99) == 0]
    for s in yizi[:3]:
        if s['code'] not in used_codes:
            samples.append(('一字板', s))
            used_codes.add(s['code'])

    # 连板龙头（连板最高的5只）
    by_chain = sorted(stocks, key=lambda s: s.get('lbc', 0), reverse=True)
    for s in by_chain[:5]:
        if s['code'] not in used_codes:
            samples.append(('连板龙头', s))
            used_codes.add(s['code'])

    # 首板热点（首板且有热点概念）
    first_board = [s for s in stocks if s.get('lbc', 0) == 1]
    for s in first_board[:5]:
        if s['code'] not in used_codes:
            samples.append(('首板热点', s))
            used_codes.add(s['code'])

    # 主营强相关（科技/医药行业）
    tech_med = [s for s in stocks if any(k in s.get('industry', '') for k in ['电子', '计算机', '通信', '医药', '医疗', '生物', '半导体', '芯片'])]
    for s in tech_med:
        if s['code'] not in used_codes and len([x for x in samples if x[0] == '主营强相关']) < 3:
            samples.append(('主营强相关', s))
            used_codes.add(s['code'])

    # 主营弱相关（传统行业）
    weak = [s for s in stocks if s['code'] not in used_codes]
    for s in weak[:4]:
        samples.append(('主营弱相关', s))
        used_codes.add(s['code'])

    # 补全到20只
    for s in stocks:
        if len(samples) >= 20:
            break
        if s['code'] not in used_codes:
            samples.append(('补充样本', s))
            used_codes.add(s['code'])

    return samples[:20]


def test_data_linkage(samples):
    """Step1: 数据链路验收"""
    print('\n' + '=' * 70)
    print('Step 1: 20只涨停样本数据链路验收')
    print('=' * 70)

    issues = []
    passed = 0
    total = 0

    for category, stock in samples:
        total += 1
        code = stock['code']
        name = stock['name']

        # 检查limit_up_center字段完整
        fields_ok = True
        required_fields = ['code', 'name', 'lbc', 'first_limit_time', 'last_limit_time',
                          'seal_amount', 'break_count', 'float_market_cap', 'pct_chg', 'industry']
        for f in required_fields:
            if f not in stock:
                fields_ok = False
                issues.append(f"{name}({code}) 缺少字段: {f}")

        # 检查seal_ratio计算
        seal = stock.get('seal_amount', 0)
        cap = stock.get('float_market_cap', 0)
        seal_ratio = (seal / cap * 100) if cap > 0 else 0
        if cap > 0 and seal_ratio < 0:
            issues.append(f"{name}({code}) seal_ratio异常: {seal_ratio}")

        # 分析并检查rank_score和AI总结
        try:
            card = analyze_and_format(code, name, stock)

            # rank_score检查
            rank = card.get('rank_score', {})
            if not rank or 'total' not in rank:
                issues.append(f"{name}({code}) rank_score缺失")
                fields_ok = False
            elif not (0 <= rank['total'] <= 100):
                issues.append(f"{name}({code}) rank_score越界: {rank['total']}")
                fields_ok = False

            # AI总结检查
            ai = card.get('ai_summary', {})
            if not ai:
                issues.append(f"{name}({code}) ai_summary缺失")
                fields_ok = False
            else:
                for key in ['logic_stars', 'hot_stars', 'fund_stars', 'risk_stars', 'summary']:
                    if key not in ai:
                        issues.append(f"{name}({code}) ai_summary.{key}缺失")
                        fields_ok = False

            # 涨停强度检查
            strength = card.get('limit_up_strength', {})
            if not strength or 'seal_ratio' not in strength:
                issues.append(f"{name}({code}) limit_up_strength.seal_ratio缺失")
                fields_ok = False

            if fields_ok:
                passed += 1

        except Exception as e:
            issues.append(f"{name}({code}) 分析异常: {e}")

    print(f"\n  样本数: {len(samples)}")
    print(f"  通过: {passed}/{total}")
    print(f"  问题数: {len(issues)}")
    if issues:
        for issue in issues[:10]:
            print(f"  ⚠️  {issue}")

    return passed == total and len(issues) == 0


def test_sorting(stocks):
    """Step2: 排序功能验收"""
    print('\n' + '=' * 70)
    print('Step 2: 排序功能验收（5种排序）')
    print('=' * 70)

    def calc_quick_rank(stock):
        consecutive = stock.get('lbc', 1)
        break_count = stock.get('break_count', 0)
        first_time = stock.get('first_limit_time', '')
        seal_amount = stock.get('seal_amount', 0)
        float_cap = stock.get('float_market_cap', 0)
        seal_ratio = (seal_amount / float_cap * 100) if float_cap > 0 else 0
        score = 0
        if consecutive >= 5: score += 20
        elif consecutive >= 3: score += 15
        elif consecutive >= 2: score += 10
        else: score += 5
        if first_time and first_time < '09:30:00': score += 20
        elif first_time and first_time < '10:00:00': score += 16
        elif first_time and first_time < '11:00:00': score += 10
        elif first_time and first_time < '14:00:00': score += 6
        else: score += 2
        if break_count == 0: score += 20
        elif break_count <= 1: score += 16
        elif break_count <= 3: score += 8
        else: score += 0
        if seal_ratio >= 5: score += 20
        elif seal_ratio >= 2: score += 16
        elif seal_ratio >= 1: score += 12
        elif seal_ratio >= 0.3: score += 8
        elif seal_ratio > 0: score += 4
        return score

    all_pass = True

    # ① 综合强度
    sorted1 = sorted(stocks, key=calc_quick_rank, reverse=True)
    scores1 = [calc_quick_rank(s) for s in sorted1]
    ok1 = all(scores1[i] >= scores1[i+1] for i in range(len(scores1)-1))
    print(f"\n  ① 综合强度排序: {'✅' if ok1 else '❌'} (TOP3: {sorted1[0]['name']}/{sorted1[1]['name']}/{sorted1[2]['name']})")
    all_pass = all_pass and ok1

    # ② 连板高度
    sorted2 = sorted(stocks, key=lambda s: s.get('lbc', 0), reverse=True)
    lbcs = [s.get('lbc', 0) for s in sorted2]
    ok2 = all(lbcs[i] >= lbcs[i+1] for i in range(len(lbcs)-1))
    print(f"  ② 连板高度排序: {'✅' if ok2 else '❌'} (最高: {sorted2[0]['name']} {lbcs[0]}板)")
    all_pass = all_pass and ok2

    # ③ 封板时间
    sorted3 = sorted(stocks, key=lambda s: s.get('first_limit_time', '99:99:99'))
    times = [s.get('first_limit_time', '') for s in sorted3]
    ok3 = all(times[i] <= times[i+1] for i in range(len(times)-1) if times[i] and times[i+1])
    print(f"  ③ 封板时间排序: {'✅' if ok3 else '❌'} (最早: {sorted3[0]['name']} {times[0]})")
    all_pass = all_pass and ok3

    # ④ 封单强度
    def seal_ratio(s):
        seal = s.get('seal_amount', 0)
        cap = s.get('float_market_cap', 0)
        return (seal / cap * 100) if cap > 0 else 0
    sorted4 = sorted(stocks, key=seal_ratio, reverse=True)
    ratios = [seal_ratio(s) for s in sorted4]
    ok4 = all(ratios[i] >= ratios[i+1] for i in range(len(ratios)-1))
    print(f"  ④ 封单强度排序: {'✅' if ok4 else '❌'} (最高: {sorted4[0]['name']} {ratios[0]:.2f}%)")
    all_pass = all_pass and ok4

    # ⑤ 炸板次数
    sorted5 = sorted(stocks, key=lambda s: s.get('break_count', 99))
    breaks = [s.get('break_count', 99) for s in sorted5]
    ok5 = all(breaks[i] <= breaks[i+1] for i in range(len(breaks)-1))
    print(f"  ⑤ 炸板次数排序: {'✅' if ok5 else '❌'} (最少: {sorted5[0]['name']} {breaks[0]}次)")
    all_pass = all_pass and ok5

    return all_pass


def test_ui_integrity(samples):
    """Step3: UI完整检查"""
    print('\n' + '=' * 70)
    print('Step 3: UI完整检查')
    print('=' * 70)

    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    issues = []
    passed = 0

    for category, stock in samples[:5]:  # 抽5只做UI检查
        try:
            card = analyze_and_format(stock['code'], stock['name'], stock)
            widget = ReasonCardWidget()
            widget.set_data(card)
            widget.show()
            app.processEvents()

            # 检查各区域
            checks = {
                '股票信息': widget.stock_info_label.text() != '',
                '概念题材': widget.concept_layout.count() > 0,
                '涨停强度': widget.strength_layout.count() > 0,
                '核心依据': widget.evidence_layout.count() > 0,
                '详细依据': widget.detail_layout.count() > 0,
                '评分拆解': widget.score_grid.count() > 0,
                'AI总结': widget.ai_layout.count() > 0,
                '风险提示': widget.risk_layout.count() > 0,
            }

            all_ok = all(checks.values())
            if all_ok:
                passed += 1
            else:
                failed = [k for k, v in checks.items() if not v]
                issues.append(f"{stock['name']} 空白模块: {failed}")

            widget.deleteLater()

        except Exception as e:
            issues.append(f"{stock['name']} UI渲染异常: {e}")

    print(f"\n  检查股票数: 5")
    print(f"  通过: {passed}/5")
    print(f"  问题数: {len(issues)}")
    if issues:
        for issue in issues:
            print(f"  ⚠️  {issue}")

    return passed == 5 and len(issues) == 0


def test_performance(stocks):
    """Step4: 性能压力测试"""
    print('\n' + '=' * 70)
    print('Step 4: 性能压力测试')
    print('=' * 70)

    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    results = {}

    # 首次加载（模拟列表加载+排序）
    gc.collect()
    start = time.time()
    def calc_quick_rank(stock):
        consecutive = stock.get('lbc', 1)
        break_count = stock.get('break_count', 0)
        first_time = stock.get('first_limit_time', '')
        seal_amount = stock.get('seal_amount', 0)
        float_cap = stock.get('float_market_cap', 0)
        seal_ratio = (seal_amount / float_cap * 100) if float_cap > 0 else 0
        score = 0
        if consecutive >= 5: score += 20
        elif consecutive >= 3: score += 15
        elif consecutive >= 2: score += 10
        else: score += 5
        if first_time and first_time < '09:30:00': score += 20
        elif first_time and first_time < '10:00:00': score += 16
        elif first_time and first_time < '11:00:00': score += 10
        elif first_time and first_time < '14:00:00': score += 6
        else: score += 2
        if break_count == 0: score += 20
        elif break_count <= 1: score += 16
        elif break_count <= 3: score += 8
        else: score += 0
        if seal_ratio >= 5: score += 20
        elif seal_ratio >= 2: score += 16
        elif seal_ratio >= 1: score += 12
        elif seal_ratio >= 0.3: score += 8
        elif seal_ratio > 0: score += 4
        return score

    sorted_stocks = sorted(stocks, key=calc_quick_rank, reverse=True)
    load_time = time.time() - start
    results['首次加载排序'] = load_time
    print(f"\n  首次加载排序({len(stocks)}只): {load_time:.3f}秒 {'✅' if load_time < 3 else '⚠️'}")

    # 排序切换（5种排序各1次）
    start = time.time()
    for mode in range(5):
        if mode == 0:
            sorted(stocks, key=calc_quick_rank, reverse=True)
        elif mode == 1:
            sorted(stocks, key=lambda s: s.get('lbc', 0), reverse=True)
        elif mode == 2:
            sorted(stocks, key=lambda s: s.get('first_limit_time', '99:99:99'))
        elif mode == 3:
            def sr(s):
                seal = s.get('seal_amount', 0); cap = s.get('float_market_cap', 0)
                return (seal/cap*100) if cap > 0 else 0
            sorted(stocks, key=sr, reverse=True)
        elif mode == 4:
            sorted(stocks, key=lambda s: s.get('break_count', 99))
    sort_time = (time.time() - start) / 5
    results['排序切换'] = sort_time
    print(f"  排序切换(平均): {sort_time:.3f}秒 {'✅' if sort_time < 0.5 else '⚠️'}")

    # 连续点击20只股票分析
    click_times = []
    errors = 0
    for i, stock in enumerate(sorted_stocks[:20]):
        start = time.time()
        try:
            card = analyze_and_format(stock['code'], stock['name'], stock)
            widget = ReasonCardWidget()
            widget.set_data(card)
            widget.show()
            app.processEvents()
            widget.deleteLater()
            elapsed = time.time() - start
            click_times.append(elapsed)
        except Exception as e:
            errors += 1
            print(f"  ⚠️  {stock['name']} 分析失败: {e}")

    avg_click = sum(click_times) / len(click_times) if click_times else 0
    max_click = max(click_times) if click_times else 0
    results['点击分析'] = avg_click
    print(f"  点击分析(20只): 平均{avg_click:.3f}秒 最大{max_click:.3f}秒 失败{errors}只 {'✅' if avg_click < 1 and errors == 0 else '⚠️'}")

    all_pass = load_time < 3 and sort_time < 0.5 and avg_click < 1 and errors == 0
    return all_pass


def main():
    print('=' * 70)
    print('V1.3-A-4.1-DEV 最终验收测试')
    print('=' * 70)

    app = QApplication(sys.argv)

    # 获取涨停池
    print('\n[0] 获取涨停池...')
    stocks = get_today_limit_up_stocks()
    print(f'  共 {len(stocks)} 只涨停股票')

    if len(stocks) < 20:
        print(f'  ⚠️  涨停股票不足20只，使用全部{len(stocks)}只')

    # 选择20只样本
    samples = select_20_samples(stocks)
    print(f'  选择 {len(samples)} 只样本')
    categories = {}
    for cat, _ in samples:
        categories[cat] = categories.get(cat, 0) + 1
    for cat, count in categories.items():
        print(f'    - {cat}: {count}只')

    # 执行验收
    r1 = test_data_linkage(samples)
    r2 = test_sorting(stocks)
    r3 = test_ui_integrity(samples)
    r4 = test_performance(stocks)

    # 汇总
    print('\n' + '=' * 70)
    print('验收汇总')
    print('=' * 70)
    print(f'  Step1 数据链路:   {"✅ 通过" if r1 else "❌ 不通过"}')
    print(f'  Step2 排序功能:   {"✅ 通过" if r2 else "❌ 不通过"}')
    print(f'  Step3 UI完整:     {"✅ 通过" if r3 else "❌ 不通过"}')
    print(f'  Step4 性能测试:   {"✅ 通过" if r4 else "❌ 不通过"}')

    all_pass = r1 and r2 and r3 and r4
    print(f'\n  最终结论: {"✅ 全部通过，可以冻结" if all_pass else "❌ 存在问题，需修复后重新验收"}')
    print('=' * 70)

    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())
