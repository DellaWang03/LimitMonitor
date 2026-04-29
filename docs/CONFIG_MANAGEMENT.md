# 统一配置管理实施说明

## 📅 实施日期
2026-01-29

## 🎯 目标
实现数据源路径的统一配置管理，避免在多个文件中硬编码路径，提高系统的可维护性和灵活性。

> 当前状态（2026-04-29）：本文原始内容记录 v2.1 路径配置改造。最新实现已进一步升级为
> `data_sources.active_profile` + `path_profiles` 多环境配置，并将业务限额主文件迁移到
> `限额配置_当前.xlsx`；旧 `config/limits.yaml` 已退休。DB current/history 读取口径详见
> `docs/db_migration_plan.md`。

---

## ✅ 已完成的修改

### 1. **配置文件更新** (`config/settings.yaml`)

#### 当前核心配置项
```yaml
data_sources:
  active_profile: "local"
  path_profiles:
    local:
      data_dir: "data_source_0123"
    migration:
      data_dir: "/Volumes/sjz-share/共享数据（财务、部门）_紫琪维护"
      file_subpaths:
        限额配置_当前.xlsx: "限额/限额监控"

alerts:
  thresholds_default:
    warning: 0.80
    overlimit: 1.00
```

#### 更新所有路径
生产 / 补跑环境下，主要数据源通过 `path_profiles.migration.file_subpaths` 解析：
- `bond_holdings`: "限额/债券持仓表.xlsx"
- `net_assets`: "限额/净资产.xlsx"
- `instrument_pool`: "限额/金融工具池设置.xlsx"
- `限额配置_当前.xlsx`: "限额/限额监控"
- `风控部债券池.accdb`: "投资条线/债券池列表"
- 等等...

---

### 2. **配置加载器增强** (`src/utils/config_loader.py`)

#### 新增方法：`get_data_dir()`

```python
def get_data_dir(self) -> Path:
    """
    获取数据源根目录的完整路径
    
    Returns:
        数据源目录的完整路径
        
    Examples:
        >>> config = ConfigLoader()
        >>> data_dir = config.get_data_dir()
        >>> print(data_dir)  # /path/to/project/限额
    """
    project_root = self.config_dir.parent
    data_dir_config = self.get("data_sources.data_dir", "sample data")
    data_dir = project_root / data_dir_config
    return data_dir
```

**特性**：
- ✅ 自动读取 `data_sources.data_dir` 配置
- ✅ 默认值为 `"sample data"` 保证向后兼容
- ✅ 返回绝对路径

---

### 3. **主程序文件修改**

#### 修改的文件（3个）

| 文件 | 原路径设置 | 新路径设置 |
|------|-----------|-----------|
| `run_stage0.py` | `data_dir = project_root / "sample data"` | `config = get_config()`<br>`data_dir = config.get_data_dir()` |
| `run_stage1.py` | `data_dir = base_dir / "sample data"` | `config = get_config()`<br>`data_dir = config.get_data_dir()` |
| `run_stage2.py` | `data_dir = project_root / "sample data"` | `config = get_config()`<br>`data_dir = config.get_data_dir()` |

#### 修改前后对比

**修改前**（硬编码）：
```python
data_dir = project_root / "sample data"
```

**修改后**（从配置读取）：
```python
# 从配置文件读取数据源目录
config = get_config()
data_dir = config.get_data_dir()
```

---

### 4. **测试脚本创建** (`tests/test_config_loader.py`)

创建了配置验证脚本，用于：
- ✅ 验证配置加载器是否正常工作
- ✅ 检查数据源目录是否存在
- ✅ 验证所有必需文件是否就绪

---

## 📊 实施效果

### ✅ **优势**

1. **统一管理**
   - 所有路径配置集中在 `config/settings.yaml`
   - 修改路径时只需更改一个配置文件

2. **灵活性**
   - 可以轻松切换数据源目录（开发/测试/生产）
   - 支持相对路径和绝对路径

3. **可维护性**
   - 代码更清晰，路径来源明确
   - 减少硬编码，降低出错风险

4. **向后兼容**
   - 默认值为 `"sample data"` 保证旧配置仍可工作
   - 渐进式迁移，不影响现有功能

### 📈 **指标对比**

| 指标 | 修改前 | 修改后 |
|-----|--------|--------|
| 路径配置位置 | 3个文件硬编码 | 1个配置文件 |
| 修改路径需改动 | 3个文件 | 1个配置项 |
| 配置可见性 | 低（分散在代码中） | 高（集中在配置文件） |
| 维护难度 | 高 | 低 |

