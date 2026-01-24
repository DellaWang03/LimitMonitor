"""
数值准确性校验（openpyxl 只读模式，避免 pandas 崩溃）
"""
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

from openpyxl import load_workbook


PROJECT_ROOT = Path(__file__).parent.parent


def collect_stats_xlsx(
    file_path: Path,
    sheet_name: Optional[str],
    numeric_fields: List[str],
    categorical_field: Optional[str] = None,
    categorical_value: Optional[str] = None,
    max_rows: Optional[int] = None,
) -> Dict[str, object]:
    """收集Excel统计信息（行数、数值字段总和、分类计数）。"""
    wb = load_workbook(file_path, read_only=True, data_only=True)
    if sheet_name:
        ws = wb[sheet_name]
    else:
        ws = wb[wb.sheetnames[0]]

    rows = ws.iter_rows(values_only=True)
    header = next(rows, None)
    if not header:
        return {"row_count": 0, "sums": {}, "cat_count": 0, "columns": []}

    columns = [str(c).strip() if c is not None else "" for c in header]
    idx_map = {col: i for i, col in enumerate(columns)}

    sums = {field: 0.0 for field in numeric_fields if field in idx_map}
    cat_count = 0
    row_count = 0

    for row in rows:
        row_count += 1
        if max_rows and row_count > max_rows:
            break

        for field in sums:
            idx = idx_map[field]
            val = row[idx]
            if val is None:
                continue
            try:
                sums[field] += float(val)
            except Exception:
                continue

        if categorical_field and categorical_value and categorical_field in idx_map:
            idx = idx_map[categorical_field]
            if row[idx] == categorical_value:
                cat_count += 1

    return {
        "row_count": row_count,
        "sums": sums,
        "cat_count": cat_count,
        "columns": columns,
    }


def compare_stats(
    name: str,
    ref_stats: Dict[str, object],
    out_stats: Dict[str, object],
    tolerance: float = 0.0001,
) -> None:
    """打印对比结果。"""
    print("\n" + "=" * 80)
    print(f"📋 {name}")
    print("=" * 80)

    # 行数对比
    ref_rows = ref_stats["row_count"]
    out_rows = out_stats["row_count"]
    row_match = ref_rows == out_rows
    print(f"✅ 行数一致" if row_match else "❌ 行数不一致")
    print(f"   参考: {ref_rows}, 实际: {out_rows}")

    # 数值字段对比
    print("\n🔢 数值字段总和对比:")
    for field, ref_sum in ref_stats["sums"].items():
        out_sum = out_stats["sums"].get(field)
        if out_sum is None:
            print(f"   ⚠️ {field}: 输出文件缺失该字段")
            continue

        if abs(ref_sum) > 1e-10:
            rel_error = abs(ref_sum - out_sum) / abs(ref_sum)
        else:
            rel_error = 0 if abs(out_sum) < 1e-10 else 1.0

        match = rel_error < tolerance
        status = "✅" if match else "❌"
        print(
            f"   {status} {field}: 参考={ref_sum:,.2f}, 实际={out_sum:,.2f}, "
            f"误差={rel_error*100:.6f}%"
        )

    # 超限对比
    if ref_stats.get("cat_count") is not None:
        print("\n📊 超限数量对比:")
        ref_count = ref_stats["cat_count"]
        out_count = out_stats["cat_count"]
        match = ref_count == out_count
        status = "✅" if match else "❌"
        print(f"   {status} 参考={ref_count}, 实际={out_count}")


def main():
    print("\n" + "🚀" * 40)
    print("数据准确性校验 - openpyxl 只读模式")
    print(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("🚀" * 40)

    # 阶段1 - 信用债1_2
    ref_stage1 = PROJECT_ROOT / "sample data" / "阶段" / "限额监控_阶段1.xlsx"
    out_stage1 = PROJECT_ROOT / "data" / "stage1_output" / "限额明细_债券持仓明细表_信用债1_2.xlsx"
    fields_stage1_1_2 = [
        "单一主体持仓(万)",
        "单一主体规模限额(万)",
        "单一实控人持仓(万)",
        "单一实控人规模限额(万)",
    ]

    ref_stats = collect_stats_xlsx(
        ref_stage1,
        "限额明细_债券持仓明细表_信用债1_2",
        fields_stage1_1_2,
        categorical_field="是否超限",
        categorical_value="是",
    )
    out_stats = collect_stats_xlsx(
        out_stage1,
        None,
        fields_stage1_1_2,
        categorical_field="是否超限",
        categorical_value="是",
    )
    compare_stats("阶段1 - 信用债1_2", ref_stats, out_stats)

    # 阶段2 - 地域集中度
    ref_stage2 = PROJECT_ROOT / "sample data" / "阶段" / "限额监控_阶段2.xlsx"
    out_stage2 = PROJECT_ROOT / "data" / "stage2_output" / "限额明细_地域集中度限额(含城投).xlsx"
    fields_stage2_regional = [
        "单一地域总持仓_PR",
        "地域集中度",
        "单一地域城投总持仓_PR",
        "城投地域集中度",
    ]

    ref_stats = collect_stats_xlsx(
        ref_stage2,
        "限额明细_地域集中度限额(含城投)",
        fields_stage2_regional,
    )
    out_stats = collect_stats_xlsx(
        out_stage2,
        None,
        fields_stage2_regional,
    )
    compare_stats("阶段2 - 地域集中度", ref_stats, out_stats)


if __name__ == "__main__":
    main()
