#!/bin/bash
# scripts/vault.sh —— 双库(公开代码库 mind + 私有内容库 mind-vault)辅助
#
# 背景:拆库后,个人内容目录(_wiki / material / raw / writing / reports/daily …)
# 是符号链接,真实文件在相邻的 mind-vault 工作树里。个人内容的 git 操作要在那个
# 库里做,而不是在 mind(公开代码库)里。本脚本自动识别"内容库"在哪,单库模式
# (尚未拆分)下自动退回当前库,所以拆分前后都能用。
#
# 用法:
#   scripts/vault.sh repo          打印内容库路径
#   scripts/vault.sh status        内容库 git status
#   scripts/vault.sh commit "msg"  提交内容库全部改动(无改动则跳过)
#   scripts/vault.sh push          推送内容库
#   scripts/vault.sh sync "msg"    commit + push 内容库
set -euo pipefail
VAULT="$(cd "$(dirname "$0")/.." && pwd)"

content_repo() {
  # 个人目录若是软链到另一个 git 库,取那个库;否则(单库模式)取当前库
  if [ -e "$VAULT/_wiki" ] && git -C "$VAULT/_wiki" rev-parse --show-toplevel >/dev/null 2>&1; then
    git -C "$VAULT/_wiki" rev-parse --show-toplevel
  else
    git -C "$VAULT" rev-parse --show-toplevel
  fi
}
REPO="$(content_repo)"

# 写集校验门禁(P1-4):提交前只校验本次变更的 .md(LLM 领地;不扫全库)。
# 红则拦下提交;VAULT_SKIP_VALIDATE=1 单次跳过;缺 python3/校验器时提示并放行。
validate_write_set() {
  [ "${VAULT_SKIP_VALIDATE:-}" = "1" ] && { echo "⚠ VAULT_SKIP_VALIDATE=1,跳过写集校验" >&2; return 0; }
  command -v python3 >/dev/null 2>&1 || { echo "⚠ 未找到 python3,跳过写集校验" >&2; return 0; }
  [ -f "$VAULT/scripts/validate_write_set.py" ] || { echo "⚠ 校验器缺失($VAULT/scripts/validate_write_set.py),跳过写集校验——门禁未生效!" >&2; return 0; }
  if ! python3 "$VAULT/scripts/validate_write_set.py" --vault "$REPO" --git-changed --empty-ok; then
    echo "✗ 写集校验未过,已拦下提交(修好再试,或 VAULT_SKIP_VALIDATE=1 单次跳过)" >&2
    return 1
  fi
}

case "${1:-}" in
  repo)   echo "$REPO" ;;
  status) git -C "$REPO" status ;;
  commit) validate_write_set && git -C "$REPO" add -A && (git -C "$REPO" commit -q -m "${2:-vault: 更新}" && echo "已提交内容库:$REPO" || echo "无改动可提交") ;;
  push)   git -C "$REPO" push ;;
  sync)   validate_write_set && git -C "$REPO" add -A && (git -C "$REPO" commit -q -m "${2:-vault: 更新}" || true) && git -C "$REPO" push && echo "内容库已同步:$REPO" ;;
  *) echo "用法: scripts/vault.sh {repo|status|commit <msg>|push|sync <msg>}"; exit 1 ;;
esac
