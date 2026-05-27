"""
环境检查脚本
检查阶段0运行所需的所有依赖
"""

import sys
from pathlib import Path

print("=" * 80)
print("阶段0环境检查")
print("=" * 80)

# 1. Python版本
print(f"\n1. Python版本")
print(f"   版本: {sys.version}")
print(f"   ✓ Python {sys.version_info.major}.{sys.version_info.minor}")

# 2. 核心依赖
print(f"\n2. 核心依赖包")

deps = {
    'pandas': 'pandas',
    'numpy': 'numpy',
    'openpyxl': 'openpyxl',
    'loguru': 'loguru',
    'pyyaml': 'yaml',
}

for name, import_name in deps.items():
    try:
        mod = __import__(import_name)
        version = getattr(mod, '__version__', 'unknown')
        print(f"   ✓ {name}: {version}")
    except ImportError:
        print(f"   ✗ {name}: 未安装")

# 3. pyodbc (Access数据库)
print(f"\n3. pyodbc (Access数据库)")
try:
    import pyodbc
    print(f"   ✓ pyodbc: {pyodbc.version}")
    
    # 检查驱动
    drivers = pyodbc.drivers()
    print(f"   可用驱动: {len(drivers)}个")
    access_drivers = [d for d in drivers if 'access' in d.lower()]
    if access_drivers:
        print(f"   ✓ Access驱动: {access_drivers}")
    else:
        print(f"   ⚠️  未找到Access驱动")
        print(f"      macOS用户建议使用mdb-tools导出CSV")
except ImportError:
    print(f"   ✗ pyodbc: 未安装")
    print(f"      安装: pip3 install --user pyodbc")

# 4. WindPy (Wind API)
print(f"\n4. WindPy (Wind API)")
try:
    from WindPy import w
    print(f"   ✓ WindPy: 已安装")
    
    # 尝试连接
    if not w.isconnected():
        print(f"   尝试连接Wind API...")
        w.start()
    
    if w.isconnected():
        print(f"   ✓ Wind API: 已连接")
    else:
        print(f"   ⚠️  Wind API: 连接失败")
        print(f"      请确保Wind终端已启动并登录")
except ImportError:
    print(f"   ✗ WindPy: 未安装")
    print(f"      安装方式:")
    print(f"      1. 从Wind终端: API → Python API")
    print(f"      2. 或手动: pip3 install WindPy")

# 5. 数据文件
print(f"\n5. 数据文件检查")

project_root = Path(__file__).parent
data_dir = project_root / "sample data"

required_files = [
    "德勤-主体评级列表.xlsx",
    "风控部债券池.accdb",
    "净资产.xlsx",
    "标准日期表.xlsx",
    "统计报表底稿1_债券.xlsx",
]

for filename in required_files:
    file_path = data_dir / filename
    if file_path.exists():
        size_mb = file_path.stat().st_size / 1024 / 1024
        print(f"   ✓ {filename} ({size_mb:.2f} MB)")
    else:
        print(f"   ✗ {filename}: 不存在")

# 6. 输出目录
print(f"\n6. 输出目录")
output_dir = project_root / "data" / "stage0_output"
print(f"   路径: {output_dir}")
if not output_dir.exists():
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"   ✓ 已创建")
else:
    print(f"   ✓ 已存在")

# 总结
print("\n" + "=" * 80)
print("环境检查完成")
print("=" * 80)

print("\n下一步:")
print("1. 安装缺失的依赖: pip3 install --user -r requirements.txt")
print("2. 安装WindPy: 从Wind终端或pip install WindPy")
print("3. 运行阶段0: python3 run_stage0.py")
print("=" * 80)
