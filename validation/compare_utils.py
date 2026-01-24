"""
数据校验通用工具函数
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Any


class CompareUtils:
    """数据对比工具类"""
    
    def __init__(self, tolerance: float = 0.0001):
        """
        初始化
        
        Args:
            tolerance: 相对误差容差（默认0.01%）
        """
        self.tolerance = tolerance
        self.results = []
    
    def compare_basic_structure(
        self, 
        ref_df: pd.DataFrame, 
        output_df: pd.DataFrame, 
        name: str
    ) -> Dict[str, Any]:
        """
        对比基础结构（行数、列数）
        
        Returns:
            包含对比结果的字典
        """
        result = {
            "表名": name,
            "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "检查项": []
        }
        
        # 行数对比
        row_match = len(ref_df) == len(output_df)
        result["检查项"].append({
            "项目": "行数",
            "参考值": len(ref_df),
            "实际值": len(output_df),
            "差异": len(output_df) - len(ref_df),
            "通过": row_match,
            "状态": "✅" if row_match else "❌"
        })
        
        # 列数对比
        col_match = len(ref_df.columns) == len(output_df.columns)
        result["检查项"].append({
            "项目": "列数",
            "参考值": len(ref_df.columns),
            "实际值": len(output_df.columns),
            "差异": len(output_df.columns) - len(ref_df.columns),
            "通过": col_match,
            "状态": "✅" if col_match else "❌"
        })
        
        # 列名对比
        ref_cols = set(ref_df.columns)
        out_cols = set(output_df.columns)
        missing_cols = ref_cols - out_cols
        extra_cols = out_cols - ref_cols
        
        if missing_cols or extra_cols:
            result["检查项"].append({
                "项目": "列名差异",
                "缺失列": list(missing_cols) if missing_cols else "无",
                "多余列": list(extra_cols) if extra_cols else "无",
                "通过": False,
                "状态": "⚠️"
            })
        
        return result
    
    def compare_numeric_field(
        self,
        ref_df: pd.DataFrame,
        output_df: pd.DataFrame,
        field: str,
        comparison_type: str = "sum"
    ) -> Dict[str, Any]:
        """
        对比数值型字段
        
        Args:
            ref_df: 参考DataFrame
            output_df: 输出DataFrame
            field: 字段名
            comparison_type: 对比类型 ('sum', 'mean', 'count')
        
        Returns:
            对比结果字典
        """
        if field not in ref_df.columns or field not in output_df.columns:
            return {
                "项目": f"{field}_{comparison_type}",
                "通过": False,
                "状态": "⚠️",
                "备注": "字段不存在"
            }
        
        # 计算统计值
        if comparison_type == "sum":
            ref_val = ref_df[field].sum()
            out_val = output_df[field].sum()
        elif comparison_type == "mean":
            ref_val = ref_df[field].mean()
            out_val = output_df[field].mean()
        elif comparison_type == "count":
            ref_val = ref_df[field].count()
            out_val = output_df[field].count()
        else:
            raise ValueError(f"不支持的对比类型: {comparison_type}")
        
        # 计算相对误差
        if abs(ref_val) > 1e-10:
            rel_error = abs(ref_val - out_val) / abs(ref_val)
        else:
            rel_error = 0 if abs(out_val) < 1e-10 else 1.0
        
        passed = rel_error < self.tolerance
        
        return {
            "项目": f"{field}_{comparison_type}",
            "参考值": f"{ref_val:,.4f}" if isinstance(ref_val, (int, float)) else str(ref_val),
            "实际值": f"{out_val:,.4f}" if isinstance(out_val, (int, float)) else str(out_val),
            "相对误差": f"{rel_error*100:.6f}%",
            "通过": passed,
            "状态": "✅" if passed else "❌"
        }
    
    def compare_categorical_field(
        self,
        ref_df: pd.DataFrame,
        output_df: pd.DataFrame,
        field: str,
        value: Any
    ) -> Dict[str, Any]:
        """
        对比分类字段（如"是否超限"）
        
        Args:
            field: 字段名
            value: 要统计的值（如"是"）
        """
        if field not in ref_df.columns or field not in output_df.columns:
            return {
                "项目": f"{field}='{value}'的数量",
                "通过": False,
                "状态": "⚠️",
                "备注": "字段不存在"
            }
        
        ref_count = (ref_df[field] == value).sum()
        out_count = (output_df[field] == value).sum()
        
        passed = ref_count == out_count
        
        return {
            "项目": f"{field}='{value}'的数量",
            "参考值": ref_count,
            "实际值": out_count,
            "差异": out_count - ref_count,
            "通过": passed,
            "状态": "✅" if passed else "❌"
        }
    
    def sample_compare_rows(
        self,
        ref_df: pd.DataFrame,
        output_df: pd.DataFrame,
        key_field: str,
        compare_fields: List[str],
        sample_size: int = 5
    ) -> List[Dict[str, Any]]:
        """
        抽样对比行数据
        
        Args:
            key_field: 用于匹配的主键字段
            compare_fields: 要对比的字段列表
            sample_size: 抽样数量
        """
        results = []
        
        if key_field not in ref_df.columns or key_field not in output_df.columns:
            return [{"错误": "主键字段不存在"}]
        
        # 获取共同的键
        common_keys = set(ref_df[key_field]) & set(output_df[key_field])
        if len(common_keys) == 0:
            return [{"错误": "没有共同的键"}]
        
        # 随机抽样
        sample_keys = list(common_keys)[:sample_size]
        
        for key in sample_keys:
            ref_row = ref_df[ref_df[key_field] == key].iloc[0]
            out_row = output_df[output_df[key_field] == key].iloc[0]
            
            row_result = {
                "键": key,
                "字段对比": []
            }
            
            for field in compare_fields:
                if field in ref_df.columns and field in output_df.columns:
                    ref_val = ref_row[field]
                    out_val = out_row[field]
                    
                    # 判断是否相等（考虑浮点数精度）
                    if isinstance(ref_val, (int, float)) and isinstance(out_val, (int, float)):
                        if abs(ref_val) > 1e-10:
                            match = abs(ref_val - out_val) / abs(ref_val) < self.tolerance
                        else:
                            match = abs(out_val) < 1e-10
                    else:
                        match = str(ref_val) == str(out_val)
                    
                    row_result["字段对比"].append({
                        "字段": field,
                        "参考值": ref_val,
                        "实际值": out_val,
                        "匹配": match,
                        "状态": "✅" if match else "❌"
                    })
            
            results.append(row_result)
        
        return results
    
    def print_result(self, result: Dict[str, Any]):
        """打印对比结果（美化输出）"""
        print("\n" + "=" * 80)
        print(f"📊 表名: {result['表名']}")
        print(f"⏰ 时间: {result['时间']}")
        print("=" * 80)
        
        for item in result["检查项"]:
            status = item.get("状态", "")
            project = item.get("项目", "")
            print(f"\n{status} {project}")
            
            for key, val in item.items():
                if key not in ["项目", "状态", "通过"]:
                    print(f"   {key}: {val}")
        
        # 统计通过率
        total = len(result["检查项"])
        passed = sum(1 for item in result["检查项"] if item.get("通过", False))
        print("\n" + "-" * 80)
        print(f"✅ 通过率: {passed}/{total} ({passed/total*100:.1f}%)")
        print("=" * 80)
