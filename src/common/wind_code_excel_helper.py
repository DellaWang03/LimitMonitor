"""
Wind代码Excel辅助获取
通过Excel的To_WindCode函数获取Python API不支持的Wind代码
"""

import pandas as pd
from pathlib import Path
import platform
import os
from loguru import logger


class WindCodeExcelHelper:
    """使用Excel的To_WindCode函数获取Wind代码"""
    
    def __init__(self, temp_dir: Path = None):
        self.temp_dir = temp_dir or Path("temp")
        self.temp_dir.mkdir(exist_ok=True)
        self.system = platform.system()

    @staticmethod
    def _is_successful_wind_result(value: object) -> bool:
        if pd.isna(value):
            return False
        text = str(value).strip()
        if text.lower() in {"", "nan", "none", "null", "na", "n/a"}:
            return False
        if text.startswith("="):
            return False
        return text.upper() not in {
            "#N/A",
            "#NAME?",
            "#VALUE!",
            "#REF!",
            "#DIV/0!",
            "#NULL!",
            "#NUM!",
        }
    
    def batch_get_wind_codes(self, issuer_names: list, use_xlwings: bool = None) -> pd.DataFrame:
        """
        批量获取Wind代码
        
        参数:
            issuer_names: 发行人名称列表
            use_xlwings: 是否使用xlwings自动化（None=自动尝试）
            
        返回:
            DataFrame: 包含'发行人名称'和'Wind代码'列
        """
        if not issuer_names:
            return pd.DataFrame(columns=['发行人名称', 'Wind代码'])
        
        logger.info(f"批量获取Wind代码: {len(issuer_names)} 个发行人")

        if os.environ.get("LIMIT_MONITOR_FROZEN_WIND_RESULT") == "1":
            if (
                os.environ.get("ENV") != "test"
                or os.environ.get("LIMIT_MONITOR_PROFILE") != "local"
            ):
                raise RuntimeError("冻结 Wind 结果仅允许测试环境 local profile 使用")
            return self._get_via_template(issuer_names)
        
        # Windows 保持现有 xlwings 生产路径；macOS 使用预写公式后由可见
        # Excel/Wind 自动计算、复制结果和关闭的独立路径。
        if use_xlwings is None:
            use_xlwings = True
        
        if use_xlwings:
            try:
                if self.system == "Darwin":
                    return self._get_via_macos_excel(issuer_names)
                return self._get_via_xlwings(issuer_names)
            except Exception as e:
                logger.warning(f"Excel自动化失败: {e}")
                if self.system == "Darwin":
                    raise
                logger.info("切换到半自动模式...")
        
        # 半自动模式：生成Excel模板
        return self._get_via_template(issuer_names)
    
    def _get_via_xlwings(self, issuer_names: list) -> pd.DataFrame:
        """通过xlwings自动获取（所有平台 + Excel）"""
        try:
            import xlwings as xw
        except ImportError:
            raise ImportError("需要安装xlwings: pip3 install xlwings")
        
        logger.info(f"使用xlwings自动化获取Wind代码（{self.system}）...")
        
        temp_file = self.temp_dir / "wind_codes_auto.xlsx"
        
        # 启动Excel（macOS和Windows兼容）
        logger.info(f"启动Excel应用...")
        app = xw.App(visible=False, add_book=False)
        
        try:
            logger.info(f"创建工作簿...")
            wb = app.books.add()
            ws = wb.sheets[0]
            
            # 写入表头
            logger.info(f"写入{len(issuer_names)}个发行人名称...")
            ws.range('A1').value = '发行人名称'
            ws.range('B1').value = 'Wind代码'
            
            # 批量写入发行人名称
            issuer_data = [[name] for name in issuer_names]
            ws.range(f'A2').value = issuer_data
            
            # 写入公式
            logger.info(f"添加To_WindCode()公式...")
            for i in range(2, len(issuer_names) + 2):
                ws.range(f'B{i}').formula = f'=To_WindCode(A{i})'
            
            # 强制计算
            logger.info(f"执行Excel公式计算...")
            app.calculate()
            
            # 等待计算完成（根据数量调整等待时间）
            import time
            wait_time = min(5 + len(issuer_names) // 100, 30)  # 最多等30秒
            logger.info(f"等待Wind API响应（{wait_time}秒）...")
            time.sleep(wait_time)
            
            # 读取数据
            logger.info(f"读取Wind代码结果...")
            last_row = len(issuer_names) + 1
            df = ws.range(f'A1:B{last_row}').options(pd.DataFrame, header=True).value
            
            # 统一列名，保证与 batch_resolve_missing 期望一致（xlwings/Excel 读回时列名可能异常或首列为 index）
            if df is None or not isinstance(df, pd.DataFrame):
                logger.warning("xlwings 未返回有效 DataFrame，返回空结果")
                return pd.DataFrame(columns=['发行人名称', 'Wind代码'])
            if len(df.columns) == 1:
                df = df.reset_index()
            if len(df.columns) < 2:
                logger.warning(f"读回列数不足 2，实际: {df.columns.tolist()}")
                return pd.DataFrame(columns=['发行人名称', 'Wind代码'])
            if '发行人名称' not in df.columns or 'Wind代码' not in df.columns:
                df = df.rename(columns={df.columns[0]: '发行人名称', df.columns[1]: 'Wind代码'})
            
            # 保存备份
            wb.save(temp_file)
            logger.info(f"✓ 结果已保存: {temp_file}")
            
            # 统计成功率
            success_count = df['Wind代码'].apply(self._is_successful_wind_result).sum()
            logger.info(f"✓ 成功获取: {success_count}/{len(issuer_names)} ({success_count/len(issuer_names)*100:.1f}%)")
            
            return df
            
        finally:
            try:
                wb.close()
            except Exception as e:
                logger.debug(f"关闭工作簿: {e}")
            try:
                app.quit()
            except Exception as e:
                logger.debug(f"退出Excel: {e}")

    def _get_via_macos_excel(self, issuer_names: list) -> pd.DataFrame:
        """通过预写公式工作簿自动调用 macOS Excel/Wind。"""
        from src.common.macos_wind_excel import MacOSWindExcelFormulaRunner

        logger.info("使用 macOS Excel/Wind 自动化获取Wind代码...")
        formulas = [
            f"=To_WindCode(A{row_number})"
            for row_number in range(2, len(issuer_names) + 2)
        ]
        values = MacOSWindExcelFormulaRunner().evaluate(
            formulas,
            labels=issuer_names,
        )
        result = pd.DataFrame(
            {
                "发行人名称": issuer_names,
                "Wind代码": values,
            }
        )
        success_count = result["Wind代码"].apply(
            self._is_successful_wind_result
        ).sum()
        logger.info(
            f"✓ macOS Excel/Wind 成功获取: "
            f"{success_count}/{len(issuer_names)}"
        )
        return result
    
    def _get_via_template(self, issuer_names: list) -> pd.DataFrame:
        """生成Excel模板，需要手动打开保存。仅合并结果文件中属于本次缺失主体的行，避免误用旧结果。"""
        template_file = self.temp_dir / "wind_codes_template.xlsx"
        result_file = self.temp_dir / "wind_codes_result.xlsx"
        issuer_set = set(issuer_names)
        
        logger.info(f"生成Excel模板: {template_file}（{len(issuer_names)} 个缺失主体）")
        
        # 创建DataFrame（B列用 Wind代码 便于另存为后直接识别）
        data = {
            '发行人名称': issuer_names,
            'Wind代码': [f'=To_WindCode(A{i+2})' for i in range(len(issuer_names))]
        }
        df = pd.DataFrame(data)
        
        # 保存为Excel
        with pd.ExcelWriter(template_file, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Wind代码查询')
        
        # 给出操作提示
        logger.warning("=" * 80)
        logger.warning("⚠️  需要手动操作（1分钟）：")
        logger.warning(f"   1. 在Windows上打开: {template_file.absolute()}")
        logger.warning(f"   2. 将B列公式粘贴为值或等待计算完成")
        logger.warning(f"   3. 另存为: {result_file.absolute()}")
        logger.warning(f"   4. 重新运行程序")
        logger.warning("=" * 80)
        
        # 检查是否有结果文件（用户可能已保存新结果）
        if result_file.exists():
            logger.info(f"✓ 发现结果文件: {result_file}")
            df_result = pd.read_excel(result_file)
            
            # 支持列名 Wind代码 或 Wind代码_公式（模板历史曾用 _公式）
            wind_col = None
            if 'Wind代码' in df_result.columns:
                wind_col = 'Wind代码'
            elif 'Wind代码_公式' in df_result.columns:
                wind_col = 'Wind代码_公式'
            if '发行人名称' in df_result.columns and wind_col:
                df_result = df_result[['发行人名称', wind_col]].copy()
                df_result.rename(columns={wind_col: 'Wind代码'}, inplace=True)
                # 只保留属于本次缺失主体的行，避免合并到其它批次的旧数据
                df_result = df_result[df_result['发行人名称'].astype(str).str.strip().isin(issuer_set)]
                # 只返回成功拉取的Wind结果；0 表示 Excel 已返回结果，但不由长期缓存复用。
                df_valid = df_result[df_result['Wind代码'].apply(self._is_successful_wind_result)].copy()
                
                n_total = len(df_valid)
                logger.info(f"✓ 有效Wind代码: {n_total} 个（均属于本次 {len(issuer_names)} 个缺失主体）")
                if n_total < len(issuer_names):
                    logger.warning(f"  结果行数({n_total})少于本次缺失数({len(issuer_names)})，请确认已对全部缺失主体另存为 result 后重跑")
                return df_valid[['发行人名称', 'Wind代码']]
            else:
                logger.warning(f"⚠️  结果文件列名不正确")
                logger.warning(f"   期望含: 发行人名称、Wind代码（或 Wind代码_公式）")
                logger.warning(f"   实际: {df_result.columns.tolist()}")
        
        # 返回空DataFrame（等待手动处理）
        raise RuntimeError(
            f"等待手动处理Excel文件。\n"
            f"详细说明: 查看 MACOS_WIND_CODE操作指南.md\n"
            f"或运行: python3 manual_get_wind_codes.py"
        )
