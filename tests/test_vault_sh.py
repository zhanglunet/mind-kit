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
    # _pyresolve.sh 是 vault.sh 的硬依赖(缺了就不知道该用哪个 Python,脚本直接硬失败)
    for s in ("vault.sh", "_pyresolve.sh", "validate_write_set.py", "decision.py", "freshness.py"):
        shutil.copy(REPO / "scripts" / s, repo / "scripts" / s)
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True)
    return repo


def _commit(repo: Path, env_extra=None):
    import os
    import sys
    # 合成 vault 里没有 .venv,不指定就会退回裸 python3 —— 那在真机上是 EOL 的 3.6,
    # 于是这几条测的就变成了"本机 python3 恰好是几"而不是 vault.sh 的门禁行为。
    # 显式钉住解释器:本套件用哪个 Python 跑,被测脚本就用哪个。
    env = {**os.environ, "MIND_PYTHON": sys.executable, **(env_extra or {})}
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


# ═══ 真机暴露:提交失败被报成「无改动」 ═══════════════════════

def _commit_without_identity(repo: Path):
    """在**无 git 身份**的环境下提交(真机 VM 上就是这样)。

    只清空配置还不够:git 在 hostname 可解析的机器上会自动猜出身份
    (user.useConfigOnly 默认 false),提交照样成功——Mac 上这条测试就因此假失败。
    写一个只含 useConfigOnly=true 的临时 global 配置,把「无身份 → 提交必败」
    变成与机器无关的确定行为。
    """
    import os
    import sys
    import tempfile
    noident = tempfile.NamedTemporaryFile(
        "w", prefix="git-noident-", suffix=".conf", delete=False)
    noident.write("[user]\n\tuseConfigOnly = true\n")
    noident.close()
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("GIT_AUTHOR", "GIT_COMMITTER"))}
    env["MIND_PYTHON"] = sys.executable
    env["GIT_CONFIG_GLOBAL"] = noident.name
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    for key in ("user.email", "user.name"):
        subprocess.run(["git", "-C", str(repo), "config", "--unset", key], env=env)
    return subprocess.run(["bash", str(repo / "scripts" / "vault.sh"), "commit", "测试提交"],
                          cwd=str(repo), capture_output=True, text=True, env=env)


def test_commit_failure_is_not_reported_as_no_changes(tmp_path):
    """提交失败必须非零退出并说清,**不能报成「无改动可提交」**。

    2026-07-29 真机:VM 上没配 git 身份,`git commit` 报
    `fatal: unable to auto-detect email address`,而 vault.sh 的
    `commit … || echo "无改动可提交"` 把**所有**失败都吞成这一句、还退 0。
    于是 compile.sh 认为收尾提交成功、update-all 报「成功 5 · 失败 0」——
    实际编译产物全堆在暂存区没进库。cron 会天天这样报绿,而内容库永远不同步。
    """
    repo = _mk_repo(tmp_path)
    good = repo / "_wiki" / "outputs" / "好页.md"
    good.parent.mkdir(parents=True)
    good.write_text("---\ntitle: 好页\n---\n正文\n", encoding="utf-8")
    r = _commit_without_identity(repo)
    both = r.stdout + r.stderr
    assert "无改动可提交" not in both, "明明有改动、提交失败了,却报「无改动」:" + both[-400:]
    assert r.returncode != 0, "提交失败必须非零退出,否则上游会当成功:" + both[-400:]
    assert "提交失败" in both or "✗" in both, "要说清是提交失败:" + both[-400:]


def test_genuinely_no_changes_still_exits_zero(tmp_path):
    """真的没有改动时仍要报「无改动可提交」并退 0 —— 别把正常情况也判成失败。"""
    repo = _mk_repo(tmp_path)
    _commit(repo)                      # 第一次会把 __pycache__ 等副产物收掉
    r = _commit(repo)                  # 第二次才是真正的"无改动"
    assert r.returncode == 0, "无改动是正常情况:" + r.stdout + r.stderr
    assert "无改动" in (r.stdout + r.stderr), r.stdout + r.stderr
