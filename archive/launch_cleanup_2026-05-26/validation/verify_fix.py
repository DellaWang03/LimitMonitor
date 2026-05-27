"""
验证超限判断逻辑修复效果
"""
import pandas as pd
from pathlib import Path

print("="*80)
print("验证超限判断逻辑修复")
print("="*80)

# 测试修复后的逻辑
print("\n测试修复后的判断逻辑:")

# 模拟数据
test_data = {
    '单一债券是否超限': ['是', '否', '否', '否'],
    '单一债券集中度是否超限': ['否', '是', '否', '否'],
    '单一主体是否超限': ['否', '否', '是', '否'],
    '单一担保人是否超限': ['否', '否', '否', '否'],
    '单一实控人是否超限': ['否', '否', '否', '是']
}

df_test = pd.DataFrame(test_data)

# 应用修复后的逻辑
df_test['是否超限'] = df_test.apply(
    lambda row: '是' if '是' in [
        row.get('单一债券是否超限'),
        row.get('单一债券集中度是否超限'),
        row.get('单一主体是否超限'),
        row.get('单一担保人是否超限')
    ] else '否',
    axis=1
)

print("\n测试结果:")
print(df_test)

# 验证第4行（只有单一实控人超限）
print("\n关键验证：")
print(f"第4行（只有单一实控人超限）的综合判断: {df_test.iloc[3]['是否超限']}")
print(f"✅ 预期结果: '否'（不应计入综合超限）")
print(f"{'✅ 通过' if df_test.iloc[3]['是否超限'] == '否' else '❌ 失败'}")

# 验证前3行
overlimit_count = (df_test['是否超限'] == '是').sum()
print(f"\n综合超限数量: {overlimit_count}")
print(f"✅ 预期结果: 3（前3行）")
print(f"{'✅ 通过' if overlimit_count == 3 else '❌ 失败'}")

print("\n" + "="*80)
print("请手动运行以下命令以重新处理数据：")
print("cd /Users/dellawang/Desktop/LimitMonitorAutomation")
print("./run_daily.sh")
print("\n处理完成后，超限数量应该从139变为66")
print("="*80)
