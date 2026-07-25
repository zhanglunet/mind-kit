"""install-hooks.sh 的行为测试:装完后 core.hooksPath 指向 .githooks 且钩子可执行。
在临时 git 仓库里跑真实 installer,不动真实仓库。
"""
import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INSTALLER = REPO / "scripts" / "install-hooks.sh"
HOOK = REPO / ".githooks" / "pre-push"


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


def _seed_repo(tmp_path: Path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "scripts").mkdir()
    (tmp_path / ".githooks").mkdir()
    shutil.copy(INSTALLER, tmp_path / "scripts" / "install-hooks.sh")
    shutil.copy(HOOK, tmp_path / ".githooks" / "pre-push")


def _install(tmp_path: Path):
    return subprocess.run(
        ["bash", "scripts/install-hooks.sh"],
        cwd=str(tmp_path), capture_output=True, text=True,
    )


def test_installer_sets_hookspath(tmp_path):
    assert INSTALLER.exists(), "install-hooks.sh 应存在"
    _seed_repo(tmp_path)
    r = _install(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    got = _git(tmp_path, "config", "--get", "core.hooksPath").stdout.strip()
    assert got == ".githooks", f"core.hooksPath 应为 .githooks,实际 {got!r}"
    assert os.access(tmp_path / ".githooks" / "pre-push", os.X_OK), "pre-push 应可执行"


def test_installer_idempotent(tmp_path):
    _seed_repo(tmp_path)
    for _ in range(2):
        r = _install(tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr
    assert _git(tmp_path, "config", "--get", "core.hooksPath").stdout.strip() == ".githooks"


def test_installer_friendly_error_outside_git(tmp_path):
    # 非 git 目录:应友好报错并非零退出,而非甩出 git 原始 fatal
    r = subprocess.run(["bash", str(INSTALLER)], cwd=str(tmp_path),
                       capture_output=True, text=True)
    assert r.returncode != 0
    assert "git 仓库" in (r.stdout + r.stderr), r.stdout + r.stderr
