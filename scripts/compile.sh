#!/usr/bin/env bash
# scripts/compile.sh —— sage-wiki 编译全流水线。
# 弥补 dev build 缺的"编译后自动动作"(PRD FR-CMP-06 / 开发计划 G1+G2):
#   1) sage-wiki compile(引擎自身会 auto_commit 编译产物)
#   2) 重建 _wiki/index.md(sage-wiki 不维护,见 build-index.py)
#   3) sage-wiki lint(dev build 的 auto_lint 不触发,这里手动跑并记账)
#   4) 生成本地浏览站 browse/wiki/(build-wiki-site.py;含关系图,best-effort,gitignore 不入库)
#   5) 提交编译后产物(index / lint 报告)
# 注:不做 auto-archive —— sage-wiki 靠 manifest hash 增量,归档已编译剪藏反而制造幻影 "removed"(G8)。
#
# 用法:bash scripts/compile.sh [compile 参数,如 --fresh / --dry-run]
# 后端由活动的 config.yaml 决定(切换见 scripts/sage-backend.sh)。

set -uo pipefail
cd "$(dirname "$0")/.."
export PATH="/opt/homebrew/bin:$HOME/go/bin:$PATH"
source ~/.zshrc 2>/dev/null || true

step() { printf '\n\033[1m▶ %s\033[0m\n' "$1"; }
today=$(date +%F)

step "1/5 sage-wiki compile $*"
if ! sage-wiki compile "$@"; then echo "❌ 编译失败,中止流水线"; exit 1; fi

# --dry-run 时不做后续写操作
case " $* " in *" --dry-run "*) echo "(dry-run:跳过 index/lint/归档/提交)"; exit 0;; esac

step "2/5 重建 index.md"
python3 scripts/build-index.py

step "3/5 sage-wiki lint(记账)"
mkdir -p reports/lint
lintfile="reports/lint/${today}.txt"
sage-wiki lint 2>&1 | grep -vE "^time=.*(embedding|no embedding)" | tee "$lintfile"
findings=$(grep -oE '[0-9]+ findings' "$lintfile" | tail -1 | grep -oE '^[0-9]+')
printf '## [%s] lint ｜ %s findings(见 reports/lint/%s.txt)\n' "$today" "${findings:-?}" "$today" >> _wiki/log.md
# 保鲜检查(P1-3)与决策队列不变量(P1-2):best-effort 追加进同一份 lint 报告,失败不中断流水线
{ echo ""; python3 scripts/freshness.py; } >> "$lintfile" 2>&1 || true
python3 scripts/decision.py check >> "$lintfile" 2>&1 || echo "⚠️ 决策队列不变量有违规,见 $lintfile"

# 注:不再自动 archive。sage-wiki 靠 manifest hash 增量,已编译剪藏留在 clippings 不会重编;
# 把它们移入 raw/archive 反而让引擎永久标记为 "removed"(见开发计划 G8)。auto-archive.sh 保留备用。

step "4/5 生成本地浏览站(browse/wiki/,含关系图)"
# best-effort:浏览站是本地便利产物(gitignore),生成失败不该中断编译/提交
python3 scripts/build-wiki-site.py || echo "⚠️ 浏览站生成失败(通常是缺依赖:pip install markdown);不影响编译产物,继续"

step "5/5 提交编译后产物"
# 经 vault.sh 提交:单库时落当前库;拆库后 index / log / lint 都在个人内容里(软链),自动落 mind-vault。
# 写集校验拦下时必须显式失败(评审 F4:静默打"完成"会让产物停止入库而无人知晓)
if ! bash scripts/vault.sh commit "post-compile: index 重建 + lint 记账 (${today})"; then
  echo "❌ 收尾提交被写集校验拦下:修复报告所列页面后重跑,或 VAULT_SKIP_VALIDATE=1 单次跳过"
  exit 1
fi
echo "✔ 流水线完成。"
