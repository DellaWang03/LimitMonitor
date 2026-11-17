"""科创页面只读已归档结果，不查询 Wind，不修改共享筛选状态。"""
import logging
import pandas as pd
import streamlit as st

from src.scitech.store import ScitechStore
from src.utils.archive_db import ArchiveDB
from src.visualization.components.controls import render_metric_card, render_page_header

logger = logging.getLogger(__name__)


def load_snapshot(data_loader):
    identity = data_loader.get_snapshot_identity()
    return ScitechStore(ArchiveDB.from_env().engine).read(**identity)


def _table(rows, key, data_date, departments, accounts, query, empty_message):
    frame = pd.DataFrame(rows)
    if frame.empty:
        st.info(empty_message)
        return
    if departments:
        frame = frame[frame['部门'].isin(departments)]
    if accounts:
        frame = frame[frame['内部证券账户名称'].isin(accounts)]
    if query:
        mask = (frame['资产代码'].str.contains(query, case=False, regex=False)
                | frame['资产名称'].str.contains(query, case=False, regex=False))
        frame = frame[mask]
    if frame.empty:
        st.info('当前筛选条件下无记录。')
        return
    # 页面只显示业务可用的原因；完整取数诊断保存在后台运行记录。
    if '待核实原因' in frame:
        frame = frame.copy()
        frame['待核实原因'] = frame['待核实原因'].map(
            lambda value: '科创分类暂不可用，待核实' if 'Wind' in value else value)
    if '剩余天数' in frame:
        frame = frame.copy()
        frame['剩余天数'] = pd.array(frame['剩余天数'], dtype='Int64')
    column_config = {c: st.column_config.NumberColumn(c, format='%.2f')
                     for c in ('PR后券面(万元)', '持仓份额(万份)') if c in frame}
    ordered = ['资产代码', '资产名称', 'PR后券面(万元)', '持仓份额(万份)', '回售/到期日',
               '剩余天数', '监控状态', '待核实原因', '部门', '内部证券账户名称', '源行号']
    st.caption(f'共 {len(frame)} ' + ('项待核实' if key == 'issues' else '条持仓记录'))
    st.dataframe(frame, hide_index=True, use_container_width=True, column_config=column_config,
                 column_order=[c for c in ordered if c in frame])
    st.download_button('下载当前明细 CSV', frame.to_csv(index=False).encode('utf-8-sig'),
                       file_name=f'科创资产_{key}_{data_date}.csv', mime='text/csv',
                       key=f'scitech_export_{key}')


