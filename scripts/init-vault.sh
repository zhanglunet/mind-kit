#!/usr/bin/env bash
# scripts/init-vault.sh —— 为新机器/新用户初始化**内容库**(mind-vault)并接好双库软链。
#
# 背景:mind 是代码库,个人内容全在相邻的 mind-vault(见 CLAUDE.md「双库布局」)。
# 新克隆 mind 后内容目录并不存在(已 gitignore、软链不入库),本脚本一步建好:
#   1) 在 --vault 处建内容库骨架(_wiki 四子目录 / material 六类 / raw 各桶 /
#      writing / reports 三桶),种 _wiki/index.md、_wiki/log.md、.gitignore,git init;
#   2) 在 --repo 处建软链指向它,使 scripts/vault.sh 能识别为双库模式。
#
# 安全:**绝不覆盖已存在的文件**,**绝不把真实目录换成软链**(遇到就跳过并告警)。
#      幂等——重复跑安全。
#
# 用法:bash scripts/init-vault.sh [--vault <路径>] [--repo <路径>] [--dry-run] [--no-git] [--no-link]
#   --vault    内容库位置(默认:<repo>/../mind-vault)
#   --repo     代码库位置(默认:本脚本所在仓)
#   --dry-run  只打印计划,不落盘
#   --no-git   不在内容库跑 git init
#   --no-link  只建内容库,不建软链
# 退出码:0 成功(含幂等重跑);1 有目标被占用而跳过;2 用法错误。
set -uo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VAULT_DIR=""
DRY=0; DO_GIT=1; DO_LINK=1

while [ $# -gt 0 ]; do
  case "$1" in
    --vault) VAULT_DIR="${2:-}"; shift 2;;
    --repo)  REPO_DIR="${2:-}";  shift 2;;
    --dry-run) DRY=1; shift;;
    --no-git)  DO_GIT=0; shift;;
    --no-link) DO_LINK=0; shift;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) echo "用法:bash scripts/init-vault.sh [--vault <路径>] [--repo <路径>] [--dry-run] [--no-git] [--no-link]" >&2; exit 2;;
  esac
done
[ -n "$VAULT_DIR" ] || VAULT_DIR="$(cd "$REPO_DIR" && pwd)/../mind-vault"

# 内容目录骨架(与 CLAUDE.md 六类素材 / 五维产出布局一致)
DIRS="
_wiki/concepts _wiki/summaries _wiki/entities _wiki/outputs
material/quotes material/stories material/references material/cases material/frameworks material/data
raw/clippings raw/todo raw/archive/clippings raw/flomo/delta raw/pdfs raw/assets
writing reports/daily reports/weekly reports/lint
"
# 需在代码库里建的软链(与 mind/.gitignore 的内容路径清单一一对应)
LINKS="_wiki material raw writing reports/daily reports/weekly reports/lint"

say()  { printf '  %s\n' "$1"; }
step() { printf '\n\033[1m▶ %s\033[0m\n' "$1"; }

if [ "$DRY" = 1 ]; then
  echo "初始化内容库 · 计划(dry-run,不执行):"
  say "代码库:$REPO_DIR"
  say "内容库:$VAULT_DIR"
  say "将建目录:$(echo $DIRS | wc -w) 个(_wiki / material / raw / writing / reports)"
  say "将种文件:_wiki/index.md、_wiki/log.md、.gitignore"
  [ "$DO_GIT" = 1 ]  && say "将在内容库跑 git init" || say "跳过 git init(--no-git)"
  if [ "$DO_LINK" = 1 ]; then say "将建软链:$LINKS"; else say "跳过软链(--no-link)"; fi
  exit 0
fi

skipped=0

