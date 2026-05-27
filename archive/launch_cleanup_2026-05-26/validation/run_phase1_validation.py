"""
运行第1段校验：阶段0配置 + 阶段1核心3表
"""
import sys
from pathlib import Path
from datetime import datetime

# 添加validation目录到路径
validation_dir = Path(__file__).parent
sys.path.insert(0, str(validation_dir))

# 导入校验模块
from validate_stage0 import validate_stage0
from validate_stage1 import validate_stage1_core_tables


def main():
    """主函数：运行第1段校验"""
    print("\n" + "🚀" * 40)
    print("数据校验 - 第1段")
    print("范围：阶段0配置 + 阶段1核心3表")
    print(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("🚀" * 40)
    
    try:
        # 阶段0校验
        print("\n\n" + "▶️ " * 30)
        print("第一部分：阶段0配置校验")
        print("▶️ " * 30)
        stage0_results = validate_stage0()
        
        # 阶段1核心表校验
        print("\n\n" + "▶️ " * 30)
        print("第二部分：阶段1核心表校验")
        print("▶️ " * 30)
        stage1_results = validate_stage1_core_tables()
        
        # ========== 整体总结 ==========
        print("\n\n" + "🎯" * 40)
        print("第1段校验完成 - 整体总结")
        print("🎯" * 40)
        
        # 统计阶段0
        stage0_total = sum(len(r["检查项"]) for r in stage0_results)
        stage0_passed = sum(
            sum(1 for item in r["检查项"] if item.get("通过", False))
            for r in stage0_results
        )
        
        # 统计阶段1
        stage1_total = sum(len(r["检查项"]) for r in stage1_results)
        stage1_passed = sum(
            sum(1 for item in r["检查项"] if item.get("通过", False))
            for r in stage1_results
        )
        
        # 总计
        total_checks = stage0_total + stage1_total
        total_passed = stage0_passed + stage1_passed
        
        print(f"\n📊 阶段0: {stage0_passed}/{stage0_total} 通过 ({stage0_passed/stage0_total*100 if stage0_total > 0 else 0:.1f}%)")
        print(f"📊 阶段1: {stage1_passed}/{stage1_total} 通过 ({stage1_passed/stage1_total*100 if stage1_total > 0 else 0:.1f}%)")
        print(f"\n{'='*80}")
        print(f"✅ 总体通过率: {total_passed}/{total_checks} ({total_passed/total_checks*100 if total_checks > 0 else 0:.1f}%)")
        print(f"{'='*80}")
        
        if total_passed == total_checks:
            print(f"\n🎉 恭喜！第1段所有校验项全部通过！")
        else:
            failed_count = total_checks - total_passed
            print(f"\n⚠️ 发现 {failed_count} 个不一致项，建议进一步检查。")
        
        print(f"\n✅ 第1段校验完成！\n")
        
    except Exception as e:
        print(f"\n❌ 校验过程出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
