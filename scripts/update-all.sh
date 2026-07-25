#!/usr/bin/env bash
# scripts/update-all.sh —— 本机「全量更新」一键编排。
# 把散落命令收成一条:日报 → sage-wiki 编译全流水线(compile.sh)→ 订阅台账页 →
# 门户入口页 → 对外文档站。逐步 best-effort:缺工具则跳过(⚠),真跑失败才记 ✗;
# 有 ✗ 时整体非零退出(供 cron/LaunchAgent 日志与门户按钮判断成败)。
# 单一真相:门户「🔄 全量更新」按钮(brain-server /api/update-all)与每日 LaunchAgent
#           (com.mind.update-all.plist)都调本脚本。
#
# 用法:bash scripts/update-all.sh [--pull] [--dry-run]
#   --pull    先 git pull --ff-only origin main 再更新内容(默认不动代码)
#   --dry-run 只打印将执行的计划,不落盘、不执行
# 退出码:0 全部成功/跳过;非零 有步骤真跑失败。
set -uo pipefail
cd "$(dirname "$0")/.."

# launchd/按钮环境 PATH 可能不含 Homebrew(brew shellenv 常在 ~/.zprofile,zsh -c 只 source
# ~/.zshrc 拿不到)——pandoc 等在 /opt/homebrew/bin 下的工具会假"未装"。显式补上,幂等。
# UPDATE_ALL_BREW_BIN 仅供测试把 brew 前缀指到空目录,保持 dry-run 工具判定封闭。
BREW_BIN="${UPDATE_ALL_BREW_BIN:-/opt/homebrew/bin}"
[ -d "$BREW_BIN" ] && export PATH="$BREW_BIN:$PATH"

DO_PULL=0; DRY=0
for a in "$@"; do
  case "$a" in
    --pull) DO_PULL=1;;
    --dry-run) DRY=1;;
    -h|--help) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) echo "用法:bash scripts/update-all.sh [--pull] [--dry-run]" >&2; exit 2;;
  esac
done

step()      { printf '\n\033[1m▶ %s\033[0m\n' "$1"; }
sage_ok()   { command -v sage-wiki >/dev/null 2>&1 || [ -x "$HOME/go/bin/sage-wiki" ]; }
pandoc_ok() { command -v pandoc    >/dev/null 2>&1; }   # brew bin 已在上文补进 PATH,无需 -x 兜底(兜底会绕过 PATH 判定,破坏测试封闭性)

# 计划表:每行「标签|命令|前置检查函数(空=总可跑)|工具名」。dry-run 与真跑共用同一份定义。
# 步序讲究:日报先跑(其产物随后被 compile 的 vault 提交一并收);compile 是核心(编译+
# index+lint+保鲜+决策+浏览站+提交);订阅/门户/文档站在内容更新后再生成快照。
plan_lines() {
  printf '%s\n' \
    "日报|python3 scripts/daily-report.py||"                 \
    "编译·核心|bash scripts/compile.sh|sage_ok|sage-wiki"     \
    "订阅台账|python3 scripts/build-subscriptions-site.py||"  \
    "门户入口|python3 scripts/build-portal.py||"              \
    "文档站|bash scripts/build-site.sh|pandoc_ok|pandoc"
}

if [ "$DRY" = 1 ]; then
  echo "本机全量更新 · 计划(dry-run,不执行):"
  [ "$DO_PULL" = 1 ] && echo "  0. [拉取代码] git pull --ff-only origin main"
  i=0
  while IFS='|' read -r label cmd check tool; do
    i=$((i + 1))
    if [ -n "$check" ]; then
      if "$check"; then status="$tool 就绪"; else status="缺 $tool,将跳过"; fi
    else status="就绪"; fi
    printf '  %d. [%s] %s · %s\n' "$i" "$label" "$cmd" "$status"
  done < <(plan_lines)
  [ "$DO_PULL" = 1 ] || echo "(加 --pull 可把「拉取最新代码」列为第 0 步)"
  exit 0
fi

fails=0; ran=0; skipped=0
if [ "$DO_PULL" = 1 ]; then
  step "拉取最新代码 git pull --ff-only origin main"
  if git pull --ff-only origin main; then ran=$((ran + 1)); else echo "✗ git pull 失败"; fails=$((fails + 1)); fi
fi

while IFS='|' read -r label cmd check tool; do
  if [ -n "$check" ] && ! "$check"; then
    printf '\n⚠ [%s] 跳过:未装 %s\n' "$label" "$tool"; skipped=$((skipped + 1)); continue
  fi
  step "[$label] $cmd"
  if $cmd; then printf '✔ [%s]\n' "$label"; ran=$((ran + 1))
  else rc=$?; printf '✗ [%s](退出码 %d)\n' "$label" "$rc"; fails=$((fails + 1)); fi
done < <(plan_lines)

printf '\n—— 全量更新汇总:成功 %d · 跳过 %d · 失败 %d ——\n' "$ran" "$skipped" "$fails"
if [ "$fails" -eq 0 ]; then echo "✔ 全量更新完成。"; exit 0
else echo "⚠ 有 $fails 步失败,见上。急用可 VAULT_SKIP_VALIDATE=1 单跳写集门禁,或逐步排查。"; exit 1; fi
