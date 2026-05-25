# 项目文件树整理方案

## 目标

在不修改业务代码、不破坏现有运行路径的前提下，降低项目根目录噪音，区分代码、数据、产物、汇报材料和本地环境。

## 当前结论

项目的代码结构本身相对清晰：

- `src/stage0/`、`src/stage1/`、`src/stage2/`：核心处理链路
- `src/visualization/`：看板与展示层逻辑
- `src/utils/`、`src/common/`：配置、归档、通用工具
- `scripts/`、`validation/`、`tests/`：辅助脚本、校验和测试

当前主要问题不是代码目录混乱，而是项目根目录同时放置了本地数据、固定样本、输出产物、汇报交付物、第三方缓存和两个虚拟环境。

## 体积分布

| 路径 | 体积 | 判断 |
| --- | ---: | --- |
| `data_source_0123/` | 3.3G | 固定样本数据源，被配置和脚本引用，不能直接移动 |
| `sample data/` | 1.6G | 历史样本、M 代码、截图、阶段参考，被测试和校验引用，不能直接移动 |
| `outputs/` | 1.6G | 本地产物，已 ignored，可清理或外置 |
| `venv/` | 472M | 本地虚拟环境，建议与 `.venv/` 二选一 |
| `.venv/` | 391M | 本地虚拟环境，建议保留一个标准环境 |
| `vendor/` | 263M | 第三方工具和 wheel 缓存，已 ignored，可外置 |
| `汇报/` | 107M | 汇报交付物，部分已被 Git 跟踪，可考虑长期外置 |
| `data_config_source/` | 75M | migration/profile 相关数据源，被配置引用，不能直接移动 |
| `logs/` | 44M | 本地日志，已 ignored，可清理 |
| `data.zip` | 14M | 已被 Git 跟踪，建议确认是否仍需留在仓库 |
| `data/` | 10M | 运行数据目录，已 ignored，保留本地即可 |

## 路径依赖扫描结果

以下路径被代码、配置、测试或文档明确引用，移动前必须先改配置或保留兼容入口：

- `data_source_0123/`
  - `config/settings.yaml` 的 local profile 使用 `data_dir: "data_source_0123"`
  - `src/utils/limit_config_loader.py` 有 fallback 到 `data_source_0123/限额配置_当前.xlsx`
  - `scripts/generate_limit_config.py` 直接读写该目录
  - README 和多份文档也把它作为固定样本源

- `sample data/`
  - 多个历史校验脚本引用，如 `validation/validate_stage1.py`、`validation/validate_stage2.py`
  - 多个测试引用，如 `tests/test_stage0_basic.py`、`tests/test_date_validator.py`
  - `scripts/export_access_to_csv.py`、`scripts/refresh_wind_code_mapping.py` 等脚本引用
  - `validation/logic_check/` 文档大量引用其中的 M 代码

- `data_config_source/`
  - `config/settings.yaml` migration profile 引用
  - `src/stage0/stage0_processor.py`、`src/utils/date_validator.py` 通过配置读取

- `data_for_testing/`
  - `tests/run_full_integration_test.sh` 默认参考目录
  - `validation/validate_dashboard_display.py` 默认参考目录

因此，第一轮整理不应移动这些目录。

## 建议保留在仓库根目录

这些文件和目录是项目入口、配置或核心工程结构，建议暂时保留：

- `README.md`
- `app.py`
- `config/`
- `src/`
- `scripts/`
- `tests/`
- `validation/`
- `requirements.txt`
- `requirements_visualization.txt`
- `run_daily.sh`
- `run_daily.bat`
- `run_stage0.py`
- `run_stage1.py`
- `run_stage2.py`
- `start_web.sh`
- `start_web.bat`

以下运行脚本是否仍需保留，可后续确认：

- `run_daily_development.sh`
- `run_daily_development.bat`
- `run_daily_production.sh`
- `run_daily_production.bat`

## 第一阶段：安全清理本地产物

这些路径已被忽略或属于本地缓存，理论上可以清理，不影响 Git 版本：

- `.DS_Store`
- `__pycache__/`
- `.pytest_cache/`
- `logs/`
- `temp/`
- `outputs/`
- `vendor/`

建议执行前先确认是否有需要保留的交付物，尤其是 `outputs/` 和 `vendor/`。

推荐策略：

