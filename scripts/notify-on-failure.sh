#!/usr/bin/env bash
# scripts/notify-on-failure.sh —— 包住一条命令,**只在它失败时**发一条通知。
#
# 为什么需要它:`update-all.sh` / `compile.sh` 的非零退出码此前**没有任何消费者** ——
# cron 把 stdout/stderr 全量重定向进日志,失败只体现在日志文本里,没人看。
# 「失败要能被看见」在编排层与编译层都做到了,通知层一直是空的。
#
# 用法(装进 crontab,把原来的命令整条包进来):
#   30 9 * * * cd $MIND && bash scripts/notify-on-failure.sh \
#                bash scripts/update-all.sh >> $HOME/.mind-update-all.log 2>&1
#
# 通知渠道由 MIND_NOTIFY_CMD 指定(接收 stdin 的任意命令);**不配 = 静默跳过**。
#   MIND_NOTIFY_CMD='mail -s "mind 定时任务失败" you@example.com'
#   MIND_NOTIFY_CMD="$MIND/.venv/bin/python $MIND/scripts/notify_feishu.py"   # 若装了飞书出口
#
# ── 四条契约(每条都对应一种「通知反而帮倒忙」的方式)────────────────────
#  1. 失败才发。天天来一条「一切正常」,很快没人看,真出事那条跟着被忽略。
#  2. **退出码原样透传**。`cmd || notify` 会把整体退出码变成 notify 的 ——
#     通知发成功了整条 cron 就"成功"了,原始失败反被通知掩盖。这是最容易写错的一处。
#  3. **发卡自己失败也不许改写退出码**。否则两个故障互相掩盖,日志上看是另一回事。
#  4. 未配置就静默跳过,且不改退出码。没配飞书的机器(笔记本、同事的)不该
#     每天刷一屏「通知发不出去」把真日志淹掉。
set -uo pipefail

if [ $# -eq 0 ]; then
  echo "用法:bash scripts/notify-on-failure.sh <命令> [参数…]" >&2
  exit 2
fi

"$@"
rc=$?                    # 立刻存下来:后面任何一条命令都会覆盖 $?

[ "$rc" -eq 0 ] && exit 0

# —— 到这里说明被包命令失败了 ——
notifier="${MIND_NOTIFY_CMD:-}"
if [ -z "$notifier" ]; then
  # 未配置:不吭声(契约 4),但退出码照旧
  exit "$rc"
fi

host="$(hostname 2>/dev/null || echo 未知主机)"
{
  printf '❌ 定时任务失败\n\n'
  printf '主机:%s\n' "$host"
  printf '时间:%s\n' "$(date '+%F %T')"
  printf '退出码:%s\n' "$rc"
  printf '命令:%s\n' "$*"
  printf '\n日志在 cron 那行的重定向目标里(通常 ~/.mind-*.log),末尾就是现场。\n'
} | $notifier
nrc=$?

# 契约 3:发卡失败要吭一声,但**绝不**改写 $rc
[ "$nrc" -eq 0 ] || echo "⚠ 失败通知本身也没发出去(通知命令退出码 $nrc)——原始失败仍为 $rc" >&2

exit "$rc"
