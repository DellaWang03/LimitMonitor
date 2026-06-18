#!/bin/bash
# 前期上线全流程集成测试（真实 DB 集成校验）
# 使用方法: bash tests/run_full_integration_test.sh [DATA_DATE] [REF_DIR]
#
# 口径：
#   1. 先由 run_daily.sh / run_daily.bat 跑完 Stage0→Stage1→Stage2→DB 归档；
#   2. 本脚本只消费 DB 中这批已落库数据，不再重跑本地固定样例；
#   3. 先校验 DB current 与显式 data_date 历史模式完全一致；
#   4. 再从 DB current 生成展示层 CSV，与人工目标目录下全部 CSV 对比。
#
# 环境变量 DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME 必须由调用方
# 提前注入（仓库不会出现明文凭据）。

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"

require_env() {
    local var_name="$1"
    if [ -z "${!var_name:-}" ]; then
        echo "❌ 缺少必需环境变量: $var_name"
        echo "   tests/run_full_integration_test.sh 目前是真实 DB 全流程集成测试，请先注入测试库连接信息。"
        exit 1
    fi
}

for required_var in DB_HOST DB_PORT DB_USER DB_PASSWORD DB_NAME; do
    require_env "$required_var"
done

TEST_DATA_DATE="${1:-$(date '+%F')}"
REF_DIR="${2:-data_for_testing}"

if [ ! -d "$REF_DIR" ]; then
    echo "❌ 目标基准目录不存在: $REF_DIR"
    exit 1
fi

echo "================================================="
echo "前期上线全流程集成测试 - 真实 DB 集成校验"
echo "校验对象: run_daily 已落库的真实 DB current"
echo "目标基准目录: $REF_DIR"
echo "期望 data_date: $TEST_DATA_DATE"
echo "Python: $PYTHON_BIN"
echo "测试模式: integration test（依赖真实测试 DB）"
echo "================================================="

echo ""
echo "[1/3] 校验 DB current / history 看板读取一致..."
"$PYTHON_BIN" validation/validate_db_dashboard_consistency.py --data-date "$TEST_DATA_DATE"
echo "✅ current/history 读取一致"

echo ""
echo "[2/3] 从 DB current 生成展示层快照..."
"$PYTHON_BIN" scripts/generate_display_snapshot.py
echo "✅ 展示层快照生成完成"

echo ""
echo "[3/3] 与目标基准目录下全部 CSV 对比..."
"$PYTHON_BIN" validation/validate_dashboard_display.py \
    --snapshot-dir data/current/display_snapshots \
    --ref-dir "$REF_DIR"
echo "✅ 对比完成"

echo ""
echo "================================================="
echo "✅ 全流程集成测试完成"
echo "================================================="
echo ""
echo "说明："
echo "  - 本脚本不会重跑 Stage0/1/2，也不会改写 DB current。"
echo "  - 若第 [1/3] 步失败，通常表示当前 DB latest 不是 data_date=$TEST_DATA_DATE。"
echo "  - 展示层快照会刷新到 data/current/display_snapshots/，供人工复核与 CSV 对比使用。"
