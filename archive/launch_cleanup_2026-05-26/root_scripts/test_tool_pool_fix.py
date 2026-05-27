#!/usr/bin/env python3
"""
测试金融工具池设置读取修复
"""
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from src.stage2.stage2_processor import Stage2Processor
from src.utils.config_loader import ConfigLoader
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def main():
    print("=" * 100)
    print("测试金融工具池设置读取修复")
    print("=" * 100)
    
    # 初始化配置
    config = ConfigLoader()
    data_dir = Path(config.get_data_dir())
    
    print(f"\n数据目录: {data_dir}")
    print(f"目标文件: {data_dir / '金融工具池设置.xlsx'}")
    
    # 初始化处理器
    processor = Stage2Processor(
        data_dir=data_dir,
        output_dir=Path("data/test_output")
    )
    
    print("\n" + "-" * 100)
    print("开始读取金融工具池设置...")
    print("-" * 100 + "\n")
    
    # 测试读取
    df = processor.query_financial_tool_pool()
    
    print("\n" + "=" * 100)
    print("读取结果")
    print("=" * 100)
    
    if df is not None and len(df) > 0:
        print(f"✅ 成功! 共读取 {len(df)} 行数据")
        print(f"   列名: {list(df.columns)}")
        
        if '简称' in df.columns:
            valid_names = df['简称'].dropna()
            valid_names = valid_names[valid_names.astype(str).str.strip().isin(['', 'nan', 'None', '<NA>']) == False]
            name_count = len(valid_names.unique())
            print(f"   有效简称: {name_count} 个")
            
            # 打印前20个简称
            print(f"\n   前20个简称:")
            for i, name in enumerate(sorted(valid_names.unique())[:20], 1):
                print(f"     {i:2d}. {name}")
            
            # 检查缺失的可转债
            missing_bonds = [
                "力合转债", "浙矿转债", "锦鸡转债", "路维转债", "华亚转债",
                "利扬转债", "优彩转债", "宇邦转债", "艾录转债", "华医转债",
                "威唐转债", "中环转2", "华辰转债", "汇成转债", "佳禾转债",
                "东亚转债", "亿田转债", "福新转债"
            ]
            
            names_set = set(valid_names.astype(str).str.strip())
            found_count = sum(1 for bond in missing_bonds if bond in names_set)
            
            print(f"\n   检查缺失债券:")
            print(f"     在白名单中: {found_count}/{len(missing_bonds)} 个")
            
            for bond in missing_bonds:
                if bond in names_set:
                    print(f"       ✓ {bond}")
                else:
                    print(f"       ✗ {bond}")
        
        if '代码' in df.columns:
            valid_codes = df['代码'].dropna()
            valid_codes = valid_codes[valid_codes.astype(str).str.strip().isin(['', 'nan', 'None', '<NA>']) == False]
            code_count = len(valid_codes.unique())
            print(f"\n   有效代码: {code_count} 个")
    else:
        print(f"❌ 失败! 未读取到数据")
        print(f"   返回数据: {df}")
    
    print("\n" + "=" * 100)
    print("测试完成")
    print("=" * 100)

if __name__ == '__main__':
    main()
