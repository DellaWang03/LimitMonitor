#!/bin/bash
# 兼容入口：已更名为 run_full_integration_test.sh

echo "⚠️  tests/run_golden_test.sh 已更名为 tests/run_full_integration_test.sh"
exec bash "$(cd "$(dirname "$0")" && pwd)/run_full_integration_test.sh" "$@"
