# scripts/larklib.py — lark-cli 调用的统一入口:多账号注入 + 数据根定位。
#
# 为什么必须有这层(实测结论,2026-08-04):
#   lark-cli 有 profile 体系(profile add/use/list、全局旗标 --profile),
#   但**不读任何环境变量**(LARK_CLI_PROFILE / LARK_PROFILE 实测均被忽略)。
#   所以要同步第二个飞书账号,只能由调用方显式传 --profile。
#
# 用法:
#   - 同步脚本一律 `larklib.lark_argv([...])` 拼命令,不要直接写 ["lark-cli", ...]
#     (tests/test_larklib.py 有扫描门禁,绕开会被拦)
#   - 数据落盘根一律 `larklib.feishu_root(VAULT)`,不要硬编码 raw/private/feishu
#
# 环境变量:
#   MIND_LARK_PROFILE   非空时给每次 lark-cli 调用注入 --profile <值>
#   MIND_FEISHU_HOME    非空时替代默认数据根 raw/private/feishu
#
# 账号 2 接入(人工两步,见 docs/dev-log.md 2026-08-04 条目):
#   lark-cli profile add --name acct2 --app-id <账号2租户的自建应用 app-id>
#   lark-cli --profile acct2 auth login   # 扫码授权
import os
import shutil
from pathlib import Path


def lark_argv(args, profile=None):
    """拼 lark-cli 命令。

    profile=None 时沿用 MIND_LARK_PROFILE；显式传字符串时由调用方选择 profile，
    传空字符串可明确使用默认配置。全局旗标始终放在子命令之前。
    """
    if profile is None:
        profile = os.environ.get("MIND_LARK_PROFILE", "")
    profile = str(profile).strip()
    executable = "lark-cli"
    if os.name == "nt":
        executable = shutil.which("lark-cli") or shutil.which("lark-cli.cmd") or executable
    return [executable] + (["--profile", profile] if profile else []) + list(args)


def feishu_root(vault: Path) -> Path:
    """飞书数据落盘根:MIND_FEISHU_HOME 非空时取之,否则默认 raw/private/feishu。"""
    override = os.environ.get("MIND_FEISHU_HOME", "").strip()
    return Path(override) if override else Path(vault) / "raw" / "private" / "feishu"
