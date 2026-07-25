#!/usr/bin/env python3
# scripts/subscriptions.py
# 数字订阅台账:记录 Claude Code / Codex / VPN / VPS 等订阅的周期与费用,列出临期续费项,防止忘记续费。
# 数据源:mind-vault/subscriptions.json(内容库,随 vault.sh 留档;勿放支付方式/卡号等敏感信息)。
#
# 用法:
#   python3 scripts/subscriptions.py             # 全量列表,按下次续费日排序
#   python3 scripts/subscriptions.py --days 30   # 只看 N 天内到期的
#   python3 scripts/subscriptions.py --notify    # ≤5 天到期时弹 macOS 通知,供 cron 每日调用
#
# cron(已装,每天 9:17:≤5 天到期弹通知 + 重建台账页和门户):
#   17 9 * * * cd $HOME/second-brain/mind && /usr/bin/python3 scripts/subscriptions.py --notify \
#     && /usr/bin/python3 scripts/build-subscriptions-site.py && /usr/bin/python3 scripts/build-portal.py
#
# 数据字段:
#   name 名称 / vendor 厂商 / category 分类 / cost 费用(null=未填) / currency 币种
#   cycle 周期:monthly | quarterly | semiannual | yearly
#   anchor 上次扣费日(YYYY-MM-DD),脚本按 cycle 顺推出下次续费日
#   next 可选:下次续费日(YYYY-MM-DD)。面板显示的截止日与 anchor 顺推不一致时
#        (如提前续了一个周期)用它直接指定;过期后自动回落到 anchor+cycle 顺推
#   auto_renew 是否自动扣款 / url 管理页 / notes 备注
import argparse
import json
import os
import subprocess
import sys
from datetime import date, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 数据在内容库 mind-vault 根下;脚本在 mind/scripts/,往上两级到 second-brain/
DATA = os.path.join(SCRIPT_DIR, "..", "..", "mind-vault", "subscriptions.json")

CYCLE_MONTHS = {"monthly": 1, "quarterly": 3, "semiannual": 6, "yearly": 12}
CYCLE_CN = {"monthly": "月付", "quarterly": "季付", "semiannual": "半年付", "yearly": "年付"}
URGENT_DAYS = 5
WARN_DAYS = 30


def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    # 月末对齐:1月31日 + 1个月 → 2月28/29日
    days_in_month = [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28,
                     31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, days_in_month))


def next_renewal(anchor: date, cycle: str, today: date) -> date:
    months = CYCLE_MONTHS[cycle]
    nxt = anchor
    while nxt < today:
        nxt = add_months(nxt, months)
    return nxt


def load() -> list:
    with open(DATA, encoding="utf-8") as f:
        subs = json.load(f)
    today = date.today()
    rows = []
    for s in subs:
        if s.get("cycle") not in CYCLE_MONTHS:
            print(f"⚠️  {s.get('name')}: 未知 cycle {s.get('cycle')!r},跳过", file=sys.stderr)
            continue
        anchor = date.fromisoformat(s["anchor"])
        nxt = next_renewal(anchor, s["cycle"], today)
        if s.get("next"):                       # 显式指定的下次续费日优先,过期回落顺推
            explicit = date.fromisoformat(s["next"])
            if explicit >= today:
                nxt = explicit
        rows.append({**s, "next": nxt, "left": (nxt - today).days})
    rows.sort(key=lambda r: r["next"])
    return rows


def mark(left: int) -> str:
    if left <= URGENT_DAYS:
        return "🔴"
    if left <= WARN_DAYS:
        return "🟡"
    return "⚪"


def render(rows: list) -> str:
    lines = [f"{'':2}{'名称':<14}{'周期':<6}{'费用':<12}{'下次续费':<12}{'剩余':<6}自动续费"]
    for r in rows:
        cost = f"{r['cost']} {r['currency']}" if r.get("cost") is not None else "—"
        auto = "是" if r.get("auto_renew") else "否"
        lines.append(f"{mark(r['left'])} {r['name']:<14}{CYCLE_CN[r['cycle']]:<6}"
                     f"{cost:<12}{r['next'].isoformat():<12}{r['left']} 天{'':<3}{auto}")
    lines.append("")
    lines.append(f"🔴 ≤{URGENT_DAYS} 天内到期  🟡 ≤{WARN_DAYS} 天  ⚪ 尚早;数据:{os.path.relpath(DATA)}")
    return "\n".join(lines)


def notify(due: list) -> None:
    body = "、".join(f"{r['name']}({r['left']} 天)" for r in due)
    subprocess.run([
        "osascript", "-e",
        f'display notification "{body}" with title "订阅续费提醒" subtitle "{len(due)} 项 ≤{URGENT_DAYS} 天内到期"',
    ], check=False)


def main() -> int:
    ap = argparse.ArgumentParser(description="数字订阅台账:列出临期续费项")
    ap.add_argument("--days", type=int, default=None, help="只看 N 天内到期的")
    ap.add_argument("--notify", action="store_true", help=f"≤{URGENT_DAYS} 天到期时弹 macOS 通知(供 cron)")
    args = ap.parse_args()

    rows = load()
    if args.notify:
        due = [r for r in rows if r["left"] <= URGENT_DAYS]
        if due:
            notify(due)
            print(f"已通知 {len(due)} 项:{', '.join(r['name'] for r in due)}")
        return 0

    shown = [r for r in rows if args.days is None or r["left"] <= args.days]
    if not shown:
        print(f"未来 {args.days} 天内无到期订阅。")
        return 0
    print(render(shown))
    return 1 if any(r["left"] <= URGENT_DAYS for r in shown) else 0


if __name__ == "__main__":
    sys.exit(main())
