"""preflight-check.py 测试:四道规则门 + 隔离/恢复 + 永不阻塞。"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "preflight-check.py"


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    """伪 vault:raw/clippings + raw/archive;脚本内 VAULT 指到这里。"""
    (tmp_path / "raw" / "clippings").mkdir(parents=True)
    (tmp_path / "raw" / "archive").mkdir(parents=True)
    (tmp_path / "raw" / "todo").mkdir(parents=True)
    (tmp_path / "reports").mkdir(parents=True)
    # 复制脚本并改 VAULT 常量,指向伪 vault
    script = tmp_path / "preflight-check.py"
    src = SCRIPT.read_text(encoding="utf-8")
    src = src.replace(
        "VAULT = Path(__file__).resolve().parent.parent",
        f"VAULT = Path({str(tmp_path)!r})",
    )
    # dedup-check.py 也复制一份(按路径加载)
    shutil.copy(REPO / "scripts" / "dedup-check.py",
                tmp_path / "scripts-dedup-check.py")
    src = src.replace(
        'str(VAULT / "scripts" / "dedup-check.py")',
        f'{str(tmp_path / "scripts-dedup-check.py")!r}',
    )
    script.write_text(src, encoding="utf-8")
    # 把脚本目录加到 sys.path 供 importlib 定位(实际用绝对路径,此处仅保险)
    return tmp_path, script


def run(script, *argv):
    p = subprocess.run([sys.executable, str(script), *argv],
                       capture_output=True, text=True, timeout=60)
    return p


def write_clip(vault, name, body):
    p = vault / "raw" / "clippings" / name
    p.write_text(body, encoding="utf-8")
    return p


def quarantined(vault, reason):
    d = vault / "raw" / "quarantine" / reason
    return sorted(f.name for f in d.glob("*.md")) if d.is_dir() else []


LONG_BODY = "这是一篇有实质内容的剪藏。" * 30  # >200 字符


def test_too_short_quarantined(vault):
    v, script = vault
    write_clip(v, "short.md", "太短了")
    p = run(script)
    assert p.returncode == 0
    assert quarantined(v, "too-short") == ["short.md"]
    assert list((v / "raw" / "clippings").glob("*.md")) == []


def test_good_file_passes(vault):
    v, script = vault
    write_clip(v, "good.md", f"# 好文章\n\n{LONG_BODY}")
    p = run(script)
    assert p.returncode == 0
    assert (v / "raw" / "clippings" / "good.md").is_file()
    assert quarantined(v, "too-short") == []


def test_exact_duplicate_quarantined(vault):
    v, script = vault
    dup_body = f"# 重复\n\n{LONG_BODY}"
    (v / "raw" / "archive" / "orig.md").write_text(dup_body, encoding="utf-8")
    write_clip(v, "copy.md", dup_body)
    p = run(script)
    assert p.returncode == 0
    assert quarantined(v, "duplicate") == ["copy.md"]


def test_boilerplate_quarantined(vault):
    v, script = vault
    junk = "Cookie 隐私政策 用户协议 立即登录 免费注册 分享到 点赞 收藏 " * 20
    write_clip(v, "junk.md", f"# 标题\n\n{junk}\n{LONG_BODY[:50]}")
    p = run(script)
    assert p.returncode == 0
    assert quarantined(v, "boilerplate") == ["junk.md"]


def test_dry_run_moves_nothing(vault):
    v, script = vault
    write_clip(v, "short.md", "太短了")
    p = run(script, "--dry-run")
    assert p.returncode == 0
    assert (v / "raw" / "clippings" / "short.md").is_file()
    assert not (v / "raw" / "quarantine").exists()


def test_restore(vault):
    v, script = vault
    write_clip(v, "short.md", "太短了")
    assert run(script).returncode == 0
    assert quarantined(v, "too-short") == ["short.md"]
    p = run(script, "--restore", "short.md")
    assert p.returncode == 0
    assert (v / "raw" / "clippings" / "short.md").is_file()


def test_report_written(vault):
    v, script = vault
    write_clip(v, "a.md", f"# A\n\n{LONG_BODY}")
    write_clip(v, "b.md", "短")
    assert run(script).returncode == 0
    reports = list((v / "reports" / "preflight").glob("*.json"))
    assert len(reports) == 1
    data = json.loads(reports[0].read_text(encoding="utf-8"))
    assert data["checked"] == 2 and data["quarantined"] == 1


def test_never_blocks_on_error(vault):
    """clippings 缺席也不非零退出 —— 预检门永不阻塞编译。"""
    v, script = vault
    shutil.rmtree(v / "raw" / "clippings")
    p = run(script)
    assert p.returncode == 0
