"""
配置加载器
用于加载和管理 YAML 配置文件
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any


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
