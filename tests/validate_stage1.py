"""
阶段1数据验证脚本
对比Python输出与Excel参考文件，验证数据准确性
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple
import sys

class Stage1Validator:
    """阶段1数据验证器"""
    
    def __init__(self):
        self.python_output_dir = Path("data/stage1_output")
        self.excel_reference = Path("sample data/阶段/限额监控_阶段1.xlsx")
        self.results = {}
        
    def validate_all(self) -> Dict:
        """执行所有验证"""
        print("=" * 80)
        print("阶段1数据验证")
        print("=" * 80)
        
        # 检查文件是否存在
        if not self.excel_reference.exists():
            print(f"❌ Excel参考文件不存在: {self.excel_reference}")
            return {}
        
        # 读取Excel参考文件的所有sheet
        excel_sheets = pd.ExcelFile(self.excel_reference).sheet_names
        print(f"\nExcel参考文件包含 {len(excel_sheets)} 个sheet:")
        for i, sheet in enumerate(excel_sheets, 1):
            print(f"  {i}. {sheet}")
        
        # 验证核心表
        print("\n" + "=" * 80)
        print("开始验证核心输出表")
        print("=" * 80)
        
        # 1. 债券持仓明细表_信用债_合并风险限额相关
        self.validate_table(
            "债券持仓明细表_信用债_合并风险限额相关",
            "债券持仓明细表_信用债_合并风险限额相关",
            key_columns=['日期', '资产代码', '资产名称', '债务主体', '库存数量(万)_PR', 
                        '是否属于高收益', '担保公司是否准入']
        )
        
        # 2. 限额明细_债券持仓明细表_信用债1_2
        self.validate_table(
            "限额明细_债券持仓明细表_信用债1_2",
            "限额明细_债券持仓明细表_信用债1_2",
            key_columns=['日期', '资产代码', '资产名称', '单一债券规模限额指标值',
                        '单一债券是否超限', '单一主体是否超限']
        )
        
        # 3. 限额明细_债券持仓明细表_信用债1_1
        self.validate_table(
            "限额明细_债券持仓明细表_信用债1_1",
            "限额明细_债券持仓明细表_信用债1_1",
            key_columns=['日期', '资产代码', '资产名称', '是否超限_合并判断']
        )
        
        # 4. 限额明细_单一担保人
        self.validate_table(
            "限额明细_单一担保人",
            "限额明细_单一担保人",
            key_columns=['日期', '资产代码', '担保人', '单一担保人规模限额指标值', 
                        '单一担保人是否超限']
        )
        
        # 生成总结报告
        self.print_summary()
        
        return self.results
    
    def validate_table(self, python_file: str, excel_sheet: str, 
                      key_columns: List[str] = None) -> bool:
        """
        验证单个表
        
        Args:
            python_file: Python输出文件名（不含.xlsx）
            excel_sheet: Excel参考文件的sheet名
            key_columns: 需要重点验证的关键列
        """
        print(f"\n{'=' * 80}")
        print(f"验证: {python_file}")
        print(f"{'=' * 80}")
        
        result = {
            'table': python_file,
            'status': 'unknown',
            'issues': []
        }
        
        # 读取Python输出
        python_path = self.python_output_dir / f"{python_file}.xlsx"
        if not python_path.exists():
            print(f"❌ Python输出文件不存在: {python_path}")
            result['status'] = 'missing'
            result['issues'].append('Python输出文件不存在')
            self.results[python_file] = result
            return False
        
        try:
            df_python = pd.read_excel(python_path)
            print(f"✓ Python输出: {len(df_python)} 行 × {len(df_python.columns)} 列")
        except Exception as e:
            print(f"❌ 读取Python输出失败: {e}")
            result['status'] = 'error'
            result['issues'].append(f'读取失败: {e}')
            self.results[python_file] = result
            return False
        
        # 读取Excel参考
        try:
            df_excel = pd.read_excel(self.excel_reference, sheet_name=excel_sheet)
            print(f"✓ Excel参考: {len(df_excel)} 行 × {len(df_excel.columns)} 列")
        except Exception as e:
            print(f"❌ 读取Excel参考失败: {e}")
            result['status'] = 'error'
            result['issues'].append(f'读取Excel参考失败: {e}')
            self.results[python_file] = result
            return False
        
        # 1. 对比行数
        row_diff = len(df_python) - len(df_excel)
        if row_diff != 0:
            print(f"⚠️  行数差异: Python {len(df_python)} 行 vs Excel {len(df_excel)} 行 (差异: {row_diff:+d})")
            result['issues'].append(f"行数差异: {row_diff:+d}")
        else:
            print(f"✓ 行数匹配: {len(df_python)} 行")
        
        # 2. 对比列数
        col_diff = len(df_python.columns) - len(df_excel.columns)
        if col_diff != 0:
            print(f"⚠️  列数差异: Python {len(df_python.columns)} 列 vs Excel {len(df_excel.columns)} 列 (差异: {col_diff:+d})")
            result['issues'].append(f"列数差异: {col_diff:+d}")
        else:
            print(f"✓ 列数匹配: {len(df_python.columns)} 列")
        
        # 3. 对比列名
        python_cols = set(df_python.columns)
        excel_cols = set(df_excel.columns)
        
        missing_cols = excel_cols - python_cols
        extra_cols = python_cols - excel_cols
        
        if missing_cols:
            print(f"⚠️  Python输出缺少列: {missing_cols}")
            result['issues'].append(f"缺少列: {missing_cols}")
        
        if extra_cols:
            print(f"⚠️  Python输出多余列: {extra_cols}")
            result['issues'].append(f"多余列: {extra_cols}")
        
        if not missing_cols and not extra_cols:
            print(f"✓ 列名完全匹配")
        
        # 4. 对比关键列的数据
        if key_columns:
            print(f"\n验证关键列:")
            common_cols = python_cols & excel_cols
            valid_key_cols = [col for col in key_columns if col in common_cols]
            
            for col in valid_key_cols:
                self.compare_column(df_python, df_excel, col, result)
        
        # 5. 检查数据类型
        print(f"\n数据类型对比:")
        for col in list(python_cols & excel_cols)[:5]:  # 只检查前5列
            py_type = df_python[col].dtype
            ex_type = df_excel[col].dtype
            if py_type != ex_type:
                print(f"  ⚠️  {col}: Python {py_type} vs Excel {ex_type}")
            else:
                print(f"  ✓ {col}: {py_type}")
        
        # 设置最终状态
        if len(result['issues']) == 0:
            result['status'] = 'perfect'
            print(f"\n✅ 验证通过: 数据完全匹配!")
        elif row_diff == 0 and col_diff == 0:
            result['status'] = 'good'
            print(f"\n✓ 验证基本通过: 行列数匹配，但存在 {len(result['issues'])} 个问题")
        else:
            result['status'] = 'failed'
            print(f"\n❌ 验证失败: 存在 {len(result['issues'])} 个问题")
        
        self.results[python_file] = result
        return result['status'] in ['perfect', 'good']
    
    def compare_column(self, df_python: pd.DataFrame, df_excel: pd.DataFrame, 
                      col: str, result: Dict):
        """对比单个列的数据"""
        if col not in df_python.columns or col not in df_excel.columns:
            return
        
        # 如果行数不同，只对比共同的行数
        min_rows = min(len(df_python), len(df_excel))
        
        py_data = df_python[col].iloc[:min_rows]
        ex_data = df_excel[col].iloc[:min_rows]
        
        # 处理数值类型
        if pd.api.types.is_numeric_dtype(py_data) and pd.api.types.is_numeric_dtype(ex_data):
            # 对于数值，检查是否完全相等（考虑NaN）
            diff_mask = ~np.isclose(py_data.fillna(0), ex_data.fillna(0), rtol=1e-10, atol=1e-10)
            diff_count = diff_mask.sum()
        else:
            # 对于非数值，直接比较
            # 先转换为字符串进行比较，处理NaN
            py_str = py_data.astype(str).replace('nan', '')
            ex_str = ex_data.astype(str).replace('nan', '')
            diff_mask = py_str != ex_str
            diff_count = diff_mask.sum()
        
        if diff_count > 0:
            match_rate = (min_rows - diff_count) / min_rows * 100
            print(f"  ⚠️  {col}: {diff_count}/{min_rows} 个值不匹配 (匹配率: {match_rate:.2f}%)")
            
            # 显示前3个不匹配的值
            diff_indices = []
            for i, val in enumerate(diff_mask):
                if val and len(diff_indices) < 3:
                    diff_indices.append(i)
            
            for idx in diff_indices:
                py_val = py_data.iloc[idx]
                ex_val = ex_data.iloc[idx]
                print(f"      行{idx}: Python={py_val} vs Excel={ex_val}")
            
            result['issues'].append(f"{col}: {diff_count}个不匹配值")
        else:
            print(f"  ✓ {col}: 完全匹配")
    
    def print_summary(self):
        """打印验证总结"""
        print("\n" + "=" * 80)
        print("验证总结")
        print("=" * 80)
        
        perfect = sum(1 for r in self.results.values() if r['status'] == 'perfect')
        good = sum(1 for r in self.results.values() if r['status'] == 'good')
        failed = sum(1 for r in self.results.values() if r['status'] == 'failed')
        total = len(self.results)
        
        print(f"\n总计: {total} 个表")
        print(f"  ✅ 完全匹配: {perfect} 个")
        print(f"  ✓ 基本通过: {good} 个")
        print(f"  ❌ 验证失败: {failed} 个")
        
        if failed > 0:
            print(f"\n失败的表:")
            for name, result in self.results.items():
                if result['status'] == 'failed':
                    print(f"  - {name}")
                    for issue in result['issues']:
                        print(f"    • {issue}")
        
        # 计算总体匹配度
        if total > 0:
            success_rate = (perfect + good) / total * 100
            print(f"\n总体匹配度: {success_rate:.1f}%")
            
            if success_rate == 100:
                print("\n🎉 恭喜！所有表验证通过！")
            elif success_rate >= 80:
                print(f"\n✓ 大部分表验证通过，需要修复 {failed} 个表")
            else:
                print(f"\n⚠️  存在较多问题，需要仔细检查")


def main():
    """主函数"""
    validator = Stage1Validator()
    results = validator.validate_all()
    
    # 返回退出码
    failed_count = sum(1 for r in results.values() if r['status'] == 'failed')
    sys.exit(0 if failed_count == 0 else 1)


if __name__ == "__main__":
    main()
