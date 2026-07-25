#!/usr/bin/env python3
# scripts/dedup-check.py — 摄入前查重提示(FR-ING-07 / 开发计划 P2-4)。只读、只提示,不改任何文件。
# 把候选文件(默认 raw/todo + raw/clippings)与既有语料(raw/archive + raw/clippings + raw/todo +
# 已编译 _wiki/summaries 记录的来源)比对:
#   - 精确重复:正文规范化后的 MD5 相同
#   - 疑似重复:标题相似度 或 内容 5-gram(词粒度)重叠 高于阈值
#
# 用法:
#   python3 scripts/dedup-check.py                     # 扫 raw/todo + raw/clippings
#   python3 scripts/dedup-check.py raw/todo/x.md       # 只查某文件
#   python3 scripts/dedup-check.py --title 0.85 --overlap 0.5

import argparse
import hashlib
import re
from difflib import SequenceMatcher
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent


def rel(p):
    """相对 vault 根的显示路径;不在 vault 内则原样返回。"""
    try:
        return p.resolve().relative_to(VAULT)
    except ValueError:
        return p


def strip_frontmatter(text):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:]
    return text


def title_of(path, text):
    if text.startswith("---"):
        m = re.search(r'^title:\s*"?(.+?)"?\s*$', text[:text.find("\n---", 3) + 1 or 0], re.M)
        if m:
            return m.group(1).strip()
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return m.group(1).strip() if m else path.stem


def norm_text(text):
    body = strip_frontmatter(text)
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body)      # 去图片
    body = re.sub(r"<[^>]+>", "", body)                     # 去标签
    body = re.sub(r"\s+", "", body)                         # 去所有空白
    return body


def content_hash(text):
    return hashlib.md5(norm_text(text).encode("utf-8")).hexdigest()


def shingles(text, n=5):
    toks = re.findall(r"[\w一-鿿]+", strip_frontmatter(text).lower())
    return set(tuple(toks[i:i + n]) for i in range(max(0, len(toks) - n + 1)))


def overlap(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def load_corpus():
    """既有来源:raw/{archive,clippings,todo} 的 md。返回 [(path, text)]。"""
    corpus = []
    for d in ["raw/archive", "raw/clippings", "raw/todo"]:
        for f in (VAULT / d).rglob("*.md"):
            try:
                corpus.append((f, f.read_text(encoding="utf-8")))
            except Exception:
                pass
    return corpus


def main():
    ap = argparse.ArgumentParser(description="摄入前查重提示")
    ap.add_argument("paths", nargs="*", help="候选文件(默认 raw/todo + raw/clippings)")
    ap.add_argument("--title", type=float, default=0.85, help="标题相似度阈值")
    ap.add_argument("--overlap", type=float, default=0.5, help="内容 5-gram 重叠阈值")
    args = ap.parse_args()

    if args.paths:
        candidates = [Path(p).resolve() for p in args.paths]
    else:
        candidates = []
        for d in ["raw/todo", "raw/clippings"]:
            candidates += sorted((VAULT / d).rglob("*.md"))

    corpus = load_corpus()
    flagged = 0
    for cand in candidates:
        if not cand.exists():
            continue
        ctext = cand.read_text(encoding="utf-8")
        chash, ctitle, cshin = content_hash(ctext), title_of(cand, ctext), shingles(ctext)
        hits = []
        for path, text in corpus:
            if path.resolve() == cand.resolve():
                continue
            if content_hash(text) == chash:
                hits.append((path, "精确重复", 1.0))
                continue
            tr = SequenceMatcher(None, ctitle, title_of(path, text)).ratio()
            ov = overlap(cshin, shingles(text))
            if tr >= args.title or ov >= args.overlap:
                why = []
                if tr >= args.title:
                    why.append(f"标题{tr:.0%}")
                if ov >= args.overlap:
                    why.append(f"内容{ov:.0%}")
                hits.append((path, "疑似:" + "/".join(why), max(tr, ov)))
        if hits:
            flagged += 1
            print(f"\n⚠️  {rel(cand)}")
            for path, why, score in sorted(hits, key=lambda x: -x[2])[:5]:
                print(f"     ↔ {why}  {rel(path)}")

    if flagged == 0:
        print("✅ 未发现重复/疑似重复。")
    else:
        print(f"\n共 {flagged} 个候选有重复/疑似,请人工确认后再决定是否摄入。")


if __name__ == "__main__":
    main()
