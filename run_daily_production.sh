#!/bin/bash
# 生产环境每日运行脚本

export LIMIT_MONITOR_ENV=production

echo "========================================="
echo "🔴 生产环境模式"
echo "  - 数据必须为T-1日期"
echo "  - 数据过期将停止处理"
echo "  - 数据完整才会归档"
echo "========================================="
echo ""

bash run_daily.sh
