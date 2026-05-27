"""
简化版校验脚本 - 使用项目现有的DataLoader
"""
import sys
from pathlib import Path
from datetime import datetime

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

try:
    from src.visualization.data_loader import DataLoader
except:
    from visualization.data_loader import DataLoader


def validate_using_dataloader():
    """使用DataLoader进行简单校验"""
    print("\n" + "🔍" * 40)
    print("数据校验 - 使用DataLoader")
    print(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("🔍" * 40 + "\n")
    
    try:
        # 初始化DataLoader
        loader = DataLoader()
        print("✅ DataLoader 初始化成功\n")
        
        results = []
        
        # ========== 阶段1核心表校验 ==========
        print("=" * 80)
        print("📋 阶段1核心表校验")
        print("=" * 80)
        
        # 1. 阶段1 - 信用债1_1
        print("\n[1/3] 阶段1_信用债1_1")
        try:
            df = loader.load_stage1_credit_1_1()
            print(f"   ✅ 加载成功: {len(df)} 行 × {len(df.columns)} 列")
            
            if '是否超限' in df.columns:
                overlimit_count = (df['是否超限'] == '是').sum()
                print(f"   📊 超限数: {overlimit_count}")
            
            results.append(("阶段1_信用债1_1", True, len(df)))
        except Exception as e:
            print(f"   ❌ 加载失败: {e}")
            results.append(("阶段1_信用债1_1", False, 0))
        
        # 2. 阶段1 - 信用债1_2
        print("\n[2/3] 阶段1_信用债1_2")
        try:
            df = loader.load_stage1_credit_1_2()
            print(f"   ✅ 加载成功: {len(df)} 行 × {len(df.columns)} 列")
            
            if '是否超限' in df.columns:
                overlimit_count = (df['是否超限'] == '是').sum()
                print(f"   📊 超限数: {overlimit_count}")
            
            results.append(("阶段1_信用债1_2", True, len(df)))
        except Exception as e:
            print(f"   ❌ 加载失败: {e}")
            results.append(("阶段1_信用债1_2", False, 0))
        
        # 3. 阶段1 - 担保明细
        print("\n[3/3] 阶段1_担保明细")
        try:
            df = loader.load_stage1_guarantee()
            print(f"   ✅ 加载成功: {len(df)} 行 × {len(df.columns)} 列")
            
            if '授信担保公司名称' in df.columns:
                company_count = df['授信担保公司名称'].nunique()
                print(f"   🏢 担保公司数: {company_count}")
            
            results.append(("阶段1_担保明细", True, len(df)))
        except Exception as e:
            print(f"   ❌ 加载失败: {e}")
            results.append(("阶段1_担保明细", False, 0))
        
        # ========== 阶段2核心表校验 ==========
        print("\n\n" + "=" * 80)
        print("📋 阶段2核心表校验")
        print("=" * 80)
        
        # 4. 地域集中度
        print("\n[1/3] 地域集中度限额（含城投）")
        try:
            df = loader.load_stage2_regional()
            print(f"   ✅ 加载成功: {len(df)} 行 × {len(df.columns)} 列")
            
            if '指标名称' in df.columns:
                province_count = df['指标名称'].nunique()
                print(f"   🗺️ 省份/地区数: {province_count}")
            
            if '单一地域总持仓_PR' in df.columns:
                total_position = df['单一地域总持仓_PR'].sum()
                print(f"   💰 总持仓: {total_position:,.2f} 万")
            
            results.append(("地域集中度限额", True, len(df)))
        except Exception as e:
            print(f"   ❌ 加载失败: {e}")
            results.append(("地域集中度限额", False, 0))
        
        # 5. 高风险行业
        print("\n[2/3] 高风险行业")
        try:
            df = loader.load_stage2_high_risk_industry()
            print(f"   ✅ 加载成功: {len(df)} 行 × {len(df.columns)} 列")
            
            if '高风险行业总持仓_PR' in df.columns:
                total_position = df['高风险行业总持仓_PR'].sum()
                print(f"   💰 总持仓: {total_position:,.2f} 万")
            
            if '集中度' in df.columns or '高风险行业集中度' in df.columns:
                conc_field = '集中度' if '集中度' in df.columns else '高风险行业集中度'
                concentration = df[conc_field].iloc[0] if len(df) > 0 else 0
                print(f"   📊 集中度: {concentration*100:.2f}%")
            
            results.append(("高风险行业", True, len(df)))
        except Exception as e:
            print(f"   ❌ 加载失败: {e}")
            results.append(("高风险行业", False, 0))
        
        # 6. 高风险省份
        print("\n[3/3] 高风险省份")
        try:
            df = loader.load_stage2_high_risk_province()
            print(f"   ✅ 加载成功: {len(df)} 行 × {len(df.columns)} 列")
            
            if '高风险省份总持仓_PR' in df.columns:
                total_position = df['高风险省份总持仓_PR'].sum()
                print(f"   💰 总持仓: {total_position:,.2f} 万")
            
            if '集中度' in df.columns or '高风险省份集中度' in df.columns:
                conc_field = '集中度' if '集中度' in df.columns else '高风险省份集中度'
                concentration = df[conc_field].iloc[0] if len(df) > 0 else 0
                print(f"   📊 集中度: {concentration*100:.2f}%")
            
            results.append(("高风险省份", True, len(df)))
        except Exception as e:
            print(f"   ❌ 加载失败: {e}")
            results.append(("高风险省份", False, 0))
        
        # ========== 总结 ==========
        print("\n\n" + "=" * 80)
        print("📊 校验总结")
        print("=" * 80)
        
        success_count = sum(1 for _, success, _ in results if success)
        total_count = len(results)
        
        print(f"\n✅ 成功加载: {success_count}/{total_count} 张表")
        
        print("\n详细结果:")
        for name, success, row_count in results:
            status = "✅" if success else "❌"
            print(f"   {status} {name}: {row_count} 行")
        
        if success_count == total_count:
            print(f"\n🎉 所有表均成功加载！数据文件完整性验证通过！")
        else:
            print(f"\n⚠️ 有 {total_count - success_count} 张表加载失败，请检查数据文件。")
        
        return results
        
    except Exception as e:
        print(f"\n❌ 校验失败: {e}")
        import traceback
        traceback.print_exc()
        return []


if __name__ == "__main__":
    validate_using_dataloader()
