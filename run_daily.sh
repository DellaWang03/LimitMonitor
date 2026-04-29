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
echo "[1/5] 运行Stage0 - Wind代码处理..."
python3 run_stage0.py
if [ $? -ne 0 ]; then
    echo "❌ Stage0运行失败"
    exit 1
fi
echo "✅ Stage0完成"

# 2. 运行Stage1
echo ""
echo "[2/5] 运行Stage1 - 限额明细计算..."
python3 run_stage1.py
if [ $? -ne 0 ]; then
    echo "❌ Stage1运行失败"
    exit 1
fi
echo "✅ Stage1完成"

# 3. 运行Stage2
echo ""
echo "[3/5] 运行Stage2 - 集中度指标计算..."
python3 run_stage2.py
if [ $? -ne 0 ]; then
    echo "❌ Stage2运行失败"
    exit 1
fi
echo "✅ Stage2完成"

# 4. 检查数据完整性并决定是否归档
echo ""
echo "[4/5] 数据归档检查..."

CURRENT_DIR="$PROJECT_ROOT/data/current"
WARNING_FILE="$CURRENT_DIR/.INCOMPLETE_DATA_WARNING"
SNAPSHOT_DIR="$CURRENT_DIR/display_snapshots"

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
        echo "⚠️  【测试模式】数据不完整，跳过 DB 归档与展示层快照生成"
        echo "   数据已保存到 data/current/ 可用于:"
        echo "     - 数据校验 (validation/)"
        echo "     - 配置调试"
        echo ""
        echo "💡 当前 Streamlit / display_snapshots 已切 DB 单源，若未归档成功，将继续显示上一次成功归档的数据"
        echo "💡 如需保留此次测试结果，请手动备份 data/current/ 文件夹"
        echo ""
        ARCHIVED=false
        if [ -d "$SNAPSHOT_DIR" ]; then
            rm -rf "$SNAPSHOT_DIR"
            echo "🧹 已清理旧的 display_snapshots，避免误用历史快照"
        fi
    fi
else
    # 数据完整，先写 DB，再基于 current 快照生成展示层快照
    echo "✅ 数据完整性检查通过，开始归档到 DB..."
    
    if [ -d "$CURRENT_DIR/stage0_output" ] && [ -d "$CURRENT_DIR/stage1_output" ] && [ -d "$CURRENT_DIR/stage2_output" ]; then
        python3 scripts/daily_archive.py
        if [ $? -eq 0 ]; then
            ARCHIVED=true
            echo "✅ 数据已写入 DB current 快照"
            echo "   archive_date: $TODAY"
        else
            echo "❌ 归档失败"
            ARCHIVED=false
            exit 1
        fi
    else
        echo "⚠️  数据目录不完整，跳过归档"
        ARCHIVED=false
    fi
fi

# 5. 基于 DB current 快照生成展示层快照
if [ "$ARCHIVED" = true ]; then
    echo ""
    echo "[5/5] 生成展示层 CSV 快照..."
    python3 scripts/generate_display_snapshot.py
    if [ $? -ne 0 ]; then
        echo "⚠️  展示层快照生成失败（DB 已归档成功，请单独检查 generate_display_snapshot.py）"
    else
        echo "✅ 展示层快照生成完成"
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
    echo "  - 当前快照: DB archive_meta.is_current=1"
    echo "  - 展示快照: data/current/display_snapshots/"
else
    echo "  - 当前快照: 未更新（数据不完整，仍沿用上一次成功归档结果）"
fi
echo ""
echo "🚀 启动Web界面: bash start_web.sh"
echo ""
