# -*- coding: utf-8 -*-
"""
把Markdown文本渲染成长图，用于企业微信推送
"""
import os
import sys
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def markdown_to_image(markdown_text: str, save_path: str = None) -> str:
    """
    把Markdown文本渲染成长图
    返回图片文件路径
    """
    import markdown as md
    from playwright.sync_api import sync_playwright

    # 转HTML
    html_body = md.markdown(markdown_text, extensions=['tables', 'fenced_code'])

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
    background: #ffffff;
    color: #1a1a1a;
    max-width: 720px;
    margin: 0 auto;
    padding: 20px;
    line-height: 1.7;
    font-size: 15px;
}}
h1 {{ font-size: 22px; color: #1a1a1a; border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; }}
h2 {{ font-size: 18px; color: #dc2626; margin-top: 20px; }}
h3 {{ font-size: 16px; color: #2563eb; margin-top: 16px; }}
strong {{ color: #dc2626; }}
hr {{ border: none; border-top: 1px solid #e5e7eb; margin: 16px 0; }}
code {{ background: #f3f4f6; padding: 2px 6px; border-radius: 3px; font-size: 13px; }}
blockquote {{ border-left: 3px solid #dc2626; margin: 8px 0; padding: 4px 12px; background: #fef2f2; }}
</style></head>
<body>{html_body}</body></html>"""

    if not save_path:
        save_path = os.path.join(PROJECT_ROOT, 'data', 'tmp_digest.png')

    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 760, 'height': 800})
        page.set_content(html)
        # 等渲染完
        page.wait_for_timeout(500)
        # 截全页长图
        page.screenshot(path=save_path, full_page=True)
        browser.close()

    return save_path


if __name__ == '__main__':
    # 测试
    test_md = """【AI股票30分钟新闻简报】
时间：测试推送

🔥 重要事件
**800G光模块需求爆发**

白话解释：AI服务器需求带动800G光模块订单翻倍

🎯 利好股票
- **中际旭创(300308)**：全球光模块龙头
- 新易盛(300502)：800G核心供应商

📊 题材变化
光模块 ↑↑
CPO ↑
"""
    path = markdown_to_image(test_md)
    print(f"图片已生成: {path}")

    # 测试推送
    from services.wechat_push import get_wechat_push_service
    svc = get_wechat_push_service()
    ok = svc.send_image(path) if hasattr(svc, 'send_image') else None
    print(f"推送结果: {ok}")
