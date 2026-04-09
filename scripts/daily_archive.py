"""
每日归档脚本 - 将current/的数据完整备份到history/
用于每天运行完Stage0/1/2后，保存当天的完整数据快照
归档时写入 data_date.txt 记录输出表中的实际数据日期，供看板下拉展示「归档日 (数据日期: xxx)」
"""
from pathlib import Path
import shutil
from datetime import datetime
import json
import sys

try:
    import pandas as pd
except ImportError:
    pd = None


def _ensure_project_import_path(project_root: Path):
    """确保脚本模式下可以导入项目内模块。"""
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)


def _write_high_yield_limit_snapshot(project_root: Path, history_target: Path):
    """写入高收益年度限额历史快照，避免历史页面回看时使用当前配置源。"""
    snapshot_file = history_target / "high_yield_limit_snapshot.json"
    payload = {
        "snapshot_type": "high_yield_limit",
        "captured_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "annual_limit_wan": 100000,
        "source": "fallback",
    }

    try:
        _ensure_project_import_path(project_root)
        from src.utils.config_loader import ConfigLoader

        config = ConfigLoader(str(project_root / "config"))
        source_file = config.get_data_file_path("限额监控_阶段0_指标设置.xlsx")
        payload["source_file"] = str(source_file)

        if pd is None:
            payload["source"] = "fallback_no_pandas"
            payload["error"] = "pandas_not_available"
        else:
            df = pd.read_excel(str(source_file), sheet_name="高收益限额")
            row = df[df["指标"].astype(str).str.strip() == "年度高收益债券投资本金规模"]
            if row.empty:
                payload["source"] = "fallback_missing_row"
                payload["error"] = "annual_limit_row_not_found"
            else:
                payload["annual_limit_wan"] = int(row.iloc[0]["限额(万)"])
                payload["source"] = "snapshot"
    except Exception as e:
        payload["source"] = "fallback_exception"
        payload["error"] = str(e)

    snapshot_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"📋 高收益限额快照已写入: {snapshot_file.name}")


def _write_alert_thresholds_snapshot(project_root: Path, history_target: Path):
    """写入展示用告警阈值历史快照，保证历史页面颜色和文案口径可回放。"""
    snapshot_file = history_target / "alert_thresholds_snapshot.json"
    payload = {
        "snapshot_type": "alert_thresholds",
        "captured_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "warning": 0.80,
        "overlimit": 1.00,
        "source": "fallback",
    }

    try:
        _ensure_project_import_path(project_root)
        from src.utils.config_loader import ConfigLoader

        config = ConfigLoader(str(project_root / "config"))
        payload["warning"] = float(config.get("alerts.thresholds.warning", 0.80))
        payload["overlimit"] = float(config.get("alerts.thresholds.overlimit", 1.00))
        payload["source"] = "snapshot"
    except Exception as e:
        payload["source"] = "fallback_exception"
        payload["error"] = str(e)

    snapshot_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"📋 告警阈值快照已写入: {snapshot_file.name}")

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
    
    # 写入数据日期 meta（从 Stage1 输出表读取「日期」列最大值，供看板展示）
    data_date_str = None
    if pd is not None and (history_target / "stage1_output").exists():
        ref_file = history_target / "stage1_output" / "限额明细_债券持仓明细表_信用债1_2.xlsx"
        if ref_file.exists():
            try:
                df = pd.read_excel(ref_file)
                if "日期" in df.columns:
                    df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
                    max_date = df["日期"].max()
                    if pd.notna(max_date):
                        data_date_str = max_date.strftime("%Y-%m-%d")
                        (history_target / "data_date.txt").write_text(
                            data_date_str, encoding="utf-8"
                        )
                        print(f"📋 数据日期已写入: {data_date_str}")
            except Exception as e:
                print(f"⚠️  读取数据日期失败（不影响归档）: {e}")
    if not data_date_str:
        print(f"📋 未写入 data_date.txt（无 pandas 或表中无日期列）")

    # 写入历史展示快照，避免历史页面回看时重新读取当前配置
    _write_high_yield_limit_snapshot(project_root, history_target)
    _write_alert_thresholds_snapshot(project_root, history_target)
    
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
