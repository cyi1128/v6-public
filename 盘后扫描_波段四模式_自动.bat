@echo off
chcp 65001 >nul
title 盘后扫描（自动·计划任务）
cd /d "%~dp0"

REM ============================================================
REM  自动版盘后扫描（供 Windows 计划任务调用）
REM  与手动版 盘后扫描_波段四模式.bat 的区别：
REM    1. 没有 pause（否则计划任务会一直挂着等按键）
REM    2. 全部输出写进 logs\auto_scan_YYYYMMDD.log
REM    3. 开头做交易日判断，非交易日直接退出
REM    4. 设 SKIP_SCAN=1 可只验通路不跑扫描（自检用）
REM ============================================================

set "PYTHON_CMD=C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe"
if not exist "%PYTHON_CMD%" set "PYTHON_CMD=python"
REM  让 Python 子进程也输出 UTF-8，避免与 bat 的 echo 混编码导致日志乱码
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

set "LOGDIR=%~dp0logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set "D=%%i"
if "%D%"=="" set "D=unknown"
set "LOG=%LOGDIR%\auto_scan_%D%.log"

echo. >> "%LOG%"
echo ============================================================ >> "%LOG%"
echo [%date% %time%] 自动扫描启动（任务计划） >> "%LOG%"

REM ---------- 交易日判断（fail-open）----------
REM  约定：python 判定"非交易日"时返回退出码 9；交易日返回 0。
REM  只有"恰好 9"才跳过。判断代码报错(返回1)或命令找不到(返回9009)
REM  一律照常扫描 —— 宁可白跑一次，绝不因判断失败漏扫。
set "IS_TRADE=1"
"%PYTHON_CMD%" -c "import sys;from utils.trade_calendar import is_trading_day;sys.exit(0 if is_trading_day() else 9)" >nul 2>&1
if errorlevel 9 if not errorlevel 10 set "IS_TRADE=0"
echo [%date% %time%] 交易日判断: IS_TRADE=%IS_TRADE% >> "%LOG%"
if "%IS_TRADE%"=="0" (
    echo [%date% %time%] 非交易日，跳过本次扫描 >> "%LOG%"
    exit /b 0
)
echo [%date% %time%] 交易日确认，开始扫描 >> "%LOG%"

REM ---------- 自检开关 ----------
if "%SKIP_SCAN%"=="1" (
    echo [%date% %time%] SKIP_SCAN=1 自检模式：通路正常，跳过实际扫描 >> "%LOG%"
    exit /b 0
)

REM ---------- 步骤1：刷新交易日历 ----------
echo [%date% %time%] [1/3] 刷新交易日历（腾讯指数日K） >> "%LOG%"
"%PYTHON_CMD%" -c "from utils.trade_calendar import refresh_from_market as _r; print('交易日历刷新：新增', _r(), '个交易日')" >> "%LOG%" 2>&1
echo [%date% %time%] 交易日历刷新 完成 >> "%LOG%"

REM ---------- 引擎1：基准阳跨日跟踪 ----------
echo [%date% %time%] [2/3] 基准阳跨日跟踪（推进状态机 + 新基准阳识别） >> "%LOG%"
"%PYTHON_CMD%" -c "from services.anchor_tracker import get_anchor_tracker, STATE_CN; e=get_anchor_tracker(); r=e.scan_daily(); print('结果:', r); [print(' ', s['code'], s['name'], STATE_CN[s['state']], s.get('note','')) for s in e.get_active_signals()[:20]]" >> "%LOG%" 2>&1
echo [%date% %time%] 引擎1 完成 >> "%LOG%"

REM ---------- 引擎2：四种独立形态全市场扫描 ----------
echo [%date% %time%] [3/3] 四种独立形态全市场扫描（静音包装：过滤K线降级噪音） >> "%LOG%"
"%PYTHON_CMD%" "%~dp0tools\run_scan_quiet.py" >> "%LOG%" 2>&1
echo [%date% %time%] 引擎2 完成 >> "%LOG%"

echo [%date% %time%] 自动扫描结束 >> "%LOG%"
exit /b 0
