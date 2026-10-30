@echo off
chcp 65001 >nul
title AI量化盯盘系统 - 网页版

echo ========================================
echo   AI量化盯盘系统 - 网页版
echo ========================================
echo.

REM 检查Flask是否安装
python -c "import flask" 2>nul
if errorlevel 1 (
    echo 正在安装Flask...
    pip install flask
    echo.
)

echo 启动网页版服务...
echo.
echo 请确保手机和电脑在同一个WiFi网络下
echo.
echo 启动后，在手机浏览器访问以下地址：
echo   http://你的电脑IP:5000
echo.
echo 查看电脑IP的方法：
echo   1. 按 Win+R，输入 cmd 回车
echo   2. 输入 ipconfig 回车
echo   3. 找到 IPv4 地址（通常是192.168.x.x）
echo.
echo ========================================
echo.

python web_app.py

pause
