"""
手动使用Excel获取Wind代码
macOS环境下手动执行脚本
"""

import pandas as pd
from pathlib import Path
import time

def manual_wind_code_process():
    """手动处理Wind代码流程"""
    
    template_file = Path("temp/wind_codes_template.xlsx")
    result_file = Path("temp/wind_codes_result.xlsx")
    
    print("=" * 80)
    print("手动获取Wind代码（macOS环境）")
    print("=" * 80)
    
    # 检查模板文件
    if not template_file.exists():
        print(f"❌ 模板文件不存在: {template_file}")
        print("   请先运行: python3 run_stage0.py")
        return
    
    print(f"\n✓ 模板文件已生成: {template_file.absolute()}")
    
    # 读取模板查看发行人数量
    df_template = pd.read_excel(template_file)
    issuer_count = len(df_template)
    print(f"✓ 需要获取Wind代码的发行人: {issuer_count} 个")
    
    # 操作提示
    print("\n" + "=" * 80)
    print("📋 操作步骤（约2-3分钟）：")
    print("=" * 80)
    print(f"\n1. 在Excel中打开: {template_file.absolute()}")
    print("\n2. 在B2单元格输入公式: =To_WindCode(A2)")
    print("\n3. 按回车确认")
    print("\n4. 复制B2单元格（Cmd+C）")
    print(f"\n5. 选中B3到B{issuer_count+1}的区域")
    print("\n6. 粘贴（Cmd+V）- Excel会自动计算所有Wind代码")
    print("\n7. 等待Wind API返回结果（约10-30秒）")
    print(f"\n8. 另存为: {result_file.absolute()}")
    print("   （文件 → 另存为... → 选择Excel格式）")
    print("\n9. 关闭Excel")
    print("\n10. 重新运行: python3 run_stage0.py")
    print("\n" + "=" * 80)
    
    # 等待结果文件
    print("\n⏳ 等待您完成Excel操作...")
    print(f"   (检测结果文件: {result_file.name})")
    
    for i in range(600):  # 最多等待10分钟
        if result_file.exists():
            print(f"\n✅ 检测到结果文件！")
            
            # 验证结果
            try:
                df_result = pd.read_excel(result_file)
                
                if '发行人名称' in df_result.columns and 'Wind代码' in df_result.columns:
                    success_count = df_result['Wind代码'].notna().sum()
                    print(f"✓ 成功获取: {success_count}/{issuer_count} ({success_count/issuer_count*100:.1f}%)")
                    
                    if success_count > 0:
                        print("\n✓ Wind代码获取完成！")
                        print("\n下一步: 运行 python3 run_stage0.py 重新处理数据")
                        return
                    else:
                        print("\n⚠️  未检测到Wind代码数据")
                        print("   请确保Excel公式已计算完成")
                else:
                    print("\n⚠️  结果文件格式不正确")
                    print("   请确保包含'发行人名称'和'Wind代码'列")
                    
            except Exception as e:
                print(f"\n⚠️  读取结果文件失败: {e}")
            
            break
        
        if i % 10 == 0 and i > 0:
            print(f"   ... 等待中 ({i}秒)")
        
        time.sleep(1)
    
    if not result_file.exists():
        print("\n⏸️  未检测到结果文件")
        print(f"   完成后请将结果保存为: {result_file.absolute()}")


if __name__ == "__main__":
    manual_wind_code_process()
