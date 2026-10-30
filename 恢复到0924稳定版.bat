@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   恢复到 0924 稳定版
echo   (覆盖前会自动先备份当前状态)
echo ========================================
echo.
python scripts\restore_stable.py
echo.
pause
