"""shell 脚本的测试示范:用 subprocess 跑脚本、断言输出/退出码/副作用。
这里测 vault.sh 的只读子命令 `repo`(内容库自动探测),不产生任何写副作用。
"""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VAULT_SH = REPO / "scripts" / "vault.sh"


def _run(*args):
    return subprocess.run(
        ["bash", str(VAULT_SH), *args],
        cwd=str(REPO), capture_output=True, text=True,
    )


def test_vault_repo_prints_valid_content_repo():
    r = _run("repo")
    assert r.returncode == 0, r.stderr
    printed = Path(r.stdout.strip())
    # 单库模式下应指向本仓;双库模式指向 mind-vault —— 无论哪种,都应是个含 vault.sh 的 git 库根
    assert printed.is_dir()
    assert (printed / "scripts" / "vault.sh").exists() or (printed / "_wiki").exists()


def test_vault_usage_on_bad_arg():
    r = _run("nonsense-subcommand")
    assert r.returncode != 0            # 未知子命令应非零退出
    assert "用法" in (r.stdout + r.stderr)


# ---------- P1-4:vault.sh commit 的写集校验门禁 ----------

def _mk_repo(base: Path) -> Path:
    """最小单库 vault:含 vault.sh 与 validate_write_set 及其依赖脚本。"""
    import shutil
    repo = base / "mind"
    (repo / "scripts").mkdir(parents=True)
    for s in ("vault.sh", "validate_write_set.py", "decision.py", "freshness.py"):
        shutil.copy(REPO / "scripts" / s, repo / "scripts" / s)
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True)
    return repo


def _commit(repo: Path, env_extra=None):
    import os
    env = {**os.environ, **(env_extra or {})}
    return subprocess.run(["bash", str(repo / "scripts" / "vault.sh"), "commit", "测试提交"],
                          cwd=str(repo), capture_output=True, text=True, env=env)


def test_vault_commit_blocked_by_bad_page(tmp_path):
    repo = _mk_repo(tmp_path)
    bad = repo / "_wiki" / "outputs" / "坏页.md"
    bad.parent.mkdir(parents=True)
    bad.write_text("---\ntitle: 断栏\n\n没闭合\n", encoding="utf-8")
    r = _commit(repo)
    assert r.returncode != 0, "坏页应拦下提交:" + r.stdout + r.stderr
    log = subprocess.run(["git", "-C", str(repo), "log", "--oneline"],
                         capture_output=True, text=True).stdout
    assert "测试提交" not in log, "被拦时不得产生提交"


def test_vault_commit_passes_good_page(tmp_path):
    repo = _mk_repo(tmp_path)
    good = repo / "_wiki" / "outputs" / "好页.md"
    good.parent.mkdir(parents=True)
    good.write_text("---\ntitle: 好页\n---\n正文\n", encoding="utf-8")
    r = _commit(repo)
    assert r.returncode == 0, r.stdout + r.stderr
    log = subprocess.run(["git", "-C", str(repo), "log", "--oneline"],
                         capture_output=True, text=True).stdout
    assert "测试提交" in log


def test_vault_commit_warns_when_validator_missing(tmp_path):
    # 评审 F10:校验器文件缺失不得静默解除门禁——放行可以,但必须有告警
    repo = _mk_repo(tmp_path)
    (repo / "scripts" / "validate_write_set.py").unlink()
    good = repo / "_wiki" / "outputs" / "页.md"
    good.parent.mkdir(parents=True)
    good.write_text("---\ntitle: 页\n---\n正文\n", encoding="utf-8")
    r = _commit(repo)
    assert r.returncode == 0
    assert "校验器缺失" in (r.stdout + r.stderr), "静默自废门禁不可接受:" + r.stderr


def test_vault_commit_skip_validate_escape_hatch(tmp_path):
    repo = _mk_repo(tmp_path)
    bad = repo / "_wiki" / "outputs" / "坏页.md"
    bad.parent.mkdir(parents=True)
    bad.write_text("---\ntitle: 断栏\n\n没闭合\n", encoding="utf-8")
    r = _commit(repo, {"VAULT_SKIP_VALIDATE": "1"})
    assert r.returncode == 0, "逃生舱应放行:" + r.stdout + r.stderr
