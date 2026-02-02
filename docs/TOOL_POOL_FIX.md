# 金融工具池设置文件解析修复

## 问题背景

### 现象
运行 `run_stage1.py` 时，金融工具池设置读取失败：
```
执行查询: 金融工具池设置
  pandas读取失败，尝试手动解析XML: Unable to read workbook: could not read stylesheet
手动解析Excel失败: "There is no item named 'xl/worksheets/sheet1.xml' in the archive"
  手动解析失败或数据格式不正确
✓ 0 行
```

### 影响
- **金融工具池白名单读取失败** → `tool_pool_names` 和 `tool_pool_codes` 都是空集合
- **所有可转债无法通过白名单匹配** → 规则1完全失效
- **导致18个可转债缺失**：
  ```
  力合转债、浙矿转债、锦鸡转债、路维转债、华亚转债、
  利扬转债、优彩转债、宇邦转债、艾录转债、华医转债、
  威唐转债、中环转2、华辰转债、汇成转债、佳禾转债、
  东亚转债、亿田转债、福新转债
  ```

---

## 根本原因

### 文件结构问题
金融工具池设置.xlsx 文件的工作表名称是 **`sheet0.xml`**，而不是标准的 `sheet1.xml`：

```bash
$ unzip -l 金融工具池设置.xlsx | grep worksheets
  1743503  01-19-2026 13:03   xl/worksheets/sheet0.xml  ← 实际名称
```

### 代码问题
`_parse_damaged_excel` 函数硬编码了工作表名称：

```python
# 修复前（第348行）
with zip_ref.open('xl/worksheets/sheet1.xml') as f:  # ← 硬编码，找不到文件
    tree = ET.parse(f)
    ...
```

**结果**：抛出异常 `There is no item named 'xl/worksheets/sheet1.xml' in the archive`

---

## 修复方案

### 改进：动态检测工作表名称

```python
def _parse_damaged_excel(self, file_path: Path) -> pd.DataFrame:
    """
    手动解析损坏的Excel文件（样式表损坏但数据完好）
    通过解析ZIP内的XML文件来提取数据
    动态检测工作表名称（sheet0.xml、sheet1.xml等）
    """
    try:
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            # 1. 读取共享字符串表
            ...
            
            # 2. 动态查找第一个工作表
            worksheet_files = [name for name in zip_ref.namelist() 
                              if name.startswith('xl/worksheets/sheet') and name.endswith('.xml')]
            
            if not worksheet_files:
                logger.error(f"手动解析Excel失败: 未找到工作表文件")
                return pd.DataFrame()
            
            # 按名称排序，使用第一个工作表
            worksheet_files.sort()
            sheet_path = worksheet_files[0]  # ← 动态选择（sheet0.xml、sheet1.xml等）
            logger.info(f"    使用工作表: {sheet_path}")
            
            # 3. 读取工作表数据
            with zip_ref.open(sheet_path) as f:
                tree = ET.parse(f)
                ...
```

### 关键改进
1. ✅ **动态查找**：扫描所有 `xl/worksheets/sheet*.xml` 文件
2. ✅ **自动选择**：按名称排序，使用第一个工作表
3. ✅ **健壮性**：适配任何工作表命名（sheet0、sheet1、sheet2等）
4. ✅ **日志记录**：记录实际使用的工作表名称

---

## 验证方法

### 方法1：运行测试脚本
```bash
cd /Users/dellawang/Desktop/LimitMonitorAutomation
python3 test_tool_pool_fix.py
```

**预期输出**：
```
✅ 成功! 共读取 XXX 行数据
   列名: ['代码', '简称', '品种', ...]
   有效简称: XXX 个
   
   前20个简称:
     1. ...
     2. ...
   
   检查缺失债券:
     在白名单中: 18/18 个
       ✓ 力合转债
       ✓ 浙矿转债
       ...
```

### 方法2：运行完整流程
```bash
python3 run_stage1.py
python3 run_stage2.py
```

**关注日志**：
```
执行查询: 金融工具池设置
    使用工作表: xl/worksheets/sheet0.xml
    手动解析成功: XXX 行, XXX 列
  金融工具池设置（可转债白名单）: XXX 行 (代码: XXX, 简称: XXX)
    前10个简称: ['...', '...', ...]
```

---

## 影响文件

- `src/stage2/stage2_processor.py` - 修复 `_parse_damaged_excel` 函数
- `test_tool_pool_fix.py` - 新增测试脚本

---

## 相关问题

- **HIGH_YIELD_BOND_FIX.md** - 高收益债券识别逻辑修复（依赖金融工具池正确加载）
- **Issue**: 缺失18个可转债

---

## 最后更新

- **日期**: 2026-01-29
- **版本**: v2.3
- **状态**: ✅ 已修复
