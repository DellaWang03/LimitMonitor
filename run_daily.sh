#!/bin/bash
# 每日生产入口：由同一 Python 进程完成运行期上下文、归档、发布与展示快照。

export LIMIT_MONITOR_ENV=${LIMIT_MONITOR_ENV:-production}

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT" || exit 1

if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
    PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
else
    PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

require_env() {
    local name="$1"
    if [ -z "${!name:-}" ]; then
        echo "❌ 缺少数据库环境变量: $name"
        exit 1
    fi
}

for variable in DB_HOST DB_PORT DB_USER DB_PASSWORD DB_NAME; do
    require_env "$variable"
done

"$PYTHON_BIN" --version || exit 1
TODAY=$(date '+%Y-%m-%d')

echo "========================================="
echo "限额监控系统 - 每日数据更新"
echo "运行模式: $LIMIT_MONITOR_ENV"
echo "启动时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================="

"$PYTHON_BIN" scripts/run_daily_pipeline.py --archive-date "$TODAY"
status=$?
if [ "$status" -ne 0 ]; then
    if [ "$status" -eq 3 ]; then
        echo "⚠️ 既有数据已发布；科创监控存在失败或待核实记录"
    elif [ "$status" -eq 2 ]; then
        echo "⚠️ 既有数据已发布；展示快照生成失败，请同时检查科创分支日志"
    else
        echo "❌ 每日生产编排失败（退出码: $status）"
    fi
    exit "$status"
fi

echo "✅ 每日生产编排完成"
