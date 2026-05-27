"""
验证持仓总计是否恢复到正确值
检查修复后的持仓总计是否约为 122.7 亿
"""
import sys
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

def main():
    print("=" * 80)
    print("验证持仓总计修复效果")
    print("=" * 80)
    
    # 1. 债券持仓明细表_信用债（merge前，基准值）
    base_path = PROJECT_ROOT / "data/current/stage1_output/债券持仓明细表_信用债.xlsx"
    if base_path.exists():
        print("\n【1】债券持仓明细表_信用债（merge前 - 基准值）")
        df_base = pd.read_excel(base_path)
        base_total_wan = df_base['库存数量(万)_PR'].sum()
        base_total_yi = base_total_wan / 10000
        print(f"  总行数: {len(df_base)}")
        print(f"  总持仓(万): {base_total_wan:,.2f}")
        print(f"  总持仓(亿): {base_total_yi:,.2f}")
    else:
        print(f"\n[跳过] 基准数据不存在: {base_path}")
        base_total_yi = None
    
    # 2. 债券持仓明细表_信用债_合并风险限额相关（merge后）
    merged_path = PROJECT_ROOT / "data/current/stage1_output/债券持仓明细表_信用债_合并风险限额相关.xlsx"
    if merged_path.exists():
        print("\n【2】债券持仓明细表_信用债_合并风险限额相关（merge后）")
        df_merged = pd.read_excel(merged_path)
        merged_total_wan = df_merged['库存数量(万)_PR'].sum()
        merged_total_yi = merged_total_wan / 10000
        print(f"  总行数: {len(df_merged)}")
        print(f"  总持仓(万): {merged_total_wan:,.2f}")
        print(f"  总持仓(亿): {merged_total_yi:,.2f}")
        
        # 检查重复的业务key
        key_cols = ['日期', '资产代码', '内部证券账户名称', '库存数量(万)_PR']
        duplicates = df_merged[df_merged.duplicated(subset=key_cols, keep=False)]
        print(f"  重复的业务key记录数: {len(duplicates)}")
        
        if base_total_yi is not None:
            diff_yi = merged_total_yi - base_total_yi
            diff_pct = (diff_yi / base_total_yi) * 100
            print(f"\n  【差异分析】merge前后持仓总计差异:")
            print(f"    差异(亿): {diff_yi:,.2f}")
            print(f"    差异比例: {diff_pct:.2f}%")
            
            if abs(diff_yi) < 0.1:
                print(f"    ✅ 差异很小（<0.1亿），merge 未增加持仓")
            elif abs(diff_yi) < 1:
                print(f"    ⚠️  差异较小（<1亿），可接受范围")
            else:
                print(f"    ❌ 差异较大（≥1亿），需要检查")
    else:
        print(f"\n[跳过] merge后数据不存在: {merged_path}")
        merged_total_yi = None
    
    # 3. 单一主体总持仓
    issuer_path = PROJECT_ROOT / "data/current/stage1_output/单一主体总持仓.xlsx"
    if issuer_path.exists():
        print("\n【3】单一主体总持仓")
        df_issuer = pd.read_excel(issuer_path)
        issuer_total_wan = df_issuer['单一主体总持仓_PR'].sum()
        issuer_total_yi = issuer_total_wan / 10000
        print(f"  总行数: {len(df_issuer)}")
        print(f"  总持仓(万): {issuer_total_wan:,.2f}")
        print(f"  总持仓(亿): {issuer_total_yi:,.2f}")
        
        if base_total_yi is not None:
            diff = issuer_total_yi - base_total_yi
            print(f"  与基准差异(亿): {diff:,.2f}")
    else:
        print(f"\n[跳过] 单一主体总持仓不存在: {issuer_path}")
    
    # 4. 单一实控人总持仓
    controller_path = PROJECT_ROOT / "data/current/stage1_output/单一实控人总持仓.xlsx"
    if controller_path.exists():
        print("\n【4】单一实控人总持仓")
        df_ctrl = pd.read_excel(controller_path)
        ctrl_total_wan = df_ctrl['单一实控人总持仓_PR'].sum()
        ctrl_total_yi = ctrl_total_wan / 10000
        print(f"  总行数: {len(df_ctrl)}")
        print(f"  总持仓(万): {ctrl_total_wan:,.2f}")
        print(f"  总持仓(亿): {ctrl_total_yi:,.2f}")
        
        if base_total_yi is not None:
            diff = ctrl_total_yi - base_total_yi
            print(f"  与基准差异(亿): {diff:,.2f}")
    else:
        print(f"\n[跳过] 单一实控人总持仓不存在: {controller_path}")
    
    # 5. 总结
    print("\n" + "=" * 80)
    print("【总结】")
    print("=" * 80)
    if base_total_yi is not None and merged_total_yi is not None:
        print(f"✅ 基准持仓（merge前）: {base_total_yi:,.2f} 亿")
        print(f"✅ 当前持仓（merge后）: {merged_total_yi:,.2f} 亿")
        print(f"✅ 预期正确值: 约 122.7 亿")
        
        # 判断是否接近预期
        expected = 122.7
        if abs(base_total_yi - expected) < 2:
            print(f"✅ 当前值接近预期正确值！")
        elif abs(base_total_yi - expected) < 5:
            print(f"⚠️  当前值与预期有一定差异（{abs(base_total_yi - expected):.1f}亿），但在可接受范围")
        else:
            print(f"❌ 当前值与预期差异较大（{abs(base_total_yi - expected):.1f}亿）")
    
    print("=" * 80)

if __name__ == "__main__":
    main()
