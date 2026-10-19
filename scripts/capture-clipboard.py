#!/usr/bin/env python3
"""scripts/capture-clipboard.py —— 剪贴板一键采集进 raw/clippings/。

把当前剪贴板文本存为 `raw/clippings/<时间戳>-clipboard.md`,带来源
frontmatter,供 sage-wiki 编译流水线自动摄入。静默采集三件套之一
(另见 scripts/capture-watch.sh 与 docs/guide/capture-hooks.md)。

跨平台取剪贴板:
  macOS   : pbpaste
  Linux   : xclip / xsel (按此顺序探测)
  Windows : powershell Get-Clipboard -Raw

退出码: 0 存入成功; 2 跳过(剪贴板为空或与上一次采集内容重复);
        1 出错。

用法:
  python3 scripts/capture-clipboard.py [--dry-run]

幂等/去重: 与最近一次 *-clipboard.md 的正文逐字节比对,重复则跳过,
避免连按快捷键产生重复条目。
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

VAULT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIPPINGS = os.path.join(VAULT, "raw", "clippings")
FILENAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{6}-clipboard(-[0-9a-f]{8})?\.md$")


def read_clipboard() -> str:
    """按平台读取剪贴板文本;取不到时返回空字符串。"""
    if sys.platform == "darwin":
        return _run(["pbpaste"])
    if sys.platform == "win32":
        out = _run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"])
        return out
    # Linux / 其他:依次探测 xclip、xsel
    if shutil.which("xclip"):
        return _run(["xclip", "-o", "-selection", "clipboard"])
    if shutil.which("xsel"):
        return _run(["xsel", "--clipboard", "--output"])
    return ""


def _run(cmd: list[str]) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if p.returncode != 0:
        return ""
    return p.stdout


def latest_clipboard_body() -> str | None:
    """最近一次剪贴板采集的正文(去 frontmatter);没有则返回 None。"""
    if not os.path.isdir(CLIPPINGS):
        return None
    cands = sorted(f for f in os.listdir(CLIPPINGS) if FILENAME_RE.match(f))
    if not cands:
        return None
    with open(os.path.join(CLIPPINGS, cands[-1]), encoding="utf-8") as fh:
        text = fh.read()
    # 去掉 --- frontmatter --- 头
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[end + 5 :]
    return text


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    body = read_clipboard().strip("\n")
    if not body.strip():
        print("剪贴板为空,跳过。")
        return 2
    prev = latest_clipboard_body()
    if prev is not None and prev.strip("\n") == body:
        print("与上一次采集内容相同,跳过(去重)。")
        return 2

    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:8]
    fname = f"{stamp}-clipboard-{digest}.md"
    frontmatter = (
        "---\n"
        "source: clipboard\n"
        f"captured_at: {datetime.now().isoformat(timespec='seconds')}\n"
        "---\n\n"
    )
    if dry:
        print(f"[dry-run] 将写入 raw/clippings/{fname} ({len(body)} 字符)")
        return 0
    os.makedirs(CLIPPINGS, exist_ok=True)
    with open(os.path.join(CLIPPINGS, fname), "w", encoding="utf-8") as fh:
        fh.write(frontmatter + body + "\n")
    print(f"已采集 -> raw/clippings/{fname}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
