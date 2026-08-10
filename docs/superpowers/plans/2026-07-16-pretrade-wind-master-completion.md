# 交易前非持仓债主数据与上线口径一致化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 让“单券可购额度查询”和“一揽子债券超限试算”对持仓债、非持仓债都构造出与已上线 Excel 底稿同形、同语义的原始交易行，并只调用既有 ProductionRiskKernel。

**Architecture:** 持仓债只从已归档交易前上下文读取原始字段；非持仓债只在当前请求中以 WindPy、Windows Excel Wind 公式和少量确定性转换生成同一组原始字段。TradeOverlayBuilder 将该行追加至共同内核的既有原始持仓输入表，Stage0/1/2 保持不变；不落库 Wind 返回值，不改展示快照。

**Tech Stack:** Python 3.14、pandas、pytest、WindPy、Windows Excel + Wind Excel 插件（xlwings）。

## Global Constraints

- 不修改 src/risk_core/ 中任何 Stage0/1/2 限额公式、分组、覆盖关系或展示快照计算。
- 持仓债只读取交易前上下文；字段不足或矛盾时返回 MISSING_SNAPSHOT，不以 Wind 补齐。
- 非持仓债的 Wind 数据仅存于单次请求内：不得写数据库、展示归档、issuer_wind_code_mapping.csv 或缓存。
- 不修改 src/common/wind_code_resolver.py；日常 Stage0 继续按既有流程维护发行人映射。
- data/current/stage0_output/issuer_wind_code_mapping.csv 可只读地优先解析债务主体代码；静态映射没有命中时才调用 Excel To_WindCode，且不得回写。
- 生产环境为 Windows，后端需安装并登录 WindPy、Excel、Wind Excel 插件；前端浏览器用户无需 Wind。
- 不以 Wind 数据日期限制查询；但 b_info_outstandingbalance(主证券代码, 业务日期) 的日期参数必须来自当日交易前上下文，因为这是上线 Excel 公式的参数。
- Excel/Wind 明确返回的 0 必须按字段语义保留，不能被统一清洗成缺失。
- 不提交、合并或推送，除非用户另外授权。

---

## 已锁定的原始字段契约

| 原始列 | 上线底稿口径 | 非持仓债实现 | 不允许的替代 |
|---|---|---|---|
| 资产名称 | 资产代码名称 | WindPy SEC_NAME(资产代码) | 不用主证券名称覆盖 |
| 债券类型1 | b_info_windl1type | WindPy WINDL1TYPE | 不作为 ABS 判断条件 |
| 债券类型2 | b_info_windl2type | WindPy WINDL2TYPE | 不模糊匹配 ABS |
| 债券分类／债券分类2 | Excel IFS | 以类型2纯函数派生 | 不用 SEC_TYPE_DE |
| 主证券代码 | b_info_anchorbond(资产代码) | Excel 同一函数 | 不截断后缀，不回退输入代码 |
| 主证券名称 | b_info_name(主证券代码) | Excel 同一函数 | 不用资产名称覆盖 |
| 债券余额(亿) | b_info_outstandingbalance(主证券代码, 日期) | Excel 同一函数 | 不用输入代码余额回退 |
| 债务主体 | 类型2严格等于资产支持证券取 ISSUER，否则 ISSUERUPDATED | 同一严格条件 | 不以类型1、名称含 ABS 或证监会主管ABS判断 |
| 债务主体wind代码 | To_WindCode(债务主体) | 静态映射优先，再 Excel To_WindCode | 不用 WindPy 代码字段猜测 |
| 实际控制人名称 | s_holder_controller | WindPy HOLDER_CONTROLLER | 不在 Provider 应用调整名单 |
| 担保人／代码 | b_agency_guarantor 与 To_WindCode | WindPy AGENCY_GUARANTOR，Excel To_WindCode | 不将 0 视为异常 |
| 发行人类型 | NATURE1 含国有企业则国企 | WindPy NATURE1 后同样派生 | 不提前应用调整表 |
| 是否城投债 | b_info_municipalbondwind | WindPy MUNICIPALBONDWIND | 不以行业替代 |
| wind行业 | b_issuer_windindustry(资产代码,4) | Excel 同一函数 | 不使用 ISSUER_ACTUAL_WINDINDUSTRY |
| 省份 | 五个静态例外后 s_info_province | 同一例外和 Excel 函数 | 不直接用 WindPy PROVINCE |
| 债券类别 | 已上线 IFS | 相同顺序纯函数 | 不简化为是否城投债 |
| ISIN码 | 仅境外债使用 | 非 IB/SH/SZ 使用 ISIN_CODE | 不给境内债补 CND ISIN |

