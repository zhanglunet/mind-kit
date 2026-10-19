#!/usr/bin/env python3
"""scripts/preflight-check.py —— 编译前规则预检门(P1-3 保鲜链路降本)。

ECC instincts 思想:「这篇剪藏值不值得调一次 LLM」是高频低风险决策,
预编译成规则,不要每次都让 LLM 自己判断。

在 `sage-wiki compile` 之前跑(见 compile.sh 第 0 步),对 raw/clippings/
逐文件过四道规则门,命中任一道就**隔离**到 raw/quarantine/<原因>/,
不删除(人可随时搬回)。隔离的文件不再进入本轮 LLM 编译 = 省下的 token。

四道门(按成本从低到高,命中即停):
  1. too-short    正文 < 200 字符 —— 大概率误存/空剪藏
  2. duplicate    规范化 MD5 与既有语料完全相同 —— 精确重复
  3. near-dup     标题相似度 ≥0.85 或内容 5-gram 重叠 ≥0.5 —— 疑似重复
                  (复用 dedup-check.py 的同一实现,阈值一致)
  4. boilerplate  样板短语(cookie/登录/分享/版权等)占比 >30% —— 网页 chrome

用法:
  python3 scripts/preflight-check.py [--dry-run] [--json]
  python3 scripts/preflight-check.py --restore <quarantine 内文件名>

退出码恒为 0(预检门永不阻塞编译,只减少编译输入);报告写
reports/preflight/<日期>.json。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# dedup-check.py 文件名含连字符,不可直接 import,用 importlib 按路径加载
import importlib.util  # noqa: E402

VAULT = Path(__file__).resolve().parent.parent
CLIPPINGS = VAULT / "raw" / "clippings"
QUARANTINE = VAULT / "raw" / "quarantine"
REPORT_DIR = VAULT / "reports" / "preflight"

MIN_CHARS = 200
TITLE_SIM = 0.85
OVERLAP = 0.5
BOILERPLATE_RATIO = 0.30

# 网页剪藏常见样板(中英)。命中即计入样板字符数。
BOILERPLATE = [
    "cookie", "隐私政策", "用户协议", "服务条款", "免责声明",
    "版权所有", "保留所有权利", "all rights reserved",
    "立即登录", "免费注册", "登录后", "sign in", "log in", "subscribe",
    "分享到", "分享至", "点赞", "收藏", "关注我们", "share this",
    "阅读原文", "查看更多", "加载更多", "load more",
    "广告", "advertisement", "sponsored",
]


def _load_dedup():
    spec = importlib.util.spec_from_file_location(
        "dedup_check", str(VAULT / "scripts" / "dedup-check.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def body_text(dedup, text: str) -> str:
    """正文(去 frontmatter),用于长度与样板判定。"""
    return dedup.strip_frontmatter(text).strip()


def boilerplate_ratio(dedup, text: str) -> float:
    body = body_text(dedup, text)
    if not body:
        return 1.0
    lowered = body.lower()
    hit_chars = sum(lowered.count(p.lower()) * len(p) for p in BOILERPLATE)
    return min(1.0, hit_chars / max(1, len(body)))


def check_file(path: Path, corpus: list, dedup) -> "tuple[str | None, str]":
    """返回 (隔离原因|None, 说明)。"""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return "unreadable", f"读失败:{e}"
    body = body_text(dedup, text)
    if len(body) < MIN_CHARS:
        return "too-short", f"正文仅 {len(body)} 字符(<{MIN_CHARS})"
    chash = dedup.content_hash(text)
    ctitle = dedup.title_of(path, text)
    cshin = dedup.shingles(text)
    for cpath, ctext in corpus:
        if cpath.resolve() == path.resolve():
            continue
        if dedup.content_hash(ctext) == chash:
            return "duplicate", f"与 {cpath.name} 精确重复"
        tr = SequenceMatcher(None, ctitle, dedup.title_of(cpath, ctext)).ratio()
        ov = dedup.overlap(cshin, dedup.shingles(ctext))
        if tr >= TITLE_SIM or ov >= OVERLAP:
            why = []
            if tr >= TITLE_SIM:
                why.append(f"标题{tr:.0%}")
            if ov >= OVERLAP:
                why.append(f"内容{ov:.0%}")
            return "near-dup", f"与 {cpath.name} 疑似重复({'/'.join(why)})"
    ratio = boilerplate_ratio(dedup, text)
    if ratio > BOILERPLATE_RATIO:
        return "boilerplate", f"样板占比 {ratio:.0%}(>{BOILERPLATE_RATIO:.0%})"
    return None, "通过"


def load_corpus(exclude: set[Path]) -> list:
    dedup = _load_dedup()
    corpus = []
    for d in ["raw/archive", "raw/clippings", "raw/todo"]:
        for f in (VAULT / d).rglob("*.md"):
            if f.resolve() in exclude:
                continue
            try:
                corpus.append((f, f.read_text(encoding="utf-8")))
            except Exception:
                pass
    return corpus, dedup


def main() -> int:
    ap = argparse.ArgumentParser(description="编译前规则预检门")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--restore", metavar="NAME",
                    help="把 quarantine/<原因>/NAME 搬回 raw/clippings/")
    args = ap.parse_args()

    if args.restore:
        for qdir in QUARANTINE.glob("*"):
            src = qdir / args.restore
            if src.is_file():
                dest = CLIPPINGS / args.restore
                CLIPPINGS.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dest))
                print(f"已恢复: {qdir.name}/{args.restore} -> raw/clippings/")
                return 0
        print(f"quarantine 中找不到: {args.restore}", file=sys.stderr)
        return 0  # 预检门永不非零

    if not CLIPPINGS.is_dir():
        print("raw/clippings/ 不存在,跳过预检。")
        return 0
    candidates = sorted(CLIPPINGS.glob("*.md"))
    exclude = {p.resolve() for p in candidates}
    corpus, dedup = load_corpus(exclude)

    decisions = []
    for p in candidates:
        reason, note = check_file(p, corpus, dedup)
        decisions.append({"file": p.name, "quarantined": reason,
                          "reason": note})
        if reason and not args.dry_run:
            qdir = QUARANTINE / reason
            qdir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(qdir / p.name))

    n_q = sum(1 for d in decisions if d["quarantined"])
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPORT_DIR / f"{date.today().isoformat()}.json",
              "w", encoding="utf-8") as f:
        json.dump({"date": date.today().isoformat(), "checked": len(decisions),
                   "quarantined": n_q, "decisions": decisions},
                  f, ensure_ascii=False, indent=1)

    if args.json:
        print(json.dumps({"checked": len(decisions), "quarantined": n_q,
                          "decisions": decisions}, ensure_ascii=False))
    else:
        print(f"预检: {len(decisions)} 篇,隔离 {n_q} 篇 → raw/quarantine/")
        for d in decisions:
            if d["quarantined"]:
                print(f"  ⛔ {d['file']}: {d['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
