"""
表格展示组件 - 现代金融看板风格
"""
import streamlit as st
import pandas as pd
import numpy as np
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
    
    # 日期列转为字符串，避免 PyArrow 序列化 object/datetime 混合时报错
    if '日期' in display_df.columns:
        display_df['日期'] = pd.to_datetime(display_df['日期'], errors='coerce').dt.strftime('%Y-%m-%d').fillna('')
    
    # 百分比列名关键词（用于识别需要按百分比显示的列）
    percentage_keywords = ['集中度', '比例', '占比', '率', '%']
    # 列名包含以下任一则为「金额/剩余额度」列，不按百分比格式化（单位：万元等）
    quota_exclude_keywords = ['剩余额度(万)', '剩余额度（万）']

    def is_percentage_column(col_name):
        """判断是否为百分比列（排除「剩余额度(万)」等金额列）"""
        name = str(col_name)
        if any(kw in name for kw in quota_exclude_keywords):
            return False
        return any(kw in name for kw in percentage_keywords)

    # 计算总计值（在修改 display_df 之前，用原始数值）
    total_values = {}
    if add_total_row and total_columns:
        for col in total_columns:
            if col in display_df.columns and pd.api.types.is_numeric_dtype(display_df[col].dtype):
                total_values[col] = display_df[col].sum()

    # 保持数值/日期类型以便列头排序正确；仅对「百分比列」做缩放便于用 column_config 显示为 X.XX%
    for col in display_df.columns:
        if pd.api.types.is_numeric_dtype(display_df[col].dtype):
            if is_percentage_column(col):
                # 0-1 的小数转为 0-100，便于 column_config 用 "%.2f%%" 显示且排序仍按数值
                def scale_pct(x):
                    if pd.isna(x):
                        return x
                    return x * 100 if abs(x) <= 1 else x
                display_df[col] = display_df[col].apply(scale_pct)
        # 非数值列：清理 nan 等，保持原类型供展示
        elif not pd.api.types.is_datetime64_any_dtype(display_df[col].dtype):
            display_df[col] = display_df[col].astype(str).replace('nan', '').replace('NaT', '').replace('None', '')

    # 在添加总计行之前根据当前列类型构建 column_config（避免总计行把首列变为 object 后类型判断错误）
    column_config = {}
    for col in display_df.columns:
        if pd.api.types.is_datetime64_any_dtype(display_df[col].dtype):
            column_config[col] = st.column_config.DatetimeColumn(col, format="YYYY-MM-DD")
        elif pd.api.types.is_numeric_dtype(display_df[col].dtype):
            if col == '内部证券账户覆盖数':
                column_config[col] = st.column_config.NumberColumn(col, format="%d")
            elif is_percentage_column(col):
                column_config[col] = st.column_config.NumberColumn(col, format="%.2f%%")
            else:
                column_config[col] = st.column_config.NumberColumn(col, format="%.2f")
        elif col == '代码':
            column_config[col] = st.column_config.TextColumn("ISIN码/资产代码", width="medium")
        elif col in {'资产名称', '证券名称'}:
            column_config[col] = st.column_config.TextColumn(col, width="medium")
        elif col == '债券分类2':
            column_config[col] = st.column_config.TextColumn("债券分类", width="small")
        # 非数值非日期列不设 column_config，使用默认展示

    # 添加总计行（数值列保持数值类型，便于 column_config 统一格式化与排序）
    # 说明：未参与合计的数值列填 pd.NA，以保持列类型为数值、列头排序正常；Streamlit 会将该行标为含缺失值（行首可能显示小叹号），
    # 且 st.column_config.NumberColumn 无“将 null 显示为空”的配置，故 NA 的展示由 Streamlit 决定（多为空白或 "None"）。
    if add_total_row and total_columns and total_values:
        total_row = {}
        for col in display_df.columns:
            if col in total_values:
                total_row[col] = total_values[col]
            elif col == display_df.columns[0]:
                total_row[col] = "合计"
            elif pd.api.types.is_numeric_dtype(display_df[col].dtype):
                total_row[col] = np.nan  # 用 np.nan 便于 astype(float)，避免 pd.NA 转 float 报 NAType 错误
            else:
                total_row[col] = ""
        # 按 display_df 的列顺序和类型构造总计行，避免 concat 时的 FutureWarning（空/全 NA 列推断行为变更）
        total_df = pd.DataFrame([total_row], columns=display_df.columns)
        for col in display_df.columns:
            if col in total_df.columns and display_df[col].dtype != total_df[col].dtype:
                try:
                    total_df[col] = total_df[col].astype(display_df[col].dtype)
                except (TypeError, ValueError):
                    # 含 nan 的列无法转为整数等，保持原类型，concat 时会自动兼容（如 int+float→float）
                    pass
        display_df = pd.concat([display_df, total_df], ignore_index=True)
    
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
    
    # 显示表格（column_config 仅控制显示格式，列仍为数值/日期类型，列头排序正确）
    st.dataframe(
        display_df,
        width='stretch',
        height=height,
        hide_index=True,
        column_config=column_config
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


def aggregate_by_asset_and_account(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    按 日期+资产代码+内部证券账户名称 聚合明细展示（page1/2/3 共用）。

    规则：
    - 仅对「库存数量(万)_PR」求和
    - 其余字段在组内一致时取首条
    - 若组内非求和字段存在差异，则该组保留原明细，不做合并
    返回：(聚合后的 DataFrame, 无法合并的组数)
    """
    group_keys = ['日期', '资产代码', '内部证券账户名称']
    sum_columns = {'库存数量(万)_PR'}
    ignored_columns = {'合并辅助列'}

    if df.empty or any(col not in df.columns for col in group_keys):
        return df, 0

    working_df = df.copy()
    duplicate_mask = working_df.duplicated(group_keys, keep=False)
    duplicate_df = working_df[duplicate_mask]
    non_duplicate_df = working_df[~duplicate_mask]

    if duplicate_df.empty:
        return working_df, 0

    aggregated_rows = []
    unresolved_groups = []

    for _, group in duplicate_df.groupby(group_keys, sort=False, dropna=False):
        varying_columns = [
            col for col in group.columns
            if col not in group_keys and col not in sum_columns and col not in ignored_columns
            and group[col].nunique(dropna=False) > 1
        ]
        if varying_columns:
            unresolved_groups.append(group)
            continue

        row = group.iloc[0].copy()
        if '库存数量(万)_PR' in group.columns:
            row['库存数量(万)_PR'] = group['库存数量(万)_PR'].sum()
        aggregated_rows.append(row)

    parts = [non_duplicate_df]
    if aggregated_rows:
        parts.append(pd.DataFrame(aggregated_rows))
    if unresolved_groups:
        parts.append(pd.concat(unresolved_groups, ignore_index=True))

    return pd.concat(parts, ignore_index=True), len(unresolved_groups)


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
