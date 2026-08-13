import json
import subprocess
import sys
from pathlib import Path

import compile_second_brain as compile_mod
import install_second_brain as install_mod
import vault_init


REPO = Path(__file__).resolve().parent.parent


def test_native_windows_entrypoints_exist_and_do_not_require_wsl():
    install_ps = (REPO / "install-second-brain.ps1").read_text(encoding="utf-8")
    compile_ps = (REPO / "compile-second-brain.ps1").read_text(encoding="utf-8")
    assert "install_second_brain.py" in install_ps
    assert "compile_second_brain.py" in compile_ps
    assert "WSL" not in install_ps + compile_ps
    assert "Invoke-Expression" not in install_ps + compile_ps


def test_venv_python_uses_windows_scripts_directory(tmp_path):
    expected = tmp_path / ".venv" / "Scripts" / "python.exe"
    expected.parent.mkdir(parents=True)
    expected.touch()
    assert install_mod.venv_python(tmp_path, platform="nt") == expected


def test_vault_initializer_is_idempotent_without_links(tmp_path):
    repo = tmp_path / "mind-kit"
    vault = tmp_path / "my-vault"
    repo.mkdir()
    first = vault_init.initialize(vault=vault, repo=repo, create_links=False, init_git=False)
    second = vault_init.initialize(vault=vault, repo=repo, create_links=False, init_git=False)
    assert first.skipped == second.skipped == []
    assert (vault / "raw" / "clippings").is_dir()
    assert (vault / "_wiki" / "index.md").read_text(encoding="utf-8").startswith("# 内容导航")


def test_installer_self_check_is_machine_readable():
    proc = subprocess.run(
        [sys.executable, "scripts/install_second_brain.py", "--self-check"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(proc.stdout)
    assert data["ok"] is True
    assert data["core_modules"]["installer"] is True
    assert data["core_modules"]["vault_init"] is True
    assert data["core_modules"]["lark_cli_argv"] is True
    assert data["core_status"] == "ready"
    expected_sync = "available" if all(
        (REPO / "scripts" / name).is_file()
        for name in ("feishu-backup-docs.py", "feishu-backup-wiki.py")
    ) else "unavailable"
    assert data["sync_status"] == expected_sync
    assert "docs" in data["optional_modules"]
    assert "wiki" in data["optional_modules"]


def test_compile_dry_run_only_invokes_engine(tmp_path):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="estimate only\n", stderr="")

    result = compile_mod.run_pipeline(
        root=tmp_path,
        python=Path(sys.executable),
        compile_args=["--dry-run"],
        runner=fake_run,
        sage="sage-wiki",
    )
    assert result == 0
    assert calls == [["sage-wiki", "compile", "--dry-run"]]


def test_gitlab_ci_owns_windows_validation():
    ci = (REPO / ".gitlab-ci.yml").read_text(encoding="utf-8")
    assert "windows-native" in ci
    assert "powershell" in ci.lower()
    assert "install-second-brain.ps1" in ci
    assert "compile-second-brain.ps1" in ci
    assert "windows-latest" not in ci
    workflows = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in (REPO / ".github" / "workflows").glob("*.yml")
    )
    assert "windows-latest" not in workflows


def test_public_release_keeps_installer_dependencies_and_removes_private_sync_connectors():
    delete_file = REPO / "publish" / "DELETE.txt"
    deleted = set()
    if delete_file.is_file():
        lines = delete_file.read_text(encoding="utf-8").splitlines()
        deleted = {line.split("#", 1)[0].strip() for line in lines}
    for required in (
        "install-second-brain",
        "install-second-brain.ps1",
        "scripts/install_second_brain.py",
        "scripts/vault_init.py",
        "scripts/lark_cli_argv.py",
    ):
        assert (REPO / required).is_file()
        assert required not in deleted
    # publish/ is private source-repository policy and intentionally absent from
    # the exported package.  Validate it only where that source policy exists.
    if delete_file.is_file():
        for private in (
            "scripts/feishu-backup-docs.py",
            "scripts/feishu-backup-wiki.py",
            "scripts/larklib.py",
            "tests/test_larklib.py",
        ):
            assert private in deleted
