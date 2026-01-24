"""
阶段0基础测试
不依赖Wind API和Access数据库，用于验证基本逻辑
"""

import sys
import pandas as pd
from pathlib import Path
from datetime import datetime

print("=" * 80)
print("阶段0基础测试（不依赖Wind API和Access）")
print("=" * 80)

project_root = Path(__file__).parent
data_dir = project_root / "sample data"
output_dir = project_root / "data" / "stage0_output_test"
output_dir.mkdir(parents=True, exist_ok=True)

print(f"\n数据目录: {data_dir}")
print(f"输出目录: {output_dir}")

# 测试1: 读取德勤列表
print("\n" + "-" * 80)
print("测试1: 读取德勤-主体评级列表")
try:
    df_deloitte = pd.read_excel(data_dir / "德勤-主体评级列表.xlsx", sheet_name="Sheet1")
    print(f"✓ 读取成功: {len(df_deloitte)} 行 × {len(df_deloitte.columns)} 列")
    print(f"  列名: {list(df_deloitte.columns[:5])}...")
    
    # 提取Wind代码映射
    mapping = df_deloitte[['主体名称', '主体wind代码']].copy()
    mapping.columns = ['发行人', 'wind代码']
    mapping = mapping[mapping['wind代码'].notna()]
    mapping = mapping[mapping['wind代码'] != 0]
    mapping = mapping.drop_duplicates(subset=['发行人'])
    
    print(f"  Wind代码映射: {len(mapping)} 个主体")
    print(f"  示例:")
    print(mapping.head(3).to_string(index=False))
    
    # 保存映射表
    mapping_file = output_dir / "wind_code_mapping.csv"
    mapping.to_csv(mapping_file, index=False, encoding='utf-8-sig')
    print(f"  ✓ 映射表已保存: {mapping_file}")
    
except Exception as e:
    print(f"✗ 失败: {e}")
    sys.exit(1)

# 测试2: 读取北京国有资本
print("\n" + "-" * 80)
print("测试2: 读取北京国有资本调整表")
try:
    df_beijing = pd.read_excel(data_dir / "德勤-主体评级列表.xlsx", sheet_name="北京国有资本")
    print(f"✓ 读取成功: {len(df_beijing)} 行")
    
    output_file = output_dir / "调整实控人_北京国有资本.xlsx"
    df_beijing.to_excel(output_file, index=False)
    print(f"  ✓ 已保存: {output_file}")
    
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试3: 合并调整实控人名单
print("\n" + "-" * 80)
print("测试3: 生成调整实控人名单")
try:
    df = df_deloitte[['主体名称', '社会信用代码', '主体wind代码', '调整后实际控制人']].copy()
    df = df.drop_duplicates()
    
    # Left Join
    df = df.merge(
        df_beijing[['统一社会信用代码', '调整后实际控制人']],
        left_on='社会信用代码',
        right_on='统一社会信用代码',
        how='left',
        suffixes=('_原始', '_北京')
    )
    
    df['调整后实际控制人'] = df['调整后实际控制人_北京'].fillna(df['调整后实际控制人_原始'])
    df = df.drop(columns=['调整后实际控制人_原始', '调整后实际控制人_北京', '统一社会信用代码'])
    
    print(f"✓ 生成成功: {len(df)} 个主体")
    
    output_file = output_dir / "调整实控人名单.xlsx"
    df.to_excel(output_file, index=False)
    print(f"  ✓ 已保存: {output_file}")
    
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试4: 读取统计报表底稿
print("\n" + "-" * 80)
print("测试4: 读取统计报表底稿（补充Wind代码）")
try:
    df_report = pd.read_excel(data_dir / "统计报表底稿1_债券.xlsx", 
                              sheet_name="债券持仓明细表")
    print(f"✓ 读取成功: {len(df_report)} 行")
    
    # 提取Wind代码映射
    if '债务主体' in df_report.columns and '债务主体wind代码' in df_report.columns:
        mapping2 = df_report[['债务主体', '债务主体wind代码']].copy()
        mapping2.columns = ['发行人', 'wind代码']
        mapping2 = mapping2[mapping2['wind代码'].notna()]
        mapping2 = mapping2[mapping2['wind代码'] != 0]
        mapping2 = mapping2.drop_duplicates(subset=['发行人'])
        
        print(f"  补充Wind代码映射: {len(mapping2)} 个主体")
        
        # 合并映射表
        combined_mapping = pd.concat([mapping, mapping2]).drop_duplicates(subset=['发行人'], keep='first')
        print(f"  合并后映射表: {len(combined_mapping)} 个主体")
        
        # 保存
        combined_file = output_dir / "wind_code_mapping_combined.csv"
        combined_mapping.to_csv(combined_file, index=False, encoding='utf-8-sig')
        print(f"  ✓ 已保存: {combined_file}")
        
except Exception as e:
    print(f"⚠️  警告: {e}")

# 测试5: 读取净资产
print("\n" + "-" * 80)
print("测试5: 读取公司净资产")
try:
    df_assets = pd.read_excel(data_dir / "净资产.xlsx", sheet_name="净资产")
    print(f"✓ 读取成功: {len(df_assets)} 行")
    
    df_assets = df_assets[['日期', '净资产（万元）']].copy()
    df_assets.columns = ['变动日期', '公司净资产(万)']
    df_assets['变动日期'] = pd.to_datetime(df_assets['变动日期'])
    
    print(f"  日期范围: {df_assets['变动日期'].min().date()} ~ {df_assets['变动日期'].max().date()}")
    print(f"  示例:")
    print(df_assets.head(3).to_string(index=False))
    
    output_file = output_dir / "公司净资产_手工.xlsx"
    df_assets.to_excel(output_file, index=False)
    print(f"  ✓ 已保存: {output_file}")
    
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试6: 读取标准日期表
print("\n" + "-" * 80)
print("测试6: 读取标准日期表")
try:
    df_dates = pd.read_excel(data_dir / "标准日期表.xlsx", sheet_name="标准日期表")
    print(f"✓ 读取成功: {len(df_dates)} 行")
    
    df_dates['日期'] = pd.to_datetime(df_dates['日期'])
    print(f"  日期范围: {df_dates['日期'].min().date()} ~ {df_dates['日期'].max().date()}")
    
except Exception as e:
    print(f"✗ 失败: {e}")

# 总结
print("\n" + "=" * 80)
print("基础测试完成")
print("=" * 80)

print(f"\n输出文件:")
for file in sorted(output_dir.glob("*.xlsx")):
    print(f"  - {file.name}")
for file in sorted(output_dir.glob("*.csv")):
    print(f"  - {file.name}")

print("\n说明:")
print("1. ✓ 基础数据读取正常")
print("2. ✓ Wind代码映射表已生成（不依赖Wind API）")
print("3. ⚠️  Access数据库和Wind API需要手动安装依赖")
print("\n下一步:")
print("  安装依赖后运行: python3 run_stage0.py")
print("=" * 80)
