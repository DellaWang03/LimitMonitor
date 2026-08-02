#!/bin/bash

echo "============================================"
echo "启动限额监控可视化系统"
echo "============================================"
echo

cd "$(dirname "$0")"

STREAMLIT_BIN="$PWD/.venv/bin/streamlit"
if [[ ! -x "$STREAMLIT_BIN" ]]; then
    echo "错误：未找到项目虚拟环境中的 Streamlit：$STREAMLIT_BIN"
    echo "请先创建虚拟环境并安装项目依赖。"
    exit 1
fi

echo "正在启动Streamlit服务..."
echo "浏览器将自动打开: http://localhost:8501"
echo
echo "使用说明:"
echo "  - 左侧导航栏选择页面"
echo "  - 顶部筛选器过滤数据"
echo "  - 点击"导出Excel"下载数据"
echo
echo "按 Ctrl+C 停止服务"
echo "============================================"
echo

exec "$STREAMLIT_BIN" run app.py --server.port 8501
