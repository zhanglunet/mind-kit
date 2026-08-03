#!/usr/bin/env bash
# scripts/sage-backend.sh —— 切换 sage-wiki 编译后端。
#
# 背景:sage-wiki 当前 dev build 的 --config flag 未接线(传参无效,永远读
# <project>/config.yaml),所以切后端只能替换 config.yaml 本身。本脚本把选定的
# profile(config.<name>.yaml)复制成活动的 config.yaml。
#
# 用法:
#   bash scripts/sage-backend.sh <name>   # 切到 config.<name>.yaml 那个后端
#   bash scripts/sage-backend.sh          # 显示当前活动后端 + 可用清单
# 可用后端 = 仓库根实际存在的 config.*.yaml,不维护硬编码清单。
#
# 切换后跑 `sage-wiki doctor` 确认连通性与模型。
# 提示:各后端的密钥都在 shell profile(见对应 profile 里的 ${...} 变量名),
#       **不入库**;config.*.yaml 里只写 ${ENV_VAR}。

set -euo pipefail
cd "$(dirname "$0")/.."

active="config.yaml"

# 可用后端 = 磁盘上实际存在的 profile。**不维护硬编码清单**:
# 之前 case 分支、用法提示、current() 三处各写一份,加一个后端要改三处,
# 漏掉任何一处都是"切过去了但认不出来"这种半生效状态。
available() {
  for f in config.*.yaml; do
    [ -e "$f" ] || continue
    n="${f#config.}"; n="${n%.yaml}"
    printf '%s\n' "$n"
  done
}

# 当前后端 = 活动 config 与哪个 profile 的 base_url 一致。
# 比匹配域名字面值稳:换端点时不必再回来改这里。
current() {
  cur_url=$(grep -E '^\s*base_url:' "$active" 2>/dev/null | head -1 | sed 's/#.*//' | tr -d ' ')
  [ -n "$cur_url" ] || { echo "unknown"; return; }
  for n in $(available); do
    p_url=$(grep -E '^\s*base_url:' "config.$n.yaml" 2>/dev/null | head -1 | sed 's/#.*//' | tr -d ' ')
    if [ "$cur_url" = "$p_url" ]; then echo "$n"; return; fi
  done
  echo "unknown"
}

list() { available | tr '\n' ' ' | sed 's/ $//'; }

case "${1:-}" in
  ""|status|-h|--help)
    echo "当前活动后端:$(current)  (config.yaml)"
    echo "可用:$(list)。用法:bash scripts/sage-backend.sh [$(available | tr '\n' '|' | sed 's/|$//')]"
    ;;
  *)
    profile="config.$1.yaml"
    if [ ! -f "$profile" ]; then
      echo "❌ 未知参数:$1(可用:$(list))" >&2; exit 1
    fi
    cp "$profile" "$active"
    echo "✅ 已切到 $1 后端(config.yaml ← $profile)"
    echo "   跑 sage-wiki doctor 确认;或 sage-wiki compile 编译。"
    ;;
esac
