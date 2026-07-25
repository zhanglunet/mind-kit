#!/usr/bin/env python3
# scripts/validate_write_set.py —— 写集校验(P1-4)。
# 机制:写集校验(只校本次变更范围)。
# **只校验本次变更范围**(耗时与写集成正比,不扫全库;全库一致性归定时 lint),
# 把评审史上抓过的"静默腐蚀"在入库前拦住:
#   - frontmatter 未闭合 / 行不是 key: value / 键重复
#   - 值含「: 」未引号化(Dataview 解析失败 → 记录在看板隐身,P1-2 评审实测)
#   - 保鲜字段写坏 / last_confirmed 在未来(P1-3 评审实测)
#   - decisions/ 记录不变量(复用 decision.record_problems,单一权威)
#   - 引用宿主临时上传路径(uploads、/tmp/claude-):证据链会失效(FR-ING-08)
#   - 非 UTF-8
# 范围:只校 **LLM 领地**;引擎领地(_wiki/{summaries,concepts,entities})跳过
# (engine 的输出我们修不了,归 lint);log.md 只查 UTF-8。
#
# 用法:validate_write_set.py [--vault V] (--path P ... | --paths-file F | --git-changed)
#       [--empty-ok] [--json]
# 退出码:0 全过;1 有违规;2 用法错误/空写集(--empty-ok 时空写集退 0,供 vault.sh 门禁用)。
import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import decision
import freshness

# 校验白名单 = LLM 领地(评审 F1:此前只排除引擎目录,raw/ 剪藏的冒号标题/非 UTF-8
# 会堵死全部提交,而宪法禁改 raw 原件——修复路径都被堵死。领地外一律跳过,归 lint)。
LLM_SCOPE = ("_wiki/outputs/", "material/", "writing/", "reports/")
TEMP_PATH_RE = re.compile(r"\.claude/uploads|/tmp/claude-")
# 键名允许 Unicode(中文属性名如「类别/主体/来源」是合法 YAML、合法 Obsidian 属性;
# 旧版限 [A-Za-z_] 会把存量中文 fm 键全部误判(实测:某次真实内容库演练中 58 页里 19 页因此误伤)。首字符的空白/#/
# 「- 」列表项已由上游过滤,这里只排除以冒号开头的畸形行;仍要求 ASCII 冒号作分隔
# (全角冒号「：」自然不匹配,照样落到"非 key: value"被拦)。
KEY_RE = re.compile(r"^([^\s:#][^:]*):(.*)$")


def _parse_porcelain_z(stdout: str) -> "list[str]":
    """解析 `git status --porcelain -z -uall`:R/C 条目后跟旧路径需跳过(评审 F7),
    删除不校,非 .md 过滤。"""
    out, parts = [], [p for p in stdout.split("\0") if p]
    i = 0
    while i < len(parts):
        entry = parts[i]
        xy, path = entry[:2], entry[3:]
        i += 1
        if xy[:1] in ("R", "C"):
            i += 1                      # 改名/拷贝条目后跟旧路径,跳过
        if "D" in xy:
            continue                    # 删除无内容可校
        if path.endswith(".md"):
            out.append(path)
    return out


