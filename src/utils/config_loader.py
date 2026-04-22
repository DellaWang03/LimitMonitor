"""
配置加载器
用于加载和管理 YAML 配置文件
支持路径双 profile 一键切换：local（当前环境）/ migration（另一台电脑）
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional

# migration 时从 data_config_source 读取的 3 个文件
CONFIG_SOURCE_FILES = {
    "发行人类型调整表.xlsx",
    "风控部债券池_主体_虚拟添加.xlsx",
}


class ConfigLoader:
    """配置加载器"""
    
    def __init__(self, config_dir: str = None):
        """
        初始化配置加载器
        
        Args:
            config_dir: 配置文件目录，默认为项目根目录的 config 文件夹
        """
        if config_dir is None:
            # 自动查找项目根目录
            current_file = Path(__file__)
            project_root = current_file.parent.parent.parent
            self.config_dir = project_root / "config"
        else:
            self.config_dir = Path(config_dir)
            
        self._settings = None
        self._limits = None
        
    def load_settings(self) -> Dict[str, Any]:
        """加载主配置文件"""
        if self._settings is None:
            settings_file = self.config_dir / "settings.yaml"
            self._settings = self._load_yaml(settings_file)
        return self._settings
    
    def load_limits(self) -> Dict[str, Any]:
        """加载限额配置文件"""
        if self._limits is None:
            limits_file = self.config_dir / "limits.yaml"
            self._limits = self._load_yaml(limits_file)
        return self._limits
    
    def _load_yaml(self, file_path: Path) -> Dict[str, Any]:
        """
        加载 YAML 文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            配置字典
        """
        if not file_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {file_path}")
            
        with open(file_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            
        return config or {}
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        获取配置值（支持点号分隔的路径）
        
        Args:
            key_path: 配置路径，如 "data_sources.excel_files.bond_pool"
            default: 默认值
            
        Returns:
            配置值
            
        Examples:
            >>> config = ConfigLoader()
            >>> bond_pool = config.get("data_sources.excel_files.bond_pool")
        """
        settings = self.load_settings()
        
        keys = key_path.split('.')
        value = settings
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
                
        return value
    
    def get_limit(self, key_path: str, default: Any = None) -> Any:
        """
        获取限额配置值
        
        Args:
            key_path: 配置路径，如 "single_bond.scale_limit"
            default: 默认值
            
        Returns:
            配置值
        """
        limits = self.load_limits()
        
        keys = key_path.split('.')
        value = limits
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
                
        return value
    
    def get_active_profile(self) -> str:
        """
        当前使用的路径 profile：local | migration
        可通过环境变量 LIMIT_MONITOR_PROFILE 覆盖配置。
        """
        env_profile = os.environ.get("LIMIT_MONITOR_PROFILE", "").strip().lower()
        if env_profile in ("local", "migration"):
            return env_profile
        return self.get("data_sources.active_profile", "local") or "local"

    def _get_migration_profile(self) -> Optional[Dict[str, Any]]:
        """获取 migration profile 配置，未配置或非 migration 时返回 None。"""
        if self.get_active_profile() != "migration":
            return None
        profiles = self.get("data_sources.path_profiles") or {}
        return profiles.get("migration")

    def _get_local_data_dir(self) -> Path:
        """
        local profile 下的数据源根目录。
        优先使用 path_profiles.local.data_dir（如 data_source_0123），
        否则回退到 data_sources.data_dir（兼容旧配置）。
        """
        project_root = self.config_dir.parent
        profiles = self.get("data_sources.path_profiles") or {}
        local = profiles.get("local") or {}
        if isinstance(local, dict) and local.get("data_dir"):
            p = Path(local["data_dir"])
            return p if p.is_absolute() else project_root / p
        data_dir_config = self.get("data_sources.data_dir", "sample data")
        return project_root / data_dir_config

    def get_data_dir(self) -> Path:
        """
        获取数据源根目录的完整路径（按当前 profile）。
        local：path_profiles.local.data_dir（若无则 data_sources.data_dir）；
        migration：path_profiles.migration.data_dir。
        """
        project_root = self.config_dir.parent
        profile = self.get_active_profile()
        if profile == "local":
            return self._get_local_data_dir()
        if profile == "migration":
            mig = self._get_migration_profile()
            if mig and mig.get("data_dir"):
                p = Path(mig["data_dir"])
                return p if p.is_absolute() else project_root / p
        data_dir_config = self.get("data_sources.data_dir", "sample data")
        return project_root / data_dir_config

    def get_data_config_source_dir(self) -> Optional[Path]:
        """
        migration 时返回 3 个配置表所在目录；local 时返回 None（调用方用 data_dir）。
        """
        mig = self._get_migration_profile()
        if not mig or not mig.get("data_config_source"):
            return None
        p = Path(mig["data_config_source"])
        project_root = self.config_dir.parent
        return p if p.is_absolute() else project_root / p

    def get_data_file_path(self, file_name: str) -> Path:
        """
        按当前 profile 返回数据源文件的完整路径。
        local：path_profiles.local.data_dir / file_name；migration：按 file_subpaths / path_overrides / data_config_source。
        """
        project_root = self.config_dir.parent
        profile = self.get_active_profile()
        if profile == "local":
            return self._get_local_data_dir() / file_name
        mig = self._get_migration_profile()
        if not mig:
            data_dir = self.get("data_sources.data_dir", "sample data")
            return project_root / data_dir / file_name
        if file_name in CONFIG_SOURCE_FILES:
            cfg_dir = mig.get("data_config_source")
            if cfg_dir:
                p = Path(cfg_dir)
                base = p if p.is_absolute() else project_root / p
                return base / file_name
        overrides = mig.get("path_overrides") or {}
        if file_name in overrides:
            p = Path(overrides[file_name])
            return p if p.is_absolute() else project_root / p
        data_dir = Path(mig.get("data_dir", "."))
        if not data_dir.is_absolute():
            data_dir = project_root / data_dir
        subpaths = mig.get("file_subpaths") or {}
        sub = subpaths.get(file_name)
        if sub:
            return data_dir / sub / file_name
        return data_dir / file_name

    def get_data_file_path_without_override(self, file_name: str) -> Path:
        """
        返回数据源文件路径但不应用 path_overrides（用于从 SMB 等原始位置读取，如 mdb-export 源）。
        仅用于风控部债券池.accdb 的自动导出场景。
        """
        project_root = self.config_dir.parent
        profile = self.get_active_profile()
        if profile == "local":
            return self._get_local_data_dir() / file_name
        mig = self._get_migration_profile()
        if not mig:
            data_dir = self.get("data_sources.data_dir", "sample data")
            return project_root / data_dir / file_name
        data_dir = Path(mig.get("data_dir", "."))
        if not data_dir.is_absolute():
            data_dir = project_root / data_dir
        subpaths = mig.get("file_subpaths") or {}
        sub = subpaths.get(file_name)
        if sub:
            return data_dir / sub / file_name
        return data_dir / file_name

    def get_data_source_path(self, source_key: str) -> Path:
        """
        获取数据源文件的完整路径
        
        Args:
            source_key: 数据源键名，如 "bond_pool", "stage_1" 等
            
        Returns:
            文件的完整路径
        """
        # 获取项目根目录
        project_root = self.config_dir.parent
        
        # 获取相对路径
        rel_path = self.get(f"data_sources.excel_files.{source_key}")
        
        if rel_path is None:
            raise ValueError(f"未找到数据源配置: {source_key}")
            
        # 转换为绝对路径
        full_path = project_root / rel_path
        
        if not full_path.exists():
            raise FileNotFoundError(f"数据文件不存在: {full_path}")
            
        return full_path


# 全局配置实例
_global_config = None


def get_config() -> ConfigLoader:
    """获取全局配置实例（单例模式）"""
    global _global_config
    if _global_config is None:
        _global_config = ConfigLoader()
    return _global_config


if __name__ == "__main__":
    # 测试配置加载
    config = ConfigLoader()
    
    print("=" * 60)
    print("配置加载测试")
    print("=" * 60)
    
    # 测试加载主配置
    settings = config.load_settings()
    print(f"\n项目名称: {settings['project']['name']}")
    print(f"版本: {settings['project']['version']}")
    
    # 测试加载限额配置
    limits = config.load_limits()
    print(f"\n单一担保人限额: {limits['single_guarantor']['scale_limit']} 万元")
    print(f"地域集中度限额: {limits['regional_concentration']['total_limit_ratio']*100}%")
    
    # 测试路径获取
    try:
        bond_pool_path = config.get_data_source_path('bond_pool')
        print(f"\n债券池文件路径: {bond_pool_path}")
        print(f"文件是否存在: {bond_pool_path.exists()}")
    except Exception as e:
        print(f"\n路径获取测试: {e}")
    
    print("\n" + "=" * 60)
