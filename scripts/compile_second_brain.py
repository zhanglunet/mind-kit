#!/usr/bin/env python3
"""Cross-platform second-brain compile pipeline.

The POSIX ``compile.sh`` remains compatible; Windows calls this module through
``compile-second-brain.ps1``. No shell is required.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Callable


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _run(runner: Runner, argv: list[str], *, root: Path, capture: bool = False):
    return runner(
        argv, cwd=str(root), text=True,
        capture_output=capture,
    )


def _content_repo(root: Path, runner: Runner) -> Path:
    candidate = root / "_wiki"
    if candidate.exists():
        proc = runner(
            ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return Path(proc.stdout.strip())
    return root


def _commit_outputs(root: Path, python: Path, runner: Runner, message: str) -> int:
    repo = _content_repo(root, runner)
    validator = root / "scripts" / "validate_write_set.py"
    if validator.exists() and os.environ.get("VAULT_SKIP_VALIDATE") != "1":
        proc = _run(
            runner,
            [str(python), str(validator), "--vault", str(repo), "--git-changed", "--empty-ok"],
            root=root,
        )
        if proc.returncode != 0:
            return proc.returncode
    if runner(["git", "-C", str(repo), "add", "-A"]).returncode != 0:
        return 1
    staged = runner(["git", "-C", str(repo), "diff", "--cached", "--quiet"])
    if staged.returncode == 0:
        print("无改动可提交")
        return 0
    return runner(["git", "-C", str(repo), "commit", "-m", message]).returncode


def run_pipeline(
    *, root: Path, python: Path, compile_args: list[str], runner: Runner = subprocess.run,
    sage: str | None = None,
) -> int:
    root = root.resolve()
    sage = sage or shutil.which("sage-wiki")
    if not sage:
        print("✗ 找不到 sage-wiki；请先按安装指南安装编译引擎。", file=sys.stderr)
        return 3

    print("▶ 1/6 sage-wiki compile", flush=True)
    proc = _run(runner, [sage, "compile", *compile_args], root=root)
    if proc.returncode != 0:
        return proc.returncode
    if "--dry-run" in compile_args:
        print("✓ 估算完成；未写入 Wiki。")
        return 0

    failures = 0
    scripts = root / "scripts"
    print("▶ 2/6 OKF 合规注入", flush=True)
    if _run(runner, [str(python), str(scripts / "okf.py"), "--fix"], root=root).returncode:
        failures += 1

    print("▶ 3/6 重建索引", flush=True)
    if _run(runner, [str(python), str(scripts / "build-index.py")], root=root).returncode:
        failures += 1

    print("▶ 4/6 lint、保鲜与决策检查", flush=True)
    lint_dir = root / "reports" / "lint"
    lint_dir.mkdir(parents=True, exist_ok=True)
    lint_file = lint_dir / f"{date.today().isoformat()}.txt"
    lint = _run(runner, [sage, "lint"], root=root, capture=True)
    lint_text = "\n".join(
        line for line in ((lint.stdout or "") + (lint.stderr or "")).splitlines()
        if not (line.startswith("time=") and ("embedding" in line or "no embedding" in line))
    )
    lint_file.write_text(lint_text + ("\n" if lint_text else ""), encoding="utf-8")
    if lint_text:
        print(lint_text)
    if lint.returncode:
        failures += 1
    for argv in (
        [str(python), str(scripts / "freshness.py")],
        [str(python), str(scripts / "decision.py"), "check"],
        [str(python), str(scripts / "okf.py"), "--check"],
    ):
        extra = _run(runner, argv, root=root, capture=True)
        with lint_file.open("a", encoding="utf-8") as handle:
            handle.write((extra.stdout or "") + (extra.stderr or ""))

    log = root / "_wiki" / "log.md"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(f"\n## [{date.today().isoformat()}] lint ｜ 见 reports/lint/{lint_file.name}\n")

    print("▶ 5/6 生成本地浏览站", flush=True)
    if _run(runner, [str(python), str(scripts / "build-wiki-site.py")], root=root).returncode:
        print("⚠ 浏览站生成失败，不影响编译产物。", file=sys.stderr)

    print("▶ 6/6 提交内容库产物", flush=True)
    commit_rc = _commit_outputs(
        root, python, runner,
        f"post-compile: index 重建 + lint 记账 ({date.today().isoformat()})",
    )
    if commit_rc:
        return commit_rc
    if failures:
        print(f"⚠ 流水线完成，但有 {failures} 个检查失败。", file=sys.stderr)
        return 1
    print("✔ 流水线完成。")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="跨平台第二大脑编译流水线。")
    parser.add_argument("--dry-run", action="store_true", help="只估算，不写入")
    parser.add_argument("--self-check", action="store_true", help="检查跨平台编译入口")
    args, compile_args = parser.parse_known_args(argv)
    root = Path(__file__).resolve().parent.parent
    if args.self_check:
        required = [root / "scripts" / "compile_second_brain.py", root / "compile-second-brain.ps1"]
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            print("缺少文件: " + ", ".join(missing), file=sys.stderr)
            return 2
        print("Windows 原生编译入口自检通过。")
        return 0
    if args.dry_run:
        compile_args.append("--dry-run")
    return run_pipeline(root=root, python=Path(sys.executable), compile_args=compile_args)


if __name__ == "__main__":
    raise SystemExit(main())
