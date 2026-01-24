"""
阶段1数值准确性校验 - 详细对比参考Excel与Python输出
"""
import pandas as pd
import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class Stage1Validator:
    """阶段1数值准确性校验器"""
    
    def __init__(self, tolerance=0.0001):
        self.tolerance = tolerance
        self.project_root = project_root
        self.ref_file = self.project_root / "sample data" / "阶段" / "限额监控_阶段1.xlsx"
        self.output_dir = self.project_root / "data" / "stage1_output"
        self.results = []
    
    def compare_numeric_values(self, ref_val, out_val, field_name):
        """对比数值，返回是否匹配及误差"""
        try:
            ref_val = float(ref_val) if pd.notna(ref_val) else 0
            out_val = float(out_val) if pd.notna(out_val) else 0
            
            if abs(ref_val) > 1e-10:
                rel_error = abs(ref_val - out_val) / abs(ref_val)
            else:
                rel_error = 0 if abs(out_val) < 1e-10 else 1.0
            
            match = rel_error < self.tolerance
            
            return {
                "字段": field_name,
                "参考值": f"{ref_val:,.4f}",
                "实际值": f"{out_val:,.4f}",
                "相对误差": f"{rel_error*100:.6f}%",
                "匹配": match,
                "状态": "✅" if match else "❌"
            }
        except:
            return {
                "字段": field_name,
                "参考值": str(ref_val),
                "实际值": str(out_val),
                "匹配": False,
                "状态": "⚠️",
                "备注": "数值转换失败"
            }
    
    def validate_single_bond(self):
        """校验单一债券限额表"""
        print("\n" + "=" * 80)
        print("📋 [1/3] 单一债券限额表 - 数值准确性校验")
        print("=" * 80)
        
        try:
            # 读取参考文件
            print("\n📖 读取参考文件...")
            df_ref = pd.read_excel(self.ref_file, sheet_name="限额明细_单一债券")
            print(f"   ✅ 参考文件: {len(df_ref)} 行")
            
            # 读取输出文件
            print("📖 读取输出文件...")
            output_file = self.output_dir / "限额明细_单一债券.xlsx"
            df_out = pd.read_excel(output_file)
            print(f"   ✅ 输出文件: {len(df_out)} 行")
            
            result = {
                "表名": "单一债券限额",
                "检查项": []
            }
            
            # 1. 行数对比
            row_match = len(df_ref) == len(df_out)
            result["检查项"].append({
                "项目": "行数",
                "参考值": len(df_ref),
                "实际值": len(df_out),
                "匹配": row_match,
                "状态": "✅" if row_match else "❌"
            })
            
            # 2. 关键数值字段汇总对比
            print("\n🔢 关键数值字段汇总对比...")
            numeric_fields = [
                "单一债券持仓(万)",
                "单一债券规模限额(万)",
                "集中度(%)"
            ]
            
            for field in numeric_fields:
                if field in df_ref.columns and field in df_out.columns:
                    ref_sum = df_ref[field].sum()
                    out_sum = df_out[field].sum()
                    
                    if abs(ref_sum) > 1e-10:
                        rel_error = abs(ref_sum - out_sum) / abs(ref_sum)
                    else:
                        rel_error = 0
                    
                    match = rel_error < self.tolerance
                    
                    result["检查项"].append({
                        "项目": f"{field}_总和",
                        "参考值": f"{ref_sum:,.4f}",
                        "实际值": f"{out_sum:,.4f}",
                        "相对误差": f"{rel_error*100:.6f}%",
                        "匹配": match,
                        "状态": "✅" if match else "❌"
                    })
                    
                    print(f"   {result['检查项'][-1]['状态']} {field}: "
                          f"参考={ref_sum:,.2f}, 实际={out_sum:,.2f}, "
                          f"误差={rel_error*100:.4f}%")
            
            # 3. 超限判断对比
            print("\n📊 超限判断对比...")
            if '是否超限' in df_ref.columns and '是否超限' in df_out.columns:
                ref_overlimit = (df_ref['是否超限'] == '是').sum()
                out_overlimit = (df_out['是否超限'] == '是').sum()
                
                match = ref_overlimit == out_overlimit
                result["检查项"].append({
                    "项目": "超限数量",
                    "参考值": ref_overlimit,
                    "实际值": out_overlimit,
                    "差异": out_overlimit - ref_overlimit,
                    "匹配": match,
                    "状态": "✅" if match else "❌"
                })
                
                print(f"   {result['检查项'][-1]['状态']} 超限数量: "
                      f"参考={ref_overlimit}, 实际={out_overlimit}")
            
            # 4. 抽样对比（前5条记录）
            print("\n🔍 抽样对比（前5条记录）...")
            if '资产代码' in df_ref.columns and '资产代码' in df_out.columns:
                sample_size = min(5, len(df_ref))
                sample_codes = df_ref['资产代码'].head(sample_size).tolist()
                
                sample_results = []
                for code in sample_codes:
                    ref_row = df_ref[df_ref['资产代码'] == code]
                    out_row = df_out[df_out['资产代码'] == code]
                    
                    if len(ref_row) > 0 and len(out_row) > 0:
                        ref_row = ref_row.iloc[0]
                        out_row = out_row.iloc[0]
                        
                        print(f"\n   样本: {code}")
                        
                        for field in numeric_fields:
                            if field in df_ref.columns and field in df_out.columns:
                                cmp = self.compare_numeric_values(
                                    ref_row[field], 
                                    out_row[field], 
                                    field
                                )
                                print(f"      {cmp['状态']} {cmp['字段']}: "
                                      f"参考={cmp['参考值']}, 实际={cmp['实际值']}, "
                                      f"误差={cmp['相对误差']}")
                                sample_results.append(cmp)
            
            self.results.append(result)
            self._print_result(result)
            
        except Exception as e:
            print(f"\n❌ 校验失败: {e}")
            import traceback
            traceback.print_exc()
    
    def validate_single_entity(self):
        """校验单一主体限额表"""
        print("\n\n" + "=" * 80)
        print("📋 [2/3] 单一主体限额表 - 数值准确性校验")
        print("=" * 80)
        
        try:
            # 读取参考文件
            print("\n📖 读取参考文件...")
            df_ref = pd.read_excel(self.ref_file, sheet_name="限额明细_单一主体")
            print(f"   ✅ 参考文件: {len(df_ref)} 行")
            
            # 读取输出文件
            print("📖 读取输出文件...")
            output_file = self.output_dir / "限额明细_单一主体.xlsx"
            df_out = pd.read_excel(output_file)
            print(f"   ✅ 输出文件: {len(df_out)} 行")
            
            result = {
                "表名": "单一主体限额",
                "检查项": []
            }
            
            # 行数对比
            row_match = len(df_ref) == len(df_out)
            result["检查项"].append({
                "项目": "行数",
                "参考值": len(df_ref),
                "实际值": len(df_out),
                "匹配": row_match,
                "状态": "✅" if row_match else "❌"
            })
            
            # 关键字段对比
            print("\n🔢 关键数值字段汇总对比...")
            numeric_fields = [
                "单一主体持仓(万)",
                "单一主体规模限额(万)",
                "集中度(%)"
            ]
            
            for field in numeric_fields:
                if field in df_ref.columns and field in df_out.columns:
                    ref_sum = df_ref[field].sum()
                    out_sum = df_out[field].sum()
                    
                    if abs(ref_sum) > 1e-10:
                        rel_error = abs(ref_sum - out_sum) / abs(ref_sum)
                    else:
                        rel_error = 0
                    
                    match = rel_error < self.tolerance
                    
                    result["检查项"].append({
                        "项目": f"{field}_总和",
                        "参考值": f"{ref_sum:,.4f}",
                        "实际值": f"{out_sum:,.4f}",
                        "相对误差": f"{rel_error*100:.6f}%",
                        "匹配": match,
                        "状态": "✅" if match else "❌"
                    })
                    
                    print(f"   {result['检查项'][-1]['状态']} {field}: "
                          f"参考={ref_sum:,.2f}, 实际={out_sum:,.2f}, "
                          f"误差={rel_error*100:.4f}%")
            
            # 超限判断对比
            print("\n📊 超限判断对比...")
            if '是否超限' in df_ref.columns and '是否超限' in df_out.columns:
                ref_overlimit = (df_ref['是否超限'] == '是').sum()
                out_overlimit = (df_out['是否超限'] == '是').sum()
                
                match = ref_overlimit == out_overlimit
                result["检查项"].append({
                    "项目": "超限数量",
                    "参考值": ref_overlimit,
                    "实际值": out_overlimit,
                    "差异": out_overlimit - ref_overlimit,
                    "匹配": match,
                    "状态": "✅" if match else "❌"
                })
                
                print(f"   {result['检查项'][-1]['状态']} 超限数量: "
                      f"参考={ref_overlimit}, 实际={out_overlimit}")
            
            self.results.append(result)
            self._print_result(result)
            
        except Exception as e:
            print(f"\n❌ 校验失败: {e}")
            import traceback
            traceback.print_exc()
    
    def validate_actual_controller(self):
        """校验单一实控人限额表"""
        print("\n\n" + "=" * 80)
        print("📋 [3/3] 单一实控人限额表 - 数值准确性校验")
        print("=" * 80)
        
        try:
            # 读取参考文件
            print("\n📖 读取参考文件...")
            df_ref = pd.read_excel(self.ref_file, sheet_name="限额明细_单一实控人")
            print(f"   ✅ 参考文件: {len(df_ref)} 行")
            
            # 读取输出文件
            print("📖 读取输出文件...")
            output_file = self.output_dir / "限额明细_单一实控人_取最高额度.xlsx"
            df_out = pd.read_excel(output_file)
            print(f"   ✅ 输出文件: {len(df_out)} 行")
            
            result = {
                "表名": "单一实控人限额",
                "检查项": []
            }
            
            # 行数对比
            row_match = len(df_ref) == len(df_out)
            result["检查项"].append({
                "项目": "行数",
                "参考值": len(df_ref),
                "实际值": len(df_out),
                "匹配": row_match,
                "状态": "✅" if row_match else "❌"
            })
            
            # 关键字段对比
            print("\n🔢 关键数值字段汇总对比...")
            numeric_fields = [
                "单一实控人持仓(万)",
                "单一实控人规模限额(万)",
                "集中度(%)"
            ]
            
            for field in numeric_fields:
                if field in df_ref.columns and field in df_out.columns:
                    ref_sum = df_ref[field].sum()
                    out_sum = df_out[field].sum()
                    
                    if abs(ref_sum) > 1e-10:
                        rel_error = abs(ref_sum - out_sum) / abs(ref_sum)
                    else:
                        rel_error = 0
                    
                    match = rel_error < self.tolerance
                    
                    result["检查项"].append({
                        "项目": f"{field}_总和",
                        "参考值": f"{ref_sum:,.4f}",
                        "实际值": f"{out_sum:,.4f}",
                        "相对误差": f"{rel_error*100:.6f}%",
                        "匹配": match,
                        "状态": "✅" if match else "❌"
                    })
                    
                    print(f"   {result['检查项'][-1]['状态']} {field}: "
                          f"参考={ref_sum:,.2f}, 实际={out_sum:,.2f}, "
                          f"误差={rel_error*100:.4f}%")
            
            # 超限判断对比
            print("\n📊 超限判断对比...")
            if '是否超限' in df_ref.columns and '是否超限' in df_out.columns:
                ref_overlimit = (df_ref['是否超限'] == '是').sum()
                out_overlimit = (df_out['是否超限'] == '是').sum()
                
                match = ref_overlimit == out_overlimit
                result["检查项"].append({
                    "项目": "超限数量",
                    "参考值": ref_overlimit,
                    "实际值": out_overlimit,
                    "差异": out_overlimit - ref_overlimit,
                    "匹配": match,
                    "状态": "✅" if match else "❌"
                })
                
                print(f"   {result['检查项'][-1]['状态']} 超限数量: "
                      f"参考={ref_overlimit}, 实际={out_overlimit}")
            
            self.results.append(result)
            self._print_result(result)
            
        except Exception as e:
            print(f"\n❌ 校验失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _print_result(self, result):
        """打印单表结果"""
        print("\n" + "-" * 80)
        print(f"📊 {result['表名']} 校验结果")
        print("-" * 80)
        
        total = len(result["检查项"])
        passed = sum(1 for item in result["检查项"] if item.get("匹配", False))
        
        print(f"✅ 通过率: {passed}/{total} ({passed/total*100 if total > 0 else 0:.1f}%)")
    
    def run_all(self):
        """运行所有校验"""
        print("\n" + "🚀" * 40)
        print("阶段1数值准确性校验 - 第2段")
        print(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("🚀" * 40)
        
        # 执行各表校验
        self.validate_single_bond()
        self.validate_single_entity()
        self.validate_actual_controller()
        
        # 总结
        print("\n\n" + "=" * 80)
        print("📊 阶段1数值准确性校验总结")
        print("=" * 80)
        
        total_checks = sum(len(r["检查项"]) for r in self.results)
        passed_checks = sum(
            sum(1 for item in r["检查项"] if item.get("匹配", False))
            for r in self.results
        )
        
        print(f"\n✅ 总通过率: {passed_checks}/{total_checks} "
              f"({passed_checks/total_checks*100 if total_checks > 0 else 0:.1f}%)")
        
        # 列出未通过的检查项
        failed_items = []
        for result in self.results:
            for item in result["检查项"]:
                if not item.get("匹配", False):
                    failed_items.append({
                        "表": result["表名"],
                        "项目": item["项目"],
                        "参考值": item.get("参考值", "N/A"),
                        "实际值": item.get("实际值", "N/A")
                    })
        
        if failed_items:
            print(f"\n❌ 未通过的检查项 ({len(failed_items)}个):")
            for item in failed_items[:20]:  # 最多显示20个
                print(f"   • {item['表']} - {item['项目']}")
                print(f"     参考: {item['参考值']}, 实际: {item['实际值']}")
        else:
            print(f"\n🎉 所有检查项全部通过！数值完全一致！")
        
        return self.results


if __name__ == "__main__":
    validator = Stage1Validator()
    validator.run_all()
