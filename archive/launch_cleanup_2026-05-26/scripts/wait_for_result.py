"""
等待用户完成Excel操作并自动继续处理
"""

import pandas as pd
from pathlib import Path
import time
import subprocess

def wait_and_process():
    """等待结果文件并自动处理"""
    
    result_file = Path("temp/wind_codes_result.xlsx")
    
    print("=" * 80)
    print("等待Excel操作完成...")
    print("=" * 80)
    print("\n已为您打开:")
    print("  1. temp/wind_codes_template.xlsx (Excel模板)")
    print("  2. temp/操作说明.txt (操作步骤)")
    print("\n请按照操作说明完成Excel操作")
    print(f"\n检测目标文件: {result_file.absolute()}")
    print("\n" + "=" * 80)
    
    # 等待结果文件
    check_count = 0
    while True:
        if result_file.exists():
            print("\n✅ 检测到结果文件！")
            
            # 等待文件写入完成
            time.sleep(2)
            
            # 验证文件
            try:
                df = pd.read_excel(result_file)
                
                if '发行人名称' in df.columns and 'Wind代码' in df.columns:
                    success_count = df['Wind代码'].notna().sum()
                    total_count = len(df)
                    
                    print(f"\n✓ 成功读取结果文件")
                    print(f"✓ 有效Wind代码: {success_count}/{total_count} ({success_count/total_count*100:.1f}%)")
                    
                    if success_count > 0:
                        print("\n" + "=" * 80)
                        print("自动重新运行阶段0...")
                        print("=" * 80)
                        
                        # 运行阶段0
                        result = subprocess.run(
                            ['python3', 'run_stage0.py'],
                            capture_output=True,
                            text=True
                        )
                        
                        # 显示关键输出
                        print(result.stdout)
                        
                        if result.returncode == 0:
                            print("\n" + "=" * 80)
                            print("🎉 阶段0处理完成！Wind代码已更新！")
                            print("=" * 80)
                        else:
                            print("\n⚠️  运行出现问题，请查看上方日志")
                        
                        break
                    else:
                        print("\n⚠️  未检测到有效Wind代码")
                        print("   请确保Excel公式已正确计算")
                        print("   或按Ctrl+C退出后手动运行: python3 run_stage0.py")
                else:
                    print("\n⚠️  结果文件格式不正确")
                    print(f"   期望列: ['发行人名称', 'Wind代码']")
                    print(f"   实际列: {df.columns.tolist()}")
                    print("\n   请检查文件并重新保存")
                    
            except Exception as e:
                print(f"\n⚠️  读取文件失败: {e}")
                print("   请确保文件已正确保存")
        
        # 定期提示
        check_count += 1
        if check_count % 10 == 0:
            elapsed = check_count * 2
            print(f"⏳ 等待中... ({elapsed}秒)")
        
        time.sleep(2)


if __name__ == "__main__":
    try:
        wait_and_process()
    except KeyboardInterrupt:
        print("\n\n⏸️  已停止等待")
        print("完成Excel操作后，请手动运行: python3 run_stage0.py")
