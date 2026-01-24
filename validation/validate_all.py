"""
数据校验主入口脚本
一键运行阶段0、阶段1、阶段2、阶段3的全部校验

执行顺序：
1. 阶段0：配置与原始数据校验
2. 阶段1：限额计算核心表校验（单一债券、单一主体、单一实控人）
3. 阶段2：高风险与地域集中度校验
4. 阶段3：可视化看板数据校验
"""
import sys
from pathlib import Path
from datetime import datetime
import json

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from validation.validate_stage0 import validate_stage0_config
from validation.validate_stage1 import validate_stage1_core_tables
from validation.validate_stage2 import validate_stage2_core_tables, validate_stage2_supplementary_tables
from validation.validate_stage3_visualization import validate_all_visualization_pages


class ValidationOrchestrator:
    """校验流程编排器"""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.results = {
            "阶段0": None,
            "阶段1": None,
            "阶段2_核心": None,
            "阶段2_辅助": None,
            "阶段3": None
        }
        self.report_path = project_root / "validation" / "reports" / f"validation_report_{self.start_time.strftime('%Y%m%d_%H%M%S')}.txt"
    
    def print_header(self, title):
        """打印标题"""
        print("\n" + "🎯" * 40)
        print(f" {title}")
        print("🎯" * 40 + "\n")
    
    def run_stage0(self):
        """运行阶段0校验"""
        self.print_header("阶段0：配置与原始数据校验")
        try:
            results = validate_stage0_config()
            self.results["阶段0"] = results
            print("✅ 阶段0校验完成")
            return True
        except Exception as e:
            print(f"❌ 阶段0校验失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run_stage1(self):
        """运行阶段1校验"""
        self.print_header("阶段1：限额计算核心表校验")
        try:
            results = validate_stage1_core_tables()
            self.results["阶段1"] = results
            print("✅ 阶段1校验完成")
            return True
        except Exception as e:
            print(f"❌ 阶段1校验失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run_stage2(self):
        """运行阶段2校验"""
        self.print_header("阶段2：高风险与地域集中度校验")
        try:
            # 核心表
            core_results = validate_stage2_core_tables()
            self.results["阶段2_核心"] = core_results
            
            # 辅助表
            print("\n" + "="*80 + "\n")
            supplementary_results = validate_stage2_supplementary_tables()
            self.results["阶段2_辅助"] = supplementary_results
            
            print("✅ 阶段2校验完成")
            return True
        except Exception as e:
            print(f"❌ 阶段2校验失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run_stage3(self):
        """运行阶段3校验"""
        self.print_header("阶段3：可视化看板数据校验")
        try:
            results = validate_all_visualization_pages()
            self.results["阶段3"] = results
            print("✅ 阶段3校验完成")
            return True
        except Exception as e:
            print(f"❌ 阶段3校验失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def generate_final_report(self):
        """生成最终校验报告"""
        self.print_header("最终校验报告")
        
        end_time = datetime.now()
        duration = end_time - self.start_time
        
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("限额监控系统 - 数据校验报告")
        report_lines.append("=" * 80)
        report_lines.append(f"开始时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append(f"结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append(f"总耗时: {duration.total_seconds():.2f} 秒")
        report_lines.append("=" * 80)
        
        # 统计各阶段情况
        report_lines.append("\n📊 各阶段校验情况：\n")
        
        for stage_name, stage_results in self.results.items():
            if stage_results is None:
                report_lines.append(f"❌ {stage_name}: 未执行")
                continue
            
            if isinstance(stage_results, list) and len(stage_results) > 0:
                total_checks = sum(len(r.get("检查项", [])) for r in stage_results if isinstance(r, dict))
                passed_checks = sum(
                    sum(1 for item in r.get("检查项", []) if item.get("通过", False))
                    for r in stage_results if isinstance(r, dict)
                )
                
                if total_checks > 0:
                    pass_rate = passed_checks / total_checks * 100
                    status = "✅" if pass_rate >= 99 else "⚠️" if pass_rate >= 95 else "❌"
                    report_lines.append(f"{status} {stage_name}: {passed_checks}/{total_checks} ({pass_rate:.1f}%)")
                else:
                    report_lines.append(f"⚠️ {stage_name}: 无检查项")
            else:
                report_lines.append(f"⚠️ {stage_name}: 格式异常")
        
        # 总结建议
        report_lines.append("\n" + "=" * 80)
        report_lines.append("💡 下一步建议：")
        report_lines.append("=" * 80)
        report_lines.append("1. 查看上述各阶段的详细校验结果")
        report_lines.append("2. 对于未通过的检查项，检查数据处理逻辑")
        report_lines.append("3. 手工对比阶段3的可视化截图数据")
        report_lines.append("4. 修复问题后重新运行校验")
        report_lines.append("=" * 80)
        
        # 打印报告
        report_text = "\n".join(report_lines)
        print(report_text)
        
        # 保存报告
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.report_path, 'w', encoding='utf-8') as f:
            f.write(report_text)
        
        print(f"\n📄 报告已保存至: {self.report_path}")


def run_full_validation():
    """运行完整的4阶段校验"""
    orchestrator = ValidationOrchestrator()
    
    print("\n" + "🚀" * 40)
    print(" 限额监控系统 - 全阶段数据校验")
    print("🚀" * 40)
    print(f"\n开始时间: {orchestrator.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("预计耗时: 5-10分钟")
    print("=" * 80 + "\n")
    
    # 执行各阶段校验
    stages = [
        ("阶段0", orchestrator.run_stage0),
        ("阶段1", orchestrator.run_stage1),
        ("阶段2", orchestrator.run_stage2),
        ("阶段3", orchestrator.run_stage3),
    ]
    
    success_count = 0
    for stage_name, stage_func in stages:
        print(f"\n{'='*80}")
        print(f"开始执行: {stage_name}")
        print(f"{'='*80}\n")
        
        if stage_func():
            success_count += 1
        
        print(f"\n✅ {stage_name} 执行完成 ({success_count}/{len(stages)})")
    
    # 生成最终报告
    orchestrator.generate_final_report()
    
    return orchestrator.results


def run_quick_validation():
    """快速校验（仅核心表）"""
    print("\n" + "⚡" * 40)
    print(" 快速校验模式（仅核心表）")
    print("⚡" * 40 + "\n")
    
    orchestrator = ValidationOrchestrator()
    
    # 仅执行核心校验
    orchestrator.run_stage1()
    orchestrator.run_stage2()
    
    orchestrator.generate_final_report()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="限额监控数据校验")
    parser.add_argument(
        "--mode",
        choices=["full", "quick", "stage1", "stage2", "stage3"],
        default="full",
        help="校验模式: full(全部), quick(快速), stage1/2/3(单阶段)"
    )
    
    args = parser.parse_args()
    
    if args.mode == "full":
        run_full_validation()
    elif args.mode == "quick":
        run_quick_validation()
    elif args.mode == "stage1":
        validate_stage1_core_tables()
    elif args.mode == "stage2":
        validate_stage2_core_tables()
        validate_stage2_supplementary_tables()
    elif args.mode == "stage3":
        validate_all_visualization_pages()
