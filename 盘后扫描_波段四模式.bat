@echo off
chcp 65001 >nul
title 波段四模式 + 基准阳跟踪 盘后扫描
cd /d "%~dp0"

echo ========================================
echo   盘后扫描（双引擎）
echo   引擎1: 4种独立形态（跳空/大阳/底部/周K）
echo   引擎2: 基准阳跨日跟踪（题材异动→放量阳→洗盘→建仓→加仓）
echo   结果自动写入金铲子 + 企业微信推送
echo ========================================
echo.

set "PYTHON_CMD=C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe"

if not exist "%PYTHON_CMD%" (
    echo [错误] 找不到 Python: %PYTHON_CMD%
    pause
    exit /b 1
)

echo [1/2] 跑基准阳跨日跟踪（推进状态机 + 新基准阳识别）...
"%PYTHON_CMD%" -c "from services.anchor_tracker import get_anchor_tracker, STATE_CN; e=get_anchor_tracker(); r=e.scan_daily(); print('结果:', r); [print(' ', s['code'], s['name'], STATE_CN[s['state']], s.get('note','')) for s in e.get_active_signals()[:20]]"
echo.

echo [2/2] 跑4种独立形态全市场扫描...
"%PYTHON_CMD%" -m services.band_pattern_engine
echo.

echo ========================================
echo   扫描完成。打开程序看"金铲子(实时)"
echo   红色=加仓 绿色=建仓 黄色=洗盘中 蓝色=基准阳
echo ========================================
pause
