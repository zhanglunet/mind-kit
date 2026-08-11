#!/usr/bin/env python3
"""Cross-platform, non-destructive second-brain Vault initializer."""

from __future__ import annotations

import argparse
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


DIRS = (
    "_wiki/concepts", "_wiki/summaries", "_wiki/entities", "_wiki/outputs",
    "material/quotes", "material/stories", "material/references", "material/cases",
    "material/frameworks", "material/data", "raw/clippings", "raw/todo",
    "raw/archive/clippings", "raw/flomo/delta", "raw/pdfs", "raw/assets",
    "raw/private/feishu", "writing", "reports/daily", "reports/weekly", "reports/lint",
)
LINKS = (
    "_wiki", "material", "raw", "writing",
    "reports/daily", "reports/weekly", "reports/lint",
)

INDEX_SEED = """# 内容导航 Index

> sage-wiki 每次编译后自动更新本文件。按分类列出所有页面 + 单行摘要 + 来源数量。
> 查询时**先读这里**，再深入相关页面。

## 概念 Concepts

## 摘要 Summaries

## 实体 Entities

## 产出 Outputs
"""
LOG_SEED = """# 时序日志 Log

> 只追加，记录每次 ingest / query / lint。格式：`## [日期] 类型 ｜ 标题`
"""
GITIGNORE_SEED = """# 凭证与机器状态
.env
.env.*
*.key
secrets.*
.DS_Store
Thumbs.db

# 私密冷存与大体积文件
raw/private
raw/_hoard/
raw/assets/
raw/**/*.pdf
raw/**/*.docx
raw/**/*.xlsx
raw/**/*.pptx
raw/**/*.zip
raw/**/*.png
raw/**/*.jpg
raw/**/*.mp4

# 引擎中间产物
_wiki/under_review/
.sage/
.manifest.json
"""


@dataclass
class InitResult:
    vault: Path
    created: list[str]
    preserved: list[str]
    skipped: list[str]


def _seed(path: Path, content: str, result: InitResult) -> None:
    if path.exists():
        result.preserved.append(str(path.relative_to(result.vault)))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    result.created.append(str(path.relative_to(result.vault)))


def _same_target(target: Path, source: Path) -> bool:
    try:
        return target.resolve() == source.resolve()
    except OSError:
        return False


def _link_directory(target: Path, source: Path, *, platform: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if platform == "nt":
        # Directory junctions work without Developer Mode or administrator rights.
        proc = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(target), str(source)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise OSError(proc.stderr.strip() or proc.stdout.strip() or "mklink /J failed")
    else:
        target.symlink_to(source, target_is_directory=True)


def initialize(
    *, vault: Path, repo: Path, create_links: bool = True, init_git: bool = True,
    dry_run: bool = False, platform: str | None = None,
) -> InitResult:
    vault = vault.expanduser().resolve()
    repo = repo.expanduser().resolve()
    result = InitResult(vault=vault, created=[], preserved=[], skipped=[])
    platform = platform or os.name
    if dry_run:
        return result

    vault.mkdir(parents=True, exist_ok=True)
    for rel in DIRS:
        directory = vault / rel
        directory.mkdir(parents=True, exist_ok=True)
        keep = directory / ".gitkeep"
        if not keep.exists():
            keep.touch()

    _seed(vault / "_wiki/index.md", INDEX_SEED, result)
    _seed(vault / "_wiki/log.md", LOG_SEED, result)
    _seed(vault / ".gitignore", GITIGNORE_SEED, result)

    if init_git and not (vault / ".git").exists():
        subprocess.run(["git", "-C", str(vault), "init", "-q"], check=True)

    if create_links:
        for rel in LINKS:
            source, target = vault / rel, repo / rel
            if target.exists() or target.is_symlink():
                if _same_target(target, source):
                    result.preserved.append(rel)
                else:
                    result.skipped.append(rel)
                continue
            _link_directory(target, source, platform=platform)
            result.created.append(rel)
    return result


def main(argv=None) -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="跨平台初始化第二大脑内容库。")
    parser.add_argument("--vault", type=Path, default=root.parent / "mind-vault")
    parser.add_argument("--repo", type=Path, default=root)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-git", action="store_true")
    parser.add_argument("--no-link", action="store_true")
    args = parser.parse_args(argv)
    result = initialize(
        vault=args.vault, repo=args.repo, create_links=not args.no_link,
        init_git=not args.no_git, dry_run=args.dry_run,
    )
    if args.dry_run:
        print(f"计划：在 {args.vault} 建内容库，并连接到 {args.repo}")
        return 0
    print(f"✓ 内容库就绪：{result.vault}")
    if result.skipped:
        print("⚠ 以下路径已有其他文件或目录，未覆盖：" + ", ".join(result.skipped))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
