"""update-all.sh 的行为测试(本机全量更新编排)。
契约:
- `--dry-run` 打印有序计划(日报→编译→订阅→门户→文档站),退出 0,不执行任何步骤。
- 计划里对缺工具的步骤标「缺 <tool>,将跳过」,对就绪的标「<tool> 就绪」。
- `--pull` 会把"拉取最新代码"列为第 0 步;不带则提示可加。
- 未知参数 → 用法 + 非零退出;`bash -n` 语法干净。
纯 .sh 用 subprocess 测(见 tests/README.md)。
"""
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SH = REPO / "scripts" / "update-all.sh"


def _run(*args, env=None):
    return subprocess.run(["bash", str(SH), *args], cwd=str(REPO),
                          capture_output=True, text=True, env=env)


def _py_dir():
    import shutil
    return str(Path(shutil.which("python3")).parent)


def test_syntax_ok():
    assert subprocess.run(["bash", "-n", str(SH)]).returncode == 0


def test_dry_run_lists_steps_in_order():
    r = _run("--dry-run")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    order = ["日报", "编译", "订阅台账", "门户入口", "文档站"]
    idx = [out.find(x) for x in order]
    assert all(i >= 0 for i in idx), f"计划应含全部步骤:{out}"
    assert idx == sorted(idx), f"步骤顺序不对:{out}"


def test_dry_run_does_not_execute(tmp_path):
    # dry-run 不得产生副作用(不生成运行日志)
    r = _run("--dry-run")
    assert r.returncode == 0
    assert not (REPO / "browse" / ".update-all.log").exists()


def test_dry_run_marks_missing_tools(tmp_path):
    # PATH 指向空目录(dry-run 只用 shell 内建,无需外部二进制)、HOME 无 go/bin、
    # brew 前缀指到不存在目录(脚本默认把 /opt/homebrew/bin 补进 PATH,会泄露本机
    # 已装的 pandoc)→ sage-wiki / pandoc 都解析不到 → 两步都标"将跳过"
    import shutil
    onlybash = tmp_path / "onlybash"
    onlybash.mkdir()
    (onlybash / "bash").symlink_to(shutil.which("bash"))   # 只放 bash,sage-wiki/pandoc 解析不到
    env = {**os.environ, "PATH": str(onlybash), "HOME": str(tmp_path),
           "UPDATE_ALL_BREW_BIN": str(tmp_path / "no-brew")}
    r = _run("--dry-run", env=env)
    assert r.returncode == 0, r.stderr
    assert "缺 sage-wiki" in r.stdout, r.stdout
    assert "缺 pandoc" in r.stdout, r.stdout


def test_dry_run_marks_present_tools(tmp_path):
    # 造 sage-wiki / pandoc 桩放进 PATH → 两步都标"就绪"
    bind = tmp_path / "bin"
    bind.mkdir()
    for name in ("sage-wiki", "pandoc"):
        s = bind / name
        s.write_text("#!/bin/sh\nexit 0\n")
        s.chmod(0o755)
    env = {**os.environ, "PATH": f"{bind}:{_py_dir()}:/usr/bin:/bin", "HOME": str(tmp_path)}
    r = _run("--dry-run", env=env)
    assert r.returncode == 0, r.stderr
    assert "sage-wiki 就绪" in r.stdout and "pandoc 就绪" in r.stdout, r.stdout


def test_pull_flag_adds_step_zero():
    r = _run("--pull", "--dry-run")
    assert r.returncode == 0
    assert "git pull" in r.stdout and "拉取" in r.stdout


def test_no_pull_hints_optional():
    r = _run("--dry-run")
    assert "--pull" in r.stdout


def test_unknown_arg_usage_nonzero():
    r = _run("--bogus")
    assert r.returncode != 0
    assert "用法" in (r.stdout + r.stderr)


def test_daily_launchagent_plist_valid():
    # 每日自启的 LaunchAgent:XML/plist 合法、Label 正确、确实调 update-all.sh、每日定时
    import plistlib
    plist = REPO / "scripts" / "com.mind.update-all.plist"
    d = plistlib.loads(plist.read_bytes())
    assert d["Label"] == "com.mind.update-all"
    assert "StartCalendarInterval" in d, "须是定时(每日)而非 KeepAlive"
    assert any("update-all.sh" in a for a in d["ProgramArguments"]), "须调用 update-all.sh"