1. `logs/`、`temp/`、`__pycache__/`、`.pytest_cache/` 可直接清理。
2. `outputs/` 先整体搬到项目外归档目录，再观察一周。
3. `vendor/` 如果只是临时下载缓存，也建议搬到项目外；如果还有复用价值，记录来源和重建方式。

## 第二阶段：统一虚拟环境

当前同时存在：

- `.venv/`
- `venv/`

建议统一为 `.venv/`。删除前先确认当前常用命令实际使用哪个解释器。

检查命令：

```bash
which python
python --version
./.venv/bin/python --version
./venv/bin/python --version
```

建议保留 `.venv/`，移除 `venv/`，但前提是 `.venv/` 能安装并运行项目依赖。

### 2026-05-25 复核结论

两个环境均为 Python 3.14.3，但依赖并不等价：

- `.venv/`：有 `SQLAlchemy`、`PyMySQL`、`streamlit` 等，但缺少 `pyodbc`、`xlwings`、`pytest`。
- `venv/`：有 `pyodbc`、`xlwings`、`plotly`、`lxml` 等，更接近 `requirements.txt` 中 Excel/Access 相关依赖，但同样缺少 `pytest`。

因此，暂不建议直接删除任一环境。更稳妥的第二阶段动作是：

1. 先选定未来标准环境名，建议为 `.venv/`。
2. 用 `requirements.txt` 和 `requirements_visualization.txt` 重建或补齐 `.venv/`。
3. 确认核心命令可运行后，再删除 `venv/`。

当前不要把 `venv/` 作为纯缓存删除，因为它包含 `.venv/` 中没有的 Excel/Access 相关包。

## 第三阶段：处理数据目录

这些目录不建议直接移动：

- `data_source_0123/`
- `sample data/`
- `data_config_source/`
- `data_for_testing/`
- `data_for_testing_0407/`
- `data_for_testing_0410/`

推荐做法是先建立约定：

```text
local_data/
  active/
  fixtures/
  archived/
  reports/
```

然后逐步迁移，并为旧路径保留兼容方式。由于当前代码和测试直接引用旧路径，迁移前需要先完成路径配置化改造或保留旧目录软链接。

## 第四阶段：处理汇报和图表材料

`汇报/` 和 `diagrams/` 混合了交付物、截图、PPT、PDF 和项目说明图。

建议：

- `diagrams/` 中与架构、业务流程直接相关的图继续保留。
- `汇报/` 中按周交付的 PPT/PDF 长期看更适合移到项目外归档。
- 如果必须保留在仓库，建议改为只保留最终 PDF 或关键源文件，不同时保留多版 PPT/PDF/截图。

注意：`汇报/` 目前有部分文件被 Git 跟踪，移动或删除前需要确认团队是否依赖 Git 历史中的交付物。

## 第五阶段：根目录脚本归位

根目录目前有一些一次性或诊断脚本：

- `check_missing_bonds.py`
- `diagnose_missing_bonds.py`
- `test_tool_pool_fix.py`

建议后续统一归入：

- `scripts/diagnostics/`
- `scripts/manual/`
- `tests/`，如果它们是自动测试

这一步会改变文件路径，可能影响人工使用习惯，应单独提交并更新 README。

## 推荐执行顺序

1. 只清理缓存：`.DS_Store`、`__pycache__/`、`.pytest_cache/`、`logs/`、`temp/`
2. 统一虚拟环境：确认后保留 `.venv/`，移除 `venv/`
3. 外置大产物：把 `outputs/`、`vendor/` 搬到项目外归档
4. 盘点交付物：决定 `汇报/` 是否继续随 Git 管理
5. 数据目录配置化：再考虑移动 `data_source_0123/`、`sample data/`、`data_config_source/`
6. 脚本归位：把根目录的一次性脚本迁到 `scripts/diagnostics/` 或 `scripts/manual/`

## 本轮不建议做的事

- 不直接移动 `data_source_0123/`
- 不直接移动 `sample data/`
- 不直接移动 `data_config_source/`
- 不删除 `汇报/` 中已被 Git 跟踪的文件
- 不重构 `src/` 目录
- 不改业务代码路径

## 验收标准

整理执行后应满足：

- `git status --short --branch` 无意外代码改动
- `README.md` 中的运行命令仍可理解
- `config/settings.yaml` 的 local profile 仍能找到样本数据
- `tests/run_full_integration_test.sh` 仍能找到默认 `data_for_testing/`
- `run_stage0.py`、`run_stage1.py`、`run_stage2.py` 的入口路径不被破坏
