#!/usr/bin/env python3
"""
检查缺失的可转债在金融工具池和数据源中的情况
"""
import pandas as pd
from pathlib import Path
import sys

# 缺失的可转债列表
missing_bonds = [
    "力合转债", "浙矿转债", "锦鸡转债", "路维转债", "华亚转债",
    "利扬转债", "优彩转债", "宇邦转债", "艾录转债", "华医转债",
    "威唐转债", "中环转2", "华辰转债", "汇成转债", "佳禾转债",
    "东亚转债", "亿田转债", "福新转债"
]

data_dir = Path("限额")

print("=" * 80)
print("检查缺失的可转债")
print("=" * 80)

# 1. 检查金融工具池设置
print("\n【1】检查金融工具池设置.xlsx")
print("-" * 80)

tool_pool_file = data_dir / "金融工具池设置.xlsx"
if tool_pool_file.exists():
    try:
        # 尝试读取
        df_tool = pd.read_excel(tool_pool_file)
        print(f"✓ 成功读取，共 {len(df_tool)} 行")
        print(f"  列名: {list(df_tool.columns)}")
        
        # 筛选可转债
        if '品种' in df_tool.columns:
            df_convertible = df_tool[df_tool['品种'] == '可转债'].copy()
            print(f"  可转债记录: {len(df_convertible)} 行")
            
            if '简称' in df_convertible.columns:
                tool_names = set(df_convertible['简称'].dropna().astype(str).str.strip())
                print(f"  简称数量: {len(tool_names)} 个")
                
                # 检查缺失的债券
                print("\n  检查缺失债券是否在工具池中:")
                found_count = 0
                not_found = []
                for bond in missing_bonds:
                    if bond in tool_names:
                        print(f"    ✓ {bond} - 在工具池中")
                        found_count += 1
                    else:
                        print(f"    ✗ {bond} - 不在工具池中")
                        not_found.append(bond)
                
                print(f"\n  汇总: {found_count}/{len(missing_bonds)} 个在工具池中")
                
                if not_found:
                    print(f"\n  未找到的债券: {', '.join(not_found)}")
                    
                    # 尝试模糊匹配
                    print("\n  尝试模糊匹配（去掉'转债'/'转2'后缀）:")
                    for bond in not_found:
                        base_name = bond.replace('转债', '').replace('转2', '')
                        matches = [name for name in tool_names if base_name in name]
                        if matches:
                            print(f"    {bond} 可能对应: {matches}")
            
            if '代码' in df_convertible.columns:
                tool_codes = set(df_convertible['代码'].dropna().astype(str).str.strip())
                print(f"  代码数量: {len(tool_codes)} 个")
        else:
            print("  ⚠️ 缺少'品种'列，无法筛选可转债")
            
    except Exception as e:
        print(f"✗ 读取失败: {str(e)}")
else:
    print(f"✗ 文件不存在: {tool_pool_file}")

# 2. 检查债券持仓明细表_信用债
print("\n\n【2】检查债券持仓明细表_信用债中的可转债")
print("-" * 80)

# 检查stage1输出
stage1_output = Path("data/stage1_output/债券持仓明细表_信用债.xlsx")
if stage1_output.exists():
    try:
        df_credit = pd.read_excel(stage1_output)
        print(f"✓ 成功读取，共 {len(df_credit)} 行")
        print(f"  列名: {list(df_credit.columns)}")
        
        if '资产名称' in df_credit.columns:
            asset_names = df_credit['资产名称'].dropna().astype(str).str.strip()
            
            print("\n  检查缺失债券是否在持仓数据中:")
            found_count = 0
            not_found = []
            for bond in missing_bonds:
                matches = df_credit[asset_names == bond]
                if len(matches) > 0:
                    print(f"    ✓ {bond} - 在持仓中 ({len(matches)} 条记录)")
                    if len(matches) <= 3 and '内部证券账户名称' in df_credit.columns:
                        for _, row in matches.iterrows():
                            account = row.get('内部证券账户名称', 'N/A')
                            code = row.get('资产代码', 'N/A')
                            print(f"        账户: {account}, 代码: {code}")
                    found_count += 1
                else:
                    not_found.append(bond)
                    # 尝试模糊匹配
                    base_name = bond.replace('转债', '').replace('转2', '')
                    fuzzy_matches = df_credit[asset_names.str.contains(base_name, na=False)]
                    if len(fuzzy_matches) > 0:
                        actual_names = fuzzy_matches['资产名称'].unique()
                        print(f"    ? {bond} - 不在持仓中，但找到类似: {list(actual_names)}")
                    else:
                        print(f"    ✗ {bond} - 不在持仓中")
            
            print(f"\n  汇总: {found_count}/{len(missing_bonds)} 个在持仓中")
        else:
            print("  ⚠️ 缺少'资产名称'列")
            
    except Exception as e:
        print(f"✗ 读取失败: {str(e)}")
else:
    print(f"⚠️  文件不存在: {stage1_output}")
    print("   请先运行 python3 run_stage1.py")

print("\n" + "=" * 80)
print("检查完成")
print("=" * 80)
