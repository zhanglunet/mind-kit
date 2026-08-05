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

# 前置检查函数可以设 SKIP_WHY 来**自报跳过理由**;不设则回落成「未装 <工具名>」。
# 存在的理由:同一步可能因不同原因跳过,而**理由说错比不说更糟** ——
# 关掉开关却报「未装 pandoc」,会把人支去装一个已经装好的东西(2026-08-04 实测教训)。
SKIP_WHY=""

# 文档站:site/*.html 是提交进仓的生成物(Cloudflare 从 GitHub main 的 site/ 部署 aip.cab)。
# 两台机器 pandoc 版本不同 → 渲染出的 HTML 有差异 → 谁跑谁把代码仓弄脏,git pull 天天被拦。
# 而 VM 上那批 HTML **没有任何消费者**。故给机器级开关:VM 的 crontab 里设 MIND_BUILD_SITE=0。
site_step_ok() {
  if [ "${MIND_BUILD_SITE:-1}" != "1" ]; then
    SKIP_WHY="本机不生成文档站(MIND_BUILD_SITE=${MIND_BUILD_SITE})"
    return 1
  fi
  # 缺 pandoc 不设 SKIP_WHY:回落到既有的「缺/未装 <工具名>」措辞,不动原有提示
  pandoc_ok || return 1
  return 0
}

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
    "文档站|bash scripts/build-site.sh|site_step_ok|pandoc|"
}

if [ "$DRY" = 1 ]; then
  echo "本机全量更新 · 计划(dry-run,不执行):"
  [ "$DO_PULL" = 1 ] && echo "  0. [拉取代码] git pull --ff-only origin main"
  i=0
  while IFS='|' read -r label cmd check tool kind; do
    i=$((i + 1))
    if [ -n "$check" ]; then
      SKIP_WHY=""
      if "$check"; then status="$tool 就绪"
      elif [ "$kind" = "core" ]; then status="**缺核心工具 $tool → 本次将判失败(非零退出)**"
      else status="${SKIP_WHY:-缺 $tool},将跳过"; fi
    else status="就绪"; fi
    printf '  %d. [%s] %s · %s\n' "$i" "$label" "$cmd" "$status"
  done < <(plan_lines)
  [ "$DO_PULL" = 1 ] || echo "(加 --pull 可把「拉取最新代码」列为第 0 步)"
  exit 0
fi

# ── 隐私兜底网的运行时自检(开跑前的硬前置)────────────────────────────
# 2026-08-04 真机事故:VM 上的 .gitignore 被**整个覆盖**,129 行只剩一行 `.sage/`
# (幸存的正是 sage-wiki 自己的缓存目录)。被抹掉的包括密钥形状(.env / *.key /
# secrets.*)、raw/private 冷存层,以及全部个人内容软链 —— CLAUDE.md 里
# 「那些路径在 .gitignore 里,`git add` 会静默什么都不干」那条兜底,当场失效。
#
# 仓库侧已有门禁(tests/test_no_personal_identifiers.py),但它只护得住**仓库里的
# 版本**,护不住**运行中的机器**被第三方工具改写。所以每轮开跑前先问 git 一句。
#
# 两个刻意的边界:
#  · 只问软链。双库布局下 _wiki/material/… 是指向内容库的软链,必须被忽略;
#    单库模式下它们是真目录、本来就该入库,那种仓这里一条都不查。
#  · 问 `git check-ignore`,不读 .gitignore 文本。规则写成什么样不重要,
#    **git 此刻到底忽不忽略**才是事实(顺带覆盖 .git/info/exclude 与全局 excludes)。
SHIELD_LINKS="_wiki material raw writing reports/daily reports/weekly reports/lint"
# 密钥形状用探针路径来问(check-ignore 不要求文件真实存在),被覆盖时一并报出来
SHIELD_SECRETS=".env probe.key probe.pem secrets.json credentials.json"

check_privacy_shield() {
  [ "${MIND_SKIP_SHIELD_CHECK:-}" = "1" ] && return 0
  # 不在 git 工作树里(临时副本、解压出来的一份)就无从问起 —— 静默放行。
  # 把"问不到"当成"破了"会让所有非 git 副本永久红,这条检查很快就被整段注释掉。
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 0

  local naked="" p
  for p in $SHIELD_LINKS; do
    [ -L "$p" ] || continue
    git check-ignore -q "$p" || naked="$naked $p"
  done
  for p in $SHIELD_SECRETS; do
    git check-ignore -q "$p" || naked="$naked $p"
  done
  [ -n "$naked" ] || return 0

  cat >&2 <<EOF

✗ 隐私兜底网破了:git 已**不再忽略**这些路径 —— $naked
  这台机器上的 .gitignore 疑似被覆盖(2026-08-04 VM 上出过一次:129 行只剩 \`.sage/\`)。
  在这种状态下跑编译,任何一次 \`git add -A\` 都会把个人内容/密钥真的加进代码仓,
  所以本轮**开跑前就停住**,不做任何步骤。

  先修再跑:
    git -C "$PWD" checkout -- .gitignore          # 仓库里那份是好的,拿回来
    git -C "$PWD" status --porcelain              # 看有没有个人内容已经被 add 进去
    git -C "$PWD" ls-files | grep -E '^(_wiki|material|raw|writing|reports/(daily|weekly|lint))' # 必须没有输出

  确要跳过(你清楚后果):MIND_SKIP_SHIELD_CHECK=1 bash scripts/update-all.sh
EOF
  return 1
}

check_privacy_shield || exit 3

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
  SKIP_WHY=""
  if [ -n "$check" ] && ! "$check"; then
    if [ "$kind" = "core" ]; then
      # 核心工具缺失绝不算"跳过成功":那样 cron 天天报绿,而 Wiki 悄悄停摆。
      printf '\n✗ [%s] 缺核心工具 %s —— 编译能力缺失,本次判失败\n' "$label" "$tool"
      fails=$((fails + 1))
    else
      printf '\n⚠ [%s] 跳过:%s\n' "$label" "${SKIP_WHY:-未装 $tool}"; skipped=$((skipped + 1))
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