def render(filters, data_loader):
    del filters
    render_page_header('🔬 科创资产监控', '汇总所有部门及账户的直接持仓，关注七日内回售/到期事项。')
    identity = data_loader.get_snapshot_identity()
    st.caption(f"持仓日期：{identity['data_date']} · 提醒基准为持仓日，含当日及未来 7 个自然日")
    try:
        snapshot = load_snapshot(data_loader)
    except Exception:
        logger.exception('科创结果读取失败')
        st.error('该批次科创数据暂不可用，请刷新或联系维护人员核查。')
        return
    if snapshot is None:
        st.info('该批次尚未生成科创监控数据；未生成不代表零持仓或没有预警。')
        return
    if snapshot['status'] == 'RUNNING':
        st.info('该批次科创数据尚未完成，请稍后刷新。')
        return
    if snapshot['status'] == 'INTERRUPTED':
        st.error('该批次科创任务可能已中断，请联系维护人员独立补跑。未完成不代表零持仓或没有预警。')
        return
    if snapshot['status'] not in ('READY', 'PARTIAL') or not snapshot.get('result'):
        st.error('该批次科创数据生成失败，请联系维护人员核查底稿或取数状态。')
        return

    result = snapshot['result']
    summary, coverage = result['summary'], result['coverage']
    partial_bonds = coverage['bond_issues'] > 0
    partial_funds = coverage['fund_issues'] > 0
    bonds_available = coverage.get('bond_input_available', True)
    funds_available = coverage.get('fund_input_available', True)
    if not bonds_available:
        st.error('债券输入不可用，无法判断七日提醒；基金持仓可单独查看。')
    if not funds_available:
        st.error('基金输入不可用；债券持仓与七日提醒仍按有效债券数据展示。')
    if snapshot['status'] == 'PARTIAL':
        st.warning('本批次存在待核实记录。概览仅汇总已识别且数量有效的持仓。'
                   + ('债券提醒清单可能不完整，请查看“待核实”。' if partial_bonds
                      else '基金异常不影响债券提醒，请查看“待核实”。'))
    bond_unknown = partial_bonds and not any(r['PR后券面(万元)'] is not None for r in result['bonds'])
    fund_unknown = partial_funds and not any(r['持仓份额(万份)'] is not None for r in result['funds'])
    cards = [
        ('科创债 PR 后券面', '不可用' if not bonds_available else '待核实' if bond_unknown else f"{summary['bond_pr_wan']:,.2f}",
         '万元 · 全部部门' + (' · 含待核实' if partial_bonds else ''), 'neutral'),
        ('科创基金持仓', '不可用' if not funds_available else '待核实' if fund_unknown else f"{summary['fund_shares_wan']:,.2f}",
         '万份 · 全部部门' + (' · 含待核实' if partial_funds else ''), 'neutral'),
        ('七日内提醒债券', '不可用' if not bonds_available else '待核实' if partial_bonds and not result['alerts'] else str(summary['alert_bond_count']),
         '只 · 同券跨账户去重' + (' · 已确认部分' if partial_bonds else ''), 'warning' if result['alerts'] else 'neutral'),
        ('七日内提醒券面', '不可用' if not bonds_available else '待核实' if partial_bonds and not result['alerts'] else f"{summary['alert_pr_wan']:,.2f}",
         '万元 · 按持仓汇总' + (' · 已确认部分' if partial_bonds else ''), 'warning' if result['alerts'] else 'neutral'),
    ]
    for column, (label, value, caption, tone) in zip(st.columns(4), cards):
        with column:
            render_metric_card(label, value, caption, tone, min_height=136)
    st.caption('债券与基金分开计量；回售提醒不代表必然兑付，不据此扣减预计持仓。')
    with st.expander('查看统计口径'):
        st.write('债券取底稿1直接持仓，按 Wind scitechbondornot 识别，数量取库存数量(万)_PR。'
                 '不纳入底稿2穿透持仓。仅使用回售/到期日判断提醒。'
                 '基金取底稿3基金持仓明细表，仅资产种类为“基金”且名称含“科创”，库存数量折为万份；基金不做日期预警。'
                 '负数量按原值保留并列入待核实，不产生七日提醒。不设最低规模阈值。')
        queried_at = result.get('wind_queried_at')
        st.caption(f'分类取数时间（UTC）：{queried_at}；历史页面使用已保存的分类。'
                   if queried_at else '本批次没有可查询的债券分类记录。')

    rows = result['bonds'] + result['funds'] + result['issues']
    scope = f"{identity['data_date']}_{snapshot['result_version']}"
    st.write('明细筛选（不改变上方全部门概览）')
    left, middle, right = st.columns(3)
    with left:
        departments = st.multiselect('部门', sorted({r['部门'] for r in rows}),
                                     placeholder='全部部门', key=f'scitech_dept_{scope}')
    with middle:
        accounts = st.multiselect('账户', sorted({r['内部证券账户名称'] for r in rows}),
                                  placeholder='全部账户', key=f'scitech_account_{scope}')
    with right:
        query = st.text_input('证券代码或名称', key=f'scitech_search_{scope}').strip()
    specs = [('七日提醒', 'alerts', '已确认记录中暂无七日提醒。' if partial_bonds else '本持仓日暂无七日内回售/到期提醒。'),
             ('债券持仓', 'bonds', '已确认记录中暂无科创债。' if partial_bonds else '本持仓日无科创债持仓。'),
             ('基金持仓', 'funds', '已确认记录中暂无科创基金。' if partial_funds else '本持仓日无符合规则的科创基金持仓。'),
             ('待核实', 'issues', '暂无待核实记录。')]
    for tab, (_, key, empty_message) in zip(st.tabs([item[0] for item in specs]), specs):
        with tab:
            if not bonds_available and key in ('bonds', 'alerts'):
                empty_message = '债券输入不可用，暂无法提供债券持仓及七日提醒。'
            if not funds_available and key == 'funds':
                empty_message = '基金输入不可用，暂无法提供基金持仓。'
            _table(result[key], key, identity['data_date'], departments, accounts, query, empty_message)