## File Structure

- Modify: src/pretrade/service_models.py — 明确资产名称、主证券名称、完整主证券代码；Provider 接收业务日期。
- Modify: src/pretrade/master_resolution.py — 持仓行读取原始字段；不截断主证券代码、不预先取修正后实控人。
- Create: src/pretrade/master_derivations.py — 仅放确定性转换规则。
- Create: src/pretrade/wind_excel_master.py — 请求内、无文件持久化的 Excel Wind 公式网关。
- Modify: src/pretrade/windpy_master.py — 一次 WindPy 原始请求加 Excel 补齐。
- Modify: src/pretrade/trade_overlay.py — 按同名、同义原始列构造交易行。
- Modify: src/pretrade/pretrade_service.py — 将 inputs.business_date 传至非持仓 Provider。
- Modify: src/visualization/pretrade_service.py — 注入已核验的生产 Provider；页面接口不变。
- Modify: tests/pretrade/test_master_resolution.py、test_trade_overlay.py、test_windpy_master.py、test_pretrade_service.py。
- Create: tests/pretrade/test_master_derivations.py、tests/pretrade/test_wind_excel_master.py。
- Modify: docs/PRETRADE_WIND_RECONCILIATION.md — 替换已过期的“待人工确认”结论。

### Task 1: 固定原始行模型与持仓快照语义

**Files:**
- Modify: src/pretrade/service_models.py
- Modify: src/pretrade/master_resolution.py
- Test: tests/pretrade/test_master_resolution.py

**Interfaces:**
- BondMaster 新增 asset_name: str、main_security_name: str；main_security_code 保持完整 Wind 代码。
- BondMasterProvider.resolve(bond_code: str, business_date: pd.Timestamp) -> MasterResolution。

- [ ] **Step 1: 写失败测试。**

~~~
def test_held_master_preserves_anchor_code_and_raw_controller() -> None:
    row = _held_row("184072.SH")
    row.update({
        "资产名称": "21台州01",
        "主证券代码": "2180399.IB",
        "主证券名称": "21台州债01",
        "实际控制人名称": "原始实控人",
        "实际控制人名称_修正": "修正后实控人",
    })
    result = _resolve_single_held_row(row, "184072.SH")
    assert result.master.main_security_code == "2180399.IB"
    assert result.master.asset_name == "21台州01"
    assert result.master.main_security_name == "21台州债01"
    assert result.master.controller_name == "原始实控人"
~~~

- [ ] **Step 2: 运行失败测试。**

Run: pytest tests/pretrade/test_master_resolution.py -q
Expected: FAIL；当前代码会截断后缀并优先读取修正后实控人。

- [ ] **Step 3: 实现最小改动。**

~~~
_MASTER_COLUMNS = {
    "asset_name": ("资产名称",),
    "main_security_code": ("主证券代码",),
    "main_security_name": ("主证券名称",),
    "controller_name": ("实际控制人名称",),
}
~~~

删除主证券代码的 suffix strip。让 position_context.py 的既有调整实控人名单逻辑在共同内核中继续执行。更新所有测试替身为 resolve(code, business_date)。

- [ ] **Step 4: 运行通过。**

Run: pytest tests/pretrade/test_master_resolution.py -q
Expected: PASS。

- [ ] **Step 5: 提交。**

~~~
git add src/pretrade/service_models.py src/pretrade/master_resolution.py tests/pretrade/test_master_resolution.py
git commit -m "refactor: preserve raw pretrade master fields"
~~~

### Task 2: 以纯函数复现底稿类型、类别和 ISIN 规则

**Files:**
- Create: src/pretrade/master_derivations.py
- Test: tests/pretrade/test_master_derivations.py

**Interfaces:**
- derive_classifications(bond_type2: str) -> tuple[str, str] 返回 (债券分类, 债券分类2)。
- derive_issuer_type(nature1: str) -> str。
- derive_bond_category(base_classification: str, city_investment: str, wind_industry: str, issuer_type: str) -> str。
- derive_isin(input_code: str, wind_isin: object) -> str | None。

- [ ] **Step 1: 写失败测试。**

