#!/usr/bin/env bash
# scripts/sage-backend.sh —— 切换 sage-wiki 编译后端(GLM ⇄ Kimi)。
#
# 背景:sage-wiki 当前 dev build 的 --config flag 未接线(传参无效,永远读
# <project>/config.yaml),所以切后端只能替换 config.yaml 本身。本脚本把选定的
# profile(config.glm.yaml / config.kimi.yaml)复制成活动的 config.yaml。
#
# 用法:
#   bash scripts/sage-backend.sh kimi     # 切到 Kimi Coding
#   bash scripts/sage-backend.sh glm      # 切回 GLM
#   bash scripts/sage-backend.sh          # 显示当前活动后端
#
# 切换后可跑 `sage-wiki doctor` 确认 connectivity 报的模型。
# 提示:两个后端的密钥都在 ~/.zshrc(GLM_API_KEY / KIMI_API_KEY),不入库。

set -euo pipefail
cd "$(dirname "$0")/.."

active="config.yaml"

current() {
  if grep -q "api.kimi.com" "$active" 2>/dev/null; then echo "kimi";
  elif grep -q "bigmodel.cn" "$active" 2>/dev/null; then echo "glm";
  else echo "unknown"; fi
}

case "${1:-}" in
  kimi|glm)
    profile="config.$1.yaml"
    [ -f "$profile" ] || { echo "❌ 缺 profile:$profile" >&2; exit 1; }
    cp "$profile" "$active"
    echo "✅ 已切到 $1 后端(config.yaml ← $profile)"
    echo "   跑 sage-wiki doctor 确认;或 sage-wiki compile 编译。"
    ;;
  ""|status|-h|--help)
    echo "当前活动后端:$(current)  (config.yaml)"
    echo "可用:kimi / glm。用法:bash scripts/sage-backend.sh [kimi|glm]"
    ;;
  *)
    echo "❌ 未知参数:$1(可用:kimi / glm)" >&2; exit 1 ;;
esac
