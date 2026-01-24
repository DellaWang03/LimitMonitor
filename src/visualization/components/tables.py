"""
表格展示组件 - 现代金融看板风格
"""
import streamlit as st
import pandas as pd
from io import BytesIO


def highlight_overlimit_rows(row, highlight_column='是否超限'):
    """
    超限行高亮样式函数
    
    Args:
        row: DataFrame行
        highlight_column: 判断超限的列名
        
    Returns:
        list: 样式列表
    """
    if highlight_column in row.index and row[highlight_column] == '是':
        return ['background-color: #fef2f2; color: #991b1b; font-weight: 600'] * len(row)
    return [''] * len(row)


def format_number(val, is_percentage=False):
    """
    格式化数字显示（仅用于最终展示，不影响中间计算精度）
    
    Args:
        val: 数值
        is_percentage: 是否为百分比（小数形式，如0.05表示5%）
        
    Returns:
        str: 格式化后的字符串
    """
    if pd.isna(val):
        return ''
    if isinstance(val, (int, float)):
        if is_percentage:
            # 百分比：保留2位小数（对应原小数4位精度）
            return f"{val * 100:.2f}%"
        else:
            # 普通数值：统一保留2位小数
            return f"{val:,.2f}"
    return str(val)


def render_data_table(
    df: pd.DataFrame,
    title: str = None,
    highlight_column: str = '是否超限',
    height: int = 600,
    show_summary: bool = True,
    enable_export: bool = True,
    export_key: str = None,
    add_total_row: bool = False,
    total_columns: list = None
):
    """
    渲染数据表格（带超限高亮和导出功能）
    
    Args:
        df: 数据DataFrame
        title: 表格标题
        highlight_column: 超限判断列名
        height: 表格高度
        show_summary: 是否显示底部统计
        enable_export: 是否显示导出按钮
        add_total_row: 是否添加总计行
        total_columns: 需要计算总计的列名列表
    """
    if title:
        st.markdown(f"#### {title}")
    
    if len(df) == 0:
        st.markdown("""
        <div style="background: #fefce8; border: 1px solid #fde047; border-radius: 8px; padding: 16px; text-align: center;">
            <span style="color: #854d0e;">📭 没有符合条件的数据</span>
        </div>
        """, unsafe_allow_html=True)
        return
    
    # 准备显示数据（不影响原始数据精度）
    display_df = df.copy()
    
    # 百分比列名关键词（用于识别需要特殊格式化的列）
    percentage_keywords = ['集中度', '比例', '占比', '率', '%']
    
    def is_percentage_column(col_name):
        """判断是否为百分比列"""
        return any(kw in str(col_name) for kw in percentage_keywords)
    
    def format_cell(val, is_pct=False):
        """格式化单元格值（智能保留小数位）"""
        if pd.isna(val):
            return ''
        if isinstance(val, (int, float)):
            if is_pct and abs(val) <= 1:
                # 百分比列且值在0-1范围：转换为百分比显示（最多2位小数）
                pct_val = val * 100
                if pct_val == int(pct_val):
                    return f"{int(pct_val)}%"
                elif abs(pct_val * 10 - int(pct_val * 10)) < 0.01:
                    return f"{pct_val:.1f}%"
                else:
                    return f"{pct_val:.2f}%"
            elif is_pct:
                # 百分比列但值已经是百分比形式（>1）
                if val == int(val):
                    return f"{int(val)}%"
                elif abs(val * 10 - int(val * 10)) < 0.01:
                    return f"{val:.1f}%"
                else:
                    return f"{val:.2f}%"
            else:
                # 普通数值：智能保留小数位（整数不显示小数点，最多2位小数）
                if val == int(val):
                    # 整数：不显示小数点
                    return f"{int(val):,}"
                elif abs(val * 10 - int(val * 10)) < 0.01:
                    # 一位小数
                    return f"{val:,.1f}"
                else:
                    # 两位或更多小数：最多保留2位
                    return f"{val:,.2f}"
        return str(val)
    
    # 预处理：将datetime列转换为字符串格式
    for col in display_df.columns:
        if pd.api.types.is_datetime64_any_dtype(display_df[col]):
            display_df[col] = display_df[col].dt.strftime('%Y-%m-%d')
    
    # 计算总计值（在格式化之前）
    total_values = {}
    if add_total_row and total_columns:
        for col in total_columns:
            if col in display_df.columns and pd.api.types.is_numeric_dtype(display_df[col].dtype):
                total_values[col] = display_df[col].sum()
    
    # 格式化所有数值列（统一保留2位小数）
    for col in display_df.columns:
        if pd.api.types.is_numeric_dtype(display_df[col].dtype):
            is_pct = is_percentage_column(col)
            display_df[col] = display_df[col].apply(lambda x, p=is_pct: format_cell(x, p))
        else:
            # 非数值列：转为字符串，清理nan
            display_df[col] = display_df[col].astype(str).replace('nan', '').replace('NaT', '').replace('None', '')
    
    # 添加总计行
    if add_total_row and total_columns and total_values:
        total_row = {}
        for col in display_df.columns:
            if col in total_values:
                val = total_values[col]
                is_pct = is_percentage_column(col)
                total_row[col] = format_cell(val, is_pct)
            elif col == display_df.columns[0]:
                total_row[col] = "合计"
            else:
                total_row[col] = ""
        
        display_df = pd.concat([display_df, pd.DataFrame([total_row])], ignore_index=True)
    
    # 底部统计和操作栏（放在表格上方）
    if show_summary or enable_export:
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            if show_summary:
                total_rows = len(df)
                if highlight_column in df.columns:
                    overlimit_count = len(df[df[highlight_column] == '是'])
                    normal_count = total_rows - overlimit_count
                    
                    st.markdown(f"""
                    <div style="display: flex; gap: 16px; align-items: center;">
                        <span style="background: #f1f5f9; padding: 6px 12px; border-radius: 6px; font-size: 0.8rem;">
                            📊 共 <strong>{total_rows}</strong> 条
                        </span>
                        <span style="background: #dcfce7; color: #166534; padding: 6px 12px; border-radius: 6px; font-size: 0.8rem;">
                            ✓ 正常 <strong>{normal_count}</strong>
                        </span>
                        <span style="background: #fee2e2; color: #991b1b; padding: 6px 12px; border-radius: 6px; font-size: 0.8rem;">
                            ⚠ 超限 <strong>{overlimit_count}</strong>
                        </span>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div style="background: #f1f5f9; padding: 6px 12px; border-radius: 6px; font-size: 0.8rem; display: inline-block;">
                        📊 共 <strong>{total_rows}</strong> 条记录
                    </div>
                    """, unsafe_allow_html=True)
        
        with col3:
            if enable_export:
                # Excel导出（导出包含总计行的数据）
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    display_df.to_excel(writer, index=False, sheet_name='数据')
                excel_data = output.getvalue()
                
                st.download_button(
                    label="📥 导出",
                    data=excel_data,
                    file_name=f"{title or '数据'}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=export_key or f"export_{id(df)}"
                )
    
    # 添加间距
    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    
    # 显示表格
    st.dataframe(
        display_df,
        use_container_width=True,
        height=height,
        hide_index=True
    )


def render_summary_card(title: str, value: str, delta: str = None, delta_color: str = "normal"):
    """
    渲染汇总指标卡片
    
    Args:
        title: 指标名称
        value: 指标值
        delta: 变化值
        delta_color: 变化颜色 ("normal", "inverse", "off")
    """
    st.metric(
        label=title,
        value=value,
        delta=delta,
        delta_color=delta_color
    )


def render_kpi_row(metrics: dict):
    """
    渲染KPI指标行
    
    Args:
        metrics: 指标字典，格式：{'指标名': {'value': '值', 'delta': '变化'}}
    """
    cols = st.columns(len(metrics))
    
    for col, (title, data) in zip(cols, metrics.items()):
        with col:
            render_summary_card(
                title=title,
                value=data.get('value', '0'),
                delta=data.get('delta'),
                delta_color=data.get('delta_color', 'normal')
            )
