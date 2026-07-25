#!/usr/bin/env python3
# scripts/localize-images.py
# 把 Markdown 里的外链图片下载到 raw/assets/ 并改成本地相对路径(FR-AUT-05 / 开发计划 P2-3)。
# 默认处理 raw/clippings 与 raw/todo;不碰 raw/private(冷存)。
# 带 auth code 的外链图可能已过期,下载失败会**保留原外链**并计入报告(尽力而为)。
#
# 用法:
#   python3 scripts/localize-images.py                    # 处理 raw/clippings + raw/todo
#   python3 scripts/localize-images.py raw/clippings/x.md # 指定文件
#   python3 scripts/localize-images.py --dir material     # 指定目录
#   python3 scripts/localize-images.py --dry-run          # 只报告不下载、不改写

import argparse
import hashlib
import os
import re
import sys
import urllib.request
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
ASSETS = VAULT / "raw" / "assets"
IMG_RE = re.compile(r'!\[([^\]]*)\]\((https?://[^)\s]+)\)')
EXT_BY_MIME = {
    "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
    "image/webp": ".webp", "image/svg+xml": ".svg", "image/bmp": ".bmp",
    "image/tiff": ".tiff",
}


def guess_ext(url, ctype):
    if ctype in EXT_BY_MIME:
        return EXT_BY_MIME[ctype]
    m = re.search(r"\.(png|jpg|jpeg|gif|webp|svg|bmp|tiff?)(?:\?|$)", url, re.I)
    if m:
        e = m.group(1).lower()
        return ".jpg" if e == "jpeg" else "." + e
    return ".png"


def download(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
        ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if not data:
        raise RuntimeError("空响应")
    return data, ctype


def rel(p):
    try:
        return p.resolve().relative_to(VAULT)
    except ValueError:
        return p


def iter_targets(args):
    if args.paths:
        for p in args.paths:
            yield Path(p).resolve()
        return
    dirs = [args.dir] if args.dir else ["raw/clippings", "raw/todo"]
    for d in dirs:
        for f in sorted((VAULT / d).rglob("*.md")):
            yield f


def main():
    ap = argparse.ArgumentParser(description="外链图片本地化到 raw/assets/")
    ap.add_argument("paths", nargs="*", help="指定 md 文件(默认扫 raw/clippings + raw/todo)")
    ap.add_argument("--dir", help="指定目录(相对 vault 根)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ASSETS.mkdir(parents=True, exist_ok=True)
    cache = {}  # url -> asset Path(已下好)
    n_files = n_localized = n_failed = n_cached = 0

    for md in iter_targets(args):
        if not md.exists() or "raw/private" in str(md):
            continue
        text = md.read_text(encoding="utf-8")
        fails, hits = [], [0]

        def repl(m):
            alt, url = m.group(1), m.group(2)
            asset = cache.get(url)
            if asset is None:
                h = hashlib.sha1(url.encode()).hexdigest()[:12]
                existing = list(ASSETS.glob(h + ".*"))
                if existing:
                    asset = existing[0]
                elif args.dry_run:
                    hits[0] += 1
                    return m.group(0)  # dry-run 不下载
                else:
                    try:
                        data, ctype = download(url)
                    except Exception as e:
                        fails.append(f"{url[:60]}… ({e})")
                        return m.group(0)  # 失败保留原链
                    asset = ASSETS / (h + guess_ext(url, ctype))
                    asset.write_bytes(data)
                cache[url] = asset
            relpath = os.path.relpath(asset, md.parent)
            hits[0] += 1
            return f"![{alt}]({relpath})"

        new = IMG_RE.sub(repl, text)
        ext_imgs = len(IMG_RE.findall(text))
        if ext_imgs == 0:
            continue
        n_files += 1
        if args.dry_run:
            print(f"  [dry] {rel(md)} — 外链图 {ext_imgs}")
            continue
        if new != text:
            md.write_text(new, encoding="utf-8")
        done = hits[0]   # hits[0] 只计成功(失败在自增前已 return)
        n_localized += done
        n_failed += len(fails)
        print(f"  {rel(md)} — 本地化 {done}/{ext_imgs}" + (f",失败 {len(fails)}" if fails else ""))
        for fa in fails[:3]:
            print(f"      ✗ {fa}")

    print(f"\n完成:处理 {n_files} 个含图文件 · 本地化 {n_localized} 张 · 失败 {n_failed} 张")
    print(f"资产目录:{ASSETS}(git 忽略,随 vault 本地留存)")


if __name__ == "__main__":
    main()
