"""
阶段2：高风险与地域集中度校验
重点校验：地域集中度、高风险行业、高风险省份、信用债2
"""
import pandas as pd
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from validation.compare_utils import CompareUtils


def validate_stage2_core_tables():
    """校验阶段2的核心表（P0级）"""
    print("\n" + "🔍" * 40)
    print("开始阶段2校验：高风险与地域集中度核心表")
    print("🔍" * 40 + "\n")
    
    utils = CompareUtils()
    all_results = []
    
    # 参考文件路径
    ref_file = project_root / "sample data" / "阶段" / "限额监控_阶段2.xlsx"
    output_dir = project_root / "data" / "stage2_output"
    
    # 定义要校验的P0级核心表
    core_tables = [
        {
            "name": "限额明细_地域集中度限额(含城投)",
            "sheet_name": "限额明细_地域集中度限额(含城投)",
            "output_file": "限额明细_地域集中度限额(含城投).xlsx",
            "key_field": "省份",
            "numeric_fields": [
                "单一地域总持仓_PR",
                "地域集中度",
                "单一地域城投总持仓_PR",
                "城投地域集中度"
            ],
            "categorical_checks": []
        },
        {
            "name": "限额明细_高风险行业",
            "sheet_name": "限额明细_高风险行业",
            "output_file": "限额明细_高风险行业.xlsx",
            "key_field": "高风险行业",
            "numeric_fields": [
                "高风险行业总持仓_PR",
                "集中度",
                "剩余额度"
            ],
            "categorical_checks": []
        },
        {
            "name": "限额明细_高风险省份",
            "sheet_name": "限额明细_高风险省份",
            "output_file": "限额明细_高风险省份.xlsx",
            "key_field": "高风险省份",
            "numeric_fields": [
                "高风险省份总持仓_PR",
                "集中度",
                "剩余额度"
            ],
            "categorical_checks": []
        },
        {
            "name": "限额明细_债券持仓明细表_信用债2",
            "sheet_name": "限额明细_债券持仓明细表_信用债2",
            "output_file": "限额明细_债券持仓明细表_信用债2.xlsx",
            "key_field": "资产代码",
            "numeric_fields": [
                "单一债券持仓(万)",
                "集中度(%)",
                "地域集中度",
                "城投地域集中度"
            ],
            "categorical_checks": [
                ("是否超限", "是")
            ]
        }
    ]
    
    for idx, table_config in enumerate(core_tables, 1):
        print(f"\n{'='*80}")
        print(f"📋 [{idx}/{len(core_tables)}] 校验: {table_config['name']}")
        print(f"{'='*80}\n")
        
        try:
            # 读取参考数据
            df_ref = pd.read_excel(ref_file, sheet_name=table_config['sheet_name'])
            print(f"✅ 参考文件加载成功: {len(df_ref)} 行 × {len(df_ref.columns)} 列")
            
            # 读取输出数据
            output_path = output_dir / table_config['output_file']
            if not output_path.exists():
                print(f"❌ 输出文件不存在: {output_path}")
                continue
            
            df_output = pd.read_excel(output_path)
            print(f"✅ 输出文件加载成功: {len(df_output)} 行 × {len(df_output.columns)} 列")
            
            # 1. 基础结构对比
            result = utils.compare_basic_structure(df_ref, df_output, table_config['name'])
            
            # 2. 数值字段对比
            print(f"\n🔢 数值字段对比...")
            for field in table_config['numeric_fields']:
                if field in df_ref.columns and field in df_output.columns:
                    # 总和对比
                    sum_result = utils.compare_numeric_field(df_ref, df_output, field, "sum")
                    result["检查项"].append(sum_result)
                    
                    # 非空值数量对比
                    count_result = utils.compare_numeric_field(df_ref, df_output, field, "count")
                    result["检查项"].append(count_result)
                else:
                    print(f"⚠️ 字段 '{field}' 在参考或输出数据中不存在")
                    result["检查项"].append({
                        "项目": f"{field}_检查",
                        "通过": False,
                        "状态": "⚠️",
                        "备注": "字段不存在"
                    })
            
            # 3. 分类字段对比（如果有）
            if table_config['categorical_checks']:
                print(f"\n📊 分类字段对比...")
                for field, value in table_config['categorical_checks']:
                    cat_result = utils.compare_categorical_field(df_ref, df_output, field, value)
                    result["检查项"].append(cat_result)
            
            # 4. 抽样行对比
            print(f"\n🔍 抽样行对比（前5条）...")
            if table_config['key_field'] in df_ref.columns and table_config['key_field'] in df_output.columns:
                compare_fields = table_config['numeric_fields'].copy()
                if table_config['categorical_checks']:
                    compare_fields.extend([field for field, _ in table_config['categorical_checks']])
                
                sample_results = utils.sample_compare_rows(
                    df_ref, 
                    df_output, 
                    table_config['key_field'],
                    compare_fields,
                    sample_size=5
                )
                
                for sample in sample_results[:3]:  # 只打印前3个样本
                    if "键" in sample:
                        print(f"\n   样本键: {sample['键']}")
                        for field_cmp in sample['字段对比'][:5]:  # 每个样本只显示前5个字段
                            print(f"      {field_cmp['状态']} {field_cmp['字段']}: "
                                  f"参考={field_cmp['参考值']}, 实际={field_cmp['实际值']}")
            
            # 打印结果
            utils.print_result(result)
            all_results.append(result)
            
        except Exception as e:
            print(f"❌ 校验失败: {e}")
            import traceback
            traceback.print_exc()
    
    # ========== 总结 ==========
    print("\n" + "=" * 80)
    print("📊 阶段2核心表校验完成")
    print("=" * 80)
    
    total_checks = sum(len(r["检查项"]) for r in all_results)
    passed_checks = sum(
        sum(1 for item in r["检查项"] if item.get("通过", False))
        for r in all_results
    )
    
    print(f"\n✅ 总通过率: {passed_checks}/{total_checks} ({passed_checks/total_checks*100 if total_checks > 0 else 0:.1f}%)")
    
    # 列出未通过的检查项
    failed_items = []
    for result in all_results:
        for item in result["检查项"]:
            if not item.get("通过", False):
                failed_items.append({
                    "表": result["表名"],
                    "项目": item["项目"],
                    "参考值": item.get("参考值", "N/A"),
                    "实际值": item.get("实际值", "N/A")
                })
    
    if failed_items:
        print(f"\n❌ 未通过的检查项 ({len(failed_items)}个):")
        for item in failed_items[:15]:  # 显示前15个
            print(f"   • {item['表']} - {item['项目']}")
            if item['参考值'] != "N/A" and item['实际值'] != "N/A":
                print(f"     参考: {item['参考值']}, 实际: {item['实际值']}")
    else:
        print(f"\n🎉 所有检查项全部通过！")
    
    return all_results


