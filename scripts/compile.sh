#!/usr/bin/env bash
# scripts/compile.sh —— sage-wiki 编译全流水线。
# 弥补 dev build 缺的"编译后自动动作"(PRD FR-CMP-06 / 开发计划 G1+G2):
#   1) sage-wiki compile(引擎自身会 auto_commit 编译产物)
#   2) OKF 合规注入(okf.py --fix;引擎写完就补齐 type/stale_after,必须早于建索引)
#   3) 重建 _wiki/index.md(sage-wiki 不维护,见 build-index.py)
#   4) sage-wiki lint(dev build 的 auto_lint 不触发,这里手动跑并记账)
#   5) 生成本地浏览站 browse/wiki/(build-wiki-site.py;含关系图,best-effort,gitignore 不入库)
#   6) 提交编译后产物(index / lint 报告)
# 注:不做 auto-archive —— sage-wiki 靠 manifest hash 增量,归档已编译剪藏反而制造幻影 "removed"(G8)。
#
# 用法:bash scripts/compile.sh [compile 参数,如 --fresh / --dry-run]
# 后端由活动的 config.yaml 决定(切换见 scripts/sage-backend.sh)。

set -uo pipefail

# 解释器解析:系统 python3 可能是 EOL 的 3.6(真机实测),依赖在 .venv 里。
. "$(dirname "${BASH_SOURCE[0]}")/_pyresolve.sh"
MIND_PY="$(mind_python "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)")"

cd "$(dirname "$0")/.."
export PATH="/opt/homebrew/bin:$HOME/go/bin:$PATH"
source ~/.zshrc 2>/dev/null || true

step() { printf '\n\033[1m▶ %s\033[0m\n' "$1"; }
today=$(date +%F)

step "1/6 sage-wiki compile $*"
if ! sage-wiki compile "$@"; then echo "❌ 编译失败,中止流水线"; exit 1; fi

# --dry-run 时不做后续写操作
case " $* " in *" --dry-run "*) echo "(dry-run:跳过 OKF/index/lint/归档/提交)"; exit 0;; esac

step "2/6 OKF 合规注入(type / stale_after)"
# 必须早于建索引:index.md 由 build-index.py 读 frontmatter 生成,注入若发生在它之后,
# 索引拿到的是上一轮的旧字段。引擎重写页面会抹掉注入的键 —— 下一轮这一步自愈,幂等。
"$MIND_PY" scripts/okf.py --fix || echo "⚠️ OKF 注入失败,继续流水线(第 4 步的体检会记账)"

step "3/6 重建 index.md"
"$MIND_PY" scripts/build-index.py

step "4/6 sage-wiki lint(记账)"
mkdir -p reports/lint
lintfile="reports/lint/${today}.txt"
sage-wiki lint 2>&1 | grep -vE "^time=.*(embedding|no embedding)" | tee "$lintfile"
findings=$(grep -oE '[0-9]+ findings' "$lintfile" | tail -1 | grep -oE '^[0-9]+')
printf '## [%s] lint ｜ %s findings(见 reports/lint/%s.txt)\n' "$today" "${findings:-?}" "$today" >> _wiki/log.md
# 保鲜检查(P1-3)与决策队列不变量(P1-2):best-effort 追加进同一份 lint 报告,失败不中断流水线
{ echo ""; "$MIND_PY" scripts/freshness.py; } >> "$lintfile" 2>&1 || true
"$MIND_PY" scripts/decision.py check >> "$lintfile" 2>&1 || echo "⚠️ 决策队列不变量有违规,见 $lintfile"
# OKF 合规体检(只读):上一步注入完还剩的不合规页,记进 lint 报告
"$MIND_PY" scripts/okf.py --check >> "$lintfile" 2>&1 || echo "⚠️ OKF 合规体检有待补页,见 $lintfile"

# 注:不再自动 archive。sage-wiki 靠 manifest hash 增量,已编译剪藏留在 clippings 不会重编;
# 把它们移入 raw/archive 反而让引擎永久标记为 "removed"(见开发计划 G8)。auto-archive.sh 保留备用。

step "5/6 生成本地浏览站(browse/wiki/,含关系图)"
# best-effort:浏览站是本地便利产物(gitignore),生成失败不该中断编译/提交
"$MIND_PY" scripts/build-wiki-site.py || echo "⚠️ 浏览站生成失败(通常是缺依赖:pip install markdown);不影响编译产物,继续"

step "6/6 提交编译后产物"
# 经 vault.sh 提交:单库时落当前库;拆库后 index / log / lint 都在个人内容里(软链),自动落 mind-vault。
# 写集校验拦下时必须显式失败(评审 F4:静默打"完成"会让产物停止入库而无人知晓)
if ! bash scripts/vault.sh commit "post-compile: index 重建 + lint 记账 (${today})"; then
  echo "❌ 收尾提交被写集校验拦下:修复报告所列页面后重跑,或 VAULT_SKIP_VALIDATE=1 单次跳过"
  exit 1
fi
echo "✔ 流水线完成。"
