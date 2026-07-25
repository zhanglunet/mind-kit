#!/usr/bin/env bash
# 启用本仓 git 钩子:把 core.hooksPath 指向版本化的 .githooks/。
# 之后每次 git push 前会自动跑 pytest(见 .githooks/pre-push)。
# 幂等,每个克隆装一次。临时跳过单次:git push --no-verify
set -euo pipefail

root=$(git rev-parse --show-toplevel 2>/dev/null) || {
  echo "✗ 请在 git 仓库内运行本脚本(未检测到 git 仓库)。" >&2
  exit 1
}
cd "$root"
git config core.hooksPath .githooks
chmod +x .githooks/* 2>/dev/null || true

echo "✅ 已启用 git 钩子(core.hooksPath → .githooks)。"
echo "   pre-push 会在每次 push 前跑 pytest;临时跳过:git push --no-verify"
