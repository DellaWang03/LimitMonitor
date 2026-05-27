"""
简单测试日期验证器功能
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("=" * 70)
print("日期验证器简单测试")
print("=" * 70)

try:
    print("\n1. 导入DateValidator...")
    from src.utils import DateValidator
    print("✅ 导入成功")
    
    print("\n2. 创建日期验证器...")
    data_dir = project_root / "sample data"
    validator = DateValidator(data_dir)
    print("✅ 创建成功")
    
    print("\n3. 获取业务日期信息...")
    date_info = validator.get_business_date_info()
    print(f"✅ 成功获取:")
    print(f"   今天: {date_info['today']}")
    print(f"   T-1日期: {date_info['t_minus_1']}")
    print(f"   今天是交易日: {date_info['is_trading_day']}")
    
    print("\n4. 日志摘要...")
    validator.log_business_date_summary()
    
    print("\n" + "=" * 70)
    print("✅ 测试完成！")
    print("=" * 70)
    
except Exception as e:
    print(f"\n❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
