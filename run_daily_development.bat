@echo off
chcp 65001 > nul
REM 测试/开发环境每日运行脚本

set LIMIT_MONITOR_ENV=development

echo =========================================
echo 🟡 测试/开发环境模式
echo   - 允许使用旧数据
echo   - 数据过期将警告但继续
echo   - 数据不完整不会归档
echo   - 可用于配置调试和功能测试
echo =========================================
echo.

call run_daily.bat
