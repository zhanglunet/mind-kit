#!/usr/bin/env python3
# scripts/daily-report.py
# 盘点某一天(默认“昨天”)在知识库上做的工作,生成/更新一份日报,持续记录。
# 数据来源:git 提交(作者日期,本地时区)+ _wiki/log.md 条目 + 当天 flomo delta。
# 每条结论可回溯到具体 git sha 或 log 条目;“手记”区由人/LLM 补写,重生成不覆盖。
# 需要 Python 3.9+,在仓库内运行(git 可用)。
#
# 用法:
#   python3 scripts/daily-report.py                # 昨天
#   python3 scripts/daily-report.py --today        # 今天(截至此刻,进行中快照)
#   python3 scripts/daily-report.py --date 2026-07-13
#   python3 scripts/daily-report.py --days 7       # 回填最近 7 天(含昨天),各生成一份
import sys, os, argparse
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reportlib as R  # noqa: E402


def render(day: str) -> str:
    g = R.gather(day)
    L = R.frontmatter(f"日报 {day}", date=day)
    L += [f"# 日报 · {day}（{R.weekday_cn(day)}）", ""]
    if day == date.today().isoformat():
        L += [f"> ⏳ 今日进行中 —— 本文是截至 {datetime.now().strftime('%H:%M')} 的快照,晚些重跑可刷新。", ""]

    # 概览:一行数字汇总(honest —— 无活动就直说)
    L += ["## 概览", ""]
    if g["has_activity"]:
        parts = [f"提交 {len(g['commits'])} 次", f"摄入 {g['ingest']} 篇",
                 f"查询 {g['query']} 次", f"健检 {g['lint']} 次"]
        if g["flomo_notes"]:
            parts.append(f"flomo 新笔记 {g['flomo_notes']} 条")
        wm = g["touched"].get("写作素材", 0)
        if wm:
            parts.append(f"写作/素材 {wm} 项")
        L.append("- " + " · ".join(parts))
    else:
        L.append("- 今日无 git 提交、无 log 记录、无 flomo 增量。（若确有库外工作,请补入下方手记。）")
    L.append("")

    # 活动明细 —— 来自 _wiki/log.md
    L += ["## 摄入 / 查询 / 健检", ""]
    if g["logs"]:
        L += ["> 来源:`_wiki/log.md`", ""]
        L += [f"- **[{e['type']}]** {e['title']}" for e in g["logs"]]
    else:
        L.append("_今日 log.md 无记录。_")
    L.append("")

    # flomo 增量
    if g["deltas"]:
        L += ["## flomo 增量", ""]
        for d in g["deltas"]:
            n = f"{d['count']} 条新笔记" if d["count"] is not None else "笔记数未知"
            L.append(f"- `{d['name']}`：{n}")
        L.append("")

    # 代码与内容变更 —— 来自 git 提交,每条挂 sha 可回溯
    L += ["## 代码与内容变更", ""]
    if g["commits"]:
        L += ["> 来源:git 提交(作者日期为本地时区当天)", ""]
        for c in g["commits"]:
            L.append(f"- `{c['sha']}` {c['subject']}")
            summ = " · ".join(f"{cat} {len(fs)} 文件" for cat, fs in c["buckets"].items())
            if summ:
                L.append(f"  - {summ}")
    else:
        L.append("_今日无提交。_")
    L.append("")

    # 手记区(保留人/LLM 补写)
    L.append(R.preserve_block(R.DAILY / f"{day}.md", R.HAND_BEGIN, R.HAND_END, R.HAND_BODY))
    L.append("")
    return "\n".join(L)


def write_day(day: str) -> None:
    R.atomic_write(R.DAILY / f"{day}.md", render(day))
    print(f"已生成日报:reports/daily/{day}.md")


def main():
    ap = argparse.ArgumentParser(description="生成前一天(或指定日)的工作日报")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--date", help="盘点指定日期 YYYY-MM-DD")
    g.add_argument("--today", action="store_true", help="盘点今天(截至此刻)")
    g.add_argument("--days", type=int, metavar="N", help="回填最近 N 天(含昨天),各生成一份")
    args = ap.parse_args()

    if args.date:
        try:
            date.fromisoformat(args.date)
        except ValueError:
            sys.exit(f"错误:日期格式应为 YYYY-MM-DD,收到:{args.date}")
        targets = [args.date]
    elif args.today:
        targets = [date.today().isoformat()]
    elif args.days is not None:
        if args.days < 1:
            sys.exit("错误:--days 需为正整数")
        targets = R.recent_days(args.days)
    else:
        targets = R.recent_days(1)  # 昨天

    for d in targets:
        write_day(d)
    R.rebuild_index()
    print("已更新 reports/index.md。")
    print("\n下一步:")
    print("- 在“手记”区补写今日反思/库外工作(可由 LLM 填)。")
    print("- 想持续留档可 git 提交 reports/;若手记含敏感内容,见 reports/README.md 的隐私说明。")
    print("- 周末运行 python3 scripts/weekly-report.py 合成周报。")


if __name__ == "__main__":
    main()
