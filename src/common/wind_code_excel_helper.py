"""
Wind代码Excel辅助获取
通过Excel的To_WindCode函数获取Python API不支持的Wind代码
"""

import pandas as pd
from pathlib import Path
import platform
from loguru import logger


class WindCodeExcelHelper:
    """使用Excel的To_WindCode函数获取Wind代码"""
    
    def __init__(self, temp_dir: Path = None):
        self.temp_dir = temp_dir or Path("temp")
        self.temp_dir.mkdir(exist_ok=True)
        self.system = platform.system()
    
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
        
        # 默认尝试使用xlwings（所有平台）
        if use_xlwings is None:
            use_xlwings = True
        
        if use_xlwings:
            try:
                return self._get_via_xlwings(issuer_names)
            except Exception as e:
                logger.warning(f"xlwings自动化失败: {e}")
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
            
            # 保存备份
            wb.save(temp_file)
            logger.info(f"✓ 结果已保存: {temp_file}")
            
            # 统计成功率
            success_count = df['Wind代码'].notna().sum()
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
    
    def _get_via_template(self, issuer_names: list) -> pd.DataFrame:
        """生成Excel模板，需要手动打开保存"""
        template_file = self.temp_dir / "wind_codes_template.xlsx"
        result_file = self.temp_dir / "wind_codes_result.xlsx"
        
        logger.info(f"生成Excel模板: {template_file}")
        
        # 创建DataFrame
        data = {
            '发行人名称': issuer_names,
            'Wind代码_公式': [f'=To_WindCode(A{i+2})' for i in range(len(issuer_names))]
        }
        df = pd.DataFrame(data)
        
        # 保存为Excel
        with pd.ExcelWriter(template_file, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Wind代码查询')
        
        # 给出操作提示
        logger.warning("=" * 80)
        logger.warning("⚠️  需要手动操作（1分钟）：")
        logger.warning(f"   1. 在Windows上打开: {template_file.absolute()}")
        logger.warning(f"   2. 将B列的公式粘贴到B列（触发计算）")
        logger.warning(f"   3. 另存为: {result_file.absolute()}")
        logger.warning(f"   4. 重新运行程序")
        logger.warning("=" * 80)
        
        # 检查是否有结果文件
        if result_file.exists():
            logger.info(f"✓ 发现结果文件: {result_file}")
            df_result = pd.read_excel(result_file)
            
            # 验证列名
            if '发行人名称' in df_result.columns and 'Wind代码' in df_result.columns:
                # 只返回有效的Wind代码（非空、非错误值）
                df_valid = df_result[['发行人名称', 'Wind代码']].copy()
                df_valid = df_valid[
                    df_valid['Wind代码'].notna() & 
                    (df_valid['Wind代码'] != '#N/A') &
                    (df_valid['Wind代码'] != '#NAME?') &
                    (df_valid['Wind代码'] != '')
                ]
                
                logger.info(f"✓ 有效Wind代码: {len(df_valid)}/{len(df_result)} 个")
                return df_valid
            else:
                logger.warning(f"⚠️  结果文件列名不正确")
                logger.warning(f"   期望: ['发行人名称', 'Wind代码']")
                logger.warning(f"   实际: {df_result.columns.tolist()}")
        
        # 返回空DataFrame（等待手动处理）
        raise RuntimeError(
            f"等待手动处理Excel文件。\n"
            f"详细说明: 查看 MACOS_WIND_CODE操作指南.md\n"
            f"或运行: python3 manual_get_wind_codes.py"
        )
