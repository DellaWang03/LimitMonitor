"""
阶段3：可视化看板数据校验
对比7个页面的关键指标与Power BI截图数据
"""
import pandas as pd
import sys
from pathlib import Path
from datetime import datetime

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.visualization.data_loader import DataLoader


class VisualizationValidator:
    """可视化数据校验器"""
    
    def __init__(self):
        self.data_loader = DataLoader()
        self.results = []
    
    def validate_page1_single_credit(self):
        """校验页面1：单一信用限额"""
        print("\n" + "=" * 80)
        print("📊 页面1：单一信用限额 - 关键指标校验")
        print("=" * 80 + "\n")
        
        result = {
            "页面": "单一信用限额",
            "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "指标": []
        }
        
        try:
            # 加载数据 - 使用正确的方法名
            df_credit_1_1 = self.data_loader.load_stage1_credit_1_1()  # 单一债券
            df_credit_1_2 = self.data_loader.load_stage1_credit_1_2()  # 单一主体/实控人
            
            # 计算关键指标
            metrics = {
                "单一债券-总数量": len(df_credit_1_1),
                "单一债券-超限数量": (df_credit_1_1['是否超限'] == '是').sum() if '是否超限' in df_credit_1_1.columns else 0,
                "单一债券-总持仓(万)": df_credit_1_1['单一债券持仓(万)'].sum() if '单一债券持仓(万)' in df_credit_1_1.columns else 0,
                
                "单一主体/实控人-总数量": len(df_credit_1_2),
                "单一主体/实控人-超限数量": (df_credit_1_2['是否超限'] == '是').sum() if '是否超限' in df_credit_1_2.columns else 0,
            }
            
            # 打印指标
            print("📌 关键指标计算结果：\n")
            for metric_name, value in metrics.items():
                if isinstance(value, float):
                    print(f"   • {metric_name}: {value:,.2f}")
                else:
                    print(f"   • {metric_name}: {value}")
                
                result["指标"].append({
                    "指标名": metric_name,
                    "计算值": value,
                    "备注": "需与Power BI截图对比"
                })
            
            print("\n💡 请手工对比以上数值与 Power BI 截图 '单一信用限额.png' 中的数据")
            
        except Exception as e:
            print(f"❌ 校验失败: {e}")
            import traceback
            traceback.print_exc()
        
        self.results.append(result)
        return result
    
    def validate_page5_high_risk(self):
        """校验页面5：高风险类明细"""
        print("\n" + "=" * 80)
        print("📊 页面5：高风险类明细 - 关键指标校验")
        print("=" * 80 + "\n")
        
        result = {
            "页面": "高风险类明细",
            "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "指标": []
        }
        
        try:
            # 加载数据
            df_industry = self.data_loader.load_stage2_high_risk_industry()
            df_province = self.data_loader.load_stage2_high_risk_province()
            
            # 计算关键指标
            metrics = {
                "高风险行业-总数量": len(df_industry),
                "高风险行业-总持仓(万)": df_industry['高风险行业总持仓_PR'].sum() if '高风险行业总持仓_PR' in df_industry.columns else 0,
                "高风险行业-平均集中度": df_industry['集中度'].mean() if '集中度' in df_industry.columns else 0,
                
                "高风险省份-总数量": len(df_province),
                "高风险省份-总持仓(万)": df_province['高风险省份总持仓_PR'].sum() if '高风险省份总持仓_PR' in df_province.columns else 0,
                "高风险省份-平均集中度": df_province['集中度'].mean() if '集中度' in df_province.columns else 0,
            }
            
            # 打印指标
            print("📌 关键指标计算结果：\n")
            for metric_name, value in metrics.items():
                if isinstance(value, float):
                    print(f"   • {metric_name}: {value:,.2f}")
                else:
                    print(f"   • {metric_name}: {value}")
                
                result["指标"].append({
                    "指标名": metric_name,
                    "计算值": value,
                    "备注": "需与Power BI截图对比"
                })
            
            print("\n💡 请手工对比以上数值与 Power BI 截图 '高风险类明细.jpg' 中的数据")
            
        except Exception as e:
            print(f"❌ 校验失败: {e}")
            import traceback
            traceback.print_exc()
        
        self.results.append(result)
        return result
    
    def validate_page6_regional(self):
        """校验页面6：地域类明细"""
        print("\n" + "=" * 80)
        print("📊 页面6：地域类明细 - 关键指标校验")
        print("=" * 80 + "\n")
        
        result = {
            "页面": "地域类明细",
            "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "指标": []
        }
        
        try:
            # 加载数据 - 使用正确的方法名
            df_regional = self.data_loader.load_stage2_regional()
            
            # 计算关键指标
            metrics = {
                "省份总数": len(df_regional),
                "地域总持仓(万)": df_regional['单一地域总持仓_PR'].sum() if '单一地域总持仓_PR' in df_regional.columns else 0,
                "城投总持仓(万)": df_regional['单一地域城投总持仓_PR'].sum() if '单一地域城投总持仓_PR' in df_regional.columns else 0,
                "平均地域集中度": df_regional['地域集中度'].mean() if '地域集中度' in df_regional.columns else 0,
                "平均城投集中度": df_regional['城投地域集中度'].mean() if '城投地域集中度' in df_regional.columns else 0,
            }
            
            # 打印指标
            print("📌 关键指标计算结果：\n")
            for metric_name, value in metrics.items():
                if isinstance(value, float):
                    print(f"   • {metric_name}: {value:,.2f}")
                else:
                    print(f"   • {metric_name}: {value}")
                
                result["指标"].append({
                    "指标名": metric_name,
                    "计算值": value,
                    "备注": "需与Power BI截图对比"
                })
            
            print("\n💡 请手工对比以上数值与 Power BI 截图 '地域类明细.jpg' 中的数据")
            
        except Exception as e:
            print(f"❌ 校验失败: {e}")
            import traceback
            traceback.print_exc()
        
        self.results.append(result)
        return result
    
    def validate_page4_guarantee(self):
        """校验页面4：专业担保明细"""
        print("\n" + "=" * 80)
        print("📊 页面4：专业担保明细 - 关键指标校验")
        print("=" * 80 + "\n")
        
        result = {
            "页面": "专业担保明细",
            "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "指标": []
        }
        
        try:
            # 加载数据 - 使用正确的方法名
            df_guarantee = self.data_loader.load_stage1_guarantee()
            
            # 计算关键指标
            metrics = {
                "担保公司数量": len(df_guarantee),
                "担保总持仓(万)": df_guarantee['担保持仓(万)'].sum() if '担保持仓(万)' in df_guarantee.columns else 0,
                "超限数量": (df_guarantee['是否超限'] == '是').sum() if '是否超限' in df_guarantee.columns else 0,
            }
            
            # 打印指标
            print("📌 关键指标计算结果：\n")
            for metric_name, value in metrics.items():
                if isinstance(value, float):
                    print(f"   • {metric_name}: {value:,.2f}")
                else:
                    print(f"   • {metric_name}: {value}")
                
                result["指标"].append({
                    "指标名": metric_name,
                    "计算值": value,
                    "备注": "需与Power BI截图对比"
                })
            
            print("\n💡 请手工对比以上数值与 Power BI 截图 '专业担保明细.jpg' 中的数据")
            
        except Exception as e:
            print(f"❌ 校验失败: {e}")
            import traceback
            traceback.print_exc()
        
        self.results.append(result)
        return result
    
    def validate_page7_high_yield(self):
        """校验页面7：高收益明细"""
        print("\n" + "=" * 80)
        print("📊 页面7：高收益明细 - 关键指标校验")
        print("=" * 80 + "\n")
        
        result = {
            "页面": "高收益明细",
            "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "指标": []
        }
        
        try:
            # 加载数据
            df_high_yield = self.data_loader.load_stage2_high_yield()
            
            # 计算关键指标
            metrics = {
                "高收益债券数量": len(df_high_yield),
                "投资本金(万)": df_high_yield['投资本金_PR'].sum() if '投资本金_PR' in df_high_yield.columns else 0,
            }
            
            # 打印指标
            print("📌 关键指标计算结果：\n")
            for metric_name, value in metrics.items():
                if isinstance(value, float):
                    print(f"   • {metric_name}: {value:,.2f}")
                else:
                    print(f"   • {metric_name}: {value}")
                
                result["指标"].append({
                    "指标名": metric_name,
                    "计算值": value,
                    "备注": "需与Power BI截图对比"
                })
            
            print("\n💡 请手工对比以上数值与 Power BI 截图 '高收益明细.jpg' 中的数据")
            
        except Exception as e:
            print(f"❌ 校验失败: {e}")
            import traceback
            traceback.print_exc()
        
        self.results.append(result)
        return result
    
    def generate_summary(self):
        """生成汇总报告"""
        print("\n" + "🎯" * 40)
        print("可视化校验汇总报告")
        print("🎯" * 40 + "\n")
        
        print(f"✅ 已校验页面数: {len(self.results)}")
        
        for result in self.results:
            print(f"\n📄 {result['页面']}: {len(result['指标'])} 个指标已计算")
        
        print("\n" + "=" * 80)
        print("💡 下一步操作：")
        print("   1. 打开 'sample data/power bi看板截图/' 目录")
        print("   2. 逐个对比截图中的数值与上述计算结果")
        print("   3. 记录任何差异超过 0.01% 的指标")
        print("=" * 80)


def validate_all_visualization_pages():
    """校验所有可视化页面"""
    print("\n" + "🔍" * 40)
    print("开始阶段3校验：可视化看板数据")
    print("🔍" * 40 + "\n")
    
    validator = VisualizationValidator()
    
    # 校验关键页面
    print("📌 校验关键页面（优先级高）\n")
    validator.validate_page1_single_credit()
    validator.validate_page5_high_risk()
    validator.validate_page6_regional()
    
    print("\n" + "=" * 80 + "\n")
    print("📌 校验辅助页面\n")
    validator.validate_page4_guarantee()
    validator.validate_page7_high_yield()
    
    # 生成汇总
    validator.generate_summary()
    
    return validator.results


if __name__ == "__main__":
    validate_all_visualization_pages()