def git_changed_md(vault: Path) -> "list[str]":
    """内容库里本次变更(未提交)的 .md 相对路径。-z 防空格;-uall 展开未跟踪目录。"""
    r = subprocess.run(["git", "-C", str(vault), "status", "--porcelain", "-z", "-uall"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"⚠ git status 失败({r.stderr.strip()[:80]}),写集视为空", file=sys.stderr)
        return []
    return _parse_porcelain_z(r.stdout)


def check_page(vault: Path, rel: str) -> "tuple[str, list[str]]":
    """返回 (checked|skipped, problems)。"""
    rel_posix = Path(rel).as_posix()
    if not any(rel_posix.startswith(d) for d in LLM_SCOPE):
        return "skipped", ["非 LLM 领地(raw/引擎目录/代码文档等),不校——原样保留,全库一致性归 lint"]
    p = vault / rel
    if not p.is_file():
        return "skipped", ["文件不存在(已删除?)"]
    try:
        text = p.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return "checked", ["非 UTF-8 编码"]

    problems = []
    if text.startswith("---") and not re.match(r"^---\n\s*---(\n|$)", text):
        # 空 frontmatter(Obsidian 清空属性残留)合法,跳过键校验(评审 F9)
        m = re.match(r"^---\n(.*?)\n---(\n|$)", text, re.S)
        if not m:
            return "checked", ["frontmatter 未闭合(有开栏无闭栏)"]
        raw_fm, seen = {}, set()
        for line in m.group(1).splitlines():
            # 缩进续行(块式列表/多行值)、顶格列表项、注释——都是合法 YAML,放行(评审 F2)
            if not line.strip() or line[0] in " \t#" or line.startswith("- "):
                continue
            km = KEY_RE.match(line)
            if not km:
                problems.append(f"fm 行不是 key: value 形态:{line[:48]}")
                continue
            k, v = km.group(1), km.group(2).strip()
            if k in seen:
                problems.append(f"fm 键重复:{k}")
            seen.add(k)
            raw_fm[k] = v
            if v and v[0] not in "\"'" and ": " in v:
                problems.append(f"fm 值含「: 」须引号化,否则 Dataview 解析失败、页面在看板隐身:{k}")
        fm = {k: decision.unyaml_val(v) for k, v in raw_fm.items()}
        # 保鲜字段(声明了才校;复用 freshness 的单一权威判定)
        _, fresh_problem = freshness.half_life_of(fm)
        if fresh_problem:
            problems.append(f"保鲜字段:{fresh_problem}")
        lc = fm.get("last_confirmed", "")
        if lc:
            try:
                if (date.today() - date.fromisoformat(lc)).days < 0:
                    problems.append(f"last_confirmed 在未来({lc}),疑似笔误")
            except ValueError:
                problems.append(f"last_confirmed 写坏({lc})")
        # 只有决策记录本体(DEC-*.md)才套记录不变量;README 等辅助文件不套(评审 F5)
        if rel_posix.startswith("_wiki/outputs/decisions/") and Path(rel).name.startswith("DEC-"):
            problems += [f"决策记录:{p2}" for p2 in decision.record_problems(fm)]
    if TEMP_PATH_RE.search(text):
        problems.append("引用了宿主临时路径(uploads / /tmp/claude-):"
                        "临时路径会失效、破坏证据链,改引 vault 内路径(FR-ING-08)")
    return "checked", problems


def main() -> int:
    ap = argparse.ArgumentParser(description="写集校验(只校本次变更,不扫全库)")
    ap.add_argument("--vault", default=None)
    ap.add_argument("--path", action="append", default=[])
    ap.add_argument("--paths-file", default=None)
    ap.add_argument("--git-changed", action="store_true")
    ap.add_argument("--empty-ok", action="store_true",
                    help="空写集时退 0(供 vault.sh 门禁:无 md 变更即无需校验)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    vault = Path(args.vault) if args.vault else Path(__file__).resolve().parent.parent

    paths = list(args.path)
    if args.paths_file:
        src = sys.stdin if args.paths_file == "-" else open(args.paths_file, encoding="utf-8")
        paths += [ln.strip() for ln in src if ln.strip()]
    if args.git_changed:
        paths += git_changed_md(vault)
    paths = list(dict.fromkeys(paths))   # 去重保序
    if not paths:
        if args.empty_ok:
            print("写集为空(无 .md 变更),无需校验。")
            return 0
        print("✗ 未给出任何写集路径(--path/--paths-file/--git-changed)。"
              "空写集不构成校验,拒绝绿灯。", file=sys.stderr)
        return 2

    results = []
    for rel in paths:
        status, problems = check_page(vault, rel)
        results.append({"path": rel, "status": status, "problems": problems})
    checked = sum(1 for r in results if r["status"] == "checked")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed = sum(1 for r in results if r["status"] == "checked" and r["problems"])
    report = {"checked": checked, "skipped": skipped, "failed": failed,
              "ok": failed == 0, "results": results}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        for r in results:
            if r["status"] == "skipped":
                print(f"⊘ {r['path']}({r['problems'][0]})")
            elif r["problems"]:
                for prob in r["problems"]:
                    print(f"✗ {r['path']}: {prob}")
            else:
                print(f"✓ {r['path']}")
        print(f"—— 写集校验:{checked} 校 / {skipped} 跳 / {failed} 败")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