step "1/3 建内容库骨架:$VAULT_DIR"
mkdir -p "$VAULT_DIR" || { echo "✗ 无法创建 $VAULT_DIR" >&2; exit 1; }
VAULT_ABS="$(cd "$VAULT_DIR" && pwd)"
for d in $DIRS; do
  mkdir -p "$VAULT_ABS/$d"
  # .gitkeep 让空目录能入库(git 不跟踪空目录)
  [ -e "$VAULT_ABS/$d/.gitkeep" ] || : > "$VAULT_ABS/$d/.gitkeep"
done
say "目录就绪($(echo $DIRS | wc -w) 个)"

# 种子文件:**只在不存在时**写,绝不覆盖用户内容
seed() {
  if [ -e "$1" ]; then say "已存在,保留不动:${1#$VAULT_ABS/}"; else printf '%s' "$2" > "$1"; say "已种:${1#$VAULT_ABS/}"; fi
}
seed "$VAULT_ABS/_wiki/index.md" '# 内容导航 Index

> sage-wiki 每次编译后自动更新本文件。按分类列出所有页面 + 单行摘要 + 来源数量。
> 查询时**先读这里**,再深入相关页面。

## 概念 Concepts

## 摘要 Summaries

## 实体 Entities

## 产出 Outputs
'
seed "$VAULT_ABS/_wiki/log.md" '# 时序日志 Log

> 只追加,记录每次 ingest / query / lint。格式:`## [日期] 类型 ｜ 标题`
'
seed "$VAULT_ABS/.gitignore" '# === 密钥 / 环境变量(绝不入库)===
.env
.env.*
*.key
secrets.*

# === 系统 / 编辑器 ===
.DS_Store
Thumbs.db
*.swp

# === 私密冷存 / 大体积二进制(内容库也不收)===
raw/private
raw/_hoard/
raw/assets/
raw/**/*.pdf
raw/**/*.docx
raw/**/*.xlsx
raw/**/*.pptx
raw/**/*.zip
raw/**/*.png
raw/**/*.jpg
raw/**/*.mp4

# === 引擎中间产物 ===
_wiki/under_review/
.sage/
.manifest.json
'

if [ "$DO_GIT" = 1 ]; then
  if [ -d "$VAULT_ABS/.git" ]; then say "已是 git 库,跳过 init"
  else git -C "$VAULT_ABS" init -q && say "git init 完成(记得建私有远端后 git remote add origin …)"; fi
fi

step "2/3 建双库软链(代码库:$REPO_DIR)"
if [ "$DO_LINK" = 0 ]; then
  say "跳过(--no-link)"
else
  for l in $LINKS; do
    target="$REPO_DIR/$l"
    mkdir -p "$(dirname "$target")"
    if [ -L "$target" ]; then
      say "软链已存在:$l"
    elif [ -e "$target" ]; then
      # 真实文件/目录占位:绝不销毁用户数据
      echo "  ⚠ 已存在真实文件/目录,跳过不动:$l(如确实要接双库,请先自行移走)" >&2
      skipped=$((skipped + 1))
    else
      ln -s "$VAULT_ABS/$l" "$target" && say "软链:$l → $VAULT_ABS/$l"
    fi
  done
fi

step "3/3 校验"
if [ "$DO_LINK" = 1 ] && [ -x "$REPO_DIR/scripts/vault.sh" ] || [ -f "$REPO_DIR/scripts/vault.sh" ]; then
  detected="$(bash "$REPO_DIR/scripts/vault.sh" repo 2>/dev/null || true)"
  if [ -n "$detected" ]; then say "vault.sh 识别到的内容库:$detected"; fi
fi
say "内容库:$VAULT_ABS"

if [ "$skipped" -gt 0 ]; then
  echo ""
  echo "⚠ 完成,但有 $skipped 个软链因目标被占用而跳过(见上)。"
  exit 1
fi
echo ""
echo "✔ 内容库初始化完成。下一步:在 GitHub 建**私有**仓库,然后"
echo "    git -C \"$VAULT_ABS\" remote add origin <你的私有仓地址>"
echo "    bash scripts/vault.sh commit \"init: 内容库骨架\" && bash scripts/vault.sh push"
