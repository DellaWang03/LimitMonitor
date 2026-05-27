#!/usr/bin/env python3
"""
诊断缺失可转债的原因
"""
import pandas as pd
from pathlib import Path
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)

# 缺失的可转债列表
MISSING_BONDS = [
    "力合转债", "浙矿转债", "锦鸡转债", "路维转债", "华亚转债",
    "利扬转债", "优彩转债", "宇邦转债", "艾录转债", "华医转债",
    "威唐转债", "中环转2", "华辰转债", "汇成转债", "佳禾转债",
    "东亚转债", "亿田转债", "福新转债"
]

def main():
    logger.info("=" * 100)
    logger.info("诊断缺失的可转债")
    logger.info("=" * 100)
    
    data_dir = Path("限额")
    
    # ========== 1. 检查金融工具池设置 ==========
    logger.info("\n【步骤1】检查金融工具池设置.xlsx")
    logger.info("-" * 100)
    
    tool_pool_file = data_dir / "金融工具池设置.xlsx"
    tool_pool_names = set()
    tool_pool_codes = set()
    
    if tool_pool_file.exists():
        try:
            df_tool = pd.read_excel(tool_pool_file)
            logger.info(f"✓ 成功读取，共 {len(df_tool)} 行")
            logger.info(f"  列名: {list(df_tool.columns)}")
            
            # 筛选可转债
            if '品种' in df_tool.columns:
                logger.info(f"\n  品种分布:")
                for variety, count in df_tool['品种'].value_counts().items():
                    logger.info(f"    - {variety}: {count} 行")
                
                df_convertible = df_tool[df_tool['品种'] == '可转债'].copy()
                logger.info(f"\n  ✓ 筛选后可转债: {len(df_convertible)} 行")
                
                if len(df_convertible) > 0:
                    # 简称处理
                    if '简称' in df_convertible.columns:
                        # 严格清洗
                        names = df_convertible['简称'].dropna()
                        names = names[names.astype(str).str.strip() != '']
                        names = names[names.astype(str).str.strip() != 'nan']
                        tool_pool_names = set(names.astype(str).str.strip().unique())
                        logger.info(f"  ✓ 有效简称: {len(tool_pool_names)} 个")
                        
                        # 打印前20个
                        logger.info(f"\n  前20个简称:")
                        for i, name in enumerate(sorted(tool_pool_names)[:20], 1):
                            logger.info(f"    {i}. {name}")
                    
                    # 代码处理
                    if '代码' in df_convertible.columns:
                        codes = df_convertible['代码'].dropna()
                        codes = codes[codes.astype(str).str.strip() != '']
                        codes = codes[codes.astype(str).str.strip() != 'nan']
                        tool_pool_codes = set(codes.astype(str).str.strip().unique())
                        logger.info(f"\n  ✓ 有效代码: {len(tool_pool_codes)} 个")
                else:
                    logger.warning("  ⚠️ 可转债筛选后为空")
            else:
                logger.warning("  ⚠️ 缺少'品种'列")
                
        except Exception as e:
            logger.error(f"✗ 读取失败: {type(e).__name__}: {str(e)}")
    else:
        logger.error(f"✗ 文件不存在: {tool_pool_file}")
    
    # ========== 2. 检查缺失债券是否在工具池中 ==========
    logger.info("\n\n【步骤2】检查缺失债券是否在金融工具池白名单中")
    logger.info("-" * 100)
    
    found_in_pool = []
    not_found_in_pool = []
    
    for bond in MISSING_BONDS:
        if bond in tool_pool_names:
            found_in_pool.append(bond)
            logger.info(f"  ✓ {bond} - 在白名单中")
        else:
            not_found_in_pool.append(bond)
            logger.info(f"  ✗ {bond} - 不在白名单中")
    
    logger.info(f"\n  汇总: {len(found_in_pool)}/{len(MISSING_BONDS)} 个在白名单中")
    
    if not_found_in_pool:
        logger.info(f"\n  ⚠️ 未在白名单中找到的债券: {', '.join(not_found_in_pool)}")
        
        # 尝试模糊匹配
        logger.info(f"\n  尝试模糊匹配:")
        for bond in not_found_in_pool:
            base_name = bond.replace('转债', '').replace('转2', '').replace('转换', '')
            matches = [name for name in tool_pool_names if base_name in name]
            if matches:
                logger.info(f"    {bond} → 可能对应: {matches}")
            else:
                logger.info(f"    {bond} → 无匹配")
    
    # ========== 3. 检查债券持仓数据 ==========
    logger.info("\n\n【步骤3】检查债券持仓明细表_信用债中的情况")
    logger.info("-" * 100)
    
    stage1_output = Path("data/stage1_output/债券持仓明细表_信用债.xlsx")
    if stage1_output.exists():
        try:
            df_credit = pd.read_excel(stage1_output)
            logger.info(f"✓ 成功读取，共 {len(df_credit)} 行")
            
            if '资产名称' in df_credit.columns:
                for bond in MISSING_BONDS:
                    matches = df_credit[df_credit['资产名称'].astype(str).str.strip() == bond]
                    if len(matches) > 0:
                        logger.info(f"\n  ✓ {bond} - 在持仓中 ({len(matches)} 条)")
                        for idx, row in matches.head(3).iterrows():
                            account = row.get('内部证券账户名称', 'N/A')
                            code = row.get('资产代码', 'N/A')
                            isin = row.get('ISIN码', 'N/A')
                            logger.info(f"      - 账户: {account}")
                            logger.info(f"        代码: {code}, ISIN: {isin}")
                            
                            # 诊断为什么没被识别
                            logger.info(f"        诊断:")
                            code_base = str(code).split('.')[0] if '.' in str(code) else str(code)
                            
                            if bond in tool_pool_names:
                                logger.info(f"          ✓ 简称'{bond}'在白名单中")
                            else:
                                logger.info(f"          ✗ 简称'{bond}'不在白名单中")
                            
                            if code_base in tool_pool_codes:
                                logger.info(f"          ✓ 代码'{code_base}'在白名单中")
                            else:
                                logger.info(f"          ✗ 代码'{code_base}'不在白名单中")
                            
                            if '高收益' in str(account):
                                logger.info(f"          ✓ 账户包含'高收益'")
                            else:
                                logger.info(f"          ✗ 账户不包含'高收益'")
                    else:
                        logger.info(f"\n  ✗ {bond} - 不在持仓中")
            else:
                logger.warning("  ⚠️ 缺少'资产名称'列")
                
        except Exception as e:
            logger.error(f"✗ 读取失败: {type(e).__name__}: {str(e)}")
    else:
        logger.warning(f"⚠️ 文件不存在: {stage1_output}")
        logger.warning("   请先运行: python3 run_stage1.py")
    
    logger.info("\n" + "=" * 100)
    logger.info("诊断完成")
    logger.info("=" * 100)

if __name__ == '__main__':
    main()
