#!/usr/bin/env python3
# scripts/feishu-backup-wiki.py
# 备份飞书知识库(wiki)文档为 Markdown → raw/private/feishu/wiki/<空间>/<路径>/...
# 依赖:已授权的 lark-cli。复用 docs +fetch 的 markdown 导出。
#
# 用法:
#   python3 scripts/feishu-backup-wiki.py --count-only          # 只枚举、报每个空间的节点规模(不取正文)
#   python3 scripts/feishu-backup-wiki.py --spaces my_library   # 只备份个人库
#   python3 scripts/feishu-backup-wiki.py --spaces 7268...,7267...  # 指定空间 ID(逗号分隔)
#   python3 scripts/feishu-backup-wiki.py                        # 备份全部空间(增量)
#   python3 scripts/feishu-backup-wiki.py --force               # 忽略增量重取
#
# 只导出 docx/doc 节点为 md;sheet/bitable/mindnote/file 等仅记录到清单(交给云盘下载脚本)。

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import larklib

VAULT = Path(__file__).resolve().parent.parent
FEISHU = larklib.feishu_root(VAULT)
OUT = FEISHU / "wiki"
META = FEISHU / "_meta"
STATE_FILE = META / "wiki-state.json"
NONDOC_MANIFEST = META / "wiki-nondoc.json"

MD_TYPES = {"docx", "doc"}


def run_lark(args, timeout=180):
    proc = subprocess.run(larklib.lark_argv([*args, "--json"]), capture_output=True, text=True, timeout=timeout)
    try:
        return json.loads(proc.stdout.strip())
    except json.JSONDecodeError:
        raise RuntimeError(f"lark-cli 非 JSON: {proc.stdout[:200]} | {proc.stderr[:200]}")


def call(args, what, retries=3):
    for attempt in range(retries):
        try:
            data = run_lark(args)
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


def find_list(o, keys):
    if isinstance(o, dict):
        for k in keys:
            if isinstance(o.get(k), list):
                return o[k]
        for v in o.values():
            r = find_list(v, keys)
            if r is not None:
                return r
    return None


def list_spaces():
    data = call(["wiki", "+space-list", "--page-all"], "wiki +space-list")
    spaces = find_list(data, ("items", "spaces", "results")) or []
    out = [{"space_id": "my_library", "name": "个人库(my_library)"}]
    for s in spaces:
        out.append({"space_id": s.get("space_id"), "name": s.get("name") or s.get("space_id")})
    return out


def list_nodes(space_id, parent=None):
    args = ["wiki", "+node-list", "--space-id", space_id, "--page-all"]
    if parent:
        args += ["--parent-node-token", parent]
    data = call(args, f"node-list {space_id}")
    return find_list(data, ("items", "nodes", "results")) or []


def walk(space_id, parent=None, path=(), depth=0, max_depth=20):
    if depth > max_depth:
        return
    for n in list_nodes(space_id, parent):
        yield n, path
        if n.get("has_child"):
            title = strip_tags(n.get("title") or n.get("node_token"))
            yield from walk(space_id, n.get("node_token"), path + (title,), depth + 1, max_depth)


