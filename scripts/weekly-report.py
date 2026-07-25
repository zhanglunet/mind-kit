#!/usr/bin/env python3
# scripts/weekly-report.py
# 把一周的日报聚合成周报:汇总数字、每日要点、分类小结、手记汇编,并留一个
# “周度综述”区供 LLM/人写叙事。默认盘点“上一个完整 ISO 周”(周一–周日)。
# 汇总数字直接盘点该周 git 提交 + log.md(源头,即使没生成过日报也准确);
# 手记来自各日日报,缺日报的日子会被标注。需要 Python 3.9+。
#
# 用法:
#   python3 scripts/weekly-report.py                 # 上一个完整周(周一–周日)
#   python3 scripts/weekly-report.py --this-week     # 本周(截至今天,可能不完整)
#   python3 scripts/weekly-report.py --week 2026-W28 # 指定 ISO 周
#   python3 scripts/weekly-report.py --last 7        # 最近 N 天(含昨天)
import sys, os, re, argparse
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reportlib as R  # noqa: E402

LLM_DEFAULT = ("## 周度综述（可由 LLM 生成）\n\n"
               "> 提示:在 Claudian 中运行 —— “读取本周报与 reports/daily/ 下本周各日报,\n"
               "> 写一段周度综述:本周主线、关键进展、遇到的问题、下周值得深挖的方向。”\n"
               "> 把结果填入本区(标记之间的内容不会被脚本覆盖)。")


def week_dates(monday: date) -> "list[str]":
    return [(monday + timedelta(days=i)).isoformat() for i in range(7)]


def render(label: str, days: "list[str]") -> str:
    start, end = days[0], days[-1]
    today = date.today().isoformat()
    gs = {d: R.gather(d) for d in days}
    total = {k: sum(gs[d][k] for d in days) for k in ("ingest", "query", "lint", "flomo_notes")}
    total_commits = sum(len(gs[d]["commits"]) for d in days)
    active_days = sum(1 for d in days if gs[d]["has_activity"])

    L = R.frontmatter(f"周报 {label}", period=f"{start} ~ {end}")
    L += [f"# 周报 · {label}（{start} ~ {end}）", "",
          "## 本周概览", "",
          f"- 活跃 {active_days}/{len(days)} 天 · 提交 {total_commits} 次 · 摄入 {total['ingest']} 篇 · "
          f"查询 {total['query']} 次 · 健检 {total['lint']} 次 · flomo 新笔记 {total['flomo_notes']} 条",
          "",
          "> 数字来自本周期 git 提交与 `_wiki/log.md`(即使未生成日报也准确);每日要点链接到已生成的日报。",
          ""]

    # 每日要点:缺日报的日子标注;未来日期(本周未到)单独标注
    L += ["## 每日要点", ""]
    for d in days:
        wd = R.weekday_cn(d)
        p = R.DAILY / f"{d}.md"
        if d > today:
            L.append(f"- **{d}（{wd}）**:_未到_")
            continue
        if not p.exists():
            g = gs[d]
            hint = "无活动" if not g["has_activity"] else f"提交 {len(g['commits'])} · 摄入 {g['ingest']} · 查询 {g['query']} · 健检 {g['lint']}"
            L.append(f"- **{d}（{wd}）**:{hint}(未生成日报 —— `python3 scripts/daily-report.py --date {d}` 可补)")
            continue
        g = gs[d]
        summ = (f"提交 {len(g['commits'])} · 摄入 {g['ingest']} · 查询 {g['query']} · 健检 {g['lint']}"
                if g["has_activity"] else "无活动记录")
        L.append(f"- **{d}（{wd}）**:{summ} → [日报](../daily/{d}.md)")
    L.append("")

    # 分类小结:把一周 log 条目按类型归并
    for typ, name in (("ingest", "摄入"), ("query", "查询"), ("lint", "健检")):
        items = [(d, e["title"]) for d in days for e in gs[d]["logs"] if e["type"] == typ]
        if items:
            L += [f"## {name}小结", ""]
            L += [f"- {d[5:]} {title}" for d, title in items]
            L.append("")

    # 手记汇编:把各日手记按日期拼接,供 LLM 叙述
    hands = [(d, R.extract_hand(R.DAILY / f"{d}.md")) for d in days]
    hands = [(d, h) for d, h in hands if h]
    if hands:
        L += ["## 手记汇编", ""]
        for d, h in hands:
            L += [f"**{d}（{R.weekday_cn(d)}）**", "", h, ""]

    # LLM 综述区(保留)
    L.append(R.preserve_block(R.WEEKLY / f"{label}.md", R.LLM_BEGIN, R.LLM_END, LLM_DEFAULT))
    L.append("")
    return "\n".join(L)


def parse_iso_week(s: str) -> "tuple[date, str]":
    m = re.fullmatch(r"(\d{4})-W(\d{2})", s)
    if not m:
        sys.exit(f"错误:ISO 周格式应为 YYYY-Www(如 2026-W28),收到:{s}")
    try:
        monday = date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)
    except ValueError:
        sys.exit(f"错误:{s} 不是有效的 ISO 周")
    return monday, s


def main():
    ap = argparse.ArgumentParser(description="把一周日报合成周报")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--week", help="指定 ISO 周 YYYY-Www")
    g.add_argument("--this-week", action="store_true", help="本周(截至今天,可能不完整)")
    g.add_argument("--last", type=int, metavar="N", help="最近 N 天(含昨天)")
    args = ap.parse_args()

    if args.week:
        monday, label = parse_iso_week(args.week)
        days = week_dates(monday)
    elif args.last is not None:
        if args.last < 1:
            sys.exit("错误:--last 需为正整数")
        days = R.recent_days(args.last)
        label = f"{days[0]}_{days[-1]}"
    else:
        today = date.today()
        this_monday = today - timedelta(days=today.isoweekday() - 1)
        monday = this_monday if args.this_week else this_monday - timedelta(days=7)
        iso = monday.isocalendar()
        label = f"{iso[0]}-W{iso[1]:02d}"
        days = week_dates(monday)

    R.atomic_write(R.WEEKLY / f"{label}.md", render(label, days))
    print(f"已生成周报:reports/weekly/{label}.md")
    R.rebuild_index()
    print("已更新 reports/index.md。")
    print("\n下一步:在“周度综述”区让 LLM 读本周日报写一段叙事(标记内内容不会被覆盖)。")


if __name__ == "__main__":
    main()
