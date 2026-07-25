#!/usr/bin/env python3
# scripts/freshness.py —— 轻量保鲜模型(P1-3,FR-LNT-07)。
# 机制借鉴同类项目实践:半衰期保鲜(自行实现,砍到三档,不抄五档/三维置信度):
# LLM 领地页面(_wiki/outputs/、material/)可选声明:
#   volatility: high|medium|low     —— 预设半衰期 30/90/365 天
#   half_life_days: <正整数>        —— 显式半衰期,优先于 volatility 预设
#   last_confirmed: YYYY-MM-DD      —— 上次人工确认"此页仍代表现状"的日期
# 健检时算 freshness_factor = 0.5^(距上次确认天数/半衰期):
#   ≤0.5(过了一个半衰期)列入"值得复核";≤0.25 标急。
# **只提示,不自动改内容**;无字段页面静默跳过。`--confirm` 是显式的人工确认动作。
#
# 用法:freshness.py [--vault V] [--json] [--threshold 0.5]     报告(退出码恒 0)
#       freshness.py --confirm <vault内相对路径>                盖 last_confirmed=今天
# lint 接入:compile.sh 第 3 步把本报告追加进 reports/lint/<日期>.txt。
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from decision import unyaml_val   # 引号标量剥离,与决策队列同一权威实现(评审 F6)

PRESETS = {"high": 30, "medium": 90, "low": 365}
URGENT = 0.25


def scan_targets(vault: Path) -> "list[Path]":
    """保鲜检查的作用面 = LLM 领地:_wiki/outputs/*.md + material/*/*.md(非递归,与宪法一致)。"""
    out = []
    d = vault / "_wiki" / "outputs"
    if d.is_dir():
        out += sorted(d.glob("*.md"))
    mat = vault / "material"
    if mat.is_dir():
        out += sorted(mat.glob("*/*.md"))
    return out