def strip_tags(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


def safe(s, maxlen=80):
    s = re.sub(r'[/\\:*?"<>|\n\r\t]+', "_", s or "").strip()
    s = re.sub(r"\s+", " ", s)
    if len(s) > maxlen:
        s = s[:maxlen].rstrip()
    return s or "untitled"


def fetch_markdown(obj_token):
    data = call(["docs", "+fetch", "--doc", obj_token, "--doc-format", "markdown"], f"fetch {obj_token}")
    return (((data.get("data") or {}).get("document") or {}).get("content")) or ""


def frontmatter(space_name, title, node):
    def esc(v): return json.dumps(str(v), ensure_ascii=False)
    return "\n".join([
        "---",
        f"title: {esc(title)}",
        "source: feishu-wiki",
        f"space: {esc(space_name)}",
        f"obj_type: {node.get('obj_type', '')}",
        f"node_token: {node.get('node_token', '')}",
        f"obj_token: {node.get('obj_token', '')}",
        f"fetched: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        "---", "",
    ])


def load(p):
    if p.exists():
        try: return json.loads(p.read_text(encoding="utf-8"))
        except Exception: pass
    return {}


def main():
    ap = argparse.ArgumentParser(description="备份飞书知识库为 Markdown")
    ap.add_argument("--spaces", default="", help="空间 ID 逗号分隔(含 my_library);留空=全部")
    ap.add_argument("--count-only", action="store_true", help="只枚举报规模,不取正文")
    ap.add_argument("--force", action="store_true", help="忽略增量重取")
    ap.add_argument("--sleep", type=float, default=0.3)
    args = ap.parse_args()

    if not OUT.parent.exists():
        print(f"❌ {OUT.parent} 不存在,请确认 raw/private 已软链 Google Drive", file=sys.stderr); sys.exit(1)
    META.mkdir(parents=True, exist_ok=True)

    all_spaces = list_spaces()
    if args.spaces:
        want = set(x.strip() for x in args.spaces.split(","))
        spaces = [s for s in all_spaces if s["space_id"] in want]
    else:
        spaces = all_spaces
    print(f"→ 将处理 {len(spaces)} 个空间" + ("(仅计数)" if args.count_only else ""))

    state = {} if args.force else load(STATE_FILE)
    nondoc = load(NONDOC_MANIFEST)
    grand = {"md": 0, "nondoc": 0, "written": 0, "skipped": 0, "failed": 0}

    for sp in spaces:
        sid, sname = sp["space_id"], sp["name"]
        print(f"\n── 空间:{sname} ({sid})")
        per = {}
        try:
            nodes = list(walk(sid))
        except Exception as e:
            print(f"   ✗ 枚举失败:{e}", file=sys.stderr); continue
        for n, path in nodes:
            per[n.get("obj_type", "?")] = per.get(n.get("obj_type", "?"), 0) + 1
        print("   节点类型分布:", per, f"(共 {len(nodes)})")

        if args.count_only:
            grand["md"] += sum(v for k, v in per.items() if k in MD_TYPES)
            grand["nondoc"] += sum(v for k, v in per.items() if k not in MD_TYPES)
            continue

        space_dir = OUT / safe(sname)
        for n, path in nodes:
            otype = n.get("obj_type")
            title = strip_tags(n.get("title") or n.get("node_token"))
            rel = space_dir.joinpath(*[safe(p) for p in path])
            if otype in MD_TYPES:
                obj = n.get("obj_token")
                key = n.get("node_token")
                if not args.force and state.get(key) and (rel / f"{safe(title)}__{obj}.md").exists():
                    grand["skipped"] += 1; continue
                try:
                    content = fetch_markdown(obj)
                except Exception as e:
                    grand["failed"] += 1; print(f"   ✗ {title[:36]} — {e}", file=sys.stderr); continue
                rel.mkdir(parents=True, exist_ok=True)
                fp = rel / f"{safe(title)}__{obj}.md"
                fp.write_text(frontmatter(sname, title, n) + content, encoding="utf-8")
                state[key] = {"file": str(fp.relative_to(OUT)), "title": title, "obj_token": obj}
                STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
                grand["written"] += 1
                print(f"   ✓ {'/'.join(path)+'/' if path else ''}{title[:36]}")
                time.sleep(args.sleep)
            else:
                # 非文档节点(表格/多维表/思维笔记/文件),记清单交给云盘下载脚本
                nondoc[n.get("node_token")] = {"space": sname, "title": title, "obj_type": otype,
                                               "obj_token": n.get("obj_token"), "path": list(path)}
                grand["nondoc"] += 1
        NONDOC_MANIFEST.write_text(json.dumps(nondoc, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n==== 汇总 ====")
    if args.count_only:
        print(f"可导出 md 的节点(docx/doc):{grand['md']}")
        print(f"非文档节点(表格/多维表/文件等):{grand['nondoc']}")
        print("→ 用 --spaces <id,...> 选择要备份的空间,或直接跑(全部)。")
    else:
        print(f"写入 {grand['written']} · 跳过 {grand['skipped']} · 失败 {grand['failed']} · 非文档记入清单 {grand['nondoc']}")
        print(f"产物:{OUT}")


if __name__ == "__main__":
    main()
