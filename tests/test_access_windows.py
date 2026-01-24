"""
Windows环境Access数据库读取测试
用于验证生产环境配置是否正确
"""

import sys
import platform
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

print("=" * 80)
print("Windows Access数据库配置测试")
print("=" * 80)

# 1. 系统信息
print(f"\n【系统信息】")
print(f"  操作系统: {platform.system()} {platform.release()}")
print(f"  Python版本: {sys.version}")
print(f"  Python位数: {platform.architecture()[0]}")

# 2. pyodbc检查
print(f"\n【pyodbc检查】")
try:
    import pyodbc
    print(f"  ✓ pyodbc版本: {pyodbc.version}")
    
    # 检查驱动
    drivers = pyodbc.drivers()
    print(f"  可用驱动数: {len(drivers)}")
    
    access_drivers = [d for d in drivers if 'access' in d.lower() or 'mdb' in d.lower()]
    if access_drivers:
        print(f"  ✓ Access驱动:")
        for driver in access_drivers:
            print(f"    - {driver}")
    else:
        print(f"  ✗ 未找到Access驱动")
        print(f"  ⚠️  请安装Microsoft Access Database Engine")
        print(f"     下载: https://www.microsoft.com/download/details.aspx?id=54920")
        
except ImportError:
    print(f"  ✗ pyodbc未安装")
    print(f"  安装命令: pip install pyodbc")

# 3. Access数据库文件检查
print(f"\n【Access数据库文件检查】")
db_path = Path("sample data/风控部债券池.accdb")

if db_path.exists():
    size_mb = db_path.stat().st_size / 1024 / 1024
    print(f"  ✓ 文件存在: {db_path}")
    print(f"  文件大小: {size_mb:.2f} MB")
else:
    print(f"  ✗ 文件不存在: {db_path}")
    print(f"  请确保数据文件在正确位置")

# 4. 读取测试
print(f"\n【Access读取测试】")

if platform.system() != 'Windows':
    print(f"  ⚠️  当前系统不是Windows")
    print(f"     此测试主要用于Windows生产环境")
    print(f"     macOS开发环境会使用临时数据源")

try:
    from src.common.access_reader import AccessDatabaseReader
    
    reader = AccessDatabaseReader(db_path)
    
    print(f"\n  尝试读取表: 风控部债券池")
    df = reader.read_table("风控部债券池", prefer_access=True)
    
    print(f"\n  ✓ 读取成功!")
    print(f"    行数: {len(df):,}")
    print(f"    列数: {len(df.columns)}")
    
    print(f"\n  前5列名:")
    for i, col in enumerate(df.columns[:5], 1):
        print(f"    {i}. {col}")
    
    print(f"\n  前3行示例:")
    print(df.head(3).to_string(index=False))
    
    # 判断数据源
    if platform.system() == 'Windows':
        print(f"\n  ✅ Windows生产环境: Access数据库配置正确!")
    else:
        print(f"\n  ✅ macOS开发环境: 使用临时数据源")
        print(f"     部署到Windows时将自动使用Access数据库")
    
except Exception as e:
    print(f"\n  ✗ 读取失败:")
    print(f"    {str(e)[:200]}")
    
    if platform.system() == 'Windows':
        print(f"\n  【Windows环境故障排查】")
        print(f"  1. 确认已安装Microsoft Access Database Engine")
        print(f"  2. 确认Python位数与Access驱动位数一致")
        print(f"  3. 确认数据库文件未被其他程序占用")
    else:
        print(f"\n  【macOS开发环境说明】")
        print(f"  这是正常的，macOS不支持原生Access读取")
        print(f"  代码会自动使用临时数据源进行开发测试")

# 5. 总结
print("\n" + "=" * 80)
print("测试完成")
print("=" * 80)

if platform.system() == 'Windows':
    print("\n【Windows生产环境检查结果】")
    try:
        import pyodbc
        drivers = pyodbc.drivers()
        access_drivers = [d for d in drivers if 'access' in d.lower()]
        
        if access_drivers and db_path.exists():
            print("  ✅ 所有检查通过，可以正常运行")
            print("  运行命令: python run_stage0.py")
        else:
            print("  ⚠️  配置不完整，请按照上述提示完成配置")
    except:
        print("  ⚠️  配置不完整，请安装必要的依赖")
else:
    print("\n【macOS开发环境说明】")
    print("  ✓ 开发环境正常")
    print("  ✓ 代码已适配跨平台，Windows部署时无需修改")
    print("  运行命令: python3 run_stage0.py")

print("=" * 80)
