"""init-vault.sh 的行为测试(为新机器/新用户初始化内容库 + 双库软链)。

契约:
- `--dry-run` 打印计划,**不创建任何东西**,退出 0。
- 正常跑:在 --vault 处建出内容库骨架(_wiki 四子目录 / material 六类 / raw 各桶 /
  writing / reports 三桶),种下 _wiki/index.md、_wiki/log.md、.gitignore,并 git init。
- 在 --repo 处建软链(/_wiki /material /raw /writing /reports/{daily,weekly,lint})指向内容库。
- 结果必须能被 vault.sh 正确识别为双库(集成断言:vault.sh repo 打印内容库路径)。
- **幂等**:二次运行不破坏已有内容、退出 0。
- **绝不覆盖**已存在的内容文件(用户数据至上)。
- 未知参数 → 用法 + 非零退出;`bash -n` 语法干净。
纯 .sh 用 subprocess 测(见 tests/README.md)。
"""
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SH = REPO / "scripts" / "init-vault.sh"
VAULT_SH = REPO / "scripts" / "vault.sh"

CONTENT_DIRS = [
    "_wiki/concepts", "_wiki/summaries", "_wiki/entities", "_wiki/outputs",
    "material/quotes", "material/stories", "material/references",
    "material/cases", "material/frameworks", "material/data",
    "raw/clippings", "raw/todo", "raw/archive/clippings",
    "raw/flomo/delta", "raw/pdfs", "raw/assets",
    "writing", "reports/daily", "reports/weekly", "reports/lint",
]
LINKS = ["_wiki", "material", "raw", "writing",
         "reports/daily", "reports/weekly", "reports/lint"]


def _run(*args, cwd=None):
    return subprocess.run(["bash", str(SH), *args], cwd=str(cwd or REPO),
                          capture_output=True, text=True)


def _fake_repo(tmp_path: Path) -> Path:
    """最小 mind 仓:含 scripts/vault.sh 与 reports/ 占位,已 git init。"""
    repo = tmp_path / "mind"
    (repo / "scripts").mkdir(parents=True)
    (repo / "reports").mkdir()
    (repo / "reports" / "README.md").write_text("报告\n", encoding="utf-8")
    import shutil
    shutil.copy(VAULT_SH, repo / "scripts" / "vault.sh")
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    return repo


def test_syntax_ok():
    assert subprocess.run(["bash", "-n", str(SH)]).returncode == 0


def test_dry_run_creates_nothing(tmp_path):
    repo = _fake_repo(tmp_path)
    vault = tmp_path / "mind-vault"
    r = _run("--repo", str(repo), "--vault", str(vault), "--dry-run")
    assert r.returncode == 0, r.stderr
    assert not vault.exists(), "dry-run 不得创建内容库"
    assert not (repo / "_wiki").exists(), "dry-run 不得建软链"
    assert "_wiki" in r.stdout and "计划" in r.stdout


def test_creates_full_skeleton(tmp_path):
    repo = _fake_repo(tmp_path)
    vault = tmp_path / "mind-vault"
    r = _run("--repo", str(repo), "--vault", str(vault))
    assert r.returncode == 0, r.stdout + r.stderr
    for d in CONTENT_DIRS:
        assert (vault / d).is_dir(), f"缺目录 {d}"
    assert (vault / "_wiki" / "index.md").is_file()
    assert (vault / "_wiki" / "log.md").is_file()
    assert (vault / ".gitignore").is_file()
    assert (vault / ".git").is_dir(), "内容库应 git init"


def test_creates_symlinks_into_repo(tmp_path):
    repo = _fake_repo(tmp_path)
    vault = tmp_path / "mind-vault"
    _run("--repo", str(repo), "--vault", str(vault))
    for link in LINKS:
        p = repo / link
        assert p.is_symlink(), f"{link} 应为软链"
        assert p.resolve() == (vault / link).resolve(), f"{link} 指向错误"


def test_vault_sh_detects_dual_repo(tmp_path):
    # 集成断言:装完后 vault.sh 必须把内容库认出来(否则提交会落错仓)
    repo = _fake_repo(tmp_path)
    vault = tmp_path / "mind-vault"
    _run("--repo", str(repo), "--vault", str(vault))
    r = subprocess.run(["bash", str(repo / "scripts" / "vault.sh"), "repo"],
                       cwd=str(repo), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert Path(r.stdout.strip()).resolve() == vault.resolve(), \
        f"vault.sh 应指向内容库,实际:{r.stdout.strip()}"


def test_idempotent_and_never_clobbers(tmp_path):
    repo = _fake_repo(tmp_path)
    vault = tmp_path / "mind-vault"
    _run("--repo", str(repo), "--vault", str(vault))
    # 用户写入真实内容
    page = vault / "_wiki" / "outputs" / "我的页.md"
    page.write_text("---\ntitle: 我的页\n---\n正文\n", encoding="utf-8")
    (vault / "_wiki" / "log.md").write_text("我改过的 log\n", encoding="utf-8")
    r2 = _run("--repo", str(repo), "--vault", str(vault))
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert page.read_text(encoding="utf-8").startswith("---"), "已有内容页不得被动"
    assert (vault / "_wiki" / "log.md").read_text(encoding="utf-8") == "我改过的 log\n", \
        "已存在的种子文件不得被覆盖"


def test_unknown_arg_usage_nonzero(tmp_path):
    r = _run("--bogus")
    assert r.returncode != 0
    assert "用法" in (r.stdout + r.stderr)


def test_no_link_skips_symlinks(tmp_path):
    repo = _fake_repo(tmp_path)
    vault = tmp_path / "mind-vault"
    r = _run("--repo", str(repo), "--vault", str(vault), "--no-link")
    assert r.returncode == 0, r.stderr
    assert (vault / "_wiki").is_dir(), "内容库仍应建出"
    assert not (repo / "_wiki").exists(), "--no-link 时不得建软链"


def test_existing_real_dir_in_repo_is_not_destroyed(tmp_path):
    # 安全红线:repo 里若已有**真实**内容目录(非软链),绝不能删了它建软链
    repo = _fake_repo(tmp_path)
    real = repo / "_wiki"
    real.mkdir()
    (real / "重要.md").write_text("别删我\n", encoding="utf-8")
    vault = tmp_path / "mind-vault"
    r = _run("--repo", str(repo), "--vault", str(vault))
    assert (real / "重要.md").is_file(), "真实目录里的文件绝不能被销毁"
    assert not real.is_symlink(), "不得把真实目录替换成软链"
    assert r.returncode != 0 or "跳过" in r.stdout or "已存在" in r.stdout, \
        "应明确拒绝/跳过而非静默破坏"
