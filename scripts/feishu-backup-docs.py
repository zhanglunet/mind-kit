#!/usr/bin/env python3
# scripts/feishu-backup-docs.py
# 备份飞书云文档(docx)为 Markdown → raw/private/feishu/docs/(Google Drive 冷存、git 忽略)
# 依赖:已安装并授权的 lark-cli(token 在系统钥匙串;凭据不入库)。
#
# 用法:
#   python3 scripts/feishu-backup-docs.py                 # 增量备份我拥有的全部 docx
#   python3 scripts/feishu-backup-docs.py --limit 3       # 只跑前 3 篇(冒烟测试)
#   python3 scripts/feishu-backup-docs.py --force         # 忽略增量,全部重取
#   python3 scripts/feishu-backup-docs.py --doc-types docx,doc
#
# 增量:按 token 记录 update_time 到 _meta/docs-state.json;未变则跳过。

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import larklib

VAULT = Path(__file__).resolve().parent.parent
FEISHU = larklib.feishu_root(VAULT)
OUT = FEISHU / "docs"
META = FEISHU / "_meta"
STATE_FILE = META / "docs-state.json"


def run_lark(args, timeout=180):
    """调用 lark-cli,返回解析后的 JSON(失败抛异常,带原始输出)。"""
    proc = subprocess.run(
        larklib.lark_argv([*args, "--json"]),
        capture_output=True, text=True, timeout=timeout,
    )
    out = proc.stdout.strip()
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        raise RuntimeError(f"lark-cli 非 JSON 输出: {out[:300]} | stderr: {proc.stderr[:200]}")
    return data


def is_rate_limited(data):
    err = (data or {}).get("error") or {}
    msg = json.dumps(err, ensure_ascii=False)
    return "rate" in msg.lower() or err.get("code") in (99991400, 99991661)


def call_with_retry(args, what, retries=3):
    for attempt in range(retries):
        try:
            data = run_lark(args)
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
            continue
        if data.get("ok"):
            return data
        if is_rate_limited(data) and attempt < retries - 1:
            time.sleep(5 * (attempt + 1))
            continue
        raise RuntimeError(f"{what} 失败: {json.dumps(data.get('error'), ensure_ascii=False)}")
    raise RuntimeError(f"{what} 重试耗尽")


def iter_owned_docs(doc_types):
    """分页枚举我拥有的文档,yield result_meta 字典。"""
    page_token = None
    while True:
        args = ["drive", "+search", "--mine", "--doc-types", doc_types,
                "--query", "", "--page-size", "20"]
        if page_token:
            args += ["--page-token", page_token]
        data = call_with_retry(args, "drive +search")["data"]
        for item in data.get("results", []):
            meta = item.get("result_meta") or {}
            meta["_title"] = strip_tags(item.get("title_highlighted") or meta.get("title") or "")
            if meta.get("token"):
                yield meta
        if not data.get("has_more"):
            break
        page_token = data.get("page_token")
        if not page_token:
            break


def strip_tags(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


def safe_filename(title, token):
    t = re.sub(r'[/\\:*?"<>|\n\r\t]+', "_", title or "").strip()
    t = re.sub(r"\s+", " ", t)
    if len(t) > 80:
        t = t[:80].rstrip()
    if not t:
        t = "untitled"
    return f"{t}__{token}.md"


def fetch_markdown(token):
    data = call_with_retry(
        ["docs", "+fetch", "--doc", token, "--doc-format", "markdown"],
        f"docs +fetch {token}",
    )
    return (((data.get("data") or {}).get("document") or {}).get("content")) or ""


def build_frontmatter(meta):
    def esc(v):
        return json.dumps(str(v), ensure_ascii=False)
    lines = [
        "---",
        f"title: {esc(meta.get('_title'))}",
        "source: feishu-docx",
        f"feishu_url: {meta.get('url', '')}",
        f"feishu_token: {meta.get('token', '')}",
        f"owner: {esc(meta.get('owner_name', ''))}",
        f"created: {meta.get('create_time_iso', '')}",
        f"updated: {meta.get('update_time_iso', '')}",
        f"fetched: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        "---",
        "",
    ]
    return "\n".join(lines)


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(state):
    META.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="备份飞书云文档为 Markdown")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 篇(0=全部)")
    ap.add_argument("--force", action="store_true", help="忽略增量,全部重取")
    ap.add_argument("--doc-types", default="docx", help="文档类型,逗号分隔(默认 docx)")
    ap.add_argument("--sleep", type=float, default=0.3, help="每篇之间的间隔秒数")
    args = ap.parse_args()

    if not OUT.exists():
        print(f"❌ 输出目录不存在:{OUT}\n   请确认 raw/private 已软链到 Google Drive 冷存。", file=sys.stderr)
        sys.exit(1)

    state = {} if args.force else load_state()
    OUT.mkdir(parents=True, exist_ok=True)

    print(f"→ 枚举我拥有的文档(类型:{args.doc_types})...")
    metas = list(iter_owned_docs(args.doc_types))
    print(f"  共 {len(metas)} 篇")
    if args.limit:
        metas = metas[: args.limit]
        print(f"  --limit 生效,只处理前 {len(metas)} 篇")

    written = skipped = failed = 0
    for i, meta in enumerate(metas, 1):
        token = meta["token"]
        title = meta.get("_title") or token
        upd = meta.get("update_time") or meta.get("update_time_iso")
        prev = state.get(token)
        fname = safe_filename(title, token)
        fpath = OUT / fname

        if (not args.force and prev and str(prev.get("update_time")) == str(upd)
                and fpath.exists()):
            skipped += 1
            print(f"  [{i}/{len(metas)}] 跳过(未变) {title[:40]}")
            continue

        try:
            content = fetch_markdown(token)
        except Exception as e:
            failed += 1
            print(f"  [{i}/{len(metas)}] ✗ {title[:40]} — {e}", file=sys.stderr)
            continue

        # 清理旧文件名(标题改动时避免留孤儿)
        if prev and prev.get("file") and prev["file"] != fname:
            old = OUT / prev["file"]
            if old.exists():
                old.unlink()

        fpath.write_text(build_frontmatter(meta) + content, encoding="utf-8")
        state[token] = {"update_time": upd, "file": fname, "title": title,
                        "url": meta.get("url", "")}
        written += 1
        print(f"  [{i}/{len(metas)}] ✓ {title[:40]}  ({len(content)} 字)")
        save_state(state)  # 边写边存,可随时中断续跑
        time.sleep(args.sleep)

    print(f"\n完成:写入 {written} · 跳过 {skipped} · 失败 {failed}")
    print(f"产物:{OUT}")
    print(f"指纹:{STATE_FILE}")


if __name__ == "__main__":
    main()
