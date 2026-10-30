@echo off
chcp 65001 >nul
title 环境诊断工具
cd /d "%~dp0"

echo ========================================
echo   量化盯盘 V6.0 - 环境诊断工具
echo ========================================
echo.

echo [1/5] 检查系统信息...
echo    操作系统: %OS%
echo.

echo [2/5] 检查Python...
python --version 2>&1
if %errorlevel%==0 (
    echo    ^[OK^] python 命令可用
) else (
    echo    ^[FAIL^] python 命令不可用
)

py --version 2>&1
if %errorlevel%==0 (
    echo    ^[OK^] py 启动器可用
) else (
    echo    ^[WARN^] py 启动器不可用
)
echo.

echo [3/5] 搜索Python安装路径...
set FOUND=0
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
    echo    找到: %LOCALAPPDATA%\Programs\Python\Python313\python.exe
    set FOUND=1
)
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    echo    找到: %LOCALAPPDATA%\Programs\Python\Python312\python.exe
    set FOUND=1
)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    echo    找到: %LOCALAPPDATA%\Programs\Python\Python311\python.exe
    set FOUND=1
)
if exist "C:\Python312\python.exe" (
    echo    找到: C:\Python312\python.exe
    set FOUND=1
)
if exist "C:\Python311\python.exe" (
    echo    找到: C:\Python311\python.exe
    set FOUND=1
)
if %FOUND%==0 (
    echo    未在常见位置找到Python
)
echo.

echo [4/5] 检查依赖库...
python -c "import PyQt6; print('   PyQt6:', PyQt6.__version__)" 2>&1
if %errorlevel% neq 0 (
    echo    ^[FAIL^] PyQt6 未安装
)

python -c "import pandas; print('   pandas:', pandas.__version__)" 2>&1
if %errorlevel% neq 0 (
    echo    ^[FAIL^] pandas 未安装
)

python -c "import numpy; print('   numpy:', numpy.__version__)" 2>&1
if %errorlevel% neq 0 (
    echo    ^[FAIL^] numpy 未安装
)

python -c "import pytdx; print('   pytdx: 已安装')" 2>&1
if %errorlevel% neq 0 (
    echo    ^[FAIL^] pytdx 未安装 (通达信行情库)
)
echo.

echo [5/5] 检查项目文件...
if exist "main.py" (
    echo    ^[OK^] main.py 存在
) else (
    echo    ^[FAIL^] main.py 不存在
)

if exist "config\settings.py" (
    echo    ^[OK^] 配置文件存在
) else (
    echo    ^[FAIL^] 配置文件缺失
)

if exist "ui\main_window.py" (
    echo    ^[OK^] UI模块存在
) else (
    echo    ^[FAIL^] UI模块缺失
)

if exist "core\scheduler.py" (
    echo    ^[OK^] 核心模块存在
) else (
    echo    ^[FAIL^] 核心模块缺失
)
echo.

echo ========================================
echo   诊断完成
echo ========================================
echo.
echo 如果Python未安装，请访问:
echo   https://www.python.org/downloads/
echo.
echo 安装时务必勾选 "Add Python to PATH"
echo.
pause