def parse_fm(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return {}
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = unyaml_val(v.strip())
    return fm


def half_life_of(fm: dict) -> "tuple[int | None, str | None]":
    """返回 (半衰期, 问题说明)。评审 F5:声明了保鲜但字段写坏时**报出来**而非静默除名;
    显式 half_life_days 写坏且有合法 volatility 时回落预设。(None, None)=未声明保鲜。"""
    v = fm.get("half_life_days")
    preset = PRESETS.get(fm.get("volatility", "").lower())
    if v:
        try:
            n = int(v)
        except ValueError:
            n = None
        if n is not None and n > 0:
            return n, None
        if preset:
            return preset, None   # 显式值坏 → 回落预设
        return None, f"half_life_days 写坏({v})且无可用 volatility"
    if preset:
        return preset, None
    if fm.get("volatility"):
        return None, f"volatility 值非法({fm.get('volatility')})"
    return None, None


def assess(vault: Path, threshold: float) -> dict:
    """扫描并评估;只读,不改任何页面。"""
    stale, tracked = [], 0
    for p in scan_targets(vault):
        fm = parse_fm(p)
        hl, problem = half_life_of(fm)
        if hl is None and problem is None:
            continue                     # 未声明保鲜字段:不参与(FR-LNT-07)
        tracked += 1
        rel = str(p.relative_to(vault))
        if hl is None:
            stale.append({"path": rel, "factor": None, "half_life_days": None,
                          "days_since": None, "urgent": True, "note": f"保鲜字段写坏:{problem}"})
            continue
        lc = fm.get("last_confirmed", "")
        try:
            days = (date.today() - date.fromisoformat(lc)).days
        except ValueError:
            # 声明了保鲜却没写/写坏 last_confirmed:视为待复核,而非静默漏掉
            note = (f"last_confirmed 写坏({lc}),请修正" if lc
                    else "缺 last_confirmed,无法计算,请确认后补上")
            stale.append({"path": rel, "factor": None, "half_life_days": hl,
                          "days_since": None, "urgent": True, "note": note})
            continue
        if days < 0:
            # 评审 F4:未来日期是笔误,不得静默当"永远新鲜"
            stale.append({"path": rel, "factor": None, "half_life_days": hl,
                          "days_since": days, "urgent": True,
                          "note": f"last_confirmed 在未来({lc}),疑似笔误"})
            continue
        factor = 0.5 ** (days / hl)
        if factor <= threshold:
            stale.append({"path": rel, "factor": round(factor, 4), "half_life_days": hl,
                          "days_since": days, "urgent": factor <= URGENT, "note": ""})
    stale.sort(key=lambda x: (x["factor"] is not None, x["factor"] or 0))
    return {"tracked": tracked, "threshold": threshold, "stale": stale}


def cmd_confirm(vault: Path, rel: str) -> int:
    """显式人工确认。副作用说明:以 UTF-8/LF 规范化回写(BOM 剥除、CRLF 归一)。
    评审 F1/F2/F8 修复:**confirm 作用面 = 扫描面的成员判定**(两侧 resolve 后比对)——
    `..` 穿透、前缀碰撞(material-old)、扫描面外的页(decisions/、六类深层)一并拒绝;
    startswith 前缀比较被实测绕过,弃用。"""
    try:
        q = (vault / rel).resolve()
    except OSError:
        print(f"✗ 路径无法解析:{rel}", file=sys.stderr)
        return 2
    targets = {t.resolve() for t in scan_targets(vault)}
    if q not in targets:
        print(f"✗ 不在保鲜作用面内(_wiki/outputs/*.md 与 material 子目录一层;"
              f"decisions/ 与更深层不参与):{rel}", file=sys.stderr)
        return 2
    text = q.read_text(encoding="utf-8-sig")
    today = date.today().isoformat()
    m = re.match(r"^(---\n.*?\n---\n)(.*)$", text, re.S)
    if not m:
        print(f"✗ 页面无 frontmatter,无法登记确认:{rel}", file=sys.stderr)
        return 1
    # 评审 F3:要求页面已声明保鲜字段才可盖章——顺带挡住"--- 水平线开头"被误认成 fm 的文档
    hl, problem = half_life_of(parse_fm(q))
    if hl is None:
        why = problem or "未声明保鲜字段(volatility / half_life_days)"
        print(f"✗ 不予盖章:{why}。先补字段再确认:{rel}", file=sys.stderr)
        return 1
    fm, body = m.group(1), m.group(2)
    if re.search(r"(?m)^last_confirmed:", fm):
        # 评审 F9:重复键全部更新,避免"确认成功但仍显示过期"
        fm = re.sub(r"(?m)^last_confirmed:.*$", lambda _: f"last_confirmed: {today}", fm)
    else:
        fm = re.sub(r"\n---\n$", f"\nlast_confirmed: {today}\n---\n", fm, count=1)
    q.write_text(fm + body, encoding="utf-8")
    print(f"✅ 已确认 {rel}(last_confirmed: {today})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="知识保鲜检查(只提示不自动改)")
    ap.add_argument("--vault", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--confirm", default=None, metavar="REL_PATH")
    args = ap.parse_args()
    vault = Path(args.vault) if args.vault else Path(__file__).resolve().parent.parent

    if args.confirm:
        return cmd_confirm(vault, args.confirm)

    report = assess(vault, args.threshold)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0
    if not report["stale"]:
        print(f"🌿 保鲜检查:{report['tracked']} 页在册,无过期风险。")
        return 0
    print(f"🍂 保鲜检查:{report['tracked']} 页在册,{len(report['stale'])} 页值得复核"
          f"(factor ≤ {report['threshold']}):")
    for x in report["stale"]:
        mark = "⚠️ 急" if x["urgent"] else "  "
        f = "—" if x["factor"] is None else f"{x['factor']:.2f}"
        extra = f";{x['note']}" if x["note"] else f"(半衰期 {x['half_life_days']} 天,{x['days_since']} 天未确认)"
        print(f"{mark} {x['path']}  factor={f} {extra}")
    print("复核后确认:python3 scripts/freshness.py --confirm <路径>(只登记日期,不改内容)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
