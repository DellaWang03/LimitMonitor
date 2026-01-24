"""
数据迁移脚本 - 将现有数据迁移到新的history结构
"""
from pathlib import Path
import shutil
from datetime import datetime

def migrate_existing_data():
    """将现有的stage1_output和stage2_output迁移到新结构"""
    
    project_root = Path(__file__).parent.parent
    
    # 旧的数据目录
    old_stage1 = project_root / "data" / "stage1_output"
    old_stage2 = project_root / "data" / "stage2_output"
    
    # 获取今天的日期
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 新的目录结构
    current_dir = project_root / "data" / "current"
    history_today = project_root / "data" / "history" / today
    
    print(f"开始数据迁移...")
    print(f"目标日期: {today}")
    print(f"=" * 50)
    
    # 1. 创建新目录
    current_dir.mkdir(parents=True, exist_ok=True)
    history_today.mkdir(parents=True, exist_ok=True)
    print(f"✅ 创建目录结构")
    
    # 2. 复制到current（用于最新数据）
    if old_stage1.exists():
        print(f"📁 复制 stage1_output 到 current/...")
        shutil.copytree(old_stage1, current_dir / "stage1_output", dirs_exist_ok=True)
        print(f"   ✅ 完成")
    else:
        print(f"⚠️  未找到 {old_stage1}")
    
    if old_stage2.exists():
        print(f"📁 复制 stage2_output 到 current/...")
        shutil.copytree(old_stage2, current_dir / "stage2_output", dirs_exist_ok=True)
        print(f"   ✅ 完成")
    else:
        print(f"⚠️  未找到 {old_stage2}")
    
    # 3. 复制到history（作为今天的历史备份）
    if old_stage1.exists():
        print(f"📁 复制 stage1_output 到 history/{today}/...")
        shutil.copytree(old_stage1, history_today / "stage1_output", dirs_exist_ok=True)
        print(f"   ✅ 完成")
    
    if old_stage2.exists():
        print(f"📁 复制 stage2_output 到 history/{today}/...")
        shutil.copytree(old_stage2, history_today / "stage2_output", dirs_exist_ok=True)
        print(f"   ✅ 完成")
    
    print(f"\n" + "=" * 50)
    print(f"✅ 迁移完成！")
    print(f"\n新的目录结构:")
    print(f"  📂 data/current/")
    print(f"     ├── stage1_output/  (最新数据)")
    print(f"     └── stage2_output/  (最新数据)")
    print(f"  📂 data/history/")
    print(f"     └── {today}/")
    print(f"         ├── stage1_output/  (历史备份)")
    print(f"         └── stage2_output/  (历史备份)")
    print(f"\n⚠️  注意事项:")
    print(f"   • 原来的 data/stage1_output 和 data/stage2_output 仍然保留")
    print(f"   • 验证系统正常运行后，可以手动删除旧目录")
    print(f"   • 从现在开始，每日脚本会自动备份到 history/ 目录")

if __name__ == "__main__":
    migrate_existing_data()
