@echo off
chcp 65001 > nul
REM 每日生产入口：由同一 Python 进程完成运行期上下文、归档、发布与展示快照。

cd /d "%~dp0"
set PROJECT_ROOT=%cd%
set LIMIT_MONITOR_PROFILE=windows
set LIMIT_MONITOR_ENV=production
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
if exist "config\local_env.bat" call "config\local_env.bat"

if exist ".venv\Scripts\python.exe" (
    set PYTHON_BIN=.venv\Scripts\python.exe
) else (
    set PYTHON_BIN=python
)

%PYTHON_BIN% --version > nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到可用的 Python 解释器
    exit /b 1
)

for %%V in (DB_HOST DB_PORT DB_USER DB_PASSWORD DB_NAME) do (
    if not defined %%V (
        echo 错误: 缺少数据库环境变量 %%V
        echo 请配置系统环境变量，或创建 config\local_env.bat
        exit /b 1
    )
)

echo =========================================
echo 限额监控系统 - 每日数据更新
echo 运行模式: %LIMIT_MONITOR_ENV%
echo =========================================

%PYTHON_BIN% scripts\run_daily_pipeline.py
set PIPELINE_STATUS=%ERRORLEVEL%
if "%PIPELINE_STATUS%"=="3" (
    echo 警告: 既有数据已发布；科创监控存在失败或待核实记录
    exit /b 3
)
if "%PIPELINE_STATUS%"=="2" (
    echo 警告: 既有数据已发布；展示快照生成失败，请同时检查科创分支日志
    exit /b 2
)
if not "%PIPELINE_STATUS%"=="0" (
    echo [ERROR] 每日生产编排失败
    exit /b %PIPELINE_STATUS%
)

echo [OK] 每日生产编排完成
