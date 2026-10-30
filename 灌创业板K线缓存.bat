@echo off
cd /d D:\QuantMonitorV6
set "PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe"
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
"%PY%" -X utf8 tools\seed_cyb_kline.py --workers 10
echo.
echo ==========================================================
echo   结束。显示"成功 xxx 只"即表示创业板数据已就位
echo   可以重新打开 QuantMonitorV6 了
echo ==========================================================
pause
