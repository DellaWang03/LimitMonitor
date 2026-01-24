#!/bin/bash
# 每日数据更新脚本 - 支持历史数据备份和环境区分

# 设置环境模式（默认为development，可通过环境变量覆盖）
export LIMIT_MONITOR_ENV=${LIMIT_MONITOR_ENV:-development}

echo "========================================="
echo "限额监控系统 - 每日数据更新"
if [ "$LIMIT_MONITOR_ENV" = "production" ]; then
    echo "运行模式: 🔴 生产环境"
else
    echo "运行模式: 🟡 测试环境"
fi
echo "启动时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================="

# 获取今天的日期
TODAY=$(date '+%Y-%m-%d')

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

# 1. 运行Stage0
echo ""
echo "[1/4] 运行Stage0 - Wind代码处理..."
python3 run_stage0.py
if [ $? -ne 0 ]; then
    echo "❌ Stage0运行失败"
    exit 1
fi
echo "✅ Stage0完成"

# 2. 运行Stage1
echo ""
echo "[2/4] 运行Stage1 - 限额明细计算..."
python3 run_stage1.py
if [ $? -ne 0 ]; then
    echo "❌ Stage1运行失败"
    exit 1
fi
echo "✅ Stage1完成"

# 3. 运行Stage2
echo ""
echo "[3/4] 运行Stage2 - 集中度指标计算..."
python3 run_stage2.py
if [ $? -ne 0 ]; then
    echo "❌ Stage2运行失败"
    exit 1
fi
echo "✅ Stage2完成"

# 4. 检查数据完整性并决定是否归档
echo ""
echo "[4/4] 数据归档检查..."

CURRENT_DIR="$PROJECT_ROOT/data/current"
WARNING_FILE="$CURRENT_DIR/.INCOMPLETE_DATA_WARNING"

# 检查数据完整性警告文件
if [ -f "$WARNING_FILE" ]; then
    echo ""
    echo "⚠️  检测到数据不完整警告"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    cat "$WARNING_FILE"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    if [ "$LIMIT_MONITOR_ENV" = "production" ]; then
        echo ""
        echo "❌ 生产环境不允许归档不完整数据"
        echo "   请更新数据源后重新运行"
        exit 1
    else
        echo ""
        echo "⚠️  【测试模式】数据不完整，跳过归档到 history/"
        echo "   数据已保存到 data/current/ 可用于:"
        echo "     - 数据校验 (validation/)"
        echo "     - 可视化查看 (streamlit)"
        echo "     - 配置调试"
        echo ""
        echo "💡 如需保留此次测试结果，请手动备份 data/current/ 文件夹"
        echo ""
        ARCHIVED=false
    fi
else
    # 数据完整，正常归档
    echo "✅ 数据完整性检查通过，开始归档..."
    
    HISTORY_DIR="$PROJECT_ROOT/data/history/$TODAY"
    mkdir -p "$HISTORY_DIR"
    
    if [ -d "$CURRENT_DIR/stage0_output" ] && [ -d "$CURRENT_DIR/stage1_output" ] && [ -d "$CURRENT_DIR/stage2_output" ]; then
        echo "  从 current/ 目录备份完整数据（Stage0/1/2）..."
        cp -r "$CURRENT_DIR/stage0_output" "$HISTORY_DIR/"
        cp -r "$CURRENT_DIR/stage1_output" "$HISTORY_DIR/"
        cp -r "$CURRENT_DIR/stage2_output" "$HISTORY_DIR/"
        echo "  ✅ 已归档: stage0_output (配置文件)"
        echo "  ✅ 已归档: stage1_output (业务数据)"
        echo "  ✅ 已归档: stage2_output (业务数据)"
        echo "✅ 数据已备份到: $HISTORY_DIR"
        ARCHIVED=true
    else
        echo "⚠️  数据目录不完整，跳过归档"
        ARCHIVED=false
    fi
fi

echo ""
echo "========================================="
echo "✅ 每日数据更新完成！"
echo "完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================="
echo ""
echo "📁 数据位置:"
echo "  - 最新数据: data/current/"
if [ "$ARCHIVED" = true ]; then
    echo "  - 历史备份: data/history/$TODAY/"
else
    echo "  - 历史备份: 未归档（数据不完整）"
fi
echo ""
echo "🚀 启动Web界面: bash start_web.sh"
echo ""
