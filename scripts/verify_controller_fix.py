"""
验证实控人修复效果
检查精达转债的实控人是否正确显示为李光荣
"""
import sys
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

def main():
    print("=" * 80)
    print("验证实控人修复效果")
    print("=" * 80)
    
    # 1. 检查阶段0输出：调整实控人名单
    stage0_path = PROJECT_ROOT / "data/current/stage0_output/调整实控人名单.xlsx"
    if stage0_path.exists():
        print("\n【1】阶段0 - 调整实控人名单")
        df0 = pd.read_excel(stage0_path)
        print(f"  总记录数: {len(df0)}")
        print(f"  列: {list(df0.columns)}")
        
        # 检查李光荣相关主体
        if '调整后实际控制人' in df0.columns:
            li_records = df0[df0['调整后实际控制人'].astype(str).str.contains('李光荣', na=False)]
            print(f"  含「李光荣」的记录数: {len(li_records)}")
            if not li_records.empty:
                print("\n  示例记录:")
                cols = [c for c in ['主体wind代码', '主体名称', '调整后实际控制人'] if c in li_records.columns]
                print(li_records[cols].head(3).to_string(index=False))
        
        # 检查主体wind代码格式
        if '主体wind代码' in df0.columns:
            print("\n  主体wind代码格式示例（前5条）:")
            for i, code in enumerate(df0['主体wind代码'].head(5)):
                print(f"    {i+1}. {repr(code)}")
    else:
        print(f"\n[跳过] 阶段0输出不存在: {stage0_path}")
    
    # 2. 检查阶段1输出：债券持仓明细表_信用债_合并风险限额相关
    stage1_path = PROJECT_ROOT / "data/current/stage1_output/债券持仓明细表_信用债_合并风险限额相关.xlsx"
    if stage1_path.exists():
        print("\n【2】阶段1 - 债券持仓明细表_信用债_合并风险限额相关")
        df1 = pd.read_excel(stage1_path)
        print(f"  总记录数: {len(df1)}")
        
        # 查找精达转债
        if '资产名称' in df1.columns:
            jingda = df1[df1['资产名称'].astype(str).str.contains('精达', na=False)]
            print(f"  含「精达」的记录数: {len(jingda)}")
            
            if not jingda.empty:
                print("\n  精达转债记录:")
                cols = [c for c in ['资产代码', '资产名称', '债务主体', '债务主体wind代码', 
                                   '实际控制人名称_修正', '调整后实际控制人', '内部证券账户名称'] 
                       if c in jingda.columns]
                print(jingda[cols].to_string(index=False))
                
                # 检查实控人是否为李光荣
                if '实际控制人名称_修正' in jingda.columns:
                    controllers = jingda['实际控制人名称_修正'].unique()
                    print(f"\n  精达转债的实际控制人名称_修正: {controllers}")
                    if any('李光荣' in str(c) for c in controllers if pd.notna(c)):
                        print("  ✅ 实控人显示正确：李光荣")
                    else:
                        print("  ❌ 实控人显示错误：不是李光荣")
                        print("     请检查底稿或德勤表中该主体的实控人设置")
        else:
            print("  [警告] 无「资产名称」列")
    else:
        print(f"\n[跳过] 阶段1输出不存在: {stage1_path}")
    
    # 3. 检查单一实控人总持仓
    stage1_controller_path = PROJECT_ROOT / "data/current/stage1_output/单一实控人总持仓.xlsx"
    if stage1_controller_path.exists():
        print("\n【3】阶段1 - 单一实控人总持仓")
        df_ctrl = pd.read_excel(stage1_controller_path)
        print(f"  总记录数: {len(df_ctrl)}")
        
        if '实际控制人名称_修正' in df_ctrl.columns:
            # 查找李光荣
            li = df_ctrl[df_ctrl['实际控制人名称_修正'].astype(str).str.contains('李光荣', na=False)]
            if not li.empty:
                print("\n  李光荣的单一实控人总持仓:")
                cols = [c for c in ['日期', '业务分类', '实际控制人名称_修正', '单一实控人总持仓_PR'] 
                       if c in li.columns]
                print(li[cols].to_string(index=False))
            else:
                print("  [警告] 未找到李光荣的记录")
            
            # 统计实控人为None的记录
            null_count = df_ctrl['实际控制人名称_修正'].isna().sum()
            print(f"\n  实控人为None的记录数: {null_count}/{len(df_ctrl)}")
    else:
        print(f"\n[跳过] 单一实控人总持仓不存在: {stage1_controller_path}")
    
    print("\n" + "=" * 80)
    print("验证完成")
    print("=" * 80)

if __name__ == "__main__":
    main()
