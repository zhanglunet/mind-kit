"""feishu_preflight 的行为测试(飞书冷存写权限前置守卫)。

存在的理由(2026-08-06 实测):冷存根 `raw/private/feishu/` 软链到 Google Drive
CloudStorage,而 **cron 起的进程拿不到该目录的 TCC 授权**。实测边界很刁钻:

  · 新建文件      → 允许(进程对自己创建的项有权限)
  · 打开"别的上下文创建的"已存在文件写 → EPERM(errno 1),连 unlink / rename 覆盖都不行

于是 `feishu-backup-messages.py` 每轮崩在第一个要覆盖的会话文件上 ——
39 次定时槽运行、**0 次成功写入**,而脚本退出码一直是 0。

所以守卫不能只问"目录在不在 / 能不能建文件"(那两条 cron 下都过),
必须问**能不能重开一个已存在的文件写** —— 这正是流水线真正需要的能力。
"""
import errno
import os
import subprocess
import sys
from pathlib import Path

import pytest

import feishu_preflight as P

REPO = Path(__file__).resolve().parent.parent


def test_missing_root_fails(tmp_path):
    ok, why = P.check(tmp_path / "不存在")
    assert ok is False
    assert "不存在" in why or "未挂载" in why, why


def test_empty_but_writable_root_passes(tmp_path):
    """全新安装:目录在、可建文件、但还没有任何会话文件 → 放行(没有可探的存量)。"""
    ok, why = P.check(tmp_path)
    assert ok is True, why


def test_existing_file_reopenable_passes(tmp_path):
    (tmp_path / "messages").mkdir()
    (tmp_path / "messages" / "张三__TESTCHAT.jsonl").write_text("{}\n", encoding="utf-8")
    ok, why = P.check(tmp_path)
    assert ok is True, why


def test_existing_file_write_denied_fails(tmp_path, monkeypatch):
    """核心用例:存量文件打不开写 → 必须拦下,且给出可执行的修法。

    真实故障是 TCC 拒绝(EPERM);这里用 monkeypatch 精确复现该 errno,
    不依赖 chmod(chmod 给的是 EACCES=13,与真实故障不同型)。
    """
    (tmp_path / "messages").mkdir()
    victim = tmp_path / "messages" / "张三__TESTCHAT.jsonl"
    victim.write_text("{}\n", encoding="utf-8")

    real_open = open

    def fake_open(path, mode="r", *a, **kw):
        if str(path) == str(victim) and "+" in mode:
            raise PermissionError(errno.EPERM, "Operation not permitted", str(path))
        return real_open(path, mode, *a, **kw)

    monkeypatch.setattr("builtins.open", fake_open)
    ok, why = P.check(tmp_path)
    assert ok is False
    assert "Operation not permitted" in why or "EPERM" in why or "权限" in why, why
    # 可执行指引:必须点名 cron 与「完全磁盘访问权限」,否则看到红卡也不知道去哪修
    assert "cron" in why and ("完全磁盘访问" in why or "Full Disk Access" in why), why


def test_unlistable_root_fails(tmp_path, monkeypatch):
    """守卫第一版在真机上放行了故障 —— 这条锁住那个洞。

    实测(cron 上下文):冷存里**每个目录 iterdir() 都是 EPERM**,连列都列不出来;
    而 `Path.glob()` 会把 OSError 吞掉、返回空列表。于是守卫拿到"零个候选文件",
    走进「全新安装,没有存量可探」那条分支,报了绿灯。

    「看不见任何存量」在真实故障里恰恰是**最危险**的状态,不能当成全新安装放行。
    """
    (tmp_path / "messages").mkdir()
    (tmp_path / "messages" / "张三__TESTCHAT.jsonl").write_text("{}\n", encoding="utf-8")
    real_listdir = os.listdir

    def fake_listdir(path, *a, **kw):
        if str(path).startswith(str(tmp_path)):
            raise PermissionError(errno.EPERM, "Operation not permitted", str(path))
        return real_listdir(path, *a, **kw)

    monkeypatch.setattr(os, "listdir", fake_listdir)
    ok, why = P.check(tmp_path)
    assert ok is False, "列不出目录却报绿灯 —— 正是真机上放行故障的那条路径"
    assert "cron" in why and ("完全磁盘访问" in why or "Full Disk Access" in why), why


def test_writes_nothing_into_the_store(tmp_path):
    """守卫本身不得留下垃圾文件(它每天在真实冷存上跑)。"""
    (tmp_path / "messages").mkdir()
    (tmp_path / "messages" / "张三__TESTCHAT.jsonl").write_text("{}\n", encoding="utf-8")
    before = {p.name for p in (tmp_path / "messages").iterdir()}
    P.check(tmp_path)
    assert {p.name for p in (tmp_path / "messages").iterdir()} == before


def test_does_not_modify_the_probed_file(tmp_path):
    (tmp_path / "messages").mkdir()
    victim = tmp_path / "messages" / "张三__TESTCHAT.jsonl"
    victim.write_text('{"a":1}\n', encoding="utf-8")
    P.check(tmp_path)
    assert victim.read_text(encoding="utf-8") == '{"a":1}\n', "守卫只许试开,不许改内容"


def test_cli_exit_zero_when_ok(tmp_path):
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "feishu_preflight.py")],
                       capture_output=True, text=True,
                       env={**os.environ, "MIND_FEISHU_HOME": str(tmp_path)})
    assert r.returncode == 0, r.stdout + r.stderr


def test_cli_exit_nonzero_when_root_missing(tmp_path):
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "feishu_preflight.py")],
                       capture_output=True, text=True,
                       env={**os.environ, "MIND_FEISHU_HOME": str(tmp_path / "没有这个目录")})
    assert r.returncode != 0
    assert (r.stdout + r.stderr).strip(), "拦下时必须说清为什么"
