"""CI 门禁自身的门禁:workflow 装齐依赖,且缺可选依赖不许炸掉整个套件。

**真实事故(2026-08-06 查出)**:`.github/workflows/tests.yml` 只装
`requirements-dev.txt`(pytest),没装 `requirements.txt`(markdown)。
而 2026-08-04 落地的 `tests/test_build_wiki_site.py` 在**模块顶层**
`exec_module()` 了 `scripts/build-wiki-site.py`,后者 `import markdown` ——
于是 CI 每次都是:

    ERROR tests/test_build_wiki_site.py  ModuleNotFoundError: No module named 'markdown'
    !!!!!! Interrupted: 1 error during collection !!!!!!
    Process completed with exit code 2

**collection error 会掐断整个套件**:退出码 2,一条测试都没跑。也就是说
CI 从 08-04 起就没真正检查过任何一次 push —— 而它正是 pre-push 钩子被
`--no-verify` 绕过时的最后兜底(同日另一 PR 查出 pre-push 也恒红,两道
同时失效)。

本仓自己的话:**恒红的门禁等于没有门禁,还更坏**——它逼人养成绕过的习惯。

所以钉两条,方向不同、缺一不可:
1. CI 必须装运行时依赖(要测的是完整功能面);
2. 即便某台机器没装可选依赖,也只能**跳过那个模块**,不许炸掉 collection
   ——`markdown` 在 requirements.txt 里明说是 best-effort 可选依赖,
   一个可选依赖不该有掐断全套件的杀伤力。
"""
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "tests.yml"


def _checkout_fetches_full_history(text):
    marker = "- uses: actions/checkout@v4"
    if marker not in text:
        return False
    checkout_step = text.split(marker, 1)[1].split("\n      - ", 1)[0]
    lines = checkout_step.splitlines()
    for index, line in enumerate(lines):
        with_match = re.match(r"^(?P<indent>[ \t]*)with:[ \t]*(?:#[^\n]*)?$", line)
        if not with_match:
            continue
        with_indent = len(with_match.group("indent"))
        for input_line in lines[index + 1:]:
            if not input_line.strip():
                continue
            input_indent = len(input_line) - len(input_line.lstrip(" \t"))
            if input_indent <= with_indent:
                break
            if re.match(
                r"^[ \t]*fetch-depth:[ \t]*0(?:[ \t]+#[^\n]*)?[ \t]*$",
                input_line,
            ):
                return True
        return False
    return False


def _missing_markdown_shim(tmp_path: Path) -> Path:
    """造一个"没装 markdown"的现场:让 `import markdown` 抛 ModuleNotFoundError。

    **异常类型必须精确**——第一版让 shim 抛通用 `ImportError`,而
    `pytest.importorskip` 默认只捕获 `ModuleNotFoundError`(通用 ImportError
    可能意味着"模块装了但它自己坏了",静默跳过是错的,pytest 这个设计对)。
    于是守卫明明写对了,测试却仍报 collection error——**测的不是真实故障型别**。
    同型教训见 tests/test_feishu_preflight.py:用 EPERM 而非 chmod 的 EACCES。
    """
    shim = tmp_path / "shim"
    shim.mkdir()
    (shim / "markdown.py").write_text(
        "raise ModuleNotFoundError(\"No module named 'markdown'\", name='markdown')\n",
        encoding="utf-8")
    return shim


def test_ci_installs_runtime_requirements():
    """CI 必须同时装 requirements.txt —— 否则 collection 就炸,一条测试都跑不了。"""
    assert WORKFLOW.is_file(), "缺 .github/workflows/tests.yml(CI 兜底门禁)"
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "requirements-dev.txt" in text, "CI 应装开发依赖(pytest)"
    assert "requirements.txt" in text.replace("requirements-dev.txt", ""), (
        "CI 只装了 requirements-dev.txt,没装 requirements.txt —— "
        "test_build_wiki_site.py 在 collection 期就 import markdown,"
        "缺它整个套件退 2、零测试执行(2026-08-04 起真实发生)")


def test_ci_checkout_fetches_full_history():
    text = WORKFLOW.read_text(encoding="utf-8")
    marker = "- uses: actions/checkout@v4"
    assert marker in text, "CI 缺 actions/checkout@v4"
    assert _checkout_fetches_full_history(text), (
        "发布世系测试需要完整 Git 历史；浅克隆会让源仓 HEAD 无法解析"
    )


def _workflow_with_checkout_config(config):
    return (
        "jobs:\n"
        "  pytest:\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        f"{config}\n"
        "      - name: Run pytest\n"
    )


def test_ci_checkout_rejects_commented_full_history():
    assert not _checkout_fetches_full_history(
        _workflow_with_checkout_config("        # fetch-depth: 0")
    )


def test_ci_checkout_rejects_wrong_fetch_depth_key():
    assert not _checkout_fetches_full_history(
        _workflow_with_checkout_config("        not-fetch-depth: 0")
    )


def test_ci_checkout_rejects_nonzero_fetch_depth_value():
    assert not _checkout_fetches_full_history(
        _workflow_with_checkout_config("        fetch-depth: 01")
    )


def test_ci_checkout_rejects_fetch_depth_outside_with_inputs():
    assert not _checkout_fetches_full_history(
        _workflow_with_checkout_config(
            "        fetch-depth: 0\n"
            "        with:\n"
            "          persist-credentials: false"
        )
    )


def test_missing_optional_dep_skips_module_instead_of_breaking_collection(tmp_path):
    """缺可选依赖时只跳过该模块,退出码不得是 2(collection error)。

    用一个抛 ModuleNotFoundError 的假 `markdown` 顶掉真的(PYTHONPATH 优先于
    site-packages),复现"这台机器没装 markdown"的现场——比 uninstall 安全,
    也不依赖当前环境装没装。异常型别为何必须精确,见 `_missing_markdown_shim`。
    """
    env = {**os.environ, "PYTHONPATH": str(_missing_markdown_shim(tmp_path))}
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--collect-only",
         "tests/test_build_wiki_site.py"],
        cwd=str(REPO), capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode != 2, (
        "缺可选依赖导致 collection error(退 2)——整个套件会被掐断,"
        "一条测试都跑不了。用 pytest.importorskip 守住模块顶层的第三方 import。\n"
        + (r.stdout + r.stderr)[-600:])


def test_whole_suite_survives_missing_optional_dep(tmp_path):
    """整套件级别的锁:缺 markdown 时收集仍能完成(个别模块 skip 是可以的)。

    上一条只测单个模块;这条确认没有**别的**模块也在 collection 期硬 import
    第三方依赖——真正致命的是"整套件退 2",而不是某个文件。
    """
    env = {**os.environ, "PYTHONPATH": str(_missing_markdown_shim(tmp_path))}
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "--collect-only"],
                       cwd=str(REPO), capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode != 2, (
        "整套件在缺可选依赖时 collection error —— CI/新机器上会零测试执行:\n"
        + (r.stdout + r.stderr)[-800:])
