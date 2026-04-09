"""
检查是否有历史数据可以对比
"""
import sys
from pathlib import Path
import pandas as pd
import os
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent

print("=" * 80)
print("查找历史输出数据")
print("=" * 80)

# 1. 检查 data/history 目录
history_dir = PROJECT_ROOT / "data/history"
if history_dir.exists():
    print(f"\n【1】历史数据目录: {history_dir}")
    subdirs = sorted([d for d in history_dir.iterdir() if d.is_dir()], reverse=True)
    print(f"  发现 {len(subdirs)} 个历史目录")
    
    for subdir in subdirs[:5]:  # 只查看最近5个
        credit_file = subdir / "stage1_output" / "债券持仓明细表_信用债.xlsx"
        if credit_file.exists():
            df = pd.read_excel(credit_file)
            total_yi = df['库存数量(万)_PR'].sum() / 10000
            print(f"\n  {subdir.name}:")
            print(f"    债券持仓明细表_信用债: {len(df)} 行, {total_yi:.2f} 亿")
else:
    print(f"\n[未找到] 历史数据目录: {history_dir}")

# 2. 检查当前数据
current_stage1 = PROJECT_ROOT / "data/current/stage1_output"
if current_stage1.exists():
    print(f"\n【2】当前数据目录: {current_stage1}")
    files = list(current_stage1.glob("*.xlsx"))
    print(f"  发现 {len(files)} 个文件")
    
    credit_file = current_stage1 / "债券持仓明细表_信用债.xlsx"
    if credit_file.exists():
        # 获取文件修改时间
        mtime = os.path.getmtime(credit_file)
        mtime_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
        
        df = pd.read_excel(credit_file)
        total_yi = df['库存数量(万)_PR'].sum() / 10000
        print(f"\n  债券持仓明细表_信用债:")
        print(f"    文件修改时间: {mtime_str}")
        print(f"    行数: {len(df)}")
        print(f"    总持仓(亿): {total_yi:.2f}")
else:
    print(f"\n[未找到] 当前数据目录: {current_stage1}")

# 3. 检查限额目录中可能的备份
limit_dir = PROJECT_ROOT / "限额"
if limit_dir.exists():
    print(f"\n【3】限额目录: {limit_dir}")
    # 查找可能的备份文件
    backups = list(limit_dir.glob("统计报表底稿2_债券SPPI*.xlsx"))
    if len(backups) > 1:
        print(f"  发现 {len(backups)} 个底稿文件（可能有备份）:")
        for backup in sorted(backups):
            print(f"    {backup.name}")

print("\n" + "=" * 80)
