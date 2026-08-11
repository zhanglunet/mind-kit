#!/usr/bin/env python3
# scripts/feishu-backup-files.py
# 备份飞书云盘"文件"(PDF/office/图片等真实文件,非在线文档)→ raw/private/feishu/files/
# 依赖:已授权 lark-cli。用 drive +search(search:docs:read) 枚举 + drive +download(drive:file:download)下载,
#       绕开被禁用的 space:document:retrieve(所以没走 drive +pull)。
#
# 用法:
#   python3 scripts/feishu-backup-files.py --limit 3     # 冒烟测试
#   python3 scripts/feishu-backup-files.py               # 全量增量下载我拥有的文件
#   python3 scripts/feishu-backup-files.py --force
#
# 下载进 Google Drive 流式冷存(下载即上传即释放);带磁盘余量守卫防撑爆。

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import larklib

VAULT = Path(__file__).resolve().parent.parent
FEISHU = larklib.feishu_root(VAULT)
FILES_LINK = FEISHU / "files"          # 软链
META = FEISHU / "_meta"
STATE_FILE = META / "files-state.json"
MIN_FREE_GB = 2.0                       # 本地可用空间低于此值即停


def run_lark(args, cwd=None, timeout=600):
    proc = subprocess.run(larklib.lark_argv([*args, "--json"]), capture_output=True, text=True,
                          cwd=cwd, timeout=timeout)
    try:
        return json.loads(proc.stdout.strip()), proc.stderr
    except json.JSONDecodeError:
        raise RuntimeError(f"lark-cli 非 JSON: {proc.stdout[:200]} | {proc.stderr[:200]}")


def call(args, what, cwd=None, retries=3, timeout=600):
    for attempt in range(retries):
        try:
            data, _ = run_lark(args, cwd=cwd, timeout=timeout)
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1)); continue
        if data.get("ok"):
            return data
        msg = json.dumps(data.get("error"), ensure_ascii=False)
        if "rate" in msg.lower() and attempt < retries - 1:
            time.sleep(5 * (attempt + 1)); continue
        raise RuntimeError(f"{what} 失败: {msg}")
    raise RuntimeError(f"{what} 重试耗尽")


def iter_files():
    page_token = None
    while True:
        args = ["drive", "+search", "--mine", "--doc-types", "file", "--query", "", "--page-size", "20"]
        if page_token:
            args += ["--page-token", page_token]
        data = call(args, "drive +search file")["data"]
        for it in data.get("results", []):
            rm = it.get("result_meta") or {}
            rm["_title"] = strip_tags(it.get("title_highlighted") or rm.get("title") or rm.get("token"))
            if rm.get("token"):
                yield rm
        if not data.get("has_more"):
            break
        page_token = data.get("page_token")
        if not page_token:
            break


def strip_tags(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


def safe(s):
    s = re.sub(r'[/\\:*?"<>|\n\r\t]+', "_", s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s or "untitled"


def target_name(title, token):
    name = safe(title)
    stem, ext = os.path.splitext(name)
    if not ext or len(ext) > 6:
        stem, ext = name, ""
    if len(stem) > 80:
        stem = stem[:80].rstrip()
    return f"{stem}__{token}{ext}"


def free_gb():
    return shutil.disk_usage(os.path.expanduser("~")).free / 1024**3


def load(p):
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def main():
    ap = argparse.ArgumentParser(description="备份飞书云盘文件")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.4)
    args = ap.parse_args()

    if not FILES_LINK.exists():
        print(f"❌ {FILES_LINK} 不存在(raw/private 是否已软链 Google Drive?)", file=sys.stderr); sys.exit(1)
    files_dir = FILES_LINK.resolve()   # 解析软链→ Google Drive 真实路径,作为下载 cwd
    files_dir.mkdir(parents=True, exist_ok=True)
    META.mkdir(parents=True, exist_ok=True)

    state = {} if args.force else load(STATE_FILE)

    print("→ 枚举我拥有的云盘文件...")
    metas = list(iter_files())
    print(f"  共 {len(metas)} 个文件")
    if args.limit:
        metas = metas[: args.limit]
        print(f"  --limit 生效,只处理前 {len(metas)} 个")

    dl = skipped = failed = 0
    for i, m in enumerate(metas, 1):
        token = m["token"]
        title = m.get("_title") or token
        upd = m.get("update_time")
        fname = target_name(title, token)
        fpath = files_dir / fname

        if (not args.force and state.get(token)
                and str(state[token].get("update_time")) == str(upd) and fpath.exists()):
            skipped += 1
            continue

        fg = free_gb()
        if fg < MIN_FREE_GB:
            print(f"\n⛔ 本地可用空间仅 {fg:.1f}G(< {MIN_FREE_GB}G),停止下载以防撑爆。"
                  f"\n   已下 {dl} 个;稍后腾出空间或确认 Google Drive 已释放本地副本后再续跑(增量)。", file=sys.stderr)
            break

        try:
            call(["drive", "+download", "--file-token", token, "--output", f"./{fname}", "--overwrite"],
                 f"download {token}", cwd=str(files_dir))
        except Exception as e:
            failed += 1
            print(f"  [{i}/{len(metas)}] ✗ {title[:40]} — {e}", file=sys.stderr)
            continue

        if not fpath.exists():
            failed += 1
            print(f"  [{i}/{len(metas)}] ✗ {title[:40]} — 下载后文件不存在", file=sys.stderr)
            continue

        size = fpath.stat().st_size
        state[token] = {"update_time": upd, "file": fname, "title": title,
                        "url": m.get("url", ""), "size": size}
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        dl += 1
        print(f"  [{i}/{len(metas)}] ✓ {title[:40]}  ({size/1024/1024:.2f}MB, free {fg:.1f}G)")
        time.sleep(args.sleep)

    print(f"\n完成:下载 {dl} · 跳过 {skipped} · 失败 {failed}")
    print(f"产物:{files_dir}")


if __name__ == "__main__":
    main()
