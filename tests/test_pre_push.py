"""pre-push 钩子的行为测试:subprocess 跑 .githooks/pre-push,验证退出码契约。
契约:测试通过→退出 0;测试失败→非 0(拦下 push);无测试(pytest exit 5)→当通过退出 0。
钩子在真实使用时由 git 以 cwd=仓库根 调用;这里用临时目录模拟不同测试状态。
"""
import os
import subprocess
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / ".githooks" / "pre-push"


def _run_hook(workdir: Path, stdin: str = ""):
    # 显式给空 stdin(EOF):无待推 ref 行 → 照常跑测试(见钩子内 have_ref 逻辑)
    return subprocess.run(
        ["bash", str(HOOK)],
        cwd=str(workdir), input=stdin, capture_output=True, text=True, env={**os.environ},
    )


def _write(workdir: Path, name: str, body: str):
    (workdir / name).write_text(textwrap.dedent(body), encoding="utf-8")


def test_hook_exists_and_executable():
    assert HOOK.exists(), "pre-push 钩子应存在于 .githooks/"
    assert HOOK.stat().st_mode & 0o111, "pre-push 应可执行"


def test_hook_passes_when_tests_green(tmp_path):
    _write(tmp_path, "test_ok.py", "def test_ok():\n    assert True\n")
    r = _run_hook(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_hook_blocks_when_tests_red(tmp_path):
    _write(tmp_path, "test_bad.py", "def test_bad():\n    assert False\n")
    r = _run_hook(tmp_path)
    assert r.returncode != 0, "测试失败时钩子必须拦下 push(非零退出)"


def test_hook_passes_when_no_tests(tmp_path):
    # 空目录:pytest 退出码 5(no tests collected)不应拦 push
    r = _run_hook(tmp_path)
    assert r.returncode == 0, "无测试不应拦下 push;实际输出:" + r.stdout + r.stderr


ZERO = "0" * 40


def test_hook_skips_when_all_deletions(tmp_path):
    # 纯删除推送(local sha 全 0):即便有失败测试,也应跳过、放行(删分支无需跑测试)
    _write(tmp_path, "test_bad.py", "def test_bad():\n    assert False\n")
    r = _run_hook(tmp_path, stdin=f"(delete) {ZERO} refs/heads/x {'1' * 40}\n")
    assert r.returncode == 0, "纯删除推送应跳过测试直接放行;" + r.stdout + r.stderr


def test_hook_runs_on_normal_push_ref(tmp_path):
    # 非删除 ref(有真实 local sha):含失败测试必须拦下
    _write(tmp_path, "test_bad.py", "def test_bad():\n    assert False\n")
    r = _run_hook(tmp_path, stdin=f"refs/heads/x {'a' * 40} refs/heads/x {'b' * 40}\n")
    assert r.returncode != 0, "正常推送含失败测试必须拦下"
