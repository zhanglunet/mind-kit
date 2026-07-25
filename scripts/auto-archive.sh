#!/bin/bash
# scripts/auto-archive.sh —— 在 sage-wiki compile 完成后运行
# 作用:把 clippings/ 中已被编译过的文件移入 archive/,避免重复编译。
#
# 判据(以 git 快照为准,不依赖 mtime——同步盘/备份恢复会保留旧 mtime,
# mtime 并不能证明文件被编译过):一个剪藏文件可归档,当且仅当
#   ① 它已存在于"最近一次编译产物 commit"的 git 快照中(编译时它已入库),且
#   ② 自那次 commit 以来内容无任何改动(含未提交的修改)。
# 未入库(untracked)或其后有改动的文件一律保留,等待下次 compile + commit。
#
# 前提:开启 auto_commit(或每周手动 commit),使编译后的库状态进入 git 历史。
# 已知限制:文件名含换行符时无法正确处理(剪藏标题不会产生换行,可接受)。
set -euo pipefail
export LC_ALL=C

VAULT="$(cd "$(dirname "$0")/.." && pwd)"
CLIP_REL="raw/clippings"
CLIPPINGS="$VAULT/$CLIP_REL"
ARCHIVE="$VAULT/raw/archive/clippings"

[ -d "$CLIPPINGS" ] || { echo "错误:目录不存在:$CLIPPINGS" >&2; exit 1; }
git -C "$VAULT" rev-parse --git-dir >/dev/null  # 非 git 仓库时在此报错退出
mkdir -p "$ARCHIVE"

# 最近一次"编译产物 commit":只认编译引擎全权管辖目录下 .md 的提交,
# 不受手工提交 outputs/、log.md 追加或 .gitkeep 骨架提交的干扰。
# 注意 stderr 不并入变量(fresh repo 的 fatal 与各类 warning 都不能进值)。
COMPILE_COMMIT=$(git -C "$VAULT" log -1 --format=%H -- \
  '_wiki/summaries/*.md' '_wiki/concepts/*.md' '_wiki/entities/*.md' 2>/dev/null || true)
if [ -z "$COMPILE_COMMIT" ]; then
  echo "尚无编译产物的 commit 记录,跳过存档。"
  echo "(首次使用请先 compile 并 commit;若确认编译过,请核对 _wiki 产物路径与本脚本 pathspec 是否一致)"
  exit 0
fi

# 可归档清单 = 编译 commit 快照中的 .md 文件 − 自该 commit 以来有改动的文件。
# core.quotepath=false 让中文文件名按原样输出;comm 要求两侧同序(LC_ALL=C)。
ELIGIBLE=$(comm -23 \
  <(git -C "$VAULT" -c core.quotepath=false ls-tree -r --name-only "$COMPILE_COMMIT" -- "$CLIP_REL" | grep '\.md$' | sort || true) \
  <(git -C "$VAULT" -c core.quotepath=false diff --name-only "$COMPILE_COMMIT" -- "$CLIP_REL" | sort || true))

archived=0
while IFS= read -r p; do
  [ -n "$p" ] || continue
  f="$VAULT/$p"
  [ -f "$f" ] || continue            # 快照中有、工作区已不存在(已手工处理)
  REL="${p#"$CLIP_REL"/}"
  DEST="$ARCHIVE/$REL"
  if [ -e "$DEST" ]; then
    DEST="${DEST%.md}-$(date +%s).md"  # 同名归档已存在时换名,绝不覆盖
  fi
  mkdir -p "${DEST%/*}"
  mv "$f" "$DEST"
  echo "已存档:$REL"
  archived=$((archived + 1))
done <<< "$ELIGIBLE"

remaining=$(find "$CLIPPINGS" -type f -name '*.md' | wc -l | tr -d ' ')
echo "存档完成:归档 $archived 个;clippings 剩余 $remaining 个(未入库或编译后有改动,待下次编译)。"
