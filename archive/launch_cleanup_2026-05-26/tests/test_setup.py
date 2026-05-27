"""
项目配置测试脚本
验证所有模块是否正常加载
"""

import sys
import os
from pathlib import Path

print("=" * 80)
print("限额监控自动化系统 - 配置测试")
print("=" * 80)

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.environ.setdefault("LIMIT_MONITOR_PROFILE", "local")

# 1. 检查 Python 版本
print(f"\n1. Python 版本: {sys.version}")

# 2. 检查项目结构
print("\n2. 检查项目结构:")

required_dirs = [
    'src',
    'src/extractors',
    'src/transformers',
    'src/stage0',
    'src/stage1',
    'src/stage2',
    'src/utils',
    'config',
    'src/visualization',
    'scripts',
    'tests'
]

for dir_name in required_dirs:
    dir_path = project_root / dir_name
    status = "✓" if dir_path.exists() else "✗"
    print(f"  {status} {dir_name}/")

# 3. 检查配置文件
print("\n3. 检查配置文件:")
config_files = [
    'config/settings.yaml',
    'requirements.txt',
    'README.md'
]

for file_name in config_files:
    file_path = project_root / file_name
    status = "✓" if file_path.exists() else "✗"
    print(f"  {status} {file_name}")

# 4. 测试导入模块
print("\n4. 测试导入模块:")

try:
    from src.utils.config_loader import ConfigLoader
    print("  ✓ ConfigLoader")
except Exception as e:
    print(f"  ✗ ConfigLoader: {e}")

try:
    from src.utils.logger import setup_logger
    print("  ✓ Logger")
except Exception as e:
    print(f"  ✗ Logger: {e}")

try:
    from src.extractors.bond_pool_extractor import BondPoolExtractor
    print("  ✓ BondPoolExtractor")
except Exception as e:
    print(f"  ✗ BondPoolExtractor: {e}")

try:
    from src.transformers.bond_transformer import BondTransformer
    print("  ✓ BondTransformer")
except Exception as e:
    print(f"  ✗ BondTransformer: {e}")

# 5. 测试配置加载
print("\n5. 测试配置加载:")

try:
    from src.utils.config_loader import get_config
    config = get_config()
    
    settings = config.load_settings()
    print(f"  ✓ 主配置: {settings['project']['name']}")
    
except Exception as e:
    print(f"  ✗ 配置加载失败: {e}")

# 6. 检查数据文件
print("\n6. 检查数据文件:")

try:
    from src.utils.config_loader import get_config
    config = get_config()
    
    data_sources = [
        ("风控部债券池.accdb", '风控部债券池'),
        ("债券持仓表.xlsx", '债券持仓表'),
    ]
    
    for file_name, name in data_sources:
        try:
            path = config.get_data_file_path(file_name)
            status = "✓" if path.exists() else "✗"
            print(f"  {status} {name}: {path.name}")
        except Exception as e:
            print(f"  ✗ {name}: {e}")
            
except Exception as e:
    print(f"  配置加载失败: {e}")

# 7. 依赖检查
print("\n7. 检查关键依赖:")

dependencies = [
    'pandas',
    'numpy',
    'openpyxl',
    'yaml',
    'loguru'
]

for dep in dependencies:
    try:
        __import__(dep)
        print(f"  ✓ {dep}")
    except ImportError:
        print(f"  ✗ {dep} (未安装)")

print("\n" + "=" * 80)
print("测试完成！")
print("=" * 80)

print("\n提示:")
print("  - 如有 ✗ 标记，请先解决相关问题")
print("  - 缺少的依赖请运行: pip install -r requirements.txt")
print("  - 全链路运行: bash run_daily.sh")
print("  - Web界面入口: streamlit run app.py")
print()
