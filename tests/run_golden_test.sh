#!/bin/bash
# 黄金集成测试 - 使用 data_source_0123/ 验证全链路代码逻辑（单模式 9 CSV）
# 使用方法: bash tests/run_golden_test.sh
# 参考基准: data_for_testing_0123/（9 张展示表 CSV）

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

export LIMIT_MONITOR_PROFILE=local

echo "================================================="
echo "黄金集成测试 - 使用固定样本数据验证代码逻辑"
echo "数据源: data_source_0123/（固定快照，2026-01-23）"
echo "参考基准: data_for_testing_0123/"
echo "================================================="

echo ""
echo "[1/4] Stage0 - Wind代码处理与数据提取..."
python3 run_stage0.py
echo "✅ Stage0 完成"

echo ""
echo "[2/4] Stage1 - 限额明细计算..."
python3 run_stage1.py
echo "✅ Stage1 完成"

echo ""
echo "[3/4] Stage2 - 集中度指标计算..."
python3 run_stage2.py
echo "✅ Stage2 完成"

echo ""
echo "[4/4] 生成展示层 9 张 CSV 快照并与黄金基准对比..."
python3 scripts/generate_display_snapshot.py
python3 validation/validate_dashboard_display.py \
    --snapshot-dir data/current/display_snapshots \
    --ref-dir data_for_testing_0123
echo "✅ 对比完成"

echo ""
echo "================================================="
echo "✅ 黄金集成测试完成"
echo "================================================="
echo ""
echo "⚠️  注意: 测试输出已写入 data/current/（含 .INCOMPLETE_DATA_WARNING 文件）"
echo "   如需恢复今日生产数据，请重新完整运行 run_daily.sh（勿手动删除 data/current/）"
echo "   run_daily.sh 运行 Stage0 成功后会自动清除警告文件并正常归档"
