@echo off
chcp 65001 > nul
echo ============================================
echo 启动限额监控可视化系统
echo ============================================
echo.

cd /d "%~dp0"

set LIMIT_MONITOR_PROFILE=windows
if exist "config\local_env.bat" call "config\local_env.bat"

if exist ".venv\Scripts\python.exe" (
    set PYTHON_BIN=.venv\Scripts\python.exe
) else (
    set PYTHON_BIN=python
)

%PYTHON_BIN% --version > nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到可用的 Python 解释器
    echo 请先安装 Python，或在项目根目录创建 .venv
    pause
    exit /b 1
)

%PYTHON_BIN% -c "import streamlit" > nul 2>&1
if errorlevel 1 (
    echo 错误: 当前 Python 环境未安装 streamlit
    echo 请先执行: %PYTHON_BIN% -m pip install -r requirements.txt
    pause
    exit /b 1
)

for %%V in (DB_HOST DB_PORT DB_USER DB_PASSWORD DB_NAME) do (
    if not defined %%V (
        echo 错误: 缺少数据库环境变量 %%V
        echo 请配置系统环境变量，或创建 config\local_env.bat
        pause
        exit /b 1
    )
)

echo 正在启动Streamlit服务...
echo 浏览器将自动打开: http://localhost:8501
echo.
echo 使用说明:
echo   - 左侧导航栏选择页面
echo   - 顶部筛选器过滤数据
echo   - 点击"导出Excel"下载数据
echo.
echo 按 Ctrl+C 停止服务
echo ============================================
echo.

%PYTHON_BIN% -m streamlit run app.py --server.port 8501

pause
