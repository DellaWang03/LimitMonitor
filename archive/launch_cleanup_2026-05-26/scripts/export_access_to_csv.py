"""
从Access数据库导出数据到CSV
适用于macOS（无需pyodbc驱动）
"""

import subprocess
import sys
from pathlib import Path

print("=" * 80)
print("Access数据库导出工具")
print("=" * 80)

access_file = Path("sample data/风控部债券池.accdb")
output_file = Path("sample data/风控部债券池_导出.csv")

if not access_file.exists():
    print(f"\n✗ Access文件不存在: {access_file}")
    sys.exit(1)

print(f"\n输入文件: {access_file}")
print(f"文件大小: {access_file.stat().st_size / 1024 / 1024:.2f} MB")

print("\n" + "=" * 80)
print("导出方案")
print("=" * 80)

print("\n【方案1：手动导出（推荐）】")
print("  1. 在Windows电脑上打开Access数据库")
print("  2. 右键表'风控部债券池' → 导出 → Excel")
print(f"  3. 保存为: {access_file.parent}/风控部债券池_导出.xlsx")
print("  4. 将导出的Excel文件复制回此目录")

print("\n【方案2：使用mdb-tools（macOS命令行工具）】")
print("  需要安装Homebrew和mdb-tools:")
print("  ")
print("  # 安装Homebrew（如未安装）")
print("  /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")
print("  ")
print("  # 安装mdb-tools")
print("  brew install mdb-tools")
print("  ")
print("  # 导出表")
print(f"  mdb-export '{access_file}' '风控部债券池' > '{output_file}'")

print("\n【方案3：临时使用阶段0的Excel输出（最快）】")
print("  如果只是为了测试代码逻辑，可以临时使用:")
print(f"  sample data/阶段/限额监控_阶段0_风控债券池.xlsx")
print("  中的'风控部债券池'工作表")

print("\n" + "=" * 80)
print("建议")
print("=" * 80)
print("\n由于您的系统是macOS，且Access数据库主要在Windows上使用，")
print("建议使用【方案1】或【方案3】：")
print("  - 方案1：在Windows上一次性导出，后续Python直接读取")
print("  - 方案3：临时使用现有Excel，先验证代码逻辑")
print("\n导出后，我会修改代码自动检测并读取导出的Excel/CSV文件。")
print("=" * 80)
