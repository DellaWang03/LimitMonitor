"""
尝试使用xlwings可见模式获取Wind代码（macOS）
"""

import pandas as pd
from pathlib import Path
import time

def try_xlwings_visible():
    """尝试使用xlwings可见模式"""
    
    try:
        import xlwings as xw
    except ImportError:
        print("❌ 需要安装xlwings: pip3 install xlwings")
        return
    
    print("=" * 80)
    print("尝试使用xlwings可见模式获取Wind代码")
    print("=" * 80)
    
    # 读取缺失的发行人列表
    missing_file = Path("temp/missing_wind_codes.txt")
    if not missing_file.exists():
        print(f"❌ 缺失列表文件不存在: {missing_file}")
        return
    
    with open(missing_file, 'r', encoding='utf-8') as f:
        issuer_names = [line.strip() for line in f if line.strip()]
    
    print(f"\n✓ 读取缺失的发行人: {len(issuer_names)} 个")
    
    # 只处理前10个测试
    test_count = min(10, len(issuer_names))
    test_issuers = issuer_names[:test_count]
    
    print(f"✓ 测试模式: 处理前 {test_count} 个发行人")
    
    temp_file = Path("temp/wind_codes_test.xlsx")
    
    print("\n启动Excel（可见模式）...")
    
    try:
        # 使用可见模式
        app = xw.App(visible=True, add_book=False)
        print("✓ Excel已启动")
        
        wb = app.books.add()
        ws = wb.sheets[0]
        
        print("✓ 工作簿已创建")
        
        # 写入表头
        ws.range('A1').value = '发行人名称'
        ws.range('B1').value = 'Wind代码'
        
        # 写入发行人名称
        print(f"\n写入 {test_count} 个发行人名称...")
        for i, name in enumerate(test_issuers, 2):
            ws.range(f'A{i}').value = name
            print(f"  {i-1}. {name}")
        
        # 写入公式
        print("\n添加To_WindCode()公式...")
        for i in range(2, test_count + 2):
            ws.range(f'B{i}').formula = f'=To_WindCode(A{i})'
        
        print("✓ 公式已添加")
        
        # 强制计算
        print("\n执行Excel计算...")
        app.calculate()
        
        # 等待计算
        wait_time = 10
        print(f"\n等待Wind API响应（{wait_time}秒）...")
        time.sleep(wait_time)
        
        # 读取结果
        print("\n读取Wind代码...")
        results = []
        for i in range(2, test_count + 2):
            issuer = ws.range(f'A{i}').value
            wind_code = ws.range(f'B{i}').value
            results.append({
                '发行人名称': issuer,
                'Wind代码': wind_code
            })
            status = "✓" if wind_code and pd.notna(wind_code) and wind_code != '#N/A' else "✗"
            print(f"  {status} {issuer}: {wind_code}")
        
        # 保存结果
        wb.save(temp_file)
        print(f"\n✓ 结果已保存: {temp_file.absolute()}")
        
        # 创建DataFrame
        df_result = pd.DataFrame(results)
        success_count = df_result['Wind代码'].notna().sum()
        
        print(f"\n" + "=" * 80)
        print(f"测试结果: {success_count}/{test_count} 成功")
        print("=" * 80)
        
        if success_count > 0:
            print("\n✅ xlwings在macOS上可以工作！")
            print("\n下一步:")
            print("1. 关闭Excel窗口")
            print("2. 如果测试成功，可以修改代码处理全部1023个发行人")
        else:
            print("\n⚠️  未能获取Wind代码")
            print("   请确保:")
            print("   1. Wind终端已启动并登录")
            print("   2. Excel的Wind插件已安装")
            print("   3. To_WindCode()函数可用")
        
        input("\n按回车键关闭Excel...")
        
        wb.close()
        app.quit()
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        
        try:
            wb.close()
        except:
            pass
        try:
            app.quit()
        except:
            pass


if __name__ == "__main__":
    try_xlwings_visible()
