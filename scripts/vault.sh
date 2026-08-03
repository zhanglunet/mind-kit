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

# 解释器解析:系统 python3 可能是 EOL 的 3.6(真机实测),写集校验器用了 3.7+ 的 API。
. "$VAULT/scripts/_pyresolve.sh"
MIND_PY="$(mind_python "$VAULT")"

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
# 红则拦下提交;VAULT_SKIP_VALIDATE=1 单次跳过;缺解释器/校验器时提示并放行。
validate_write_set() {
  [ "${VAULT_SKIP_VALIDATE:-}" = "1" ] && { echo "⚠ VAULT_SKIP_VALIDATE=1,跳过写集校验" >&2; return 0; }
  command -v "$MIND_PY" >/dev/null 2>&1 || { echo "⚠ 未找到 Python($MIND_PY),跳过写集校验" >&2; return 0; }
  [ -f "$VAULT/scripts/validate_write_set.py" ] || { echo "⚠ 校验器缺失($VAULT/scripts/validate_write_set.py),跳过写集校验——门禁未生效!" >&2; return 0; }
  if ! "$MIND_PY" "$VAULT/scripts/validate_write_set.py" --vault "$REPO" --git-changed --empty-ok; then
    echo "✗ 写集校验未过,已拦下提交(修好再试,或 VAULT_SKIP_VALIDATE=1 单次跳过)" >&2
    return 1
  fi
}

# 提交:必须把「没东西要提交」和「提交失败了」分开。
#
# `git commit` 这两种情况都返回非零,所以老写法 `commit || echo "无改动可提交"`
# 会把**一切**失败都吞成那一句、还退 0:真机上没配 git 身份,提交每天失败、
# 每天报「无改动」,compile.sh 与 update-all 于是一路报绿,而内容库永远不同步。
# 先用 `diff --cached --quiet` 判断暂存区空不空,再决定这次非零是哪一种。
do_commit() {
  git -C "$REPO" add -A || { echo "✗ git add 失败" >&2; return 1; }
  if git -C "$REPO" diff --cached --quiet; then
    echo "无改动可提交"
    return 0
  fi
  if git -C "$REPO" commit -q -m "$1"; then
    echo "已提交内容库:$REPO"
    return 0
  fi
  echo "✗ 提交失败(改动仍在暂存区,没有丢)。常见原因:未配 git 身份 ——" >&2
  echo "    git -C \"$REPO\" config user.name  \"你的名字\"" >&2
  echo "    git -C \"$REPO\" config user.email \"你的邮箱\"" >&2
  return 1
}

case "${1:-}" in
  repo)   echo "$REPO" ;;
  status) git -C "$REPO" status ;;
  commit) validate_write_set && do_commit "${2:-vault: 更新}" ;;
  push)   git -C "$REPO" push ;;
  sync)   validate_write_set && do_commit "${2:-vault: 更新}" && git -C "$REPO" push && echo "内容库已同步:$REPO" ;;
  *) echo "用法: scripts/vault.sh {repo|status|commit <msg>|push|sync <msg>}"; exit 1 ;;
esac
