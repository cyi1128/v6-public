# -*- coding: utf-8 -*-
"""用 GBK 重写 bat：cmd.exe 原生代码页，避免 UTF-8 中文在批处理里被误解析
（症状：屏幕上蹦出 'xxx' is not recognized as an internal or external command）。"""
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"D:\QuantMonitorV6" + os.sep

bat = """@echo off
cd /d D:\\QuantMonitorV6
set "PY=C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python314\\python.exe"
echo ==========================================================
echo   灌入创业板(300/301)日K线到本地缓存
echo.
echo   作用：让全市场扫描、控盘度、K线读取走本地缓存
echo         不走在线接口，速度快十几倍
echo.
echo   ！！运行前请先关闭 QuantMonitorV6 主程序 ！！
echo      程序开着时数据库被占用，脚本会拒绝运行
echo.
echo   首次约 10-30 分钟；之后重复运行只补漏，很快
echo ==========================================================
echo.
pause
echo.
"%PY%" -X utf8 tools\\seed_cyb_kline.py --workers 10
echo.
echo ==========================================================
echo   结束。显示"成功 xxx 只"即表示创业板数据已就位
echo   可以重新打开 QuantMonitorV6 了
echo ==========================================================
pause
"""

bp = ROOT + "灌创业板K线缓存.bat"
data = bat.replace("\n", "\r\n").encode("gbk")
io.open(bp, "wb").write(data)
print("OK bat 已用 GBK 重写：%d 字节" % len(data))
print("   编码自检（GBK 解码回读首行）: %s" % data.decode("gbk").splitlines()[0])
