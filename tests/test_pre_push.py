"""pre-push 钩子的行为测试:subprocess 跑 .githooks/pre-push,验证退出码契约。
契约:测试通过→退出 0;测试失败→非 0(拦下 push);无测试(pytest exit 5)→当通过退出 0。
钩子在真实使用时由 git 以 cwd=仓库根 调用;这里用临时目录模拟不同测试状态。
"""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / ".githooks" / "pre-push"


def _marker_python(path: Path, tag: str) -> Path:
    """一个会在 stderr 打标记、其余行为等同真解释器的假 python。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'#!/bin/sh\necho "{tag}" >&2\nexec "{sys.executable}" "$@"\n',
                    encoding="utf-8")
    path.chmod(0o755)
    return path


def _synthetic_repo(base: Path, name: str = "synthetic-repo") -> Path:
    """造一个只含钩子与解析库的合成仓。

    **不能拿真实仓库测解释器解析** —— 真仓有没有 `.venv` 是环境事实:
    开发容器里没有(于是 MIND_PYTHON 生效),部署 VM 上有(于是 venv 优先、
    MIND_PYTHON 被忽略)。对真仓断言就等于把"本机恰好有什么"焊进了测试。
    """
    import shutil
    repo = base / name
    (repo / ".githooks").mkdir(parents=True, exist_ok=True)
    (repo / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy(HOOK, repo / ".githooks" / "pre-push")
    shutil.copy(REPO / "scripts" / "_pyresolve.sh", repo / "scripts" / "_pyresolve.sh")
    return repo


def _run_hook(workdir: Path, stdin: str = ""):
    """跑钩子的**合成仓副本**,并把解释器钉死成跑本套件的这个。

    为什么不直接跑真实仓的钩子:钩子内部用 mind_python 解析 PY,而
    「真仓有没有 .venv / 系统 python3 是哪版 / 它装没装 pytest」全是环境事实。
    解析出的解释器一旦没有 pytest,钩子会**静默 exit 0** —— 于是
    「测试红要拦下 push」直接翻红,而「测试绿要放行」那几条变成
    **从没跑过 pytest 的假绿**,恰好是这套钩子最初翻车的形态。

    合成仓里没有 .venv → MIND_PYTHON 必然是解析结果 → 测到的是钩子的判定逻辑本身。
    目录名以 . 开头,pytest 默认不递归进去,不会污染 workdir 的收集结果。
    """
    repo = _synthetic_repo(workdir, name=".hookrepo")
    return subprocess.run(
        ["bash", str(repo / ".githooks" / "pre-push")],
        cwd=str(workdir), input=stdin, capture_output=True, text=True,
        env={**os.environ, "MIND_PYTHON": sys.executable},
    )


def _write(workdir: Path, name: str, body: str):
    (workdir / name).write_text(textwrap.dedent(body), encoding="utf-8")


def test_hook_exists_and_executable():
    assert HOOK.exists(), "pre-push 钩子应存在于 .githooks/"
    assert HOOK.stat().st_mode & 0o111, "pre-push 应可执行"


def _assert_actually_ran_pytest(r):
    """退 0 有两种可能:pytest 真跑过且全绿,或者钩子**跳过了**测试直接放行。
    只断言 returncode == 0 分不出这两者 —— 后者正是这套钩子最初翻车的形态。"""
    assert "运行 pytest" in r.stderr, \
        "钩子跳过了测试(没跑就放行),这条绿是假的:" + r.stdout + r.stderr


def test_hook_passes_when_tests_green(tmp_path):
    _write(tmp_path, "test_ok.py", "def test_ok():\n    assert True\n")
    r = _run_hook(tmp_path)
    _assert_actually_ran_pytest(r)
    assert r.returncode == 0, r.stdout + r.stderr


def test_hook_blocks_when_tests_red(tmp_path):
    _write(tmp_path, "test_bad.py", "def test_bad():\n    assert False\n")
    r = _run_hook(tmp_path)
    assert r.returncode != 0, "测试失败时钩子必须拦下 push(非零退出)"


def test_hook_passes_when_no_tests(tmp_path):
    # 空目录:pytest 退出码 5(no tests collected)不应拦 push
    r = _run_hook(tmp_path)
    _assert_actually_ran_pytest(r)     # 必须真跑到 pytest,才谈得上"退出码 5 不拦"
    assert r.returncode == 0, "无测试不应拦下 push;实际输出:" + r.stdout + r.stderr


ZERO = "0" * 40


def test_hook_skips_when_all_deletions(tmp_path):
    # 纯删除推送(local sha 全 0):即便有失败测试,也应跳过、放行(删分支无需跑测试)
    _write(tmp_path, "test_bad.py", "def test_bad():\n    assert False\n")
    r = _run_hook(tmp_path, stdin=f"(delete) {ZERO} refs/heads/x {'1' * 40}\n")
    assert "运行 pytest" not in r.stderr, "纯删除推送就不该跑测试:" + r.stderr
    assert r.returncode == 0, "纯删除推送应跳过测试直接放行;" + r.stdout + r.stderr


def test_hook_runs_on_normal_push_ref(tmp_path):
    # 非删除 ref(有真实 local sha):含失败测试必须拦下
    _write(tmp_path, "test_bad.py", "def test_bad():\n    assert False\n")
    r = _run_hook(tmp_path, stdin=f"refs/heads/x {'a' * 40} refs/heads/x {'b' * 40}\n")
    assert r.returncode != 0, "正常推送含失败测试必须拦下"


def test_hook_finds_resolver_relative_to_itself_not_cwd(tmp_path):
    """钩子要按**自己所在的仓库**找解释器解析库,而不是按 cwd 猜。

    原来用 `git rev-parse --show-toplevel || pwd` 定位 scripts/_pyresolve.sh:
    cwd 不在仓库里(本测试、以及 git 在 worktree/子模块下的调用)就找不到,
    退回裸 python3 —— 真机上那是没装 pytest 的 3.6,钩子于是**静默放行**。

    合成仓里没有 .venv,所以 MIND_PYTHON 必然是解析结果 —— 与本机装了什么无关。
    """
    repo = _synthetic_repo(tmp_path)
    marker = _marker_python(tmp_path / "marker-python", "RESOLVER-USED")
    work = tmp_path / "elsewhere"      # cwd 故意不在那个仓库里
    work.mkdir()
    _write(work, "test_ok.py", "def test_ok():\n    assert True\n")
    r = subprocess.run(["bash", str(repo / ".githooks" / "pre-push")], cwd=str(work),
                       input="", capture_output=True, text=True,
                       env={**os.environ, "MIND_PYTHON": str(marker)})
    assert "RESOLVER-USED" in r.stderr, \
        "钩子没走本仓的 _pyresolve.sh(于是也读不到 MIND_PYTHON):" + r.stdout + r.stderr
    assert r.returncode == 0, r.stdout + r.stderr


def test_hook_prefers_repo_venv_over_env(tmp_path):
    """仓库里有 .venv 时,钩子必须用它 —— 那才是装了依赖的解释器。

    与上一条互为对照:两条合起来把「解析顺序」在**钩子这一层**钉死,
    而不是依赖跑测试的这台机器恰好处于哪种状态。
    """
    repo = _synthetic_repo(tmp_path)
    _marker_python(repo / ".venv" / "bin" / "python", "VENV-USED")
    ignored = _marker_python(tmp_path / "should-be-ignored", "MINDPY-USED")
    work = tmp_path / "elsewhere2"
    work.mkdir()
    _write(work, "test_ok.py", "def test_ok():\n    assert True\n")
    r = subprocess.run(["bash", str(repo / ".githooks" / "pre-push")], cwd=str(work),
                       input="", capture_output=True, text=True,
                       env={**os.environ, "MIND_PYTHON": str(ignored)})
    assert "VENV-USED" in r.stderr, "有 .venv 就该用 .venv:" + r.stdout + r.stderr
    assert "MINDPY-USED" not in r.stderr, "MIND_PYTHON 不该盖过 .venv:" + r.stderr
    assert r.returncode == 0, r.stdout + r.stderr
