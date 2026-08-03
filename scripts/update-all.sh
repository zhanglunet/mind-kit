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

# 解释器解析:系统 python3 可能是 EOL 的 3.6(真机实测),依赖在 .venv 里。
. "$(dirname "${BASH_SOURCE[0]}")/_pyresolve.sh"
MIND_PY="$(mind_python "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)")"

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

# 内容库(拆库后是相邻的 mind-vault)。编译产物落在那里,所以两端同步必须成对:
# **编译前拉**,否则像 2026-07-29 真机那样一直在旧基线上编译、产物和远端对不上;
# **编译后推**,否则提交只堆在本地,笔记本永远看不到。
# 单库模式下 vault.sh repo 打印的就是本仓,拉推同样成立。
vault_repo() { bash scripts/vault.sh repo 2>/dev/null; }

vault_pull() {
  local repo; repo="$(vault_repo)"
  [ -n "$repo" ] || { echo "✗ 定位不到内容库(vault.sh repo 无输出)" >&2; return 1; }
  git -C "$repo" remote get-url origin >/dev/null 2>&1 || {
    echo "✗ 内容库没有 origin 远端:$repo" >&2; return 1; }
  # --ff-only:本地若有未推的提交就**停下来**,而不是悄悄 rebase 生成物。
  git -C "$repo" pull --ff-only
}

vault_push() {
  local repo; repo="$(vault_repo)"
  [ -n "$repo" ] || { echo "✗ 定位不到内容库" >&2; return 1; }
  git -C "$repo" push
}
sage_ok()   { command -v sage-wiki >/dev/null 2>&1 || [ -x "$HOME/go/bin/sage-wiki" ]; }
pandoc_ok() { command -v pandoc    >/dev/null 2>&1; }   # brew bin 已在上文补进 PATH,无需 -x 兜底(兜底会绕过 PATH 判定,破坏测试封闭性)

# 计划表:每行「标签|命令|前置检查函数(空=总可跑)|工具名」。dry-run 与真跑共用同一份定义。
# 步序讲究:日报先跑(其产物随后被 compile 的 vault 提交一并收);compile 是核心(编译+
# index+lint+保鲜+决策+浏览站+提交);订阅/门户/文档站在内容更新后再生成快照。
plan_lines() {
  printf '%s\n' \
    "拉取内容库·核心|vault_pull|||core"                           \
    "日报|"$MIND_PY" scripts/daily-report.py|||"                  \
    "编译·核心|bash scripts/compile.sh|sage_ok|sage-wiki|core" \
    "推送内容库·核心|vault_push|||core"                           \
    "订阅台账|"$MIND_PY" scripts/build-subscriptions-site.py|||"  \
    "门户入口|"$MIND_PY" scripts/build-portal.py|||"              \
    "文档站|bash scripts/build-site.sh|pandoc_ok|pandoc|"
}

if [ "$DRY" = 1 ]; then
  echo "本机全量更新 · 计划(dry-run,不执行):"
  [ "$DO_PULL" = 1 ] && echo "  0. [拉取代码] git pull --ff-only origin main"
  i=0
  while IFS='|' read -r label cmd check tool kind; do
    i=$((i + 1))
    if [ -n "$check" ]; then
      if "$check"; then status="$tool 就绪"
      elif [ "$kind" = "core" ]; then status="**缺核心工具 $tool → 本次将判失败(非零退出)**"
      else status="缺 $tool,将跳过"; fi
    else status="就绪"; fi
    printf '  %d. [%s] %s · %s\n' "$i" "$label" "$cmd" "$status"
  done < <(plan_lines)
  [ "$DO_PULL" = 1 ] || echo "(加 --pull 可把「拉取最新代码」列为第 0 步)"
  exit 0
fi

# 跨进程互斥:门户按钮(brain-server)、飞书机器人、cron 三条路都会跑本脚本,
# 约定同一把锁。**dry-run 在上面已提前 exit,不受此锁影响。**
# 锁冲突退 0 而非非零:手点一次编译不该让 cron 每天发一封失败邮件。
#
# flock(1) 是 util-linux 专有,**macOS 没有**。原先无 flock 就只打一句警告然后
# 照常往下跑 —— 也就是说用户笔记本(门户按钮 + 飞书机器人 + 每日定时三条路都在用)
# 上这把锁从来不存在。故补一条 mkdir 兜底:mkdir 的原子性是 POSIX 保证的。
LOCKDIR=".update-all.lock.d"

holder_alive() {   # $1=pid;拿不到权限也算活着(EPERM≠不存在)
  [ -n "${1:-}" ] || return 1
  local err
  err="$(kill -0 "$1" 2>&1)" && return 0
  printf '%s' "$err" | grep -qi 'permitted'
}

take_lock_portable() {
  if mkdir "$LOCKDIR" 2>/dev/null; then
    echo $$ > "$LOCKDIR/pid"
    trap 'rm -rf "$LOCKDIR"' EXIT
    return 0
  fi
  local pid; pid="$(cat "$LOCKDIR/pid" 2>/dev/null || true)"
  if holder_alive "$pid"; then
    return 1
  fi
  # 持有者已经死了(机器崩过、进程被 kill -9):清掉陈旧锁,否则永久卡死
  echo "⚠ 清理陈旧锁(持有者 PID ${pid:-未知} 已不存在)"
  rm -rf "$LOCKDIR"
  mkdir "$LOCKDIR" 2>/dev/null || return 1
  echo $$ > "$LOCKDIR/pid"
  trap 'rm -rf "$LOCKDIR"' EXIT
}

locked=0
if command -v flock >/dev/null 2>&1; then
  exec 9>".update-all.lock"
  flock -n 9 && locked=1
else
  take_lock_portable && locked=1
fi
if [ "$locked" != 1 ]; then
  echo "⚠ 已有一轮全量更新在跑(门户按钮 / 机器人 / 定时任务),本次退出不重入。"
  exit 0
fi

fails=0; ran=0; skipped=0
if [ "$DO_PULL" = 1 ]; then
  step "拉取最新代码 git pull --ff-only origin main"
  if git pull --ff-only origin main; then ran=$((ran + 1)); else echo "✗ git pull 失败"; fails=$((fails + 1)); fi
fi

while IFS='|' read -r label cmd check tool kind; do
  if [ -n "$check" ] && ! "$check"; then
    if [ "$kind" = "core" ]; then
      # 核心工具缺失绝不算"跳过成功":那样 cron 天天报绿,而 Wiki 悄悄停摆。
      printf '\n✗ [%s] 缺核心工具 %s —— 编译能力缺失,本次判失败\n' "$label" "$tool"
      fails=$((fails + 1))
    else
      printf '\n⚠ [%s] 跳过:未装 %s\n' "$label" "$tool"; skipped=$((skipped + 1))
    fi
    continue
  fi
  step "[$label] $cmd"
  if $cmd; then printf '✔ [%s]\n' "$label"; ran=$((ran + 1))
  else rc=$?; printf '✗ [%s](退出码 %d)\n' "$label" "$rc"; fails=$((fails + 1)); fi
done < <(plan_lines)

printf '\n—— 全量更新汇总:成功 %d · 跳过 %d · 失败 %d ——\n' "$ran" "$skipped" "$fails"
if [ "$fails" -eq 0 ]; then echo "✔ 全量更新完成。"; exit 0
else echo "⚠ 有 $fails 步失败,见上。急用可 VAULT_SKIP_VALIDATE=1 单跳写集门禁,或逐步排查。"; exit 1; fi
