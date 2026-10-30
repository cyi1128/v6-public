# -*- coding: utf-8 -*-
"""验证核心依据增强：新增真实数据字段"""
import os
import sys
import json

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PyQt6.QtCore import Qt, QCoreApplication
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.limit_up_reason_card import analyze_and_format
from ui.widgets.reason_card_widget import ReasonCardWidget


def test_enhanced_evidence():
    app = QApplication(sys.argv)

    print('=' * 70)
    print('核心依据增强验证 - 华森制药(002907)')
    print('=' * 70)

    # 分析华森制药
    print('\n[1] 分析华森制药...')
    card = analyze_and_format('002907', '华森制药', {
        'is_limit_up': True,
        'pct_chg': 10.02,
        'consecutive_days': 1,
        'industry': '中药II',
        'turnover_rate': 15.0,
        'amount': 500000000,
        'price': 25.50,
    })

    # 2. 验证股票基本信息
    print('\n[2] 股票基本信息')
    stock_info = card.get('stock_info', {})
    print(f"  行业: {stock_info.get('industry')}")
    print(f"  涨跌幅: {stock_info.get('pct_chg')}%")
    print(f"  换手率: {stock_info.get('turnover_rate')}%")
    print(f"  成交额: {stock_info.get('amount')}")
    print(f"  连板数: {stock_info.get('consecutive_days')}")
    print(f"  现价: {stock_info.get('price')}")
    assert stock_info.get('industry') == '中药II', "行业应正确"
    print('  ✅ 股票基本信息正确')

    # 3. 验证概念标签
    print('\n[3] 概念题材标签')
    concepts = card.get('concepts', [])
    concept_source = card.get('concept_source', '')
    print(f"  概念数量: {len(concepts)}")
    print(f"  概念列表: {concepts}")
    print(f"  数据来源: {concept_source}")
    assert len(concepts) > 0, "应至少有1个概念标签"
    print('  ✅ 概念标签获取成功')

    # 4. 验证新闻详情
    print('\n[4] 新闻详情')
    news = card.get('news', {})
    print(f"  有新闻: {news.get('has_news')}")
    print(f"  新闻标题: {news.get('title')}")
    print(f"  新闻来源: {news.get('source')}")
    print(f"  关键词: {news.get('keyword')}")
    if news.get('has_news'):
        assert news.get('title'), "有新闻时应有标题"
        print('  ✅ 新闻详情正确')
    else:
        print('  ℹ️  该股票暂无新闻')

    # 5. 验证详细依据
    print('\n[5] 详细依据')
    evidence_detail = card.get('evidence_detail', [])
    print(f"  详细依据数量: {len(evidence_detail)}")
    for i, ev in enumerate(evidence_detail[:5]):
        text = ev.get('text', '') if isinstance(ev, dict) else str(ev)
        print(f"  [{i}] {text[:80]}")
    assert len(evidence_detail) > 0, "应至少有1条详细依据"
    print('  ✅ 详细依据正确')

    # 6. 验证Widget渲染
    print('\n[6] Widget渲染测试')
    widget = ReasonCardWidget(card)
    widget.show()
    app.processEvents()

    # 检查各区域是否有内容
    assert widget.stock_info_label.text() != '', "股票信息栏不应为空"
    assert widget.concept_layout.count() > 0, "概念标签区域应有内容"
    assert widget.detail_layout.count() > 0, "详细依据区域应有内容"

    print(f"  股票信息栏: {widget.stock_info_label.text()[:60]}...")
    print(f"  概念标签区域: {widget.concept_layout.count()} 个布局项")
    print(f"  详细依据区域: {widget.detail_layout.count()} 个控件")
    print('  ✅ Widget渲染成功')

    # 7. 对比增强前后
    print('\n[7] 增强前后对比')
    print('  增强前核心依据: 3条（主营/公告/新闻），新闻只显示"存在新闻催化"')
    print('  增强后核心依据: 3条 + 新闻显示具体标题来源')
    print('  新增模块:')
    print('    - 股票基本信息栏（行业/涨幅/换手/成交额/连板）')
    print('    - 概念题材标签（彩色标签，数据来源标注）')
    print('    - 详细依据列表（engine evidence_list完整展示）')
    print('  ✅ 增强完成')

    print('\n' + '=' * 70)
    print('测试结果: ✅ 全部通过')
    print('=' * 70)

    return 0


if __name__ == '__main__':
    sys.exit(test_enhanced_evidence())
