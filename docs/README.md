# 文档目录

## 📚 系统文档

本目录包含限额监控系统的详细技术文档和参考资料。

---

## 📄 文档列表

### 1. HISTORY_DATA_IMPLEMENTATION.md
**历史数据功能实现说明**

详细描述历史数据管理机制的实现：
- 数据归档策略
- 目录结构设计
- DataLoader实现
- 日期选择器集成

### 2. 省份标准化方案说明.md
**省份名称标准化方案**

说明省份数据清洗和标准化逻辑：
- 省份名称映射规则
- 特殊情况处理
- ProvinceNormalizer实现

### 3. 附件1：固定收益事业部债券投资限额情况表.pdf
**业务需求文档**

原始的限额监控业务需求和规则说明。

---

## 🔗 相关资源

### 主文档
- **项目README**: `../README.md` - 项目总览、快速开始、使用说明
- **Cursor规则**: `../.cursorrules` - AI交互规范

### 配置文件
- **系统设置**: `../config/settings.yaml` - 数据源 profile、路径映射、告警阈值默认值
- **限额配置**: `限额配置_当前.xlsx` - 当前限额配置主文件，路径由 `config/settings.yaml` 的 `path_profiles` 解析
- **DB迁移说明**: `db_migration_plan.md` - current/history 快照切 DB 后的归档、读取和校验口径

> `../config/limits.yaml` 已退休；运行时限额来自 `限额配置_当前.xlsx`、Stage 输出表和 `archive_meta`。

### 代码文档
- **数据加载器**: `../src/visualization/data_loader.py` - 包含详细注释
- **阶段处理器**: `../src/stage*/` - 各阶段处理逻辑

---

## 📝 文档维护

- 文档应与代码实现保持同步
- 重大功能变更需更新相关文档
- 不创建冗余或过时的文档

---

**最后更新**: 2026-04-29
