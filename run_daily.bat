@echo off
chcp 65001 > nul
REM 每日数据更新脚本 - 支持历史数据备份和环境区分

REM 设置环境模式（默认为development）
if not defined LIMIT_MONITOR_ENV set LIMIT_MONITOR_ENV=development

echo =========================================
echo 限额监控系统 - 每日数据更新
if "%LIMIT_MONITOR_ENV%"=="production" (
    echo 运行模式: 生产环境
) else (
    echo 运行模式: 测试环境
)
echo 启动时间: %date% %time%
echo =========================================

REM 获取今天的日期 (格式: YYYY-MM-DD)
for /f "tokens=1-3 delims=/ " %%a in ('date /t') do (
    set TODAY=%%a-%%b-%%c
)

REM 切换到脚本所在目录
cd /d "%~dp0"
set PROJECT_ROOT=%cd%

REM 1. 运行Stage0
echo.
echo [1/4] 运行Stage0 - Wind代码处理...
python run_stage0.py
if errorlevel 1 (
    echo ❌ Stage0运行失败
    pause
    exit /b 1
)
echo ✅ Stage0完成

REM 2. 运行Stage1
echo.
echo [2/4] 运行Stage1 - 限额明细计算...
python run_stage1.py
if errorlevel 1 (
    echo ❌ Stage1运行失败
    pause
    exit /b 1
)
echo ✅ Stage1完成

REM 3. 运行Stage2
echo.
echo [3/4] 运行Stage2 - 集中度指标计算...
python run_stage2.py
if errorlevel 1 (
    echo ❌ Stage2运行失败
    pause
    exit /b 1
)
echo ✅ Stage2完成

REM 4. 检查数据完整性并决定是否归档
echo.
echo [4/4] 数据归档检查...

set CURRENT_DIR=%PROJECT_ROOT%\data\current
set WARNING_FILE=%CURRENT_DIR%\.INCOMPLETE_DATA_WARNING

REM 检查数据完整性警告文件
if exist "%WARNING_FILE%" (
    echo.
    echo ⚠️  检测到数据不完整警告
    echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    type "%WARNING_FILE%"
    echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    if "%LIMIT_MONITOR_ENV%"=="production" (
        echo.
        echo ❌ 生产环境不允许归档不完整数据
        echo    请更新数据源后重新运行
        pause
        exit /b 1
    ) else (
        echo.
        echo ⚠️  【测试模式】数据不完整，跳过归档到 history\
        echo    数据已保存到 data\current\ 可用于:
        echo      - 数据校验 (validation\)
        echo      - 可视化查看 (streamlit)
        echo      - 配置调试
        echo.
        echo 💡 如需保留此次测试结果，请手动备份 data\current\ 文件夹
        set ARCHIVED=false
    )
) else (
    REM 数据完整，正常归档
    echo ✅ 数据完整性检查通过，开始归档...
    
    set HISTORY_DIR=%PROJECT_ROOT%\data\history\%TODAY%
    if not exist "%HISTORY_DIR%" mkdir "%HISTORY_DIR%"
    
    if exist "%CURRENT_DIR%\stage0_output" (
        if exist "%CURRENT_DIR%\stage1_output" (
            if exist "%CURRENT_DIR%\stage2_output" (
                echo   从 current\ 目录备份完整数据（Stage0/1/2）...
                xcopy /E /I /Y "%CURRENT_DIR%\stage0_output" "%HISTORY_DIR%\stage0_output\" > nul
                xcopy /E /I /Y "%CURRENT_DIR%\stage1_output" "%HISTORY_DIR%\stage1_output\" > nul
                xcopy /E /I /Y "%CURRENT_DIR%\stage2_output" "%HISTORY_DIR%\stage2_output\" > nul
                echo   ✅ 已归档: stage0_output (配置文件)
                echo   ✅ 已归档: stage1_output (业务数据)
                echo   ✅ 已归档: stage2_output (业务数据)
                echo ✅ 数据已备份到: %HISTORY_DIR%
                set ARCHIVED=true
            ) else (
                echo ⚠️  数据目录不完整，跳过归档
                set ARCHIVED=false
            )
        ) else (
            echo ⚠️  数据目录不完整，跳过归档
            set ARCHIVED=false
        )
    ) else (
        echo ⚠️  数据目录不完整，跳过归档
        set ARCHIVED=false
    )
)

echo.
echo =========================================
echo ✅ 每日数据更新完成！
echo 完成时间: %date% %time%
echo =========================================
echo.
echo 📁 数据位置:
echo   - 最新数据: data\current\
if "%ARCHIVED%"=="true" (
    echo   - 历史备份: data\history\%TODAY%\
) else (
    echo   - 历史备份: 未归档（数据不完整）
)
echo.
echo 🚀 启动Web界面: start_web.bat
echo.
pause