~~~
@pytest.mark.parametrize(("type2", "expected"), [
    ("地方政府债", ("利率债", "利率债")),
    ("国债", ("利率债", "利率债")),
    ("政策银行债", ("利率债", "利率债")),
    ("政府支持机构债", ("利率债", "利率债")),
    ("可转债", ("信用债", "转债交债")),
    ("可交换债", ("信用债", "转债交债")),
    ("证监会主管ABS", ("信用债", "信用债")),
])
def test_derive_classifications(type2, expected):
    assert derive_classifications(type2) == expected

def test_category_keeps_real_estate_precedence_over_state_owned():
    assert derive_bond_category("信用债", "否", "房地产开发", "国企") == "地产债"

def test_domestic_bond_does_not_receive_wind_isin():
    assert derive_isin("102480811.IB", "CND1000") is None
~~~

- [ ] **Step 2: 运行并确认失败。**

Run: pytest tests/pretrade/test_master_derivations.py -q
Expected: collection failure，因为模块不存在。

- [ ] **Step 3: 实现精确派生。**

~~~
_RATE_TYPES = frozenset({"地方政府债", "国债", "政策银行债", "政府支持机构债"})
_CONVERTIBLE_TYPES = frozenset({"可交换债", "可转债"})
_REAL_ESTATE = frozenset({"房地产开发", "房地产经营公司", "房地产服务", "多样化房地产活动"})

def derive_classifications(bond_type2: str) -> tuple[str, str]:
    base = "利率债" if bond_type2 in _RATE_TYPES else "信用债"
    final = "利率债" if base == "利率债" else ("转债交债" if bond_type2 in _CONVERTIBLE_TYPES else "信用债")
    return base, final
~~~

债券类别顺序必须为：利率债、城投债、四类房地产行业、国企、民企。发行人类型只判断 NATURE1 是否包含“国有企业”。

- [ ] **Step 4: 运行通过并提交。**

Run: pytest tests/pretrade/test_master_derivations.py -q
Expected: PASS。

~~~
git add src/pretrade/master_derivations.py tests/pretrade/test_master_derivations.py
git commit -m "test: lock pretrade master derivations"
~~~

### Task 3: 建立请求内 Excel Wind 公式网关

**Files:**
- Create: src/pretrade/wind_excel_master.py
- Test: tests/pretrade/test_wind_excel_master.py

**Interfaces:**
- ExcelMasterGateway.resolve_anchor_bond(code: str) -> str | int | None。
- ExcelMasterGateway.resolve_main_name(main_code: str) -> str | int | None。
- ExcelMasterGateway.resolve_outstanding_balance(main_code: str, business_date: pd.Timestamp) -> float | int | None。
- ExcelMasterGateway.resolve_to_wind_code(name: str) -> str | int | None。
- ExcelMasterGateway.resolve_industry(code: str) -> str | int | None。
- ExcelMasterGateway.resolve_province(code: str) -> str | int | None。

- [ ] **Step 1: 写失败测试，锁定公式和零值。**

~~~
def test_formulas_match_source_workbook():
    formulas = FormulaBuilder(pd.Timestamp("2026-07-10")).for_code("184072.SH")
    assert formulas.anchor == '=b_info_anchorbond("184072.SH")'
    assert formulas.industry == '=b_issuer_windindustry("184072.SH",4)'
    assert formulas.province == '=s_info_province("184072.SH")'

def test_excel_zero_is_preserved_as_source_value():
    gateway = FakeExcelGateway(
        anchor={"292680009.IB": "UULB.SG"},
        name={"UULB.SG": 0},
        balance={"UULB.SG": 0},
    )
    assert gateway.resolve_main_name("UULB.SG") == 0
    assert gateway.resolve_outstanding_balance("UULB.SG", pd.Timestamp("2026-07-10")) == 0
~~~

- [ ] **Step 2: 运行并确认失败。**

Run: pytest tests/pretrade/test_wind_excel_master.py -q
Expected: collection failure，因为模块不存在。

- [ ] **Step 3: 实现无持久化生产适配器。**

生产适配器使用隐藏 Excel 和未保存临时工作簿，在内存写入上述精确公式、调用 calculate、读取结果，并在 finally 中关闭 workbook 与 Excel app。不得创建 xlsx 文件、不得调用 WindCodeResolver、不得写数据库或 CSV。省份先处理 144212.SZ 为北京，292680009.IB、292480003.IB、292480007.IB、102582786.IB 为海外，其他代码调用 s_info_province。

- [ ] **Step 4: 运行通过并提交。**

