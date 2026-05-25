# 汇报与图表材料整理建议

## 目标

为第四阶段整理提供清单：先判断哪些保留、哪些外置归档、哪些可删除。本文只给建议，不直接移动或删除文件。

## 总体判断

`汇报/` 更像交付物归档，不是运行代码依赖；`diagrams/` 更像项目说明资产，其中部分图和 Markdown 对 README、交接和架构理解有长期价值。

建议原则：

1. 业务流程、架构、核心逻辑说明图保留。
2. `汇报/` 不需要留太多，当前口径是保留每周代表性 PDF，关键 Markdown 若已不存在则不补回。
3. 同一主题同时存在 PPT、PDF、多版本时，仓库内只保留最终版或最有复用价值的一份。
4. 已被 Git 跟踪的文件不要直接本地删除，应单独提交一次“文档/交付物归档”变更。
5. 截图、制作过程素材、提示词草稿、重复版本优先外置归档或删除。

## 建议保留

### `diagrams/`

这些文件建议保留在仓库中，因为它们是项目理解和交接材料：

- `diagrams/业务流程分阶段说明.md`
- `diagrams/业务流程分阶段说明.png`
- `diagrams/分层架构各层说明.md`
- `diagrams/分层架构各层说明.png`
- `diagrams/可视化看板页面说明.md`
- `diagrams/技术实现架构.md`
- `diagrams/投后限额监控Dashboard业务全景.md`
- `diagrams/投后限额监控Dashboard业务全景.png`
- `diagrams/投后限额监控业务流程图.md`
- `diagrams/投后限额监控业务逻辑梳理.md`
- `diagrams/核心设计原则与架构优势.md`
- `diagrams/核心设计原则与架构优势.png`
- `diagrams/系统整体架构.md`
- `diagrams/限额监控核心逻辑要点.md`
- `diagrams/限额监控核心逻辑要点（7 大维度）.png`

### `docs/`

这些文档建议保留：

- `docs/CONFIG_MANAGEMENT.md`
- `docs/HISTORY_DATA_IMPLEMENTATION.md`
- `docs/config_refactor_plan.md`
- `docs/config_refactor_validation.md`
- `docs/db_migration_plan.md`
- `docs/golden_test_validation_issues.md`
- `docs/stage0_mcode_logic_10_tables.md`
- `docs/省份标准化方案说明.md`
- `docs/file_tree_cleanup_plan.md`
- `docs/materials_cleanup_recommendations.md`

### `汇报/`

`汇报/` 建议保留少量关键 PDF，形成“项目阶段成果索引”，而不是保留所有过程材料。

建议保留：

- `汇报/限额监控看板week1.pdf`
- `汇报/week2/限额监控看板week2v2.pdf`
- `汇报/week3/week3汇报.pdf`
- `汇报/week4/week4汇报.pdf`
- `汇报/week5/week5.pdf`
- `汇报/week6/限额监控自动化系统阶段性汇报.pdf`
- `汇报/week7/数据库落库实施方案.pdf`
- `汇报/week8/week8.pdf`

如后续仍需要可编辑源文件，可额外保留对应 PPTX；否则建议仓库只保留 PDF，PPTX 外置归档。

## 建议外置归档

### `汇报/`

以下内容建议移到项目外归档目录，例如：

```text
~/Documents/LimitMonitorReports/
```

建议外置或从仓库移除：

- `汇报/week2/限额监控看板week2.pptx`
- `汇报/week2/限额监控看板week2v2.pptx`
- `汇报/week3/week3汇报.pptx`
- `汇报/week3/截图/截图1.png`
- `汇报/week3/截图/截图3.png`
- `汇报/week3/截图/截图4png.png`
- `汇报/week4/week4汇报.pptx`
- `汇报/week5/week5.pptx`
- `汇报/week5/分类信用与集中度监控：Stage2-A 计算引擎落地.pptx`
- `汇报/week6/限额监控自动化系统阶段性汇报-活泼版.pdf`
- `汇报/week6/限额监控自动化系统阶段性汇报.pptx`
- `汇报/week7/数据库落库实施方案.pptx`
- `汇报/week8/01.png`
- `汇报/week8/02.png`
- `汇报/week8/03.png`
- `汇报/week8/04.png`
- `汇报/week8/05.png`
- `汇报/week8/06.png`
- `汇报/week8/07.png`
- `汇报/week8/08.png`
- `汇报/week8/09.png`
- `汇报/week8/11.png`
- `汇报/week8/12.png`
- `汇报/week8/13.png`
- `汇报/week8/14.png`
- `汇报/week8/高收益口径与限额配置重构_PPT讲稿_小白版.md`
- `汇报/week8/高收益口径与限额配置重构_PPT讲稿_小白版.pdf`
- `汇报/week8/高收益口径与限额配置重构_imagegen作图提示词.md`

注意：week1 到 week6 的多份文件已经被 Git 跟踪；week7/week8 目前属于 ignored 本地材料。处理策略应不同：

- 已跟踪文件：需要用一次 Git 提交移出仓库。
- ignored 本地材料：可以直接移动到项目外归档。

### `diagrams/` 中可外置的交付型文件

- `diagrams/限额监控看板.pptx`

这个 PPT 更像演示交付物，不像项目运行文档。建议外置，仓库保留相关 Markdown 和导出的关键 PNG 即可。

## 建议删除或仅归档后删除

以下内容建议先外置归档，再从项目工作区删除：

- `汇报/week2/` 中旧版和 v2 同时存在，仓库只保留 `week2v2.pdf`。
- `汇报/week5/` 中 `week5.*` 与专题版并存，仓库只保留专题版 PDF。
- `汇报/week6/` 中普通版和活泼版并存，仓库只保留普通最终 PDF。
- `汇报/week8/` 中 `01.png` 到 `14.png` 属于制作素材，若最终 PDF 已确认，可移出项目。
- 所有 `.DS_Store` 文件。

不建议直接删除尚未归档的 PPT/PDF，因为它们可能仍有复用价值。

## 暂不建议动

- `data_source_0123/`
- `sample data/`
- `data_config_source/`
- `data_for_testing/`
- `data_for_testing_0407/`
- `data_for_testing_0410/`

这些属于第三阶段数据目录，当前暂不处理。

## 推荐第四阶段执行方案

1. 创建项目外归档目录。
2. 复制或移动所有 `汇报/` 原始材料到项目外归档，确保可回溯。
3. 仓库内保留“建议保留”的关键 Markdown 和关键 PPT/PDF。
4. 删除仓库内重复 PPTX、截图、制作素材和非最终版本。
5. 对 Git 已跟踪的 week1 到 week6 文件，单独提交一次文档整理变更。
6. 保留 `diagrams/` 中架构和业务流程相关 Markdown/PNG。
7. 将 `diagrams/限额监控看板.pptx` 外置归档。

## 建议最终仓库内 `汇报/` 形态

```text
汇报/
  限额监控看板week1.pdf
  week2/
    限额监控看板week2v2.pdf
  week3/
    week3汇报.pdf
  week4/
    week4汇报.pdf
  week5/
    week5.pdf
  week6/
    限额监控自动化系统阶段性汇报.pdf
  week7/
    数据库落库实施方案.pdf
  week8/
    week8.pdf
```

这会保留阶段性成果，同时去掉大部分重复源文件、截图和制作过程材料。
