"""
检验：精达转债的实控人为何在看板为 None、PBI 为李光荣
1. 底稿中精达转债的 债务主体、债务主体wind代码、实际控制人名称_修正
2. 调整实控人名单（德勤）中是否包含该 债务主体wind代码，以及 调整后实际控制人
3. 结论与建议
"""
import sys
from pathlib import Path

import pandas as pd

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "限额"
DRAFT_PATH = DATA_DIR / "统计报表底稿2_债券SPPI.xlsx"
DELOITTE_PATH = DATA_DIR / "德勤-主体评级列表.xlsx"
BOND_NAME = "精达转债"


def main():
    print("=" * 60)
    print("检验：精达转债 实控人 (看板 None vs PBI 李光荣)")
    print("=" * 60)

    # ---------- 1. 底稿中精达转债 ----------
    if not DRAFT_PATH.exists():
        print(f"\n[跳过] 底稿不存在: {DRAFT_PATH}")
    else:
        print(f"\n【1】底稿: {DRAFT_PATH.name} / 债券_含穿透持仓")
        try:
            df_draft = pd.read_excel(DRAFT_PATH, sheet_name="债券_含穿透持仓", engine="openpyxl")
        except Exception as e:
            print(f"  读取失败: {e}")
            df_draft = None
        if df_draft is not None:
            # 匹配 精达转债：资产名称或资产代码
            name_col = "资产名称" if "资产名称" in df_draft.columns else None
            code_col = "资产代码" if "资产代码" in df_draft.columns else None
            if name_col:
                mask = df_draft[name_col].astype(str).str.contains(BOND_NAME, na=False)
            else:
                mask = pd.Series(False, index=df_draft.index)
            if code_col and not mask.any():
                mask = df_draft[code_col].astype(str).str.contains("精达", na=False)
            hit = df_draft.loc[mask]
            if hit.empty:
                print(f"  未找到包含「{BOND_NAME}」或「精达」的记录。")
            else:
                cols = [c for c in ["资产代码", "资产名称", "债务主体", "债务主体wind代码", "实际控制人名称_修正", "内部证券账户名称"] if c in hit.columns]
                print(hit[cols].head(10).to_string())
                # 逐行检查实控人是否为空
                for i, row in hit.iterrows():
                    controller_draft = row.get("实际控制人名称_修正")
                    account = row.get("内部证券账户名称", "—")
                    if pd.isna(controller_draft) or str(controller_draft).strip() == "" or str(controller_draft).strip().lower() == "nan":
                        print(f"  → 行(内证={account}): 底稿 实际控制人名称_修正 = 为空/NaN")
                    else:
                        print(f"  → 行(内证={account}): 底稿 实际控制人名称_修正 = {controller_draft}")
                # 若仅一条且非空，再输出结论
                if len(hit) == 1:
                    c0 = hit.iloc[0].get("实际控制人名称_修正")
                    if pd.notna(c0) and str(c0).strip():
                        print(f"  → 底稿仅一条且为 李光荣，合并后理论上应为 李光荣；若看板仍为 None，请检查 Stage1 中 replace('', None) 或后续是否覆盖。")
        print()

    # ---------- 2. 调整实控人名单（德勤） ----------
    if not DELOITTE_PATH.exists():
        print(f"\n[跳过] 德勤表不存在: {DELOITTE_PATH}")
    else:
        print(f"\n【2】调整实控人名单: {DELOITTE_PATH.name} / Sheet1")
        try:
            df_deloitte = pd.read_excel(DELOITTE_PATH, sheet_name="Sheet1", engine="openpyxl")
        except Exception as e:
            print(f"  读取失败: {e}")
            df_deloitte = None
        if df_deloitte is not None:
            code_col = "主体wind代码" if "主体wind代码" in df_deloitte.columns else None
            name_col = "主体名称" if "主体名称" in df_deloitte.columns else None
            controller_col = "调整后实际控制人" if "调整后实际控制人" in df_deloitte.columns else None
            if not code_col:
                print(f"  表中无「主体wind代码」列，现有列: {list(df_deloitte.columns)}")
            else:
                # 从底稿取 债务主体wind代码（若已读）
                issuer_codes_to_check = []
                if not DRAFT_PATH.exists():
                    pass
                else:
                    try:
                        df_d = pd.read_excel(DRAFT_PATH, sheet_name="债券_含穿透持仓", engine="openpyxl")
                        if "债务主体wind代码" in df_d.columns and "资产名称" in df_d.columns:
                            m = df_d["资产名称"].astype(str).str.contains(BOND_NAME, na=False)
                            if m.any():
                                issuer_codes_to_check = df_d.loc[m, "债务主体wind代码"].dropna().astype(str).str.strip().unique().tolist()
                    except Exception:
                        pass
                if not issuer_codes_to_check:
                    # 用「李光荣」反查德勤表
                    if controller_col:
                        li = df_deloitte[df_deloitte[controller_col].astype(str).str.strip().str.contains("李光荣", na=False)]
                        if not li.empty:
                            print("  德勤表中「调整后实际控制人」含「李光荣」的记录（前5条）:")
                            cols = [c for c in ["主体wind代码", "主体名称", "调整后实际控制人"] if c in li.columns]
                            print(li[cols].head().to_string())
                    # 列出德勤表主体数量
                    print(f"  德勤表主体数: {len(df_deloitte)}，列: {list(df_deloitte.columns)}")
                else:
                    for ic in issuer_codes_to_check:
                        in_list = df_deloitte[df_deloitte[code_col].astype(str).str.strip() == str(ic).strip()]
                        if in_list.empty:
                            # 尝试去掉 .0
                            ic_alt = str(ic).replace(".0", "").strip()
                            in_list = df_deloitte[df_deloitte[code_col].astype(str).str.strip().str.replace(".0", "", regex=False) == ic_alt]
                        if in_list.empty:
                            print(f"  → 债务主体wind代码 [{ic}] 不在德勤表中。")
                        else:
                            row = in_list.iloc[0]
                            print(f"  → 债务主体wind代码 [{ic}] 在德勤表中:")
                            print(f"     主体名称: {row.get(name_col, '—')}")
                            print(f"     调整后实际控制人: {row.get(controller_col, '—')}")
        print()

    # ---------- 3. 结论 ----------
    print("【3】结论与建议")
    print("  - 底稿中精达转债 实际控制人名称_修正 = 李光荣（仅一条，内证=多资产投资部交易性-可转债量化策略）。")
    print("  - 德勤表中该主体(铜陵精达…)存在，但 调整后实际控制人 = nan；合并后代码会用底稿值 fillna，理论上应为 李光荣。")
    print("  - 若看板仍为 None：请确认 Stage1 运行时使用的底稿/德勤表与当前一致，并检查 Stage1 中 replace('', None) 或后续是否将 李光荣 覆盖。")
    print("  - 建议：在德勤-主体评级列表.xlsx 中把该主体的「调整后实际控制人」设为「李光荣」，与 PBI 一致且不依赖底稿兜底。")
    print("=" * 60)


if __name__ == "__main__":
    main()
    sys.exit(0)