Run: pytest tests/pretrade/test_wind_excel_master.py -q
Expected: PASS；测试仅使用 Fake，不依赖本机 Excel。

~~~
git add src/pretrade/wind_excel_master.py tests/pretrade/test_wind_excel_master.py
git commit -m "feat: add request scoped Excel Wind gateway"
~~~

### Task 4: 替换临时 Wind Provider，落实债务主体与主证券链路

**Files:**
- Modify: src/pretrade/windpy_master.py
- Test: tests/pretrade/test_windpy_master.py

**Interfaces:**
- WindPyBondMasterProvider.resolve(bond_code: str, business_date: pd.Timestamp) -> MasterResolution。
- 一次 WindPy 请求字段固定为 SEC_NAME、ISIN_CODE、ISSUER、ISSUERUPDATED、HOLDER_CONTROLLER、AGENCY_GUARANTOR、WINDL1TYPE、WINDL2TYPE、NATURE1、MUNICIPALBONDWIND。

- [ ] **Step 1: 写失败测试。**

~~~
def test_abs_uses_issuer_only_when_type2_is_exact_asset_backed_security():
    row = make_wind_row(
        WINDL2TYPE="资产支持证券",
        ISSUER="原始权益人",
        ISSUERUPDATED="更新债务主体",
    )
    assert provider_for(row).resolve("X.IB", DAY).master.issuer_name == "原始权益人"

def test_non_exact_abs_type2_keeps_issuerupdated():
    row = make_wind_row(
        WINDL2TYPE="证监会主管ABS",
        ISSUER="原始权益人",
        ISSUERUPDATED="更新债务主体",
    )
    assert provider_for(row).resolve("X.IB", DAY).master.issuer_name == "更新债务主体"

def test_anchor_code_keeps_suffix_and_never_falls_back_to_input_code():
    result = provider_with_excel(anchor={"184072.SH": "2180399.IB"}).resolve("184072.SH", DAY)
    assert result.master.main_security_code == "2180399.IB"
~~~

另加静态映射优先、映射未命中才 To_WindCode、担保人 0 对应空代码、境内债 ISIN 为空、UULB.SG 名称和余额 0 无输入代码回退、行业和省份经 Excel 获取的测试。

- [ ] **Step 2: 运行并确认失败。**

Run: pytest tests/pretrade/test_windpy_master.py -q
Expected: FAIL；当前 Provider 将字段都当作 WindPy 直取，且截断主证券代码。

- [ ] **Step 3: 实现最小适配器序列。**

~~~
issuer_name = raw["ISSUER"] if raw["WINDL2TYPE"] == "资产支持证券" else raw["ISSUERUPDATED"]
main_code = excel.resolve_anchor_bond(input_code)
main_name = excel.resolve_main_name(main_code)
balance = excel.resolve_outstanding_balance(main_code, business_date)
issuer_code = static_issuer_map.get(issuer_name) or excel.resolve_to_wind_code(issuer_name)
~~~

将 HOLDER_CONTROLLER 原样传出；Provider 不读调整实控人名单或发行人类型调整表。只把调用失败、主证券代码不能解析、债务主体或类型2真实缺失视为 MISSING_MASTER。担保名称非 0 而 To_WindCode 为 0 时，按照 Excel 公式返回空担保代码，让既有内核决定适用性。

- [ ] **Step 4: 运行通过并提交。**

Run: pytest tests/pretrade/test_windpy_master.py -q
Expected: PASS。

~~~
git add src/pretrade/windpy_master.py tests/pretrade/test_windpy_master.py
git commit -m "fix: align nonheld Wind master with source workbook"
~~~

### Task 5: 以同形原始交易行连接共同内核

**Files:**
- Modify: src/pretrade/trade_overlay.py
- Modify: src/pretrade/pretrade_service.py
- Modify: src/visualization/pretrade_service.py
- Test: tests/pretrade/test_trade_overlay.py
- Test: tests/pretrade/test_pretrade_service.py

**Interfaces:**
- _position_row() 输出与 债券持仓明细表_信用债 相同字段语义。
- 页面服务 API 不变。

- [ ] **Step 1: 写失败测试。**

~~~
def test_overlay_uses_asset_and_anchor_fields_without_rewriting():
    row = _position_row(DAY, line, alias_master())
    assert row["资产代码"] == "184072.SH"
    assert row["资产名称"] == "21台州01"
    assert row["主证券代码"] == "2180399.IB"
    assert row["主证券名称"] == "21台州债01"
    assert row["实际控制人名称"] == "原始实控人"
    assert row["实际控制人名称_修正"] == "原始实控人"
