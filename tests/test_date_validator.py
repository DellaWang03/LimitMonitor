"""
测试日期验证器功能
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils import DateValidator
from datetime import datetime, timedelta

def test_date_validator():
    """测试日期验证器的基本功能"""
    
    # 使用全局project_root
    data_dir = project_root / "sample data"
    
    print("=" * 70)
    print("测试日期验证器")
    print("=" * 70)
    
    # 1. 创建验证器
    print("\n1. 创建日期验证器...")
    validator = DateValidator(data_dir)
    print("✅ 创建成功")
    
    # 2. 测试获取标准日期表
    print("\n2. 读取标准日期表...")
    df_dates = validator.get_standard_dates()
    print(f"✅ 读取成功: {len(df_dates)} 个交易日")
    print(f"   最早日期: {df_dates['日期'].min().date()}")
    print(f"   最晚日期: {df_dates['日期'].max().date()}")
    
    # 3. 测试获取T-1日期
    print("\n3. 测试T-1日期获取...")
    
    # 测试今天的T-1
    t_minus_1 = validator.get_t_minus_1_date()
    print(f"✅ 今天: {datetime.now().date()}")
    print(f"   T-1日期: {t_minus_1.date()}")
    
    # 测试指定日期的T-1
    test_date = datetime(2026, 1, 23).date()  # 假设是周五
    t_minus_1_specific = validator.get_t_minus_1_date(test_date)
    print(f"\n   测试日期: {test_date}")
    print(f"   T-1日期: {t_minus_1_specific.date()}")
    
    # 4. 测试业务日期信息
    print("\n4. 获取业务日期信息...")
    date_info = validator.get_business_date_info()
    print(f"✅ 业务日期信息:")
    print(f"   今天: {date_info['today']}")
    print(f"   T-1日期: {date_info['t_minus_1']}")
    print(f"   今天是交易日: {date_info['is_trading_day']}")
    print(f"   T-1日期字符串: {date_info['t_minus_1_str']}")
    
    # 5. 测试Access数据库验证
    print("\n5. 测试Access数据库验证...")
    access_db_path = data_dir / "风控部债券池.accdb"
    
    if access_db_path.exists():
        is_fresh, message, actual_date = validator.validate_access_database_freshness(
            access_db_path,
            strict_mode=False
        )
        
        print(f"\n验证结果:")
        print(f"  是否通过: {'✅ 是' if is_fresh else '❌ 否'}")
        if actual_date:
            print(f"  实际日期: {actual_date.date()}")
        print(f"\n详细信息:")
        print(message)
    else:
        print(f"⚠️  Access数据库不存在: {access_db_path}")
    
    # 6. 测试日志摘要
    print("\n6. 测试日志摘要输出...")
    validator.log_business_date_summary()
    
    print("\n" + "=" * 70)
    print("✅ 所有测试完成！")
    print("=" * 70)


def test_file_overwrite():
    """测试文件覆盖功能"""
    import pandas as pd
    
    print("\n" + "=" * 70)
    print("测试文件覆盖功能")
    print("=" * 70)
    
    # 使用全局project_root
    test_output_dir = project_root / "data" / "current" / "stage0_output"
    test_file = test_output_dir / "test_overwrite.xlsx"
    
    # 确保输出目录存在
    test_output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. 第一次保存
    print("\n1. 第一次保存文件...")
    df1 = pd.DataFrame({
        '列1': [1, 2, 3],
        '列2': ['A', 'B', 'C']
    })
    
    file_exists_before = test_file.exists()
    print(f"   文件存在（保存前）: {file_exists_before}")
    
    df1.to_excel(test_file, index=False)
    print(f"   ✅ 已保存: {test_file.name}")
    
    # 读取验证
    df_read1 = pd.read_excel(test_file)
    print(f"   验证读取: {len(df_read1)} 行")
    
    # 2. 第二次保存（覆盖）
    print("\n2. 第二次保存文件（覆盖）...")
    df2 = pd.DataFrame({
        '列1': [10, 20, 30, 40],
        '列2': ['X', 'Y', 'Z', 'W'],
        '列3': [100, 200, 300, 400]  # 新增列
    })
    
    file_exists_before = test_file.exists()
    print(f"   文件存在（保存前）: {file_exists_before}")
    
    df2.to_excel(test_file, index=False)
    print(f"   ✅ 已覆盖: {test_file.name}")
    
    # 读取验证
    df_read2 = pd.read_excel(test_file)
    print(f"   验证读取: {len(df_read2)} 行 × {len(df_read2.columns)} 列")
    print(f"   验证数据已更新: {len(df_read2) == 4 and len(df_read2.columns) == 3}")
    
    # 3. 清理测试文件
    print("\n3. 清理测试文件...")
    test_file.unlink()
    print(f"   ✅ 已删除: {test_file.name}")
    
    print("\n" + "=" * 70)
    print("✅ 文件覆盖测试完成！")
    print("=" * 70)


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("日期验证器和文件覆盖功能测试")
    print("=" * 70)
    
    try:
        # 测试日期验证器
        test_date_validator()
        
        # 测试文件覆盖
        test_file_overwrite()
        
        print("\n" + "=" * 70)
        print("✅ 所有测试通过！")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
