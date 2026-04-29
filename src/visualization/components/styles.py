"""
自定义CSS样式管理
现代金融看板风格 - 参考Shadcn UI、FusionCharts Investment Dashboard
"""

# 现代金融看板主题
CUSTOM_CSS = """
<style>
/* ====== 全局样式 ====== */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

* {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
}

/* 主容器背景 - 简洁浅灰 */
.stApp,
[data-testid="stAppViewContainer"],
.main {
    background: #f8fafc !important;
}

/* 主内容区域 */
.main .block-container {
    background: transparent;
    border-radius: 16px;
    padding: 1rem 2rem 1.5rem;
    box-shadow: none;
    max-width: 1400px;
}

/* Streamlit 顶部壳层 */
header[data-testid="stHeader"],
[data-testid="stHeader"],
[data-testid="stToolbar"] {
    background: #f8fafc !important;
    border-bottom: none !important;
    box-shadow: none !important;
}

header[data-testid="stHeader"],
[data-testid="stHeader"] {
    height: 0 !important;
}

[data-testid="stToolbar"] {
    top: 0.5rem !important;
    right: 1rem !important;
}

[data-testid="stDecoration"] {
    display: none !important;
}

/* ====== 侧边栏样式 ====== */
section[data-testid="stSidebar"],
section[data-testid="stSidebar"] > div {
    background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%) !important;
    border-right: none !important;
    box-shadow: none !important;
}

/* 清理侧边栏和主区之间的默认分隔线 */
[data-testid="stSidebar"] + div,
[data-testid="stSidebarResizer"] {
    border-left: none !important;
    box-shadow: none !important;
}

section[data-testid="stSidebar"] .stMarkdown {
    color: #e2e8f0;
}

section[data-testid="stSidebar"] .stMarkdown h1,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3 {
    color: #f8fafc !important;
}

section[data-testid="stSidebar"] hr {
    border-color: #334155;
    opacity: 0.5;
}

/* 侧边栏Radio按钮 */
section[data-testid="stSidebar"] .stRadio > div {
    gap: 4px;
}

section[data-testid="stSidebar"] .stRadio label {
    background: transparent;
    border-radius: 8px;
    padding: 10px 12px;
    margin: 2px 0;
    transition: all 0.2s ease;
    color: #cbd5e1;
    font-weight: 500;
}

section[data-testid="stSidebar"] .stRadio label *,
section[data-testid="stSidebar"] .stRadio [role="radiogroup"] label *,
section[data-testid="stSidebar"] .stRadio [data-baseweb="radio"] *,
section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] label *,
section[data-testid="stSidebar"] .stSelectbox *,
section[data-testid="stSidebar"] .stDateInput * {
    color: #dbe7f5 !important;
}

section[data-testid="stSidebar"] .stRadio label:hover {
    background: rgba(255, 255, 255, 0.07);
    color: #f1f5f9;
}

section[data-testid="stSidebar"] .stRadio label:hover *,
section[data-testid="stSidebar"] .stRadio [role="radiogroup"] label:hover * {
    color: #f8fbff !important;
}

section[data-testid="stSidebar"] .stRadio label[data-checked="true"] {
    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
    color: white;
}

section[data-testid="stSidebar"] .stRadio label[data-checked="true"] *,
section[data-testid="stSidebar"] .stRadio [role="radiogroup"] label[data-checked="true"] * {
    color: #ffffff !important;
}

section[data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] > div,
section[data-testid="stSidebar"] .stDateInput > div > div > input {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(148, 163, 184, 0.28);
}

section[data-testid="stSidebar"] .stSelectbox svg,
section[data-testid="stSidebar"] .stDateInput svg {
    fill: #dbe7f5 !important;
}

/* ====== 按钮样式 ====== */
.stButton > button,
.stFormSubmitButton > button {
    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
    color: white;
    border: none;
    border-radius: 8px;
    padding: 0.6rem 1.25rem;
    font-weight: 500;
    font-size: 0.875rem;
    transition: all 0.2s ease;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.stButton > button:hover,
.stFormSubmitButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.35);
}

.stButton > button:active,
.stFormSubmitButton > button:active {
    transform: translateY(0);
}

/* ====== KPI 指标卡片 ====== */
div[data-testid="stMetric"] {
    background: #ffffff;
    padding: 1.25rem 1.5rem;
    border-radius: 12px;
    border: 1px solid #e2e8f0;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
    transition: all 0.2s ease;
}

div[data-testid="stMetric"]:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    border-color: #cbd5e1;
}

div[data-testid="stMetric"] label {
    font-size: 0.75rem !important;
    font-weight: 500 !important;
    color: #64748b !important;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-size: 1.75rem !important;
    font-weight: 700 !important;
    color: #1e293b !important;
    line-height: 1.2;
}

div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
    font-size: 0.8rem !important;
}

/* ====== 表格样式 ====== */
.stDataFrame {
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid #e2e8f0;
}

.stDataFrame [data-testid="stDataFrameResizable"] {
    border-radius: 12px;
}

/* 表头 */
.stDataFrame th {
    background: #f8fafc !important;
    color: #475569 !important;
    font-weight: 600 !important;
    font-size: 0.75rem !important;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 12px 16px !important;
    border-bottom: 2px solid #e2e8f0 !important;
}

/* 表格行 */
.stDataFrame td {
    padding: 10px 16px !important;
    font-size: 0.875rem !important;
    color: #334155;
    border-bottom: 1px solid #f1f5f9 !important;
}

.stDataFrame tr:hover td {
    background-color: #f8fafc !important;
}

/* ====== 标签页样式 ====== */
.stTabs [data-baseweb="tab-list"] {
    gap: 0;
    background: #f1f5f9;
    border-radius: 10px;
    padding: 4px;
}

.stTabs [data-baseweb="tab"] {
    background: transparent;
    border-radius: 8px;
    padding: 10px 20px;
    font-weight: 500;
    font-size: 0.875rem;
    color: #64748b;
    border: none;
    transition: all 0.2s ease;
}

.stTabs [data-baseweb="tab"]:hover {
    color: #334155;
    background: rgba(255, 255, 255, 0.5);
}

.stTabs [aria-selected="true"] {
    background: #ffffff !important;
    color: #1e293b !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.stTabs [data-baseweb="tab-panel"] {
    padding-top: 1.5rem;
}

/* ====== 筛选器区域 ====== */
.filter-container {
    background: #f8fafc;
    padding: 1.25rem;
    border-radius: 12px;
    margin-bottom: 1.5rem;
    border: 1px solid #e2e8f0;
}

/* ====== 超限警示 ====== */
.overlimit-warning {
    background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
    border: 1px solid #fecaca;
    border-radius: 8px;
    padding: 12px 16px;
    color: #991b1b;
    font-weight: 500;
}

/* ====== 下载按钮 ====== */
.stDownloadButton > button {
    background: #10b981;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 0.5rem 1rem;
    font-size: 0.8rem;
    font-weight: 500;
}

.stDownloadButton > button:hover {
    background: #059669;
    box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
}

/* ====== 分隔线 ====== */
hr {
    margin: 1.5rem 0;
    border: none;
    border-top: 1px solid #e2e8f0;
}

/* ====== 警示框 ====== */
.stAlert {
    border-radius: 10px;
    border: none;
}

div[data-testid="stAlert"] > div {
    padding: 12px 16px;
    border-radius: 10px;
}

/* 信息框 */
div[data-baseweb="notification"][kind="info"] {
    background: #eff6ff;
    border-left: 4px solid #3b82f6;
}

/* 警告框 */
div[data-baseweb="notification"][kind="warning"] {
    background: #fefce8;
    border-left: 4px solid #eab308;
}

/* 错误框 */
div[data-baseweb="notification"][kind="negative"] {
    background: #fef2f2;
    border-left: 4px solid #ef4444;
}

/* 成功框 */
div[data-baseweb="notification"][kind="positive"] {
    background: #f0fdf4;
    border-left: 4px solid #22c55e;
}

/* ====== 标题样式 ====== */
h1 {
    color: #0f172a;
    font-weight: 700;
    font-size: 1.75rem;
    margin-bottom: 0.5rem;
    letter-spacing: -0.5px;
}

h2 {
    color: #1e293b;
    font-weight: 600;
    font-size: 1.25rem;
    margin-top: 1.5rem;
    margin-bottom: 1rem;
}

h3 {
    color: #334155;
    font-weight: 600;
    font-size: 1rem;
}

/* ====== 输入控件 ====== */
.stTextInput > div > div > input,
.stSelectbox > div > div,
.stMultiSelect > div > div,
.stDateInput > div > div > input {
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    font-size: 0.875rem;
    transition: all 0.2s ease;
}

.stTextInput > div > div > input,
.stSelectbox [data-baseweb="select"] > div,
.stMultiSelect [data-baseweb="select"] > div,
.stDateInput > div > div > input {
    background: #ffffff;
    min-height: 42px;
}

.stTextInput > div > div > input:focus,
.stSelectbox > div > div:focus-within,
.stMultiSelect > div > div:focus-within {
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
}

.stMultiSelect [data-baseweb="select"] {
    border-radius: 8px;
}

.stMultiSelect [data-baseweb="select"] input {
    color: #1e293b !important;
    font-size: 0.875rem;
}

.stMultiSelect [data-baseweb="select"] input::placeholder {
    color: #94a3b8;
}

.stMultiSelect [data-baseweb="tag"] {
    background: #eff6ff !important;
    border: 1px solid #bfdbfe !important;
    border-radius: 6px !important;
    color: #1d4ed8 !important;
    min-height: 24px !important;
    margin: 2px 4px 2px 0 !important;
}

.stMultiSelect [data-baseweb="tag"] span {
    color: #1d4ed8 !important;
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    line-height: 1.2 !important;
    max-width: 180px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.stMultiSelect [data-baseweb="tag"] svg {
    fill: #2563eb !important;
    width: 14px;
    height: 14px;
}

.stMultiSelect [data-baseweb="tag"]:hover {
    background: #dbeafe !important;
    border-color: #93c5fd !important;
}

div[data-baseweb="popover"] [role="listbox"],
div[data-baseweb="popover"] ul {
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    box-shadow: 0 12px 28px rgba(15, 23, 42, 0.12);
    padding: 6px;
}

div[data-baseweb="popover"] [role="option"] {
    border-radius: 6px;
    color: #334155;
    font-size: 0.875rem;
}

div[data-baseweb="popover"] [role="option"]:hover {
    background: #f1f5f9;
}

div[data-baseweb="popover"] [aria-selected="true"] {
    background: #eff6ff !important;
    color: #1d4ed8 !important;
    font-weight: 600;
}

/* ====== 加载动画 ====== */
.stSpinner > div {
    border-top-color: #3b82f6 !important;
}

/* 隐藏 Streamlit 默认的加载/状态框，避免页面切换时出现缓存提示框 */
div[data-testid="stSpinner"],
div[data-testid="stStatusWidget"],
.stSpinner {
    display: none !important;
}

/* ====== 进度条 ====== */
.stProgress > div > div > div {
    background: linear-gradient(90deg, #3b82f6 0%, #2563eb 100%) !important;
    border-radius: 4px;
}

/* ====== Expander ====== */
.streamlit-expanderHeader {
    background: #f8fafc;
    border-radius: 8px;
    font-weight: 500;
    font-size: 0.875rem;
}

/* ====== 状态标签 ====== */
.status-normal {
    display: inline-block;
    padding: 4px 10px;
    background: #dcfce7;
    color: #166534;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
}

.status-overlimit {
    display: inline-block;
    padding: 4px 10px;
    background: #fee2e2;
    color: #991b1b;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
}

/* ====== 打印样式 ====== */
@media print {
    .stApp {
        background: white;
    }
    
    .main .block-container {
        box-shadow: none;
        padding: 0;
    }
    
    section[data-testid="stSidebar"] {
        display: none;
    }
    
    .stButton, .stDownloadButton {
        display: none;
    }
}

/* ====== 响应式调整 ====== */
@media (max-width: 768px) {
    .main .block-container {
        padding: 1rem;
    }
    
    div[data-testid="stMetric"] {
        padding: 1rem;
    }
    
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
    }
}
</style>
"""


def apply_custom_styles():
    """应用自定义样式"""
    import streamlit as st
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
