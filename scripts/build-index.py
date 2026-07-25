#!/usr/bin/env python3
# scripts/build-index.py
# 重建 _wiki/index.md —— 弥补 sage-wiki dev build 不自动维护 index.md 的差距(PRD FR-CMP-04 / 开发计划 G1)。
# 直接读 _wiki/{concepts,summaries,outputs}/ 的 frontmatter + 首句,按分类生成"页面 + 单行摘要 + 来源数"导航。
# 幂等:每次全量重写 index.md。建议在 compile 后运行(见 scripts/compile.sh)。
#
# 用法:python3 scripts/build-index.py

import json
import re
from datetime import date
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
WIKI = VAULT / "_wiki"
INDEX = WIKI / "index.md"


def split_frontmatter(text):
    """返回 (frontmatter_dict, body)。只解析我们需要的少数字段。"""
    fm, body = {}, text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            raw = text[3:end].strip("\n")
            body = text[end + 4:].lstrip("\n")
            for line in raw.splitlines():
                m = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
                if m:
                    fm[m.group(1)] = m.group(2).strip()
    return fm, body


def as_list(val):
    """把 frontmatter 里的 '["a","b"]' 或 'a' 解析成 list。"""
    if not val:
        return []
    try:
        v = json.loads(val)
        return v if isinstance(v, list) else [v]
    except Exception:
        return [val]


def first_sentence(body, max_len=90):
    """取正文第一句实义文字(跳过标题行),截断。"""
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith(">") or s.startswith("!["):
            continue
        s = re.sub(r"\[\[([^\]|]+)(\|[^\]]+)?\]\]", r"\1", s)   # 去 wikilink 语法
        s = re.split(r"(?<=[。.!?！?])\s", s)[0]
        return (s[:max_len] + "…") if len(s) > max_len else s
    return ""


def h1(body, fallback):
    m = re.search(r"^#\s+(.+)$", body, re.M)
    return m.group(1).strip() if m else fallback


def wikilink(path: Path):
    return f"[[{path.stem}]]"


def collect_concepts():
    """按 entity_type 分组:{type: [(name, link, oneliner, src_count), ...]}"""
    groups = {}
    for f in sorted((WIKI / "concepts").glob("*.md")):
        fm, body = split_frontmatter(f.read_text(encoding="utf-8"))
        etype = fm.get("entity_type", "concept")
        name = h1(body, fm.get("concept", f.stem))
        groups.setdefault(etype, []).append(
            (name, wikilink(f), first_sentence(body), len(as_list(fm.get("sources"))))
        )
    for t in groups:
        groups[t].sort(key=lambda x: x[0].lower())
    return groups


def collect_summaries():
    items = []
    for f in sorted((WIKI / "summaries").glob("*.md")):
        fm, body = split_frontmatter(f.read_text(encoding="utf-8"))
        src = fm.get("source", f.stem)
        items.append((Path(src).name, wikilink(f), first_sentence(body)))
    return items


def collect_outputs():
    items = []
    for f in sorted((WIKI / "outputs").glob("*.md")):
        fm, body = split_frontmatter(f.read_text(encoding="utf-8"))
        title = fm.get("标题") or fm.get("title") or h1(body, f.stem)
        items.append((title, wikilink(f)))
    return items


def main():
    concepts = collect_concepts()
    summaries = collect_summaries()
    outputs = collect_outputs()
    n_concept = sum(len(v) for v in concepts.values())

    out = []
    out.append("# 内容导航 Index")
    out.append("")
    out.append("> 由 `scripts/build-index.py` 生成(compile 后运行);sage-wiki 本身不维护此文件。查询时**先读这里**再深入相关页面。")
    out.append("")
    out.append(f"_最后更新:{date.today().isoformat()} · 概念 {n_concept} · 来源摘要 {len(summaries)} · 查询产出 {len(outputs)}_")
    out.append("")

    out.append("## 概念 Concepts")
    if not concepts:
        out.append("*(暂无 —— 运行 `sage-wiki compile` 后再跑本脚本)*")
    for etype in sorted(concepts):
        out.append("")
        out.append(f"### {etype}")
        for name, link, one, n in concepts[etype]:
            tail = f" — {one}" if one else ""
            src = f"({n} 源)" if n else ""
            out.append(f"- {link} {src}{tail}")
    out.append("")

    out.append("## 来源摘要 Summaries")
    if not summaries:
        out.append("*(暂无)*")
    for name, link, one in summaries:
        tail = f" — {one}" if one else ""
        out.append(f"- {link}{tail}")
    out.append("")

    out.append("## 查询产出 Outputs")
    if not outputs:
        out.append("*(暂无)*")
    for title, link in outputs:
        out.append(f"- {link} — {title}")
    out.append("")

    INDEX.write_text("\n".join(out), encoding="utf-8")
    print(f"✅ index.md 已重建:概念 {n_concept}(类型 {len(concepts)})· 摘要 {len(summaries)} · 产出 {len(outputs)}")


if __name__ == "__main__":
    main()
