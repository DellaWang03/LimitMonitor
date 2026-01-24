"""
数值准确性校验V2 - 基于实际存在的Sheet
"""
import pandas as pd
import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class DataValidator:
    """数据准确性校验器"""
    
    def __init__(self, tolerance=0.0001):
        self.tolerance = tolerance
        self.project_root = project_root
        self.ref_stage1 = self.project_root / "sample data" / "阶段" / "限额监控_阶段1.xlsx"
        self.ref_stage2 = self.project_root / "sample data" / "阶段" / "限额监控_阶段2.xlsx"
        self.output_stage1 = self.project_root / "data" / "stage1_output"
        self.output_stage2 = self.project_root / "data" / "stage2_output"
        self.results = []
    
    def compare_table(self, ref_df, out_df, table_name, numeric_fields, key_field=None):
        """通用表格对比"""
        result = {
            "表名": table_name,
            "检查项": []
        }
        
        print(f"\n📊 对比 {table_name}...")
        print(f"   参考: {len(ref_df)} 行 × {len(ref_df.columns)} 列")
        print(f"   输出: {len(out_df)} 行 × {len(out_df.columns)} 列")
        
        # 1. 行数对比
        row_match = len(ref_df) == len(out_df)
        result["检查项"].append({
            "项目": "行数",
            "参考值": len(ref_df),
            "实际值": len(out_df),
            "差异": len(out_df) - len(ref_df),
            "匹配": row_match,
            "状态": "✅" if row_match else "❌"
        })
        print(f"   {'✅' if row_match else '❌'} 行数: 参考={len(ref_df)}, 实际={len(out_df)}")
        
        # 2. 数值字段汇总对比
        print(f"\n   🔢 数值字段对比:")
        for field in numeric_fields:
            if field in ref_df.columns and field in out_df.columns:
                ref_sum = ref_df[field].sum()
                out_sum = out_df[field].sum()
                
                if abs(ref_sum) > 1e-10:
                    rel_error = abs(ref_sum - out_sum) / abs(ref_sum)
                else:
                    rel_error = 0 if abs(out_sum) < 1e-10 else 1.0
                
                match = rel_error < self.tolerance
                
                result["检查项"].append({
                    "项目": f"{field}_总和",
                    "参考值": f"{ref_sum:,.4f}",
                    "实际值": f"{out_sum:,.4f}",
                    "相对误差": f"{rel_error*100:.6f}%",
                    "匹配": match,
                    "状态": "✅" if match else "❌"
                })
                
                print(f"      {'✅' if match else '❌'} {field}: "
                      f"参考={ref_sum:,.2f}, 实际={out_sum:,.2f}, "
                      f"误差={rel_error*100:.6f}%")
            else:
                if field not in ref_df.columns:
                    print(f"      ⚠️ {field}: 参考文件中不存在")
                if field not in out_df.columns:
                    print(f"      ⚠️ {field}: 输出文件中不存在")
        
        # 3. 超限判断对比（如果存在）
        if '是否超限' in ref_df.columns and '是否超限' in out_df.columns:
            print(f"\n   📊 超限判断对比:")
            ref_overlimit = (ref_df['是否超限'] == '是').sum()
            out_overlimit = (out_df['是否超限'] == '是').sum()
            
            match = ref_overlimit == out_overlimit
            result["检查项"].append({
                "项目": "超限数量",
                "参考值": ref_overlimit,
                "实际值": out_overlimit,
                "差异": out_overlimit - ref_overlimit,
                "匹配": match,
                "状态": "✅" if match else "❌"
            })
            
            print(f"      {'✅' if match else '❌'} 超限数量: "
                  f"参考={ref_overlimit}, 实际={out_overlimit}")
        
        self.results.append(result)
        return result
    
    def validate_stage1_credit_1_1(self):
        """校验阶段1 - 信用债1_1"""
        print("\n" + "=" * 80)
        print("📋 [1/5] 阶段1 - 信用债1_1")
        print("=" * 80)
        
        try:
            df_ref = pd.read_excel(self.ref_stage1, sheet_name="限额明细_债券持仓明细表_信用债1_1")
            output_file = self.output_stage1 / "限额明细_债券持仓明细表_信用债1_1.xlsx"
            df_out = pd.read_excel(output_file)
            
            numeric_fields = [
                "单一债券持仓(万)",
                "单一债券规模限额(万)",
                "集中度(%)"
            ]
            
            self.compare_table(df_ref, df_out, "信用债1_1", numeric_fields)
            
        except Exception as e:
            print(f"❌ 校验失败: {e}")
    
    def validate_stage1_credit_1_2(self):
        """校验阶段1 - 信用债1_2"""
        print("\n\n" + "=" * 80)
        print("📋 [2/5] 阶段1 - 信用债1_2")
        print("=" * 80)
        
        try:
            df_ref = pd.read_excel(self.ref_stage1, sheet_name="限额明细_债券持仓明细表_信用债1_2")
            output_file = self.output_stage1 / "限额明细_债券持仓明细表_信用债1_2.xlsx"
            df_out = pd.read_excel(output_file)
            
            numeric_fields = [
                "单一主体持仓(万)",
                "单一主体规模限额(万)",
                "单一实控人持仓(万)",
                "单一实控人规模限额(万)"
            ]
            
            self.compare_table(df_ref, df_out, "信用债1_2", numeric_fields)
            
        except Exception as e:
            print(f"❌ 校验失败: {e}")
    
    def validate_stage2_regional(self):
        """校验阶段2 - 地域集中度"""
        print("\n\n" + "=" * 80)
        print("📋 [3/5] 阶段2 - 地域集中度限额")
        print("=" * 80)
        
        try:
            df_ref = pd.read_excel(self.ref_stage2, sheet_name="限额明细_地域集中度限额(含城投)")
            output_file = self.output_stage2 / "限额明细_地域集中度限额(含城投).xlsx"
            df_out = pd.read_excel(output_file)
            
            numeric_fields = [
                "单一地域总持仓_PR",
                "地域集中度",
                "单一地域城投总持仓_PR",
                "城投地域集中度"
            ]
            
            self.compare_table(df_ref, df_out, "地域集中度限额", numeric_fields)
            
        except Exception as e:
            print(f"❌ 校验失败: {e}")
    
    def validate_stage2_high_risk_industry(self):
        """校验阶段2 - 高风险行业"""
        print("\n\n" + "=" * 80)
        print("📋 [4/5] 阶段2 - 高风险行业")
        print("=" * 80)
        
        try:
            df_ref = pd.read_excel(self.ref_stage2, sheet_name="限额明细_高风险行业")
            output_file = self.output_stage2 / "限额明细_高风险行业.xlsx"
            df_out = pd.read_excel(output_file)
            
            numeric_fields = [
                "高风险行业总持仓_PR",
                "信用债总持仓_PR",
                "高风险行业集中度" if "高风险行业集中度" in df_ref.columns else "集中度"
            ]
            
            self.compare_table(df_ref, df_out, "高风险行业", numeric_fields)
            
        except Exception as e:
            print(f"❌ 校验失败: {e}")
    
    def validate_stage2_high_risk_province(self):
        """校验阶段2 - 高风险省份"""
        print("\n\n" + "=" * 80)
        print("📋 [5/5] 阶段2 - 高风险省份")
        print("=" * 80)
        
        try:
            df_ref = pd.read_excel(self.ref_stage2, sheet_name="限额明细_高风险省份")
            output_file = self.output_stage2 / "限额明细_高风险省份.xlsx"
            df_out = pd.read_excel(output_file)
            
            numeric_fields = [
                "高风险省份总持仓_PR",
                "高风险省份集中度" if "高风险省份集中度" in df_ref.columns else "集中度"
            ]
            
            self.compare_table(df_ref, df_out, "高风险省份", numeric_fields)
            
        except Exception as e:
            print(f"❌ 校验失败: {e}")
    
    def run_all(self):
        """运行所有校验"""
        print("\n" + "🚀" * 40)
        print("数据准确性校验 - 第2段")
        print(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"容差标准：{self.tolerance*100}% (0.01%)")
        print("🚀" * 40)
        
        # 执行校验
        self.validate_stage1_credit_1_1()
        self.validate_stage1_credit_1_2()
        self.validate_stage2_regional()
        self.validate_stage2_high_risk_industry()
        self.validate_stage2_high_risk_province()
        
        # 总结
        print("\n\n" + "=" * 80)
        print("📊 数值准确性校验总结")
        print("=" * 80)
        
        total_checks = sum(len(r["检查项"]) for r in self.results)
        passed_checks = sum(
            sum(1 for item in r["检查项"] if item.get("匹配", False))
            for r in self.results
        )
        
        print(f"\n✅ 总通过率: {passed_checks}/{total_checks} "
              f"({passed_checks/total_checks*100 if total_checks > 0 else 0:.1f}%)")
        
        # 按表统计
        print(f"\n📋 各表通过率:")
        for result in self.results:
            total = len(result["检查项"])
            passed = sum(1 for item in result["检查项"] if item.get("匹配", False))
            status = "✅" if passed == total else "⚠️"
            print(f"   {status} {result['表名']}: {passed}/{total} ({passed/total*100 if total > 0 else 0:.1f}%)")
        
        # 列出未通过的检查项
        failed_items = []
        for result in self.results:
            for item in result["检查项"]:
                if not item.get("匹配", False):
                    failed_items.append({
                        "表": result["表名"],
                        "项目": item["项目"],
                        "参考值": item.get("参考值", "N/A"),
                        "实际值": item.get("实际值", "N/A"),
                        "相对误差": item.get("相对误差", "N/A")
                    })
        
        if failed_items:
            print(f"\n❌ 未通过的检查项 ({len(failed_items)}个):")
            for item in failed_items[:20]:
                print(f"\n   • {item['表']} - {item['项目']}")
                print(f"     参考值: {item['参考值']}")
                print(f"     实际值: {item['实际值']}")
                if '相对误差' in item:
                    print(f"     相对误差: {item['相对误差']}")
        else:
            print(f"\n🎉 所有检查项全部通过！数值准确性验证通过！")
        
        return self.results


if __name__ == "__main__":
    validator = DataValidator()
    validator.run_all()
