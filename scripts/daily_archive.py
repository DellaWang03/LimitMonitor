"""
每日归档脚本 - 将current/的数据完整备份到history/
用于每天运行完Stage0/1/2后，保存当天的完整数据快照
"""
from pathlib import Path
import shutil
from datetime import datetime
import sys

def archive_current_to_history(target_date: str = None):
    """
    将current/目录的数据归档到history/
    
    Args:
        target_date: 归档日期（格式：YYYY-MM-DD），默认为今天
    """
    project_root = Path(__file__).parent.parent
    
    # 确定归档日期
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')
    
    current_dir = project_root / "data" / "current"
    history_target = project_root / "data" / "history" / target_date
    
    print(f"📦 开始每日归档...")
    print(f"📅 归档日期: {target_date}")
    print(f"=" * 70)
    
    # 验证current目录存在
    if not current_dir.exists():
        print(f"❌ 错误: current目录不存在: {current_dir}")
        return 1
    
    # 检查current目录的完整性
    required_dirs = ['stage0_output', 'stage1_output', 'stage2_output']
    missing_dirs = []
    for dir_name in required_dirs:
        if not (current_dir / dir_name).exists():
            missing_dirs.append(dir_name)
    
    if missing_dirs:
        print(f"⚠️  警告: current目录不完整，缺少: {', '.join(missing_dirs)}")
        print(f"   建议先运行完整的Stage0/1/2处理流程")
        response = input("是否继续归档？(y/n): ")
        if response.lower() != 'y':
            print("取消归档")
            return 1
    
    # 创建history目标目录
    history_target.mkdir(parents=True, exist_ok=True)
    
    # 归档各个stage
    archived_files = {}
    for stage_name in required_dirs:
        source_dir = current_dir / stage_name
        target_dir = history_target / stage_name
        
        if source_dir.exists():
            # 如果目标已存在，先删除
            if target_dir.exists():
                print(f"📁 {stage_name}: 目标已存在，覆盖中...")
                shutil.rmtree(target_dir)
            
            # 复制目录
            shutil.copytree(source_dir, target_dir)
            
            # 统计文件数
            file_count = len(list(target_dir.glob('*.xlsx'))) + len(list(target_dir.glob('*.csv')))
            archived_files[stage_name] = file_count
            
            print(f"✅ {stage_name}: {file_count} 个文件已归档")
        else:
            print(f"⏭️  {stage_name}: 跳过（不存在）")
            archived_files[stage_name] = 0
    
    print(f"\n" + "=" * 70)
    print(f"✅ 归档完成！")
    print(f"\n📊 归档统计:")
    print(f"   Stage0 配置文件: {archived_files.get('stage0_output', 0)} 个")
    print(f"   Stage1 业务文件: {archived_files.get('stage1_output', 0)} 个")
    print(f"   Stage2 业务文件: {archived_files.get('stage2_output', 0)} 个")
    print(f"\n📂 归档位置: data/history/{target_date}/")
    
    # 列出所有历史归档
    history_dir = project_root / "data" / "history"
    if history_dir.exists():
        archive_dates = sorted([d.name for d in history_dir.iterdir() if d.is_dir()], reverse=True)
        print(f"\n📚 历史归档列表 (共{len(archive_dates)}个):")
        for i, date in enumerate(archive_dates[:10], 1):
            print(f"   {i}. {date}")
        if len(archive_dates) > 10:
            print(f"   ... 还有 {len(archive_dates) - 10} 个更早的归档")
    
    return 0


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='每日归档脚本')
    parser.add_argument(
        '--date', 
        type=str, 
        help='归档日期（YYYY-MM-DD格式），默认为今天'
    )
    
    args = parser.parse_args()
    
    try:
        return archive_current_to_history(args.date)
    except Exception as e:
        print(f"\n❌ 归档失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
