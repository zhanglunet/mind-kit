#!/usr/bin/env python3
"""okf.py —— Open Knowledge Format v0.2 合规:体检(--check)与注入(--fix)。

OKF(https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf)是
"用 markdown + YAML frontmatter 表示知识"的中立格式。本库的形态与它高度重合
(bundle=目录、保留文件 index.md/log.md、容忍未知键),**硬性要求只有三条**:

  1. 每个非保留 .md 有合法 YAML frontmatter
  2. 每个 frontmatter 的 `type` 非空
  3. index.md / log.md 出现时结构符合 §8-9      ← 本脚本不管,另议

本脚本只管 1 和 2,外加把已有的保鲜机制映射成 OKF 的 `stale_after`。

## 三条设计原则

**确定性映射,不用 LLM。** `type` 的值从目录 + 已有键推出:概念页的 `entity_type`
本来就是 OKF 的 `type` 语义,搬过来即可。

**幂等。** 引擎领地(_wiki/{concepts,summaries,entities})的页每轮编译都会被扫一遍。
不幂等的话每轮都改文件 —— git 每天一堆空 diff,还会触发 sage-wiki 的 reconcile churn。
所以:已有目标键就一个字节都不写。

**只加不改,保留原键。** `entity_type` / `类别` / `decision_type` 全部原样留着 ——
OKF 明确要求消费者容忍未知键,而这些键有现成消费者(build-index.py:71、
build-wiki-site.py:107、Obsidian 属性面板),改名等于砸自家管线。

## 为什么引擎领地也能改

CLAUDE.md 规定 `_wiki/{summaries,concepts,entities}` 由 sage-wiki 全权负责,人不要手改。
本脚本不是"手改":它是 compile.sh 流水线的一步,在引擎写完之后确定性地补齐字段,
每轮自动重放。源文件一变引擎会整页重写、抹掉注入的键 —— 但下一步就是本脚本,自愈。

用法:
  python3 scripts/okf.py --check          # 只读体检,不合规非零退出
  python3 scripts/okf.py --fix            # 幂等注入
  python3 scripts/okf.py --check --json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

# 与 freshness.py 保持同一套预设(那边是权威,这里只是复用算式)
VOLATILITY_HALF_LIFE = {"high": 30, "medium": 90, "low": 365}

# OKF §8-9 的保留文件名:不得有 frontmatter,一律跳过
RESERVED = {"index.md", "log.md"}

# bundle 边界。writing/ 是写作成稿存档,不是知识页 —— 它已经被排除在编译源
# (config.yaml)、索引(indexlib.py)、浏览站(build-wiki-site.py)之外,这里同样排除。
BUNDLE_DIRS = ("_wiki", "material", "reports")
EXCLUDED = ("_wiki/under_review", "raw", "writing", "browse", "site", "docs", "scripts")


def type_for(rel: str, fm: dict) -> str:
    """确定性推出 OKF 的 `type`。目录决定大类,已有键提供更细的值。

    辅助文件(CHANGELOG / README)先判:它们散落在各目录下,若按目录先判就会
    被 `material/` `reports/` 这些前缀吃掉,拿到语义错误的 type。
    """
    name = rel.rsplit("/", 1)[-1]
    if name in ("CHANGELOG.md", "README.md"):
        # OKF 只保留 index.md / log.md 两个文件名,别的辅助文件同样要有 type
        return "changelog" if name == "CHANGELOG.md" else "readme"
    if rel.startswith("_wiki/concepts/"):
        # entity_type 的值域是 concept / technique / claim(prompts/extract-concepts.md:25)
        v = str(fm.get("entity_type", "")).strip()
        return v or "concept"
    if rel.startswith("_wiki/summaries/"):
        return "summary"
    if rel.startswith("_wiki/entities/"):
        return "entity"
    if rel.startswith("_wiki/outputs/decisions/"):
        return "decision"
    if rel.startswith("_wiki/outputs/"):
        return "output"
    if rel.startswith("material/"):
        return "material"
    if rel.startswith("reports/"):
        return "report"
    return "note"


def split_fm(text: str) -> "tuple[list[str], str]":
    """→ (frontmatter 行列表, 正文)。无 frontmatter 时返回 ([], 全文)。"""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return [], text
    for i, ln in enumerate(lines[1:], start=1):
        if ln.strip() == "---":
            return [l.rstrip("\n") for l in lines[1:i]], "".join(lines[i + 1:])
    return [], text          # 未闭合:当作没有,交给 validate_write_set 去报


def parse_fm(fm_lines: "list[str]") -> dict:
    """够用就好的解析:只取顶层 `key: value`。块式列表的值取不到,但我们只读标量键。"""
    out = {}
    for ln in fm_lines:
        s = ln.strip()
        if not s or s.startswith("#") or s.startswith("-") or ln[:1] in (" ", "\t"):
            continue
        k, sep, v = ln.partition(":")
        if sep and k.strip():
            out[k.strip()] = v.strip()
    return out


def half_life_of(fm: dict) -> "int | None":
    """显式 half_life_days 优先,否则按 volatility 预设。未声明保鲜 → None。"""
    v = fm.get("half_life_days")
    if v is not None:
        try:
            n = int(str(v).strip())
            if n > 0:
                return n
        except ValueError:
            pass                       # 写坏了就回落 volatility
    vol = str(fm.get("volatility", "")).strip().lower()
    return VOLATILITY_HALF_LIFE.get(vol)


def stale_after_for(fm: dict) -> "str | None":
    """last_confirmed + 半衰期。缺任一 → None(不追踪的页不塞这个键)。"""
    hl = half_life_of(fm)
    if hl is None:
        return None
    lc = str(fm.get("last_confirmed", "")).strip().strip("'\"")
    if not lc:
        return None
    try:
        return (date.fromisoformat(lc) + timedelta(days=hl)).isoformat()
    except ValueError:
        return None


def pages(vault: Path) -> "list[Path]":
    out = []
    for d in BUNDLE_DIRS:
        root = vault / d
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*.md")):
            rel = p.relative_to(vault).as_posix()
            if p.name in RESERVED or any(rel.startswith(x + "/") or rel == x for x in EXCLUDED):
                continue
            out.append(p)
    return out


def plan(p: Path, vault: Path) -> dict:
    """这一页缺什么。不写盘。"""
    rel = p.relative_to(vault).as_posix()
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return {"path": rel, "error": str(e)}
    fm_lines, body = split_fm(text)
    fm = parse_fm(fm_lines)
    add = {}
    if not str(fm.get("type", "")).strip():
        add["type"] = type_for(rel, fm)
    sa = stale_after_for(fm)
    if sa and not str(fm.get("stale_after", "")).strip():
        add["stale_after"] = sa
    return {"path": rel, "add": add, "has_fm": bool(fm_lines) or text.startswith("---"),
            "fm_lines": fm_lines, "body": body}


def apply(p: Path, item: dict) -> None:
    """把缺的键写进 frontmatter。`type` 放首位(与 reportlib.frontmatter() 的写法一致)。"""
    add, fm_lines, body = item["add"], item["fm_lines"], item["body"]
    head = []
    if "type" in add:
        head.append(f"type: {add['type']}")
    tail = [f"stale_after: {add['stale_after']}"] if "stale_after" in add else []
    new = ["---"] + head + fm_lines + tail + ["---", ""]
    p.write_text("\n".join(new) + body, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="OKF v0.2 合规体检与注入")
    ap.add_argument("--vault", default=None)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="只读体检,不合规非零退出")
    g.add_argument("--fix", action="store_true", help="幂等注入缺失字段")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    vault = Path(a.vault).resolve() if a.vault else Path(__file__).resolve().parent.parent
    items = [plan(p, vault) for p in pages(vault)]
    bad = [i for i in items if i.get("error") or i.get("add") or not i.get("has_fm")]

    if a.json:
        print(json.dumps({"total": len(items), "pending": len(bad),
                          "items": [{k: v for k, v in i.items()
                                     if k not in ("fm_lines", "body")} for i in bad]},
                         ensure_ascii=False, indent=2))
    if a.check:
        if not a.json:
            print(f"OKF 合规体检:{len(items)} 页,{len(bad)} 页待补")
            for i in bad[:40]:
                why = i.get("error") or ("缺 " + " / ".join(i["add"]) if i.get("add") else "无 frontmatter")
                print(f"  · {i['path']} —— {why}")
            if len(bad) > 40:
                print(f"  …… 另有 {len(bad) - 40} 页")
        return 1 if bad else 0

    changed = 0
    for i in items:
        if i.get("error") or not i.get("add"):
            continue
        apply(vault / i["path"], i)
        changed += 1
    if not a.json:
        print(f"OKF 注入:{len(items)} 页扫描,{changed} 页更新"
              + ("(其余已合规,未改动)" if changed < len(items) else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
