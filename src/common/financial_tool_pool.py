from __future__ import annotations

from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET
import zipfile

import pandas as pd

from .financial_tool_pool_rules import (
    build_financial_tool_pool_sets,
    clean_tool_pool_text,
    normalize_tool_pool_code,
    row_in_financial_tool_pool,
)


def _parse_damaged_excel(file_path: Path, logger: Any = None) -> pd.DataFrame:
    try:
        with zipfile.ZipFile(file_path, "r") as zip_ref:
            with zip_ref.open("xl/sharedStrings.xml") as f:
                tree = ET.parse(f)
                root = tree.getroot()
                ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                strings = []
                for si in root.findall(".//main:si", ns):
                    t = si.find(".//main:t", ns)
                    strings.append(t.text if t is not None and t.text else "")

            worksheet_files = [
                name
                for name in zip_ref.namelist()
                if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
            ]
            if not worksheet_files:
                if logger is not None:
                    logger.error("手动解析Excel失败: 未找到工作表文件")
                return pd.DataFrame()

            worksheet_files.sort()
            sheet_path = worksheet_files[0]
            if logger is not None:
                logger.info(f"    使用工作表: {sheet_path}")

            with zip_ref.open(sheet_path) as f:
                tree = ET.parse(f)
                root = tree.getroot()
                rows = root.findall(".//main:row", ns)

                data = []
                for row in rows:
                    row_data = []
                    for cell in row.findall(".//main:c", ns):
                        cell_type = cell.get("t", "n")
                        v = cell.find(".//main:v", ns)
                        if v is None or not v.text:
                            row_data.append(None)
                            continue
                        if cell_type == "s":
                            idx = int(v.text)
                            row_data.append(strings[idx] if idx < len(strings) else None)
                        else:
                            row_data.append(v.text)
                    if row_data:
                        data.append(row_data)

                if data:
                    df = pd.DataFrame(data[1:], columns=data[0])
                    if logger is not None:
                        logger.info(f"    手动解析成功: {len(df)} 行, {len(df.columns)} 列")
                    return df
    except Exception as exc:
        if logger is not None:
            logger.error(f"手动解析Excel失败: {exc}")

    return pd.DataFrame()


def _prepare_financial_tool_pool(df: pd.DataFrame, logger: Any = None) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame({"代码": [], "简称": []})

    if "品种" in df.columns:
        df = df[df["品种"].astype(str).str.strip() == "可转债"].copy()
        if logger is not None:
            logger.info(f"    ✓ 筛选品种='可转债': {len(df)} 行")

    cols_to_keep = [col for col in ("代码", "简称") if col in df.columns]
    if not cols_to_keep:
        if logger is not None:
            logger.warning("  金融工具池设置缺少'代码'/'简称'列")
        return pd.DataFrame({"代码": [], "简称": []})

    df = df[cols_to_keep].copy()
    if "代码" in df.columns:
        df["代码"] = df["代码"].apply(normalize_tool_pool_code)
        df.loc[df["代码"] == "", "代码"] = pd.NA
    if "简称" in df.columns:
        df["简称"] = df["简称"].apply(clean_tool_pool_text)
        df.loc[df["简称"] == "", "简称"] = pd.NA

    df = df.dropna(how="all").drop_duplicates()

    if "代码" not in df.columns:
        df["代码"] = pd.NA
    if "简称" not in df.columns:
        df["简称"] = pd.NA

    code_count = df["代码"].notna().sum()
    name_count = df["简称"].notna().sum()
    if logger is not None:
        logger.info(f"  金融工具池设置（可转债白名单）: {len(df)} 行 (代码: {code_count}, 简称: {name_count})")
        valid_names = df["简称"].dropna().head(10).tolist()
        if valid_names:
            logger.info(f"    前10个简称: {valid_names}")

    return df[["代码", "简称"]]


def load_financial_tool_pool(file_path: str | Path, logger: Any = None) -> pd.DataFrame:
    file_path = Path(file_path)
    try:
        xls = pd.ExcelFile(file_path)
        sheet_name = xls.sheet_names[0] if xls.sheet_names else None
        if sheet_name:
            return _prepare_financial_tool_pool(
                pd.read_excel(file_path, sheet_name=sheet_name),
                logger=logger,
            )
    except Exception as exc:
        if logger is not None:
            logger.warning(f"  pandas读取失败，尝试手动解析XML: {str(exc)[:50]}")

    df = _parse_damaged_excel(file_path, logger=logger)
    return _prepare_financial_tool_pool(df, logger=logger)
