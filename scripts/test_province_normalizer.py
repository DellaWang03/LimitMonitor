"""
测试省份标准化工具
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_basic():
    """基础测试（不依赖pandas）"""
    from src.common.province_normalizer import ProvinceNormalizer
    
    print("=" * 80)
    print("省份标准化工具 - 基础测试")
    print("=" * 80)
    
    print(f"\n1. 映射表包含 {len(ProvinceNormalizer.PROVINCE_MAPPING)} 个省份变体")
    print(f"2. 标准省份名称 {len(ProvinceNormalizer.STANDARD_PROVINCES)} 个")
    
    print("\n3. 测试标准化功能:")
    test_cases = {
        '云南': '云南省',
        '贵州': '贵州省',
        '北京': '北京市',
        '内蒙古': '内蒙古自治区',
        '内蒙': '内蒙古自治区',
        '广西': '广西壮族自治区',
        '云南省': '云南省',  # 已经是标准格式
        '贵州省': '贵州省',  # 已经是标准格式
    }
    
    all_passed = True
    for original, expected in test_cases.items():
        result = ProvinceNormalizer._normalize_single(original)
        status = "✓" if result == expected else "✗"
        if result != expected:
            all_passed = False
        print(f"  {status} '{original}' → '{result}' (期望: '{expected}')")
    
    print("\n" + "=" * 80)
    if all_passed:
        print("✓ 所有测试通过")
    else:
        print("✗ 部分测试失败")
    print("=" * 80)
    
    return all_passed

if __name__ == "__main__":
    success = test_basic()
    sys.exit(0 if success else 1)
