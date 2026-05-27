"""
阶段0：配置与原始数据校验
"""
import pandas as pd
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from compare_utils import CompareUtils


def validate_stage0():
    """校验阶段0配置数据"""
    print("\n" + "🔍" * 40)
    print("开始阶段0校验：配置与原始数据")
    print("🔍" * 40 + "\n")
    
    utils = CompareUtils()
    all_results = []
    
    # ========== 1. 净资产配置 ==========
    print("\n📋 [1/4] 校验净资产配置...")
    try:
        net_asset_file = project_root / "sample data" / "净资产.xlsx"
        df_net_asset = pd.read_excel(net_asset_file)
        
        print(f"✅ 净资产文件加载成功")
        print(f"   行数: {len(df_net_asset)}")
        print(f"   列名: {list(df_net_asset.columns)}")
        
        if '公司净资产(万)' in df_net_asset.columns:
            net_asset_value = df_net_asset['公司净资产(万)'].iloc[0]
            print(f"   净资产值: {net_asset_value:,.0f} 万元")
            
            # 对比代码中使用的值（从阶段2输出中验证）
            stage2_file = project_root / "data" / "stage2_output" / "限额明细_地域集中度限额(含城投).xlsx"
            if stage2_file.exists():
                df_stage2 = pd.read_excel(stage2_file)
                if '公司净资产(万)' in df_stage2.columns:
                    stage2_net_asset = df_stage2['公司净资产(万)'].iloc[0]
                    match = abs(net_asset_value - stage2_net_asset) < 0.01
                    print(f"   Stage2使用值: {stage2_net_asset:,.0f} 万元")
                    print(f"   {'✅ 一致' if match else '❌ 不一致'}")
        
    except Exception as e:
        print(f"❌ 净资产校验失败: {e}")
    
    # ========== 2. 高风险行业配置 ==========
    print("\n📋 [2/4] 校验高风险行业配置...")
    try:
        config_file = project_root / "sample data" / "限额监控_阶段0_指标设置.xlsx"
        df_ref_industry = pd.read_excel(config_file, sheet_name="高风险行业表")
        
        # 从Stage2输出中读取
        stage2_industry_file = project_root / "data" / "stage2_output" / "高风险行业.xlsx"
        if stage2_industry_file.exists():
            df_output_industry = pd.read_excel(stage2_industry_file)
            
            result = utils.compare_basic_structure(
                df_ref_industry, 
                df_output_industry, 
                "高风险行业配置"
            )
            
            # 对比行业数量
            ref_count = df_ref_industry['行业名称'].nunique()
            out_count = df_output_industry['行业名称'].nunique()
            result["检查项"].append({
                "项目": "唯一行业数量",
                "参考值": ref_count,
                "实际值": out_count,
                "通过": ref_count == out_count,
                "状态": "✅" if ref_count == out_count else "❌"
            })
            
            utils.print_result(result)
            all_results.append(result)
        else:
            print(f"⚠️ Stage2输出文件不存在: {stage2_industry_file}")
            
    except Exception as e:
        print(f"❌ 高风险行业校验失败: {e}")
    
    # ========== 3. 高风险省份配置 ==========
    print("\n📋 [3/4] 校验高风险省份配置...")
    try:
        df_ref_province = pd.read_excel(config_file, sheet_name="高风险省份表")
        
        stage2_province_file = project_root / "data" / "stage2_output" / "高风险省份.xlsx"
        if stage2_province_file.exists():
            df_output_province = pd.read_excel(stage2_province_file)
            
            result = utils.compare_basic_structure(
                df_ref_province, 
                df_output_province, 
                "高风险省份配置"
            )
            
            # 对比省份数量
            ref_count = df_ref_province['省份名称'].nunique()
            out_count = df_output_province['省份名称'].nunique()
            result["检查项"].append({
                "项目": "唯一省份数量",
                "参考值": ref_count,
                "实际值": out_count,
                "通过": ref_count == out_count,
                "状态": "✅" if ref_count == out_count else "❌"
            })
            
            utils.print_result(result)
            all_results.append(result)
        else:
            print(f"⚠️ Stage2输出文件不存在: {stage2_province_file}")
            
    except Exception as e:
        print(f"❌ 高风险省份校验失败: {e}")
    
    # ========== 4. 地域集中度限额配置 ==========
    print("\n📋 [4/4] 校验地域集中度限额配置...")
    try:
        df_ref_region = pd.read_excel(config_file, sheet_name="单一省份限额")
        
        stage2_region_file = project_root / "data" / "stage2_output" / "地域集中度限额(含城投).xlsx"
        if stage2_region_file.exists():
            df_output_region = pd.read_excel(stage2_region_file)
            
            result = utils.compare_basic_structure(
                df_ref_region, 
                df_output_region, 
                "地域集中度限额配置"
            )
            
            # 对比省份数量
            ref_count = df_ref_region['指标名称'].nunique()
            out_count = df_output_region['指标名称'].nunique()
            result["检查项"].append({
                "项目": "省份/地区数量",
                "参考值": ref_count,
                "实际值": out_count,
                "通过": ref_count == out_count,
                "状态": "✅" if ref_count == out_count else "❌"
            })
            
            utils.print_result(result)
            all_results.append(result)
        else:
            print(f"⚠️ Stage2输出文件不存在: {stage2_region_file}")
            
    except Exception as e:
        print(f"❌ 地域集中度限额校验失败: {e}")
    
    # ========== 总结 ==========
    print("\n" + "=" * 80)
    print("📊 阶段0校验完成")
    print("=" * 80)
    
    total_checks = sum(len(r["检查项"]) for r in all_results)
    passed_checks = sum(
        sum(1 for item in r["检查项"] if item.get("通过", False))
        for r in all_results
    )
    
    print(f"\n✅ 总通过率: {passed_checks}/{total_checks} ({passed_checks/total_checks*100 if total_checks > 0 else 0:.1f}%)")
    
    return all_results


if __name__ == "__main__":
    validate_stage0()
