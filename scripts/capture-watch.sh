#!/usr/bin/env bash
# scripts/capture-watch.sh —— 投递目录监听:把"随手丢进来的文件"搬进 raw/clippings/。
#
# 静默采集三件套之一(另见 scripts/capture-clipboard.py 与
# docs/guide/capture-hooks.md)。解决"采集"的第一公里:用户不再需要记住
# raw/clippings/ 这个路径,只要把文件丢进投递目录(默认 ~/mind-inbox),
# 本脚本负责搬运、改名、去重。
#
# 后端优先级: fswatch (macOS) > inotifywait (Linux) > 轮询兜底(全平台)。
# 轮询兜底无外部依赖,Windows Git Bash / PowerShell 下也能跑。
#
# 用法:
#   bash scripts/capture-watch.sh [--once] [--interval N]
#     --once        只扫一轮(供 cron / LaunchAgent / 计划任务调用),然后退出
#     --interval N  轮询间隔秒数(默认 5),仅轮询兜底时有效
#
# 投递目录决定顺序: $MIND_INBOX > <vault>/.mind-inbox 文件首行 > ~/mind-inbox
# 只搬运 *.md *.markdown *.txt *.html;跳过临时文件(.part/.crdownload/~ 结尾、
# 点开头)。搬运是"移动"不是复制:投递目录保持干净,下次不重复处理。
# 目标文件名: <时间戳>-<清洗后的原名>,清洗规则见 sanitize();重名自动加 -2/-3。
set -uo pipefail

VAULT="$(cd "$(dirname "$0")/.." && pwd)"
CLIPPINGS="$VAULT/raw/clippings"

resolve_inbox() {
  if [ -n "${MIND_INBOX:-}" ]; then echo "$MIND_INBOX"; return; fi
  if [ -f "$VAULT/.mind-inbox" ]; then head -n1 "$VAULT/.mind-inbox" | sed 's/[[:space:]]*$//'; return; fi
  echo "$HOME/mind-inbox"
}

sanitize() {
  # 文件名清洗:空格转 -,去掉除 [A-Za-z0-9._- + CJK] 外的字符,防路径穿越
  local n
  n="$(basename "$1")"
  n="${n// /-}"
  n="$(printf '%s' "$n" | sed 's#[^A-Za-z0-9._\-\x80-\xff]#_#g')"
  n="$(printf '%s' "$n" | sed 's#^\.*##;s#/\.\.#_#g')"
  [ -n "$n" ] || n="untitled"
  printf '%s' "$n"
}

is_temp() {
  case "$(basename "$1")" in
    .*|*.part|*.crdownload|*.tmp|*~|*.swp|*.swo) return 0;;
  esac
  return 1
}

is_wanted() {
  case "$1" in
    *.md|*.markdown|*.txt|*.html|*.htm) return 0;;
  esac
  return 1
}

sweep_once() {
  local inbox="$1" moved=0 f base stamp dest n
  [ -d "$inbox" ] || { echo "投递目录不存在,已创建: $inbox"; mkdir -p "$inbox"; return 0; }
  mkdir -p "$CLIPPINGS"
  for f in "$inbox"/*; do
    [ -e "$f" ] || continue
    [ -f "$f" ] || continue
    is_temp "$f" && continue
    is_wanted "$f" || continue
    base="$(sanitize "$f")"
    stamp="$(date +%Y-%m-%d-%H%M%S)"
    dest="$CLIPPINGS/${stamp}-${base}"
    n=2
    while [ -e "$dest" ]; do dest="$CLIPPINGS/${stamp}-${n}-${base}"; n=$((n+1)); done
    # 仍在写入中的文件(1 秒内还在变大)跳过,等下一轮
    s1=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f" 2>/dev/null || echo 0)
    sleep 1
    s2=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f" 2>/dev/null || echo 0)
    if [ "$s1" != "$s2" ]; then echo "跳过(仍在写入): $(basename "$f")"; continue; fi
    mv -- "$f" "$dest"
    echo "已搬运: $(basename "$f") -> raw/clippings/$(basename "$dest")"
    moved=$((moved+1))
  done
  [ "$moved" -gt 0 ] || echo "本轮无新文件。"
}

ONCE=0; INTERVAL=5
for a in "$@"; do
  case "$a" in
    --once) ONCE=1;;
    --interval=*) INTERVAL="${a#--interval=}";;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) echo "未知参数: $a" >&2; exit 2;;
  esac
done

INBOX="$(resolve_inbox)"
echo "投递目录: $INBOX"

if [ "$ONCE" -eq 1 ]; then sweep_once "$INBOX"; exit 0; fi

mkdir -p "$INBOX"
if command -v fswatch >/dev/null 2>&1; then
  echo "后端: fswatch"
  fswatch -0 -e '.*' -i '\.(md|markdown|txt|html?)$' "$INBOX" | while IFS= read -r -d '' _; do sweep_once "$INBOX"; done
elif command -v inotifywait >/dev/null 2>&1; then
  echo "后端: inotifywait"
  inotifywait -m -q -e close_write -e moved_to --format '%f' "$INBOX" | while IFS= read -r _; do sweep_once "$INBOX"; done
else
  echo "后端: 轮询(每 ${INTERVAL}s,无外部依赖)"
  while true; do sweep_once "$INBOX" >/dev/null; sleep "$INTERVAL"; done
fi
