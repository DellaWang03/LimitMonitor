# 交易前非持仓债 Wind 主数据对账

核验日期：2026-07-17。目标不是重写限额计算，而是让非持仓债在进入共同内核前，得到与上线债券持仓底稿相同语义的原始字段。

## 已实现的来源契约

| 字段 | 上线底稿口径 | 新增模块实现 |
|---|---|---|
| 债务主体 | 类型2严格等于“资产支持证券”取 ISSUER，否则 ISSUERUPDATED | 相同严格判断 |
| 债务主体 Wind 代码 | To_WindCode(债务主体) | 只读静态发行人映射优先，未命中再 Excel To_WindCode |
| 主证券代码 | b_info_anchorbond(资产代码) | Excel 同一函数；保留完整市场后缀 |
| 主证券名称 | b_info_name(主证券代码) | Excel 同一函数 |
| 债券余额 | b_info_outstandingbalance(主证券代码, 业务日期) | Excel 同一函数；不回退输入代码 |
| 原始实控人 | s_holder_controller | WindPy HOLDER_CONTROLLER；调整仍由共同内核完成 |
| 担保人 | b_agency_guarantor | WindPy AGENCY_GUARANTOR；0 代表无担保 |
| 担保人代码 | IF(To_WindCode(...)=0,"",...) | Excel To_WindCode 后同样将 0 置空 |
| 债券类型1／2 | b_info_windl1type／b_info_windl2type | WindPy WINDL1TYPE／WINDL2TYPE |
| 债券分类、债券类别 | 底稿 IFS | 经单元测试的同顺序 Python 公式 |
| 发行人类型 | NATURE1 含“国有企业”为国企 | WindPy NATURE1 后同样派生 |
| 城投、行业、省份 | 对应 Excel Wind 公式及省份例外 | 城投由 MUNICIPALBONDWIND；行业、省份由同一 Excel 公式和例外 |
| ISIN | 境外债使用，境内为空 | 同一市场规则 |

## 已实测的边界样本

- 102480811.IB：普通债券，行业 Excel 公式返回“煤炭与消费用燃料”。
- 184072.SH → 2180399.IB：资产代码和主证券代码不同，anchor 结果必须完整保留。
- 292680009.IB → UULB.SG：主证券名称、余额的 Excel 输出均为明确 0；不得以输入代码回退。
- 159636.SH：类型1为资产支持证券、类型2为“证监会主管ABS”；仍必须取 ISSUERUPDATED。

## Mac 实时 Wind 复核（2026-07-17）

- 当前 Mac 的 WindPy 已以 `SEC_NAME`、`ISIN_CODE`、`ISSUER`、`ISSUERUPDATED`、
  `HOLDER_CONTROLLER`、`AGENCY_GUARANTOR`、`WINDL1TYPE`、`WINDL2TYPE`、`NATURE1`、
  `MUNICIPALBONDWIND` 成功查询四个边界样本。
- 已登录的 Excel Wind 实时计算确认：`184072.SH -> 2180399.IB`，
  `292680009.IB -> UULB.SG`；对 `UULB.SG`，主证券名称、余额、实控人、担保人和省份均为
  明确的 `0`，不得当作缺失或回退。
- 同一日期下，WindPy `OUTSTANDINGBALANCE` 对 `UULB.SG` 返回 `50`，而底稿函数
  `b_info_outstandingbalance("UULB.SG", "2026-07-10")` 返回 `0`。这证明该字段不能用
  WindPy 余额替换 Excel 公式口径。

## 明确不使用的字段或做法

- 不使用 ISSUER_ACTUAL_WINDINDUSTRY；实测结果不能替代 b_issuer_windindustry(资产代码,4)。
- 不使用 Python WindPy 推断发行人或担保人 Wind 代码；该口径是 Excel To_WindCode。
- 不将 Wind 最新余额改写为 b_info_outstandingbalance 的替代来源。
- 不把非持仓 Wind 返回落库、缓存、写入展示快照或写回发行人映射文件。
- 不修改 Stage0/1/2 限额计算、展示快照计算或数据库 schema。

## 自动化验证

当前交易前测试覆盖：

1. 资产支持证券债务主体严格分支，以及“证监会主管ABS”反例；
2. 主证券代码、名称和余额的 anchor 链路；
3. 静态发行人映射优先、Excel To_WindCode 回退和担保人代码的 0 到空；
4. 债券分类、发行人类型、债券类别、境内 ISIN 规则；
5. 持仓债不补 Wind、原始实控人交由共同内核调整；
6. 交易叠加行的资产字段与主证券字段分离；
7. 非持仓请求使用交易前上下文的业务日期。

## 运行环境说明

生产 Windows 主机须提供已登录的 WindPy、Excel、Wind Excel 插件与 requirements.txt 中声明的 xlwings。浏览器用户无需安装 Wind。开发 Mac 已实时核验 Excel Wind 公式结果；本机 Python 到 Excel 自动化仍需要稳定的 xlwings/Excel 授权环境，不能以此改变 Windows 的生产口径。
