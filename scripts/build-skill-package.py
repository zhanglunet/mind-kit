#!/usr/bin/env python3
"""把 skills/workbuddy-second-brain/ 确定性打包成可分发的 WorkBuddy 技能包 zip。

为什么要有这个脚本(2026-08-14 的教训):技能包此前**只有二进制、没有源**,
于是它的内容既进不了 code review,也被 `test_publish_privacy.py` 的
`ALLOWED_OPAQUE` 豁免在禁忌词门禁之外——全仓唯一「有对外内容却对所有检查不可见」
的载体。v1.8 把六处文案改到 Vault-only 口径,唯独漏了它,正是因为没人看得见它。

**确定性**(同源必同字节)是这道设计的关键,否则 zip 每次构建都变,
`git diff` 全是噪音,「产物有没有跟上源」就又成了没人能验的事:

- 固定时间戳:zip 会记录 mtime,不固定则每次构建都不同
- 固定成员顺序:目录遍历顺序在不同文件系统上不一样
- **ZIP_STORED 不压缩**:deflate 的输出随 zlib 版本变化,而这几个文件总共几 KB,
  压缩收益还不如跨机器可复现来得值钱
- 固定权限位与 create_system:否则 umask 和平台差异会渗进字节

用法:
    python3 scripts/build-skill-package.py                 # 落到 site/downloads/
    python3 scripts/build-skill-package.py --out-dir DIR   # 落到别处(测试用)
    python3 scripts/build-skill-package.py --check         # 只校验产物是否跟上源
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "skills" / "workbuddy-second-brain"
DEFAULT_OUT = ROOT / "site" / "downloads"
MEMBERS = ("README.md", "SKILL.md", "skill.yaml")

# 任意固定值即可,只要跨机器一致(1980-01-01 是 zip 格式能表示的最早时间)
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
FIXED_MODE = 0o644 << 16
UNIX_CREATE_SYSTEM = 3


def read_version(source: Path = SOURCE) -> str:
    """版本号的单一来源是 skill.yaml;产物名由它推出,不在别处重复维护。"""
    meta = source / "skill.yaml"
    for line in meta.read_text(encoding="utf-8").splitlines():
        if line.startswith("version:"):
            version = line.split(":", 1)[1].strip()
            if not version:
                raise SystemExit(f"✗ {meta} 的 version 为空")
            return version
    raise SystemExit(f"✗ {meta} 缺 version 字段")


def package_name(source: Path = SOURCE) -> str:
    return f"workbuddy-second-brain-skill-v{read_version(source)}.zip"


def build_bytes(source: Path = SOURCE) -> bytes:
    """构建 zip 字节。同样的源必然产出同样的字节。"""
    missing = [name for name in MEMBERS if not (source / name).is_file()]
    if missing:
        raise SystemExit(f"✗ 技能包源缺文件:{', '.join(missing)}")

    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in MEMBERS:                      # 固定顺序,不依赖目录遍历
            info = zipfile.ZipInfo(name, date_time=FIXED_TIMESTAMP)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = FIXED_MODE
            info.create_system = UNIX_CREATE_SYSTEM
            archive.writestr(info, (source / name).read_bytes())
    return buffer.getvalue()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="确定性构建 WorkBuddy 技能包。")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true",
                        help="只校验已有产物是否与源一致,不写文件")
    args = parser.parse_args(argv)

    payload = build_bytes()
    target = args.out_dir / package_name()

    if args.check:
        if not target.is_file():
            print(f"✗ 缺产物:{target}", file=sys.stderr)
            return 1
        if target.read_bytes() != payload:
            print(f"✗ 产物与源不一致,请重新构建:{target}", file=sys.stderr)
            return 1
        print(f"✓ 产物与源一致:{target.name}")
        return 0

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stale = [p for p in args.out_dir.glob("workbuddy-second-brain-skill-v*.zip")
             if p.name != target.name]
    target.write_bytes(payload)
    for old in stale:                              # 两个版本并存 = 用户下到哪个全看运气
        old.unlink()
        print(f"  − 移除旧版本:{old.name}")
    print(f"✓ 已构建:{target.relative_to(ROOT) if target.is_relative_to(ROOT) else target}"
          f"({len(payload)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
