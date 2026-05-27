"""
测试配置加载器 - 验证数据源路径配置
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 本地开发环境默认验证 local profile，避免误把 migration 挂载缺失当成代码问题
os.environ.setdefault("LIMIT_MONITOR_PROFILE", "local")

from src.utils.config_loader import get_config

print("=" * 70)
print("配置加载器测试 - 数据源路径验证")
print("=" * 70)

try:
    # 获取配置实例
    config = get_config()
    
    # 测试数据源目录
    print("\n1. 测试数据源根目录配置:")
    data_dir = config.get_data_dir()
    print(f"   当前 profile: {config.get_active_profile()}")
    print(f"   配置路径: {data_dir}")
    print(f"   是否存在: {'✅' if data_dir.exists() else '❌'}")
    
    # 测试配置文件中的其他路径
    print("\n2. 测试配置文件中的数据源路径:")
    data_dir_config = config.get("data_sources.data_dir")
    print(f"   data_sources.data_dir = {data_dir_config}")
    
    bond_holdings = config.get("data_sources.excel_files.bond_holdings")
    print(f"   bond_holdings = {bond_holdings}")
    
    bond_pool_db = config.get("data_sources.access_db.bond_pool_db")
    print(f"   bond_pool_db = {bond_pool_db}")
    
    # 验证关键数据文件是否存在
    print("\n3. 验证关键数据文件:")
    required_files = [
        "标准日期表.xlsx",
        "限额配置_当前.xlsx",
        "限额监控_阶段0_指标设置.xlsx",
        "统计报表底稿1_债券.xlsx",
        "统计报表底稿2_债券SPPI.xlsx",
        "风控部债券池.accdb",
        "净资产.xlsx",
        "金融工具池设置.xlsx",
        "德勤-主体评级列表.xlsx",
        "发行人类型调整表.xlsx"
    ]
    
    missing_files = []
    for file_name in required_files:
        file_path = config.get_data_file_path(file_name)
        status = "✅" if file_path.exists() else "❌"
        print(f"   {status} {file_name} -> {file_path}")
        if not file_path.exists():
            missing_files.append(file_name)
    
    # 总结
    print("\n" + "=" * 70)
    if missing_files:
        print(f"⚠️  警告: {len(missing_files)} 个文件缺失")
        for file_name in missing_files:
            print(f"   - {file_name}")
    else:
        print("✅ 所有必需文件均已就绪！")
    print("=" * 70)
    
except Exception as e:
    print(f"\n❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