~~~

- [ ] **Step 2: 运行并确认失败。**

Run: pytest tests/pretrade/test_trade_overlay.py tests/pretrade/test_pretrade_service.py -q
Expected: FAIL；当前代码把输入代码和单一名称写进多个不同语义的列。

- [ ] **Step 3: 实现最小改动。**

资产名称写 master.asset_name；主证券代码写 master.main_security_code；主证券名称写 master.main_security_name。服务装配向 Resolver 传 inputs.business_date。高收益附加行只替换为与现有原始源同义的代码和名称；不得改动 risk_core。

- [ ] **Step 4: 运行通过并提交。**

Run: pytest tests/pretrade/test_trade_overlay.py tests/pretrade/test_pretrade_service.py -q
Expected: PASS。

~~~
git add src/pretrade/trade_overlay.py src/pretrade/pretrade_service.py src/visualization/pretrade_service.py tests/pretrade/test_trade_overlay.py tests/pretrade/test_pretrade_service.py
git commit -m "fix: overlay exact pretrade source fields"
~~~

### Task 6: 分层回归、实测与归档烟测

**Files:**
- Modify: docs/PRETRADE_WIND_RECONCILIATION.md
- Test: tests/pretrade/
- Test data: data_source_0123/统计报表底稿1_债券.xlsx

- [ ] **Step 1: 添加冻结样本测试。**

固定以下样本：102480811.IB（普通持仓）、184072.SH 到 2180399.IB（主证券别名）、292680009.IB 到 UULB.SG（名称和余额明确为 0）、159636.SH（类型1为资产支持证券但类型2为证监会主管ABS）。断言 Provider 原始字段与 data_source_0123 同名列一致，并断言 Stage0/1/2 指纹不变。

- [ ] **Step 2: 运行全量自动测试。**

Run: PYTHONPATH=".:/Users/dellawang/Desktop/LimitMonitorAutomation/.venv/lib/python3.14/site-packages" /opt/homebrew/bin/pytest -q
Expected: 全部通过；允许原有已知 skip，不允许新增失败。

- [ ] **Step 3: 在已登录的 Windows Wind 环境做四债实测。**

Run: python scripts/verify_pretrade_wind_master.py 102480811.IB 184072.SH 292680009.IB 159636.SH
Expected: 每只输出资产代码、主证券代码、主证券名称、余额、债务主体、债务主体代码、行业、省份；不写数据库或文件。

- [ ] **Step 4: 用 data_source_0123 完整归档并做交易前烟测。**

运行既有归档入口，再调用持仓债单券、非持仓债单券、单债篮子、同主体两债篮子。检查：展示快照结果未改变；两个新增模块只读已归档上下文；非持仓债只在本次调用 Wind。

- [ ] **Step 5: 更新核验文档并提交。**

核验文档写明已验证字段、四个冻结样本、禁用字段和“Wind 不持久化”检查结论。

~~~
git add docs/PRETRADE_WIND_RECONCILIATION.md tests/pretrade
git commit -m "test: verify pretrade Wind source parity"
~~~

## 验收标准

1. 债务主体严格复现 IF(债券类型2="资产支持证券", ISSUER, ISSUERUPDATED)；证监会主管ABS 固定验证为默认 ISSUERUPDATED 分支。
2. 主证券代码、名称、余额均以 Excel anchor 结果为唯一输入，完整后缀保留，绝不回退输入代码。
3. 交易追加行可与持仓底稿逐列比较；共同内核继续独立应用原有实控人和发行人类型调整表。
4. Stage0/1/2 源码不变；冻结数据既有归档结果指纹一致。
5. 不新增数据库表、写入、Wind 缓存或展示快照字段；非持仓 Wind 数据不持久化。
6. 自动测试、Windows 四样本实测、完整归档和页面烟测全部通过后，才能申请合并。

## 自检

- 债务主体严格分支由 Task 4 与验收标准 1 覆盖。
- 主证券完整链路由 Task 1、Task 3、Task 4、Task 5 与验收标准 2 覆盖。
- 共同内核不变由全局约束、Task 5、验收标准 4 覆盖。
- 无落库由全局约束、Task 6、验收标准 5 覆盖。
- Provider、Resolver 的 resolve(code, business_date) 签名在 Task 1 定义，在 Task 4、Task 5 使用。
