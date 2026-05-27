"""
文件元数据校验 - 对比参考文件和输出文件的基本信息
"""
import os
from pathlib import Path
from datetime import datetime
import subprocess


def get_file_info(filepath):
    """获取文件基本信息"""
    if not filepath.exists():
        return None
    
    stat = filepath.stat()
    return {
        "存在": True,
        "大小(KB)": round(stat.st_size / 1024, 2),
        "修改时间": datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
    }


def count_excel_rows(filepath):
    """统计Excel文件行数（使用命令行工具）"""
    try:
        # 使用unzip和grep来快速统计（Excel是zip格式）
        result = subprocess.run(
            f'unzip -p "{filepath}" xl/worksheets/sheet1.xml 2>/dev/null | grep -o "<row" | wc -l',
            shell=True,
            capture_output=True,
            text=True
        )
        count = int(result.stdout.strip())
        return count - 1 if count > 0 else 0  # 减去表头
    except:
        return "N/A"


def validate_stage1_files():
    """校验阶段1文件"""
    print("\n" + "=" * 80)
    print("📋 阶段1文件校验")
    print("=" * 80)
    
    project_root = Path(__file__).parent.parent
    
    # 定义核心文件列表
    core_files = [
        "限额明细_单一债券.xlsx",
        "限额明细_单一主体.xlsx",
        "限额明细_单一实控人_取最高额度.xlsx",
        "限额明细_单一担保人.xlsx",
        "债券持仓明细表_信用债1_1.xlsx",
        "债券持仓明细表_信用债1_2.xlsx"
    ]
    
    output_dir = project_root / "data" / "stage1_output"
    
    results = []
    
    for idx, filename in enumerate(core_files, 1):
        filepath = output_dir / filename
        info = get_file_info(filepath)
        
        if info:
            print(f"\n[{idx}/{len(core_files)}] ✅ {filename}")
            print(f"     大小: {info['大小(KB)']} KB")
            print(f"     修改时间: {info['修改时间']}")
            results.append((filename, True, info['大小(KB)']))
        else:
            print(f"\n[{idx}/{len(core_files)}] ❌ {filename} - 文件不存在")
            results.append((filename, False, 0))
    
    return results


def validate_stage2_files():
    """校验阶段2文件"""
    print("\n\n" + "=" * 80)
    print("📋 阶段2文件校验")
    print("=" * 80)
    
    project_root = Path(__file__).parent.parent
    
    # 定义核心文件列表
    core_files = [
        "限额明细_地域集中度限额(含城投).xlsx",
        "限额明细_高风险行业.xlsx",
        "限额明细_高风险省份.xlsx",
        "限额明细_债券持仓明细表_信用债2.xlsx",
        "限额明细_高收益.xlsx",
        "限额明细_高收益_投资本金规模.xlsx",
        "地域集中度限额(含城投).xlsx",
        "单一地域总持仓.xlsx",
        "单一地域城投总持仓.xlsx",
        "高风险行业.xlsx",
        "高风险省份.xlsx"
    ]
    
    output_dir = project_root / "data" / "stage2_output"
    
    results = []
    
    for idx, filename in enumerate(core_files, 1):
        filepath = output_dir / filename
        info = get_file_info(filepath)
        
        if info:
            print(f"\n[{idx}/{len(core_files)}] ✅ {filename}")
            print(f"     大小: {info['大小(KB)']} KB")
            print(f"     修改时间: {info['修改时间']}")
            results.append((filename, True, info['大小(KB)']))
        else:
            print(f"\n[{idx}/{len(core_files)}] ❌ {filename} - 文件不存在")
            results.append((filename, False, 0))
    
    return results


def main():
    """主函数"""
    print("\n" + "🔍" * 40)
    print("数据文件元数据校验")
    print(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("🔍" * 40)
    
    # 阶段1文件校验
    stage1_results = validate_stage1_files()
    
    # 阶段2文件校验
    stage2_results = validate_stage2_files()
    
    # 总结
    print("\n\n" + "=" * 80)
    print("📊 校验总结")
    print("=" * 80)
    
    stage1_success = sum(1 for _, exists, _ in stage1_results if exists)
    stage2_success = sum(1 for _, exists, _ in stage2_results if exists)
    
    print(f"\n✅ 阶段1: {stage1_success}/{len(stage1_results)} 个文件存在")
    print(f"✅ 阶段2: {stage2_success}/{len(stage2_results)} 个文件存在")
    
    total_files = len(stage1_results) + len(stage2_results)
    total_success = stage1_success + stage2_success
    
    print(f"\n{'='*80}")
    print(f"✅ 总计: {total_success}/{total_files} 个文件存在 ({total_success/total_files*100:.1f}%)")
    print(f"{'='*80}")
    
    if total_success == total_files:
        print(f"\n🎉 所有核心数据文件均已生成！")
    else:
        missing = total_files - total_success
        print(f"\n⚠️ 缺失 {missing} 个文件，请检查数据处理流程。")
    
    # 计算总文件大小
    total_size = sum(size for _, exists, size in stage1_results + stage2_results if exists)
    print(f"\n📦 数据文件总大小: {total_size:,.2f} KB ({total_size/1024:.2f} MB)")


if __name__ == "__main__":
    main()