---

## 🔄 使用方法

### 切换数据源目录

**方法1：修改配置文件**（推荐）

编辑 `config/settings.yaml`：
```yaml
data_sources:
  data_dir: "新的数据目录名称"
```

**方法2：环境变量**（未实现，可扩展）

未来可以支持通过环境变量覆盖：
```bash
export LIMIT_MONITOR_DATA_DIR="/path/to/data"
```

### 在代码中使用

```python
from src.utils.config_loader import get_config

# 获取数据源目录
config = get_config()
data_dir = config.get_data_dir()

# 构建完整文件路径
file_path = data_dir / "某个数据文件.xlsx"
```

---

## 🧪 验证方法

### 1. 运行测试脚本

```bash
cd /Users/dellawang/Desktop/LimitMonitorAutomation
python3 tests/test_config_loader.py
```

### 2. 运行主程序

```bash
# 运行完整流程
bash run_daily.sh

# 或分别运行各阶段
python3 run_stage0.py
python3 run_stage1.py
python3 run_stage2.py
```

**预期结果**：
- ✅ 日志显示 `数据目录: .../限额 (从配置文件读取)`
- ✅ 程序正常读取 `/限额` 目录下的数据文件
- ✅ 无路径相关错误

---

## 🔍 故障排查

### 问题1：配置文件未生效

**症状**：程序仍然尝试读取 `sample data` 目录

**排查**：
1. 检查 `config/settings.yaml` 中 `data_sources.data_dir` 是否正确
2. 确认主程序文件已更新（包含 `from src.utils.config_loader import get_config`）
3. 清除Python缓存：`find . -name "*.pyc" -delete`

### 问题2：数据文件找不到

**症状**：`FileNotFoundError` 或类似错误

**排查**：
1. 运行 `python3 tests/test_config_loader.py` 检查文件完整性
2. 确认 `/限额` 目录下包含所有必需文件
3. 检查文件名是否完全匹配（包括大小写）

### 问题3：路径编码问题

**症状**：中文路径识别错误

**排查**：
1. 确认系统字符编码为 UTF-8
2. Python 版本 >= 3.6（支持路径中的中文）
3. 使用 `Path` 对象而非字符串拼接

---

## 📝 后续优化建议

### 1. **环境变量支持**
```python
def get_data_dir(self) -> Path:
    # 优先从环境变量读取
    env_data_dir = os.getenv('LIMIT_MONITOR_DATA_DIR')
    if env_data_dir:
        return Path(env_data_dir)
    
    # 否则从配置文件读取
    data_dir_config = self.get("data_sources.data_dir", "sample data")
    return self.config_dir.parent / data_dir_config
```

### 2. **多环境配置**
```yaml
data_sources:
  data_dir:
    development: "sample data"
    testing: "test_data"
    production: "限额"
```

### 3. **配置验证**
在启动时自动验证：
- 数据源目录是否存在
- 必需文件是否齐全
- 文件是否可读

### 4. **配置热加载**
支持运行时重新加载配置，无需重启程序。

---

## 📚 相关文档

- [配置加载器源码](../src/utils/config_loader.py)
- [主配置文件](../config/settings.yaml)
- [测试脚本](../tests/test_config_loader.py)
- [项目README](../README.md)

---

## ✅ 实施检查清单

- [x] 更新 `config/settings.yaml` 添加 `data_dir` 配置
- [x] 更新所有数据源路径从 `sample data` 到 `限额`
- [x] 增强 `ConfigLoader` 添加 `get_data_dir()` 方法
- [x] 修改 `run_stage0.py` 使用配置加载器
- [x] 修改 `run_stage1.py` 使用配置加载器
- [x] 修改 `run_stage2.py` 使用配置加载器
- [x] 创建测试脚本 `tests/test_config_loader.py`
- [x] 创建本文档说明实施过程
- [ ] 运行完整测试验证功能正常
- [x] 更新 README.md 提及配置管理改进

---

## 🎉 总结

通过本次实施，系统实现了：
1. ✅ **数据源路径统一配置管理**
2. ✅ **路径从 `sample data` 切换到 `限额`**
3. ✅ **提高代码可维护性和灵活性**
4. ✅ **保持向后兼容性**

现在只需修改一个配置文件，即可切换整个系统的数据源目录！

---

**实施人员**：AI Assistant  
**审核状态**：待用户验证  
**版本**：v2.1  
**日期**：2026-01-29
