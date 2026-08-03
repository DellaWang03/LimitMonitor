"""单券可购额度与一揽子超限试算的共同内核服务。"""

from __future__ import annotations

from collections.abc import Sequence
from math import isfinite
from numbers import Real
from typing import Any

from src.risk_core import ProductionRiskKernel

from .master_resolution import SnapshotBondMasterResolver
from .result_adapter import (
    BasketCheck,
    KernelProjectionRun,
    PretradeResultAdapter,
    SingleBondQuote,
)
from .service_models import BondMasterProvider, MasterResolution, PretradeLine
from .trade_overlay import TradeOverlayBuilder


class PretradeServiceError(RuntimeError):
    """交易前服务无法从完整 current 快照构造共同内核试算。"""


class PretradeRiskService:
    """只读 current 快照，使用生产共同内核完成一次请求本地的试算。"""

    def __init__(
        self,
        *,
        store: Any,
        wind_provider: BondMasterProvider,
        kernel: ProductionRiskKernel | None = None,
        overlay_builder: TradeOverlayBuilder | None = None,
        result_adapter: PretradeResultAdapter | None = None,
    ) -> None:
        self._store = store
        self._resolver = SnapshotBondMasterResolver(wind_provider)
        self._kernel = kernel or ProductionRiskKernel()
        self._overlay_builder = overlay_builder or TradeOverlayBuilder()
        self._result_adapter = result_adapter or PretradeResultAdapter()

    def available_accounts(self) -> tuple[str, ...]:
        """返回交易前 current 快照实际包含的账户。"""

        _snapshot, inputs = self._load_current_context()
        return _available_accounts(inputs)

    def quote_single_bond(self, bond_code: str, account: str) -> SingleBondQuote:
        """用内部零 PR 探针取得交易前可购上限；该探针不会持久化。"""

        normalized_code = _validate_text(bond_code, "债券代码").upper()
        validated_account = _validate_text(account, "拟买入账户")
        line = PretradeLine(
            line_id=1,
            bond_code=normalized_code,
            account=validated_account,
            pr_wan=0.0,
        )
        run = self._run((line,))
        return self._result_adapter.single_from_probe(run)

    def check_basket(self, lines: Sequence[PretradeLine]) -> BasketCheck:
        """对全部有效拟买行执行一次合并后的交易后试算。"""

        validated_lines = _validate_basket_lines(lines)
        run = self._run(validated_lines)
        return self._result_adapter.basket_from_kernel(run)

    def _run(self, lines: tuple[PretradeLine, ...]) -> KernelProjectionRun:
        snapshot, inputs = self._load_current_context()
        available_accounts = set(_available_accounts(inputs))
        invalid_accounts = sorted(
            {line.account for line in lines if line.account not in available_accounts}
        )
        if invalid_accounts:
            raise ValueError(
                "拟买入账户不属于当前交易前快照: "
                + "、".join(invalid_accounts)
            )

        resolutions = self._resolve_lines(inputs, lines)
        baseline_stage1, baseline_stage2 = _run_kernel(self._kernel, inputs)
        overlay_inputs = self._overlay_builder.build(inputs, lines, resolutions)
        overlay_stage1, overlay_stage2 = _run_kernel(self._kernel, overlay_inputs)
        return KernelProjectionRun(
            data_date=str(snapshot.data_date),
            lines=lines,
            resolutions=resolutions,
            baseline_stage1=baseline_stage1,
            baseline_stage2=baseline_stage2,
            overlay_stage1=overlay_stage1,
            overlay_stage2=overlay_stage2,
        )

    def _load_current_context(self):
        snapshot = self._store.get_current_snapshot()
        if snapshot is None:
            raise PretradeServiceError("交易前当前快照不存在")
        try:
            inputs = self._store.load_kernel_input(snapshot.snapshot_id)
        except Exception as exc:
            raise PretradeServiceError("交易前当前快照读取失败") from exc
        return snapshot, inputs

    def _resolve_lines(self, inputs, lines: tuple[PretradeLine, ...]) -> dict[int, MasterResolution]:
        by_code: dict[str, MasterResolution] = {}
        resolutions: dict[int, MasterResolution] = {}
        # 整批共用一个 Wind/Excel 会话：一揽子里每笔非持仓债都要跑两批 Excel
        # 公式，逐笔启停会反复弹出 Excel，也会成倍放大关不掉窗口的概率。
        with self._resolver.master_session():
            for line in lines:
                if line.bond_code not in by_code:
                    by_code[line.bond_code] = self._resolver.resolve(
                        inputs, line.bond_code
                    )
                resolutions[line.line_id] = by_code[line.bond_code]
        return resolutions


def _run_kernel(kernel: Any, inputs):
    try:
        stage1 = kernel.run_stage1(inputs)
        stage2 = kernel.run_stage2(inputs, stage1)
    except Exception as exc:
        raise PretradeServiceError("共同限额内核运行失败") from exc
    return stage1, stage2


def _available_accounts(inputs: Any) -> tuple[str, ...]:
    try:
        frame = inputs.require_frames(("债券持仓明细表",))["债券持仓明细表"]
    except Exception as exc:
        raise PretradeServiceError("交易前快照缺少账户来源") from exc
    column = "内部证券账户名称"
    if column not in frame.columns:
        raise PretradeServiceError("交易前快照缺少账户来源")
    accounts = {
        str(value).strip()
        for value in frame[column].dropna().tolist()
        if str(value).strip() and str(value).strip() != "全部"
    }
    if not accounts:
        raise PretradeServiceError("交易前快照没有可用账户")
    return tuple(sorted(accounts))


def _validate_basket_lines(lines: Sequence[PretradeLine]) -> tuple[PretradeLine, ...]:
    if isinstance(lines, (str, bytes)) or not isinstance(lines, Sequence) or not lines:
        raise ValueError("交易清单不能为空")
    seen_ids: set[int] = set()
    validated: list[PretradeLine] = []
    for line in lines:
        if not isinstance(line, PretradeLine):
            raise TypeError("交易清单必须由 PretradeLine 组成")
        if isinstance(line.line_id, bool) or not isinstance(line.line_id, int):
            raise ValueError("输入行编号必须是整数")
        if line.line_id in seen_ids:
            raise ValueError("输入行编号不能重复")
        seen_ids.add(line.line_id)
        bond_code = _validate_text(line.bond_code, "债券代码").upper()
        account = _validate_text(line.account, "拟买入账户")
        pr_wan = _validate_positive_finite(line.pr_wan, "拟买金额_PR")
        full_price = _validate_optional_positive_finite(line.full_price_cost_wan)
        validated.append(
            PretradeLine(
                line_id=line.line_id,
                bond_code=bond_code,
                account=account,
                pr_wan=pr_wan,
                full_price_cost_wan=full_price,
            )
        )
    return tuple(validated)


def _validate_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}不能为空")
    return value.strip()


def _validate_positive_finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field}必须是有限正数")
    numeric = float(value)
    if not isfinite(numeric) or numeric <= 0:
        raise ValueError(f"{field}必须是有限正数")
    return numeric


def _validate_optional_positive_finite(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("拟买全价成本必须是有限正数")
    numeric = float(value)
    if not isfinite(numeric) or numeric <= 0:
        raise ValueError("拟买全价成本必须是有限正数")
    return numeric