def validate_stage2_supplementary_tables():
    """校验阶段2的辅助表（P1级）"""
    print("\n" + "📊" * 40)
    print("开始阶段2辅助表校验（P1级）")
    print("📊" * 40 + "\n")
    
    utils = CompareUtils()
    all_results = []
    
    ref_file = project_root / "sample data" / "阶段" / "限额监控_阶段2.xlsx"
    output_dir = project_root / "data" / "stage2_output"
    
    # P1级辅助表
    supplementary_tables = [
        {
            "name": "限额明细_高风险行业_2",
            "sheet_name": "限额明细_高风险行业_2",
            "output_file": "限额明细_高风险行业_2.xlsx",
        },
        {
            "name": "限额明细_高风险省份2",
            "sheet_name": "限额明细_高风险省份2",
            "output_file": "限额明细_高风险省份2.xlsx",
        },
        {
            "name": "限额明细_高收益",
            "sheet_name": "限额明细_高收益",
            "output_file": "限额明细_高收益.xlsx",
        },
        {
            "name": "限额明细_高收益_投资本金规模",
            "sheet_name": "限额明细_高收益_投资本金规模",
            "output_file": "限额明细_高收益_投资本金规模.xlsx",
        }
    ]
    
    for idx, table_config in enumerate(supplementary_tables, 1):
        print(f"\n{'='*80}")
        print(f"📋 [{idx}/{len(supplementary_tables)}] 校验: {table_config['name']}")
        print(f"{'='*80}\n")
        
        try:
            df_ref = pd.read_excel(ref_file, sheet_name=table_config['sheet_name'])
            print(f"✅ 参考文件: {len(df_ref)} 行 × {len(df_ref.columns)} 列")
            
            output_path = output_dir / table_config['output_file']
            if not output_path.exists():
                print(f"⚠️ 输出文件不存在: {output_path}")
                continue
            
            df_output = pd.read_excel(output_path)
            print(f"✅ 输出文件: {len(df_output)} 行 × {len(df_output.columns)} 列")
            
            # 只做基础结构对比
            result = utils.compare_basic_structure(df_ref, df_output, table_config['name'])
            utils.print_result(result)
            all_results.append(result)
            
        except Exception as e:
            print(f"❌ 校验失败: {e}")
    
    print(f"\n📊 阶段2辅助表校验完成")
    return all_results


if __name__ == "__main__":
    # 执行P0级核心表校验
    core_results = validate_stage2_core_tables()
    
    # 执行P1级辅助表校验
    print("\n" + "="*80 + "\n")
    supplementary_results = validate_stage2_supplementary_tables()
    
    # 总体总结
    print("\n" + "🎯" * 40)
    print("阶段2全部校验完成")
    print("🎯" * 40)
    print(f"\n✅ 核心表数量: {len(core_results)}")
    print(f"✅ 辅助表数量: {len(supplementary_results)}")
