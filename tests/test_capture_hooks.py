"""静默采集三件套测试: capture-clipboard.py / capture-watch.sh。

约定: 不碰真实剪贴板、不碰真实 ~/mind-inbox;全部用临时目录 + 环境变量隔离。
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIP_PY = os.path.join(REPO, "scripts", "capture-clipboard.py")
WATCH_SH = os.path.join(REPO, "scripts", "capture-watch.sh")


@pytest.fixture()
def vault(tmp_path):
    """伪造一个最小 vault:raw/clippings + 可写的 HOME。"""
    (tmp_path / "raw" / "clippings").mkdir(parents=True)
    (tmp_path / ".git").mkdir()
    return tmp_path


def run_clip(monkeypatch, vault, clip_text, argv=()):
    """用 fake pbpaste/xclip 喂剪贴板内容,跑 capture-clipboard.py。"""
    bindir = vault / "bin"
    bindir.mkdir(exist_ok=True)
    fake = bindir / ("pbpaste" if sys.platform == "darwin" else "xclip")
    fake.write_text("#!/bin/sh\nprintf %s \"$CLIP_TEXT\"\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("CLIP_TEXT", clip_text)
    # 让脚本把 VAULT 解析到伪 vault:复制脚本到临时位并改 VAULT 常量
    script = vault / "capture-clipboard.py"
    src = open(CLIP_PY, encoding="utf-8").read()
    src = src.replace(
        'VAULT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))',
        f'VAULT = {str(vault)!r}',
    )
    script.write_text(src, encoding="utf-8")
    p = subprocess.run(
        [sys.executable, str(script), *argv],
        capture_output=True, text=True, timeout=30,
    )
    return p


def clip_files(vault):
    d = vault / "raw" / "clippings"
    return sorted(f.name for f in d.iterdir() if f.is_file())


def test_clipboard_saves_with_frontmatter(monkeypatch, vault):
    p = run_clip(monkeypatch, vault, "hello 知识")
    assert p.returncode == 0, p.stderr
    files = clip_files(vault)
    assert len(files) == 1
    assert re.match(r"^\d{4}-\d{2}-\d{2}-\d{6}-clipboard-[0-9a-f]{8}\.md$", files[0])
    text = (vault / "raw" / "clippings" / files[0]).read_text(encoding="utf-8")
    assert text.startswith("---\nsource: clipboard\ncaptured_at: ")
    assert "hello 知识" in text


def test_clipboard_empty_skipped(monkeypatch, vault):
    p = run_clip(monkeypatch, vault, "   \n  ")
    assert p.returncode == 2
    assert clip_files(vault) == []


def test_clipboard_duplicate_skipped(monkeypatch, vault):
    assert run_clip(monkeypatch, vault, "重复内容").returncode == 0
    p = run_clip(monkeypatch, vault, "重复内容")
    assert p.returncode == 2
    assert len(clip_files(vault)) == 1


def test_clipboard_dry_run_writes_nothing(monkeypatch, vault):
    p = run_clip(monkeypatch, vault, "dry", argv=("--dry-run",))
    assert p.returncode == 0
    assert clip_files(vault) == []


def run_watch_once(vault, inbox, monkeypatch):
    monkeypatch.setenv("MIND_INBOX", str(inbox))
    # 把脚本内 VAULT 指到伪 vault
    script = vault / "capture-watch.sh"
    src = open(WATCH_SH, encoding="utf-8").read()
    src = src.replace(
        'VAULT="$(cd "$(dirname "$0")/.." && pwd)"',
        f'VAULT="{vault}"',
    )
    script.write_text(src, encoding="utf-8")
    p = subprocess.run(
        ["bash", str(script), "--once"],
        capture_output=True, text=True, timeout=60,
    )
    return p


def test_watch_moves_files(monkeypatch, vault, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "文章.md").write_text("正文", encoding="utf-8")
    (inbox / "notes.txt").write_text("txt", encoding="utf-8")
    p = run_watch_once(vault, inbox, monkeypatch)
    assert p.returncode == 0, p.stderr
    assert list(inbox.iterdir()) == []  # 移动,不是复制
    moved = clip_files(vault)
    assert len(moved) == 2
    assert all(re.match(r"^\d{4}-\d{2}-\d{2}-\d{6}-", f) for f in moved)


def test_watch_skips_temp_and_unwanted(monkeypatch, vault, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.crdownload").write_text("x", encoding="utf-8")
    (inbox / ".hidden.md").write_text("x", encoding="utf-8")
    (inbox / "b.png").write_text("x", encoding="utf-8")
    (inbox / "ok.md").write_text("正文", encoding="utf-8")
    p = run_watch_once(vault, inbox, monkeypatch)
    assert p.returncode == 0, p.stderr
    assert len(clip_files(vault)) == 1
    # 临时/无关文件留在投递目录
    rest = sorted(f.name for f in inbox.iterdir())
    assert rest == [".hidden.md", "a.crdownload", "b.png"]


def test_watch_sanitizes_filename(monkeypatch, vault, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a b:c?.md").write_text("x", encoding="utf-8")
    p = run_watch_once(vault, inbox, monkeypatch)
    assert p.returncode == 0, p.stderr
    moved = clip_files(vault)
    assert len(moved) == 1
    assert ":" not in moved[0] and "?" not in moved[0]
    assert " " not in moved[0]


def test_watch_creates_missing_inbox(monkeypatch, vault, tmp_path):
    inbox = tmp_path / "not-exist"
    p = run_watch_once(vault, inbox, monkeypatch)
    assert p.returncode == 0, p.stderr
    assert inbox.is_dir()
