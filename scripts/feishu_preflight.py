#!/usr/bin/env python3
# scripts/feishu_preflight.py — 飞书冷存「写权限」前置守卫。
#
# 为什么需要它(2026-08-06 取证,见 docs/dev-log.md 同日条目):
#   冷存根 raw/private/feishu/ 软链到 Google Drive CloudStorage,该目录受 macOS TCC 保护。
#   **cron 起的进程拿不到这份授权**,而权限边界很反直觉 —— 一次性探针实测(cron 上下文):
#
#       新建文件                          → OK(进程对自己创建的项有权)
#       打开"别的上下文建的"已存在文件写   → EPERM(errno 1)
#       连 unlink / rename 覆盖也一样      → EPERM
#
#   于是 feishu-backup-messages.py 每轮崩在第一个要覆盖的会话文件上:
#   **39 次定时槽运行、0 次成功写入**,而脚本退出码一直是 0,没人知道。
#
# 所以守卫不能只问「目录在不在 / 能不能建文件」—— 那两条在 cron 下都过。
# 必须问**能不能重开一个已存在的会话文件写**,这正是流水线真正需要的能力。
#
# 只读式探测:open(p,"r+") 拿到句柄就立刻关,不写一个字节、不留任何文件。
#
# 用法:python3 scripts/feishu_preflight.py   # 通过退 0;拦下退 3 并打印修法

import os
import sys
from pathlib import Path

import larklib

FIX = """
修法(二选一):
  1)【推荐】给 cron 完全磁盘访问权限(Full Disk Access):
     系统设置 → 隐私与安全性 → 完全磁盘访问权限 → 「+」→ ⌘⇧G 输入 /usr/sbin/cron → 添加并勾选。
     这是一次性操作;加完不必重启,下一个整点的定时任务即恢复。
  2) 或把冷存根移出 ~/Library/CloudStorage(设 MIND_FEISHU_HOME 指到普通本地目录),
     代价是失去 Google Drive 那层异地备份。
注:手动在终端里跑一切正常 —— 终端继承了它自己的完全磁盘访问权限,cron 没有。
   所以「我手动跑通了」不能证明定时任务也通。"""


def _listdir(p: Path):
    """列目录,**让 OSError 冒出来**。

    绝不能用 Path.glob():它把 OSError 吞掉、返回空列表。守卫第一版就栽在这 ——
    cron 下每个目录 iterdir() 都是 EPERM,glob 静静地给了个空列表,
    守卫据此认定"没有存量可探,应属全新安装",对着真实故障报了绿灯。
    """
    return os.listdir(p)


def _candidates(root: Path, limit: int = 3):
    """挑几个**流水线真会覆盖**的存量文件当探针,取最近改动的几个。

    调用方须自行处理 OSError —— 列不出目录本身就是故障信号,不是"没有候选"。
    """
    subs = (("messages", ".jsonl"), ("messages/groups", ".jsonl"))
    found = []
    for sub, ext in subs:
        d = root / sub
        if not d.is_dir():
            continue
        found += [d / n for n in _listdir(d) if n.endswith(ext)]
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return found[:limit]


def check(root):
    """→ (ok: bool, why: str)。ok=True 时 why 为空串。只读,不落任何文件。"""
    root = Path(root)
    if not root.exists():
        return False, (f"冷存根不存在:{root}\n"
                       "  (Google Drive 未挂载 / raw/private 软链断了 / MIND_FEISHU_HOME 指错?)")
    if not root.is_dir():
        return False, f"冷存根不是目录:{root}"

    # ① 先问「能不能列目录」。这是最直接的信号,且**全新安装也能通过**(空目录列出来是空列表)。
    #    真实故障下这一步就是 EPERM —— 比"找不到候选文件"精确得多。
    try:
        _listdir(root)
        cands = _candidates(root)
    except OSError as e:
        return False, (
            f"列不出冷存目录:{root}\n"
            f"  [Errno {e.errno}] {e.strerror}\n"
            "  —— 本进程连目录内容都看不到。这是 macOS TCC 在挡:\n"
            "     冷存在 ~/Library/CloudStorage(Google Drive)下,cron 起的进程没有该目录的授权。\n"
            f"{FIX}")

    # ② 再问「能不能重开一个已存在的会话文件写」—— 流水线真正需要的能力。
    if not cands:
        # 全新安装:没有存量可探,只能退而求其次问目录本身可写
        if not os.access(root, os.W_OK | os.X_OK):
            return False, f"冷存根不可写:{root}\n{FIX}"
        return True, ""

    for p in cands:
        try:
            with open(p, "r+"):
                pass
        except OSError as e:
            return False, (
                f"存量文件打不开写:{p}\n"
                f"  [Errno {e.errno}] {e.strerror}\n"
                "  —— 本进程能建新文件,却动不了已存在的文件。这是 macOS TCC 在挡:\n"
                "     冷存在 ~/Library/CloudStorage(Google Drive)下,cron 起的进程没有该目录的授权。\n"
                f"{FIX}")
    return True, ""


def main():
    vault = Path(__file__).resolve().parent.parent
    root = larklib.feishu_root(vault)
    ok, why = check(root)
    if ok:
        print(f"✔ 冷存写权限正常:{root}")
        return 0
    print(f"✗ 飞书冷存前置检查未通过\n{why}", file=sys.stderr)
    return 3


if __name__ == "__main__":
    sys.exit(main())
