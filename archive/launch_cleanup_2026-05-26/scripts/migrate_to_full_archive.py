"""
完整归档迁移脚本 - 将Stage0/1/2迁移到新的完整归档结构
包含配置文件的完整可追溯性
"""
from pathlib import Path
import shutil
from datetime import datetime

def migrate_to_full_archive():
    """将现有的stage0/1/2输出迁移到完整归档结构"""
    
    project_root = Path(__file__).parent.parent
    
    # 旧的数据目录
    old_stage0 = project_root / "data" / "stage0_output"
    old_stage1 = project_root / "data" / "stage1_output"
    old_stage2 = project_root / "data" / "stage2_output"
    
    # 获取今天的日期
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 新的目录结构
    current_dir = project_root / "data" / "current"
    history_today = project_root / "data" / "history" / today
    
    print(f"🚀 开始完整归档迁移...")
    print(f"📅 目标日期: {today}")
    print(f"=" * 70)
    
    # 1. 创建新目录
    current_dir.mkdir(parents=True, exist_ok=True)
    history_today.mkdir(parents=True, exist_ok=True)
    print(f"✅ 创建目录结构")
    
    # 统计信息
    migrated_files = {'stage0': 0, 'stage1': 0, 'stage2': 0}
    
    # 2. 迁移Stage0（配置文件）
    if old_stage0.exists():
        print(f"\n📁 迁移 Stage0 配置文件...")
        
        # 复制到current
        current_stage0 = current_dir / "stage0_output"
        shutil.copytree(old_stage0, current_stage0, dirs_exist_ok=True)
        migrated_files['stage0'] = len(list(current_stage0.glob('*.xlsx')))
        print(f"   ✅ → data/current/stage0_output/ ({migrated_files['stage0']}个文件)")
        
        # 复制到history
        history_stage0 = history_today / "stage0_output"
        shutil.copytree(old_stage0, history_stage0, dirs_exist_ok=True)
        print(f"   ✅ → data/history/{today}/stage0_output/ ({migrated_files['stage0']}个文件)")
    else:
        print(f"⚠️  未找到 {old_stage0}")
    
    # 3. 迁移Stage1
    if old_stage1.exists():
        print(f"\n📁 迁移 Stage1 业务数据...")
        
        # 复制到current（如果已存在则覆盖）
        current_stage1 = current_dir / "stage1_output"
        if current_stage1.exists():
            shutil.rmtree(current_stage1)
        shutil.copytree(old_stage1, current_stage1)
        migrated_files['stage1'] = len(list(current_stage1.glob('*.xlsx')))
        print(f"   ✅ → data/current/stage1_output/ ({migrated_files['stage1']}个文件)")
        
        # 复制到history（如果已存在则覆盖）
        history_stage1 = history_today / "stage1_output"
        if history_stage1.exists():
            shutil.rmtree(history_stage1)
        shutil.copytree(old_stage1, history_stage1)
        print(f"   ✅ → data/history/{today}/stage1_output/ ({migrated_files['stage1']}个文件)")
    else:
        print(f"⚠️  未找到 {old_stage1}")
    
    # 4. 迁移Stage2
    if old_stage2.exists():
        print(f"\n📁 迁移 Stage2 业务数据...")
        
        # 复制到current
        current_stage2 = current_dir / "stage2_output"
        if current_stage2.exists():
            shutil.rmtree(current_stage2)
        shutil.copytree(old_stage2, current_stage2)
        migrated_files['stage2'] = len(list(current_stage2.glob('*.xlsx')))
        print(f"   ✅ → data/current/stage2_output/ ({migrated_files['stage2']}个文件)")
        
        # 复制到history
        history_stage2 = history_today / "stage2_output"
        if history_stage2.exists():
            shutil.rmtree(history_stage2)
        shutil.copytree(old_stage2, history_stage2)
        print(f"   ✅ → data/history/{today}/stage2_output/ ({migrated_files['stage2']}个文件)")
    else:
        print(f"⚠️  未找到 {old_stage2}")
    
    print(f"\n" + "=" * 70)
    print(f"✅ 迁移完成！")
    print(f"\n📊 迁移统计:")
    print(f"   Stage0 配置文件: {migrated_files['stage0']} 个")
    print(f"   Stage1 业务文件: {migrated_files['stage1']} 个")
    print(f"   Stage2 业务文件: {migrated_files['stage2']} 个")
    print(f"\n📂 新的完整归档结构:")
    print(f"   data/")
    print(f"   ├── current/                    (最新数据)")
    print(f"   │   ├── stage0_output/          ✨ 当前配置文件")
    print(f"   │   ├── stage1_output/          最新Stage1结果")
    print(f"   │   └── stage2_output/          最新Stage2结果")
    print(f"   ├── history/                    (历史完整快照)")
    print(f"   │   └── {today}/")
    print(f"   │       ├── stage0_output/      ✨ 该日期的配置文件")
    print(f"   │       ├── stage1_output/      该日期的Stage1结果")
    print(f"   │       └── stage2_output/      该日期的Stage2结果")
    print(f"   └── snapshots/                  (PowerBI截图)")
    print(f"\n⚠️  下一步操作:")
    print(f"   1. 验证系统运行正常（运行validation脚本）")
    print(f"   2. 更新run_stage脚本使用current/路径")
    print(f"   3. 确认无误后，删除旧的根目录输出文件夹")
    print(f"      • data/stage0_output/")
    print(f"      • data/stage1_output/")
    print(f"      • data/stage2_output/")

if __name__ == "__main__":
    migrate_to_full_archive()
