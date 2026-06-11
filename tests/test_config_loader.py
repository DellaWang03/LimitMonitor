from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.config_loader import ConfigLoader


def test_config_loader_uses_windows_profile_from_env(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "settings.yaml").write_text(
        """
data_sources:
  active_profile: local
  data_dir: fallback
  path_profiles:
    local:
      data_dir: local_data
    windows:
      data_dir: '\\\\192.168.136.150\\sjz-share\\PBI'
      data_config_source: '\\\\192.168.136.150\\sjz-share\\PBI\\限额\\限额监控'
      file_subpaths:
        统计报表底稿1_债券.xlsx: '投资条线\\2026\\统计报表新\\收益互换临时文件'
      path_overrides:
        净资产.xlsx: '\\\\192.168.136.150\\sjz-share\\共享数据\\净资产.xlsx'
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("LIMIT_MONITOR_PROFILE", "windows")

    config = ConfigLoader(config_dir=str(config_dir))

    assert config.get_active_profile() == "windows"
    assert str(config.get_data_dir()) == r"\\192.168.136.150\sjz-share\PBI"
    assert (
        str(config.get_data_config_source_dir())
        == r"\\192.168.136.150\sjz-share\PBI\限额\限额监控"
    )
    assert (
        str(config.get_data_file_path("统计报表底稿1_债券.xlsx"))
        == r"\\192.168.136.150\sjz-share\PBI/投资条线\2026\统计报表新\收益互换临时文件/统计报表底稿1_债券.xlsx"
    )
    assert (
        str(config.get_data_file_path("净资产.xlsx"))
        == r"\\192.168.136.150\sjz-share\共享数据\净资产.xlsx"
    )
