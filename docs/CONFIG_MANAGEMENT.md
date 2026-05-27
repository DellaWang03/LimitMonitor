# 配置管理说明

本文说明上线运行时需要关注的数据源路径与环境切换配置。配置文件位于 `config/settings.yaml`。

## 数据源 Profile

系统通过 `data_sources.active_profile` 选择数据源路径：

```yaml
data_sources:
  active_profile: "migration"
  path_profiles:
    local:
      data_dir: "data_source_0123"
    migration:
      data_dir: "/Volumes/sjz-share/PBI"
      data_config_source: "/Volumes/sjz-share/PBI/限额/限额监控"
```

- `local`：本地固定样本调试，默认读取项目根目录下的 `data_source_0123/`。
- `migration`：上线 / 补跑使用，默认读取共享盘路径；Base64 拆出的两张静态口径表也从共享盘读取。

也可以用环境变量临时覆盖：

```bash
export LIMIT_MONITOR_PROFILE=migration
```

## 共享盘路径

上线前重点确认 `path_profiles.migration`：

```yaml
migration:
  data_dir: "/Volumes/sjz-share/PBI"
  data_config_source: "/Volumes/sjz-share/PBI/限额/限额监控"
  file_subpaths:
    金融工具池设置.xlsx: "限额/限额监控"
    限额监控_阶段0_指标设置.xlsx: "限额/限额监控"
    限额配置_当前.xlsx: "限额/限额监控"
    统计报表底稿1_债券.xlsx: "投资条线/2026/统计报表新"
    统计报表底稿2_债券SPPI.xlsx: "投资条线/2026/统计报表新"
    德勤-主体评级列表.xlsx: "投资条线/2026/统计报表新/数据源"
    债券持仓表.xlsx: "投资条线/2026/1.收入核算/核算底稿V3"
    标准日期表.xlsx: "日期表"
    风控部债券池.accdb: "投资条线/债券池列表"
  path_overrides:
    净资产.xlsx: "/Volumes/sjz-share/共享数据（财务、部门）_紫琪维护/部门数据/4.净资产/净资产.xlsx"
```

规则：

- `data_dir` 是共享盘根目录。
- `file_subpaths` 是各数据文件相对 `data_dir` 的目录。
- `path_overrides` 用于少数不在 `data_dir` 树下的文件。
- `data_config_source` 是 `发行人类型调整表.xlsx` 与 `风控部债券池_主体_虚拟添加.xlsx` 所在目录；上线使用共享盘绝对路径。

## DB 连接

DB 连接不写入配置文件，统一由环境变量提供：

```bash
export DB_HOST=<host>
export DB_PORT=<port>
export DB_USER=<user>
export DB_PASSWORD=<password>
export DB_NAME=<database>
```

## 告警阈值

全局展示阈值位于：

```yaml
alerts:
  thresholds_default:
    warning: 0.80
    overlimit: 1.00
```

`scripts/daily_archive.py` 会在归档时把这些阈值写入 `archive_meta`。历史日期展示使用对应归档日写入的阈值。

## 常用命令

```bash
# 使用共享盘 profile 跑每日链路
LIMIT_MONITOR_PROFILE=migration LIMIT_MONITOR_ENV=production bash run_daily.sh

# 启动看板
bash start_web.sh

# 上线前集成验收
bash tests/run_full_integration_test.sh [ARCHIVE_DATE] [REF_DIR]
```

DB current/history 的表结构与归档口径详见 `docs/db_migration_plan.md`。
