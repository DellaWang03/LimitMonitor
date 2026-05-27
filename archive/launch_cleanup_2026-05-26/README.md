# 上线收尾归档

本目录存放 2026-05-26 上线收尾时从主工作区移出的外围文件。归档原则是保留可追溯性，但不再让一次性脚本、历史校验和旧测试入口干扰当前上线运行口径。

## 目录说明

- `tests/`：历史业务验证、环境检查、脚本式测试
- `validation/`：旧 Stage 级验证、专项准确性校验、历史逻辑校验材料
- `scripts/`：一次性迁移、诊断、手动 Wind/Excel 辅助脚本
- `root_scripts/`：曾放在项目根目录的临时诊断脚本
- `environment/`：已被根目录 `requirements.txt` 合并替代的旧依赖文件

## 当前保留入口

- 每日生产链路：`bash run_daily.sh`
- Web 看板：`bash start_web.sh`
- 代码级测试：`python3 -m pytest -q tests`
- 上线前集成测试：`bash tests/run_full_integration_test.sh [ARCHIVE_DATE] [REF_DIR]`
