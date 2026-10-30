@echo off
chcp 936 >nul
title 量化交易作战中控台 V2.7.1
cd /d "%~dp0"

echo ========================================
echo   量化交易作战中控台 V2.7.1
echo ========================================
echo.
echo PROJECT_ROOT: %CD%
echo MAIN_FILE: %CD%\main.py
echo.

REM 优先使用 Python 3.14（已安装 PyQt6/duckdb/pandas 的完整环境）
set "PYTHON_CMD=C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe"

if exist "%PYTHON_CMD%" (
    echo Python环境正常: %PYTHON_CMD%
    goto :start
)

REM 兜底：PATH 中的 python
set PYTHON_CMD=python
python --version >nul 2>&1
if %errorlevel%==0 (
    echo 使用 PATH 中的 Python
    goto :start
)

echo 未找到Python，请先安装Python 3.10+
pause
exit /b 1

:start
echo.
echo 正在启动程序...
echo.

"%PYTHON_CMD%" main.py

if %errorlevel% neq 0 (
    echo.
    echo ========================================
    echo 程序异常退出，错误码: %errorlevel%
    echo ========================================
    echo.
    pause
)
