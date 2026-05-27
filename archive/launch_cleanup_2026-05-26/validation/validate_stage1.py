"""
阶段1：限额计算核心表校验（单一债券、单一主体、单一实控人）
"""
import pandas as pd
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from compare_utils import CompareUtils


def validate_stage1_core_tables():
    """校验阶段1的3张核心表"""
    print("\n" + "🔍" * 40)
    print("开始阶段1校验：核心限额表（单一债券、单一主体、单一实控人）")
    print("🔍" * 40 + "\n")
    
    utils = CompareUtils()
    all_results = []
    
    # 参考文件路径
    ref_file = project_root / "sample data" / "阶段" / "限额监控_阶段1.xlsx"
    
    # 定义要校验的核心表
    core_tables = [
        {
            "name": "限额明细_单一债券",
            "sheet_name": "限额明细_单一债券",
            "output_file": "限额明细_单一债券.xlsx",
            "key_field": "资产代码",
            "numeric_fields": [
                "单一债券持仓(万)",
                "单一债券规模限额(万)",
                "集中度(%)"
            ],
            "categorical_checks": [
                ("是否超限", "是")
            ]
        },
        {
            "name": "限额明细_单一主体",
            "sheet_name": "限额明细_单一主体",
            "output_file": "限额明细_单一主体.xlsx",
            "key_field": "债务主体",
            "numeric_fields": [
                "单一主体持仓(万)",
                "单一主体规模限额(万)",
                "集中度(%)"
            ],
            "categorical_checks": [
                ("是否超限", "是")
            ]
        },
        {
            "name": "限额明细_单一实控人",
            "sheet_name": "限额明细_单一实控人",
            "output_file": "限额明细_单一实控人_取最高额度.xlsx",
            "key_field": "调整后实际控制人",
            "numeric_fields": [
                "单一实控人持仓(万)",
                "单一实控人规模限额(万)",
                "集中度(%)"
            ],
            "categorical_checks": [
                ("是否超限", "是")
            ]
        }
    ]
    
    for idx, table_config in enumerate(core_tables, 1):
        print(f"\n{'='*80}")
        print(f"📋 [{idx}/3] 校验: {table_config['name']}")
        print(f"{'='*80}\n")
        
        try:
            # 读取参考数据
            df_ref = pd.read_excel(ref_file, sheet_name=table_config['sheet_name'])
            print(f"✅ 参考文件加载成功: {len(df_ref)} 行 × {len(df_ref.columns)} 列")
            
            # 读取输出数据
            output_path = project_root / "data" / "stage1_output" / table_config['output_file']
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
            
            # 3. 分类字段对比
            print(f"\n📊 分类字段对比...")
            for field, value in table_config['categorical_checks']:
                cat_result = utils.compare_categorical_field(df_ref, df_output, field, value)
                result["检查项"].append(cat_result)
            
            # 4. 抽样行对比
            print(f"\n🔍 抽样行对比（前5条）...")
            if table_config['key_field'] in df_ref.columns and table_config['key_field'] in df_output.columns:
                sample_results = utils.sample_compare_rows(
                    df_ref, 
                    df_output, 
                    table_config['key_field'],
                    table_config['numeric_fields'] + ['是否超限'],
                    sample_size=5
                )
                
                for sample in sample_results[:3]:  # 只打印前3个样本
                    if "键" in sample:
                        print(f"\n   样本键: {sample['键']}")
                        for field_cmp in sample['字段对比']:
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
    print("📊 阶段1核心表校验完成")
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
        for item in failed_items[:10]:  # 只显示前10个
            print(f"   • {item['表']} - {item['项目']}")
            print(f"     参考: {item['参考值']}, 实际: {item['实际值']}")
    else:
        print(f"\n🎉 所有检查项全部通过！")
    
    return all_results


if __name__ == "__main__":
    validate_stage1_core_tables()
